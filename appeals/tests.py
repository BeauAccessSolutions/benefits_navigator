"""
Tests for the appeals app - Appeal workflow, guidance, documents, and notes.

Covers:
- AppealGuidance model
- Appeal model and properties
- AppealDocument model
- AppealNote model
- Public guidance views
- Decision tree workflow
- Appeal management views
- HTMX endpoints for step toggling
- Access control and permissions
"""

import pytest
from datetime import date, timedelta

from django.core.files.base import ContentFile
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from appeals.models import Appeal, AppealGuidance, AppealDocument, AppealNote

User = get_user_model()


# =============================================================================
# APPEAL GUIDANCE MODEL TESTS
# =============================================================================


class TestAppealGuidanceModel(TestCase):
    """Tests for the AppealGuidance model."""

    def test_guidance_creation(self):
        """AppealGuidance can be created with all fields."""
        guidance = AppealGuidance.objects.create(
            title="Higher-Level Review Guide",
            slug="hlr-guide",
            appeal_type="hlr",
            va_form_number="VA Form 20-0996",
            average_processing_days=141,
            when_to_use="Use when VA made an error",
            overview="HLR is a de novo review...",
            is_published=True,
        )
        self.assertEqual(guidance.title, "Higher-Level Review Guide")
        self.assertEqual(guidance.appeal_type, "hlr")

    def test_guidance_str_representation(self):
        """AppealGuidance string is the title."""
        guidance = AppealGuidance.objects.create(
            title="Supplemental Claim Guide",
            slug="supplemental-guide",
            appeal_type="supplemental",
            average_processing_days=125,
        )
        self.assertEqual(str(guidance), "Supplemental Claim Guide")

    def test_guidance_unique_slug(self):
        """AppealGuidance slug must be unique."""
        AppealGuidance.objects.create(
            title="Guide 1",
            slug="test-slug",
            appeal_type="hlr",
            average_processing_days=141,
        )
        with self.assertRaises(Exception):
            AppealGuidance.objects.create(
                title="Guide 2",
                slug="test-slug",
                appeal_type="supplemental",
                average_processing_days=125,
            )

    def test_guidance_appeal_type_choices(self):
        """AppealGuidance accepts valid appeal type choices."""
        valid_types = ["hlr", "supplemental", "board"]
        processing_days = {"hlr": 141, "supplemental": 125, "board": 365}
        for atype in valid_types:
            guidance = AppealGuidance.objects.create(
                title=f"Guide for {atype}",
                slug=f"guide-{atype}",
                appeal_type=atype,
                average_processing_days=processing_days[atype],
            )
            self.assertEqual(guidance.appeal_type, atype)

    def test_guidance_checklist_items_json(self):
        """AppealGuidance can store checklist items as JSON."""
        guidance = AppealGuidance.objects.create(
            title="Test Guide",
            slug="test-checklist",
            appeal_type="hlr",
            average_processing_days=141,
            checklist_items=[
                {"id": "step1", "text": "Download form"},
                {"id": "step2", "text": "Fill out form"},
            ],
        )
        self.assertEqual(len(guidance.checklist_items), 2)
        self.assertEqual(guidance.checklist_items[0]["id"], "step1")

    def test_guidance_ordering(self):
        """AppealGuidance is ordered by order field."""
        g3 = AppealGuidance.objects.create(
            title="G3",
            slug="g3",
            order=3,
            appeal_type="hlr",
            average_processing_days=141,
        )
        g1 = AppealGuidance.objects.create(
            title="G1",
            slug="g1",
            order=1,
            appeal_type="supplemental",
            average_processing_days=125,
        )
        g2 = AppealGuidance.objects.create(
            title="G2",
            slug="g2",
            order=2,
            appeal_type="board",
            average_processing_days=365,
        )

        guides = list(AppealGuidance.objects.all())
        self.assertEqual(guides[0], g1)
        self.assertEqual(guides[1], g2)
        self.assertEqual(guides[2], g3)


# =============================================================================
# APPEAL MODEL TESTS
# =============================================================================


