"""
Tests for the documentation app.

Covers:
- DocumentCategory model
- VAForm model
- CPExamGuideCondition model
- LegalReference model
- Search functionality
- Views and templates
"""

import pytest
from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from documentation.models import (
    DocumentCategory,
    VAForm,
    CPExamGuideCondition,
    LegalReference,
)

User = get_user_model()


# =============================================================================
# MODEL TESTS
# =============================================================================


class TestDocumentCategoryModel(TestCase):
    """Tests for the DocumentCategory model."""

    def test_category_creation(self):
        """DocumentCategory can be created with all fields."""
        category = DocumentCategory.objects.create(
            name="Disability Claims",
            slug="disability-claims",
            description="Forms for disability claims.",
            order=1,
        )
        self.assertEqual(category.name, "Disability Claims")
        self.assertEqual(category.slug, "disability-claims")
        self.assertTrue(category.is_active)

    def test_category_str_representation(self):
        """DocumentCategory string is the name."""
        category = DocumentCategory.objects.create(
            name="Test Category", slug="test-category"
        )
        self.assertEqual(str(category), "Test Category")

    def test_category_ordering(self):
        """Categories are ordered by order field then name."""
        cat1 = DocumentCategory.objects.create(name="B Category", slug="b-cat", order=2)
        cat2 = DocumentCategory.objects.create(name="A Category", slug="a-cat", order=1)
        cat3 = DocumentCategory.objects.create(name="C Category", slug="c-cat", order=1)

        categories = list(DocumentCategory.objects.all())
        self.assertEqual(categories[0], cat2)  # order=1, A
        self.assertEqual(categories[1], cat3)  # order=1, C
        self.assertEqual(categories[2], cat1)  # order=2


class TestVAFormModel(TestCase):
    """Tests for the VAForm model."""

    def setUp(self):
        self.category = DocumentCategory.objects.create(
            name="Test Category", slug="test-cat"
        )

    def test_form_creation(self):
        """VAForm can be created with all fields."""
        form = VAForm.objects.create(
            form_number="21-526EZ",
            title="Application for Disability Compensation",
            description="Primary disability claim form",
            instructions="Complete all sections...",
            official_url="https://www.va.gov/find-forms/about-form-21-526ez/",
            workflow_stages=["initial_claim"],
            last_updated=date.today(),
            category=self.category,
        )
        self.assertEqual(form.form_number, "21-526EZ")
        self.assertTrue(form.is_active)

    def test_form_str_representation(self):
        """VAForm string includes number and title."""
        form = VAForm.objects.create(
            form_number="21-4138",
            title="Statement in Support of Claim",
            description="Test",
            instructions="Test",
            official_url="https://va.gov",
            last_updated=date.today(),
        )
        self.assertEqual(str(form), "21-4138: Statement in Support of Claim")

    def test_form_unique_number(self):
        """VAForm form_number must be unique."""
        VAForm.objects.create(
            form_number="TEST-001",
            title="Test Form",
            description="Test",
            instructions="Test",
            official_url="https://va.gov",
            last_updated=date.today(),
        )
        with self.assertRaises(Exception):
            VAForm.objects.create(
                form_number="TEST-001",
                title="Another Form",
                description="Test",
                instructions="Test",
                official_url="https://va.gov",
                last_updated=date.today(),
            )

    def test_form_workflow_stages_json(self):
        """VAForm workflow_stages stores as JSON."""
        form = VAForm.objects.create(
            form_number="TEST-002",
            title="Multi-stage Form",
            description="Test",
            instructions="Test",
            official_url="https://va.gov",
            workflow_stages=["initial_claim", "supplemental_claim"],
            last_updated=date.today(),
        )
        self.assertEqual(len(form.workflow_stages), 2)
        self.assertIn("initial_claim", form.workflow_stages)


