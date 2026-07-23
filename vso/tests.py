"""
Tests for VSO app - Organization scoping and access control.

Covers:
- Multi-org user access scoping
- Organization selection for multi-org users
- VSO dashboard and case management permissions
"""

from unittest import mock

import pytest
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from accounts.models import Organization, OrganizationMembership
from vso.views import (
    get_user_staff_memberships,
    get_user_organization,
    requires_org_selection,
)

User = get_user_model()


# =============================================================================
# MULTI-ORG SCOPING TESTS
# =============================================================================


class TestGetUserStaffMemberships(TestCase):
    """Tests for get_user_staff_memberships function."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="vsostaff@example.com", password="TestPass123!"
        )
        self.org1 = Organization.objects.create(
            name="VSO Org 1",
            slug="vso-org-1",
            org_type="vso",
        )
        self.org2 = Organization.objects.create(
            name="VSO Org 2",
            slug="vso-org-2",
            org_type="vso",
        )

    def test_returns_empty_for_unauthenticated(self):
        """Unauthenticated user gets empty queryset."""
        from django.contrib.auth.models import AnonymousUser

        anon = AnonymousUser()
        result = get_user_staff_memberships(anon)
        self.assertEqual(result.count(), 0)

    def test_returns_empty_for_user_with_no_memberships(self):
        """User with no memberships gets empty queryset."""
        result = get_user_staff_memberships(self.user)
        self.assertEqual(result.count(), 0)

    def test_returns_admin_membership(self):
        """Returns membership where user is admin."""
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org1,
            role="admin",
            is_active=True,
        )
        result = get_user_staff_memberships(self.user)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().organization, self.org1)

    def test_returns_caseworker_membership(self):
        """Returns membership where user is caseworker."""
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org1,
            role="caseworker",
            is_active=True,
        )
        result = get_user_staff_memberships(self.user)
        self.assertEqual(result.count(), 1)

    def test_excludes_member_role(self):
        """Does not return membership where user is just a member."""
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org1,
            role="member",
            is_active=True,
        )
        result = get_user_staff_memberships(self.user)
        self.assertEqual(result.count(), 0)

    def test_excludes_inactive_memberships(self):
        """Does not return inactive memberships."""
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org1,
            role="admin",
            is_active=False,  # Inactive
        )
        result = get_user_staff_memberships(self.user)
        self.assertEqual(result.count(), 0)

    def test_returns_multiple_memberships(self):
        """Returns all active staff memberships."""
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org1,
            role="admin",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org2,
            role="caseworker",
            is_active=True,
        )
        result = get_user_staff_memberships(self.user)
        self.assertEqual(result.count(), 2)


class TestGetUserOrganization(TestCase):
    """Tests for get_user_organization function."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="vsouser@example.com", password="TestPass123!"
        )
        self.org1 = Organization.objects.create(
            name="Primary VSO",
            slug="primary-vso",
            org_type="vso",
        )
        self.org2 = Organization.objects.create(
            name="Secondary VSO",
            slug="secondary-vso",
            org_type="vso",
        )

    def test_returns_none_for_user_with_no_memberships(self):
        """User with no memberships gets None."""
        result = get_user_organization(self.user)
        self.assertIsNone(result)

    def test_returns_org_for_single_membership(self):
        """User with single membership gets that org automatically."""
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org1,
            role="admin",
            is_active=True,
        )
        result = get_user_organization(self.user)
        self.assertEqual(result, self.org1)

    def test_multi_org_user_without_slug_returns_none(self):
        """Multi-org user without explicit selection gets None."""
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org1,
            role="admin",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org2,
            role="caseworker",
            is_active=True,
        )
        # No org_slug provided - should return None
        result = get_user_organization(self.user)
        self.assertIsNone(result)

    def test_multi_org_user_with_valid_slug_returns_org(self):
        """Multi-org user with valid slug gets that org."""
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org1,
            role="admin",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org2,
            role="caseworker",
            is_active=True,
        )
        result = get_user_organization(self.user, org_slug="secondary-vso")
        self.assertEqual(result, self.org2)

    def test_multi_org_user_with_invalid_slug_returns_none(self):
        """Multi-org user with invalid slug gets None."""
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org1,
            role="admin",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org2,
            role="caseworker",
            is_active=True,
        )
        result = get_user_organization(self.user, org_slug="non-existent-org")
        self.assertIsNone(result)

    def test_cannot_access_org_without_membership(self):
        """User cannot select org they don't belong to."""
        # User has membership in org1 only
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org1,
            role="admin",
            is_active=True,
        )
        # Try to access org2 via slug
        result = get_user_organization(self.user, org_slug="secondary-vso")
        self.assertIsNone(result)