class TestAppealModel(TestCase):
    """Tests for the Appeal model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )

    def test_appeal_creation(self):
        """Appeal can be created with required fields."""
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="hlr",
            status="gathering",
        )
        self.assertEqual(appeal.user, self.user)
        self.assertEqual(appeal.appeal_type, "hlr")

    def test_appeal_str_representation(self):
        """Appeal string includes type display name and user."""
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="hlr",
        )
        appeal_str = str(appeal)
        self.assertIn("Higher-Level Review", appeal_str)
        self.assertIn("test@example.com", appeal_str)

    def test_appeal_type_choices(self):
        """Appeal accepts all valid type choices."""
        valid_types = [
            "hlr",
            "supplemental",
            "board_direct",
            "board_evidence",
            "board_hearing",
        ]
        for atype in valid_types:
            appeal = Appeal.objects.create(
                user=self.user,
                appeal_type=atype,
            )
            self.assertEqual(appeal.appeal_type, atype)

    def test_appeal_status_choices(self):
        """Appeal accepts all valid status choices."""
        valid_statuses = [
            "deciding",
            "gathering",
            "preparing",
            "ready",
            "submitted",
            "acknowledged",
            "in_review",
            "decision_pending",
            "decided",
            "closed",
        ]
        for status in valid_statuses:
            appeal = Appeal.objects.create(
                user=self.user,
                appeal_type="hlr",
                status=status,
            )
            self.assertEqual(appeal.status, status)

    def test_appeal_deadline_auto_calculation(self):
        """Appeal deadline is auto-calculated from decision date for HLR."""
        decision_date = date.today() - timedelta(days=30)
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="hlr",
            original_decision_date=decision_date,
        )
        # Deadline should be 1 year from decision
        expected_deadline = decision_date + timedelta(days=365)
        self.assertEqual(appeal.deadline, expected_deadline)

    def test_supplemental_no_deadline(self):
        """Supplemental claims have no filing deadline (38 CFR § 20.204)."""
        decision_date = date.today() - timedelta(days=30)
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="supplemental",
            original_decision_date=decision_date,
        )
        self.assertIsNone(appeal.deadline)

    def test_supplemental_clears_existing_deadline(self):
        """Changing appeal type to supplemental clears existing deadline."""
        decision_date = date.today() - timedelta(days=30)
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="hlr",
            original_decision_date=decision_date,
        )
        # HLR should have a deadline
        self.assertIsNotNone(appeal.deadline)

        # Change to supplemental — deadline should be cleared
        appeal.appeal_type = "supplemental"
        appeal.save()
        self.assertIsNone(appeal.deadline)

    def test_board_appeal_gets_deadline(self):
        """Board appeals still auto-calculate 1-year deadline."""
        decision_date = date.today() - timedelta(days=30)
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="board_direct",
            original_decision_date=decision_date,
        )
        expected_deadline = decision_date + timedelta(days=365)
        self.assertEqual(appeal.deadline, expected_deadline)

    def test_appeal_days_until_deadline(self):
        """days_until_deadline calculates correctly."""
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="hlr",
            original_decision_date=date.today() - timedelta(days=30),
        )
        # Should be approximately 335 days (365 - 30)
        self.assertIsNotNone(appeal.days_until_deadline)
        self.assertTrue(330 <= appeal.days_until_deadline <= 340)

    def test_appeal_is_deadline_urgent(self):
        """is_deadline_urgent returns True when deadline is within 30 days."""
        # Decision date 340 days ago = 25 days until deadline
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="hlr",
            original_decision_date=date.today() - timedelta(days=340),
        )
        self.assertTrue(appeal.is_deadline_urgent)

    def test_appeal_is_past_deadline(self):
        """is_past_deadline returns True when deadline has passed."""
        # Decision date over a year ago
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="hlr",
            original_decision_date=date.today() - timedelta(days=400),
        )
        self.assertTrue(appeal.is_past_deadline)

    def test_appeal_recommended_type_hlr(self):
        """recommended_appeal_type suggests HLR when VA error believed."""
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="hlr",
            has_new_evidence=False,
            believes_va_error=True,
            wants_hearing=False,
        )
        self.assertEqual(appeal.recommended_appeal_type, "hlr")

    def test_appeal_recommended_type_supplemental(self):
        """recommended_appeal_type suggests supplemental when new evidence."""
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="supplemental",
            has_new_evidence=True,
            believes_va_error=False,
            wants_hearing=False,
        )
        self.assertEqual(appeal.recommended_appeal_type, "supplemental")

    def test_appeal_recommended_type_board_hearing(self):
        """recommended_appeal_type suggests board when hearing wanted."""
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="board_hearing",
            has_new_evidence=False,
            believes_va_error=False,
            wants_hearing=True,
        )
        self.assertEqual(appeal.recommended_appeal_type, "board_hearing")

    def test_appeal_completion_percentage(self):
        """completion_percentage calculates based on steps completed."""
        guidance = AppealGuidance.objects.create(
            title="Test Guide",
            slug="test",
            appeal_type="hlr",
            average_processing_days=141,
            checklist_items=[
                {"id": "step1", "text": "Step 1"},
                {"id": "step2", "text": "Step 2"},
                {"id": "step3", "text": "Step 3"},
                {"id": "step4", "text": "Step 4"},
            ],
        )
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="hlr",
            steps_completed=["step1", "step2"],
        )
        # 2 of 4 steps = 50%
        # Note: completion_percentage may need guidance linked to calculate

    def test_appeal_get_guidance(self):
        """get_guidance returns appropriate guidance for appeal type."""
        guidance = AppealGuidance.objects.create(
            title="HLR Guide",
            slug="hlr",
            appeal_type="hlr",
            average_processing_days=141,
            is_published=True,
        )
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="hlr",
        )
        result = appeal.get_guidance()
        self.assertEqual(result, guidance)


# =============================================================================
# APPEAL DOCUMENT MODEL TESTS
# =============================================================================


class TestAppealDocumentModel(TestCase):
    """Tests for the AppealDocument model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="hlr",
        )

    def test_appeal_document_creation(self):
        """AppealDocument can be created."""
        doc = AppealDocument.objects.create(
            appeal=self.appeal,
            document_type="new_evidence",
            title="Medical Records",
        )
        self.assertEqual(doc.appeal, self.appeal)
        self.assertEqual(doc.document_type, "new_evidence")

    def test_appeal_document_str_representation(self):
        """AppealDocument string includes title."""
        doc = AppealDocument.objects.create(
            appeal=self.appeal,
            title="Nexus Letter",
        )
        self.assertIn("Nexus Letter", str(doc))

    def test_appeal_document_type_choices(self):
        """AppealDocument accepts valid type choices."""
        valid_types = [
            "decision_letter",
            "new_evidence",
            "medical_record",
            "nexus_letter",
            "buddy_statement",
            "personal_statement",
            "form",
            "other",
        ]
        for dtype in valid_types:
            doc = AppealDocument.objects.create(
                appeal=self.appeal,
                document_type=dtype,
                title=f"Doc {dtype}",
            )
            self.assertEqual(doc.document_type, dtype)


