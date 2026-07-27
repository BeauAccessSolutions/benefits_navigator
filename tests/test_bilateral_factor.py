"""The bilateral factor requires a disability in BOTH limbs of a pair.

38 CFR § 4.26 adds 10% when a partial disability results from disease or injury
of **both** arms, of **both** legs, or of paired skeletal muscles. The ratings
for the two sides are combined as usual, 10% of that value is *added* (not
combined), and the result is treated as one disability for further combination.

The calculator applied that 10% to anything flagged ``is_bilateral``, with no
pairing test whatsoever. A single 50% knee rating with the box ticked combined
to 55% and displayed as **60%** — a full rating bracket, and real monthly money,
that the regulation does not grant. ``DisabilityRating.bilateral_group`` had
existed since the file was written and was never read by anything.

The fix records *which* limb each disability affects, because "is this
bilateral?" is not a question a single rating can answer — pairing is a property
of the set.
"""

import pytest

from examprep.va_math import (
    DisabilityRating,
    calculate_combined_rating,
    group_bilateral_ratings,
)


def r(percentage, limb="", **kw):
    """A rating on a given limb; is_bilateral follows from having a limb."""
    return DisabilityRating(
        percentage=percentage,
        is_bilateral=kw.pop("is_bilateral", bool(limb)),
        limb=limb,
        **kw,
    )


class TestTheRegression:
    """The exact case the audit reproduced."""

    def test_one_limb_alone_does_not_get_the_factor(self):
        result = calculate_combined_rating([r(50, "left_leg")])

        assert result.bilateral_factor_applied == 0
        assert result.combined_raw == 50.0
        assert result.combined_rounded == 50  # was 60

    def test_and_the_user_is_told_why(self):
        result = calculate_combined_rating([r(50, "left_leg")])

        assert result.bilateral_notes
        assert "both" in result.bilateral_notes[0]

    def test_the_legacy_boolean_alone_never_qualifies_either(self):
        """A pre-`limb` saved calculation with one flagged rating."""
        result = calculate_combined_rating(
            [DisabilityRating(percentage=50, is_bilateral=True)]
        )

        assert result.bilateral_factor_applied == 0
        assert result.combined_rounded == 50


class TestQualifyingPairs:
    def test_both_legs_qualifies(self):
        result = calculate_combined_rating([r(50, "left_leg"), r(30, "right_leg")])

        # 50 and 30 combine to 65; the factor is 10% of that = 6.5, giving 71.5.
        # The subtotal is then rounded to a whole number (72) before any further
        # combination, because VA's combined-ratings table under 38 CFR § 4.25
        # is defined over whole numbers. That intermediate rounding predates
        # this change and is left alone here; either way the final figure is 70.
        assert result.bilateral_factor_applied == pytest.approx(6.5)
        assert result.combined_raw == pytest.approx(72.0)
        assert result.combined_rounded == 70

    def test_both_arms_qualifies(self):
        result = calculate_combined_rating([r(40, "left_arm"), r(20, "right_arm")])

        assert result.bilateral_factor_applied > 0

    def test_two_disabilities_on_the_same_leg_do_not_qualify(self):
        """
        The case a boolean checkbox cannot distinguish, and the reason the fix
        needed the limb rather than a count.
        """
        result = calculate_combined_rating([r(30, "left_leg"), r(20, "left_leg")])

        assert result.bilateral_factor_applied == 0
        assert any("only the left leg" in n for n in result.bilateral_notes)

    def test_an_arm_and_a_leg_are_not_a_pair(self):
        result = calculate_combined_rating([r(30, "left_arm"), r(30, "right_leg")])

        assert result.bilateral_factor_applied == 0

    def test_arms_and_legs_each_get_their_own_factor(self):
        """
        Two independent pairs. The old single-bucket implementation could not
        express this at all — it lumped every flagged rating into one group.
        """
        result = calculate_combined_rating(
            [
                r(40, "left_arm"),
                r(30, "right_arm"),
                r(20, "left_leg"),
                r(10, "right_leg"),
            ]
        )

        bilateral_phases = [
            s for s in result.step_by_step if s.get("phase") == "bilateral"
        ]
        assert len(bilateral_phases) == 2
        assert {p["group"] for p in bilateral_phases} == {"arm", "leg"}

    def test_a_qualifying_pair_combines_with_unpaired_ratings(self):
        """The pair, with its factor, is one disability for further combining."""
        paired = calculate_combined_rating([r(50, "left_leg"), r(30, "right_leg")])
        with_extra = calculate_combined_rating(
            [r(50, "left_leg"), r(30, "right_leg"), r(20)]
        )

        assert with_extra.combined_raw > paired.combined_raw
        assert with_extra.bilateral_factor_applied == paired.bilateral_factor_applied