class TestRequiresOrgSelection(TestCase):
    """Tests for requires_org_selection function."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="multiorg@example.com", password="TestPass123!"
        )
        self.org1 = Organization.objects.create(
            name="Org One",
            slug="org-one",
            org_type="vso",
        )
        self.org2 = Organization.objects.create(
            name="Org Two",
            slug="org-two",
            org_type="vso",
        )

    def test_false_for_no_memberships(self):
        """User with no memberships doesn't need selection."""
        result = requires_org_selection(self.user)
        self.assertFalse(result)

    def test_false_for_single_membership(self):
        """User with single membership doesn't need selection."""
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org1,
            role="admin",
            is_active=True,
        )
        result = requires_org_selection(self.user)
        self.assertFalse(result)

    def test_true_for_multiple_memberships(self):
        """User with multiple memberships needs selection."""
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org1,
            role="admin",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org2,
            role="caseworker",
            is_active=True,
        )
        result = requires_org_selection(self.user)
        self.assertTrue(result)


# =============================================================================
# VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestSelectOrganizationView:
    """Tests for the organization selection view."""

    def test_redirects_unauthenticated_user(self, client):
        """Unauthenticated user is redirected to login."""
        response = client.get(reverse("vso:select_organization"))
        assert response.status_code == 302
        assert "login" in response.url.lower() or "accounts" in response.url.lower()

    def test_shows_org_selection_for_multi_org_user(self, client, db):
        """Multi-org user sees organization selection page."""
        user = User.objects.create_user(
            email="multiselect@example.com", password="TestPass123!"
        )
        org1 = Organization.objects.create(
            name="Select Org 1",
            slug="select-org-1",
            org_type="vso",
        )
        org2 = Organization.objects.create(
            name="Select Org 2",
            slug="select-org-2",
            org_type="vso",
        )
        OrganizationMembership.objects.create(
            user=user,
            organization=org1,
            role="admin",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            user=user,
            organization=org2,
            role="caseworker",
            is_active=True,
        )

        client.login(email="multiselect@example.com", password="TestPass123!")
        response = client.get(reverse("vso:select_organization"))

        assert response.status_code == 200
        assert b"Select Org 1" in response.content
        assert b"Select Org 2" in response.content

    def test_post_sets_session_and_redirects(self, client, db):
        """POST with organization sets session and redirects."""
        user = User.objects.create_user(
            email="postselect@example.com", password="TestPass123!"
        )
        org = Organization.objects.create(
            name="Post Org",
            slug="post-org",
            org_type="vso",
        )
        OrganizationMembership.objects.create(
            user=user,
            organization=org,
            role="admin",
            is_active=True,
        )

        client.login(email="postselect@example.com", password="TestPass123!")
        response = client.post(
            reverse("vso:select_organization"), {"organization": "post-org"}
        )

        assert response.status_code == 302
        # Session should have the selected org
        assert client.session.get("selected_org_slug") == "post-org"


@pytest.mark.django_db
class TestVSODashboardOrgScoping:
    """Tests for VSO dashboard organization scoping."""

    def test_dashboard_redirects_multi_org_user_without_selection(self, client, db):
        """Multi-org user without selection is redirected to select org."""
        user = User.objects.create_user(
            email="dashredirect@example.com", password="TestPass123!"
        )
        org1 = Organization.objects.create(
            name="Dash Org 1",
            slug="dash-org-1",
            org_type="vso",
        )
        org2 = Organization.objects.create(
            name="Dash Org 2",
            slug="dash-org-2",
            org_type="vso",
        )
        OrganizationMembership.objects.create(
            user=user,
            organization=org1,
            role="admin",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            user=user,
            organization=org2,
            role="caseworker",
            is_active=True,
        )

        client.login(email="dashredirect@example.com", password="TestPass123!")
        response = client.get(reverse("vso:dashboard"))

        # Should redirect to org selection
        assert response.status_code == 302
        assert "select" in response.url.lower()

    def test_dashboard_accessible_for_single_org_user(self, client, db):
        """Single-org user can access dashboard directly."""
        user = User.objects.create_user(
            email="singledash@example.com", password="TestPass123!"
        )
        org = Organization.objects.create(
            name="Single Dash Org",
            slug="single-dash-org",
            org_type="vso",
        )
        OrganizationMembership.objects.create(
            user=user,
            organization=org,
            role="admin",
            is_active=True,
        )

        client.login(email="singledash@example.com", password="TestPass123!")
        response = client.get(reverse("vso:dashboard"))

        # Should be accessible (200 or 302 to a valid page, not org selection)
        if response.status_code == 302:
            assert "select" not in response.url.lower()
        else:
            assert response.status_code == 200


