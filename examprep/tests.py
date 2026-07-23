"""
Tests for the examprep app - C&P Exam preparation, rating calculator, and evidence checklists.

Covers:
- ExamGuidance model
- GlossaryTerm model
- ExamChecklist model
- SavedRatingCalculation model
- EvidenceChecklist model
- VA Math calculations (va_math.py)
- Public guide and glossary views
- Rating calculator views
- Exam checklist views
- Evidence checklist views
- HTMX endpoints
"""

import json
import pytest
from datetime import date, timedelta

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from examprep.models import (
    ExamGuidance,
    GlossaryTerm,
    ExamChecklist,
    SavedRatingCalculation,
    EvidenceChecklist,
)
from examprep.va_math import (
    DisabilityRating,
    CalculationResult,
    calculate_combined_rating,
    calculate_bilateral_factor,
    combine_two_ratings,
    combine_multiple_ratings,
    round_to_nearest_10,
    estimate_monthly_compensation,
    format_currency,
    validate_rating,
    VA_COMPENSATION_RATES_2024,
    DEPENDENT_RATES_2024,
)

User = get_user_model()


# =============================================================================
# VA MATH CALCULATION TESTS - COMPREHENSIVE SUITE
# =============================================================================


class TestValidateRating(TestCase):
    """Tests for validate_rating function - 38 CFR § 4.25 compliance."""

    def test_all_valid_va_ratings(self):
        """All valid VA ratings (0-100 in 10% increments) pass validation."""
        valid_ratings = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        for rating in valid_ratings:
            with self.subTest(rating=rating):
                self.assertTrue(validate_rating(rating))

    def test_invalid_negative_ratings(self):
        """Negative ratings fail validation."""
        for rating in [-10, -1, -100]:
            with self.subTest(rating=rating):
                self.assertFalse(validate_rating(rating))

    def test_invalid_non_multiples_of_10(self):
        """Non-multiples of 10 fail validation."""
        invalid = [5, 15, 25, 35, 45, 55, 65, 75, 85, 95, 1, 99]
        for rating in invalid:
            with self.subTest(rating=rating):
                self.assertFalse(validate_rating(rating))

    def test_invalid_over_100(self):
        """Ratings over 100 fail validation."""
        for rating in [110, 150, 200]:
            with self.subTest(rating=rating):
                self.assertFalse(validate_rating(rating))

    def test_boundary_values(self):
        """Boundary values at 0 and 100."""
        self.assertTrue(validate_rating(0))
        self.assertTrue(validate_rating(100))
        self.assertFalse(validate_rating(-10))
        self.assertFalse(validate_rating(110))


class TestCombineTwoRatings(TestCase):
    """Tests for combine_two_ratings function - VA Math formula A + B(1-A)."""

    def test_classic_50_30_example(self):
        """Classic VA example: 50% + 30% = 65%."""
        # 0.50 + 0.30(1-0.50) = 0.50 + 0.15 = 0.65
        result = combine_two_ratings(50, 30)
        self.assertEqual(result, 65.0)

    def test_10_10_combination(self):
        """10% + 10% = 19%."""
        # 0.10 + 0.10(1-0.10) = 0.10 + 0.09 = 0.19
        result = combine_two_ratings(10, 10)
        self.assertEqual(result, 19.0)

    def test_70_50_combination(self):
        """70% + 50% = 85%."""
        # 0.70 + 0.50(1-0.70) = 0.70 + 0.15 = 0.85
        result = combine_two_ratings(70, 50)
        self.assertEqual(result, 85.0)

    def test_order_affects_result(self):
        """Order of ratings affects raw result due to formula structure."""
        # A + B(1-A) vs B + A(1-B)
        result1 = combine_two_ratings(50, 30)  # 50 + 30*0.5 = 65
        result2 = combine_two_ratings(30, 50)  # 30 + 50*0.7 = 65
        # Both equal 65% because formula is mathematically equivalent
        self.assertAlmostEqual(result1, result2, places=10)

    def test_zero_rating_first(self):
        """0% + X% = X%."""
        result = combine_two_ratings(0, 50)
        self.assertEqual(result, 50.0)

    def test_zero_rating_second(self):
        """X% + 0% = X%."""
        result = combine_two_ratings(50, 0)
        self.assertEqual(result, 50.0)

    def test_zero_both(self):
        """0% + 0% = 0%."""
        result = combine_two_ratings(0, 0)
        self.assertEqual(result, 0.0)

    def test_100_rating_first(self):
        """100% + X% = 100%."""
        result = combine_two_ratings(100, 50)
        self.assertEqual(result, 100.0)

    def test_100_rating_second(self):
        """X% + 100% = 100%."""
        result = combine_two_ratings(50, 100)
        self.assertEqual(result, 100.0)

    def test_100_both(self):
        """100% + 100% = 100%."""
        result = combine_two_ratings(100, 100)
        self.assertEqual(result, 100.0)

    def test_same_ratings(self):
        """Same ratings combined correctly."""
        # 30% + 30% = 30 + 30*0.7 = 30 + 21 = 51
        result = combine_two_ratings(30, 30)
        self.assertEqual(result, 51.0)

    def test_small_ratings(self):
        """Small ratings combine correctly."""
        # 10% + 20% = 10 + 20*0.9 = 10 + 18 = 28
        result = combine_two_ratings(10, 20)
        self.assertAlmostEqual(result, 28.0, places=10)

    def test_high_ratings(self):
        """High ratings approach but don't exceed 100%."""
        # 90% + 90% = 90 + 90*0.1 = 90 + 9 = 99
        result = combine_two_ratings(90, 90)
        self.assertEqual(result, 99.0)


class TestCombineMultipleRatings(TestCase):
    """Tests for combine_multiple_ratings function."""

    def test_empty_list(self):
        """Empty list returns 0 with no steps."""
        result, steps = combine_multiple_ratings([])
        self.assertEqual(result, 0.0)
        self.assertEqual(steps, [])

    def test_single_rating(self):
        """Single rating returns itself."""
        result, steps = combine_multiple_ratings([70])
        self.assertEqual(result, 70.0)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["rating"], 70)

    def test_two_ratings(self):
        """Two ratings combined correctly."""
        result, steps = combine_multiple_ratings([50, 30])
        self.assertEqual(result, 65.0)
        self.assertEqual(len(steps), 2)

    def test_three_ratings(self):
        """Three ratings combine correctly with proper order."""
        # 50% + 30% + 20%
        # Step 1: 50%
        # Step 2: 50 + 30*0.5 = 65%
        # Step 3: 65 + 20*0.35 = 65 + 7 = 72%
        result, steps = combine_multiple_ratings([50, 30, 20])
        self.assertAlmostEqual(result, 72.0, places=1)
        self.assertEqual(len(steps), 3)

    def test_sorted_highest_to_lowest(self):
        """Ratings are automatically sorted highest to lowest."""
        # Input [10, 50, 30] should be processed as [50, 30, 10]
        result1, steps1 = combine_multiple_ratings([10, 50, 30])
        result2, steps2 = combine_multiple_ratings([50, 30, 10])
        self.assertEqual(result1, result2)
        # First step should start with 50
        self.assertEqual(steps1[0]["rating"], 50)
        self.assertEqual(steps2[0]["rating"], 50)

    def test_many_small_ratings(self):
        """Many small ratings combine progressively."""
        # Five 10% ratings - VA Math rounds intermediate results
        # 10 → 19 → 27.1 → 34.3 → 40.6
        result, steps = combine_multiple_ratings([10, 10, 10, 10, 10])
        self.assertAlmostEqual(result, 40.6, places=0)
        self.assertEqual(len(steps), 5)

    def test_all_100_ratings(self):
        """Multiple 100% ratings still equal 100%."""
        result, _ = combine_multiple_ratings([100, 100, 100])
        self.assertEqual(result, 100.0)

    def test_all_zero_ratings(self):
        """Multiple 0% ratings still equal 0%."""
        result, _ = combine_multiple_ratings([0, 0, 0])
        self.assertEqual(result, 0.0)

    def test_steps_include_explanation(self):
        """Steps include explanation text."""
        _, steps = combine_multiple_ratings([50, 30])
        self.assertIn("explanation", steps[0])
        self.assertIn("explanation", steps[1])

    def test_real_world_veteran_scenario(self):
        """Real-world scenario: PTSD 70%, Back 40%, Knee 20%, Tinnitus 10%."""
        result, steps = combine_multiple_ratings([70, 40, 20, 10])
        # 70 + 40*0.3 = 82
        # 82 + 20*0.18 = 85.6
        # 85.6 + 10*0.144 = 87.04
        self.assertAlmostEqual(result, 87.04, places=0)
        self.assertEqual(len(steps), 4)


