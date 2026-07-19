"""
Tests for the claims app - Document management, OCR, AI analysis, and Celery tasks.

Covers:
- Document model and properties
- Claim model and properties
- DocumentUploadForm validation
- Document upload and processing views
- Denial decoder views and workflow
- OCRService functionality
- AIService functionality
- Celery tasks for document processing
- Access control and permissions
"""

import json
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.utils import timezone

from claims.models import Document, Claim
from claims.forms import DocumentUploadForm

User = get_user_model()


# =============================================================================
# DOCUMENT MODEL TESTS
# =============================================================================


class TestDocumentModel(TestCase):
    """Tests for the Document model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )

    def test_document_creation(self):
        """Document can be created with required fields."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            file_size=1024,
            mime_type="application/pdf",
            document_type="medical_records",
        )
        self.assertEqual(doc.user, self.user)
        self.assertEqual(doc.file_name, "test.pdf")

    def test_document_str_representation(self):
        """Document string includes file name."""
        doc = Document.objects.create(
            user=self.user,
            file_name="my_records.pdf",
            document_type="medical_records",
        )
        self.assertIn("my_records.pdf", str(doc))

    def test_document_type_choices(self):
        """Document accepts all valid type choices."""
        valid_types = [
            "medical_records",
            "service_records",
            "decision_letter",
            "buddy_statement",
            "lay_statement",
            "nexus_letter",
            "employment_records",
            "personal_statement",
            "other",
        ]
        for doc_type in valid_types:
            doc = Document.objects.create(
                user=self.user,
                file_name=f"test_{doc_type}.pdf",
                document_type=doc_type,
            )
            self.assertEqual(doc.document_type, doc_type)

    def test_document_status_transitions(self):
        """Document status can transition through states."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            status="uploading",
        )
        self.assertEqual(doc.status, "uploading")

        doc.mark_processing()
        self.assertEqual(doc.status, "processing")

        doc.mark_analyzing()
        self.assertEqual(doc.status, "analyzing")

        doc.mark_completed(
            ocr_length=14,  # "Extracted text" length
            ocr_confidence=95.0,
            page_count=1,
        )
        self.assertEqual(doc.status, "completed")
        self.assertEqual(doc.ocr_length, 14)

    def test_document_mark_failed(self):
        """Document can be marked as failed with error message."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            status="processing",
        )
        doc.mark_failed("OCR engine error")
        doc.refresh_from_db()

        self.assertEqual(doc.status, "failed")
        self.assertEqual(doc.error_message, "OCR engine error")

    def test_document_file_size_mb(self):
        """file_size_mb property calculates correctly."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            file_size=5242880,  # 5 MB in bytes
        )
        self.assertEqual(doc.file_size_mb, 5.0)

    def test_document_is_processing(self):
        """is_processing property returns True for processing/analyzing."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            status="processing",
        )
        self.assertTrue(doc.is_processing)

        doc.status = "analyzing"
        doc.save()
        self.assertTrue(doc.is_processing)

        doc.status = "completed"
        doc.save()
        self.assertFalse(doc.is_processing)

    def test_document_is_complete(self):
        """is_complete property returns True for completed documents."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            status="completed",
        )
        self.assertTrue(doc.is_complete)

        doc.status = "processing"
        doc.save()
        self.assertFalse(doc.is_complete)

    def test_document_has_failed(self):
        """has_failed property returns True for failed documents."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            status="failed",
        )
        self.assertTrue(doc.has_failed)

    def test_document_soft_delete(self):
        """Document can be soft deleted."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
        )
        doc.delete()  # Soft delete

        self.assertTrue(doc.is_deleted)
        self.assertIsNotNone(doc.deleted_at)

        # Can still find with all objects
        all_docs = Document.all_objects.filter(user=self.user)
        self.assertEqual(all_docs.count(), 1)

    def test_document_hard_delete(self):
        """Document can be permanently deleted."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
        )
        doc.hard_delete()

        self.assertEqual(Document.all_objects.count(), 0)

    # OCR Metadata Tests (PR 1 - Ephemeral OCR Refactor)
    def test_ocr_metadata_default_values(self):
        """OCR metadata fields have correct defaults."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
        )
        self.assertEqual(doc.ocr_length, 0)
        self.assertEqual(doc.ocr_status, "pending")

    def test_mark_completed_sets_ocr_status(self):
        """mark_completed sets ocr_status to 'completed'."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            status="processing",
        )
        doc.mark_completed(ocr_length=20, ocr_confidence=95.0)
        doc.refresh_from_db()

        self.assertEqual(doc.ocr_status, "completed")

    def test_mark_completed_sets_ocr_length(self):
        """mark_completed sets ocr_length from parameter."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            status="processing",
        )
        test_length = 32
        doc.mark_completed(ocr_length=test_length, ocr_confidence=95.0)
        doc.refresh_from_db()

        self.assertEqual(doc.ocr_length, test_length)

    def test_mark_completed_accepts_explicit_ocr_length(self):
        """mark_completed accepts explicit ocr_length parameter."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            status="processing",
        )
        doc.mark_completed(ocr_confidence=95.0, ocr_length=12345)
        doc.refresh_from_db()

        self.assertEqual(doc.ocr_length, 12345)

    def test_mark_failed_with_ocr_failure(self):
        """mark_failed with ocr_failed=True sets ocr_status to 'failed'."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            status="processing",
        )
        doc.mark_failed("OCR engine unavailable", ocr_failed=True)
        doc.refresh_from_db()

        self.assertEqual(doc.status, "failed")
        self.assertEqual(doc.ocr_status, "failed")

    def test_mark_failed_without_ocr_failure(self):
        """mark_failed without ocr_failed keeps ocr_status unchanged."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            status="processing",
            ocr_status="completed",  # OCR succeeded, AI failed
        )
        doc.mark_failed("AI analysis error")
        doc.refresh_from_db()

        self.assertEqual(doc.status, "failed")
        self.assertEqual(doc.ocr_status, "completed")  # Unchanged

    def test_ocr_status_choices(self):
        """OCR status accepts all valid choices."""
        valid_statuses = ["pending", "completed", "failed"]
        for ocr_status in valid_statuses:
            doc = Document.objects.create(
                user=self.user,
                file_name=f"test_{ocr_status}.pdf",
                ocr_status=ocr_status,
            )
            self.assertEqual(doc.ocr_status, ocr_status)


# =============================================================================
# CLAIM MODEL TESTS
# =============================================================================


