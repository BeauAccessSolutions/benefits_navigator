"""
Tests for Phase 4 of docs/PRIVACY_HARDENING_PLAN.md — operator access
minimization:

- Django admin never renders decrypted PII/PHI field values
- Admin access to veteran records is audit-logged and visible on the
  veteran's /data-activity/ page
"""

import pytest
from django.test import Client
from django.urls import reverse

from accounts.models import Organization
from claims.models import Document
from core.models import AuditLog
from vso.models import VeteranCase

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def admin_user(django_user_model, user_password):
    return django_user_model.objects.create_superuser(
        email="ops@benefitsnavigator.test", password=user_password
    )


@pytest.fixture
def admin_client_(admin_user, user_password):
    c = Client()
    c.login(email="ops@benefitsnavigator.test", password=user_password)
    return c


@pytest.fixture
def document(user):
    return Document.objects.create(
        user=user,
        file_name="decision.pdf",
        file_size=1024,
        mime_type="application/pdf",
        document_type="decision_letter",
        ai_summary={"secret_finding": "PTSD denied for missing nexus"},
    )


@pytest.fixture
def case(user):
    org = Organization.objects.create(name="VSO", slug="vso-x", org_type="vso")
    return VeteranCase.objects.create(
        organization=org,
        veteran=user,
        title="Case X",
        description="Veteran reports MST-related PTSD",
        conditions=[{"condition": "PTSD"}],
        closure_notes="Sensitive closure detail",
    )


class TestAdminPIIRedaction:
    def test_document_admin_hides_ai_summary(self, admin_client_, document):
        url = reverse("admin:claims_document_change", args=[document.pk])
        response = admin_client_.get(url)
        content = response.content.decode()

        assert response.status_code == 200
        assert "secret_finding" not in content
        assert "PTSD denied" not in content

    def test_case_admin_hides_phi_fields(self, admin_client_, case):
        url = reverse("admin:vso_veterancase_change", args=[case.pk])
        response = admin_client_.get(url)
        content = response.content.decode()

        assert response.status_code == 200
        assert "MST-related" not in content
        assert "Sensitive closure detail" not in content
        assert '"condition": "PTSD"' not in content

    def test_profile_admin_hides_encrypted_pii(self, admin_client_, user):
        profile = user.profile
        profile.va_file_number = "C12345678"
        profile.save()

        url = reverse("admin:accounts_userprofile_change", args=[profile.pk])
        response = admin_client_.get(url)
        content = response.content.decode()

        assert response.status_code == 200
        assert "C12345678" not in content
        assert 'name="va_file_number"' not in content
        assert 'name="date_of_birth"' not in content

    def test_user_admin_hides_phone_number(self, admin_client_, user):
        user.phone_number = "555-867-5309"
        user.save()

        url = reverse("admin:accounts_user_change", args=[user.pk])
        response = admin_client_.get(url)

        assert response.status_code == 200
        assert "555-867-5309" not in response.content.decode()


class TestAdminAccessLogging:
    def test_document_change_view_logged(self, admin_client_, document):
        admin_client_.get(
            reverse("admin:claims_document_change", args=[document.pk])
        )
        log = AuditLog.objects.filter(
            action="admin_action",
            resource_type="Document",
            resource_id=document.pk,
        ).first()
        assert log is not None
        assert log.details["event"] == "admin_change_view"

    def test_case_change_view_logged(self, admin_client_, case):
        admin_client_.get(
            reverse("admin:vso_veterancase_change", args=[case.pk])
        )
        assert AuditLog.objects.filter(
            action="admin_action",
            resource_type="VeteranCase",
            resource_id=case.pk,
        ).exists()

    def test_admin_access_visible_on_veteran_activity_page(
        self, admin_client_, authenticated_client, document
    ):
        # Operator opens the veteran's document in admin...
        admin_client_.get(
            reverse("admin:claims_document_change", args=[document.pk])
        )

        # ...and the veteran sees it on their data-activity page
        response = authenticated_client.get(reverse("core:data_activity"))
        content = response.content.decode()

        assert response.status_code == 200
        assert "ops@benefitsnavigator.test" in content
        assert "Admin Action" in content
