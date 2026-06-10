"""
Tests for Phase 3 of docs/PRIVACY_HARDENING_PLAN.md:

- Least-privilege case visibility (Organization.restrict_caseworker_visibility)
- Bulk CSV export as an org-admin privilege, without veteran emails
- MFA enforcement for VSO staff (VSO_MFA_REQUIRED)
"""

import pytest
from django.test import Client
from django.urls import reverse

from accounts.models import Organization, OrganizationMembership
from vso.models import VeteranCase
from vso.permissions import scope_cases_for_member

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="Test VSO", slug="test-vso", org_type="vso"
    )


@pytest.fixture
def restricted_org(db):
    return Organization.objects.create(
        name="Restricted VSO",
        slug="restricted-vso",
        org_type="vso",
        restrict_caseworker_visibility=True,
    )


def _make_staff(django_user_model, password, org, email, role):
    staff = django_user_model.objects.create_user(email=email, password=password)
    OrganizationMembership.objects.create(organization=org, user=staff, role=role)
    return staff


def _staff_client(email, password):
    c = Client()
    c.login(email=email, password=password)
    return c


@pytest.fixture
def veteran(django_user_model, user_password):
    return django_user_model.objects.create_user(
        email="vet@example.com", password=user_password
    )


class TestCaseworkerScoping:
    def _cases(self, org, veteran, caseworker, other_worker):
        mine = VeteranCase.objects.create(
            organization=org, veteran=veteran, assigned_to=caseworker,
            title="Mine", status="intake",
        )
        unassigned = VeteranCase.objects.create(
            organization=org, veteran=veteran,
            title="Unassigned", status="intake",
        )
        someone_elses = VeteranCase.objects.create(
            organization=org, veteran=veteran, assigned_to=other_worker,
            title="Someone Else's", status="intake",
        )
        return mine, unassigned, someone_elses

    def test_restricted_org_caseworker_sees_only_own_and_unassigned(
        self, restricted_org, veteran, django_user_model, user_password
    ):
        worker = _make_staff(
            django_user_model, user_password, restricted_org,
            "worker@vso.org", "caseworker",
        )
        other = _make_staff(
            django_user_model, user_password, restricted_org,
            "other@vso.org", "caseworker",
        )
        mine, unassigned, someone_elses = self._cases(
            restricted_org, veteran, worker, other
        )

        scoped = scope_cases_for_member(
            worker, restricted_org,
            VeteranCase.objects.filter(organization=restricted_org),
        )
        pks = set(scoped.values_list('pk', flat=True))
        assert pks == {mine.pk, unassigned.pk}

    def test_restricted_org_admin_sees_all(
        self, restricted_org, veteran, django_user_model, user_password
    ):
        admin = _make_staff(
            django_user_model, user_password, restricted_org,
            "admin@vso.org", "admin",
        )
        worker = _make_staff(
            django_user_model, user_password, restricted_org,
            "worker@vso.org", "caseworker",
        )
        self._cases(restricted_org, veteran, worker, admin)

        scoped = scope_cases_for_member(
            admin, restricted_org,
            VeteranCase.objects.filter(organization=restricted_org),
        )
        assert scoped.count() == 3

    def test_unrestricted_org_unchanged(
        self, org, veteran, django_user_model, user_password
    ):
        worker = _make_staff(
            django_user_model, user_password, org, "worker@vso.org", "caseworker"
        )
        other = _make_staff(
            django_user_model, user_password, org, "other@vso.org", "caseworker"
        )
        self._cases(org, veteran, worker, other)

        scoped = scope_cases_for_member(
            worker, org, VeteranCase.objects.filter(organization=org)
        )
        assert scoped.count() == 3

    def test_restricted_caseworker_gets_404_on_unassigned_to_them_case(
        self, restricted_org, veteran, django_user_model, user_password
    ):
        worker = _make_staff(
            django_user_model, user_password, restricted_org,
            "worker@vso.org", "caseworker",
        )
        other = _make_staff(
            django_user_model, user_password, restricted_org,
            "other@vso.org", "caseworker",
        )
        _, _, someone_elses = self._cases(restricted_org, veteran, worker, other)

        client = _staff_client("worker@vso.org", user_password)
        response = client.get(
            reverse("vso:case_detail", kwargs={"pk": someone_elses.pk})
        )
        assert response.status_code == 404


