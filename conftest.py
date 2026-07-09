"""
Pytest configuration and shared fixtures for VA Benefits Navigator tests.

This file provides:
- Factory classes for creating test objects
- Shared fixtures for common test scenarios
- Mock configurations for external services (OpenAI, Celery, etc.)
"""

import os
import django

# Configure Django settings before any Django imports
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "benefits_navigator.settings")
django.setup()

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model

User = get_user_model()


# =============================================================================
# USER & ACCOUNT FIXTURES
# =============================================================================


@pytest.fixture
def user_password():
    """Standard password for test users."""
    return "TestPassword123!"


@pytest.fixture
def user(db, user_password):
    """Create a standard test user with profile."""
    from accounts.models import UserProfile

    user = User.objects.create_user(
        email="testuser@example.com",
        password=user_password,
        first_name="Test",
        last_name="User",
    )
    # Set AI consent on profile to avoid privacy redirect
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.ai_processing_consent = True
    profile.save()
    return user


@pytest.fixture
def premium_user(db, user_password):
    """Create a premium user with active subscription."""
    from accounts.models import Subscription, UserProfile

    user = User.objects.create_user(
        email="premium@example.com",
        password=user_password,
        first_name="Premium",
        last_name="User",
    )
    # Set AI consent on profile to avoid privacy redirect
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.ai_processing_consent = True
    profile.save()
    Subscription.objects.create(
        user=user,
        plan_type="premium",
        status="active",
        current_period_end=datetime.now() + timedelta(days=30),
    )
    return user


@pytest.fixture
def admin_user(db, user_password):
    """Create an admin/superuser."""
    return User.objects.create_superuser(
        email="admin@example.com",
        password=user_password,
    )


@pytest.fixture
def other_user(db, user_password):
    """Create another user for permission testing."""
    from accounts.models import UserProfile

    user = User.objects.create_user(
        email="other@example.com",
        password=user_password,
        first_name="Other",
        last_name="User",
    )
    # Set AI consent on profile to avoid privacy redirect
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.ai_processing_consent = True
    profile.save()
    return user


@pytest.fixture
def authenticated_client(client, user, user_password):
    """Return a client logged in as the standard test user."""
    client.login(email=user.email, password=user_password)
    return client


@pytest.fixture
def premium_client(client, premium_user, user_password):
    """Return a client logged in as a premium user."""
    client.login(email=premium_user.email, password=user_password)
    return client


@pytest.fixture
def admin_client(client, admin_user, user_password):
    """Return a client logged in as admin."""
    client.login(email=admin_user.email, password=user_password)
    return client


# =============================================================================
# DOCUMENT & FILE FIXTURES
# =============================================================================


@pytest.fixture
def sample_pdf():
    """Create a simple PDF file for testing."""
    # Minimal PDF content
    pdf_content = b"""%PDF-1.4
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
    return SimpleUploadedFile(
        name="test_document.pdf", content=pdf_content, content_type="application/pdf"
    )


@pytest.fixture
def sample_image():
    """Create a simple PNG image for testing."""
    # Minimal 1x1 PNG
    png_content = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
        b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
        b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return SimpleUploadedFile(
        name="test_image.png", content=png_content, content_type="image/png"
    )


@pytest.fixture
def document(db, user, sample_pdf):
    """Create a test document."""
    from claims.models import Document

    doc = Document.objects.create(
        user=user,
        file=sample_pdf,
        file_name="test_document.pdf",
        file_size=1024,
        mime_type="application/pdf",
        document_type="medical_records",
        status="completed",
        ocr_length=37,  # Length of simulated OCR text
        ocr_status="completed",
        ocr_confidence=95.5,
        page_count=1,
    )
    return doc


@pytest.fixture
def processing_document(db, user, sample_pdf):
    """Create a document that's still processing."""
    from claims.models import Document

    doc = Document.objects.create(
        user=user,
        file=sample_pdf,
        file_name="processing_document.pdf",
        file_size=2048,
        mime_type="application/pdf",
        document_type="decision_letter",
        status="processing",
    )
    return doc