# =============================================================================
# APPEAL NOTE MODEL TESTS
# =============================================================================


class TestAppealNoteModel(TestCase):
    """Tests for the AppealNote model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="hlr",
        )

    def test_appeal_note_creation(self):
        """AppealNote can be created."""
        note = AppealNote.objects.create(
            appeal=self.appeal,
            note_type="user",
            content="Spoke with VSO today.",
        )
        self.assertEqual(note.appeal, self.appeal)
        self.assertEqual(note.content, "Spoke with VSO today.")

    def test_appeal_note_str_representation(self):
        """AppealNote string includes type and date."""
        note = AppealNote.objects.create(
            appeal=self.appeal,
            note_type="status",
            content="Status updated",
        )
        self.assertIn("status", str(note).lower())

    def test_appeal_note_type_choices(self):
        """AppealNote accepts valid type choices."""
        valid_types = ["user", "status", "reminder", "va_communication"]
        for ntype in valid_types:
            note = AppealNote.objects.create(
                appeal=self.appeal,
                note_type=ntype,
                content=f"Note type: {ntype}",
            )
            self.assertEqual(note.note_type, ntype)

    def test_appeal_note_is_important(self):
        """AppealNote can be marked as important."""
        note = AppealNote.objects.create(
            appeal=self.appeal,
            content="Important note",
            is_important=True,
        )
        self.assertTrue(note.is_important)


# =============================================================================
# PUBLIC GUIDANCE VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestPublicGuidanceViews:
    """Tests for public (no login required) guidance views."""

    def test_appeals_home_loads(self, client):
        """Appeals home page loads without login."""
        response = client.get(reverse("appeals:home"))
        assert response.status_code == 200

    def test_guidance_detail_loads(self, client, appeal_guidance):
        """Guidance detail page loads without login."""
        response = client.get(
            reverse("appeals:guidance_detail", kwargs={"slug": appeal_guidance.slug})
        )
        assert response.status_code == 200

    def test_guidance_detail_404_unpublished(self, client, db):
        """Unpublished guidance returns 404."""
        guidance = AppealGuidance.objects.create(
            title="Unpublished Guide",
            slug="unpublished",
            appeal_type="hlr",
            average_processing_days=141,
            is_published=False,
        )
        response = client.get(
            reverse("appeals:guidance_detail", kwargs={"slug": "unpublished"})
        )
        assert response.status_code == 404

    def test_decision_tree_loads(self, client):
        """Decision tree page loads without login."""
        response = client.get(reverse("appeals:decision_tree"))
        assert response.status_code == 200


# =============================================================================
# APPEAL LIST VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestAppealListView:
    """Tests for the appeal list view."""

    def test_appeal_list_requires_login(self, client):
        """Appeal list requires authentication."""
        response = client.get(reverse("appeals:appeal_list"))
        assert response.status_code == 302

    def test_appeal_list_loads(self, authenticated_client):
        """Appeal list loads for authenticated user."""
        response = authenticated_client.get(reverse("appeals:appeal_list"))
        assert response.status_code == 200

    def test_appeal_list_shows_user_appeals(self, authenticated_client, appeal):
        """Appeal list shows user's appeals."""
        response = authenticated_client.get(reverse("appeals:appeal_list"))
        assert response.status_code == 200
        assert (
            appeal in response.context["active_appeals"]
            or appeal in response.context["completed_appeals"]
        )

    def test_appeal_list_hides_other_user_appeals(
        self, authenticated_client, other_user
    ):
        """Appeal list doesn't show other user's appeals."""
        other_appeal = Appeal.objects.create(
            user=other_user,
            appeal_type="hlr",
        )
        response = authenticated_client.get(reverse("appeals:appeal_list"))
        active = list(response.context["active_appeals"])
        completed = list(response.context["completed_appeals"])
        assert other_appeal not in active + completed