# =============================================================================
# CASE CONDITION MODEL TESTS
# =============================================================================


class TestCaseConditionModel(TestCase):
    """Tests for the CaseCondition model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="veteran@example.com", password="TestPass123!"
        )
        self.vso_user = User.objects.create_user(
            email="vso@example.com", password="TestPass123!"
        )
        self.org = Organization.objects.create(
            name="Test VSO",
            slug="test-vso",
            org_type="vso",
        )
        OrganizationMembership.objects.create(
            user=self.vso_user,
            organization=self.org,
            role="caseworker",
            is_active=True,
        )
        from vso.models import VeteranCase, CaseCondition

        self.case = VeteranCase.objects.create(
            organization=self.org,
            veteran=self.user,
            assigned_to=self.vso_user,
            title="Test Case",
            status="gathering_evidence",
        )
        self.CaseCondition = CaseCondition

    def test_gap_count_all_missing(self):
        """Gap count should be 3 when all evidence is missing."""
        condition = self.CaseCondition.objects.create(
            case=self.case,
            condition_name="PTSD",
            has_diagnosis=False,
            has_in_service_event=False,
            has_nexus=False,
        )
        self.assertEqual(condition.gap_count, 3)

    def test_gap_count_partial(self):
        """Gap count should reflect partial evidence."""
        condition = self.CaseCondition.objects.create(
            case=self.case,
            condition_name="Tinnitus",
            has_diagnosis=True,
            has_in_service_event=True,
            has_nexus=False,
        )
        self.assertEqual(condition.gap_count, 1)

    def test_gap_count_complete(self):
        """Gap count should be 0 when all evidence is present."""
        condition = self.CaseCondition.objects.create(
            case=self.case,
            condition_name="Hearing Loss",
            has_diagnosis=True,
            has_in_service_event=True,
            has_nexus=True,
        )
        self.assertEqual(condition.gap_count, 0)

    def test_is_evidence_complete_true(self):
        """is_evidence_complete should be True when all evidence present."""
        condition = self.CaseCondition.objects.create(
            case=self.case,
            condition_name="Back Pain",
            has_diagnosis=True,
            has_in_service_event=True,
            has_nexus=True,
        )
        self.assertTrue(condition.is_evidence_complete)

    def test_is_evidence_complete_false(self):
        """is_evidence_complete should be False when evidence missing."""
        condition = self.CaseCondition.objects.create(
            case=self.case,
            condition_name="Knee Pain",
            has_diagnosis=True,
            has_in_service_event=False,
            has_nexus=True,
        )
        self.assertFalse(condition.is_evidence_complete)

    def test_unique_together_constraint(self):
        """Cannot create duplicate condition names for same case."""
        from django.db import IntegrityError

        self.CaseCondition.objects.create(
            case=self.case,
            condition_name="PTSD",
        )
        with self.assertRaises(IntegrityError):
            self.CaseCondition.objects.create(
                case=self.case,
                condition_name="PTSD",
            )


# =============================================================================
# GAP CHECKER SERVICE TESTS
# =============================================================================


class TestGapCheckerService(TestCase):
    """Tests for the GapCheckerService."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="veteran2@example.com", password="TestPass123!"
        )
        self.org = Organization.objects.create(
            name="Gap Test VSO",
            slug="gap-test-vso",
            org_type="vso",
        )
        from vso.models import VeteranCase, CaseCondition
        from vso.services import GapCheckerService

        self.case = VeteranCase.objects.create(
            organization=self.org,
            veteran=self.user,
            title="Gap Test Case",
            status="gathering_evidence",
        )
        self.CaseCondition = CaseCondition
        self.GapCheckerService = GapCheckerService

    def test_triage_label_needs_review_no_conditions(self):
        """Case with no conditions should return needs_review."""
        label = self.GapCheckerService.get_triage_label(self.case)
        self.assertEqual(label, "needs_review")

    def test_triage_label_ready_to_file(self):
        """Case with complete evidence should return ready_to_file."""
        self.CaseCondition.objects.create(
            case=self.case,
            condition_name="PTSD",
            workflow_status="gathering_evidence",
            has_diagnosis=True,
            has_in_service_event=True,
            has_nexus=True,
        )
        label = self.GapCheckerService.get_triage_label(self.case)
        self.assertEqual(label, "ready_to_file")

    def test_triage_label_needs_nexus(self):
        """Case missing only nexus should return needs_nexus."""
        self.CaseCondition.objects.create(
            case=self.case,
            condition_name="PTSD",
            workflow_status="gathering_evidence",
            has_diagnosis=True,
            has_in_service_event=True,
            has_nexus=False,
        )
        label = self.GapCheckerService.get_triage_label(self.case)
        self.assertEqual(label, "needs_nexus")

    def test_triage_label_needs_evidence(self):
        """Case missing diagnosis or in-service should return needs_evidence."""
        self.CaseCondition.objects.create(
            case=self.case,
            condition_name="PTSD",
            workflow_status="gathering_evidence",
            has_diagnosis=False,
            has_in_service_event=True,
            has_nexus=True,
        )
        label = self.GapCheckerService.get_triage_label(self.case)
        self.assertEqual(label, "needs_evidence")

    def test_excludes_granted_conditions_from_triage(self):
        """Granted conditions should not affect triage calculation."""
        self.CaseCondition.objects.create(
            case=self.case,
            condition_name="PTSD",
            workflow_status="granted",
            has_diagnosis=False,
            has_in_service_event=False,
            has_nexus=False,
        )
        # With only granted condition, should return needs_review
        label = self.GapCheckerService.get_triage_label(self.case)
        self.assertEqual(label, "needs_review")


