"""Report whether the VA compensation rate tables are current.

Companion to the CI gate in ``tests/test_rate_currency.py``. The test fails the
build once the tables fall behind; this command is what you run on a schedule
or by hand to get warning *before* that happens, and to see the December
checklist without going to find it.

Exit codes make it usable as a cron/monitoring check:
    0  current
    1  overdue — the rate year in force is missing from the tables
    0  due soon (warns on stderr, does not fail)
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from examprep.va_math import rate_currency_status

CHECKLIST = """
December update checklist (also in CLAUDE.md):
  1. Read the new rates from
     https://www.va.gov/disability/compensation-rates/veteran-rates/
  2. examprep/va_math.py — add VA_COMPENSATION_RATES_{year} and
     DEPENDENT_RATES_{year}, then register both in the *_BY_YEAR maps
  3. examprep/va_special_compensation.py — SMC rates
  4. Add {year} to AVAILABLE_RATE_YEARS
  5. Add tests for the new rate year
  6. Re-verify the bilateral factor and rounding against 38 CFR § 4.25
"""


class Command(BaseCommand):
    help = "Check whether VA compensation rate tables cover the current rate year."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            dest="as_of",
            help="Check as of a specific date (YYYY-MM-DD) instead of today.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Also exit non-zero when an update is merely due soon.",
        )

    def handle(self, *args, **options):
        as_of = None
        if options.get("as_of"):
            try:
                as_of = date.fromisoformat(options["as_of"])
            except ValueError:
                raise CommandError("--date must be YYYY-MM-DD")

        status = rate_currency_status(as_of)

        self.stdout.write(f"Checked as of:     {status['today']}")
        self.stdout.write(f"Rate year in force: {status['required_rate_year']}")
        self.stdout.write(f"Newest table:       {status['latest_available_rate_year']}")
        self.stdout.write(
            f"Next COLA:          {status['next_cola_date']} "
            f"({status['days_until_next_cola']} days)"
        )

        if status["is_overdue"]:
            self.stderr.write(self.style.ERROR(status["message"]))
            self.stderr.write(
                CHECKLIST.format(year=status["required_rate_year"]).strip()
            )
            raise CommandError("Rate tables are out of date.")

        if status["is_due_soon"]:
            self.stderr.write(self.style.WARNING(status["message"]))
            self.stderr.write(
                CHECKLIST.format(year=status["required_rate_year"] + 1).strip()
            )
            if options["strict"]:
                raise CommandError("Rate update is due soon (--strict).")
            return

        self.stdout.write(self.style.SUCCESS(status["message"]))
