"""
Management command to seed VSO test data for development and testing.

Creates comprehensive VSO data including:
- Organizations (VSO, Law Firm)
- Staff users (admins, caseworkers)
- Veteran users with profiles
- Cases with various statuses
- Case conditions with evidence gaps
- Case notes and action items
- Sample shared documents/analyses

Usage:
    python manage.py seed_vso_data
    python manage.py seed_vso_data --clear  # Clear existing VSO data first
    python manage.py seed_vso_data --minimal  # Create minimal data set
"""

from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User, Organization, OrganizationMembership


class Command(BaseCommand):
    help = "Seed VSO test data for development and manual testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing VSO test data before seeding",
        )
        parser.add_argument(
            "--minimal",
            action="store_true",
            help="Create minimal data set (1 org, 1 caseworker, 2 cases)",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.clear_vso_data()

        if options["minimal"]:
            self.seed_minimal()
        else:
            self.seed_full()

        self.stdout.write(self.style.SUCCESS("\nVSO test data seeded successfully!"))
        self.print_login_info()

    def clear_vso_data(self):
        """Clear existing VSO test data."""
        from vso.models import VeteranCase

        self.stdout.write("Clearing existing VSO test data...")

        # Delete VSO-specific data
        cases_deleted, _ = VeteranCase.objects.filter(
            organization__slug__startswith="test-"
        ).delete()

        orgs_deleted, _ = Organization.objects.filter(slug__startswith="test-").delete()

        users_deleted, _ = User.objects.filter(email__endswith="@testvso.org").delete()

        users_deleted2, _ = User.objects.filter(
            email__endswith="@testvetslaw.com"
        ).delete()

        self.stdout.write(f"  Deleted {cases_deleted} cases")
        self.stdout.write(f"  Deleted {orgs_deleted} organizations")
        self.stdout.write(f"  Deleted {users_deleted + users_deleted2} users")

    def seed_minimal(self):
        """Seed minimal VSO data for quick testing."""
        self.stdout.write(
            self.style.MIGRATE_HEADING("\n=== Seeding Minimal VSO Data ===")
        )

        # Create organization
        org = self.create_organization(name="Test VSO", slug="test-vso", org_type="vso")

        # Create caseworker
        caseworker = self.create_user(
            email="caseworker@testvso.org",
            password="testpass123",
            first_name="Sarah",
            last_name="Johnson",
        )
        self.create_membership(caseworker, org, "caseworker")
        self.stdout.write(f"  Created caseworker: {caseworker.email}")

        # Create veterans and cases
        veteran1 = self.create_user(
            email="veteran1@testvso.org",
            password="testpass123",
            first_name="James",
            last_name="Wilson",
        )
        self.setup_veteran_profile(veteran1, branch="army", rating=40)
        case1 = self.create_case(
            org,
            veteran1,
            caseworker,
            title="PTSD Increase Claim",
            status="gathering_evidence",
            priority="high",
        )
        self.create_conditions(
            case1,
            [
                ("PTSD", "9411", "gathering_evidence", 50, 70, True, True, False),
                ("Tinnitus", "6260", "identified", 10, 10, True, False, False),
            ],
        )
        self.stdout.write(f"  Created case: {case1.title}")

        veteran2 = self.create_user(
            email="veteran2@testvso.org",
            password="testpass123",
            first_name="Maria",
            last_name="Garcia",
        )
        self.setup_veteran_profile(veteran2, branch="navy", rating=30)
        case2 = self.create_case(
            org,
            veteran2,
            caseworker,
            title="Secondary Connection - Sleep Apnea",
            status="intake",
            priority="normal",
        )
        self.create_conditions(
            case2,
            [
                ("Sleep Apnea", "6847", "identified", None, 50, False, False, False),
            ],
        )
        self.stdout.write(f"  Created case: {case2.title}")

    def seed_full(self):
        """Seed full VSO test data."""
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Seeding Full VSO Data ==="))

        # === Organization 1: VSO ===
        vso = self.create_organization(
            name="Test Veterans Service Organization",
            slug="test-vso",
            org_type="vso",
            description="A test VSO for development",
        )
        self.stdout.write(f"\n  Organization: {vso.name}")

        # VSO Admin
        vso_admin = self.create_user(
            email="admin@testvso.org",
            password="testpass123",
            first_name="Jennifer",
            last_name="Adams",
        )
        self.create_membership(vso_admin, vso, "admin")
        self.stdout.write(f"    Admin: {vso_admin.email}")

        # Caseworkers
        caseworker1 = self.create_user(
            email="caseworker1@testvso.org",
            password="testpass123",
            first_name="Michael",
            last_name="Brown",
        )
        self.create_membership(caseworker1, vso, "caseworker")
        self.stdout.write(f"    Caseworker: {caseworker1.email}")

        caseworker2 = self.create_user(
            email="caseworker2@testvso.org",
            password="testpass123",
            first_name="Lisa",
            last_name="Davis",
        )
        self.create_membership(caseworker2, vso, "caseworker")
        self.stdout.write(f"    Caseworker: {caseworker2.email}")

        # === Create Veterans and Cases ===
        self.stdout.write("\n  Creating veterans and cases...")

        # Case 1: Active PTSD claim (high priority, gathering evidence)
        vet1 = self.create_user(
            email="veteran1@testvso.org",
            password="testpass123",
            first_name="James",
            last_name="Wilson",
        )
        self.setup_veteran_profile(vet1, branch="army", rating=50)
        case1 = self.create_case(
            vso,
            vet1,
            caseworker1,
            title="PTSD Rating Increase",
            description="Veteran seeking increase from 50% to 70% for PTSD.",
            status="gathering_evidence",
            priority="high",
            initial_rating=50,
            days_ago=45,
        )
        self.create_conditions(
            case1,
            [
                ("PTSD", "9411", "gathering_evidence", 50, 70, True, True, False),
                (
                    "Major Depressive Disorder",
                    "9434",
                    "identified",
                    None,
                    30,
                    True,
                    False,
                    False,
                ),
            ],
        )
        self.create_notes(
            case1,
            caseworker1,
            [
                (
                    "Initial consultation completed",
                    "Veteran provided service records and current treatment records.",
                    "consultation",
                    False,
                ),
                (
                    "Obtain buddy statement",
                    "Need statement from spouse regarding symptoms.",
                    "general",
                    True,
                    7,
                ),
                (
                    "Schedule C&P exam prep",
                    "Review DBQ criteria with veteran before exam.",
                    "general",
                    True,
                    14,
                ),
            ],
        )
        self.stdout.write(f"    Case: {case1.title} (High Priority)")

        # Case 2: Secondary connection claim (normal priority, intake)
        vet2 = self.create_user(
            email="veteran2@testvso.org",
            password="testpass123",
            first_name="Patricia",
            last_name="Garcia",
        )
        self.setup_veteran_profile(vet2, branch="navy", rating=30)
        case2 = self.create_case(
            vso,
            vet2,
            caseworker1,
            title="Secondary Service Connection - Sleep Apnea",
            description="Claiming sleep apnea as secondary to service-connected PTSD.",
            status="intake",
            priority="normal",
            initial_rating=30,
            days_ago=5,
        )
        self.create_conditions(
            case2,
            [
                ("Sleep Apnea", "6847", "identified", None, 50, False, False, False),
                ("PTSD", "9411", "granted", 30, 30, True, True, True),
            ],
        )
        self.create_notes(
            case2,
            caseworker1,
            [
                (
                    "Case opened",
                    "Veteran referred by DAV. Initial documents received.",
                    "milestone",
                    False,
                ),
            ],
        )
        self.stdout.write(f"    Case: {case2.title} (Intake)")

        # Case 3: Appeal in progress (urgent)
        vet3 = self.create_user(
            email="veteran3@testvso.org",
            password="testpass123",
            first_name="William",
            last_name="Anderson",
        )
        self.setup_veteran_profile(vet3, branch="marines", rating=40)
        case3 = self.create_case(
            vso,
            vet3,
            caseworker2,
            title="HLR Appeal - Back Condition",
            description="Higher Level Review for denied back condition claim.",
            status="appeal_in_progress",
            priority="urgent",
            initial_rating=40,
            days_ago=90,
        )
        self.create_conditions(
            case3,
            [
                ("Lumbar Strain", "5237", "appealing", None, 20, True, True, False),
                ("Radiculopathy", "8520", "denied", None, 20, True, False, False),
            ],
        )
        self.create_notes(
            case3,
            caseworker2,
            [
                (
                    "HLR submitted",
                    "Higher Level Review request filed on 12/15.",
                    "milestone",
                    False,
                ),
                (
                    "Informal conference scheduled",
                    "Conference with DRO set for next month.",
                    "deadline",
                    True,
                    21,
                ),
            ],
        )
        self.stdout.write(f"    Case: {case3.title} (Urgent - Appeal)")

        # Case 4: Claim filed, pending decision
        vet4 = self.create_user(
            email="veteran4@testvso.org",
            password="testpass123",
            first_name="Elizabeth",
            last_name="Taylor",
        )
        self.setup_veteran_profile(vet4, branch="air_force", rating=60)
        case4 = self.create_case(
            vso,
            vet4,
            caseworker2,
            title="Multiple Conditions Claim",
            description="New claims for hearing loss, tinnitus, and knee condition.",
            status="pending_decision",
            priority="normal",
            initial_rating=60,
            days_ago=120,
        )
        self.create_conditions(
            case4,
            [
                (
                    "Hearing Loss",
                    "6100",
                    "pending_decision",
                    None,
                    10,
                    True,
                    True,
                    True,
                ),
                ("Tinnitus", "6260", "pending_decision", None, 10, True, True, True),
                (
                    "Knee Condition",
                    "5260",
                    "pending_decision",
                    None,
                    10,
                    True,
                    True,
                    True,
                ),
            ],
        )
        self.stdout.write(f"    Case: {case4.title} (Pending Decision)")

        # Case 5: Closed - Won
        vet5 = self.create_user(
            email="veteran5@testvso.org",
            password="testpass123",
            first_name="Robert",
            last_name="Martinez",
        )
        self.setup_veteran_profile(vet5, branch="coast_guard", rating=70)
        case5 = self.create_case(
            vso,
            vet5,
            caseworker1,
            title="TDIU Claim",
            description="Total Disability Individual Unemployability claim.",
            status="closed_won",
            priority="normal",
            initial_rating=60,
            final_rating=100,
            days_ago=200,
        )
        self.create_conditions(
            case5,
            [
                ("TDIU", None, "granted", None, 100, True, True, True),
            ],
        )
        self.create_notes(
            case5,
            caseworker1,
            [
                (
                    "TDIU Granted",
                    "Veteran awarded TDIU effective 6 months ago. Great outcome!",
                    "milestone",
                    False,
                ),
            ],
        )
        self.stdout.write(f"    Case: {case5.title} (Closed - Won)")

        # Case 6: Stale case (no activity in 45 days)
        vet6 = self.create_user(
            email="veteran6@testvso.org",
            password="testpass123",
            first_name="Susan",
            last_name="Clark",
        )
        self.setup_veteran_profile(vet6, branch="army", rating=20)
        case6 = self.create_case(
            vso,
            vet6,
            caseworker2,
            title="Migraine Claim",
            description="New claim for service-connected migraines.",
            status="gathering_evidence",
            priority="normal",
            initial_rating=20,
            days_ago=60,
            last_activity_days_ago=45,
        )
        self.create_conditions(
            case6,
            [
                (
                    "Migraines",
                    "8100",
                    "gathering_evidence",
                    None,
                    30,
                    True,
                    False,
                    False,
                ),
            ],
        )
        self.stdout.write(f"    Case: {case6.title} (Stale - No Activity)")

        # === Organization 2: Law Firm ===
        law_firm = self.create_organization(
            name="Test Veterans Law Group",
            slug="test-law-firm",
            org_type="law_firm",
            description="Legal representation for VA appeals",
        )
        self.stdout.write(f"\n  Organization: {law_firm.name}")

        attorney = self.create_user(
            email="attorney@testvetslaw.com",
            password="testpass123",
            first_name="Richard",
            last_name="Sterling",
        )
        self.create_membership(attorney, law_firm, "admin")
        self.stdout.write(f"    Attorney: {attorney.email}")

        # Law firm case
        vet7 = self.create_user(
            email="client1@testvetslaw.com",
            password="testpass123",
            first_name="David",
            last_name="Thompson",
        )
        self.setup_veteran_profile(vet7, branch="army", rating=30)
        case7 = self.create_case(
            law_firm,
            vet7,
            attorney,
            title="BVA Appeal - TBI",
            description="Board of Veterans Appeals case for TBI denial.",
            status="appeal_in_progress",
            priority="high",
            initial_rating=30,
            days_ago=180,
        )
        self.create_conditions(
            case7,
            [
                (
                    "Traumatic Brain Injury",
                    "8045",
                    "appealing",
                    None,
                    70,
                    True,
                    True,
                    False,
                ),
            ],
        )
        self.stdout.write(f"    Case: {case7.title} (BVA Appeal)")

    def create_organization(self, name, slug, org_type="vso", description=""):
        """Create an organization."""
        org, _ = Organization.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "org_type": org_type,
                "description": description,
                "plan": "pro",
                "seats": 10,
                "is_active": True,
            },
        )
        return org

    def create_user(self, email, password, first_name, last_name):
        """Create a user with AI consent enabled."""
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "is_verified": True,
            },
        )
        if created:
            user.set_password(password)
            user.save()

        # Enable AI consent
        if hasattr(user, "profile"):
            user.profile.ai_processing_consent = True
            user.profile.save()

        return user

    def setup_veteran_profile(self, user, branch="army", rating=None):
        """Set up veteran profile with branch and rating."""
        if hasattr(user, "profile"):
            user.profile.branch_of_service = branch
            user.profile.disability_rating = rating
            user.profile.date_of_birth = date(1985, 6, 15)
            user.profile.save()

    def create_membership(self, user, org, role):
        """Create organization membership."""
        OrganizationMembership.objects.get_or_create(
            user=user,
            organization=org,
            defaults={
                "role": role,
                "is_active": True,
                "accepted_at": timezone.now(),
            },
        )

    def create_case(
        self,
        org,
        veteran,
        assigned_to,
        title,
        description="",
        status="intake",
        priority="normal",
        initial_rating=None,
        final_rating=None,
        days_ago=0,
        last_activity_days_ago=None,
    ):
        """Create a veteran case."""
        from vso.models import VeteranCase

        intake_date = timezone.now().date() - timedelta(days=days_ago)
        created_at = timezone.now() - timedelta(days=days_ago)

        if last_activity_days_ago is not None:
            last_activity = timezone.now() - timedelta(days=last_activity_days_ago)
        else:
            last_activity = timezone.now()

        case, _ = VeteranCase.objects.get_or_create(
            organization=org,
            veteran=veteran,
            title=title,
            defaults={
                "description": description,
                "status": status,
                "priority": priority,
                "assigned_to": assigned_to,
                "intake_date": intake_date,
                "initial_combined_rating": initial_rating,
                "final_combined_rating": final_rating,
                "last_activity_at": last_activity,
                "veteran_consent_date": timezone.now(),
            },
        )

        # Update created_at manually
        VeteranCase.objects.filter(pk=case.pk).update(created_at=created_at)

        return case

    def create_conditions(self, case, conditions):
        """
        Create case conditions.

        conditions: list of tuples (name, code, status, current_rating, target_rating, has_dx, has_event, has_nexus)
        """
        from vso.models import CaseCondition

        for (
            name,
            code,
            status,
            current,
            target,
            has_dx,
            has_event,
            has_nexus,
        ) in conditions:
            CaseCondition.objects.get_or_create(
                case=case,
                condition_name=name,
                defaults={
                    "diagnostic_code": code or "",
                    "workflow_status": status,
                    "current_rating": current,
                    "target_rating": target,
                    "has_diagnosis": has_dx,
                    "has_in_service_event": has_event,
                    "has_nexus": has_nexus,
                    "source": "manual",
                },
            )

    def create_notes(self, case, author, notes):
        """
        Create case notes.

        notes: list of tuples (subject, content, note_type, is_action_item, due_days=None)
        """
        from vso.models import CaseNote

        for note_data in notes:
            if len(note_data) == 4:
                subject, content, note_type, is_action = note_data
                due_days = None
            else:
                subject, content, note_type, is_action, due_days = note_data

            due_date = None
            if is_action and due_days:
                due_date = timezone.now().date() + timedelta(days=due_days)

            CaseNote.objects.get_or_create(
                case=case,
                subject=subject,
                defaults={
                    "author": author,
                    "content": content,
                    "note_type": note_type,
                    "is_action_item": is_action,
                    "action_due_date": due_date,
                    "visible_to_veteran": True,
                },
            )

    def print_login_info(self):
        """Print login credentials for test users."""
        self.stdout.write(
            self.style.MIGRATE_HEADING("\n=== Test Login Credentials ===")
        )
        self.stdout.write("Password for all users: testpass123\n")

        self.stdout.write("VSO Staff:")
        self.stdout.write("  admin@testvso.org         - VSO Admin")
        self.stdout.write("  caseworker1@testvso.org   - Caseworker (6 cases)")
        self.stdout.write("  caseworker2@testvso.org   - Caseworker")

        self.stdout.write("\nLaw Firm:")
        self.stdout.write("  attorney@testvetslaw.com  - Attorney/Admin")

        self.stdout.write("\nVeterans:")
        self.stdout.write("  veteran1@testvso.org      - James Wilson (Army, 50%)")
        self.stdout.write("  veteran2@testvso.org      - Patricia Garcia (Navy, 30%)")
        self.stdout.write(
            "  veteran3@testvso.org      - William Anderson (Marines, 40%)"
        )

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== VSO URLs ==="))
        self.stdout.write("  /vso/                     - Dashboard")
        self.stdout.write("  /vso/cases/               - Case List")
        self.stdout.write("  /vso/cases/new/           - Create Case")
        self.stdout.write("  /vso/invitations/         - Invitations")
        self.stdout.write("  /accounts/2fa/            - MFA Setup")