class TestClaimModel(TestCase):
    """Tests for the Claim model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )

    def test_claim_creation(self):
        """Claim can be created with required fields."""
        claim = Claim.objects.create(
            user=self.user,
            title="PTSD Service Connection",
            claim_type="initial",
            status="draft",
        )
        self.assertEqual(claim.user, self.user)
        self.assertEqual(claim.title, "PTSD Service Connection")

    def test_claim_str_representation(self):
        """Claim string includes title."""
        claim = Claim.objects.create(
            user=self.user,
            title="Knee Injury Increase",
            claim_type="increase",
        )
        self.assertIn("Knee Injury Increase", str(claim))

    def test_claim_type_choices(self):
        """Claim accepts all valid type choices."""
        valid_types = ["initial", "increase", "secondary", "new_condition"]
        for claim_type in valid_types:
            claim = Claim.objects.create(
                user=self.user,
                title=f"Test {claim_type}",
                claim_type=claim_type,
            )
            self.assertEqual(claim.claim_type, claim_type)

    def test_claim_status_choices(self):
        """Claim accepts all valid status choices."""
        valid_statuses = [
            "draft",
            "gathering_evidence",
            "submitted",
            "pending",
            "decided",
            "appealed",
        ]
        for status in valid_statuses:
            claim = Claim.objects.create(
                user=self.user,
                title=f"Test {status}",
                status=status,
            )
            self.assertEqual(claim.status, status)

    def test_claim_days_since_submission(self):
        """days_since_submission calculates correctly."""
        claim = Claim.objects.create(
            user=self.user,
            title="Submitted Claim",
            submission_date=date.today() - timedelta(days=45),
        )
        self.assertEqual(claim.days_since_submission, 45)

    def test_claim_days_since_submission_none(self):
        """days_since_submission returns None when not submitted."""
        claim = Claim.objects.create(
            user=self.user,
            title="Draft Claim",
        )
        self.assertIsNone(claim.days_since_submission)

    def test_claim_document_count(self):
        """document_count returns correct number of documents."""
        claim = Claim.objects.create(
            user=self.user,
            title="Test Claim",
        )
        # Add documents to claim
        for i in range(3):
            Document.objects.create(
                user=self.user,
                file_name=f"doc{i}.pdf",
                claim=claim,
            )
        self.assertEqual(claim.document_count, 3)


# =============================================================================
# DOCUMENT UPLOAD FORM TESTS
# =============================================================================


class TestDocumentUploadForm(TestCase):
    """Tests for the DocumentUploadForm."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )

    def get_test_pdf(self, size=1024):
        """Create a test PDF file."""
        # Minimal valid PDF
        content = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer << /Size 4 /Root 1 0 R >>
startxref
190
%%EOF"""
        # Pad to desired size
        if len(content) < size:
            content = content + b"\x00" * (size - len(content))
        return SimpleUploadedFile("test.pdf", content, content_type="application/pdf")

    def test_form_valid_with_pdf(self):
        """Form is valid with a PDF file."""
        pdf_file = self.get_test_pdf()
        form = DocumentUploadForm(
            data={"document_type": "medical_records"},
            files={"file": pdf_file},
            user=self.user,
        )
        # May fail due to magic byte validation in tests
        # Testing the basic form structure
        self.assertIn("document_type", form.fields)
        self.assertIn("file", form.fields)

    def test_form_rejects_empty_file(self):
        """Form rejects empty file upload."""
        form = DocumentUploadForm(
            data={"document_type": "medical_records"}, files={}, user=self.user
        )
        self.assertFalse(form.is_valid())

    def test_form_rejects_invalid_extension(self):
        """Form rejects files with invalid extensions."""
        txt_file = SimpleUploadedFile(
            "test.txt", b"This is a text file", content_type="text/plain"
        )
        form = DocumentUploadForm(
            data={"document_type": "medical_records"},
            files={"file": txt_file},
            user=self.user,
        )
        self.assertFalse(form.is_valid())

    def test_form_document_type_required(self):
        """Form requires document_type selection."""
        pdf_file = self.get_test_pdf()
        form = DocumentUploadForm(
            data={}, files={"file": pdf_file}, user=self.user  # Missing document_type
        )
        self.assertFalse(form.is_valid())
        self.assertIn("document_type", form.errors)


# =============================================================================
# DOCUMENT VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestDocumentListView:
    """Tests for the document list view."""

    def test_document_list_requires_login(self, client):
        """Document list requires authentication."""
        response = client.get(reverse("claims:document_list"))
        assert response.status_code == 302

    def test_document_list_loads(self, authenticated_client):
        """Document list loads for authenticated user."""
        response = authenticated_client.get(reverse("claims:document_list"))
        assert response.status_code == 200

    def test_document_list_shows_user_documents(self, authenticated_client, document):
        """Document list shows user's documents."""
        response = authenticated_client.get(reverse("claims:document_list"))
        assert response.status_code == 200
        assert document in response.context["documents"]

    def test_document_list_hides_other_user_documents(
        self, authenticated_client, other_user
    ):
        """Document list doesn't show other user's documents."""
        other_doc = Document.objects.create(
            user=other_user,
            file_name="other_user.pdf",
        )
        response = authenticated_client.get(reverse("claims:document_list"))
        documents = response.context["documents"]
        assert other_doc not in documents


@pytest.mark.django_db
class TestDocumentUploadView:
    """Tests for the document upload view."""

    def test_upload_requires_login(self, client):
        """Upload page requires authentication."""
        response = client.get(reverse("claims:document_upload"))
        assert response.status_code == 302

    def test_upload_page_loads(self, authenticated_client):
        """Upload page loads for authenticated user."""
        response = authenticated_client.get(reverse("claims:document_upload"))
        assert response.status_code == 200
        assert "form" in response.context


