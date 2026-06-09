"""
Tests for veteran-controlled sharing revocation (Phase 1 of
docs/PRIVACY_HARDENING_PLAN.md).

The claim under test: a veteran can revoke a document share at any time,
the VSO loses access immediately, and the revocation is audit-logged.
"""

import pytest
from django.urls import reverse

from accounts.models import Organization, OrganizationMembership
from claims.models import Document
from core.models import AuditLog
from vso.models import SharedDocument, VeteranCase

User = None  # resolved via fixtures; module kept import-light

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="Test VSO", slug="test-vso", org_type="vso"
    )


@pytest.fixture
def vso_staff(db, org, django_user_model, user_password):
    staff = django_user_model.objects.create_user(
        email="caseworker@vso.org", password=user_password
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


def _revoke_url(document, shared_doc):
    return reverse(
        "claims:document_unshare",
        kwargs={"pk": document.pk, "share_pk": shared_doc.pk},
    )


class TestDocumentUnshare:
    def test_owner_can_revoke_share(
        self, authenticated_client, user, document, shared_doc
    ):
        response = authenticated_client.post(_revoke_url(document, shared_doc))

        assert response.status_code == 302
        assert response.url == reverse(
            "claims:document_detail", kwargs={"pk": document.pk}
        )
        assert not SharedDocument.objects.filter(pk=shared_doc.pk).exists()

    def test_revocation_is_audit_logged(
        self, authenticated_client, user, document, shared_doc, case
    ):
        share_pk = shared_doc.pk
        authenticated_client.post(_revoke_url(document, shared_doc))

        log = AuditLog.objects.filter(
            action="vso_document_unshare", resource_id=share_pk
        ).first()
        assert log is not None
        assert log.details["document_id"] == document.pk
        assert log.details["case_id"] == case.pk
        assert log.details["organization_id"] == case.organization.pk

    def test_non_owner_cannot_revoke(
        self, client, document, shared_doc, vso_staff, user_password
    ):
        # Even the VSO staffer on the case cannot revoke through this route —
        # only the veteran who owns the document can.
        client.login(email="caseworker@vso.org", password=user_password)
        response = client.post(_revoke_url(document, shared_doc))

        assert response.status_code == 404
        assert SharedDocument.objects.filter(pk=shared_doc.pk).exists()

    def test_get_method_not_allowed(
        self, authenticated_client, document, shared_doc
    ):
        response = authenticated_client.get(_revoke_url(document, shared_doc))
        assert response.status_code == 405
        assert SharedDocument.objects.filter(pk=shared_doc.pk).exists()

    def test_anonymous_redirected_to_login(self, client, document, shared_doc):
        response = client.post(_revoke_url(document, shared_doc))
        assert response.status_code == 302
        assert "login" in response.url
        assert SharedDocument.objects.filter(pk=shared_doc.pk).exists()

    def test_share_pk_must_belong_to_document(
        self, authenticated_client, user, case, document, shared_doc
    ):
        other_doc = Document.objects.create(
            user=user,
            file_name="other.pdf",
            file_size=512,
            mime_type="application/pdf",
            document_type="medical_records",
        )
        # share_pk belongs to `document`, not `other_doc` — mismatch must 404
        url = reverse(
            "claims:document_unshare",
            kwargs={"pk": other_doc.pk, "share_pk": shared_doc.pk},
        )
        response = authenticated_client.post(url)
        assert response.status_code == 404
        assert SharedDocument.objects.filter(pk=shared_doc.pk).exists()

    def test_reshare_after_revoke_works(
        self, authenticated_client, user, case, document, shared_doc
    ):
        authenticated_client.post(_revoke_url(document, shared_doc))
        assert not SharedDocument.objects.filter(document=document).exists()

        # unique_together (case, document) must be freed by the delete
        reshared = SharedDocument.objects.create(
            case=case, document=document, shared_by=user, status="pending"
        )
        assert reshared.pk is not None

    def test_detail_page_lists_active_shares(
        self, authenticated_client, document, shared_doc, org
    ):
        response = authenticated_client.get(
            reverse("claims:document_detail", kwargs={"pk": document.pk})
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "Shared With" in content
        assert org.name in content
        assert _revoke_url(document, shared_doc) in content

    def test_vso_loses_access_after_revoke(
        self, authenticated_client, client, user, user_password,
        document, shared_doc, case, vso_staff
    ):
        """End-to-end: after revocation the share is gone from the VSO's case."""
        authenticated_client.post(_revoke_url(document, shared_doc))

        assert not SharedDocument.objects.filter(case=case).exists()
        assert case.shared_documents.count() == 0