class TestExportPrivilege:
    @pytest.fixture
    def cases(self, org, veteran, django_user_model, user_password):
        worker = _make_staff(
            django_user_model, user_password, org, "worker@vso.org", "caseworker"
        )
        VeteranCase.objects.create(
            organization=org, veteran=veteran, assigned_to=worker,
            title="Case A", status="intake",
        )
        return worker

    def test_caseworker_cannot_export(self, org, cases, user_password):
        client = _staff_client("worker@vso.org", user_password)
        response = client.get(reverse("vso:case_list") + "?export=csv")

        # Redirected back with an error, not a CSV
        assert response.status_code == 302
        assert response.url == reverse("vso:case_list")

    def test_admin_can_export_without_veteran_email(
        self, org, cases, veteran, django_user_model, user_password
    ):
        _make_staff(django_user_model, user_password, org, "admin@vso.org", "admin")
        client = _staff_client("admin@vso.org", user_password)

        response = client.get(reverse("vso:case_list") + "?export=csv")
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"

        content = response.content.decode()
        assert "Case A" in content
        assert "Veteran Email" not in content
        assert veteran.email not in content

    def test_export_rate_limited(
        self, org, cases, django_user_model, user_password, settings
    ):
        settings.RATELIMIT_ENABLE = True  # disabled by default under DEBUG
        _make_staff(django_user_model, user_password, org, "admin@vso.org", "admin")
        client = _staff_client("admin@vso.org", user_password)
        url = reverse("vso:case_list") + "?export=csv"

        for _ in range(5):
            assert client.get(url).status_code == 200

        # Sixth export within the hour is refused
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("vso:case_list")


class TestMFAEnforcement:
    @pytest.fixture
    def staff(self, org, django_user_model, user_password):
        return _make_staff(
            django_user_model, user_password, org, "worker@vso.org", "caseworker"
        )

    def test_default_mode_warns_but_allows(self, staff, user_password):
        client = _staff_client("worker@vso.org", user_password)
        response = client.get(reverse("vso:dashboard"))
        # Encouragement mode: page loads (200 or org-selection redirect, not 2FA)
        assert response.status_code in (200, 302)
        if response.status_code == 302:
            assert "two-factor" not in response.url

    def test_required_mode_blocks_after_grace(
        self, staff, org, user_password, settings
    ):
        settings.VSO_MFA_REQUIRED = True
        settings.VSO_MFA_GRACE_PERIOD_DAYS = 0  # grace already over

        client = _staff_client("worker@vso.org", user_password)
        response = client.get(reverse("vso:dashboard"))

        assert response.status_code == 302
        assert response.url == reverse("two-factor-setup")

    def test_required_mode_allows_during_grace(
        self, staff, org, user_password, settings
    ):
        settings.VSO_MFA_REQUIRED = True
        settings.VSO_MFA_GRACE_PERIOD_DAYS = 30  # joined today → in grace

        client = _staff_client("worker@vso.org", user_password)
        response = client.get(reverse("vso:dashboard"))

        assert response.status_code in (200, 302)
        if response.status_code == 302:
            assert "two-factor" not in response.url

    def test_required_mode_ignores_non_vso_pages(
        self, staff, user_password, settings
    ):
        settings.VSO_MFA_REQUIRED = True
        settings.VSO_MFA_GRACE_PERIOD_DAYS = 0

        client = _staff_client("worker@vso.org", user_password)
        response = client.get(reverse("dashboard"))
        # Veteran-path pages stay accessible; only /vso/ is gated
        assert response.status_code == 200