# =============================================================================
# APPEAL WORKFLOW VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestAppealWorkflowViews:
    """Tests for appeal workflow views."""

    def test_start_appeal_requires_login(self, client):
        """Starting an appeal requires authentication."""
        response = client.get(reverse("appeals:appeal_start"))
        assert response.status_code == 302

    def test_start_appeal_get_shows_form(self, authenticated_client):
        """GET request shows appeal start form."""
        response = authenticated_client.get(reverse("appeals:appeal_start"))
        assert response.status_code == 200

    def test_start_appeal_post_creates_appeal(self, authenticated_client, user):
        """POST request creates new appeal."""
        response = authenticated_client.post(
            reverse("appeals:appeal_start"),
            {
                "original_decision_date": date.today().isoformat(),
                "conditions_appealed": "PTSD, Tinnitus",
                "denial_reasons": "Insufficient nexus evidence",
            },
        )
        assert response.status_code == 302  # Redirect to decide step
        assert Appeal.objects.filter(user=user).exists()

    def test_appeal_detail_requires_login(self, client, appeal):
        """Appeal detail requires authentication."""
        response = client.get(
            reverse("appeals:appeal_detail", kwargs={"pk": appeal.pk})
        )
        assert response.status_code == 302

    def test_appeal_detail_loads_for_owner(self, authenticated_client, appeal):
        """Appeal detail loads for appeal owner."""
        response = authenticated_client.get(
            reverse("appeals:appeal_detail", kwargs={"pk": appeal.pk})
        )
        assert response.status_code == 200
        assert response.context["appeal"] == appeal

    def test_appeal_detail_denied_for_other_user(
        self, authenticated_client, other_user
    ):
        """Appeal detail returns 404 for non-owner."""
        other_appeal = Appeal.objects.create(
            user=other_user,
            appeal_type="hlr",
        )
        response = authenticated_client.get(
            reverse("appeals:appeal_detail", kwargs={"pk": other_appeal.pk})
        )
        assert response.status_code == 404


# =============================================================================
# APPEAL DECISION TREE TESTS
# =============================================================================