class TestCPExamGuideConditionModel(TestCase):
    """Tests for the CPExamGuideCondition model."""

    def test_guide_creation(self):
        """CPExamGuideCondition can be created."""
        guide = CPExamGuideCondition.objects.create(
            condition_name="PTSD",
            slug="ptsd",
            category="mental_health",
            what_to_expect="The examiner will ask about your symptoms...",
            how_to_prepare="Bring documentation...",
            tips="Be honest about your worst days...",
        )
        self.assertEqual(guide.condition_name, "PTSD")
        self.assertTrue(guide.is_published)

    def test_guide_str_representation(self):
        """CPExamGuideCondition string includes condition name."""
        guide = CPExamGuideCondition.objects.create(
            condition_name="Sleep Apnea",
            slug="sleep-apnea",
            what_to_expect="Test",
            how_to_prepare="Test",
            tips="Test",
        )
        self.assertEqual(str(guide), "C&P Guide: Sleep Apnea")

    def test_guide_key_questions_json(self):
        """CPExamGuideCondition key_questions stores as JSON list."""
        guide = CPExamGuideCondition.objects.create(
            condition_name="Test Condition",
            slug="test-condition",
            what_to_expect="Test",
            how_to_prepare="Test",
            tips="Test",
            key_questions=[
                "When did your symptoms start?",
                "How often do you experience symptoms?",
                "How do symptoms affect your work?",
            ],
        )
        self.assertEqual(len(guide.key_questions), 3)


class TestLegalReferenceModel(TestCase):
    """Tests for the LegalReference model."""

    def test_reference_creation(self):
        """LegalReference can be created."""
        ref = LegalReference.objects.create(
            reference_type="cavc",
            citation="Caluza v. Brown, 7 Vet. App. 498 (1995)",
            short_name="Caluza",
            title="Three elements of service connection",
            summary="Establishes the three elements needed for service connection...",
            relevance="Applies to all service connection claims...",
            date_issued=date(1995, 5, 1),
        )
        self.assertEqual(ref.reference_type, "cavc")
        self.assertTrue(ref.is_active)

    def test_reference_str_representation(self):
        """LegalReference string includes short name and type."""
        ref = LegalReference.objects.create(
            reference_type="vaopgcprec",
            citation="VAOPGCPREC 5-94",
            short_name="OGC 5-94",
            title="Test Opinion",
            summary="Test",
            relevance="Test",
            date_issued=date(1994, 1, 1),
        )
        self.assertIn("OGC 5-94", str(ref))

    def test_reference_disclaimer_property(self):
        """LegalReference has disclaimer property."""
        ref = LegalReference.objects.create(
            reference_type="cavc",
            citation="Test v. Test",
            short_name="Test",
            title="Test",
            summary="Test",
            relevance="Test",
            date_issued=date.today(),
        )
        self.assertIn("educational purposes", ref.disclaimer)
        self.assertIn("legal advice", ref.disclaimer)

    def test_reference_superseded_by(self):
        """LegalReference can be superseded by another."""
        old_ref = LegalReference.objects.create(
            reference_type="cavc",
            citation="Old Case",
            short_name="Old",
            title="Old Decision",
            summary="Test",
            relevance="Test",
            date_issued=date(1990, 1, 1),
            is_active=False,
        )
        new_ref = LegalReference.objects.create(
            reference_type="cavc",
            citation="New Case",
            short_name="New",
            title="New Decision",
            summary="Test",
            relevance="Test",
            date_issued=date(2000, 1, 1),
        )
        old_ref.superseded_by = new_ref
        old_ref.save()

        self.assertEqual(old_ref.superseded_by, new_ref)
        self.assertIn(old_ref, new_ref.supersedes.all())