# =============================================================================
# CASE LIST N+1 REGRESSION TEST (TODO.md P1: vso/views.py triage-per-case)
# =============================================================================


class TestCaseListQueryCount(TestCase):
    """
    case_list() runs GapCheckerService.get_triage_label() over every case in
    the org. That must not issue a fresh query per case (N+1) — query count
    should stay flat as the case count grows.
    """

    def setUp(self):
        from vso.models import VeteranCase, CaseCondition

        self.org = Organization.objects.create(
            name="Query Count VSO",
            slug="query-count-vso",
            org_type="vso",
        )
        self.staff = User.objects.create_user(
            email="qc_staff@example.com", password="TestPass123!"
        )
        OrganizationMembership.objects.create(
            user=self.staff,
            organization=self.org,
            role="admin",
            is_active=True,
        )
        self.VeteranCase = VeteranCase
        self.CaseCondition = CaseCondition
        self.client.login(username="qc_staff@example.com", password="TestPass123!")
        self._vet_counter = 0

    def _create_cases(self, count):
        for _ in range(count):
            self._vet_counter += 1
            veteran = User.objects.create_user(
                email=f"qc_vet{self._vet_counter}@example.com", password="TestPass123!"
            )
            case = self.VeteranCase.objects.create(
                organization=self.org,
                veteran=veteran,
                title=f"QC Case {self._vet_counter}",
                status="gathering_evidence",
            )
            self.CaseCondition.objects.create(
                case=case,
                condition_name="PTSD",
                workflow_status="gathering_evidence",
                has_diagnosis=True,
                has_in_service_event=True,
                has_nexus=False,
            )

    def test_query_count_does_not_scale_with_case_count(self):
        """Query count for 2 cases should match query count for 8 cases.

        Each request uses a fresh, freshly-logged-in client so that
        session-level caching (e.g. org-membership lookups cached after the
        first request) can't mask or fake a query-count difference — the
        only thing that should vary between the two requests is case count.
        """
        from django.test import Client
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        self._create_cases(2)
        small_client = Client()
        small_client.login(username="qc_staff@example.com", password="TestPass123!")
        with CaptureQueriesContext(connection) as small:
            small_client.get(reverse("vso:case_list"))

        self._create_cases(6)

        large_client = Client()
        large_client.login(username="qc_staff@example.com", password="TestPass123!")
        with CaptureQueriesContext(connection) as large:
            large_client.get(reverse("vso:case_list"))

        self.assertEqual(
            len(small.captured_queries),
            len(large.captured_queries),
            "case_list query count scaled with case count — N+1 regression",
        )


