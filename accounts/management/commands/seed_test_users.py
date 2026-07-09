"""
Management command to seed test users for development and testing.

Creates users for both Path A (B2C) and Path B (B2B/Organizations).

Usage:
    python manage.py seed_test_users
    python manage.py seed_test_users --path=a
    python manage.py seed_test_users --path=b
    python manage.py seed_test_users --clear  # Remove all test users first
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, date

from accounts.models import (
    User,
    UserProfile,
    Subscription,
    NotificationPreferences,
    UsageTracking,
    Organization,
    OrganizationMembership,
    OrganizationInvitation,
)


class Command(BaseCommand):
    help = "Seed test users for Path A (B2C) and Path B (B2B)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            choices=["a", "b", "both"],
            default="both",
            help="Which path to seed: a (B2C), b (B2B), or both (default)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing test users before seeding",
        )

    def handle(self, *args, **options):
        path = options["path"]
        clear = options["clear"]

        if clear:
            self.clear_test_users()

        if path in ("a", "both"):
            self.seed_path_a()

        if path in ("b", "both"):
            self.seed_path_b()

        self.stdout.write(self.style.SUCCESS("\nTest users seeded successfully!"))
        self.print_login_info(path)

    def clear_test_users(self):
        """Remove all test users (emails containing 'test' or '@example.com')."""
        self.stdout.write("Clearing existing test users...")

        # Delete organizations first (cascade will handle memberships)
        orgs_deleted, _ = Organization.objects.filter(slug__startswith="test-").delete()

        # Delete test users
        users_deleted, _ = User.objects.filter(email__icontains="test").delete()

        users_deleted2, _ = User.objects.filter(email__endswith="@example.com").delete()

        self.stdout.write(f"  Deleted {orgs_deleted} organizations")
        self.stdout.write(f"  Deleted {users_deleted + users_deleted2} users")

    def seed_path_a(self):
        """Seed Path A (B2C) - Individual veteran users."""
        self.stdout.write(
            self.style.MIGRATE_HEADING("\n=== Path A: Direct-to-Veteran (B2C) ===")
        )

        # 1. Free tier veteran (just signed up)
        free_user = self.create_user(
            email="veteran.free@example.com",
            password="TestPass123!",
            first_name="Marcus",
            last_name="Johnson",
            is_verified=True,
        )
        self.create_profile(free_user, branch="army", rating=30)
        self.create_usage(free_user, docs_this_month=1, total_docs=1)
        self.stdout.write(f"  Created: {free_user.email} (Free tier, 30% rating)")

        # 2. Free tier veteran (at limit)
        limited_user = self.create_user(
            email="veteran.limited@example.com",
            password="TestPass123!",
            first_name="Sarah",
            last_name="Williams",
            is_verified=True,
        )
        self.create_profile(limited_user, branch="air_force", rating=50)
        self.create_usage(limited_user, docs_this_month=3, total_docs=5, storage_mb=95)
        self.stdout.write(
            f"  Created: {limited_user.email} (Free tier, at upload limit)"
        )

        # 3. Premium veteran
        premium_user = self.create_user(
            email="veteran.premium@example.com",
            password="TestPass123!",
            first_name="David",
            last_name="Martinez",
            is_verified=True,
        )
        self.create_profile(premium_user, branch="marines", rating=70)
        self.create_subscription(premium_user, plan="premium")
        self.create_usage(
            premium_user, docs_this_month=15, total_docs=45, storage_mb=250
        )
        self.stdout.write(f"  Created: {premium_user.email} (Premium, 70% rating)")

        # 4. New veteran (unverified, no profile completed)
        new_user = self.create_user(
            email="veteran.new@example.com",
            password="TestPass123!",
            first_name="",
            last_name="",
            is_verified=False,
        )
        self.stdout.write(f"  Created: {new_user.email} (Unverified, no profile)")

        # 5. Veteran going through appeals
        appeals_user = self.create_user(
            email="veteran.appeals@example.com",
            password="TestPass123!",
            first_name="Robert",
            last_name="Thompson",
            is_verified=True,
        )
        self.create_profile(appeals_user, branch="navy", rating=40)
        self.create_subscription(appeals_user, plan="premium")
        self.stdout.write(
            f"  Created: {appeals_user.email} (Premium, in appeals process)"
        )

    def seed_path_b(self):
        """Seed Path B (B2B) - Organizations and their members."""
        self.stdout.write(
            self.style.MIGRATE_HEADING("\n=== Path B: VSO Platform (B2B) ===")
        )

        # === Organization 1: Local VSO ===
        vso = Organization.objects.create(
            name="Test Veterans Support Center",
            slug="test-vso",
            org_type="vso",
            description="A local VSO chapter helping veterans with claims",
            plan="pro",
            seats=10,
            contact_email="admin@testvso.org",
            is_active=True,
        )
        self.stdout.write(f"\n  Created Organization: {vso.name}")

        # VSO Admin
        vso_admin = self.create_user(
            email="admin@testvso.org",
            password="TestPass123!",
            first_name="Jennifer",
            last_name="Adams",
            is_verified=True,
        )
        OrganizationMembership.objects.create(
            user=vso_admin,
            organization=vso,
            role="admin",
            is_active=True,
            accepted_at=timezone.now(),
        )
        vso.seats_used = 1
        vso.save()
        self.stdout.write(f"    Admin: {vso_admin.email}")

        # VSO Caseworkers
        for i, (first, last) in enumerate([("Michael", "Brown"), ("Lisa", "Davis")], 1):
            caseworker = self.create_user(
                email=f"caseworker{i}@testvso.org",
                password="TestPass123!",
                first_name=first,
                last_name=last,
                is_verified=True,
            )
            OrganizationMembership.objects.create(
                user=caseworker,
                organization=vso,
                role="caseworker",
                is_active=True,
                invited_by=vso_admin,
                accepted_at=timezone.now(),
            )
            vso.seats_used += 1
            self.stdout.write(f"    Caseworker: {caseworker.email}")
        vso.save()

        # Veterans assigned to VSO
        for i, (first, last, branch, rating) in enumerate(
            [
                ("James", "Wilson", "army", 40),
                ("Patricia", "Garcia", "navy", 60),
                ("William", "Anderson", "marines", 20),
            ],
            1,
        ):
            vet = self.create_user(
                email=f"veteran{i}@testvso.org",
                password="TestPass123!",
                first_name=first,
                last_name=last,
                is_verified=True,
            )
            self.create_profile(vet, branch=branch, rating=rating)
            OrganizationMembership.objects.create(
                user=vet,
                organization=vso,
                role="veteran",
                is_active=True,
                invited_by=vso_admin,
                accepted_at=timezone.now(),
            )
            vso.seats_used += 1
            self.stdout.write(f"    Veteran: {vet.email} ({rating}% rating)")
        vso.save()

        # === Organization 2: Law Firm ===
        law_firm = Organization.objects.create(
            name="Test Veterans Law Group",
            slug="test-law-firm",
            org_type="law_firm",
            description="Legal representation for VA claims appeals",
            plan="enterprise",
            seats=25,
            contact_email="contact@testvetslaw.com",
            is_active=True,
        )
        self.stdout.write(f"\n  Created Organization: {law_firm.name}")

        # Law firm admin
        law_admin = self.create_user(
            email="partner@testvetslaw.com",
            password="TestPass123!",
            first_name="Richard",
            last_name="Sterling",
            is_verified=True,
        )
        OrganizationMembership.objects.create(
            user=law_admin,
            organization=law_firm,
            role="admin",
            is_active=True,
            accepted_at=timezone.now(),
        )
        law_firm.seats_used = 1
        law_firm.save()
        self.stdout.write(f"    Admin: {law_admin.email}")

        # === Pending Invitation ===
        OrganizationInvitation.objects.create(
            organization=vso,
            email="pending.invite@example.com",
            role="veteran",
            invited_by=vso_admin,
            token="test-invitation-token-12345",
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.stdout.write("\n  Created pending invitation: pending.invite@example.com")

    def create_user(
        self, email, password, first_name="", last_name="", is_verified=True
    ):
        """Create a user if they don't exist."""
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "is_verified": is_verified,
            },
        )
        if created:
            user.set_password(password)
            user.save()
        return user

    def create_profile(self, user, branch="army", rating=None):
        """Create user profile."""
        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "branch_of_service": branch,
                "disability_rating": rating,
                "date_of_birth": date(1985, 6, 15),
            },
        )
        # Create notification preferences
        NotificationPreferences.objects.get_or_create(
            user=user, defaults={"email_enabled": True}
        )

    def create_subscription(self, user, plan="free"):
        """Create subscription."""
        Subscription.objects.get_or_create(
            user=user,
            defaults={
                "plan_type": plan,
                "status": "active" if plan == "premium" else "active",
                "current_period_end": timezone.now() + timedelta(days=30),
            },
        )

    def create_usage(self, user, docs_this_month=0, total_docs=0, storage_mb=0):
        """Create usage tracking."""
        UsageTracking.objects.get_or_create(
            user=user,
            defaults={
                "documents_uploaded_this_month": docs_this_month,
                "total_documents_uploaded": total_docs,
                "total_storage_bytes": storage_mb * 1024 * 1024,
            },
        )

    def print_login_info(self, path):
        """Print login credentials for test users."""
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Login Credentials ==="))
        self.stdout.write("All test users use password: TestPass123!\n")

        if path in ("a", "both"):
            self.stdout.write(self.style.WARNING("Path A (B2C) Users:"))
            self.stdout.write("  veteran.free@example.com      - Free tier, basic")
            self.stdout.write(
                "  veteran.limited@example.com   - Free tier, at upload limit"
            )
            self.stdout.write("  veteran.premium@example.com   - Premium subscriber")
            self.stdout.write(
                "  veteran.new@example.com       - Unverified, no profile"
            )
            self.stdout.write(
                "  veteran.appeals@example.com   - Premium, appeals focused"
            )

        if path in ("b", "both"):
            self.stdout.write(self.style.WARNING("\nPath B (B2B) Users:"))
            self.stdout.write("  VSO (test-vso):")
            self.stdout.write("    admin@testvso.org           - Organization Admin")
            self.stdout.write("    caseworker1@testvso.org     - Caseworker")
            self.stdout.write("    caseworker2@testvso.org     - Caseworker")
            self.stdout.write("    veteran1@testvso.org        - Veteran (40%)")
            self.stdout.write("    veteran2@testvso.org        - Veteran (60%)")
            self.stdout.write("    veteran3@testvso.org        - Veteran (20%)")
            self.stdout.write("  Law Firm (test-law-firm):")
            self.stdout.write("    partner@testvetslaw.com     - Organization Admin")