# =============================================================================
# VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestDocumentationSearchViews:
    """Tests for documentation search views."""

    def test_search_page_loads(self, client):
        """Search page loads without error."""
        response = client.get(reverse("documentation:search"))
        assert response.status_code == 200

    def test_search_with_query(self, client, va_form):
        """Search returns results for matching query."""
        response = client.get(reverse("documentation:search") + "?q=disability")
        assert response.status_code == 200

    def test_search_htmx_endpoint(self, client, va_form):
        """HTMX search endpoint returns results."""
        response = client.get(
            reverse("documentation:search_results_htmx") + "?q=disability",
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestVAFormViews:
    """Tests for VA Form views."""

    def test_form_list_loads(self, client):
        """Form list page loads."""
        response = client.get(reverse("documentation:form_list"))
        assert response.status_code == 200

    def test_form_detail_loads(self, client, va_form):
        """Form detail page loads."""
        response = client.get(
            reverse(
                "documentation:form_detail", kwargs={"form_number": va_form.form_number}
            )
        )
        assert response.status_code == 200

    def test_form_list_filtered_by_stage(self, client, va_form):
        """Form list can be filtered by workflow stage."""
        response = client.get(
            reverse("documentation:form_list") + "?stage=initial_claim"
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestExamGuideViews:
    """Tests for C&P Exam Guide views."""

    def test_guide_list_loads(self, client):
        """Guide list page loads."""
        response = client.get(reverse("documentation:exam_guide_list"))
        assert response.status_code == 200

    def test_guide_detail_loads(self, client, exam_guide_condition):
        """Guide detail page loads."""
        response = client.get(
            reverse(
                "documentation:exam_guide_detail",
                kwargs={"slug": exam_guide_condition.slug},
            )
        )
        assert response.status_code == 200

    def test_guide_list_filtered_by_category(self, client, exam_guide_condition):
        """Guide list can be filtered by category."""
        response = client.get(
            reverse("documentation:exam_guide_list") + "?category=mental_health"
        )
        assert response.status_code == 200

    def test_unpublished_guide_404(self, client, db):
        """Unpublished guides return 404."""
        guide = CPExamGuideCondition.objects.create(
            condition_name="Hidden Guide",
            slug="hidden-guide",
            what_to_expect="Test",
            how_to_prepare="Test",
            tips="Test",
            is_published=False,
        )
        response = client.get(
            reverse("documentation:exam_guide_detail", kwargs={"slug": guide.slug})
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestLegalReferenceViews:
    """Tests for Legal Reference views."""

    def test_reference_list_loads(self, client):
        """Reference list page loads with disclaimer."""
        response = client.get(reverse("documentation:legal_reference_list"))
        assert response.status_code == 200
        assert "disclaimer" in response.context

    def test_reference_detail_loads(self, client, legal_reference):
        """Reference detail page loads."""
        response = client.get(
            reverse(
                "documentation:legal_reference_detail",
                kwargs={"pk": legal_reference.pk},
            )
        )
        assert response.status_code == 200

    def test_reference_list_filtered_by_type(self, client, legal_reference):
        """Reference list can be filtered by type."""
        response = client.get(
            reverse("documentation:legal_reference_list") + "?type=cavc"
        )
        assert response.status_code == 200


# =============================================================================
# PYTEST FIXTURES
# =============================================================================


@pytest.fixture
def va_form(db):
    """Create a VA Form for testing."""
    return VAForm.objects.create(
        form_number="21-526EZ",
        title="Application for Disability Compensation",
        description="Primary form for disability claims",
        instructions="Complete all sections",
        official_url="https://va.gov/test",
        workflow_stages=["initial_claim"],
        last_updated=date.today(),
    )


@pytest.fixture
def exam_guide_condition(db):
    """Create a C&P Exam Guide for testing."""
    return CPExamGuideCondition.objects.create(
        condition_name="PTSD",
        slug="ptsd",
        category="mental_health",
        what_to_expect="The examiner will ask about symptoms...",
        how_to_prepare="Bring documentation of treatment...",
        tips="Be honest about your worst days",
        key_questions=["When did symptoms start?", "How often do symptoms occur?"],
    )


@pytest.fixture
def legal_reference(db):
    """Create a Legal Reference for testing."""
    return LegalReference.objects.create(
        reference_type="cavc",
        citation="Caluza v. Brown, 7 Vet. App. 498 (1995)",
        short_name="Caluza",
        title="Three elements of service connection",
        summary="Establishes three elements needed for service connection.",
        relevance="Applies to all service connection claims.",
        date_issued=date(1995, 5, 1),
    )