@pytest.fixture
def document_with_file(db, user, tmp_path, settings):
    """
    Create a test document with an actual file on disk.
    Used for testing file download/view operations.
    """
    from claims.models import Document

    # Set MEDIA_ROOT to temp path for this test
    settings.MEDIA_ROOT = str(tmp_path)

    # Create the documents directory
    user_doc_dir = tmp_path / "documents" / f"user_{user.id}"
    user_doc_dir.mkdir(parents=True, exist_ok=True)

    # Create the actual file on disk
    file_name = "test_file_on_disk.pdf"
    file_path = user_doc_dir / file_name

    # Write minimal PDF content
    pdf_content = b"""%PDF-1.4
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

    with open(file_path, "wb") as f:
        f.write(pdf_content)

    # Create the Document object pointing to this file
    doc = Document.objects.create(
        user=user,
        file=f"documents/user_{user.id}/{file_name}",
        file_name=file_name,
        file_size=len(pdf_content),
        mime_type="application/pdf",
        document_type="decision_letter",
        status="completed",
    )

    return doc


# =============================================================================
# CLAIMS FIXTURES
# =============================================================================


@pytest.fixture
def claim(db, user):
    """Create a test claim."""
    from claims.models import Claim

    return Claim.objects.create(
        user=user,
        title="PTSD Service Connection",
        description="Initial claim for PTSD",
        claim_type="initial",
        status="gathering_evidence",
    )


@pytest.fixture
def submitted_claim(db, user):
    """Create a submitted claim."""
    from claims.models import Claim

    return Claim.objects.create(
        user=user,
        title="Knee Injury Increase",
        description="Claim for increase on knee condition",
        claim_type="increase",
        status="submitted",
        submission_date=date.today() - timedelta(days=30),
    )


# =============================================================================
# APPEALS FIXTURES
# =============================================================================


@pytest.fixture
def appeal_guidance(db):
    """Create appeal guidance content."""
    from appeals.models import AppealGuidance

    return AppealGuidance.objects.create(
        title="Higher-Level Review Guide",
        slug="higher-level-review",
        appeal_type="hlr",
        va_form_number="VA Form 20-0996",
        average_processing_days=141,
        when_to_use="Use when VA made an error with existing evidence.",
        when_not_to_use="Don't use if you have new evidence.",
        overview="A Higher-Level Review is a lane in the VA appeals system...",
        requirements="You must file within 1 year of decision date.",
        step_by_step="1. Download form\n2. Fill out form\n3. Submit",
        common_mistakes="Don't include new evidence.",
        after_submission="Wait for acknowledgment letter.",
        tips="Be patient.",
        checklist_items=[
            {"id": "step1", "text": "Download VA Form 20-0996"},
            {"id": "step2", "text": "Fill out personal information"},
            {"id": "step3", "text": "List conditions being appealed"},
        ],
        is_published=True,
    )


@pytest.fixture
def appeal(db, user):
    """Create a test appeal."""
    from appeals.models import Appeal

    return Appeal.objects.create(
        user=user,
        appeal_type="hlr",
        status="gathering",
        original_decision_date=date.today() - timedelta(days=60),
        conditions_appealed="PTSD",
        denial_reasons="Insufficient nexus evidence",
        has_new_evidence=False,
        believes_va_error=True,
        wants_hearing=False,
    )


@pytest.fixture
def board_appeal(db, user):
    """Create a board appeal."""
    from appeals.models import Appeal

    return Appeal.objects.create(
        user=user,
        appeal_type="board_hearing",
        status="preparing",
        original_decision_date=date.today() - timedelta(days=90),
        conditions_appealed="TBI, PTSD",
        denial_reasons="Insufficient evidence of in-service event",
        has_new_evidence=True,
        believes_va_error=True,
        wants_hearing=True,
    )


# =============================================================================
# EXAMPREP FIXTURES
# =============================================================================


@pytest.fixture
def exam_guidance(db):
    """Create exam preparation guidance."""
    from examprep.models import ExamGuidance

    return ExamGuidance.objects.create(
        title="PTSD C&P Exam Guide",
        slug="ptsd-exam",
        category="ptsd",
        introduction="This guide helps you prepare for a PTSD C&P exam.",
        what_exam_measures="The examiner will assess your PTSD symptoms.",
        physical_tests="No physical tests for mental health exams.",
        questions_to_expect="Tell me about your trauma...",
        preparation_tips="Write down your symptoms beforehand.",
        day_of_guidance="Be honest about your worst days.",
        common_mistakes="Don't minimize your symptoms.",
        after_exam="Follow up with your VSO.",
        checklist_items=[
            "Review your stressor statement",
            "List all symptoms",
            "Bring medication list",
            "Arrive early",
        ],
        is_published=True,
    )


@pytest.fixture
def glossary_term(db):
    """Create a glossary term."""
    from examprep.models import GlossaryTerm

    return GlossaryTerm.objects.create(
        term="Nexus Letter",
        plain_language="A medical opinion letter that connects your condition to your military service.",
        context="Required for service connection claims.",
        example="'It is at least as likely as not that the veteran's knee condition is related to service.'",
        show_in_tooltips=True,
    )


@pytest.fixture
def exam_checklist(db, user, exam_guidance):
    """Create an exam checklist."""
    from examprep.models import ExamChecklist

    return ExamChecklist.objects.create(
        user=user,
        condition="PTSD",
        exam_date=date.today() + timedelta(days=14),
        guidance=exam_guidance,
        tasks_completed=["task_1"],
        symptom_notes="Nightmares, flashbacks, hypervigilance",
    )


@pytest.fixture
def saved_rating(db, user):
    """Create a saved rating calculation."""
    from examprep.models import SavedRatingCalculation

    calc = SavedRatingCalculation.objects.create(
        user=user,
        name="Current Rating",
        ratings=[
            {"percentage": 50, "description": "PTSD", "is_bilateral": False},
            {"percentage": 20, "description": "Tinnitus", "is_bilateral": False},
        ],
        has_spouse=True,
        children_under_18=2,
    )
    calc.recalculate()
    calc.save()
    return calc


@pytest.fixture
def evidence_checklist(db, user):
    """Create an evidence checklist."""
    from examprep.models import EvidenceChecklist

    return EvidenceChecklist.objects.create(
        user=user,
        condition="Sleep Apnea",
        claim_type="secondary",
        primary_condition="PTSD",
        checklist_items=[
            {
                "id": "sleep_study",
                "category": "Medical Evidence",
                "title": "Sleep Study Results",
                "description": "Polysomnography showing sleep apnea diagnosis",
                "priority": "critical",
                "completed": False,
            },
            {
                "id": "nexus_letter",
                "category": "Medical Evidence",
                "title": "Nexus Letter",
                "description": "Medical opinion linking sleep apnea to PTSD",
                "priority": "critical",
                "completed": False,
            },
            {
                "id": "buddy_statement",
                "category": "Lay Evidence",
                "title": "Buddy Statement",
                "description": "Statement from spouse about sleep problems",
                "priority": "standard",
                "completed": True,
            },
        ],
        completion_percentage=33,
    )


# =============================================================================
# CORE APP FIXTURES
# =============================================================================


@pytest.fixture
def journey_stage(db):
    """Create a journey stage."""
    from core.models import JourneyStage

    return JourneyStage.objects.create(
        code="claim_filed",
        name="Claim Filed",
        description="Initial claim submitted to VA",
        order=1,
        typical_duration_days=30,
        icon="document",
        color="blue",
    )


@pytest.fixture
def journey_event(db, user, journey_stage):
    """Create a journey event."""
    from core.models import UserJourneyEvent

    return UserJourneyEvent.objects.create(
        user=user,
        stage=journey_stage,
        event_type="manual",
        title="Filed Initial Claim",
        description="Submitted my PTSD claim",
        event_date=date.today() - timedelta(days=30),
        is_completed=True,
    )


@pytest.fixture
def milestone(db, user):
    """Create a journey milestone."""
    from core.models import JourneyMilestone

    return JourneyMilestone.objects.create(
        user=user,
        milestone_type="claim_filed",
        title="Filed PTSD Claim",
        date=date.today() - timedelta(days=60),
        notes="Finally got all my evidence together.",
    )


@pytest.fixture
def deadline(db, user):
    """Create a deadline."""
    from core.models import Deadline

    return Deadline.objects.create(
        user=user,
        title="Appeal Deadline",
        description="File HLR within 1 year of decision",
        deadline_date=date.today() + timedelta(days=90),
        priority="critical",
    )


@pytest.fixture
def past_deadline(db, user):
    """Create a past deadline."""
    from core.models import Deadline

    return Deadline.objects.create(
        user=user,
        title="Past Deadline",
        description="This deadline has passed",
        deadline_date=date.today() - timedelta(days=10),
        priority="high",
    )


# =============================================================================
# AGENTS FIXTURES
# =============================================================================


@pytest.fixture
def agent_interaction(db, user):
    """Create an agent interaction."""
    from agents.models import AgentInteraction

    return AgentInteraction.objects.create(
        user=user,
        agent_type="decision_analyzer",
        status="completed",
        tokens_used=1500,
        cost_estimate=Decimal("0.003"),
    )


@pytest.fixture
def decision_analysis(db, user, agent_interaction, document):
    """Create a decision letter analysis."""
    from agents.models import DecisionLetterAnalysis

    return DecisionLetterAnalysis.objects.create(
        interaction=agent_interaction,
        user=user,
        document=document,
        decision_date=date.today() - timedelta(days=30),
        conditions_granted=[
            {"condition": "Tinnitus", "rating": 10, "effective_date": "2024-01-01"}
        ],
        conditions_denied=[{"condition": "PTSD", "reason": "No nexus to service"}],
        conditions_deferred=[],
        summary="Your claim for tinnitus was granted at 10%. PTSD was denied.",
        appeal_options=[
            {"type": "HLR", "deadline": "2025-01-01"},
            {"type": "Supplemental", "deadline": "2025-01-01"},
        ],
        evidence_issues=["Missing nexus letter for PTSD"],
        action_items=["Get IMO for PTSD nexus"],
        appeal_deadline=date.today() + timedelta(days=335),
    )


@pytest.fixture
def denial_decoding(db, decision_analysis):
    """Create a denial decoding."""
    from agents.models import DenialDecoding

    return DenialDecoding.objects.create(
        analysis=decision_analysis,
        denial_mappings=[
            {
                "condition": "PTSD",
                "denial_reason": "No nexus to service",
                "denial_category": "nexus",
                "matched_m21_sections": [
                    {
                        "reference": "M21-1.V.ii.2.A",
                        "title": "Service Connection",
                        "relevance_score": 0.95,
                    }
                ],
                "required_evidence": [
                    {
                        "type": "nexus_letter",
                        "description": "IMO from psychiatrist",
                        "priority": "critical",
                    }
                ],
                "suggested_actions": ["Get IMO from treating psychiatrist"],
                "va_standard": "At least as likely as not (50%+)",
            }
        ],
        evidence_strategy="Focus on getting a strong nexus letter from your treating psychiatrist.",
        priority_order=[0],
        m21_sections_searched=25,
        processing_time_seconds=12.5,
    )


@pytest.fixture
def m21_section(db):
    """Create an M21 manual section."""
    from agents.models import M21ManualSection

    return M21ManualSection.objects.create(
        part="V",
        part_number=5,
        part_title="Claims Processing",
        subpart="ii",
        chapter="2",
        section="A",
        title="Service Connection",
        reference="M21-1.V.ii.2.A",
        full_reference="M21-1, Part V, Subpart ii, Chapter 2, Section A",
        overview="This section covers service connection requirements.",
        content="To establish service connection, the following elements must be met...",
        topics=[
            {"code": "V.ii.2.A.1", "title": "In-Service Event", "content": "..."},
            {"code": "V.ii.2.A.2", "title": "Current Disability", "content": "..."},
        ],
        article_id="KA-12345",
    )


# =============================================================================
# MOCKS FOR EXTERNAL SERVICES
# =============================================================================


def _mock_anthropic_message(text='{"test": "data"}', input_tokens=60, output_tokens=40):
    """Build a MagicMock shaped like an anthropic Message response."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    response = MagicMock()
    response.content = [block]
    response.stop_reason = "end_turn"
    response.usage = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


