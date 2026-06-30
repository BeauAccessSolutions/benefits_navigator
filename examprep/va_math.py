"""
VA Combined Rating Calculator - Accurate Implementation

The VA uses a "whole person" theory for combining disability ratings.
Each rating is applied to the remaining "healthy" percentage, not added directly.

References:
- 38 CFR § 4.25 - Combined ratings table
- 38 CFR § 4.26 - Bilateral factor
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class DisabilityRating:
    """Individual disability rating"""

    percentage: int
    description: str = ""
    is_bilateral: bool = False
    bilateral_group: str = ""  # e.g., "upper", "lower" for grouping


@dataclass
class CalculationResult:
    """Result of VA combined rating calculation"""

    combined_raw: float
    combined_rounded: int
    bilateral_factor_applied: float
    step_by_step: List[dict]
    ratings_used: List[DisabilityRating]
    estimated_monthly: Optional[float] = None


def validate_rating(percentage: int) -> bool:
    """
    Validate that a rating is a valid VA disability percentage.
    VA ratings must be 0-100 in increments of 10.
    """
    return 0 <= percentage <= 100 and percentage % 10 == 0


def combine_two_ratings(rating1: int, rating2: int) -> float:
    """
    Combine two disability ratings using VA Math formula.

    Formula: A + B(1-A) = Combined
    Where A and B are expressed as decimals.

    Example: 50% + 30%
    - 0.50 + 0.30(1 - 0.50) = 0.50 + 0.30(0.50) = 0.50 + 0.15 = 0.65 = 65%
    """
    # Convert to decimals
    a = rating1 / 100.0
    b = rating2 / 100.0

    # Apply formula: combined = A + B(1-A)
    combined = a + b * (1 - a)

    return combined * 100


def combine_multiple_ratings(ratings: List[int]) -> Tuple[float, List[dict]]:
    """
    Combine multiple disability ratings in order from highest to lowest.

    Returns the combined percentage (not rounded) and step-by-step calculations.
    """
    if not ratings:
        return 0.0, []

    if len(ratings) == 1:
        return float(ratings[0]), [
            {
                "step": 1,
                "rating": ratings[0],
                "combined_before": 0,
                "combined_after": float(ratings[0]),
                "explanation": f"Single rating: {ratings[0]}%",
            }
        ]

    # Sort ratings highest to lowest (VA requirement)
    sorted_ratings = sorted(ratings, reverse=True)

    steps = []
    combined = float(sorted_ratings[0])

    steps.append(
        {
            "step": 1,
            "rating": sorted_ratings[0],
            "combined_before": 0,
            "combined_after": combined,
            "explanation": f"Start with highest rating: {sorted_ratings[0]}%",
        }
    )

    for i, rating in enumerate(sorted_ratings[1:], start=2):
        before = combined
        combined = combine_two_ratings(int(round(combined)), rating)

        remaining = 100 - before
        contribution = rating * remaining / 100

        steps.append(
            {
                "step": i,
                "rating": rating,
                "combined_before": before,
                "combined_after": combined,
                "remaining_healthy": remaining,
                "contribution": contribution,
                "explanation": (
                    f"Add {rating}%: {rating}% × {remaining:.1f}% remaining = "
                    f"{contribution:.1f}% → Combined: {combined:.1f}%"
                ),
            }
        )

    return combined, steps


def calculate_bilateral_factor(bilateral_ratings: List[int]) -> Tuple[float, float]:
    """
    Calculate the bilateral factor for paired extremity conditions.

    Per 38 CFR § 4.26:
    1. Combine all bilateral ratings
    2. Add 10% of that combined value as the bilateral factor

    Returns: (combined_bilateral, bilateral_factor_bonus)
    """
    if not bilateral_ratings:
        return 0.0, 0.0

    combined, _ = combine_multiple_ratings(bilateral_ratings)

    # Bilateral factor is 10% of the combined bilateral rating
    bilateral_factor = combined * 0.10

    return combined, bilateral_factor


def round_to_nearest_10(value: float) -> int:
    """
    Round combined rating to nearest 10% per VA rules.

    Per 38 CFR § 4.25:
    - 0.5 and above rounds up
    - Below 0.5 rounds down

    Examples:
    - 65% rounds to 70%
    - 64% rounds to 60%
    - 75% rounds to 80%
    """
    # Use Decimal for precise rounding
    d = Decimal(str(value))
    # Divide by 10, round to nearest integer, multiply by 10
    rounded = int(Decimal(d / 10).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 10)
    return min(100, max(0, rounded))


def calculate_combined_rating(ratings: List[DisabilityRating]) -> CalculationResult:
    """
    Calculate combined VA disability rating with full bilateral factor support.

    Process:
    1. Separate bilateral and non-bilateral ratings
    2. Combine bilateral ratings and add 10% bilateral factor
    3. Combine bilateral result with non-bilateral ratings
    4. Round to nearest 10%
    """
    if not ratings:
        return CalculationResult(
            combined_raw=0.0,
            combined_rounded=0,
            bilateral_factor_applied=0.0,
            step_by_step=[],
            ratings_used=[],
        )

    # Separate bilateral and non-bilateral ratings
    bilateral_ratings = [r for r in ratings if r.is_bilateral]
    non_bilateral_ratings = [r for r in ratings if not r.is_bilateral]

    all_steps = []
    bilateral_factor_bonus = 0.0

    # Process bilateral ratings if any
    bilateral_combined = 0.0
    if bilateral_ratings:
        bilateral_percentages = [r.percentage for r in bilateral_ratings]
        bilateral_combined, bilateral_steps = combine_multiple_ratings(
            bilateral_percentages
        )

        # Add bilateral factor (10% of combined bilateral)
        bilateral_factor_bonus = bilateral_combined * 0.10
        bilateral_with_factor = bilateral_combined + bilateral_factor_bonus

        all_steps.append(
            {
                "phase": "bilateral",
                "description": "Bilateral Conditions (paired extremities)",
                "ratings": bilateral_percentages,
                "combined": bilateral_combined,
                "bilateral_factor": bilateral_factor_bonus,
                "total_with_factor": bilateral_with_factor,
                "steps": bilateral_steps,
            }
        )

        # The bilateral total (with factor) is treated as one rating
        all_percentages = [bilateral_with_factor] + [
            r.percentage for r in non_bilateral_ratings
        ]
    else:
        all_percentages = [r.percentage for r in non_bilateral_ratings]

    # Combine all ratings
    if all_percentages:
        # Convert to integers for combination (bilateral total might be float)
        int_percentages = [int(round(p)) for p in all_percentages]
        final_combined, final_steps = combine_multiple_ratings(int_percentages)

        all_steps.append(
            {
                "phase": "final",
                "description": "Final Combination",
                "ratings": int_percentages,
                "combined_raw": final_combined,
                "steps": final_steps,
            }
        )
    else:
        final_combined = 0.0

    # Round to nearest 10%
    rounded = round_to_nearest_10(final_combined)

    return CalculationResult(
        combined_raw=final_combined,
        combined_rounded=rounded,
        bilateral_factor_applied=bilateral_factor_bonus,
        step_by_step=all_steps,
        ratings_used=ratings,
    )


# 2026 VA Compensation Rates (effective December 1, 2025)
# 2.8% COLA increase from 2025
VA_COMPENSATION_RATES_2026 = {
    0: 0.00,
    10: 180.42,
    20: 356.66,
    30: 552.47,
    40: 795.84,
    50: 1132.90,
    60: 1435.02,
    70: 1808.45,
    80: 2102.15,
    90: 2362.30,
    100: 3938.58,
}

# Additional amounts for dependents at 30%+ rating (2026)
DEPENDENT_RATES_2026 = {
    "spouse": {
        30: 63.74,
        40: 85.33,
        50: 106.91,
        60: 128.50,
        70: 150.09,
        80: 170.65,
        90: 192.24,
        100: 214.21,
    },
    "child_under_18": {
        30: 31.87,
        40: 42.15,
        50: 53.46,
        60: 63.74,
        70: 74.02,
        80: 85.33,
        90: 95.61,
        100: 106.45,
    },
    "parent_one": {
        30: 55.51,
        40: 73.00,
        50: 91.51,
        60: 110.00,
        70: 128.50,
        80: 147.00,
        90: 165.51,
        100: 183.64,
    },
}

# 2025 VA Compensation Rates (effective December 1, 2024)
# 2.5% COLA increase from 2024
VA_COMPENSATION_RATES_2025 = {
    0: 0.00,
    10: 175.51,
    20: 346.95,
    30: 537.42,
    40: 774.16,
    50: 1102.04,
    60: 1395.93,
    70: 1759.19,
    80: 2044.89,
    90: 2297.96,
    100: 3831.30,
}

# Additional amounts for dependents at 30%+ rating (2025)
DEPENDENT_RATES_2025 = {
    "spouse": {
        30: 63.55,
        40: 85.08,
        50: 106.60,
        60: 128.13,
        70: 149.65,
        80: 170.15,
        90: 191.68,
        100: 213.59,
    },
    "child_under_18": {
        30: 31.78,
        40: 42.03,
        50: 53.30,
        60: 63.55,
        70: 73.80,
        80: 85.08,
        90: 95.33,
        100: 106.14,
    },
    "parent_one": {
        30: 55.35,
        40: 72.78,
        50: 91.23,
        60: 109.68,
        70: 128.13,
        80: 146.58,
        90: 165.03,
        100: 183.10,
    },
}

# 2024 VA Compensation Rates (effective December 1, 2023)
# These are monthly rates for veterans with no dependents
VA_COMPENSATION_RATES_2024 = {
    0: 0.00,
    10: 171.23,
    20: 338.49,
    30: 524.31,
    40: 755.28,
    50: 1075.16,
    60: 1361.88,
    70: 1716.28,
    80: 1995.01,
    90: 2241.91,
    100: 3737.85,
}

# Additional amounts for dependents at 30%+ rating
DEPENDENT_RATES_2024 = {
    "spouse": {
        30: 62.00,
        40: 83.00,
        50: 104.00,
        60: 125.00,
        70: 146.00,
        80: 166.00,
        90: 187.00,
        100: 208.38,
    },
    "child_under_18": {
        30: 31.00,
        40: 41.00,
        50: 52.00,
        60: 62.00,
        70: 72.00,
        80: 83.00,
        90: 93.00,
        100: 103.55,
    },
    "parent_one": {
        30: 54.00,
        40: 71.00,
        50: 89.00,
        60: 107.00,
        70: 125.00,
        80: 143.00,
        90: 161.00,
        100: 178.63,
    },
}

# 2023 VA Compensation Rates (effective December 1, 2022)
# 8.7% COLA increase from 2022
VA_COMPENSATION_RATES_2023 = {
    0: 0.00,
    10: 165.92,
    20: 327.99,
    30: 508.05,
    40: 731.86,
    50: 1041.82,
    60: 1319.65,
    70: 1663.06,
    80: 1933.15,
    90: 2172.39,
    100: 3621.95,
}

# 2022 VA Compensation Rates (effective December 1, 2021)
# 5.9% COLA increase from 2021
VA_COMPENSATION_RATES_2022 = {
    0: 0.00,
    10: 152.64,
    20: 301.74,
    30: 467.39,
    40: 673.28,
    50: 958.44,
    60: 1214.03,
    70: 1529.95,
    80: 1778.43,
    90: 1998.52,
    100: 3332.06,
}

# 2021 VA Compensation Rates (effective December 1, 2020)
# 1.3% COLA increase from 2020
VA_COMPENSATION_RATES_2021 = {
    0: 0.00,
    10: 144.14,
    20: 284.93,
    30: 441.35,
    40: 635.77,
    50: 905.04,
    60: 1146.39,
    70: 1444.71,
    80: 1679.35,
    90: 1887.18,
    100: 3146.42,
}

# 2020 VA Compensation Rates (effective December 1, 2019)
# 1.6% COLA increase from 2019
VA_COMPENSATION_RATES_2020 = {
    0: 0.00,
    10: 142.29,
    20: 281.27,
    30: 435.69,
    40: 627.61,
    50: 893.43,
    60: 1131.68,
    70: 1426.17,
    80: 1657.80,
    90: 1862.96,
    100: 3106.04,
}

# Master lookup for all years
VA_COMPENSATION_RATES_BY_YEAR = {
    2026: VA_COMPENSATION_RATES_2026,
    2025: VA_COMPENSATION_RATES_2025,
    2024: VA_COMPENSATION_RATES_2024,
    2023: VA_COMPENSATION_RATES_2023,
    2022: VA_COMPENSATION_RATES_2022,
    2021: VA_COMPENSATION_RATES_2021,
    2020: VA_COMPENSATION_RATES_2020,
}

# Dependent rates by year
DEPENDENT_RATES_BY_YEAR = {
    2026: DEPENDENT_RATES_2026,
    2025: DEPENDENT_RATES_2025,
    2024: DEPENDENT_RATES_2024,
}

# Available rate years (most recent first)
AVAILABLE_RATE_YEARS = [2026, 2025, 2024, 2023, 2022, 2021, 2020]


def estimate_monthly_compensation(
    combined_rating: int,
    spouse: bool = False,
    children_under_18: int = 0,
    dependent_parents: int = 0,
    year: int = 2026,
) -> float:
    """
    Estimate monthly VA disability compensation.

    Args:
        combined_rating: The combined VA disability rating (0-100, multiples of 10)
        spouse: Whether veteran has a spouse
        children_under_18: Number of children under 18
        dependent_parents: Number of dependent parents (max 2)
        year: The rate year to use (2020-2026). Defaults to 2026.

    Note: This is an estimate. Actual rates depend on many factors
    including effective date, special monthly compensation, etc.
    Dependent rates are available for 2024-2026; for earlier years,
    only base rates are applied.
    """
    # Get rates for the specified year, fallback to 2026
    rates = VA_COMPENSATION_RATES_BY_YEAR.get(year, VA_COMPENSATION_RATES_2026)

    if combined_rating not in rates:
        return 0.0

    base = rates[combined_rating]
    total = base

    # Dependents only add to 30%+ ratings
    dep_rates = DEPENDENT_RATES_BY_YEAR.get(year)
    if combined_rating >= 30 and dep_rates:
        if spouse and combined_rating in dep_rates["spouse"]:
            total += dep_rates["spouse"][combined_rating]

        for _ in range(children_under_18):
            if combined_rating in dep_rates["child_under_18"]:
                total += dep_rates["child_under_18"][combined_rating]

        for _ in range(min(2, dependent_parents)):  # Max 2 parents
            if combined_rating in dep_rates["parent_one"]:
                total += dep_rates["parent_one"][combined_rating]

    return round(total, 2)


def format_currency(amount: float) -> str:
    """Format amount as USD currency"""
    return f"${amount:,.2f}"
