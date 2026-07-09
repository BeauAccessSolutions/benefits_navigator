"""
Tests for the veteran-facing data-activity (access transparency) page and
the VSO access logging that feeds it (Phase 2 of
docs/PRIVACY_HARDENING_PLAN.md).

The claim under test: every access to a veteran's records by someone other
than the veteran is recorded and visible to the veteran.
"""

import pytest
from django.urls import reverse

from accounts.models import Organization, OrganizationMembership
from claims.models import Document
from core.models import AuditLog
from vso.models import SharedDocument, VeteranCase

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test VSO", slug="test-vso", org_type="vso")


@pytest.fixture
def vso_staff(db, org, django_user_model, user_password):
    staff = django_user_model.objects.create_user(
        email="caseworker@vso.org",
        password=user_password,
        first_name="Casey",
        last_name="Worker",
    )
    OrganizationMembership.objects.create(
        organization=org, user=staff, role="caseworker"
    )
    return staff


@pytest.fixture
def case(db, org, user, vso_staff):
    return VeteranCase.objects.create(
        organization=org,
        veteran=user,
        assigned_to=vso_staff,
        title="Test Case",
        status="gathering_evidence",
    )


@pytest.fixture
def document(db, user):
    return Document.objects.create(
        user=user,
        file_name="decision_letter.pdf",
        file_size=1024,
        mime_type="application/pdf",
        document_type="decision_letter",
        status="completed",
    )


@pytest.fixture
def shared_doc(db, case, document, user):
    return SharedDocument.objects.create(
        case=case,
        document=document,
        shared_by=user,
        include_ai_analysis=False,
        status="pending",
    )


@pytest.fixture
def vso_client(vso_staff, user_password):
    # Separate Client instance — must not share login state with
    # authenticated_client (the veteran) in the same test.
    from django.test import Client

    vso = Client()
    vso.login(email="caseworker@vso.org", password=user_password)
    return vso


class TestVSOAccessLogging:
    """VSO access points must write AuditLog rows the veteran can see."""

    def test_case_view_is_logged(self, vso_client, case, user):
        response = vso_client.get(reverse("vso:case_detail", kwargs={"pk": case.pk}))
        assert response.status_code == 200

        log = AuditLog.objects.filter(
            action="vso_case_view",
            resource_type="VeteranCase",
            resource_id=case.pk,
        ).first()
        assert log is not None
        assert log.user.email == "caseworker@vso.org"
        assert log.details["veteran_id"] == user.pk

    def test_shared_document_review_is_logged(
        self, vso_client, case, document, shared_doc
    ):
        response = vso_client.get(
            reverse(
                "vso:shared_document_review",
                kwargs={"pk": case.pk, "doc_pk": shared_doc.pk},
            )
        )
        assert response.status_code == 200

        log = AuditLog.objects.filter(
            action="vso_document_review",
            resource_type="Document",
            resource_id=document.pk,
        ).first()
        assert log is not None
        assert log.details["event"] == "viewed"
        assert log.details["case_id"] == case.pk


class TestDataActivityPage:
    url = reverse("core:data_activity")

    def test_requires_login(self, client):
        response = client.get(self.url)
        assert response.status_code == 302
        assert "login" in response.url

    def test_empty_state(self, authenticated_client):
        response = authenticated_client.get(self.url)
        assert response.status_code == 200
        assert "No outside access recorded" in response.content.decode()

    def test_vso_access_visible_to_veteran(
        self, authenticated_client, vso_client, case, document, shared_doc, org
    ):
        # VSO staffer views the case and the shared document
        vso_client.get(reverse("vso:case_detail", kwargs={"pk": case.pk}))
        vso_client.get(
            reverse(
                "vso:shared_document_review",
                kwargs={"pk": case.pk, "doc_pk": shared_doc.pk},
            )
        )

        response = authenticated_client.get(self.url)
        content = response.content.decode()

        assert response.status_code == 200
        assert "Casey Worker" in content
        assert org.name in content
        assert "Case Viewed" in content
        assert "Document Reviewed" in content

    def test_own_actions_excluded(self, authenticated_client, user, document):
        AuditLog.log(
            action="document_view",
            user=user,
            resource_type="Document",
            resource_id=document.pk,
        )
        response = authenticated_client.get(self.url)
        assert "No outside access recorded" in response.content.decode()

    def test_other_veterans_activity_not_visible(
        self, authenticated_client, django_user_model, user_password, vso_staff
    ):
        # Access to ANOTHER veteran's document must never appear
        other = django_user_model.objects.create_user(
            email="other-vet@example.com", password=user_password
        )
        other_doc = Document.objects.create(
            user=other,
            file_name="other.pdf",
            file_size=512,
            mime_type="application/pdf",
            document_type="medical_records",
        )
        AuditLog.log(
            action="vso_document_review",
            user=vso_staff,
            resource_type="Document",
            resource_id=other_doc.pk,
        )

        response = authenticated_client.get(self.url)
        assert "No outside access recorded" in response.content.decode()

    def test_pagination(self, authenticated_client, user, document, vso_staff):
        for _ in range(30):
            AuditLog.log(
                action="vso_document_review",
                user=vso_staff,
                resource_type="Document",
                resource_id=document.pk,
            )
        response = authenticated_client.get(self.url)
        content = response.content.decode()
        assert "Page 1 of 2" in content
        assert "30 accesses recorded" in content