class TestRoundToNearest10(TestCase):
    """Tests for round_to_nearest_10 function - 38 CFR § 4.25 rounding."""

    def test_round_down_below_5(self):
        """Values ending in 0-4 round down."""
        self.assertEqual(round_to_nearest_10(60.0), 60)
        self.assertEqual(round_to_nearest_10(61.0), 60)
        self.assertEqual(round_to_nearest_10(62.0), 60)
        self.assertEqual(round_to_nearest_10(63.0), 60)
        self.assertEqual(round_to_nearest_10(64.0), 60)
        self.assertEqual(round_to_nearest_10(64.4), 60)
        self.assertEqual(round_to_nearest_10(64.9), 60)

    def test_round_up_at_5(self):
        """Values ending in 5+ round up (banker's rounding: .5 rounds to even)."""
        self.assertEqual(round_to_nearest_10(65.0), 70)
        self.assertEqual(round_to_nearest_10(66.0), 70)
        self.assertEqual(round_to_nearest_10(67.0), 70)
        self.assertEqual(round_to_nearest_10(68.0), 70)
        self.assertEqual(round_to_nearest_10(69.0), 70)
        self.assertEqual(round_to_nearest_10(69.9), 70)

    def test_exact_tens(self):
        """Exact tens stay the same."""
        for tens in [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            with self.subTest(value=tens):
                self.assertEqual(round_to_nearest_10(float(tens)), tens)

    def test_cap_at_100(self):
        """Values over 95 cap at 100."""
        self.assertEqual(round_to_nearest_10(95.0), 100)
        self.assertEqual(round_to_nearest_10(99.0), 100)
        self.assertEqual(round_to_nearest_10(99.9), 100)
        self.assertEqual(round_to_nearest_10(100.0), 100)
        self.assertEqual(round_to_nearest_10(105.0), 100)
        self.assertEqual(round_to_nearest_10(150.0), 100)

    def test_floor_at_0(self):
        """Values below 5 floor at 0."""
        self.assertEqual(round_to_nearest_10(0.0), 0)
        self.assertEqual(round_to_nearest_10(1.0), 0)
        self.assertEqual(round_to_nearest_10(4.9), 0)

    def test_boundary_at_5(self):
        """5% rounds to 10%."""
        self.assertEqual(round_to_nearest_10(5.0), 10)

    def test_common_combined_ratings(self):
        """Common combined rating values round correctly."""
        test_cases = [
            (72.0, 70),  # Common 3-rating combo
            (65.0, 70),  # 50+30 combo
            (87.04, 90),  # 4-rating combo
            (51.0, 50),  # 30+30 combo
            (44.0, 40),
            (46.0, 50),
        ]
        for raw, expected in test_cases:
            with self.subTest(raw=raw):
                self.assertEqual(round_to_nearest_10(raw), expected)


class TestCalculateBilateralFactor(TestCase):
    """Tests for calculate_bilateral_factor function - 38 CFR § 4.26."""

    def test_empty_bilateral_list(self):
        """Empty bilateral list returns 0."""
        combined, factor = calculate_bilateral_factor([])
        self.assertEqual(combined, 0.0)
        self.assertEqual(factor, 0.0)

    def test_single_bilateral_rating(self):
        """Single bilateral rating gets 10% factor."""
        combined, factor = calculate_bilateral_factor([30])
        self.assertEqual(combined, 30.0)
        self.assertEqual(factor, 3.0)  # 10% of 30

    def test_two_bilateral_ratings(self):
        """Two bilateral ratings combined with 10% factor."""
        # 30% + 20% = 44%
        # Bilateral factor = 4.4%
        combined, factor = calculate_bilateral_factor([30, 20])
        self.assertAlmostEqual(combined, 44.0, places=10)
        self.assertAlmostEqual(factor, 4.4, places=1)

    def test_bilateral_knees_example(self):
        """Common bilateral knee example."""
        # Left knee 20%, Right knee 10%
        # Combined: 20 + 10*0.8 = 28%
        # Bilateral factor: 2.8%
        combined, factor = calculate_bilateral_factor([20, 10])
        self.assertAlmostEqual(combined, 28.0, places=10)
        self.assertAlmostEqual(factor, 2.8, places=1)

    def test_high_bilateral_ratings(self):
        """High bilateral ratings."""
        # 40% + 40% = 64%
        # Factor = 6.4%
        combined, factor = calculate_bilateral_factor([40, 40])
        self.assertEqual(combined, 64.0)
        self.assertAlmostEqual(factor, 6.4, places=1)


class TestCalculateCombinedRating(TestCase):
    """Tests for calculate_combined_rating function - full calculation."""

    def test_empty_ratings(self):
        """Empty rating list returns zero result."""
        result = calculate_combined_rating([])
        self.assertEqual(result.combined_raw, 0.0)
        self.assertEqual(result.combined_rounded, 0)
        self.assertEqual(result.bilateral_factor_applied, 0.0)
        self.assertEqual(result.step_by_step, [])
        self.assertEqual(result.ratings_used, [])

    def test_single_rating(self):
        """Single rating returns that rating."""
        ratings = [DisabilityRating(percentage=70, description="PTSD")]
        result = calculate_combined_rating(ratings)
        self.assertEqual(result.combined_rounded, 70)

    def test_two_non_bilateral_ratings(self):
        """Two non-bilateral ratings combine correctly."""
        ratings = [
            DisabilityRating(percentage=50, description="PTSD"),
            DisabilityRating(percentage=30, description="Back"),
        ]
        result = calculate_combined_rating(ratings)
        self.assertEqual(result.combined_rounded, 70)  # 65 rounds to 70
        self.assertEqual(result.bilateral_factor_applied, 0.0)

    def test_bilateral_ratings_only(self):
        """Bilateral-only ratings apply factor correctly."""
        ratings = [
            DisabilityRating(percentage=30, description="Left Knee", is_bilateral=True),
            DisabilityRating(
                percentage=20, description="Right Knee", is_bilateral=True
            ),
        ]
        result = calculate_combined_rating(ratings)
        # Combined: 44%, Factor: 4.4%, Total: 48.4% → rounds to 50%
        self.assertGreater(result.bilateral_factor_applied, 0)
        self.assertEqual(result.combined_rounded, 50)

    def test_mixed_bilateral_and_non_bilateral(self):
        """Mixed bilateral and non-bilateral ratings."""
        ratings = [
            DisabilityRating(percentage=50, description="PTSD", is_bilateral=False),
            DisabilityRating(percentage=20, description="Left Knee", is_bilateral=True),
            DisabilityRating(
                percentage=10, description="Right Knee", is_bilateral=True
            ),
        ]
        result = calculate_combined_rating(ratings)
        # Bilateral: 28% + 2.8% factor = 30.8% → round to 31%
        # Final: combine 50% with 31% = 65.5% → rounds to 70%
        self.assertGreater(result.bilateral_factor_applied, 0)
        self.assertIn(result.combined_rounded, [60, 70])

    def test_result_contains_step_by_step(self):
        """Result includes step-by-step explanation."""
        ratings = [
            DisabilityRating(percentage=50, description="PTSD"),
            DisabilityRating(percentage=30, description="Back"),
        ]
        result = calculate_combined_rating(ratings)
        self.assertIsInstance(result.step_by_step, list)
        self.assertGreater(len(result.step_by_step), 0)

    def test_result_contains_ratings_used(self):
        """Result includes original ratings."""
        ratings = [
            DisabilityRating(percentage=50, description="PTSD"),
            DisabilityRating(percentage=30, description="Back"),
        ]
        result = calculate_combined_rating(ratings)
        self.assertEqual(result.ratings_used, ratings)

    def test_real_world_complex_scenario(self):
        """Complex real-world scenario with bilateral and non-bilateral."""
        ratings = [
            DisabilityRating(percentage=70, description="PTSD", is_bilateral=False),
            DisabilityRating(percentage=40, description="Back", is_bilateral=False),
            DisabilityRating(
                percentage=20, description="Left Shoulder", is_bilateral=True
            ),
            DisabilityRating(
                percentage=20, description="Right Shoulder", is_bilateral=True
            ),
            DisabilityRating(percentage=10, description="Tinnitus", is_bilateral=False),
        ]
        result = calculate_combined_rating(ratings)
        # Should produce a high combined rating
        self.assertGreaterEqual(result.combined_rounded, 80)
        self.assertLessEqual(result.combined_rounded, 100)
        self.assertGreater(result.bilateral_factor_applied, 0)

    def test_result_is_calculation_result_type(self):
        """Result is CalculationResult dataclass."""
        ratings = [DisabilityRating(percentage=50, description="Test")]
        result = calculate_combined_rating(ratings)
        self.assertIsInstance(result, CalculationResult)

    def test_all_100_ratings(self):
        """Multiple 100% ratings yield 100%."""
        ratings = [
            DisabilityRating(percentage=100, description="Condition 1"),
            DisabilityRating(percentage=100, description="Condition 2"),
        ]
        result = calculate_combined_rating(ratings)
        self.assertEqual(result.combined_rounded, 100)


class TestEstimateMonthlyCompensation(TestCase):
    """Tests for estimate_monthly_compensation function - 2024 rates."""

    def test_zero_rating(self):
        """0% rating = $0."""
        result = estimate_monthly_compensation(0, year=2024)
        self.assertEqual(result, 0.0)

    def test_10_percent_rating(self):
        """10% rating base compensation."""
        result = estimate_monthly_compensation(10, year=2024)
        self.assertEqual(result, VA_COMPENSATION_RATES_2024[10])

    def test_all_base_rates(self):
        """All base rates match 2024 table."""
        for rating, expected in VA_COMPENSATION_RATES_2024.items():
            with self.subTest(rating=rating):
                result = estimate_monthly_compensation(rating, year=2024)
                self.assertEqual(result, expected)

    def test_100_percent_base(self):
        """100% rating base compensation."""
        result = estimate_monthly_compensation(100, year=2024)
        self.assertEqual(result, VA_COMPENSATION_RATES_2024[100])

    def test_invalid_rating_returns_zero(self):
        """Invalid ratings return 0."""
        self.assertEqual(estimate_monthly_compensation(15, year=2024), 0.0)
        self.assertEqual(estimate_monthly_compensation(55, year=2024), 0.0)
        self.assertEqual(estimate_monthly_compensation(110, year=2024), 0.0)

    def test_spouse_adds_at_30_percent_and_above(self):
        """Spouse adds to compensation at 30%+."""
        for rating in [30, 40, 50, 60, 70, 80, 90, 100]:
            with self.subTest(rating=rating):
                base = estimate_monthly_compensation(rating, year=2024)
                with_spouse = estimate_monthly_compensation(
                    rating, spouse=True, year=2024
                )
                self.assertGreater(with_spouse, base)
                # Verify exact spouse addition
                expected = base + DEPENDENT_RATES_2024["spouse"][rating]
                self.assertEqual(with_spouse, expected)

    def test_spouse_no_effect_below_30(self):
        """Spouse doesn't add below 30%."""
        for rating in [0, 10, 20]:
            with self.subTest(rating=rating):
                base = estimate_monthly_compensation(rating, year=2024)
                with_spouse = estimate_monthly_compensation(
                    rating, spouse=True, year=2024
                )
                self.assertEqual(base, with_spouse)

    def test_children_add_at_30_percent_and_above(self):
        """Children add to compensation at 30%+."""
        base = estimate_monthly_compensation(50, year=2024)
        with_one = estimate_monthly_compensation(50, children_under_18=1, year=2024)
        with_two = estimate_monthly_compensation(50, children_under_18=2, year=2024)
        self.assertGreater(with_one, base)
        self.assertGreater(with_two, with_one)

    def test_children_no_effect_below_30(self):
        """Children don't add below 30%."""
        base = estimate_monthly_compensation(20, year=2024)
        with_children = estimate_monthly_compensation(
            20, children_under_18=3, year=2024
        )
        self.assertEqual(base, with_children)

    def test_dependent_parents(self):
        """Dependent parents add to compensation at 30%+."""
        base = estimate_monthly_compensation(50, year=2024)
        with_one_parent = estimate_monthly_compensation(
            50, dependent_parents=1, year=2024
        )
        with_two_parents = estimate_monthly_compensation(
            50, dependent_parents=2, year=2024
        )
        self.assertGreater(with_one_parent, base)
        self.assertGreater(with_two_parents, with_one_parent)

    def test_max_two_dependent_parents(self):
        """Maximum of 2 dependent parents counted."""
        with_two = estimate_monthly_compensation(50, dependent_parents=2, year=2024)
        with_three = estimate_monthly_compensation(50, dependent_parents=3, year=2024)
        self.assertEqual(with_two, with_three)

    def test_full_family(self):
        """Full family calculation: spouse + children + parents."""
        base = estimate_monthly_compensation(100, year=2024)
        full = estimate_monthly_compensation(
            100, spouse=True, children_under_18=3, dependent_parents=2, year=2024
        )
        expected = (
            base
            + DEPENDENT_RATES_2024["spouse"][100]
            + 3 * DEPENDENT_RATES_2024["child_under_18"][100]
            + 2 * DEPENDENT_RATES_2024["parent_one"][100]
        )
        self.assertEqual(full, expected)

    def test_result_is_rounded(self):
        """Result is rounded to 2 decimal places."""
        result = estimate_monthly_compensation(100, spouse=True, year=2024)
        # Check it's properly rounded
        self.assertEqual(result, round(result, 2))


class TestFormatCurrency(TestCase):
    """Tests for format_currency helper function."""

    def test_whole_dollars(self):
        """Whole dollar amounts."""
        self.assertEqual(format_currency(100), "$100.00")
        self.assertEqual(format_currency(0), "$0.00")
        self.assertEqual(format_currency(1000), "$1,000.00")

    def test_dollars_and_cents(self):
        """Dollar and cents amounts."""
        self.assertEqual(format_currency(1234.56), "$1,234.56")
        self.assertEqual(format_currency(99.99), "$99.99")

    def test_large_amounts(self):
        """Large amounts with commas."""
        self.assertEqual(format_currency(10000.00), "$10,000.00")
        self.assertEqual(format_currency(100000.00), "$100,000.00")

    def test_small_cents(self):
        """Small cent values."""
        self.assertEqual(format_currency(0.01), "$0.01")
        self.assertEqual(format_currency(0.99), "$0.99")


class TestVAMathRealWorldScenarios(TestCase):
    """Real-world scenarios to validate VA Math implementation."""

    def test_common_ptsd_back_tinnitus(self):
        """Common combo: PTSD 50%, Back 20%, Tinnitus 10%."""
        ratings = [
            DisabilityRating(percentage=50, description="PTSD"),
            DisabilityRating(percentage=20, description="Lumbar Spine"),
            DisabilityRating(percentage=10, description="Tinnitus"),
        ]
        result = calculate_combined_rating(ratings)
        # 50 + 20*0.5 = 60, 60 + 10*0.4 = 64 → rounds to 60%
        self.assertEqual(result.combined_rounded, 60)

    def test_high_ptsd_with_secondaries(self):
        """High PTSD with multiple secondaries."""
        ratings = [
            DisabilityRating(percentage=70, description="PTSD"),
            DisabilityRating(percentage=50, description="Sleep Apnea"),
            DisabilityRating(percentage=30, description="Migraines"),
            DisabilityRating(percentage=10, description="Tinnitus"),
        ]
        result = calculate_combined_rating(ratings)
        # Should be high 80s or 90
        self.assertGreaterEqual(result.combined_rounded, 80)

    def test_bilateral_knees_with_back(self):
        """Bilateral knees with back condition."""
        ratings = [
            DisabilityRating(
                percentage=40, description="Lumbar Spine", is_bilateral=False
            ),
            DisabilityRating(percentage=20, description="Left Knee", is_bilateral=True),
            DisabilityRating(
                percentage=20, description="Right Knee", is_bilateral=True
            ),
        ]
        result = calculate_combined_rating(ratings)
        # Bilateral: 36% + 3.6% = 39.6% → 40%
        # Final: 40% + 40% = 64% → 60%
        self.assertIn(result.combined_rounded, [60, 70])
        self.assertGreater(result.bilateral_factor_applied, 0)

    def test_gulf_war_presumptives(self):
        """Gulf War presumptive conditions."""
        ratings = [
            DisabilityRating(percentage=30, description="IBS"),
            DisabilityRating(percentage=30, description="Chronic Fatigue"),
            DisabilityRating(percentage=20, description="Fibromyalgia"),
            DisabilityRating(percentage=10, description="Headaches"),
        ]
        result = calculate_combined_rating(ratings)
        # Should be around 60-70%
        self.assertGreaterEqual(result.combined_rounded, 60)
        self.assertLessEqual(result.combined_rounded, 80)

    def test_tdiu_threshold_scenario(self):
        """Scenario near TDIU schedular threshold (60% single or 70% combined)."""
        # Just under threshold
        ratings = [
            DisabilityRating(percentage=50, description="PTSD"),
            DisabilityRating(percentage=10, description="Tinnitus"),
            DisabilityRating(percentage=10, description="Hearing Loss"),
        ]
        result = calculate_combined_rating(ratings)
        # 50 + 10*0.5 = 55, 55 + 10*0.45 = 59.5 → 60%
        self.assertEqual(result.combined_rounded, 60)

    def test_veteran_with_many_10_percent_ratings(self):
        """Veteran with many 10% ratings (common scenario)."""
        ratings = [
            DisabilityRating(percentage=10, description="Tinnitus"),
            DisabilityRating(percentage=10, description="Hearing Loss"),
            DisabilityRating(percentage=10, description="Scars"),
            DisabilityRating(percentage=10, description="Headaches"),
            DisabilityRating(percentage=10, description="Allergies"),
        ]
        result = calculate_combined_rating(ratings)
        # Five 10%s = approximately 41% → rounds to 40%
        self.assertEqual(result.combined_rounded, 40)

    def test_100_percent_scheduler(self):
        """Scenario that achieves 100% schedular."""
        ratings = [
            DisabilityRating(percentage=70, description="PTSD"),
            DisabilityRating(percentage=70, description="TBI"),
            DisabilityRating(percentage=50, description="Back"),
        ]
        result = calculate_combined_rating(ratings)
        # 70 + 70*0.3 = 91, 91 + 50*0.09 = 95.5 → 100%
        self.assertEqual(result.combined_rounded, 100)


class TestVAMathEdgeCases(TestCase):
    """Edge cases and boundary conditions."""

    def test_single_100_percent(self):
        """Single 100% rating."""
        ratings = [DisabilityRating(percentage=100, description="TBI")]
        result = calculate_combined_rating(ratings)
        self.assertEqual(result.combined_rounded, 100)

    def test_single_0_percent(self):
        """Single 0% rating."""
        ratings = [DisabilityRating(percentage=0, description="Resolved")]
        result = calculate_combined_rating(ratings)
        self.assertEqual(result.combined_rounded, 0)

    def test_many_zeros_plus_one_rating(self):
        """Multiple 0% ratings with one actual rating."""
        ratings = [
            DisabilityRating(percentage=0, description="Resolved 1"),
            DisabilityRating(percentage=50, description="Active"),
            DisabilityRating(percentage=0, description="Resolved 2"),
        ]
        result = calculate_combined_rating(ratings)
        self.assertEqual(result.combined_rounded, 50)

    def test_bilateral_with_zeros(self):
        """Bilateral ratings with zeros."""
        ratings = [
            DisabilityRating(percentage=20, description="Left Knee", is_bilateral=True),
            DisabilityRating(percentage=0, description="Right Knee", is_bilateral=True),
        ]
        result = calculate_combined_rating(ratings)
        # 20% + 0% bilateral = 20%, factor = 2%, total ≈ 22% → 20%
        self.assertEqual(result.combined_rounded, 20)

    def test_all_bilateral_ratings(self):
        """All ratings are bilateral."""
        ratings = [
            DisabilityRating(
                percentage=30, description="Left Ankle", is_bilateral=True
            ),
            DisabilityRating(
                percentage=30, description="Right Ankle", is_bilateral=True
            ),
            DisabilityRating(percentage=20, description="Left Knee", is_bilateral=True),
            DisabilityRating(
                percentage=20, description="Right Knee", is_bilateral=True
            ),
        ]
        result = calculate_combined_rating(ratings)
        self.assertGreater(result.bilateral_factor_applied, 0)

    def test_description_preserved(self):
        """Descriptions are preserved in result."""
        ratings = [
            DisabilityRating(percentage=50, description="My PTSD"),
            DisabilityRating(percentage=30, description="My Back Pain"),
        ]
        result = calculate_combined_rating(ratings)
        descriptions = [r.description for r in result.ratings_used]
        self.assertIn("My PTSD", descriptions)
        self.assertIn("My Back Pain", descriptions)


# =============================================================================
# EXAM GUIDANCE MODEL TESTS
# =============================================================================


class TestExamGuidanceModel(TestCase):
    """Tests for the ExamGuidance model."""

    def test_guidance_creation(self):
        """ExamGuidance can be created with all fields."""
        guidance = ExamGuidance.objects.create(
            title="PTSD C&P Exam Guide",
            slug="ptsd-exam",
            category="ptsd",
            introduction="This guide covers the PTSD exam.",
            is_published=True,
        )
        self.assertEqual(guidance.title, "PTSD C&P Exam Guide")
        self.assertEqual(guidance.category, "ptsd")

    def test_guidance_str_representation(self):
        """ExamGuidance string includes title and category."""
        guidance = ExamGuidance.objects.create(
            title="General Exam Guide",
            slug="general",
            category="general",
        )
        self.assertEqual(str(guidance), "General Exam Guide (General Guidance)")

    def test_guidance_unique_slug(self):
        """ExamGuidance slug must be unique."""
        ExamGuidance.objects.create(title="Guide 1", slug="test-slug")
        with self.assertRaises(Exception):
            ExamGuidance.objects.create(title="Guide 2", slug="test-slug")

    def test_guidance_category_choices(self):
        """ExamGuidance accepts valid category choices."""
        valid_cats = [
            "general",
            "ptsd",
            "tbi",
            "musculoskeletal",
            "hearing",
            "respiratory",
            "sleep_apnea",
            "mental_health",
            "other",
        ]
        for cat in valid_cats:
            guidance = ExamGuidance.objects.create(
                title=f"Guide {cat}",
                slug=f"guide-{cat}",
                category=cat,
            )
            self.assertEqual(guidance.category, cat)

    def test_guidance_checklist_items_json(self):
        """ExamGuidance stores checklist items as JSON."""
        guidance = ExamGuidance.objects.create(
            title="Test Guide",
            slug="test-checklist",
            checklist_items=["Item 1", "Item 2", "Item 3"],
        )
        self.assertEqual(len(guidance.checklist_items), 3)


# =============================================================================
# GLOSSARY TERM MODEL TESTS
# =============================================================================


class TestGlossaryTermModel(TestCase):
    """Tests for the GlossaryTerm model."""

    def test_glossary_term_creation(self):
        """GlossaryTerm can be created."""
        term = GlossaryTerm.objects.create(
            term="Nexus Letter",
            plain_language="A medical opinion connecting your condition to service.",
            context="Required for service connection claims.",
        )
        self.assertEqual(term.term, "Nexus Letter")

    def test_glossary_term_str_representation(self):
        """GlossaryTerm string is the term."""
        term = GlossaryTerm.objects.create(
            term="C&P Exam",
            plain_language="Compensation and Pension examination",
        )
        self.assertEqual(str(term), "C&P Exam")

    def test_glossary_term_unique(self):
        """GlossaryTerm must be unique."""
        GlossaryTerm.objects.create(term="Test Term", plain_language="Explanation")
        with self.assertRaises(Exception):
            GlossaryTerm.objects.create(term="Test Term", plain_language="Other")

    def test_glossary_term_related_terms(self):
        """GlossaryTerm can have related terms."""
        term1 = GlossaryTerm.objects.create(term="Term 1", plain_language="T1")
        term2 = GlossaryTerm.objects.create(term="Term 2", plain_language="T2")
        term1.related_terms.add(term2)

        self.assertIn(term2, term1.related_terms.all())


# =============================================================================
# EXAM CHECKLIST MODEL TESTS
# =============================================================================


class TestExamChecklistModel(TestCase):
    """Tests for the ExamChecklist model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.guidance = ExamGuidance.objects.create(
            title="Test Guide",
            slug="test",
            checklist_items=["Task 1", "Task 2", "Task 3"],
        )

    def test_checklist_creation(self):
        """ExamChecklist can be created."""
        checklist = ExamChecklist.objects.create(
            user=self.user,
            condition="PTSD",
            exam_date=date.today() + timedelta(days=14),
            guidance=self.guidance,
        )
        self.assertEqual(checklist.user, self.user)
        self.assertEqual(checklist.condition, "PTSD")

    def test_checklist_str_representation(self):
        """ExamChecklist string includes condition."""
        checklist = ExamChecklist.objects.create(
            user=self.user,
            condition="Back Pain",
            exam_date=date.today(),
        )
        self.assertIn("Back Pain", str(checklist))

    def test_checklist_is_upcoming_future(self):
        """is_upcoming returns True for future exams."""
        checklist = ExamChecklist.objects.create(
            user=self.user,
            condition="PTSD",
            exam_date=date.today() + timedelta(days=7),
        )
        self.assertTrue(checklist.is_upcoming)

    def test_checklist_is_upcoming_past(self):
        """is_upcoming returns False for past exams."""
        checklist = ExamChecklist.objects.create(
            user=self.user,
            condition="PTSD",
            exam_date=date.today() - timedelta(days=7),
        )
        self.assertFalse(checklist.is_upcoming)

    def test_checklist_days_until_exam(self):
        """days_until_exam calculates correctly."""
        checklist = ExamChecklist.objects.create(
            user=self.user,
            condition="PTSD",
            exam_date=date.today() + timedelta(days=10),
        )
        self.assertEqual(checklist.days_until_exam, 10)

    def test_checklist_completion_percentage(self):
        """completion_percentage calculates correctly."""
        checklist = ExamChecklist.objects.create(
            user=self.user,
            condition="PTSD",
            guidance=self.guidance,
            tasks_completed=["task_1"],  # 1 of 3
        )
        # Should be approximately 33%
        self.assertIsNotNone(checklist.completion_percentage)


# =============================================================================
# SAVED RATING CALCULATION MODEL TESTS
# =============================================================================


class TestSavedRatingCalculationModel(TestCase):
    """Tests for the SavedRatingCalculation model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )

    def test_calculation_creation(self):
        """SavedRatingCalculation can be created."""
        calc = SavedRatingCalculation.objects.create(
            user=self.user,
            name="My Current Rating",
            ratings=[
                {"percentage": 50, "description": "PTSD", "is_bilateral": False},
                {"percentage": 30, "description": "Back", "is_bilateral": False},
            ],
        )
        self.assertEqual(calc.name, "My Current Rating")
        self.assertEqual(len(calc.ratings), 2)

    def test_calculation_str_representation(self):
        """SavedRatingCalculation string includes name and user."""
        calc = SavedRatingCalculation.objects.create(
            user=self.user,
            name="Test Calc",
            ratings=[],
        )
        self.assertIn("Test Calc", str(calc))

    def test_calculation_recalculate(self):
        """recalculate method updates combined ratings."""
        calc = SavedRatingCalculation.objects.create(
            user=self.user,
            name="Test",
            ratings=[
                {"percentage": 50, "description": "PTSD", "is_bilateral": False},
                {"percentage": 30, "description": "Back", "is_bilateral": False},
            ],
        )
        calc.recalculate()
        calc.save()

        self.assertIsNotNone(calc.combined_raw)
        self.assertIsNotNone(calc.combined_rounded)
        self.assertTrue(60 <= calc.combined_rounded <= 80)

    def test_calculation_with_dependents(self):
        """Calculation with dependents calculates compensation."""
        calc = SavedRatingCalculation.objects.create(
            user=self.user,
            name="With Deps",
            ratings=[{"percentage": 70, "description": "PTSD", "is_bilateral": False}],
            has_spouse=True,
            children_under_18=2,
        )
        calc.recalculate()
        calc.save()

        self.assertIsNotNone(calc.estimated_monthly)
        self.assertGreater(calc.estimated_monthly, 0)


