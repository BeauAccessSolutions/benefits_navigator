"""CI gate: the VA compensation rate tables must cover the year in force.

VA rates change every December 1 with the COLA. Keeping up was a checklist in
CLAUDE.md and a note to update ``AVAILABLE_RATE_YEARS`` — that is, it depended
on somebody remembering, in December, a year after the last time they did it.

It had already failed. The rating calculator defaulted to the **2024** rates
and labelled them "(Current)" in its year picker, so a veteran who did not
change the dropdown was quoted a two-year-stale monthly dollar figure — under
a heading that said 2024 while the page itself was being served in 2026. The
combined-rating math was right; the money was wrong.

So the reminder becomes a build failure. ``test_rate_tables_cover_the_current_rate_year``
is the gate: it goes red the moment the rates in force are missing, whoever is
or isn't paying attention. The rest of the file pins the date arithmetic, which
is the part most likely to be quietly wrong — a rate year starts the December 1
*before* the year it is named for.
"""

from datetime import date

import pytest

from examprep.va_math import (
    AVAILABLE_RATE_YEARS,
    current_rate_year,
    default_rate_year,
    estimate_monthly_compensation,
    latest_available_rate_year,
    next_cola_date,
    rate_currency_status,
)

# =============================================================================
# THE GATE
# =============================================================================


def test_rate_tables_cover_the_current_rate_year():
    """
    Fails when the VA rates in force are not in the tables.

    If you are reading this because CI went red: the December COLA landed and
    the new rates have not been added. Run

        python manage.py check_rate_currency

    for the checklist. Do not skip this test to get the build green — a green
    build here means the app is quoting veterans the right dollars.
    """
    status = rate_currency_status()

    assert not status["is_overdue"], status["message"]


def test_the_default_year_is_a_year_we_have_rates_for():
    """Whatever the date, the app must never select a missing table."""
    assert default_rate_year() in AVAILABLE_RATE_YEARS


# =============================================================================
# DATE ARITHMETIC — deterministic, not dependent on when the suite runs
# =============================================================================


class TestCurrentRateYear:
    @pytest.mark.parametrize(
        "today,expected",
        [
            (date(2026, 1, 1), 2026),  # early in the year
            (date(2026, 7, 26), 2026),  # mid-year
            (date(2026, 11, 30), 2026),  # day before the COLA
            (date(2026, 12, 1), 2027),  # COLA day — next year's rates begin
            (date(2026, 12, 31), 2027),  # after the COLA
            (date(2027, 1, 1), 2027),
        ],
    )
    def test_the_rate_year_turns_over_on_december_first(self, today, expected):
        assert current_rate_year(today) == expected

    def test_next_cola_is_december_first_this_year_before_it_happens(self):
        assert next_cola_date(date(2026, 7, 26)) == date(2026, 12, 1)

    def test_next_cola_rolls_over_once_it_has_passed(self):
        assert next_cola_date(date(2026, 12, 2)) == date(2027, 12, 1)

    def test_on_cola_day_the_next_one_is_a_year_out(self):
        """
        Consistency with current_rate_year, which treats Dec 1 as the day the
        new rates take effect. Reporting "next COLA: 0 days" alongside a rate
        year that has already turned over would read as time still to prepare.
        """
        assert next_cola_date(date(2026, 12, 1)) == date(2027, 12, 1)


class TestCurrencyStatus:
    def test_overdue_once_the_cola_passes_without_new_rates(self):
        """Simulates December 2026 arriving with no 2027 table."""
        status = rate_currency_status(date(2026, 12, 1))

        assert status["is_overdue"]
        assert status["required_rate_year"] == 2027
        assert "missing" in status["message"]

    def test_due_soon_in_the_run_up_to_the_cola(self):
        status = rate_currency_status(date(2026, 11, 1))

        assert not status["is_overdue"]
        assert status["is_due_soon"]
        assert "take effect in" in status["message"]

    def test_quiet_the_rest_of_the_year(self):
        status = rate_currency_status(date(2026, 7, 26))

        assert not status["is_overdue"]
        assert not status["is_due_soon"]
        assert "current through" in status["message"]


class TestDefaultRateYear:
    def test_it_follows_the_year_in_force(self):
        assert default_rate_year(date(2026, 7, 26)) == 2026

    def test_it_degrades_to_the_newest_table_rather_than_raising(self):
        """
        On the day the COLA moves and the table is not in yet, quoting last
        year's rates is wrong but survivable; a KeyError on the calculator is
        not. The gate above is what makes the shortfall loud.
        """
        assert default_rate_year(date(2026, 12, 1)) == latest_available_rate_year()


class TestEstimatorUsesTheCurrentYear:
    def test_no_explicit_year_uses_the_year_in_force(self):
        """
        The regression: this defaulted to a hardcoded year, so the estimate
        silently stayed on an old table after the COLA.
        """
        from examprep.va_math import VA_COMPENSATION_RATES_BY_YEAR

        expected = VA_COMPENSATION_RATES_BY_YEAR[default_rate_year(date(2026, 7, 26))]

        assert estimate_monthly_compensation(
            50, today=date(2026, 7, 26)
        ) == pytest.approx(expected[50])

    def test_an_explicit_year_still_wins(self):
        """Historical lookups must keep working — veterans compare years."""
        from examprep.va_math import VA_COMPENSATION_RATES_2020

        assert estimate_monthly_compensation(50, year=2020) == pytest.approx(
            VA_COMPENSATION_RATES_2020[50]
        )


@pytest.mark.django_db
class TestCalculatorPageShowsTheCurrentYear:
    def test_the_page_labels_the_year_in_force_as_current(self, client):
        """
        It used to hardcode 2024 as selected and captioned "(Current)". The
        page must name the year actually in force.
        """
        from django.urls import reverse

        response = client.get(reverse("examprep:rating_calculator"))
        html = response.content.decode()
        expected = default_rate_year()

        assert f"{expected} Rates (Current)" in " ".join(html.split())
        assert response.context["current_rate_year"] == expected