@pytest.fixture
def mock_anthropic():
    """Mock Anthropic API responses (module-level client)."""
    with patch("anthropic.Anthropic") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_message(
            '{"summary": "Test analysis", "conditions": []}', 300, 200
        )
        yield mock_client


# Backwards-compatible alias — older tests request mock_openai
@pytest.fixture
def mock_openai(mock_anthropic):
    """Deprecated alias for mock_anthropic (provider switched 2026-06)."""
    yield mock_anthropic


@pytest.fixture
def mock_ai_gateway():
    """Mock the AI gateway for tests.

    Patches the Anthropic client used by the AI gateway, providing a
    consistent mock for all tests that use AI functionality. Covers both
    messages.create (complete) and messages.parse (complete_structured).
    """
    with patch("agents.ai_gateway.Anthropic") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client

        # Default successful raw completion
        mock_client.messages.create.return_value = _mock_anthropic_message()

        # Default successful structured completion: parsed_output is set
        # per-test (a validated Pydantic instance), so leave a MagicMock
        parse_response = _mock_anthropic_message()
        mock_client.messages.parse.return_value = parse_response

        yield mock_client


@pytest.fixture
def ai_gateway(mock_ai_gateway):
    """Get an AI gateway instance with a mocked Anthropic client.

    Use this fixture when you need to test code that uses the AI gateway.
    The Anthropic client is already mocked via the mock_ai_gateway fixture.
    """
    from agents.ai_gateway import AIGateway, GatewayConfig, reset_gateway

    # Reset the singleton to ensure fresh instance
    reset_gateway()

    gateway = AIGateway(
        GatewayConfig(
            timeout_seconds=30,
            max_retries=2,
            retry_base_delay=0.01,  # Fast retries for tests
        )
    )
    yield gateway

    # Reset after test to avoid state leakage
    reset_gateway()


