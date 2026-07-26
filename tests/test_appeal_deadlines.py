"""Appeal deadlines are per lane, and a Supplemental Claim has none.

38 CFR § 20.202 gives Higher-Level Review and Board Appeal one year from the
decision. 38 CFR § 20.204 gives a Supplemental Claim no deadline at all — the
one-year mark matters there only because filing within it preserves the
effective date, which governs back pay rather than eligibility.

The analyzer used to flatten all three into one ``appeal_deadline`` date, and
the result templates rendered it in a red box captioned "Appeal Deadline". For
a veteran whose recommended route was a Supplemental Claim — which is the
recommendation whenever there is new evidence — the app was telling them their
time had run out while their best option was still open.

These tests pin the distinction at all three levels it has to survive: the
calculation, the analyzer's output payload, and the page the veteran reads.
"""

from datetime import date, timedelta

import pytest

from agents.models import AgentInteraction, DecisionLetterAnalysis
from core.va_deadlines import (
    appeal_deadlines,
    appeal_deadlines_iso,
    lanes_from_filing_deadline,
)

DECISION_DATE = date(2025, 3, 10)
ONE_YEAR_LATER = date(2026, 3, 10)


class TestDeadlineCalculation:
    def test_time_barred_lanes_get_one_year(self):
        deadlines = appeal_deadlines(DECISION_DATE)

        assert deadlines["higher_level_review"] == ONE_YEAR_LATER
        assert deadlines["board_appeal"] == ONE_YEAR_LATER

    def test_supplemental_claim_has_no_deadline(self):
        """The whole point: None means 'no deadline', not 'unknown'."""
        assert appeal_deadlines(DECISION_DATE)["supplemental_claim"] is None

    def test_one_year_mark_is_kept_as_effective_date_protection(self):
        """The date still matters for back pay — it just isn't a filing bar."""
        deadlines = appeal_deadlines(DECISION_DATE)

        assert deadlines["effective_date_protection"] == ONE_YEAR_LATER
        assert "effective date" in deadlines["supplemental_claim_note"]

    def test_no_decision_date_invents_no_deadline(self):
        assert appeal_deadlines(None) is None
        assert appeal_deadlines_iso(None) is None

    def test_iso_variant_serialises_dates_and_keeps_the_none(self):
        deadlines = appeal_deadlines_iso(DECISION_DATE)

        assert deadlines["higher_level_review"] == "2026-03-10"
        assert deadlines["supplemental_claim"] is None

    def test_lanes_can_be_built_from_a_stored_deadline(self):
        """The model column holds the one-year date, not the decision date."""
        assert lanes_from_filing_deadline(ONE_YEAR_LATER) == appeal_deadlines(
            DECISION_DATE
        )

    def test_a_decision_over_a_year_old_still_leaves_supplemental_open(self):
        """The case the intake form used to reject outright."""
        old = date.today() - timedelta(days=550)
        deadlines = appeal_deadlines(old)

        assert deadlines["higher_level_review"] < date.today()  # time-barred
        assert deadlines["supplemental_claim"] is None  # still open


@pytest.mark.django_db
class TestAnalysisModel:
    def _analysis(self, user, deadline):
        interaction = AgentInteraction.objects.create(
            user=user, agent_type="decision_analyzer"
        )
        return DecisionLetterAnalysis.objects.create(
            interaction=interaction, user=user, appeal_deadline=deadline
        )

    def test_per_lane_deadlines_derive_from_the_stored_date(self, user):
        analysis = self._analysis(user, ONE_YEAR_LATER)

        assert analysis.appeal_deadlines["higher_level_review"] == ONE_YEAR_LATER
        assert analysis.appeal_deadlines["supplemental_claim"] is None

    def test_no_stored_deadline_yields_nothing_to_render(self, user):
        assert self._analysis(user, None).appeal_deadlines is None


@pytest.mark.django_db
class TestResultPageWording:
    """What the veteran actually reads."""

    def _rendered(self, user, document, template):
        from django.template.loader import render_to_string

        interaction = AgentInteraction.objects.create(
            user=user, agent_type="decision_analyzer"
        )
        analysis = DecisionLetterAnalysis.objects.create(
            interaction=interaction,
            user=user,
            appeal_deadline=ONE_YEAR_LATER,
            summary="Knee granted, back denied.",
        )
        # denial_decoder_result.html gates its results block on a completed
        # document plus a decoding; supply both so the deadline block renders.
        from agents.models import DenialDecoding

        return render_to_string(
            template,
            {
                "analysis": analysis,
                "user": user,
                "document": document,
                "decoding": DenialDecoding.objects.create(analysis=analysis),
            },
        )

    @pytest.mark.parametrize(
        "template",
        [
            "agents/decision_analyzer_result.html",
            "claims/denial_decoder_result.html",
        ],
    )
    def test_page_names_both_lanes_and_denies_a_supplemental_deadline(
        self, user, document, template
    ):
        html = self._rendered(user, document, template)

        assert "Higher-Level Review or Board Appeal" in html
        assert "March 10, 2026" in html
        assert "Supplemental Claim" in html
        assert "no deadline" in html
        assert "effective date" in html

    @pytest.mark.parametrize(
        "template",
        [
            "agents/decision_analyzer_result.html",
            "claims/denial_decoder_result.html",
        ],
    )
    def test_page_no_longer_shows_a_bare_appeal_deadline_banner(
        self, user, document, template
    ):
        """The exact string that made the claim the CFR contradicts."""
        html = self._rendered(user, document, template)

        assert "Appeal Deadline:" not in html