class TestUnqualifiedRatingsStillCount:
    def test_a_lone_limb_rating_is_still_combined_normally(self):
        """Declining the factor must not drop the rating from the calculation."""
        result = calculate_combined_rating([r(50, "left_leg"), r(30)])

        assert result.combined_raw == pytest.approx(65.0)
        assert result.bilateral_factor_applied == 0


class TestLegacySavedCalculations:
    """
    Rows saved before ``limb`` existed carry only the boolean. Sides cannot be
    recovered, so they are held to the weaker test that is still necessary —
    two or more flagged ratings — and told the pairing is unverified.
    """

    def _legacy(self, *percentages):
        return [DisabilityRating(percentage=p, is_bilateral=True) for p in percentages]

    def test_two_legacy_flagged_ratings_still_get_the_factor(self):
        result = calculate_combined_rating(self._legacy(50, 30))

        assert result.bilateral_factor_applied == pytest.approx(6.5)

    def test_but_the_result_says_the_pairing_is_unverified(self):
        result = calculate_combined_rating(self._legacy(50, 30))

        assert any("could not be verified" in n for n in result.bilateral_notes)

    def test_mixing_legacy_and_limb_data_does_not_silently_pair_them(self):
        """A legacy row must not be treated as the missing second side."""
        result = calculate_combined_rating(
            [r(50, "left_leg"), DisabilityRating(percentage=30, is_bilateral=True)]
        )

        assert result.bilateral_factor_applied == 0


class TestGroupingHelper:
    def test_it_reports_qualifying_groups_and_leftovers(self):
        groups, unqualified, notes = group_bilateral_ratings(
            [r(30, "left_arm"), r(20, "right_arm"), r(10, "left_leg")]
        )

        assert set(groups) == {"arm"}
        assert [u.limb for u in unqualified] == ["left_leg"]
        assert notes

    def test_no_bilateral_ratings_is_quiet(self):
        groups, unqualified, notes = group_bilateral_ratings([r(30), r(20)])

        assert groups == {} and unqualified == [] and notes == []


@pytest.mark.django_db
class TestCalculatorEndpoint:
    def test_the_endpoint_declines_the_factor_for_a_single_limb(self, client):
        import json

        from django.urls import reverse

        response = client.post(
            reverse("examprep:calculate_rating"),
            {
                "ratings": json.dumps(
                    [{"percentage": 50, "is_bilateral": True, "limb": "left_leg"}]
                )
            },
        )
        html = response.content.decode()

        assert response.status_code == 200
        assert "60%" not in html
        assert "About the bilateral factor" in html

    def test_the_limb_is_named_in_the_result(self, client):
        """ "(Left Leg)", not a bare "(B)" — which limb is what decides the factor."""
        import json

        from django.urls import reverse

        response = client.post(
            reverse("examprep:calculate_rating"),
            {
                "ratings": json.dumps(
                    [
                        {"percentage": 50, "is_bilateral": True, "limb": "left_leg"},
                        {"percentage": 30, "is_bilateral": True, "limb": "right_leg"},
                    ]
                )
            },
        )
        html = response.content.decode()

        assert "(Left Leg)" in html and "(Right Leg)" in html