# =============================================================================
# ACCEPT INVITATION ATOMICITY TESTS (TODO.md P1: transaction.atomic)
# =============================================================================


class TestAcceptInvitationAtomicity(TestCase):
    """
    accept_invitation() does 3 writes (accept invitation, create case, create
    milestone note). They must succeed or fail together — a failure partway
    through must not leave an accepted invitation with no case.
    """

    def setUp(self):
        from accounts.models import OrganizationInvitation

        self.org = Organization.objects.create(
            name="Atomic Test VSO",
            slug="atomic-test-vso",
            org_type="vso",
        )
        self.caseworker = User.objects.create_user(
            email="atomic_caseworker@example.com", password="TestPass123!"
        )
        self.veteran = User.objects.create_user(
            email="atomic_veteran@example.com", password="TestPass123!"
        )
        self.invitation = OrganizationInvitation.objects.create(
            organization=self.org,
            email=self.veteran.email,
            role="veteran",
            invited_by=self.caseworker,
        )
        self.client.login(
            username="atomic_veteran@example.com", password="TestPass123!"
        )

    def _seed_pending_case_session(self):
        session = self.client.session
        session[f"pending_case_{self.invitation.token}"] = {
            "title": "Atomic Test Case",
            "description": "",
            "priority": "normal",
            "invited_by_id": self.caseworker.id,
        }
        session.save()

    def test_accept_creates_membership_case_and_note_together(self):
        """Happy path: invitation, case, and note are all created."""
        from accounts.models import OrganizationMembership
        from vso.models import VeteranCase, CaseNote

        self._seed_pending_case_session()
        response = self.client.post(
            reverse("vso:accept_invitation", args=[self.invitation.token])
        )
        self.assertEqual(response.status_code, 302)

        self.invitation.refresh_from_db()
        self.assertIsNotNone(self.invitation.accepted_at)
        self.assertTrue(
            OrganizationMembership.objects.filter(
                user=self.veteran, organization=self.org
            ).exists()
        )
        case = VeteranCase.objects.get(organization=self.org, veteran=self.veteran)
        self.assertTrue(
            CaseNote.objects.filter(case=case, note_type="milestone").exists()
        )

    def test_failure_creating_note_rolls_back_invitation_and_case(self):
        """
        If the note creation fails, the invitation must not be left
        accepted and no orphan case should exist — proves the 3 writes
        share one transaction instead of partially committing.
        """
        from accounts.models import OrganizationMembership
        from vso.models import VeteranCase, CaseNote

        self._seed_pending_case_session()

        with mock.patch(
            "vso.views.CaseNote.objects.create",
            side_effect=RuntimeError("simulated failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("vso:accept_invitation", args=[self.invitation.token])
                )

        self.invitation.refresh_from_db()
        self.assertIsNone(self.invitation.accepted_at)
        self.assertFalse(
            OrganizationMembership.objects.filter(
                user=self.veteran, organization=self.org
            ).exists()
        )
        self.assertFalse(VeteranCase.objects.filter(organization=self.org).exists())
        self.assertFalse(CaseNote.objects.exists())


# =============================================================================
# CASE ARCHIVE VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestCaseArchiveView:
    """Tests for the case archive functionality."""

    def test_can_archive_closed_case(self, client, db):
        """Closed cases can be archived."""
        user = User.objects.create_user(
            email="archivetester@example.com", password="TestPass123!"
        )
        org = Organization.objects.create(
            name="Archive Test Org",
            slug="archive-test-org",
            org_type="vso",
        )
        OrganizationMembership.objects.create(
            user=user,
            organization=org,
            role="admin",
            is_active=True,
        )
        from vso.models import VeteranCase

        case = VeteranCase.objects.create(
            organization=org,
            veteran=user,
            title="Closed Case",
            status="closed_won",
        )

        client.login(email="archivetester@example.com", password="TestPass123!")
        response = client.post(reverse("vso:case_archive", args=[case.pk]))

        case.refresh_from_db()
        assert case.is_archived is True
        assert case.archived_at is not None
        assert response.status_code == 302

    def test_cannot_archive_open_case(self, client, db):
        """Open cases cannot be archived."""
        user = User.objects.create_user(
            email="openarchivetester@example.com", password="TestPass123!"
        )
        org = Organization.objects.create(
            name="Open Archive Test Org",
            slug="open-archive-test-org",
            org_type="vso",
        )
        OrganizationMembership.objects.create(
            user=user,
            organization=org,
            role="admin",
            is_active=True,
        )
        from vso.models import VeteranCase

        case = VeteranCase.objects.create(
            organization=org,
            veteran=user,
            title="Open Case",
            status="gathering_evidence",
        )

        client.login(email="openarchivetester@example.com", password="TestPass123!")
        response = client.post(reverse("vso:case_archive", args=[case.pk]))

        case.refresh_from_db()
        assert case.is_archived is False


# =============================================================================
# ACTIVITY TRACKING SIGNAL TESTS
# =============================================================================


class TestActivityTrackingSignals(TestCase):
    """Tests for activity tracking signals."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="signaltest@example.com", password="TestPass123!"
        )
        self.org = Organization.objects.create(
            name="Signal Test VSO",
            slug="signal-test-vso",
            org_type="vso",
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            role="caseworker",
            is_active=True,
        )
        from vso.models import VeteranCase

        self.case = VeteranCase.objects.create(
            organization=self.org,
            veteran=self.user,
            title="Signal Test Case",
            status="intake",
        )

    def test_note_creation_updates_activity(self):
        """Creating a note should update last_activity_at."""
        from vso.models import CaseNote

        initial_activity = self.case.last_activity_at

        CaseNote.objects.create(
            case=self.case,
            author=self.user,
            subject="Test Note",
            content="Test content",
        )

        self.case.refresh_from_db()
        # After note creation, last_activity_at should be updated
        self.assertIsNotNone(self.case.last_activity_at)
        if initial_activity:
            self.assertGreaterEqual(self.case.last_activity_at, initial_activity)

    def test_condition_creation_updates_activity(self):
        """Creating a condition should update last_activity_at."""
        from vso.models import CaseCondition

        initial_activity = self.case.last_activity_at

        CaseCondition.objects.create(
            case=self.case,
            condition_name="PTSD",
        )

        self.case.refresh_from_db()
        self.assertIsNotNone(self.case.last_activity_at)
        if initial_activity:
            self.assertGreaterEqual(self.case.last_activity_at, initial_activity)


# =============================================================================
# CROSS-ORG SECURITY TESTS (IDOR Defense-in-Depth)
# =============================================================================


@pytest.mark.django_db
class TestCrossOrgSecurity:
    """
    Tests that users in Org A cannot access Org B cases/documents.

    Validates defense-in-depth: even if a user guesses a case PK,
    the org filter prevents cross-organization data access.
    """

    @pytest.fixture(autouse=True)
    def setup_orgs(self, db):
        """Create two organizations with separate users and cases."""
        from vso.models import VeteranCase

        # Org A
        self.org_a = Organization.objects.create(
            name="Org Alpha",
            slug="org-alpha",
            org_type="vso",
        )
        self.user_a = User.objects.create_user(
            email="staff_a@example.com", password="TestPass123!"
        )
        self.veteran_a = User.objects.create_user(
            email="vet_a@example.com", password="TestPass123!"
        )
        OrganizationMembership.objects.create(
            user=self.user_a,
            organization=self.org_a,
            role="admin",
            is_active=True,
        )
        self.case_a = VeteranCase.objects.create(
            organization=self.org_a,
            veteran=self.veteran_a,
            assigned_to=self.user_a,
            title="Org A Case",
            status="intake",
        )

        # Org B
        self.org_b = Organization.objects.create(
            name="Org Beta",
            slug="org-beta",
            org_type="vso",
        )
        self.user_b = User.objects.create_user(
            email="staff_b@example.com", password="TestPass123!"
        )
        self.veteran_b = User.objects.create_user(
            email="vet_b@example.com", password="TestPass123!"
        )
        OrganizationMembership.objects.create(
            user=self.user_b,
            organization=self.org_b,
            role="admin",
            is_active=True,
        )
        self.case_b = VeteranCase.objects.create(
            organization=self.org_b,
            veteran=self.veteran_b,
            assigned_to=self.user_b,
            title="Org B Case",
            status="intake",
        )

    def test_org_a_cannot_view_org_b_case_detail(self, client):
        """User in Org A gets 404 when trying to view Org B case."""
        client.login(email="staff_a@example.com", password="TestPass123!")
        response = client.get(reverse("vso:case_detail", args=[self.case_b.pk]))
        # Should be 404 (org filter) or redirect, not 200
        assert response.status_code in (404, 302)
        if response.status_code == 302:
            assert "case_detail" not in response.url

    def test_org_b_cannot_view_org_a_case_detail(self, client):
        """User in Org B gets 404 when trying to view Org A case."""
        client.login(email="staff_b@example.com", password="TestPass123!")
        response = client.get(reverse("vso:case_detail", args=[self.case_a.pk]))
        assert response.status_code in (404, 302)
        if response.status_code == 302:
            assert "case_detail" not in response.url

    def test_org_a_cannot_update_org_b_case_status(self, client):
        """User in Org A cannot update status of Org B case."""
        client.login(email="staff_a@example.com", password="TestPass123!")
        response = client.post(
            reverse("vso:case_update_status", args=[self.case_b.pk]),
            {"status": "closed_won"},
        )
        assert response.status_code in (404, 302)
        self.case_b.refresh_from_db()
        assert self.case_b.status == "intake"  # Unchanged

    def test_org_a_cannot_add_note_to_org_b_case(self, client):
        """User in Org A cannot add notes to Org B case."""
        client.login(email="staff_a@example.com", password="TestPass123!")
        response = client.post(
            reverse("vso:add_case_note", args=[self.case_b.pk]),
            {"subject": "Malicious Note", "content": "Cross-org injection"},
        )
        assert response.status_code in (404, 302)
        from vso.models import CaseNote

        assert (
            CaseNote.objects.filter(case=self.case_b, subject="Malicious Note").count()
            == 0
        )

    def test_org_a_cannot_archive_org_b_case(self, client):
        """User in Org A cannot archive Org B case."""
        self.case_b.status = "closed_won"
        self.case_b.save()

        client.login(email="staff_a@example.com", password="TestPass123!")
        response = client.post(reverse("vso:case_archive", args=[self.case_b.pk]))
        assert response.status_code in (404, 302)
        self.case_b.refresh_from_db()
        assert self.case_b.is_archived is False

    def test_case_list_only_shows_own_org_cases(self, client):
        """Case list only shows cases from the user's organization."""
        client.login(email="staff_a@example.com", password="TestPass123!")
        response = client.get(reverse("vso:case_list"))

        if response.status_code == 200:
            # Org B case title should NOT appear
            assert b"Org B Case" not in response.content
            # Org A case title SHOULD appear
            assert b"Org A Case" in response.content


class TestCaseNotePHIEncryptionAtRest(TestCase):
    """CaseNote.content is caseworker PHI — must be encrypted at rest."""

    def test_case_note_content_encrypted_at_rest(self):
        from django.db import connection
        from vso.models import VeteranCase, CaseNote
        from core.encryption import FieldEncryption

        User = get_user_model()
        veteran = User.objects.create_user(
            email="vet@example.com", password="TestPass123!"
        )
        author = User.objects.create_user(
            email="cw@example.com", password="TestPass123!"
        )
        org = Organization.objects.create(
            name="Enc Org", slug="enc-org", org_type="vso"
        )
        case = VeteranCase.objects.create(
            organization=org, veteran=veteran, title="Case"
        )
        secret = "Veteran disclosed suicidal ideation during intake call."
        note = CaseNote.objects.create(
            case=case, author=author, subject="Intake", content=secret
        )

        self.assertEqual(CaseNote.objects.get(pk=note.pk).content, secret)

        with connection.cursor() as cursor:
            cursor.execute("SELECT content FROM vso_casenote WHERE id = %s", [note.pk])
            raw = cursor.fetchone()[0]
        self.assertNotIn("suicidal", raw)
        self.assertEqual(FieldEncryption.decrypt(raw), secret)