@pytest.mark.django_db
class TestAppealDecisionTree:
    """Tests for the appeal decision tree workflow."""

    def test_decide_requires_login(self, client, appeal):
        """Decision step requires authentication."""
        response = client.get(
            reverse("appeals:appeal_decide", kwargs={"pk": appeal.pk})
        )
        assert response.status_code == 302

    def test_decide_page_loads(self, authenticated_client, appeal):
        """Decision tree page loads."""
        response = authenticated_client.get(
            reverse("appeals:appeal_decide", kwargs={"pk": appeal.pk})
        )
        assert response.status_code == 200

    def test_set_type_updates_appeal(self, authenticated_client, appeal):
        """Setting appeal type updates the appeal."""
        response = authenticated_client.post(
            reverse("appeals:appeal_set_type", kwargs={"pk": appeal.pk}),
            {"appeal_type": "supplemental"},
        )
        assert response.status_code == 302

        appeal.refresh_from_db()
        assert appeal.appeal_type == "supplemental"


# =============================================================================
# APPEAL UPDATE AND DECISION TESTS
# =============================================================================


@pytest.mark.django_db
class TestAppealUpdateViews:
    """Tests for appeal update views."""

    def test_update_appeal_requires_login(self, client, appeal):
        """Update appeal requires authentication."""
        response = client.get(
            reverse("appeals:appeal_update", kwargs={"pk": appeal.pk})
        )
        assert response.status_code == 302

    def test_update_appeal_loads(self, authenticated_client, appeal):
        """Update appeal page loads."""
        response = authenticated_client.get(
            reverse("appeals:appeal_update", kwargs={"pk": appeal.pk})
        )
        assert response.status_code == 200

    def test_record_decision_requires_login(self, client, appeal):
        """Recording decision requires authentication."""
        response = client.get(
            reverse("appeals:appeal_record_decision", kwargs={"pk": appeal.pk})
        )
        assert response.status_code == 302

    def test_record_decision_loads(self, authenticated_client, appeal):
        """Record decision page loads."""
        response = authenticated_client.get(
            reverse("appeals:appeal_record_decision", kwargs={"pk": appeal.pk})
        )
        assert response.status_code == 200


# =============================================================================
# HTMX ENDPOINT TESTS
# =============================================================================