@pytest.fixture
def mock_celery():
    """Mock Celery task execution to run synchronously."""
    with patch("claims.tasks.process_document_task.delay") as mock_process, patch(
        "claims.tasks.decode_denial_letter_task.delay"
    ) as mock_decode:
        yield {
            "process_document": mock_process,
            "decode_denial": mock_decode,
        }


@pytest.fixture
def mock_ocr():
    """Mock OCR service."""
    with patch("claims.services.ocr_service.OCRService") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        mock_instance.extract_text.return_value = {
            "text": "Extracted text from document",
            "confidence": 95.0,
            "page_count": 1,
        }
        yield mock_instance


# =============================================================================
# DJANGO SETTINGS OVERRIDES
# =============================================================================


@pytest.fixture(autouse=True)
def use_dummy_cache(settings):
    """Use local memory cache for tests."""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }


@pytest.fixture(autouse=True)
def disable_rate_limiting(settings):
    """Disable rate limiting in tests."""
    settings.RATELIMIT_ENABLE = False


@pytest.fixture(autouse=True)
def use_test_file_storage(settings, tmp_path):
    """Use temporary directory for file storage in tests."""
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.MEDIA_ROOT.mkdir(exist_ok=True)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def create_test_user(email="test@example.com", password="TestPass123!", **kwargs):
    """Helper to create a test user."""
    return User.objects.create_user(email=email, password=password, **kwargs)


def login_user(client, user, password="TestPass123!"):
    """Helper to log in a user."""
    return client.login(email=user.email, password=password)