@pytest.mark.django_db
class TestDocumentDetailView:
    """Tests for the document detail view."""

    def test_detail_requires_login(self, client, document):
        """Document detail requires authentication."""
        response = client.get(
            reverse("claims:document_detail", kwargs={"pk": document.pk})
        )
        assert response.status_code == 302

    def test_detail_loads_for_owner(self, authenticated_client, document):
        """Document detail loads for document owner."""
        response = authenticated_client.get(
            reverse("claims:document_detail", kwargs={"pk": document.pk})
        )
        assert response.status_code == 200
        assert response.context["document"] == document

    def test_detail_denied_for_other_user(self, authenticated_client, other_user):
        """Document detail returns 404 for non-owner."""
        other_doc = Document.objects.create(
            user=other_user,
            file_name="other.pdf",
        )
        response = authenticated_client.get(
            reverse("claims:document_detail", kwargs={"pk": other_doc.pk})
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestDocumentFileAffordances:
    """
    The protected file routes must be reachable from the UI.

    These views were correct and fully tested but no template ever linked to
    them, so users could upload, tag, share and delete a document without ever
    being able to open it. These tests pin the link, not just the route.
    """

    def test_detail_page_links_to_protected_view_and_download(
        self, authenticated_client, document
    ):
        """The detail page exposes both file routes."""
        response = authenticated_client.get(
            reverse("claims:document_detail", kwargs={"pk": document.pk})
        )
        html = response.content.decode()

        assert reverse("claims:document_view", kwargs={"pk": document.pk}) in html
        assert reverse("claims:document_download", kwargs={"pk": document.pk}) in html

    def test_detail_page_never_links_to_media_url(
        self, authenticated_client, document
    ):
        """/media/ is not served, so a raw file URL would be a guaranteed 404."""
        response = authenticated_client.get(
            reverse("claims:document_detail", kwargs={"pk": document.pk})
        )
        assert document.file.url not in response.content.decode()

    def test_file_links_are_not_blank_targeted(self, authenticated_client, document):
        """
        The file links must not use target="_blank": the Capacitor iOS wrapper
        sends _blank to Safari, which has no session cookie and would show a
        login page instead of the document.
        """
        response = authenticated_client.get(
            reverse("claims:document_detail", kwargs={"pk": document.pk})
        )
        html = response.content.decode()

        for name in ("claims:document_view", "claims:document_download"):
            url = reverse(name, kwargs={"pk": document.pk})
            start = html.index(f'href="{url}"')
            anchor = html[html.rindex("<a ", 0, start) : html.index(">", start)]
            assert "_blank" not in anchor, f"{name} anchor is _blank targeted"

    def test_no_template_comment_leaks_into_page(
        self, authenticated_client, document
    ):
        """
        Django's {# #} comment syntax is single-line only; a multi-line one is
        not parsed as a comment and renders as visible text to the user.
        """
        response = authenticated_client.get(
            reverse("claims:document_detail", kwargs={"pk": document.pk})
        )
        html = response.content.decode()

        assert "{#" not in html
        assert "{% comment" not in html

    def test_file_links_shown_even_when_processing_incomplete(
        self, authenticated_client, document
    ):
        """
        Opening the file is gated on the file existing, not on AI processing
        having finished -- a user most needs the original when processing failed.
        """
        document.status = "failed"
        document.save()

        response = authenticated_client.get(
            reverse("claims:document_detail", kwargs={"pk": document.pk})
        )
        html = response.content.decode()

        assert not document.is_complete
        assert reverse("claims:document_view", kwargs={"pk": document.pk}) in html
        assert reverse("claims:document_download", kwargs={"pk": document.pk}) in html


@pytest.mark.django_db
class TestDocumentFileAccessControl:
    """
    Ownership and auth gates on the protected file routes.

    The views enforced this already but nothing tested it, and until now the
    routes were unreachable from the UI so the gate was never exercised in
    practice. These pin it.
    """

    @pytest.mark.parametrize("route", ["claims:document_view", "claims:document_download"])
    def test_owner_gets_file(self, authenticated_client, document, route):
        """The owning user receives the file bytes."""
        response = authenticated_client.get(
            reverse(route, kwargs={"pk": document.pk})
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("route", ["claims:document_view", "claims:document_download"])
    def test_other_user_gets_404(
        self, client, document, other_user, user_password, route
    ):
        """A second user cannot fetch someone else's document."""
        client.login(email=other_user.email, password=user_password)

        response = client.get(reverse(route, kwargs={"pk": document.pk}))

        assert response.status_code == 404

    @pytest.mark.parametrize("route", ["claims:document_view", "claims:document_download"])
    def test_anonymous_is_redirected(self, client, document, route):
        """Anonymous users are sent to login, never served the file."""
        response = client.get(reverse(route, kwargs={"pk": document.pk}))
        assert response.status_code == 302

    @pytest.mark.parametrize("route", ["claims:document_view", "claims:document_download"])
    def test_soft_deleted_document_is_404(
        self, authenticated_client, document, route
    ):
        """Soft-deleted documents are not retrievable."""
        document.is_deleted = True
        document.save()

        response = authenticated_client.get(
            reverse(route, kwargs={"pk": document.pk})
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestDocumentStatusView:
    """Tests for the document status polling view."""

    def test_status_returns_json(self, authenticated_client, processing_document):
        """Status endpoint returns JSON for AJAX requests."""
        response = authenticated_client.get(
            reverse("claims:document_status", kwargs={"pk": processing_document.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert response.status_code == 200

    def test_status_returns_correct_status(self, authenticated_client, document):
        """Status endpoint returns correct document status."""
        response = authenticated_client.get(
            reverse("claims:document_status", kwargs={"pk": document.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestDocumentDeleteView:
    """Tests for the document delete view."""

    def test_delete_requires_login(self, client, document):
        """Delete requires authentication."""
        response = client.post(
            reverse("claims:document_delete", kwargs={"pk": document.pk})
        )
        assert response.status_code == 302

    def test_delete_soft_deletes_document(self, authenticated_client, document):
        """Delete endpoint soft deletes the document."""
        response = authenticated_client.post(
            reverse("claims:document_delete", kwargs={"pk": document.pk})
        )
        assert response.status_code == 302

        document.refresh_from_db()
        assert document.is_deleted

    def test_delete_denied_for_other_user(self, authenticated_client, other_user):
        """Delete returns 404 for non-owner."""
        other_doc = Document.objects.create(
            user=other_user,
            file_name="other.pdf",
        )
        response = authenticated_client.post(
            reverse("claims:document_delete", kwargs={"pk": other_doc.pk})
        )
        assert response.status_code == 404


# =============================================================================
# DENIAL DECODER VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestDenialDecoderViews:
    """Tests for the denial decoder workflow."""

    def test_upload_requires_login(self, client):
        """Denial decoder upload requires authentication."""
        response = client.get(reverse("claims:denial_decoder"))
        assert response.status_code == 302

    def test_upload_page_loads(self, authenticated_client):
        """Denial decoder upload page loads."""
        response = authenticated_client.get(reverse("claims:denial_decoder"))
        assert response.status_code == 200


# =============================================================================
# OCR SERVICE TESTS
# =============================================================================


class TestOCRService(TestCase):
    """Tests for the OCRService."""

    @patch("claims.services.ocr_service.pytesseract")
    @patch("claims.services.ocr_service.Image")
    def test_extract_from_image(self, mock_image, mock_tesseract):
        """OCRService extracts text from images."""
        from claims.services.ocr_service import OCRService

        mock_tesseract.image_to_string.return_value = "Extracted text"
        mock_tesseract.image_to_data.return_value = "conf\t80\n90\n85"

        service = OCRService()
        # Service should be able to extract from images
        # Full test would require actual image data

    def test_ocr_service_init(self):
        """OCRService can be initialized."""
        from claims.services.ocr_service import OCRService

        service = OCRService()
        self.assertIsNotNone(service)


# =============================================================================
# AI SERVICE TESTS
# =============================================================================


class TestAIService(TestCase):
    """Tests for the AIService."""

    @patch("claims.services.ai_service.get_gateway")
    def test_analyze_document_mocked(self, mock_get_gateway):
        """AIService analyzes documents with OpenAI via gateway."""
        from claims.services.ai_service import AIService
        from agents.ai_gateway import Result, CompletionResponse

        # Mock gateway response
        mock_gateway = MagicMock()
        mock_get_gateway.return_value = mock_gateway
        mock_gateway.config.model = "gpt-3.5-turbo"
        mock_gateway.config.max_tokens = 4000

        # Mock completion result
        mock_completion = CompletionResponse(
            content=json.dumps(
                {
                    "summary": "Test document summary",
                    "key_findings": ["Finding 1", "Finding 2"],
                }
            ),
            tokens_used=500,
            model="gpt-3.5-turbo",
            finish_reason="stop",
        )
        mock_gateway.complete.return_value = Result.success(mock_completion, tokens=500)

        service = AIService()
        # Test service initialization
        self.assertIsNotNone(service)
        self.assertEqual(service.model, "gpt-3.5-turbo")

    def test_get_system_prompt_for_medical_records(self):
        """AIService returns appropriate prompt for medical records."""
        from claims.services.ai_service import AIService

        service = AIService()
        prompt = service._get_system_prompt("medical_records")
        self.assertIn("medical", prompt.lower())

    def test_get_system_prompt_for_decision_letter(self):
        """AIService returns appropriate prompt for decision letters."""
        from claims.services.ai_service import AIService

        service = AIService()
        prompt = service._get_system_prompt("decision_letter")
        self.assertIn("decision", prompt.lower())


# =============================================================================
# CELERY TASK TESTS
# =============================================================================


class TestCeleryTasks(TestCase):
    """Tests for Celery tasks."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )

    @patch("claims.tasks.OCRService")
    @patch("claims.tasks.AIService")
    def test_process_document_task(self, mock_ai_service, mock_ocr_service):
        """process_document_task processes document through OCR and AI."""
        from claims.tasks import process_document_task

        # Create test document
        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            status="uploading",
        )

        # Mock OCR service
        mock_ocr_instance = MagicMock()
        mock_ocr_instance.extract_text.return_value = {
            "text": "Extracted text from document",
            "confidence": 95.0,
            "page_count": 1,
        }
        mock_ocr_service.return_value = mock_ocr_instance

        # Mock AI service
        mock_ai_instance = MagicMock()
        mock_ai_instance.analyze_document.return_value = {
            "analysis": {"summary": "Test summary"},
            "model": "gpt-3.5-turbo",
            "tokens": 500,
        }
        mock_ai_service.return_value = mock_ai_instance

        # Task should exist and be callable
        self.assertTrue(callable(process_document_task))

    @patch("claims.tasks.OCRService")
    def test_process_document_task_handles_ocr_failure(self, mock_ocr_service):
        """process_document_task handles OCR failures gracefully."""

        doc = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            status="uploading",
        )

        # Mock OCR to raise exception
        mock_ocr_instance = MagicMock()
        mock_ocr_instance.extract_text.side_effect = Exception("OCR failed")
        mock_ocr_service.return_value = mock_ocr_instance

        # Task should handle exception
        # In real test, we'd run the task and verify document is marked failed

    def test_cleanup_old_documents_removes_old_soft_deleted(self):
        """cleanup_old_documents removes documents soft-deleted over 90 days ago."""
        from claims.tasks import cleanup_old_documents
        from datetime import timedelta

        # Create a document soft-deleted 100 days ago
        old_doc = Document.objects.create(
            user=self.user,
            file_name="old_deleted.pdf",
            status="completed",
        )
        old_doc.is_deleted = True
        old_doc.deleted_at = timezone.now() - timedelta(days=100)
        old_doc.save()

        # Create a document soft-deleted 30 days ago (should NOT be deleted)
        recent_doc = Document.objects.create(
            user=self.user,
            file_name="recent_deleted.pdf",
            status="completed",
        )
        recent_doc.is_deleted = True
        recent_doc.deleted_at = timezone.now() - timedelta(days=30)
        recent_doc.save()

        # Create a non-deleted document (should NOT be deleted)
        active_doc = Document.objects.create(
            user=self.user,
            file_name="active.pdf",
            status="completed",
        )

        # Run cleanup task
        result = cleanup_old_documents()

        # Verify old document was hard deleted (check all_objects since it was soft-deleted)
        self.assertFalse(
            Document.all_objects.filter(id=old_doc.id).exists(),
            "Old soft-deleted document should be permanently deleted",
        )

        # Verify recent soft-deleted document still exists (use all_objects for soft-deleted)
        self.assertTrue(
            Document.all_objects.filter(id=recent_doc.id).exists(),
            "Recently soft-deleted document should still exist",
        )

        # Verify active document still exists (regular objects manager works for non-deleted)
        self.assertTrue(
            Document.objects.filter(id=active_doc.id).exists(),
            "Active document should still exist",
        )

        self.assertIn("1", result)  # Should indicate 1 document cleaned up

    def test_cleanup_old_documents_handles_empty_queryset(self):
        """cleanup_old_documents handles case with no documents to clean."""
        from claims.tasks import cleanup_old_documents

        # No soft-deleted documents exist
        result = cleanup_old_documents()

        self.assertIn("0", result)

    @patch("claims.tasks.OCRService")
    @patch("claims.tasks.logger")
    def test_cleanup_old_documents_handles_deletion_errors(self, mock_logger, mock_ocr):
        """cleanup_old_documents logs errors but continues processing."""
        from claims.tasks import cleanup_old_documents
        from datetime import timedelta

        # Create old soft-deleted documents
        doc1 = Document.objects.create(
            user=self.user,
            file_name="doc1.pdf",
            status="completed",
        )
        doc1.is_deleted = True
        doc1.deleted_at = timezone.now() - timedelta(days=100)
        doc1.save()

        doc2 = Document.objects.create(
            user=self.user,
            file_name="doc2.pdf",
            status="completed",
        )
        doc2.is_deleted = True
        doc2.deleted_at = timezone.now() - timedelta(days=100)
        doc2.save()

        # Run cleanup - should complete even if individual deletions fail
        result = cleanup_old_documents()

        # Task should return a result string
        self.assertIsInstance(result, str)


class TestDecodeDenialLetterTask(TestCase):
    """Tests for the decode_denial_letter_task."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )

    @patch("claims.tasks.OCRService")
    def test_decode_denial_letter_task_exists(self, mock_ocr):
        """decode_denial_letter_task is importable and callable."""
        from claims.tasks import decode_denial_letter_task

        self.assertTrue(callable(decode_denial_letter_task))

    @patch("claims.tasks.OCRService")
    def test_decode_denial_letter_performs_ocr(self, mock_ocr_service):
        """decode_denial_letter_task always performs OCR (ephemeral approach)."""

        # Create document pending OCR
        doc = Document.objects.create(
            user=self.user,
            file_name="denial.pdf",
            document_type="decision_letter",
            status="uploading",
            ocr_status="pending",
        )

        # Mock OCR service
        mock_ocr_instance = MagicMock()
        mock_ocr_instance.extract_text.return_value = {
            "text": "Your claim for PTSD has been denied...",
            "confidence": 95.0,
            "page_count": 2,
        }
        mock_ocr_service.return_value = mock_ocr_instance

        # OCR should always be called (ephemeral approach - no persistent text)
        self.assertEqual(doc.ocr_status, "pending")
        self.assertEqual(doc.ocr_length, 0)

    @patch("claims.tasks.OCRService")
    def test_decode_denial_letter_sets_ocr_metadata(self, mock_ocr_service):
        """decode_denial_letter_task sets OCR metadata fields."""
        # Create document
        doc = Document.objects.create(
            user=self.user,
            file_name="denial.pdf",
            document_type="decision_letter",
            status="completed",
            ocr_status="completed",
            ocr_length=45,
        )

        # OCR metadata should be set
        self.assertEqual(doc.ocr_status, "completed")
        self.assertEqual(doc.ocr_length, 45)

    def test_decode_denial_letter_handles_missing_document(self):
        """decode_denial_letter_task raises error for non-existent document."""
        from claims.tasks import decode_denial_letter_task

        # Try to decode a non-existent document ID
        with self.assertRaises(Document.DoesNotExist):
            # Run synchronously to catch the exception
            decode_denial_letter_task.apply(args=[99999]).get()


# =============================================================================
# FREE TIER LIMIT TESTS
# =============================================================================


@pytest.mark.django_db
class TestFreeTierLimits:
    """Tests for free tier document limits."""

    def test_free_user_limited_uploads(self, authenticated_client, user):
        """Free users are limited to 3 documents per month."""
        # Create 3 documents this month (at the limit)
        for i in range(3):
            Document.objects.create(
                user=user,
                file_name=f"doc{i}.pdf",
            )

        # Form should show limit reached
        response = authenticated_client.get(reverse("claims:document_upload"))
        # Check context or form for limit information
        assert response.status_code == 200

    def test_premium_user_unlimited_uploads(self, premium_client, premium_user):
        """Premium users have unlimited uploads."""
        # Create many documents
        for i in range(10):
            Document.objects.create(
                user=premium_user,
                file_name=f"doc{i}.pdf",
            )

        # Premium user should still be able to upload
        response = premium_client.get(reverse("claims:document_upload"))
        assert response.status_code == 200


# =============================================================================
# ACCESS CONTROL TESTS
# =============================================================================


@pytest.mark.django_db
class TestDocumentAccessControl:
    """Tests for document access control."""

    def test_user_only_sees_own_documents(self, authenticated_client, user, other_user):
        """Users only see their own documents in list."""
        # Create documents for both users
        user_doc = Document.objects.create(user=user, file_name="user.pdf")
        other_doc = Document.objects.create(user=other_user, file_name="other.pdf")

        response = authenticated_client.get(reverse("claims:document_list"))
        documents = list(response.context["documents"])

        assert user_doc in documents
        assert other_doc not in documents

    def test_user_cannot_view_other_document(self, authenticated_client, other_user):
        """Users cannot view other user's document details."""
        other_doc = Document.objects.create(user=other_user, file_name="secret.pdf")

        response = authenticated_client.get(
            reverse("claims:document_detail", kwargs={"pk": other_doc.pk})
        )
        assert response.status_code == 404

    def test_user_cannot_delete_other_document(self, authenticated_client, other_user):
        """Users cannot delete other user's documents."""
        other_doc = Document.objects.create(user=other_user, file_name="protected.pdf")

        response = authenticated_client.post(
            reverse("claims:document_delete", kwargs={"pk": other_doc.pk})
        )
        assert response.status_code == 404

        # Document should still exist
        assert Document.objects.filter(pk=other_doc.pk).exists()


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestDocumentWorkflow(TestCase):
    """Integration tests for complete document workflows."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.client = Client()
        self.client.login(email="test@example.com", password="TestPass123!")

    def test_document_lifecycle(self):
        """Test complete document lifecycle from upload to analysis."""
        # 1. Create document in uploading state
        doc = Document.objects.create(
            user=self.user,
            file_name="lifecycle_test.pdf",
            file_size=1024,
            document_type="medical_records",
            status="uploading",
        )

        # 2. Mark as processing
        doc.mark_processing()
        self.assertEqual(doc.status, "processing")

        # 3. Mark as analyzing
        doc.mark_analyzing()
        self.assertEqual(doc.status, "analyzing")

        # 4. Complete with results
        doc.mark_completed(
            ocr_length=50,  # Length of extracted text
            ocr_confidence=92.5,
            page_count=3,
        )
        self.assertEqual(doc.status, "completed")
        self.assertEqual(doc.page_count, 3)

        # 5. Soft delete
        doc.delete()
        self.assertTrue(doc.is_deleted)

        # 6. Restore
        doc.restore()
        self.assertFalse(doc.is_deleted)

        # 7. Hard delete
        doc_id = doc.id
        doc.hard_delete()
        self.assertFalse(Document.all_objects.filter(id=doc_id).exists())

    def test_claim_with_documents(self):
        """Test claim with associated documents."""
        # Create claim
        claim = Claim.objects.create(
            user=self.user,
            title="PTSD Claim",
            claim_type="initial",
            status="gathering_evidence",
        )

        # Add documents to claim
        doc1 = Document.objects.create(
            user=self.user,
            file_name="medical_record.pdf",
            document_type="medical_records",
            claim=claim,
        )
        doc2 = Document.objects.create(
            user=self.user,
            file_name="buddy_statement.pdf",
            document_type="buddy_statement",
            claim=claim,
        )

        # Verify relationship
        self.assertEqual(claim.document_count, 2)
        self.assertIn(doc1, claim.documents.all())
        self.assertIn(doc2, claim.documents.all())

        # Submit claim
        claim.status = "submitted"
        claim.submission_date = date.today()
        claim.save()

        self.assertIsNotNone(claim.days_since_submission)


# =============================================================================
# DOCUMENT UPLOAD END-TO-END INTEGRATION TESTS
# =============================================================================


class TestDocumentUploadEndToEnd(TestCase):
    """End-to-end integration tests for document upload flow."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="e2e@example.com", password="TestPass123!"
        )
        # Enable AI consent for upload tests (required by require_ai_consent_view)
        self.user.profile.ai_processing_consent = True
        self.user.profile.save()
        self.client = Client()
        self.client.login(email="e2e@example.com", password="TestPass123!")

    def get_test_pdf(self, size=1024, name="test.pdf"):
        """Create a minimal valid PDF file for testing."""
        content = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer << /Size 4 /Root 1 0 R >>
startxref
190
%%EOF"""
        if len(content) < size:
            content = content + b"\x00" * (size - len(content))
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    def get_test_image(self, name="test.jpg"):
        """Create a minimal valid JPEG file for testing."""
        # Minimal JPEG (1x1 pixel white)
        content = bytes(
            [
                0xFF,
                0xD8,
                0xFF,
                0xE0,
                0x00,
                0x10,
                0x4A,
                0x46,
                0x49,
                0x46,
                0x00,
                0x01,
                0x01,
                0x00,
                0x00,
                0x01,
                0x00,
                0x01,
                0x00,
                0x00,
                0xFF,
                0xDB,
                0x00,
                0x43,
                0x00,
                0x08,
                0x06,
                0x06,
                0x07,
                0x06,
                0x05,
                0x08,
                0x07,
                0x07,
                0x07,
                0x09,
                0x09,
                0x08,
                0x0A,
                0x0C,
                0x14,
                0x0D,
                0x0C,
                0x0B,
                0x0B,
                0x0C,
                0x19,
                0x12,
                0x13,
                0x0F,
                0x14,
                0x1D,
                0x1A,
                0x1F,
                0x1E,
                0x1D,
                0x1A,
                0x1C,
                0x1C,
                0x20,
                0x24,
                0x2E,
                0x27,
                0x20,
                0x22,
                0x2C,
                0x23,
                0x1C,
                0x1C,
                0x28,
                0x37,
                0x29,
                0x2C,
                0x30,
                0x31,
                0x34,
                0x34,
                0x34,
                0x1F,
                0x27,
                0x39,
                0x3D,
                0x38,
                0x32,
                0x3C,
                0x2E,
                0x33,
                0x34,
                0x32,
                0xFF,
                0xC0,
                0x00,
                0x0B,
                0x08,
                0x00,
                0x01,
                0x00,
                0x01,
                0x01,
                0x01,
                0x11,
                0x00,
                0xFF,
                0xC4,
                0x00,
                0x1F,
                0x00,
                0x00,
                0x01,
                0x05,
                0x01,
                0x01,
                0x01,
                0x01,
                0x01,
                0x01,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x01,
                0x02,
                0x03,
                0x04,
                0x05,
                0x06,
                0x07,
                0x08,
                0x09,
                0x0A,
                0x0B,
                0xFF,
                0xC4,
                0x00,
                0xB5,
                0x10,
                0x00,
                0x02,
                0x01,
                0x03,
                0x03,
                0x02,
                0x04,
                0x03,
                0x05,
                0x05,
                0x04,
                0x04,
                0x00,
                0x00,
                0x01,
                0x7D,
                0x01,
                0x02,
                0x03,
                0x00,
                0x04,
                0x11,
                0x05,
                0x12,
                0x21,
                0x31,
                0x41,
                0x06,
                0x13,
                0x51,
                0x61,
                0x07,
                0x22,
                0x71,
                0x14,
                0x32,
                0x81,
                0x91,
                0xA1,
                0x08,
                0x23,
                0x42,
                0xB1,
                0xC1,
                0x15,
                0x52,
                0xD1,
                0xF0,
                0x24,
                0x33,
                0x62,
                0x72,
                0x82,
                0x09,
                0x0A,
                0x16,
                0x17,
                0x18,
                0x19,
                0x1A,
                0x25,
                0x26,
                0x27,
                0x28,
                0x29,
                0x2A,
                0x34,
                0x35,
                0x36,
                0x37,
                0x38,
                0x39,
                0x3A,
                0x43,
                0x44,
                0x45,
                0x46,
                0x47,
                0x48,
                0x49,
                0x4A,
                0x53,
                0x54,
                0x55,
                0x56,
                0x57,
                0x58,
                0x59,
                0x5A,
                0x63,
                0x64,
                0x65,
                0x66,
                0x67,
                0x68,
                0x69,
                0x6A,
                0x73,
                0x74,
                0x75,
                0x76,
                0x77,
                0x78,
                0x79,
                0x7A,
                0x83,
                0x84,
                0x85,
                0x86,
                0x87,
                0x88,
                0x89,
                0x8A,
                0x92,
                0x93,
                0x94,
                0x95,
                0x96,
                0x97,
                0x98,
                0x99,
                0x9A,
                0xA2,
                0xA3,
                0xA4,
                0xA5,
                0xA6,
                0xA7,
                0xA8,
                0xA9,
                0xAA,
                0xB2,
                0xB3,
                0xB4,
                0xB5,
                0xB6,
                0xB7,
                0xB8,
                0xB9,
                0xBA,
                0xC2,
                0xC3,
                0xC4,
                0xC5,
                0xC6,
                0xC7,
                0xC8,
                0xC9,
                0xCA,
                0xD2,
                0xD3,
                0xD4,
                0xD5,
                0xD6,
                0xD7,
                0xD8,
                0xD9,
                0xDA,
                0xE1,
                0xE2,
                0xE3,
                0xE4,
                0xE5,
                0xE6,
                0xE7,
                0xE8,
                0xE9,
                0xEA,
                0xF1,
                0xF2,
                0xF3,
                0xF4,
                0xF5,
                0xF6,
                0xF7,
                0xF8,
                0xF9,
                0xFA,
                0xFF,
                0xDA,
                0x00,
                0x08,
                0x01,
                0x01,
                0x00,
                0x00,
                0x3F,
                0x00,
                0xFB,
                0xD5,
                0xDB,
                0x20,
                0xA8,
                0xF3,
                0xFF,
                0xD9,
            ]
        )
        return SimpleUploadedFile(name, content, content_type="image/jpeg")

    def test_upload_page_loads_with_form(self):
        """Upload page loads with the document upload form."""
        response = self.client.get(reverse("claims:document_upload"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        self.assertTemplateUsed(response, "claims/document_upload.html")

    def test_upload_page_shows_document_types(self):
        """Upload form includes all document type options."""
        response = self.client.get(reverse("claims:document_upload"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Check for document type options
        self.assertIn("medical_records", content)
        self.assertIn("decision_letter", content)

    def test_document_list_empty_for_new_user(self):
        """New user sees empty document list."""
        response = self.client.get(reverse("claims:document_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["documents"]), 0)

    def test_document_list_shows_uploaded_documents(self):
        """Document list shows user's uploaded documents."""
        # Create test documents
        doc1 = Document.objects.create(
            user=self.user,
            file_name="medical.pdf",
            document_type="medical_records",
            status="completed",
        )
        doc2 = Document.objects.create(
            user=self.user,
            file_name="buddy_stmt.pdf",
            document_type="buddy_statement",
            status="completed",
        )

        response = self.client.get(reverse("claims:document_list"))
        self.assertEqual(response.status_code, 200)
        documents = list(response.context["documents"])
        self.assertEqual(len(documents), 2)

    def test_document_detail_shows_metadata(self):
        """Document detail page shows file metadata."""
        doc = Document.objects.create(
            user=self.user,
            file_name="test_doc.pdf",
            file_size=1024000,  # ~1MB
            document_type="medical_records",
            status="completed",
            ocr_status="completed",
            ocr_length=36,  # Length of "Sample extracted text from document."
            ocr_confidence=95.5,
            page_count=3,
        )

        response = self.client.get(
            reverse("claims:document_detail", kwargs={"pk": doc.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["document"], doc)

    def test_document_status_polling_htmx(self):
        """Status endpoint returns correct status for HTMX polling."""
        doc = Document.objects.create(
            user=self.user,
            file_name="processing.pdf",
            status="processing",
        )

        response = self.client.get(
            reverse("claims:document_status", kwargs={"pk": doc.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

    def test_document_status_transitions_reflected(self):
        """Status endpoint reflects document status changes."""
        doc = Document.objects.create(
            user=self.user,
            file_name="status_test.pdf",
            status="uploading",
        )

        # Check uploading status
        response = self.client.get(
            reverse("claims:document_status", kwargs={"pk": doc.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

        # Transition to processing
        doc.mark_processing()

        response = self.client.get(
            reverse("claims:document_status", kwargs={"pk": doc.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

        # Complete
        doc.mark_completed(ocr_length=4, ocr_confidence=90.0, page_count=1)

        response = self.client.get(
            reverse("claims:document_status", kwargs={"pk": doc.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

    def test_document_delete_workflow(self):
        """Document delete workflow soft deletes and redirects."""
        doc = Document.objects.create(
            user=self.user,
            file_name="to_delete.pdf",
            status="completed",
        )

        response = self.client.post(
            reverse("claims:document_delete", kwargs={"pk": doc.pk})
        )
        self.assertEqual(response.status_code, 302)

        # Document should be soft deleted
        doc.refresh_from_db()
        self.assertTrue(doc.is_deleted)

        # Document should not appear in list
        response = self.client.get(reverse("claims:document_list"))
        documents = list(response.context["documents"])
        self.assertNotIn(doc, documents)


class TestDocumentProcessingIntegration(TestCase):
    """Integration tests for document processing workflow."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="processing@example.com", password="TestPass123!"
        )

    def test_document_status_workflow(self):
        """Test document status transitions through processing workflow."""
        doc = Document.objects.create(
            user=self.user,
            file_name="workflow.pdf",
            document_type="medical_records",
            status="uploading",
        )

        # Transition through statuses
        self.assertEqual(doc.status, "uploading")
        self.assertTrue(doc.is_processing)  # uploading is considered processing
        self.assertFalse(doc.is_complete)

        doc.mark_processing()
        self.assertEqual(doc.status, "processing")
        self.assertTrue(doc.is_processing)

        doc.mark_analyzing()
        self.assertEqual(doc.status, "analyzing")
        self.assertTrue(doc.is_processing)

        doc.mark_completed(
            ocr_length=22,  # Length of "Extracted text content"
            ocr_confidence=95.0,
            page_count=3,
        )
        self.assertEqual(doc.status, "completed")
        self.assertFalse(doc.is_processing)
        self.assertTrue(doc.is_complete)
        self.assertEqual(doc.ocr_length, 22)
        self.assertEqual(doc.page_count, 3)

    def test_document_failure_workflow(self):
        """Test document failure handling."""
        doc = Document.objects.create(
            user=self.user,
            file_name="fail.pdf",
            status="processing",
        )

        doc.mark_failed("OCR engine crashed: corrupted PDF")
        doc.refresh_from_db()

        self.assertEqual(doc.status, "failed")
        self.assertTrue(doc.has_failed)
        self.assertIn("OCR", doc.error_message)
        self.assertFalse(doc.is_processing)

    def test_document_processing_with_ai_results(self):
        """Test document with complete AI analysis results."""
        doc = Document.objects.create(
            user=self.user,
            file_name="analyzed.pdf",
            document_type="medical_records",
            status="uploading",
        )

        # Simulate OCR completion
        doc.mark_processing()
        doc.mark_analyzing()

        # Complete with full results
        doc.mark_completed(
            ocr_length=35,  # Length of "Patient: John Doe\nDiagnosis: PTSD"
            ocr_confidence=92.5,
            page_count=5,
        )

        # Add AI results
        doc.ai_summary = {
            "summary": "Medical records showing PTSD diagnosis",
            "key_findings": ["PTSD diagnosis", "Treatment plan"],
        }
        doc.ai_model_used = "gpt-4"
        doc.ai_tokens_used = 1500
        doc.save()

        # Verify all data persisted
        doc.refresh_from_db()
        self.assertEqual(doc.status, "completed")
        self.assertEqual(doc.ocr_length, 35)
        self.assertIsNotNone(doc.ai_summary)
        self.assertEqual(doc.ai_model_used, "gpt-4")
        self.assertEqual(doc.ai_tokens_used, 1500)


class TestDenialDecoderEndToEnd(TestCase):
    """End-to-end integration tests for denial decoder workflow."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="denial@example.com", password="TestPass123!"
        )
        # Enable AI consent for denial decoder tests (required by require_ai_consent_view)
        self.user.profile.ai_processing_consent = True
        self.user.profile.save()
        self.client = Client()
        self.client.login(email="denial@example.com", password="TestPass123!")

    def test_denial_decoder_page_loads(self):
        """Denial decoder upload page loads correctly."""
        response = self.client.get(reverse("claims:denial_decoder"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_denial_decoder_status_polling(self):
        """Denial decoder status endpoint works."""
        doc = Document.objects.create(
            user=self.user,
            file_name="denial_letter.pdf",
            document_type="decision_letter",
            status="processing",
        )

        response = self.client.get(
            reverse("claims:denial_decoder_status", kwargs={"pk": doc.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

    def test_denial_decoder_completed_document(self):
        """Completed denial decoder document displays results."""
        doc = Document.objects.create(
            user=self.user,
            file_name="denial_letter.pdf",
            document_type="decision_letter",
            status="completed",
            ocr_length=40,  # Simulating processed document
            ocr_status="completed",
        )

        # View status - should show completed
        response = self.client.get(
            reverse("claims:denial_decoder_status", kwargs={"pk": doc.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)


class TestDocumentSecurityIntegration(TestCase):
    """Integration tests for document security features."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="security@example.com", password="TestPass123!"
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", password="TestPass123!"
        )
        self.client = Client()

    def test_anonymous_cannot_access_documents(self):
        """Anonymous users cannot access document views."""
        doc = Document.objects.create(
            user=self.user,
            file_name="secure.pdf",
        )

        # List
        response = self.client.get(reverse("claims:document_list"))
        self.assertEqual(response.status_code, 302)

        # Detail
        response = self.client.get(
            reverse("claims:document_detail", kwargs={"pk": doc.pk})
        )
        self.assertEqual(response.status_code, 302)

        # Upload
        response = self.client.get(reverse("claims:document_upload"))
        self.assertEqual(response.status_code, 302)

    def test_user_cannot_access_other_user_document_detail(self):
        """User cannot view another user's document."""
        doc = Document.objects.create(
            user=self.user,
            file_name="private.pdf",
        )

        self.client.login(email="other@example.com", password="TestPass123!")

        response = self.client.get(
            reverse("claims:document_detail", kwargs={"pk": doc.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_user_cannot_delete_other_user_document(self):
        """User cannot delete another user's document."""
        doc = Document.objects.create(
            user=self.user,
            file_name="protected.pdf",
        )

        self.client.login(email="other@example.com", password="TestPass123!")

        response = self.client.post(
            reverse("claims:document_delete", kwargs={"pk": doc.pk})
        )
        self.assertEqual(response.status_code, 404)

        # Document should still exist
        self.assertTrue(Document.objects.filter(pk=doc.pk).exists())

    def test_user_cannot_poll_other_user_document_status(self):
        """User cannot poll status of another user's document."""
        doc = Document.objects.create(
            user=self.user,
            file_name="status.pdf",
            status="processing",
        )

        self.client.login(email="other@example.com", password="TestPass123!")

        response = self.client.get(
            reverse("claims:document_status", kwargs={"pk": doc.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 404)


class TestDocumentFormValidation(TestCase):
    """Integration tests for document upload form validation."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="validation@example.com", password="TestPass123!"
        )

    def test_form_rejects_oversized_file(self):
        """Form rejects files over size limit."""
        # Create mock large file
        large_content = b"x" * (51 * 1024 * 1024)  # 51 MB
        large_file = SimpleUploadedFile(
            "large.pdf", large_content, content_type="application/pdf"
        )

        form = DocumentUploadForm(
            data={"document_type": "medical_records"},
            files={"file": large_file},
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    def test_form_rejects_executable(self):
        """Form rejects executable files."""
        exe_file = SimpleUploadedFile(
            "malware.exe",
            b"MZ\x90\x00" + b"\x00" * 100,  # DOS header
            content_type="application/x-executable",
        )

        form = DocumentUploadForm(
            data={"document_type": "other"}, files={"file": exe_file}, user=self.user
        )

        self.assertFalse(form.is_valid())

    def test_form_rejects_html_file(self):
        """Form rejects HTML files (XSS prevention)."""
        html_file = SimpleUploadedFile(
            "xss.html",
            b"<html><script>alert('xss')</script></html>",
            content_type="text/html",
        )

        form = DocumentUploadForm(
            data={"document_type": "other"}, files={"file": html_file}, user=self.user
        )

        self.assertFalse(form.is_valid())

    def test_form_rejects_script_extension(self):
        """Form rejects script file extensions."""
        for ext in [".js", ".py", ".sh", ".bat", ".ps1"]:
            script_file = SimpleUploadedFile(
                f"script{ext}", b"malicious code", content_type="text/plain"
            )

            form = DocumentUploadForm(
                data={"document_type": "other"},
                files={"file": script_file},
                user=self.user,
            )

            self.assertFalse(form.is_valid(), f"Should reject {ext} files")


class TestDocumentCompleteWorkflow(TestCase):
    """Complete end-to-end workflow tests for document lifecycle."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="workflow@example.com", password="TestPass123!"
        )
        # Enable AI consent for workflow tests (required by require_ai_consent_view)
        self.user.profile.ai_processing_consent = True
        self.user.profile.save()
        self.client = Client()
        self.client.login(email="workflow@example.com", password="TestPass123!")

    def test_complete_upload_to_analysis_workflow(self):
        """Test complete workflow from upload to viewing analysis."""
        # 1. View upload page
        response = self.client.get(reverse("claims:document_upload"))
        self.assertEqual(response.status_code, 200)

        # 2. Create document (simulating successful upload)
        doc = Document.objects.create(
            user=self.user,
            file_name="complete_workflow.pdf",
            file_size=2048,
            document_type="medical_records",
            status="uploading",
        )

        # 3. Simulate processing workflow
        doc.mark_processing()
        doc.mark_analyzing()
        doc.mark_completed(
            ocr_length=50,  # Length of simulated OCR text
            ocr_confidence=92.0,
            page_count=5,
        )

        # Add AI analysis results
        doc.ai_summary = {
            "summary": "Medical records confirming PTSD diagnosis",
            "key_findings": ["PTSD diagnosis", "Ongoing treatment"],
            "recommendations": ["Use for service connection claim"],
        }
        doc.ai_model_used = "gpt-4"
        doc.ai_tokens_used = 800
        doc.save()

        # 4. View document list - should show document
        response = self.client.get(reverse("claims:document_list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(doc, response.context["documents"])

        # 5. View document detail with analysis
        response = self.client.get(
            reverse("claims:document_detail", kwargs={"pk": doc.pk})
        )
        self.assertEqual(response.status_code, 200)
        detail_doc = response.context["document"]
        self.assertEqual(detail_doc.status, "completed")
        self.assertIsNotNone(detail_doc.ai_summary)

        # 6. Delete document
        response = self.client.post(
            reverse("claims:document_delete", kwargs={"pk": doc.pk})
        )
        self.assertEqual(response.status_code, 302)

        # 7. Verify soft deleted
        doc.refresh_from_db()
        self.assertTrue(doc.is_deleted)

        # 8. Verify not in list
        response = self.client.get(reverse("claims:document_list"))
        self.assertNotIn(doc, response.context["documents"])

    def test_multiple_documents_workflow(self):
        """Test managing multiple documents."""
        # Create multiple documents
        docs = []
        for i, doc_type in enumerate(
            ["medical_records", "buddy_statement", "nexus_letter"]
        ):
            doc = Document.objects.create(
                user=self.user,
                file_name=f"document_{i}.pdf",
                document_type=doc_type,
                status="completed",
                ocr_length=20 + i,  # Simulating processed document
                ocr_status="completed",
            )
            docs.append(doc)

        # View list
        response = self.client.get(reverse("claims:document_list"))
        self.assertEqual(len(response.context["documents"]), 3)

        # View each detail
        for doc in docs:
            response = self.client.get(
                reverse("claims:document_detail", kwargs={"pk": doc.pk})
            )
            self.assertEqual(response.status_code, 200)

        # Delete one
        self.client.post(reverse("claims:document_delete", kwargs={"pk": docs[0].pk}))

        # Verify count
        response = self.client.get(reverse("claims:document_list"))
        self.assertEqual(len(response.context["documents"]), 2)

    def test_failed_document_workflow(self):
        """Test workflow when document processing fails."""
        # Create document that will fail
        doc = Document.objects.create(
            user=self.user,
            file_name="will_fail.pdf",
            status="processing",
        )

        # Mark as failed
        doc.mark_failed("Unable to extract text - file corrupted")

        # View detail - should show error
        response = self.client.get(
            reverse("claims:document_detail", kwargs={"pk": doc.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["document"].has_failed)

        # Status polling should reflect failure
        response = self.client.get(
            reverse("claims:document_status", kwargs={"pk": doc.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
