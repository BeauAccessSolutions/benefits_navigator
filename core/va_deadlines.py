"""Per-lane VA appeal deadlines, in one place, with the CFR citations.

The three review lanes after a rating decision do **not** share a deadline:

===================  ==========================  ====================
Lane                 Deadline                    Authority
===================  ==========================  ====================
Higher-Level Review  1 year from decision        38 CFR § 20.202
Board Appeal         1 year from decision        38 CFR § 20.202
Supplemental Claim   **none**                    38 CFR § 20.204
===================  ==========================  ====================

The one-year mark still matters for a Supplemental Claim, but for a different
reason and with a different consequence: filing within a year of the decision
preserves the original effective date, so it governs *back pay*, not
eligibility. Missing it costs money; it does not close the door.

Collapsing all of that into a single ``appeal_deadline`` date is how the app
came to show veterans a red "Appeal Deadline: <date>" banner after a decision
letter analysis. For anyone whose best route was a Supplemental Claim — the
recommended lane whenever there is new evidence — that banner said their time
had run out when it had not. This module exists so the distinction is computed
once, cited once, and cannot drift between the analyzer, the models, and the
templates.

See also ``appeals.models.Appeal.save()``, which already exempts supplemental
claims from deadline auto-calculation, and ``appeals/forms.py``, which stopped
rejecting year-old decisions at intake.
"""

from datetime import timedelta

# 38 CFR § 20.202 — one year from the date of the decision notice.
APPEAL_PERIOD_DAYS = 365

# Lanes that close one year after the decision.
TIME_BARRED_LANES = ("higher_level_review", "board_appeal")

SUPPLEMENTAL_CLAIM_NOTE = (
    "No deadline — but filing within 1 year of the decision protects your "
    "effective date (back pay)."
)


def lanes_from_filing_deadline(one_year):
    """
    Build the per-lane mapping from an already-computed one-year date.

    For callers holding the deadline rather than the decision date — the
    ``DecisionLetterAnalysis.appeal_deadline`` column stores exactly this.
    """
    if not one_year:
        return None

    return {
        "higher_level_review": one_year,
        "board_appeal": one_year,
        "supplemental_claim": None,
        "effective_date_protection": one_year,
        "supplemental_claim_note": SUPPLEMENTAL_CLAIM_NOTE,
    }


def appeal_deadlines(decision_date):
    """
    Return each lane's deadline for a decision issued on ``decision_date``.

    ``supplemental_claim`` is ``None`` on purpose, and callers must render that
    as "no deadline" rather than as missing data. ``effective_date_protection``
    carries the one-year mark that does apply to that lane, so nothing is lost
    by not pretending it is a filing deadline.

    Returns ``None`` when the decision date is unknown — there is nothing to
    compute from, and inventing a deadline is the failure mode this replaces.
    """
    if not decision_date:
        return None

    return lanes_from_filing_deadline(
        decision_date + timedelta(days=APPEAL_PERIOD_DAYS)
    )


def appeal_deadlines_iso(decision_date):
    """``appeal_deadlines`` with dates as ISO strings, for JSON payloads."""
    deadlines = appeal_deadlines(decision_date)
    if deadlines is None:
        return None

    return {
        key: (value.isoformat() if hasattr(value, "isoformat") else value)
        for key, value in deadlines.items()
    }
