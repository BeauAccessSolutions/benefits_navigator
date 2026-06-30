"""
Management command to set up pilot test accounts with sample data.

Usage:
    python manage.py setup_pilot_accounts
    python manage.py setup_pilot_accounts --clean  # Remove existing pilot data first
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from allauth.account.models import EmailAddress
from datetime import timedelta
import json

User = get_user_model()

PILOT_PASSWORD = "PilotTest2026!"

PILOT_ACCOUNTS = [
    {
        "email": "pilot_a@test.com",
        "first_name": "Pilot",
        "last_name": "PathA",
        "description": "Document upload path tester",
    },
    {
        "email": "pilot_b@test.com",
        "first_name": "Pilot",
        "last_name": "PathB",
        "description": "Rating calculator path tester",
    },
    {
        "email": "pilot_both@test.com",
        "first_name": "Pilot",
        "last_name": "BothPaths",
        "description": "Both paths tester",
    },
]


class Command(BaseCommand):
    help = "Set up pilot test accounts with sample data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Remove existing pilot accounts before creating new ones",
        )

    def handle(self, *args, **options):
        if options["clean"]:
            self.clean_pilot_accounts()

        self.create_pilot_accounts()
        self.create_sample_data()

        self.stdout.write(self.style.SUCCESS("\nPilot setup complete!"))
        self.stdout.write("\nAccounts created:")
        for account in PILOT_ACCOUNTS:
            self.stdout.write(f"  - {account['email']} ({account['description']})")
        self.stdout.write(f"\nPassword for all accounts: {PILOT_PASSWORD}")

    def clean_pilot_accounts(self):
        """Remove existing pilot accounts."""
        pilot_emails = [a["email"] for a in PILOT_ACCOUNTS]
        deleted, _ = User.objects.filter(email__in=pilot_emails).delete()
        self.stdout.write(f"Deleted {deleted} existing pilot accounts")

    def create_pilot_accounts(self):
        """Create pilot test accounts."""
        for account in PILOT_ACCOUNTS:
            user, created = User.objects.get_or_create(
                email=account["email"],
                defaults={
                    "first_name": account["first_name"],
                    "last_name": account["last_name"],
                },
            )

            if created:
                user.set_password(PILOT_PASSWORD)
                user.save()

                # Verify email
                EmailAddress.objects.create(
                    user=user, email=user.email, verified=True, primary=True
                )

                # Enable all notifications
                if hasattr(user, "notification_preferences"):
                    prefs = user.notification_preferences
                    prefs.email_enabled = True
                    prefs.deadline_reminders = True
                    prefs.exam_reminders = True
                    prefs.document_analysis = True
                    prefs.save()

                self.stdout.write(f'Created account: {account["email"]}')
            else:
                self.stdout.write(f'Account exists: {account["email"]}')

    def create_sample_data(self):
        """Create sample data for pilot accounts."""
        from core.models import JourneyMilestone, Deadline
        from examprep.models import SavedRatingCalculation, ExamChecklist, ExamGuidance

        # Get pilot users
        pilot_b = User.objects.filter(email="pilot_b@test.com").first()
        pilot_both = User.objects.filter(email="pilot_both@test.com").first()

        if not pilot_b and not pilot_both:
            return

        # Sample saved calculation for Path B users
        for user in [pilot_b, pilot_both]:
            if not user:
                continue

            # Create sample saved calculation
            calc, created = SavedRatingCalculation.objects.get_or_create(
                user=user,
                name="Example Rating Calculation",
                defaults={
                    "ratings": json.dumps(
                        [
                            {
                                "percentage": 30,
                                "description": "Knee injury (left)",
                                "is_bilateral": True,
                            },
                            {
                                "percentage": 20,
                                "description": "Knee injury (right)",
                                "is_bilateral": True,
                            },
                            {
                                "percentage": 10,
                                "description": "Tinnitus",
                                "is_bilateral": False,
                            },
                        ]
                    ),
                    "combined_raw": 49.6,
                    "combined_rounded": 50,
                    "bilateral_factor": 5.0,
                    "has_spouse": True,
                    "children_under_18": 0,
                    "dependent_parents": 0,
                    "estimated_monthly": 1041.82,
                    "notes": "Sample calculation for pilot testing",
                },
            )
            if created:
                self.stdout.write(f"Created sample calculation for {user.email}")

            # Create sample milestone
            milestone, created = JourneyMilestone.objects.get_or_create(
                user=user,
                title="Started VA Claim Process",
                defaults={
                    "milestone_type": "claim_filed",
                    "date": timezone.now().date() - timedelta(days=30),
                    "description": "Began the disability claim process",
                },
            )
            if created:
                self.stdout.write(f"Created sample milestone for {user.email}")

            # Create sample deadline
            deadline, created = Deadline.objects.get_or_create(
                user=user,
                title="Submit Additional Evidence",
                defaults={
                    "deadline_date": timezone.now().date() + timedelta(days=14),
                    "priority": "high",
                    "description": "Submit buddy statements and medical records",
                },
            )
            if created:
                self.stdout.write(f"Created sample deadline for {user.email}")

            # Create sample exam checklist if guides exist
            guide = ExamGuidance.objects.filter(is_published=True).first()
            if guide:
                checklist, created = ExamChecklist.objects.get_or_create(
                    user=user,
                    condition="Sample Condition",
                    defaults={
                        "guidance": guide,
                        "exam_date": timezone.now().date() + timedelta(days=7),
                    },
                )
                if created:
                    self.stdout.write(f"Created sample exam checklist for {user.email}")