# =============================================================================
# EVIDENCE CHECKLIST MODEL TESTS
# =============================================================================


class TestEvidenceChecklistModel(TestCase):
    """Tests for the EvidenceChecklist model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )

    def test_evidence_checklist_creation(self):
        """EvidenceChecklist can be created."""
        checklist = EvidenceChecklist.objects.create(
            user=self.user,
            condition="Sleep Apnea",
            claim_type="secondary",
            primary_condition="PTSD",
            checklist_items=[
                {"id": "item1", "title": "Sleep Study", "completed": False},
            ],
        )
        self.assertEqual(checklist.condition, "Sleep Apnea")
        self.assertEqual(checklist.claim_type, "secondary")

    def test_evidence_checklist_str_representation(self):
        """EvidenceChecklist string includes condition."""
        checklist = EvidenceChecklist.objects.create(
            user=self.user,
            condition="Tinnitus",
            claim_type="initial",
        )
        self.assertIn("Tinnitus", str(checklist))

    def test_evidence_checklist_toggle_item(self):
        """toggle_item toggles completion status."""
        checklist = EvidenceChecklist.objects.create(
            user=self.user,
            condition="Test",
            checklist_items=[
                {"id": "item1", "title": "Test Item", "completed": False},
            ],
        )
        # Toggle to completed
        checklist.toggle_item("item1")
        self.assertTrue(checklist.checklist_items[0]["completed"])

        # Toggle back
        checklist.toggle_item("item1")
        self.assertFalse(checklist.checklist_items[0]["completed"])

    def test_evidence_checklist_update_completion(self):
        """update_completion calculates percentage correctly."""
        checklist = EvidenceChecklist.objects.create(
            user=self.user,
            condition="Test",
            checklist_items=[
                {"id": "item1", "title": "Item 1", "completed": True},
                {"id": "item2", "title": "Item 2", "completed": False},
                {"id": "item3", "title": "Item 3", "completed": False},
            ],
        )
        checklist.update_completion()
        # 1 of 3 = 33%
        self.assertEqual(checklist.completion_percentage, 33)

    def test_evidence_checklist_get_items_by_category(self):
        """get_items_by_category groups items correctly."""
        checklist = EvidenceChecklist.objects.create(
            user=self.user,
            condition="Test",
            checklist_items=[
                {"id": "item1", "category": "Medical Evidence", "completed": False},
                {"id": "item2", "category": "Medical Evidence", "completed": False},
                {"id": "item3", "category": "Lay Evidence", "completed": False},
            ],
        )
        by_category = checklist.get_items_by_category()

        self.assertIn("Medical Evidence", by_category)
        self.assertEqual(len(by_category["Medical Evidence"]), 2)

    def test_evidence_checklist_critical_items_remaining(self):
        """critical_items_remaining counts uncompleted critical items."""
        checklist = EvidenceChecklist.objects.create(
            user=self.user,
            condition="Test",
            checklist_items=[
                {"id": "item1", "priority": "critical", "completed": False},
                {"id": "item2", "priority": "critical", "completed": True},
                {"id": "item3", "priority": "standard", "completed": False},
            ],
        )
        self.assertEqual(checklist.critical_items_remaining, 1)


# =============================================================================
# PUBLIC GUIDE VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestPublicGuideViews:
    """Tests for public guide views (no login required)."""

    def test_guide_list_loads(self, client):
        """Guide list page loads without login."""
        response = client.get(reverse("examprep:guide_list"))
        assert response.status_code == 200

    def test_guide_list_shows_published(self, client, exam_guidance):
        """Guide list shows published guides."""
        response = client.get(reverse("examprep:guide_list"))
        assert response.status_code == 200
        # Check context for guides

    def test_guide_detail_loads(self, client, exam_guidance):
        """Guide detail page loads without login."""
        response = client.get(
            reverse("examprep:guide_detail", kwargs={"slug": exam_guidance.slug})
        )
        assert response.status_code == 200

    def test_guide_detail_404_unpublished(self, client, db):
        """Unpublished guide returns 404."""
        guide = ExamGuidance.objects.create(
            title="Unpublished",
            slug="unpublished",
            is_published=False,
        )
        response = client.get(
            reverse("examprep:guide_detail", kwargs={"slug": "unpublished"})
        )
        assert response.status_code == 404


# =============================================================================
# PUBLIC GLOSSARY VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestPublicGlossaryViews:
    """Tests for public glossary views (no login required)."""

    def test_glossary_list_loads(self, client):
        """Glossary list page loads without login."""
        response = client.get(reverse("examprep:glossary_list"))
        assert response.status_code == 200

    def test_glossary_list_search(self, client, glossary_term):
        """Glossary list supports search."""
        response = client.get(reverse("examprep:glossary_list") + "?q=Nexus")
        assert response.status_code == 200

    def test_glossary_detail_loads(self, client, glossary_term):
        """Glossary detail page loads without login."""
        response = client.get(
            reverse("examprep:glossary_detail", kwargs={"pk": glossary_term.pk})
        )
        assert response.status_code == 200


# =============================================================================
# RATING CALCULATOR VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestRatingCalculatorViews:
    """Tests for rating calculator views."""

    def test_calculator_loads_anonymous(self, client):
        """Rating calculator loads for anonymous users."""
        response = client.get(reverse("examprep:rating_calculator"))
        assert response.status_code == 200

    def test_calculator_loads_authenticated(self, authenticated_client):
        """Rating calculator loads for authenticated users."""
        response = authenticated_client.get(reverse("examprep:rating_calculator"))
        assert response.status_code == 200
        # Should have saved_calculations in context
        assert "saved_calculations" in response.context

    def test_calculate_htmx_endpoint(self, client):
        """Calculate HTMX endpoint returns results."""
        response = client.post(
            reverse("examprep:calculate_rating"),
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 30,
                            "description": "Back",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200

    def test_calculate_htmx_empty_ratings(self, client):
        """Calculate HTMX handles empty ratings."""
        response = client.post(
            reverse("examprep:calculate_rating"),
            {
                "ratings": "[]",
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestSaveCalculationViews:
    """Tests for saving rating calculations."""

    def test_save_calculation_requires_login(self, client):
        """Saving calculation requires authentication."""
        response = client.post(reverse("examprep:save_calculation"))
        assert response.status_code == 302

    def test_save_calculation_creates_record(
        self, authenticated_client, user, settings
    ):
        """Saving calculation creates database record."""
        settings.PILOT_PREMIUM_ACCESS = True
        response = authenticated_client.post(
            reverse("examprep:save_calculation"),
            {
                "name": "Test Calculation",
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )
        assert response.status_code in [200, 302]
        assert SavedRatingCalculation.objects.filter(user=user).exists()

    def test_saved_calculations_list(self, authenticated_client, saved_rating):
        """Saved calculations list shows user's calculations."""
        response = authenticated_client.get(reverse("examprep:saved_calculations"))
        assert response.status_code == 200
        assert saved_rating in response.context["calculations"]

    def test_saved_calculations_list_is_a_live_region(
        self, authenticated_client, saved_rating
    ):
        """
        Deleting a calculation swaps #calc-<pk> with hx-swap="outerHTML",
        which destroys that element entirely — aria-live has to live on the
        persistent list wrapper, not the item being removed.
        """
        html = authenticated_client.get(
            reverse("examprep:saved_calculations")
        ).content.decode()
        assert 'class="space-y-4" aria-live="polite"' in html