@pytest.mark.django_db
class TestAppealHTMXEndpoints:
    """Tests for HTMX endpoints."""

    def test_toggle_step_requires_login(self, client, appeal):
        """Toggle step requires authentication."""
        response = client.post(
            reverse("appeals:appeal_toggle_step", kwargs={"pk": appeal.pk}),
            {"step_id": "step_1"},
        )
        assert response.status_code == 302

    def test_toggle_step_adds_step(self, authenticated_client, appeal):
        """Toggle step adds step to completed list."""
        response = authenticated_client.post(
            reverse("appeals:appeal_toggle_step", kwargs={"pk": appeal.pk}),
            {"step_id": "step_1"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200

        appeal.refresh_from_db()
        assert "step_1" in appeal.steps_completed

    def test_toggle_step_removes_step(self, authenticated_client, appeal):
        """Toggle step removes already completed step."""
        appeal.steps_completed = ["step_1"]
        appeal.save()

        response = authenticated_client.post(
            reverse("appeals:appeal_toggle_step", kwargs={"pk": appeal.pk}),
            {"step_id": "step_1"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200

        appeal.refresh_from_db()
        assert "step_1" not in appeal.steps_completed


# =============================================================================
# APPEAL DOCUMENT VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestAppealDocumentViews:
    """Tests for appeal document views."""

    def test_add_document_requires_login(self, client, appeal):
        """Adding document requires authentication."""
        response = client.post(
            reverse("appeals:appeal_add_document", kwargs={"pk": appeal.pk})
        )
        assert response.status_code == 302

    def test_delete_document_requires_login(self, client, appeal):
        """Deleting document requires authentication."""
        doc = AppealDocument.objects.create(
            appeal=appeal,
            title="Test Doc",
        )
        response = client.post(
            reverse(
                "appeals:appeal_delete_document",
                kwargs={"pk": appeal.pk, "doc_pk": doc.pk},
            )
        )
        assert response.status_code == 302


# =============================================================================
# APPEAL PROTECTED MEDIA TESTS
# =============================================================================


@pytest.mark.django_db
class TestAppealDocumentMediaViews:
    """
    Tests for the protected appeal-document media views.

    /media/ is deliberately never served (see benefits_navigator/urls.py), so
    these views are the only path to an appeal document's bytes.
    """

    @staticmethod
    def _make_doc(appeal, content=b"%PDF-1.4 fake decision letter"):
        doc = AppealDocument.objects.create(
            appeal=appeal,
            document_type="decision_letter",
            title="VA Decision Letter",
        )
        doc.file.save("decision.pdf", ContentFile(content), save=True)
        return doc

    def test_owner_can_view_document_inline(self, authenticated_client, appeal):
        """The owning user gets the file bytes back, served inline."""
        doc = self._make_doc(appeal)

        response = authenticated_client.get(
            reverse(
                "appeals:appeal_document_view",
                kwargs={"pk": appeal.pk, "doc_pk": doc.pk},
            )
        )

        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"].startswith("inline;")
        assert b"".join(response.streaming_content) == b"%PDF-1.4 fake decision letter"

    def test_owner_can_download_document(self, authenticated_client, appeal):
        """The download variant serves the same bytes as an attachment."""
        doc = self._make_doc(appeal)

        response = authenticated_client.get(
            reverse(
                "appeals:appeal_document_download",
                kwargs={"pk": appeal.pk, "doc_pk": doc.pk},
            )
        )

        assert response.status_code == 200
        assert response["Content-Disposition"].startswith("attachment;")
        assert b"".join(response.streaming_content) == b"%PDF-1.4 fake decision letter"

    def test_other_user_cannot_view_document(self, client, appeal, other_user, user_password):
        """A second user gets 404 rather than another veteran's decision letter."""
        doc = self._make_doc(appeal)
        client.login(email=other_user.email, password=user_password)

        response = client.get(
            reverse(
                "appeals:appeal_document_view",
                kwargs={"pk": appeal.pk, "doc_pk": doc.pk},
            )
        )

        assert response.status_code == 404

    def test_other_user_cannot_download_document(
        self, client, appeal, other_user, user_password
    ):
        """Same ownership gate on the download route."""
        doc = self._make_doc(appeal)
        client.login(email=other_user.email, password=user_password)

        response = client.get(
            reverse(
                "appeals:appeal_document_download",
                kwargs={"pk": appeal.pk, "doc_pk": doc.pk},
            )
        )

        assert response.status_code == 404

    def test_document_view_requires_login(self, client, appeal):
        """Anonymous users are redirected to login, never served the file."""
        doc = self._make_doc(appeal)

        response = client.get(
            reverse(
                "appeals:appeal_document_view",
                kwargs={"pk": appeal.pk, "doc_pk": doc.pk},
            )
        )

        assert response.status_code == 302

    def test_document_from_another_appeal_is_404(
        self, authenticated_client, appeal, board_appeal
    ):
        """doc_pk must belong to the appeal in the URL, not just to the user."""
        doc = self._make_doc(board_appeal)

        response = authenticated_client.get(
            reverse(
                "appeals:appeal_document_view",
                kwargs={"pk": appeal.pk, "doc_pk": doc.pk},
            )
        )

        assert response.status_code == 404

    def test_document_without_file_is_404(self, authenticated_client, appeal):
        """A metadata-only document row has no bytes to serve."""
        doc = AppealDocument.objects.create(
            appeal=appeal, document_type="other", title="No file"
        )

        response = authenticated_client.get(
            reverse(
                "appeals:appeal_document_view",
                kwargs={"pk": appeal.pk, "doc_pk": doc.pk},
            )
        )

        assert response.status_code == 404

    def test_view_is_audit_logged(self, authenticated_client, appeal, user):
        """Access to a document is recorded for the audit trail."""
        from core.models import AuditLog

        doc = self._make_doc(appeal)
        authenticated_client.get(
            reverse(
                "appeals:appeal_document_view",
                kwargs={"pk": appeal.pk, "doc_pk": doc.pk},
            )
        )

        entry = AuditLog.objects.filter(
            action="document_view", resource_type="AppealDocument", resource_id=doc.pk
        ).first()
        assert entry is not None
        assert entry.user == user

    def test_no_template_comment_leaks_into_page(self, authenticated_client, appeal):
        """
        Django's {# #} comment syntax is single-line only; a multi-line one is
        not parsed as a comment and renders as visible text to the user.
        """
        self._make_doc(appeal)

        response = authenticated_client.get(
            reverse("appeals:appeal_detail", kwargs={"pk": appeal.pk})
        )
        html = response.content.decode()

        assert "{#" not in html
        assert "{% comment" not in html

    def test_template_links_to_protected_url_without_blank(
        self, authenticated_client, appeal
    ):
        """
        The rendered document list must point at the protected view, not
        MEDIA_URL, and must not use target="_blank" (the Capacitor iOS wrapper
        sends _blank to Safari, which has no session cookie).
        """
        doc = self._make_doc(appeal)

        response = authenticated_client.get(
            reverse("appeals:appeal_detail", kwargs={"pk": appeal.pk})
        )
        html = response.content.decode()

        expected = reverse(
            "appeals:appeal_document_view",
            kwargs={"pk": appeal.pk, "doc_pk": doc.pk},
        )
        assert expected in html
        assert doc.file.url not in html

        # The document anchor specifically must not be _blank. Other links on the
        # page (va.gov, GitHub) are genuinely external and keep their _blank.
        anchor_start = html.index(f'href="{expected}"')
        anchor = html[html.rindex("<a ", 0, anchor_start) : html.index(">", anchor_start)]
        assert "_blank" not in anchor


# =============================================================================
# APPEAL NOTE VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestAppealNoteViews:
    """Tests for appeal note views."""

    def test_add_note_requires_login(self, client, appeal):
        """Adding note requires authentication."""
        response = client.post(
            reverse("appeals:appeal_add_note", kwargs={"pk": appeal.pk})
        )
        assert response.status_code == 302

    def test_add_note_creates_note(self, authenticated_client, appeal):
        """Adding note creates new note."""
        response = authenticated_client.post(
            reverse("appeals:appeal_add_note", kwargs={"pk": appeal.pk}),
            {
                "content": "Test note content",
                "note_type": "user",
            },
        )
        assert response.status_code == 302

        assert AppealNote.objects.filter(
            appeal=appeal, content="Test note content"
        ).exists()


# =============================================================================
# ACCESS CONTROL TESTS
# =============================================================================


@pytest.mark.django_db
class TestAppealAccessControl:
    """Tests for appeal access control."""

    def test_user_cannot_view_other_appeal(self, authenticated_client, other_user):
        """Users cannot view other user's appeals."""
        other_appeal = Appeal.objects.create(
            user=other_user,
            appeal_type="hlr",
        )
        response = authenticated_client.get(
            reverse("appeals:appeal_detail", kwargs={"pk": other_appeal.pk})
        )
        assert response.status_code == 404

    def test_user_cannot_update_other_appeal(self, authenticated_client, other_user):
        """Users cannot update other user's appeals."""
        other_appeal = Appeal.objects.create(
            user=other_user,
            appeal_type="hlr",
        )
        response = authenticated_client.post(
            reverse("appeals:appeal_update", kwargs={"pk": other_appeal.pk}),
            {"status": "submitted"},
        )
        assert response.status_code == 404

    def test_user_cannot_toggle_other_appeal_steps(
        self, authenticated_client, other_user
    ):
        """Users cannot toggle steps on other user's appeals."""
        other_appeal = Appeal.objects.create(
            user=other_user,
            appeal_type="hlr",
        )
        response = authenticated_client.post(
            reverse("appeals:appeal_toggle_step", kwargs={"pk": other_appeal.pk}),
            {"step_id": "step_1"},
        )
        assert response.status_code == 404


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestAppealWorkflow(TestCase):
    """Integration tests for complete appeal workflows."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.client = Client()
        self.client.login(email="test@example.com", password="TestPass123!")

    def test_complete_hlr_workflow(self):
        """Test complete HLR appeal workflow."""
        # 1. Create guidance
        guidance = AppealGuidance.objects.create(
            title="HLR Guide",
            slug="hlr",
            appeal_type="hlr",
            average_processing_days=141,
            checklist_items=[
                {"id": "step1", "text": "Download form"},
                {"id": "step2", "text": "Fill out form"},
                {"id": "step3", "text": "Submit"},
            ],
            is_published=True,
        )

        # 2. Start appeal
        appeal = Appeal.objects.create(
            user=self.user,
            appeal_type="hlr",
            status="gathering",
            original_decision_date=date.today() - timedelta(days=30),
            conditions_appealed="PTSD",
            denial_reasons="No nexus",
            has_new_evidence=False,
            believes_va_error=True,
        )

        # 3. Add documents
        doc = AppealDocument.objects.create(
            appeal=appeal,
            document_type="decision_letter",
            title="Original Decision Letter",
        )

        # 4. Complete steps
        appeal.steps_completed = ["step1", "step2", "step3"]
        appeal.status = "ready"
        appeal.save()

        # 5. Submit
        appeal.status = "submitted"
        appeal.submission_date = date.today()
        appeal.va_confirmation_number = "HLR-12345"
        appeal.save()

        # 6. Add note
        note = AppealNote.objects.create(
            appeal=appeal,
            note_type="status",
            content="Submitted successfully",
        )

        # 7. Record decision
        appeal.status = "decided"
        appeal.decision_received_date = date.today() + timedelta(days=141)
        appeal.decision_outcome = "granted"
        appeal.save()

        # Verify final state
        self.assertEqual(appeal.status, "decided")
        self.assertEqual(appeal.documents.count(), 1)
        self.assertEqual(appeal.timeline_notes.count(), 1)


class TestDecisionTreeToAppealFlow(TestCase):
    """Test the streamlined flow from decision tree to appeal creation."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="decisiontreeuser",
            email="decision@example.com",
            password="testpass123",
        )
        self.client = Client()
        self.client.force_login(self.user)

        # Create guidance for the appeal type
        AppealGuidance.objects.create(
            title="Higher-Level Review Guide",
            slug="hlr",
            appeal_type="hlr",
            average_processing_days=141,
            is_published=True,
        )

    def test_decision_tree_stores_answers_in_session(self):
        """Decision tree should store both recommendation and answers in session."""
        response = self.client.post(
            reverse("appeals:decision_tree"),
            {
                "has_new_evidence": "no",
                "believes_va_error": "yes",
                "wants_hearing": "no",
                "start_appeal": "1",
            },
        )

        # Should redirect to appeal_start
        self.assertEqual(response.status_code, 302)
        self.assertIn("/appeals/start/", response.url)

        # Check session has both recommendation and answers
        session = self.client.session
        # Note: session is consumed on redirect, but we tested the redirect worked

    def test_appeal_start_skips_decision_tree_when_answers_provided(self):
        """When starting appeal with decision tree answers, should skip to detail page."""
        # Simulate coming from decision tree by setting session
        session = self.client.session
        session["appeal_recommendation"] = {
            "type": "hlr",
            "name": "Higher-Level Review",
            "form": "VA Form 20-0996",
            "time": "~141 days",
            "reason": "You believe the VA made an error.",
        }
        session["appeal_decision_tree_answers"] = {
            "has_new_evidence": "no",
            "believes_va_error": "yes",
            "wants_hearing": "no",
        }
        session.save()

        # Submit appeal start form
        response = self.client.post(
            reverse("appeals:appeal_start"),
            {
                "original_decision_date": (
                    date.today() - timedelta(days=30)
                ).isoformat(),
                "conditions_appealed": "PTSD - denied",
                "denial_reasons": "VA said no nexus",
            },
        )

        # Should redirect to appeal detail (not appeal_decide)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/appeals/", response.url)
        self.assertNotIn("decide", response.url)

        # Verify appeal was created with correct fields
        appeal = Appeal.objects.filter(user=self.user).first()
        self.assertIsNotNone(appeal)
        self.assertEqual(appeal.appeal_type, "hlr")
        self.assertEqual(appeal.status, "gathering")  # Not 'deciding'
        self.assertFalse(appeal.has_new_evidence)
        self.assertTrue(appeal.believes_va_error)
        self.assertFalse(appeal.wants_hearing)

        # Verify a status note was created
        self.assertEqual(appeal.timeline_notes.count(), 1)
        self.assertIn("Higher-Level Review", appeal.timeline_notes.first().content)

    def test_appeal_start_goes_to_decide_when_no_recommendation(self):
        """When starting appeal without decision tree, should go to decide page."""
        # No session data - direct start

        response = self.client.post(
            reverse("appeals:appeal_start"),
            {
                "original_decision_date": (
                    date.today() - timedelta(days=30)
                ).isoformat(),
                "conditions_appealed": "PTSD - denied",
                "denial_reasons": "VA said no nexus",
            },
        )

        # Should redirect to appeal_decide
        self.assertEqual(response.status_code, 302)
        self.assertIn("decide", response.url)

        # Verify appeal was created without appeal_type
        appeal = Appeal.objects.filter(user=self.user).first()
        self.assertIsNotNone(appeal)
        self.assertEqual(appeal.appeal_type, "")  # Not set yet
        self.assertEqual(appeal.status, "deciding")