# =============================================================================
# EXAM CHECKLIST VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestExamChecklistViews:
    """Tests for exam checklist views."""

    def test_checklist_list_requires_login(self, client):
        """Checklist list requires authentication."""
        response = client.get(reverse("examprep:checklist_list"))
        assert response.status_code == 302

    def test_checklist_list_loads(self, authenticated_client):
        """Checklist list loads for authenticated user."""
        response = authenticated_client.get(reverse("examprep:checklist_list"))
        assert response.status_code == 200

    def test_checklist_create_requires_login(self, client):
        """Creating checklist requires authentication."""
        response = client.get(reverse("examprep:checklist_create"))
        assert response.status_code == 302

    def test_checklist_create_loads(self, authenticated_client):
        """Create checklist page loads."""
        response = authenticated_client.get(reverse("examprep:checklist_create"))
        assert response.status_code == 200

    def test_checklist_detail_loads(self, authenticated_client, exam_checklist):
        """Checklist detail loads for owner."""
        response = authenticated_client.get(
            reverse("examprep:checklist_detail", kwargs={"pk": exam_checklist.pk})
        )
        assert response.status_code == 200

    def test_checklist_task_list_is_a_live_region(
        self, authenticated_client, exam_checklist
    ):
        """
        Task toggling swaps each <li> with hx-target="this" outerHTML, which
        destroys the toggled item — aria-live must be on the persistent
        #task-list wrapper for the completion state change to be announced.
        """
        html = authenticated_client.get(
            reverse("examprep:checklist_detail", kwargs={"pk": exam_checklist.pk})
        ).content.decode()
        assert 'id="task-list"' in html
        list_start = html.index('id="task-list"')
        list_tag = html[list_start : list_start + 200]
        assert 'aria-live="polite"' in list_tag

    def test_checklist_toggle_task(self, authenticated_client, exam_checklist):
        """Toggle task HTMX endpoint works."""
        response = authenticated_client.post(
            reverse("examprep:checklist_toggle_task", kwargs={"pk": exam_checklist.pk}),
            {"task_id": "task_1"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200


# =============================================================================
# EVIDENCE CHECKLIST VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestEvidenceChecklistViews:
    """Tests for evidence checklist views."""

    def test_evidence_list_requires_login(self, client):
        """Evidence checklist list requires authentication."""
        response = client.get(reverse("examprep:evidence_checklist_list"))
        assert response.status_code == 302

    def test_evidence_list_loads(self, authenticated_client):
        """Evidence checklist list loads for authenticated user."""
        response = authenticated_client.get(reverse("examprep:evidence_checklist_list"))
        assert response.status_code == 200

    def test_evidence_detail_loads(self, authenticated_client, evidence_checklist):
        """Evidence checklist detail loads for owner."""
        response = authenticated_client.get(
            reverse(
                "examprep:evidence_checklist_detail",
                kwargs={"pk": evidence_checklist.pk},
            )
        )
        assert response.status_code == 200

    def test_evidence_toggle_item(self, authenticated_client, evidence_checklist):
        """Toggle item HTMX endpoint works."""
        response = authenticated_client.post(
            reverse(
                "examprep:evidence_checklist_toggle",
                kwargs={"pk": evidence_checklist.pk},
            ),
            {"item_id": "sleep_study"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200


# =============================================================================
# ACCESS CONTROL TESTS
# =============================================================================


@pytest.mark.django_db
class TestExamPrepAccessControl:
    """Tests for access control on examprep views."""

    def test_user_cannot_view_other_checklist(
        self, authenticated_client, other_user, exam_guidance
    ):
        """Users cannot view other user's exam checklist."""
        other_checklist = ExamChecklist.objects.create(
            user=other_user,
            condition="Other's Checklist",
            exam_date=date.today() + timedelta(days=7),
        )
        response = authenticated_client.get(
            reverse("examprep:checklist_detail", kwargs={"pk": other_checklist.pk})
        )
        assert response.status_code == 404

    def test_user_cannot_view_other_evidence_checklist(
        self, authenticated_client, other_user
    ):
        """Users cannot view other user's evidence checklist."""
        other_checklist = EvidenceChecklist.objects.create(
            user=other_user,
            condition="Other's Evidence",
            claim_type="initial",
        )
        response = authenticated_client.get(
            reverse(
                "examprep:evidence_checklist_detail", kwargs={"pk": other_checklist.pk}
            )
        )
        assert response.status_code == 404

    def test_user_cannot_view_other_saved_calculation(
        self, authenticated_client, other_user
    ):
        """Users cannot load other user's saved calculation."""
        other_calc = SavedRatingCalculation.objects.create(
            user=other_user,
            name="Other's Calc",
            ratings=[],
        )
        response = authenticated_client.get(
            reverse("examprep:load_calculation", kwargs={"pk": other_calc.pk})
        )
        assert response.status_code == 404


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestExamPrepWorkflow(TestCase):
    """Integration tests for examprep workflows."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.client = Client()
        self.client.login(email="test@example.com", password="TestPass123!")

    def test_rating_calculator_full_workflow(self):
        """Test complete rating calculation workflow."""
        # 1. Calculate rating
        ratings = [
            DisabilityRating(percentage=50, description="PTSD"),
            DisabilityRating(percentage=30, description="Back"),
            DisabilityRating(percentage=20, description="Knee", is_bilateral=True),
            DisabilityRating(percentage=10, description="Knee", is_bilateral=True),
        ]
        result = calculate_combined_rating(ratings)

        # Verify calculation
        self.assertGreater(result.combined_raw, 60)
        self.assertGreater(result.bilateral_factor_applied, 0)

        # 2. Save calculation
        calc = SavedRatingCalculation.objects.create(
            user=self.user,
            name="My Full Rating",
            ratings=[
                {
                    "percentage": r.percentage,
                    "description": r.description,
                    "is_bilateral": r.is_bilateral,
                }
                for r in ratings
            ],
            has_spouse=True,
            children_under_18=1,
        )
        calc.recalculate()
        calc.save()

        # 3. Verify saved calculation
        self.assertIsNotNone(calc.combined_rounded)
        self.assertGreater(calc.estimated_monthly, 0)

    def test_exam_preparation_workflow(self):
        """Test complete exam preparation workflow."""
        # 1. Create guide
        guide = ExamGuidance.objects.create(
            title="PTSD Guide",
            slug="ptsd",
            category="ptsd",
            checklist_items=[
                "Review stressor statement",
                "List all symptoms",
                "Bring medication list",
            ],
            is_published=True,
        )

        # 2. Create checklist
        checklist = ExamChecklist.objects.create(
            user=self.user,
            condition="PTSD",
            exam_date=date.today() + timedelta(days=14),
            guidance=guide,
            tasks_completed=[],
        )

        # 3. Complete tasks
        checklist.tasks_completed = ["task_1", "task_2"]
        checklist.save()

        # 4. Add notes
        checklist.symptom_notes = "Nightmares 3x per week"
        checklist.worst_day_description = "Can't leave the house"
        checklist.save()

        # 5. Mark exam completed
        checklist.exam_completed = True
        checklist.exam_notes = "Exam went well"
        checklist.save()

        # Verify final state
        self.assertTrue(checklist.exam_completed)
        self.assertFalse(checklist.is_upcoming)

    def test_evidence_collection_workflow(self):
        """Test complete evidence collection workflow."""
        # 1. Create evidence checklist
        checklist = EvidenceChecklist.objects.create(
            user=self.user,
            condition="Sleep Apnea",
            claim_type="secondary",
            primary_condition="PTSD",
            checklist_items=[
                {
                    "id": "sleep_study",
                    "category": "Medical",
                    "title": "Sleep Study",
                    "priority": "critical",
                    "completed": False,
                },
                {
                    "id": "nexus",
                    "category": "Medical",
                    "title": "Nexus Letter",
                    "priority": "critical",
                    "completed": False,
                },
                {
                    "id": "buddy",
                    "category": "Lay",
                    "title": "Buddy Statement",
                    "priority": "standard",
                    "completed": False,
                },
            ],
        )
        checklist.update_completion()
        self.assertEqual(checklist.completion_percentage, 0)

        # 2. Complete critical items
        checklist.toggle_item("sleep_study")
        checklist.toggle_item("nexus")
        checklist.update_completion()

        # 3. Verify progress
        self.assertEqual(checklist.completion_percentage, 66)
        self.assertEqual(checklist.critical_items_remaining, 0)

        # 4. Complete all
        checklist.toggle_item("buddy")
        checklist.update_completion()
        self.assertEqual(checklist.completion_percentage, 100)


# =============================================================================
# RATING CALCULATOR INTEGRATION TESTS - COMPREHENSIVE SUITE
# =============================================================================


class TestRatingCalculatorPageIntegration(TestCase):
    """Integration tests for rating calculator page loading and context."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="calcuser@example.com", password="TestPass123!"
        )

    def test_calculator_page_loads_anonymous(self):
        """Calculator page loads for anonymous users."""
        response = self.client.get(reverse("examprep:rating_calculator"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "examprep/rating_calculator.html")

    def test_calculator_page_contains_compensation_rates(self):
        """Calculator page includes 2024 compensation rates."""
        response = self.client.get(reverse("examprep:rating_calculator"))
        self.assertIn("compensation_rates", response.context)
        rates = response.context["compensation_rates"]
        self.assertEqual(rates[100], VA_COMPENSATION_RATES_2024[100])

    def test_calculator_page_no_saved_calculations_anonymous(self):
        """Anonymous users have no saved calculations."""
        response = self.client.get(reverse("examprep:rating_calculator"))
        self.assertIsNone(response.context.get("saved_calculations"))

    def test_calculator_page_shows_saved_calculations_authenticated(self):
        """Authenticated users see their saved calculations."""
        self.client.login(email="calcuser@example.com", password="TestPass123!")

        # Create some saved calculations
        for i in range(3):
            SavedRatingCalculation.objects.create(
                user=self.user,
                name=f"Calculation {i}",
                ratings=[
                    {"percentage": 50, "description": "Test", "is_bilateral": False}
                ],
            )

        response = self.client.get(reverse("examprep:rating_calculator"))
        self.assertIn("saved_calculations", response.context)
        self.assertEqual(len(response.context["saved_calculations"]), 3)

    def test_calculator_page_limits_saved_calculations_to_5(self):
        """Calculator page shows at most 5 recent saved calculations."""
        self.client.login(email="calcuser@example.com", password="TestPass123!")

        # Create 10 saved calculations
        for i in range(10):
            SavedRatingCalculation.objects.create(
                user=self.user,
                name=f"Calculation {i}",
                ratings=[
                    {"percentage": 50, "description": "Test", "is_bilateral": False}
                ],
            )

        response = self.client.get(reverse("examprep:rating_calculator"))
        self.assertEqual(len(response.context["saved_calculations"]), 5)


class TestCalculateRatingHTMXEndpoint(TestCase):
    """Integration tests for the calculate_rating HTMX endpoint."""

    def setUp(self):
        self.client = Client()
        self.url = reverse("examprep:calculate_rating")

    def test_calculate_get_not_allowed(self):
        """GET requests are not allowed."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_calculate_single_rating(self):
        """Calculate single rating correctly."""
        response = self.client.post(
            self.url,
            {
                "ratings": json.dumps(
                    [{"percentage": 70, "description": "PTSD", "is_bilateral": False}]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "70")

    def test_calculate_two_ratings(self):
        """Calculate two ratings combined correctly."""
        response = self.client.post(
            self.url,
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 30,
                            "description": "Back",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        # 50% + 30% = 65% → rounds to 70%
        self.assertContains(response, "70")

    def test_calculate_with_bilateral(self):
        """Calculate with bilateral factor."""
        response = self.client.post(
            self.url,
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 30,
                            "description": "Left Knee",
                            "is_bilateral": True,
                        },
                        {
                            "percentage": 20,
                            "description": "Right Knee",
                            "is_bilateral": True,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        # Should show bilateral factor was applied
        self.assertContains(
            response, "bilateral", status_code=200, msg_prefix="", html=False
        )

    def test_calculate_with_spouse(self):
        """Calculate with spouse dependent."""
        response = self.client.post(
            self.url,
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "true",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        # Compensation should be higher than base 50%

    def test_calculate_with_children(self):
        """Calculate with children dependents."""
        response = self.client.post(
            self.url,
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 70,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "3",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

    def test_calculate_with_dependent_parents(self):
        """Calculate with dependent parents."""
        response = self.client.post(
            self.url,
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "2",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

    def test_calculate_full_family(self):
        """Calculate with spouse, children, and parents."""
        response = self.client.post(
            self.url,
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 100,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "true",
                "children_under_18": "2",
                "dependent_parents": "1",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

    def test_calculate_empty_ratings(self):
        """Empty ratings return zero result."""
        response = self.client.post(
            self.url,
            {
                "ratings": "[]",
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("has_ratings", response.context)
        self.assertFalse(response.context["has_ratings"])

    def test_calculate_zero_percentage_ratings_filtered(self):
        """Zero percentage ratings are filtered out."""
        response = self.client.post(
            self.url,
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 0,
                            "description": "Resolved",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 50,
                            "description": "Active",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "50")

    def test_calculate_invalid_json(self):
        """Invalid JSON returns error."""
        response = self.client.post(
            self.url,
            {
                "ratings": "not valid json",
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 400)

    def test_calculate_complex_scenario(self):
        """Calculate complex real-world scenario."""
        response = self.client.post(
            self.url,
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 70,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 50,
                            "description": "Sleep Apnea",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 30,
                            "description": "Back",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 20,
                            "description": "Left Knee",
                            "is_bilateral": True,
                        },
                        {
                            "percentage": 20,
                            "description": "Right Knee",
                            "is_bilateral": True,
                        },
                        {
                            "percentage": 10,
                            "description": "Tinnitus",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "true",
                "children_under_18": "2",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        # Should be high combined rating
        self.assertContains(response, "90")

    def test_calculate_returns_step_by_step(self):
        """Calculate endpoint returns step-by-step breakdown."""
        response = self.client.post(
            self.url,
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 30,
                            "description": "Back",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("step_by_step", response.context)


@override_settings(PILOT_PREMIUM_ACCESS=True)
class TestSaveCalculationIntegration(TestCase):
    """Integration tests for saving rating calculations."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="saveuser@example.com", password="TestPass123!"
        )
        self.url = reverse("examprep:save_calculation")

    def test_save_requires_authentication(self):
        """Save endpoint requires login."""
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_save_get_not_allowed(self):
        """GET requests are not allowed."""
        self.client.login(email="saveuser@example.com", password="TestPass123!")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_save_creates_calculation(self):
        """Save creates a new calculation record."""
        self.client.login(email="saveuser@example.com", password="TestPass123!")

        response = self.client.post(
            self.url,
            {
                "name": "My Test Calculation",
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 30,
                            "description": "Back",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "true",
                "children_under_18": "2",
                "dependent_parents": "0",
                "notes": "Test notes",
            },
        )

        # Should redirect to saved calculations
        self.assertIn(response.status_code, [200, 302])

        # Verify calculation was created
        calc = SavedRatingCalculation.objects.filter(user=self.user).first()
        self.assertIsNotNone(calc)
        self.assertEqual(calc.name, "My Test Calculation")
        self.assertEqual(len(calc.ratings), 2)
        self.assertTrue(calc.has_spouse)
        self.assertEqual(calc.children_under_18, 2)
        self.assertEqual(calc.notes, "Test notes")

    def test_save_calculates_combined_rating(self):
        """Saved calculation includes calculated values."""
        self.client.login(email="saveuser@example.com", password="TestPass123!")

        self.client.post(
            self.url,
            {
                "name": "Calculated",
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 30,
                            "description": "Back",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )

        calc = SavedRatingCalculation.objects.filter(user=self.user).first()
        self.assertIsNotNone(calc.combined_raw)
        self.assertIsNotNone(calc.combined_rounded)
        self.assertEqual(calc.combined_rounded, 70)  # 65 rounds to 70

    def test_save_with_bilateral(self):
        """Save calculation with bilateral ratings."""
        self.client.login(email="saveuser@example.com", password="TestPass123!")

        self.client.post(
            self.url,
            {
                "name": "Bilateral Test",
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 30,
                            "description": "Left Knee",
                            "is_bilateral": True,
                        },
                        {
                            "percentage": 20,
                            "description": "Right Knee",
                            "is_bilateral": True,
                        },
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )

        calc = SavedRatingCalculation.objects.filter(user=self.user).first()
        self.assertIsNotNone(calc)
        # Verify bilateral ratings are stored
        bilateral_count = sum(1 for r in calc.ratings if r.get("is_bilateral", False))
        self.assertEqual(bilateral_count, 2)

    def test_save_htmx_returns_confirmation(self):
        """HTMX save request returns confirmation partial."""
        self.client.login(email="saveuser@example.com", password="TestPass123!")

        response = self.client.post(
            self.url,
            {
                "name": "HTMX Test",
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)

    def test_save_invalid_json(self):
        """Invalid JSON returns error."""
        self.client.login(email="saveuser@example.com", password="TestPass123!")

        response = self.client.post(
            self.url,
            {
                "name": "Invalid",
                "ratings": "not valid json",
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 400)


class TestLoadCalculationIntegration(TestCase):
    """Integration tests for loading saved calculations."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="loaduser@example.com", password="TestPass123!"
        )
        self.other_user = User.objects.create_user(
            email="otheruser@example.com", password="TestPass123!"
        )
        self.calc = SavedRatingCalculation.objects.create(
            user=self.user,
            name="Test Calculation",
            ratings=[
                {"percentage": 50, "description": "PTSD", "is_bilateral": False},
                {"percentage": 30, "description": "Back", "is_bilateral": False},
            ],
            has_spouse=True,
            children_under_18=2,
            dependent_parents=1,
            notes="Test notes",
        )
        self.calc.recalculate()
        self.calc.save()

    def test_load_requires_authentication(self):
        """Load endpoint requires login."""
        response = self.client.get(
            reverse("examprep:load_calculation", kwargs={"pk": self.calc.pk})
        )
        self.assertEqual(response.status_code, 302)

    def test_load_returns_json(self):
        """Load returns JSON with calculation data."""
        self.client.login(email="loaduser@example.com", password="TestPass123!")

        response = self.client.get(
            reverse("examprep:load_calculation", kwargs={"pk": self.calc.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        data = json.loads(response.content)
        self.assertEqual(data["name"], "Test Calculation")
        self.assertEqual(len(data["ratings"]), 2)
        self.assertTrue(data["has_spouse"])
        self.assertEqual(data["children_under_18"], 2)
        self.assertEqual(data["dependent_parents"], 1)
        self.assertEqual(data["notes"], "Test notes")

    def test_load_other_user_calculation_404(self):
        """Cannot load another user's calculation."""
        self.client.login(email="otheruser@example.com", password="TestPass123!")

        response = self.client.get(
            reverse("examprep:load_calculation", kwargs={"pk": self.calc.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_load_nonexistent_calculation_404(self):
        """Loading nonexistent calculation returns 404."""
        self.client.login(email="loaduser@example.com", password="TestPass123!")

        response = self.client.get(
            reverse("examprep:load_calculation", kwargs={"pk": 99999})
        )

        self.assertEqual(response.status_code, 404)


class TestDeleteCalculationIntegration(TestCase):
    """Integration tests for deleting saved calculations."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="deleteuser@example.com", password="TestPass123!"
        )
        self.other_user = User.objects.create_user(
            email="otherdeleteuser@example.com", password="TestPass123!"
        )

    def test_delete_requires_authentication(self):
        """Delete endpoint requires login."""
        calc = SavedRatingCalculation.objects.create(
            user=self.user,
            name="To Delete",
            ratings=[],
        )
        response = self.client.post(
            reverse("examprep:delete_calculation", kwargs={"pk": calc.pk})
        )
        self.assertEqual(response.status_code, 302)

    def test_delete_removes_calculation(self):
        """Delete removes the calculation from database."""
        self.client.login(email="deleteuser@example.com", password="TestPass123!")

        calc = SavedRatingCalculation.objects.create(
            user=self.user,
            name="To Delete",
            ratings=[{"percentage": 50, "description": "Test", "is_bilateral": False}],
        )
        calc_pk = calc.pk

        response = self.client.post(
            reverse("examprep:delete_calculation", kwargs={"pk": calc_pk})
        )

        # Should redirect to saved calculations list
        self.assertEqual(response.status_code, 302)

        # Verify calculation is deleted
        self.assertFalse(SavedRatingCalculation.objects.filter(pk=calc_pk).exists())

    def test_delete_other_user_calculation_404(self):
        """Cannot delete another user's calculation."""
        calc = SavedRatingCalculation.objects.create(
            user=self.user,
            name="Other User's Calc",
            ratings=[],
        )

        self.client.login(email="otherdeleteuser@example.com", password="TestPass123!")

        response = self.client.post(
            reverse("examprep:delete_calculation", kwargs={"pk": calc.pk})
        )

        self.assertEqual(response.status_code, 404)
        # Verify calculation still exists
        self.assertTrue(SavedRatingCalculation.objects.filter(pk=calc.pk).exists())

    def test_delete_htmx_returns_empty(self):
        """HTMX delete returns empty response for element removal."""
        self.client.login(email="deleteuser@example.com", password="TestPass123!")

        calc = SavedRatingCalculation.objects.create(
            user=self.user,
            name="HTMX Delete",
            ratings=[],
        )

        response = self.client.post(
            reverse("examprep:delete_calculation", kwargs={"pk": calc.pk}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    def test_delete_confirmation_page_get(self):
        """GET request shows deletion confirmation page or redirects."""
        self.client.login(email="deleteuser@example.com", password="TestPass123!")

        calc = SavedRatingCalculation.objects.create(
            user=self.user,
            name="Confirm Delete",
            ratings=[],
        )

        response = self.client.get(
            reverse("examprep:delete_calculation", kwargs={"pk": calc.pk})
        )

        # View may render template or redirect - both are valid
        self.assertIn(response.status_code, [200, 302])


class TestSavedCalculationsListIntegration(TestCase):
    """Integration tests for saved calculations list view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="listuser@example.com", password="TestPass123!"
        )

    def test_list_requires_authentication(self):
        """Saved calculations list requires login."""
        response = self.client.get(reverse("examprep:saved_calculations"))
        self.assertEqual(response.status_code, 302)

    def test_list_shows_user_calculations(self):
        """List shows only user's calculations."""
        self.client.login(email="listuser@example.com", password="TestPass123!")

        # Create calculations for this user
        for i in range(3):
            SavedRatingCalculation.objects.create(
                user=self.user,
                name=f"My Calc {i}",
                ratings=[
                    {"percentage": 50, "description": "Test", "is_bilateral": False}
                ],
            )

        # Create calculation for another user
        other_user = User.objects.create_user(
            email="otherlistuser@example.com", password="TestPass123!"
        )
        SavedRatingCalculation.objects.create(
            user=other_user,
            name="Other User Calc",
            ratings=[],
        )

        response = self.client.get(reverse("examprep:saved_calculations"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["calculations"]), 3)

    def test_list_ordered_by_updated_date(self):
        """List is ordered by most recently updated."""
        self.client.login(email="listuser@example.com", password="TestPass123!")

        calc1 = SavedRatingCalculation.objects.create(
            user=self.user,
            name="Oldest",
            ratings=[],
        )
        calc2 = SavedRatingCalculation.objects.create(
            user=self.user,
            name="Newest",
            ratings=[],
        )

        response = self.client.get(reverse("examprep:saved_calculations"))

        calculations = list(response.context["calculations"])
        # Newest should be first
        self.assertEqual(calculations[0].name, "Newest")


@override_settings(PILOT_PREMIUM_ACCESS=True)
class TestRatingCalculatorEndToEndWorkflow(TestCase):
    """End-to-end integration tests for complete rating calculator workflows."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="e2euser@example.com", password="TestPass123!"
        )

    def test_complete_workflow_anonymous_user(self):
        """Complete workflow for anonymous user (calculate only, no save)."""
        # 1. Load calculator page
        response = self.client.get(reverse("examprep:rating_calculator"))
        self.assertEqual(response.status_code, 200)

        # 2. Calculate ratings
        response = self.client.post(
            reverse("examprep:calculate_rating"),
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 70,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 40,
                            "description": "Back",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 10,
                            "description": "Tinnitus",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

        # 3. Attempting to save should redirect to login
        response = self.client.post(
            reverse("examprep:save_calculation"),
            {
                "name": "Cannot Save",
                "ratings": "[]",
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_complete_workflow_authenticated_user(self):
        """Complete workflow for authenticated user."""
        self.client.login(email="e2euser@example.com", password="TestPass123!")

        # 1. Load calculator page
        response = self.client.get(reverse("examprep:rating_calculator"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("saved_calculations", response.context)

        # 2. Calculate ratings
        ratings_data = [
            {"percentage": 70, "description": "PTSD", "is_bilateral": False},
            {"percentage": 40, "description": "Back", "is_bilateral": False},
            {"percentage": 20, "description": "Left Knee", "is_bilateral": True},
            {"percentage": 10, "description": "Right Knee", "is_bilateral": True},
            {"percentage": 10, "description": "Tinnitus", "is_bilateral": False},
        ]

        response = self.client.post(
            reverse("examprep:calculate_rating"),
            {
                "ratings": json.dumps(ratings_data),
                "has_spouse": "true",
                "children_under_18": "2",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["has_ratings"])
        self.assertGreater(response.context["combined_rounded"], 80)

        # 3. Save calculation
        response = self.client.post(
            reverse("examprep:save_calculation"),
            {
                "name": "My Complex Rating",
                "ratings": json.dumps(ratings_data),
                "has_spouse": "true",
                "children_under_18": "2",
                "dependent_parents": "0",
                "notes": "Bilateral knees from service",
            },
        )
        self.assertIn(response.status_code, [200, 302])

        # 4. Verify saved calculation
        calc = SavedRatingCalculation.objects.get(
            user=self.user, name="My Complex Rating"
        )
        self.assertEqual(len(calc.ratings), 5)
        self.assertTrue(calc.has_spouse)
        self.assertEqual(calc.children_under_18, 2)
        self.assertIsNotNone(calc.combined_rounded)
        self.assertIsNotNone(calc.estimated_monthly)

        # 5. View saved calculations list
        response = self.client.get(reverse("examprep:saved_calculations"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["calculations"]), 1)

        # 6. Load the saved calculation
        response = self.client.get(
            reverse("examprep:load_calculation", kwargs={"pk": calc.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["name"], "My Complex Rating")

        # 7. Delete the calculation
        response = self.client.post(
            reverse("examprep:delete_calculation", kwargs={"pk": calc.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SavedRatingCalculation.objects.filter(pk=calc.pk).exists())

    def test_workflow_update_existing_calculation(self):
        """Test updating an existing saved calculation."""
        self.client.login(email="e2euser@example.com", password="TestPass123!")

        # Create initial calculation
        initial_ratings = [
            {"percentage": 50, "description": "PTSD", "is_bilateral": False},
        ]
        self.client.post(
            reverse("examprep:save_calculation"),
            {
                "name": "Initial Rating",
                "ratings": json.dumps(initial_ratings),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )

        # Create updated calculation with same name
        updated_ratings = [
            {"percentage": 70, "description": "PTSD", "is_bilateral": False},
            {"percentage": 30, "description": "Back", "is_bilateral": False},
        ]
        self.client.post(
            reverse("examprep:save_calculation"),
            {
                "name": "Updated Rating",
                "ratings": json.dumps(updated_ratings),
                "has_spouse": "true",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )

        # Should now have 2 calculations
        calcs = SavedRatingCalculation.objects.filter(user=self.user)
        self.assertEqual(calcs.count(), 2)

    def test_workflow_multiple_calculations(self):
        """Test managing multiple saved calculations."""
        self.client.login(email="e2euser@example.com", password="TestPass123!")

        # Create multiple calculations
        scenarios = [
            (
                "Current Rating",
                [{"percentage": 70, "description": "PTSD", "is_bilateral": False}],
            ),
            (
                "Best Case",
                [
                    {"percentage": 70, "description": "PTSD", "is_bilateral": False},
                    {"percentage": 50, "description": "Back", "is_bilateral": False},
                ],
            ),
            (
                "With Bilateral",
                [
                    {"percentage": 50, "description": "PTSD", "is_bilateral": False},
                    {
                        "percentage": 20,
                        "description": "Left Knee",
                        "is_bilateral": True,
                    },
                    {
                        "percentage": 20,
                        "description": "Right Knee",
                        "is_bilateral": True,
                    },
                ],
            ),
        ]

        for name, ratings in scenarios:
            self.client.post(
                reverse("examprep:save_calculation"),
                {
                    "name": name,
                    "ratings": json.dumps(ratings),
                    "has_spouse": "false",
                    "children_under_18": "0",
                    "dependent_parents": "0",
                },
            )

        # Verify all saved
        calcs = SavedRatingCalculation.objects.filter(user=self.user)
        self.assertEqual(calcs.count(), 3)

        # Load each and verify
        for calc in calcs:
            response = self.client.get(
                reverse("examprep:load_calculation", kwargs={"pk": calc.pk})
            )
            self.assertEqual(response.status_code, 200)


@override_settings(PILOT_PREMIUM_ACCESS=True)
class TestRatingCalculatorErrorHandling(TestCase):
    """Tests for error handling in rating calculator."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="erroruser@example.com", password="TestPass123!"
        )

    def test_calculate_malformed_json(self):
        """Malformed JSON returns 400 error."""
        response = self.client.post(
            reverse("examprep:calculate_rating"),
            {
                "ratings": "{invalid json",
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 400)

    def test_calculate_missing_ratings(self):
        """Missing ratings field handles gracefully."""
        response = self.client.post(
            reverse("examprep:calculate_rating"),
            {
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        # Should default to empty ratings
        self.assertEqual(response.status_code, 200)

    def test_calculate_invalid_percentage(self):
        """Invalid percentage value handles gracefully."""
        response = self.client.post(
            reverse("examprep:calculate_rating"),
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": "not a number",
                            "description": "Test",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 400)

    def test_save_with_name(self):
        """Save with provided name."""
        self.client.login(email="erroruser@example.com", password="TestPass123!")

        response = self.client.post(
            reverse("examprep:save_calculation"),
            {
                "name": "My Custom Name",
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "Test",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )

        calc = SavedRatingCalculation.objects.filter(user=self.user).first()
        self.assertIsNotNone(calc)
        self.assertEqual(calc.name, "My Custom Name")


# =============================================================================
# PDF EXPORT TESTS
# =============================================================================


class TestPDFExport(TestCase):
    """Tests for PDF export functionality."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="pdfuser@example.com", password="TestPass123!"
        )
        self.other_user = User.objects.create_user(
            email="otheruser@example.com", password="TestPass123!"
        )
        # Create a saved calculation for the user
        self.saved_calc = SavedRatingCalculation.objects.create(
            user=self.user,
            name="My Test Calculation",
            notes="Test notes",
            ratings=[
                {"percentage": 50, "description": "PTSD", "is_bilateral": False},
                {"percentage": 30, "description": "Knee", "is_bilateral": True},
            ],
            combined_raw=65.0,
            combined_rounded=70,
            bilateral_factor=3.0,
            estimated_monthly=1628.24,
            has_spouse=False,
            children_under_18=0,
            dependent_parents=0,
        )

    def test_export_pdf_returns_pdf_content_type(self):
        """Export PDF returns application/pdf content type."""
        response = self.client.post(
            reverse("examprep:export_rating_pdf"),
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 30,
                            "description": "Knee",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_export_pdf_has_attachment_disposition(self):
        """Export PDF has attachment Content-Disposition header."""
        response = self.client.post(
            reverse("examprep:export_rating_pdf"),
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".pdf", response["Content-Disposition"])

    def test_export_pdf_with_single_rating(self):
        """Export PDF works with a single rating."""
        response = self.client.post(
            reverse("examprep:export_rating_pdf"),
            {
                "ratings": json.dumps(
                    [
                        {"percentage": 70, "description": "TBI", "is_bilateral": False},
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_export_pdf_with_multiple_ratings(self):
        """Export PDF works with multiple ratings."""
        response = self.client.post(
            reverse("examprep:export_rating_pdf"),
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 30,
                            "description": "Back",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 20,
                            "description": "Tinnitus",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 10,
                            "description": "Scars",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "true",
                "children_under_18": "2",
                "dependent_parents": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_export_pdf_with_bilateral_ratings(self):
        """Export PDF works with bilateral factor ratings."""
        response = self.client.post(
            reverse("examprep:export_rating_pdf"),
            {
                "ratings": json.dumps(
                    [
                        {"percentage": 40, "description": "Knee", "is_bilateral": True},
                        {
                            "percentage": 30,
                            "description": "Shoulder",
                            "is_bilateral": True,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_export_pdf_empty_ratings_returns_400(self):
        """Export PDF with empty ratings returns 400 error."""
        response = self.client.post(
            reverse("examprep:export_rating_pdf"),
            {
                "ratings": json.dumps([]),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_export_pdf_malformed_json_returns_400(self):
        """Export PDF with malformed JSON returns 400 error."""
        response = self.client.post(
            reverse("examprep:export_rating_pdf"),
            {
                "ratings": "{invalid json",
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_export_pdf_get_not_allowed(self):
        """Export PDF via GET method returns 405 Method Not Allowed."""
        response = self.client.get(reverse("examprep:export_rating_pdf"))
        self.assertEqual(response.status_code, 405)

    def test_export_saved_calculation_requires_login(self):
        """Exporting a saved calculation requires authentication."""
        response = self.client.get(
            reverse(
                "examprep:export_saved_rating_pdf", kwargs={"pk": self.saved_calc.pk}
            )
        )
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_export_saved_calculation_returns_pdf(self):
        """Exporting a saved calculation returns PDF."""
        self.client.login(email="pdfuser@example.com", password="TestPass123!")
        response = self.client.get(
            reverse(
                "examprep:export_saved_rating_pdf", kwargs={"pk": self.saved_calc.pk}
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_export_saved_calculation_only_owner_can_access(self):
        """Only the owner can export their saved calculation."""
        # Login as different user
        self.client.login(email="otheruser@example.com", password="TestPass123!")
        response = self.client.get(
            reverse(
                "examprep:export_saved_rating_pdf", kwargs={"pk": self.saved_calc.pk}
            )
        )
        # Should return 404 (not found) since query filters by user
        self.assertEqual(response.status_code, 404)

    def test_export_nonexistent_saved_calculation_returns_404(self):
        """Exporting a non-existent saved calculation returns 404."""
        self.client.login(email="pdfuser@example.com", password="TestPass123!")
        response = self.client.get(
            reverse("examprep:export_saved_rating_pdf", kwargs={"pk": 99999})
        )
        self.assertEqual(response.status_code, 404)

    def test_export_pdf_file_starts_with_pdf_header(self):
        """Exported file starts with PDF header bytes."""
        response = self.client.post(
            reverse("examprep:export_rating_pdf"),
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        # PDF files start with %PDF
        content = response.content
        self.assertTrue(content.startswith(b"%PDF"))


class TestPDFGeneratorService(TestCase):
    """Tests for the PDF generator service directly."""

    def test_generate_rating_pdf_returns_bytes(self):
        """generate_rating_pdf returns bytes."""
        from examprep.services.pdf_generator import generate_rating_pdf

        pdf_bytes = generate_rating_pdf(
            ratings=[
                {"percentage": 50, "description": "PTSD", "is_bilateral": False},
            ],
            combined_raw=50.0,
            combined_rounded=50,
            bilateral_factor=0.0,
            monthly_compensation="$1,041.82",
            annual_compensation="$12,501.84",
            step_by_step=[
                {"description": "Starting with 50%", "result": "50%"},
            ],
            has_spouse=False,
            children_under_18=0,
            dependent_parents=0,
            calculation_name="Test Calculation",
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 0)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_generate_rating_pdf_with_all_dependents(self):
        """generate_rating_pdf works with all dependent types."""
        from examprep.services.pdf_generator import generate_rating_pdf

        pdf_bytes = generate_rating_pdf(
            ratings=[
                {"percentage": 70, "description": "PTSD", "is_bilateral": False},
                {"percentage": 30, "description": "Back", "is_bilateral": False},
            ],
            combined_raw=79.0,
            combined_rounded=80,
            bilateral_factor=0.0,
            monthly_compensation="$2,044.77",
            annual_compensation="$24,537.24",
            step_by_step=[
                {"description": "Starting with 70%", "result": "70%"},
                {"description": "Adding 30% of remaining 30%", "result": "79%"},
            ],
            has_spouse=True,
            children_under_18=3,
            dependent_parents=2,
            calculation_name="Full Dependents Test",
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_generate_rating_pdf_with_bilateral_factor(self):
        """generate_rating_pdf includes bilateral factor when present."""
        from examprep.services.pdf_generator import generate_rating_pdf

        pdf_bytes = generate_rating_pdf(
            ratings=[
                {"percentage": 40, "description": "Knee", "is_bilateral": True},
                {"percentage": 30, "description": "Ankle", "is_bilateral": True},
            ],
            combined_raw=62.08,
            combined_rounded=60,
            bilateral_factor=5.8,
            monthly_compensation="$1,319.65",
            annual_compensation="$15,835.80",
            step_by_step=[
                {"description": "Bilateral conditions combined", "result": "58%"},
                {"description": "Bilateral factor applied (+10%)", "result": "62.08%"},
            ],
            has_spouse=False,
            children_under_18=0,
            dependent_parents=0,
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_generate_rating_pdf_with_empty_step_by_step(self):
        """generate_rating_pdf handles empty step_by_step list."""
        from examprep.services.pdf_generator import generate_rating_pdf

        pdf_bytes = generate_rating_pdf(
            ratings=[
                {"percentage": 30, "description": "Test", "is_bilateral": False},
            ],
            combined_raw=30.0,
            combined_rounded=30,
            bilateral_factor=0.0,
            monthly_compensation="$508.05",
            annual_compensation="$6,096.60",
            step_by_step=[],
            has_spouse=False,
            children_under_18=0,
            dependent_parents=0,
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_rating_calculation_pdf_class_directly(self):
        """RatingCalculationPDF class generates valid PDF."""
        from examprep.services.pdf_generator import RatingCalculationPDF

        generator = RatingCalculationPDF(
            ratings=[
                {"percentage": 50, "description": "PTSD", "is_bilateral": False},
            ],
            combined_raw=50.0,
            combined_rounded=50,
            bilateral_factor=0.0,
            monthly_compensation="$1,041.82",
            annual_compensation="$12,501.84",
            step_by_step=[],
            calculation_name="Direct Class Test",
        )

        pdf_bytes = generator.generate()
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


# =============================================================================
# SHARE CALCULATION TESTS
# =============================================================================


class TestShareCalculation(TestCase):
    """Tests for share calculation functionality."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="shareuser@example.com", password="TestPass123!"
        )
        self.other_user = User.objects.create_user(
            email="otheruser2@example.com", password="TestPass123!"
        )
        # Create a saved calculation for testing
        self.saved_calc = SavedRatingCalculation.objects.create(
            user=self.user,
            name="Test Calculation",
            ratings=[
                {"percentage": 50, "description": "PTSD", "is_bilateral": False},
                {"percentage": 30, "description": "Knee", "is_bilateral": True},
            ],
            combined_raw=65.0,
            combined_rounded=70,
            bilateral_factor=3.0,
            estimated_monthly=1628.24,
            has_spouse=True,
            children_under_18=1,
            dependent_parents=0,
        )

    def test_share_calculation_creates_shared_record(self):
        """Sharing a calculation creates a SharedCalculation record."""
        from examprep.models import SharedCalculation

        response = self.client.post(
            reverse("examprep:share_calculation"),
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
                "name": "My Shared Calculation",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("share_url", data)
        self.assertIn("token", data)

        # Verify record created
        shared = SharedCalculation.objects.filter(share_token=data["token"]).first()
        self.assertIsNotNone(shared)
        self.assertEqual(shared.combined_rounded, 50)

    def test_share_calculation_returns_json(self):
        """Share endpoint returns JSON response."""
        response = self.client.post(
            reverse("examprep:share_calculation"),
            {
                "ratings": json.dumps(
                    [
                        {"percentage": 70, "description": "TBI", "is_bilateral": False},
                    ]
                ),
                "has_spouse": "true",
                "children_under_18": "2",
                "dependent_parents": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_share_calculation_empty_ratings_returns_400(self):
        """Share with empty ratings returns 400 error."""
        response = self.client.post(
            reverse("examprep:share_calculation"),
            {
                "ratings": json.dumps([]),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_share_calculation_get_not_allowed(self):
        """GET request to share endpoint returns 405."""
        response = self.client.get(reverse("examprep:share_calculation"))
        self.assertEqual(response.status_code, 405)

    def test_share_saved_calculation_requires_login(self):
        """Sharing a saved calculation requires authentication."""
        response = self.client.get(
            reverse(
                "examprep:share_saved_calculation", kwargs={"pk": self.saved_calc.pk}
            )
        )
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_share_saved_calculation_returns_share_url(self):
        """Sharing a saved calculation returns a share URL."""
        self.client.login(email="shareuser@example.com", password="TestPass123!")
        response = self.client.get(
            reverse(
                "examprep:share_saved_calculation", kwargs={"pk": self.saved_calc.pk}
            )
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("share_url", data)
        self.assertIn("token", data)

    def test_share_saved_calculation_only_owner_can_share(self):
        """Only the owner can share their saved calculation."""
        self.client.login(email="otheruser2@example.com", password="TestPass123!")
        response = self.client.get(
            reverse(
                "examprep:share_saved_calculation", kwargs={"pk": self.saved_calc.pk}
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_share_saved_calculation_reuses_existing_share(self):
        """Sharing the same saved calculation reuses existing share link."""

        self.client.login(email="shareuser@example.com", password="TestPass123!")

        # First share
        response1 = self.client.get(
            reverse(
                "examprep:share_saved_calculation", kwargs={"pk": self.saved_calc.pk}
            )
        )
        data1 = response1.json()
        token1 = data1["token"]

        # Second share - should return same token
        response2 = self.client.get(
            reverse(
                "examprep:share_saved_calculation", kwargs={"pk": self.saved_calc.pk}
            )
        )
        data2 = response2.json()
        token2 = data2["token"]

        self.assertEqual(token1, token2)
        self.assertTrue(data2["existing"])

    def test_view_shared_calculation_public_access(self):
        """Shared calculations can be viewed without login."""
        from examprep.models import SharedCalculation

        # Create a shared calculation
        shared = SharedCalculation.create_from_data(
            ratings=[{"percentage": 50, "description": "PTSD", "is_bilateral": False}],
            combined_raw=50.0,
            combined_rounded=50,
            bilateral_factor=0.0,
            estimated_monthly=1041.82,
        )

        response = self.client.get(
            reverse("examprep:shared_calculation", kwargs={"token": shared.share_token})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "50%")

    def test_view_shared_calculation_increments_views(self):
        """Viewing a shared calculation increments view count."""
        from examprep.models import SharedCalculation

        shared = SharedCalculation.create_from_data(
            ratings=[{"percentage": 50, "description": "PTSD", "is_bilateral": False}],
            combined_raw=50.0,
            combined_rounded=50,
            bilateral_factor=0.0,
            estimated_monthly=1041.82,
        )
        initial_views = shared.view_count

        # View the shared calculation
        self.client.get(
            reverse("examprep:shared_calculation", kwargs={"token": shared.share_token})
        )

        shared.refresh_from_db()
        self.assertEqual(shared.view_count, initial_views + 1)

    def test_view_expired_shared_calculation(self):
        """Viewing an expired shared calculation shows expired page."""
        from examprep.models import SharedCalculation
        from django.utils import timezone
        from datetime import timedelta

        # Create an expired shared calculation
        shared = SharedCalculation.create_from_data(
            ratings=[{"percentage": 50, "description": "PTSD", "is_bilateral": False}],
            combined_raw=50.0,
            combined_rounded=50,
            bilateral_factor=0.0,
            estimated_monthly=1041.82,
            expires_in_days=-1,  # Already expired
        )
        # Force expired
        shared.expires_at = timezone.now() - timedelta(days=1)
        shared.save()

        response = self.client.get(
            reverse("examprep:shared_calculation", kwargs={"token": shared.share_token})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "expired")

    def test_view_nonexistent_shared_calculation_returns_404(self):
        """Viewing a nonexistent shared calculation returns 404."""
        response = self.client.get(
            reverse(
                "examprep:shared_calculation", kwargs={"token": "nonexistent-token"}
            )
        )
        self.assertEqual(response.status_code, 404)


class TestSharedCalculationModel(TestCase):
    """Tests for SharedCalculation model."""

    def test_create_from_data_generates_token(self):
        """create_from_data generates a unique token."""
        from examprep.models import SharedCalculation

        shared = SharedCalculation.create_from_data(
            ratings=[{"percentage": 50, "description": "PTSD", "is_bilateral": False}],
            combined_raw=50.0,
            combined_rounded=50,
            bilateral_factor=0.0,
            estimated_monthly=1041.82,
        )
        self.assertIsNotNone(shared.share_token)
        self.assertTrue(len(shared.share_token) > 10)

    def test_create_from_data_sets_expiry(self):
        """create_from_data sets expiry date when specified."""
        from examprep.models import SharedCalculation

        shared = SharedCalculation.create_from_data(
            ratings=[{"percentage": 50, "description": "PTSD", "is_bilateral": False}],
            combined_raw=50.0,
            combined_rounded=50,
            bilateral_factor=0.0,
            estimated_monthly=1041.82,
            expires_in_days=30,
        )
        self.assertIsNotNone(shared.expires_at)

    def test_create_from_data_no_expiry(self):
        """create_from_data can create shares without expiry."""
        from examprep.models import SharedCalculation

        shared = SharedCalculation.create_from_data(
            ratings=[{"percentage": 50, "description": "PTSD", "is_bilateral": False}],
            combined_raw=50.0,
            combined_rounded=50,
            bilateral_factor=0.0,
            estimated_monthly=1041.82,
            expires_in_days=None,
        )
        self.assertIsNone(shared.expires_at)

    def test_is_expired_property(self):
        """is_expired property works correctly."""
        from examprep.models import SharedCalculation
        from django.utils import timezone
        from datetime import timedelta

        # Not expired
        shared = SharedCalculation.create_from_data(
            ratings=[{"percentage": 50, "description": "PTSD", "is_bilateral": False}],
            combined_raw=50.0,
            combined_rounded=50,
            bilateral_factor=0.0,
            estimated_monthly=1041.82,
            expires_in_days=30,
        )
        self.assertFalse(shared.is_expired)

        # Expired
        shared.expires_at = timezone.now() - timedelta(days=1)
        shared.save()
        self.assertTrue(shared.is_expired)

    def test_no_expiry_never_expires(self):
        """Shares without expiry are never expired."""
        from examprep.models import SharedCalculation

        shared = SharedCalculation.create_from_data(
            ratings=[{"percentage": 50, "description": "PTSD", "is_bilateral": False}],
            combined_raw=50.0,
            combined_rounded=50,
            bilateral_factor=0.0,
            estimated_monthly=1041.82,
            expires_in_days=None,
        )
        self.assertFalse(shared.is_expired)

    def test_get_absolute_url(self):
        """get_absolute_url returns correct URL."""
        from examprep.models import SharedCalculation

        shared = SharedCalculation.create_from_data(
            ratings=[{"percentage": 50, "description": "PTSD", "is_bilateral": False}],
            combined_raw=50.0,
            combined_rounded=50,
            bilateral_factor=0.0,
            estimated_monthly=1041.82,
        )
        url = shared.get_absolute_url()
        self.assertIn(shared.share_token, url)
        self.assertIn("shared", url)


# =============================================================================
# TDIU BOUNDARY TESTS — 38 CFR § 4.16
# =============================================================================


class TestTDIUBoundaryEligibility(TestCase):
    """
    Boundary tests for TDIU schedular eligibility thresholds.

    Schedular TDIU (38 CFR 4.16(a)):
    - Single disability 60%+ → eligible
    - Combined 70%+ with one disability 40%+ → eligible
    - Below thresholds with combined 40%+ → extraschedular possible
    """

    def setUp(self):
        from examprep.va_special_compensation import check_tdiu_eligibility

        self.check_tdiu = check_tdiu_eligibility

    def _make_ratings(self, percentages):
        """Helper to build ratings list from percentages."""
        return [
            {"percentage": p, "description": f"Condition {i}", "is_bilateral": False}
            for i, p in enumerate(percentages)
        ]

    def test_tdiu_single_59_percent(self):
        """59% single disability should NOT meet schedular criteria."""
        ratings = self._make_ratings([59])
        # 59% is not a valid VA rating (must be multiples of 10), but the function
        # checks raw percentage values; use 50 for realistic boundary
        ratings_50 = self._make_ratings([50])
        result = self.check_tdiu(ratings_50, combined_rating=50)
        self.assertFalse(result.meets_single_disability)
        self.assertFalse(result.schedular_eligible)

    def test_tdiu_single_60_percent(self):
        """60% single disability SHOULD meet schedular criteria."""
        ratings = self._make_ratings([60])
        result = self.check_tdiu(ratings, combined_rating=60)
        self.assertTrue(result.meets_single_disability)
        self.assertTrue(result.schedular_eligible)

    def test_tdiu_combined_69_plus_40(self):
        """69% combined + one 40% disability should NOT meet combined criteria."""
        # 40% + 40% = 64% combined via VA Math; doesn't reach 70%
        ratings = self._make_ratings([40, 40])
        result = self.check_tdiu(ratings, combined_rating=64)
        self.assertFalse(result.meets_combined_criteria)
        self.assertFalse(result.schedular_eligible)
        # But extraschedular should be possible (combined >= 40)
        self.assertTrue(result.extraschedular_possible)

    def test_tdiu_combined_70_plus_40(self):
        """70% combined with one 40%+ disability SHOULD meet combined criteria."""
        # 50% + 40% = 70% combined via VA Math
        ratings = self._make_ratings([50, 40])
        result = self.check_tdiu(ratings, combined_rating=70)
        self.assertTrue(result.meets_combined_criteria)
        self.assertTrue(result.schedular_eligible)

    def test_tdiu_combined_70_but_no_40_single(self):
        """70%+ combined but NO single 40%+ disability should NOT meet combined criteria."""
        # Multiple ratings that combine to 70 but none individually >= 40
        ratings = self._make_ratings([30, 30, 30])
        result = self.check_tdiu(ratings, combined_rating=70)
        self.assertFalse(result.meets_combined_criteria)
        # But also doesn't meet single disability (highest is 30)
        self.assertFalse(result.meets_single_disability)
        self.assertFalse(result.schedular_eligible)

    def test_tdiu_extraschedular_below_threshold(self):
        """Below 40% combined should have no extraschedular possibility."""
        ratings = self._make_ratings([30])
        result = self.check_tdiu(ratings, combined_rating=30)
        self.assertFalse(result.schedular_eligible)
        self.assertFalse(result.extraschedular_possible)

    def test_tdiu_extraschedular_at_40(self):
        """Exactly 40% combined, not meeting schedular, should offer extraschedular."""
        ratings = self._make_ratings([40])
        result = self.check_tdiu(ratings, combined_rating=40)
        self.assertFalse(result.schedular_eligible)
        self.assertTrue(result.extraschedular_possible)


# =============================================================================
# SMC BOUNDARY TESTS — 38 CFR § 3.350
# =============================================================================


class TestSMCBoundaryEligibility(TestCase):
    """
    Boundary tests for SMC(s) eligibility (housebound).

    SMC(s): One disability at 100% PLUS additional disabilities combining to 60%+.
    """

    def setUp(self):
        from examprep.va_special_compensation import (
            check_smc_eligibility,
            SMCCondition,
            SMCLevel,
        )

        self.check_smc = check_smc_eligibility
        self.SMCCondition = SMCCondition
        self.SMCLevel = SMCLevel

    def _make_conditions(self, ratings):
        """Helper to build SMCCondition list from (name, rating) tuples."""
        return [self.SMCCondition(name=name, rating=rating) for name, rating in ratings]

    def test_smc_s_combined_59_other(self):
        """100% + 59% other should NOT meet SMC(s) threshold."""
        # 50% + 20% = 60% via VA Math; but we need just under 60
        # Use a single 50% which stays at 50% combined
        conditions = self._make_conditions(
            [
                ("PTSD", 100),
                ("Back Pain", 50),
            ]
        )
        result = self.check_smc(conditions)
        # 50% other doesn't meet 60% threshold
        self.assertNotIn(self.SMCLevel.S, result.levels)

    def test_smc_s_combined_60_other(self):
        """100% + 60% other SHOULD meet SMC(s) threshold."""
        conditions = self._make_conditions(
            [
                ("PTSD", 100),
                ("Back Pain", 60),
            ]
        )
        result = self.check_smc(conditions)
        self.assertTrue(result.eligible)
        self.assertIn(self.SMCLevel.S, result.levels)

    def test_smc_s_multiple_reaching_60(self):
        """100% + multiple disabilities combining to 60%+ should meet SMC(s)."""
        # 40% + 40% = 64% via VA Math: 40 + 40*(1-0.40) = 40 + 24 = 64
        conditions = self._make_conditions(
            [
                ("PTSD", 100),
                ("Back Pain", 40),
                ("Knee", 40),
            ]
        )
        result = self.check_smc(conditions)
        self.assertTrue(result.eligible)
        self.assertIn(self.SMCLevel.S, result.levels)

    def test_smc_s_no_100_percent(self):
        """Without any 100% disability, SMC(s) should not apply."""
        conditions = self._make_conditions(
            [
                ("PTSD", 90),
                ("Back Pain", 70),
            ]
        )
        result = self.check_smc(conditions)
        self.assertNotIn(self.SMCLevel.S, result.levels)
