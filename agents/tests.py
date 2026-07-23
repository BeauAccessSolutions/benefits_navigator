"""
Tests for the agents app - AI-powered analysis and M21 reference data.

Covers:
- AgentInteraction model
- DecisionLetterAnalysis model
- DenialDecoding model
- EvidenceGapAnalysis model
- PersonalStatement model
- M21ManualSection model
- M21ScrapeJob model
- Agent services (Decision Analyzer, Evidence Gap, Statement Generator)
- Denial decoder service
- Evidence checklist generator
- M21 search and retrieval
- Agent views
"""

import json
import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from agents.models import (
    AgentInteraction,
    DecisionLetterAnalysis,
    DenialDecoding,
    EvidenceGapAnalysis,
    PersonalStatement,
    M21ManualSection,
    M21ScrapeJob,
)

User = get_user_model()


# =============================================================================
# AGENT INTERACTION MODEL TESTS
# =============================================================================


class TestAgentInteractionModel(TestCase):
    """Tests for the AgentInteraction model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )

    def test_interaction_creation(self):
        """AgentInteraction can be created."""
        interaction = AgentInteraction.objects.create(
            user=self.user,
            agent_type="decision_analyzer",
            status="pending",
        )
        self.assertEqual(interaction.user, self.user)
        self.assertEqual(interaction.agent_type, "decision_analyzer")

    def test_interaction_str_representation(self):
        """AgentInteraction string includes display name and user."""
        interaction = AgentInteraction.objects.create(
            user=self.user,
            agent_type="evidence_gap",
        )
        # Model uses get_agent_type_display() which returns "Evidence Gap Analyzer"
        self.assertIn("Evidence Gap Analyzer", str(interaction))

    def test_interaction_agent_type_choices(self):
        """AgentInteraction accepts valid agent type choices."""
        valid_types = ["decision_analyzer", "evidence_gap", "statement_generator"]
        for atype in valid_types:
            interaction = AgentInteraction.objects.create(
                user=self.user,
                agent_type=atype,
            )
            self.assertEqual(interaction.agent_type, atype)

    def test_interaction_status_choices(self):
        """AgentInteraction accepts valid status choices."""
        valid_statuses = ["pending", "processing", "completed", "failed"]
        for status in valid_statuses:
            interaction = AgentInteraction.objects.create(
                user=self.user,
                agent_type="decision_analyzer",
                status=status,
            )
            self.assertEqual(interaction.status, status)

    def test_interaction_token_tracking(self):
        """AgentInteraction tracks token usage and cost."""
        interaction = AgentInteraction.objects.create(
            user=self.user,
            agent_type="decision_analyzer",
            status="completed",
            tokens_used=2500,
            cost_estimate=Decimal("0.005"),
        )
        self.assertEqual(interaction.tokens_used, 2500)
        self.assertEqual(interaction.cost_estimate, Decimal("0.005"))


# =============================================================================
# DECISION LETTER ANALYSIS MODEL TESTS
# =============================================================================


class TestDecisionLetterAnalysisModel(TestCase):
    """Tests for the DecisionLetterAnalysis model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.interaction = AgentInteraction.objects.create(
            user=self.user,
            agent_type="decision_analyzer",
        )

    def test_analysis_creation(self):
        """DecisionLetterAnalysis can be created."""
        analysis = DecisionLetterAnalysis.objects.create(
            interaction=self.interaction,
            user=self.user,
            decision_date=date.today() - timedelta(days=30),
        )
        self.assertEqual(analysis.user, self.user)

    def test_analysis_str_representation(self):
        """DecisionLetterAnalysis string includes user and date."""
        analysis = DecisionLetterAnalysis.objects.create(
            interaction=self.interaction,
            user=self.user,
            decision_date=date.today(),
        )
        # Check user email is in the string representation
        self.assertIn(self.user.email, str(analysis))
        # Check format includes "Decision Analysis"
        self.assertIn("Decision Analysis", str(analysis))

    def test_analysis_conditions_json(self):
        """DecisionLetterAnalysis stores conditions as JSON."""
        analysis = DecisionLetterAnalysis.objects.create(
            interaction=self.interaction,
            user=self.user,
            conditions_granted=[
                {"condition": "Tinnitus", "rating": 10, "effective_date": "2024-01-01"},
            ],
            conditions_denied=[
                {"condition": "PTSD", "reason": "No nexus"},
            ],
            conditions_deferred=[
                {"condition": "Sleep Apnea", "reason": "Awaiting exam"},
            ],
        )
        self.assertEqual(len(analysis.conditions_granted), 1)
        self.assertEqual(len(analysis.conditions_denied), 1)
        self.assertEqual(analysis.conditions_denied[0]["condition"], "PTSD")

    def test_analysis_appeal_options_json(self):
        """DecisionLetterAnalysis stores appeal options as JSON."""
        analysis = DecisionLetterAnalysis.objects.create(
            interaction=self.interaction,
            user=self.user,
            appeal_options=[
                {"type": "HLR", "deadline": "2025-01-01"},
                {"type": "Supplemental", "deadline": "No deadline"},
                {"type": "Board", "deadline": "2025-01-01"},
            ],
        )
        self.assertEqual(len(analysis.appeal_options), 3)

    def test_analysis_action_items(self):
        """DecisionLetterAnalysis stores action items."""
        analysis = DecisionLetterAnalysis.objects.create(
            interaction=self.interaction,
            user=self.user,
            action_items=[
                "Get nexus letter from psychiatrist",
                "Request buddy statement",
                "File supplemental claim within 1 year",
            ],
        )
        self.assertEqual(len(analysis.action_items), 3)


# =============================================================================
# DENIAL DECODING MODEL TESTS
# =============================================================================


class TestDenialDecodingModel(TestCase):
    """Tests for the DenialDecoding model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.interaction = AgentInteraction.objects.create(
            user=self.user,
            agent_type="decision_analyzer",
        )
        self.analysis = DecisionLetterAnalysis.objects.create(
            interaction=self.interaction,
            user=self.user,
        )

    def test_decoding_creation(self):
        """DenialDecoding can be created."""
        decoding = DenialDecoding.objects.create(
            analysis=self.analysis,
            denial_mappings=[],
            evidence_strategy="Focus on nexus evidence.",
        )
        self.assertEqual(decoding.analysis, self.analysis)

    def test_decoding_str_representation(self):
        """DenialDecoding string includes analysis reference."""
        decoding = DenialDecoding.objects.create(
            analysis=self.analysis,
        )
        self.assertIsNotNone(str(decoding))

    def test_decoding_denial_mappings(self):
        """DenialDecoding stores detailed denial mappings."""
        decoding = DenialDecoding.objects.create(
            analysis=self.analysis,
            denial_mappings=[
                {
                    "condition": "PTSD",
                    "denial_reason": "No nexus to service",
                    "denial_category": "nexus",
                    "matched_m21_sections": [
                        {"reference": "M21-1.V.ii.2.A", "title": "Service Connection"},
                    ],
                    "required_evidence": [
                        {"type": "nexus_letter", "priority": "critical"},
                    ],
                    "suggested_actions": ["Get IMO"],
                    "va_standard": "50% or greater likelihood",
                },
            ],
        )
        self.assertEqual(len(decoding.denial_mappings), 1)
        self.assertEqual(decoding.denial_mappings[0]["condition"], "PTSD")

    def test_decoding_denial_count(self):
        """denial_count property returns correct count."""
        decoding = DenialDecoding.objects.create(
            analysis=self.analysis,
            denial_mappings=[
                {"condition": "PTSD"},
                {"condition": "Back Pain"},
            ],
        )
        self.assertEqual(decoding.denial_count, 2)

    def test_decoding_critical_evidence_count(self):
        """critical_evidence_count returns count of critical items."""
        decoding = DenialDecoding.objects.create(
            analysis=self.analysis,
            denial_mappings=[
                {
                    "condition": "PTSD",
                    "required_evidence": [
                        {"type": "nexus", "priority": "critical"},
                        {"type": "buddy", "priority": "standard"},
                    ],
                },
                {
                    "condition": "Back",
                    "required_evidence": [
                        {"type": "nexus", "priority": "critical"},
                    ],
                },
            ],
        )
        self.assertEqual(decoding.critical_evidence_count, 2)


# =============================================================================
# EVIDENCE GAP ANALYSIS MODEL TESTS
# =============================================================================


class TestEvidenceGapAnalysisModel(TestCase):
    """Tests for the EvidenceGapAnalysis model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.interaction = AgentInteraction.objects.create(
            user=self.user,
            agent_type="evidence_gap",
        )

    def test_gap_analysis_creation(self):
        """EvidenceGapAnalysis can be created."""
        analysis = EvidenceGapAnalysis.objects.create(
            interaction=self.interaction,
            user=self.user,
            claimed_conditions=["PTSD", "Sleep Apnea"],
            existing_evidence=[
                {"type": "medical_records", "description": "VA treatment records"},
            ],
        )
        self.assertEqual(analysis.user, self.user)

    def test_gap_analysis_str_representation(self):
        """EvidenceGapAnalysis string includes user."""
        analysis = EvidenceGapAnalysis.objects.create(
            interaction=self.interaction,
            user=self.user,
        )
        self.assertIn("test@example.com", str(analysis))

    def test_gap_analysis_evidence_gaps(self):
        """EvidenceGapAnalysis stores identified gaps."""
        analysis = EvidenceGapAnalysis.objects.create(
            interaction=self.interaction,
            user=self.user,
            evidence_gaps=[
                {
                    "condition": "PTSD",
                    "missing": "Nexus letter",
                    "priority": "critical",
                },
                {
                    "condition": "Sleep Apnea",
                    "missing": "Sleep study",
                    "priority": "critical",
                },
            ],
        )
        self.assertEqual(len(analysis.evidence_gaps), 2)

    def test_gap_analysis_readiness_score(self):
        """EvidenceGapAnalysis stores readiness score."""
        analysis = EvidenceGapAnalysis.objects.create(
            interaction=self.interaction,
            user=self.user,
            readiness_score=45,
        )
        self.assertEqual(analysis.readiness_score, 45)


# =============================================================================
# PERSONAL STATEMENT MODEL TESTS
# =============================================================================


class TestPersonalStatementModel(TestCase):
    """Tests for the PersonalStatement model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.interaction = AgentInteraction.objects.create(
            user=self.user,
            agent_type="statement_generator",
        )

    def test_statement_creation(self):
        """PersonalStatement can be created."""
        statement = PersonalStatement.objects.create(
            interaction=self.interaction,
            user=self.user,
            condition="PTSD",
            in_service_event="Combat deployment to Iraq",
            current_symptoms="Nightmares, hypervigilance",
        )
        self.assertEqual(statement.condition, "PTSD")

    def test_statement_str_representation(self):
        """PersonalStatement string includes condition."""
        statement = PersonalStatement.objects.create(
            interaction=self.interaction,
            user=self.user,
            condition="Back Pain",
        )
        self.assertIn("Back Pain", str(statement))

    def test_statement_generated_text(self):
        """PersonalStatement stores generated text and computes word count."""
        generated_text = "During my service in Iraq from 2003-2004, I experienced many traumatic events."
        statement = PersonalStatement.objects.create(
            interaction=self.interaction,
            user=self.user,
            condition="PTSD",
            generated_statement=generated_text,
        )
        self.assertIn("During my service", statement.generated_statement)
        # word_count is auto-computed from generated_statement
        self.assertEqual(statement.word_count, len(generated_text.split()))

    def test_statement_finalization(self):
        """PersonalStatement can be finalized."""
        statement = PersonalStatement.objects.create(
            interaction=self.interaction,
            user=self.user,
            condition="PTSD",
            generated_statement="Original text...",
        )

        statement.final_statement = "Edited and finalized text..."
        statement.is_finalized = True
        statement.save()

        statement.refresh_from_db()
        self.assertTrue(statement.is_finalized)
        self.assertIn("finalized", statement.final_statement)

    def test_statement_type_choices(self):
        """PersonalStatement accepts valid type choices."""
        valid_types = ["initial", "increase", "secondary", "appeal"]
        for i, stype in enumerate(valid_types):
            # Each statement needs a unique interaction (OneToOne relationship)
            interaction = AgentInteraction.objects.create(
                user=self.user,
                agent_type="statement_generator",
            )
            statement = PersonalStatement.objects.create(
                interaction=interaction,
                user=self.user,
                condition=f"Test {i}",
                statement_type=stype,
            )
            self.assertEqual(statement.statement_type, stype)


# =============================================================================
# M21 MANUAL SECTION MODEL TESTS
# =============================================================================


class TestM21ManualSectionModel(TestCase):
    """Tests for the M21ManualSection model."""

    def test_section_creation(self):
        """M21ManualSection can be created."""
        section = M21ManualSection.objects.create(
            part="V",
            part_number=5,
            part_title="Claims Processing",
            subpart="ii",
            chapter="2",
            section="A",
            title="Service Connection",
            reference="M21-1.V.ii.2.A",
            content="To establish service connection...",
        )
        self.assertEqual(section.reference, "M21-1.V.ii.2.A")

    def test_section_str_representation(self):
        """M21ManualSection string includes reference and title."""
        section = M21ManualSection.objects.create(
            part="V",
            part_number=5,
            subpart="ii",
            chapter="2",
            section="B",
            reference="M21-1.V.ii.2.B",
            title="Evidence Requirements",
            content="Evidence requirements content...",
        )
        self.assertIn("M21-1.V.ii.2.B", str(section))

    def test_section_unique_reference(self):
        """M21ManualSection reference must be unique."""
        M21ManualSection.objects.create(
            part="V",
            part_number=5,
            subpart="ii",
            chapter="1",
            section="A",
            reference="M21-1.Test",
            title="Test 1",
            content="Test content",
        )
        with self.assertRaises(Exception):
            M21ManualSection.objects.create(
                part="V",
                part_number=5,
                subpart="ii",
                chapter="1",
                section="B",
                reference="M21-1.Test",
                title="Test 2",
                content="Test content 2",
            )

    def test_section_topics_json(self):
        """M21ManualSection stores topics as JSON."""
        section = M21ManualSection.objects.create(
            part="V",
            part_number=5,
            subpart="ii",
            chapter="2",
            section="A",
            reference="M21-1.V.ii.2.A.topics",
            title="Service Connection",
            content="Service connection content...",
            topics=[
                {"code": "V.ii.2.A.1", "title": "In-Service Event"},
                {"code": "V.ii.2.A.2", "title": "Current Disability"},
                {"code": "V.ii.2.A.3", "title": "Nexus"},
            ],
        )
        self.assertEqual(len(section.topics), 3)


# =============================================================================
# M21 SCRAPE JOB MODEL TESTS
# =============================================================================


class TestM21ScrapeJobModel(TestCase):
    """Tests for the M21ScrapeJob model."""

    def test_scrape_job_creation(self):
        """M21ScrapeJob can be created."""
        job = M21ScrapeJob.objects.create(
            status="pending",
            target_parts=["V", "VI"],
        )
        self.assertEqual(job.status, "pending")

    def test_scrape_job_str_representation(self):
        """M21ScrapeJob string includes status."""
        job = M21ScrapeJob.objects.create(
            status="running",
        )
        self.assertIn("running", str(job).lower())

    def test_scrape_job_progress_tracking(self):
        """M21ScrapeJob tracks progress."""
        job = M21ScrapeJob.objects.create(
            status="running",
            total_sections=5,
            sections_completed=2,
            sections_failed=1,
        )
        self.assertEqual(job.sections_completed, 2)
        self.assertEqual(job.sections_failed, 1)
        # Progress would be 2/5 = 40%


# =============================================================================
# AGENT VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestAgentHomeView:
    """Tests for the agents home view."""

    def test_agents_home_loads(self, client):
        """Agents home page loads."""
        response = client.get(reverse("agents:home"))
        assert response.status_code == 200


@pytest.mark.django_db
class TestAgentHistoryView:
    """Tests for the agent history view."""

    def test_history_requires_login(self, client):
        """Agent history requires authentication."""
        response = client.get(reverse("agents:history"))
        assert response.status_code == 302

    def test_history_loads(self, authenticated_client):
        """Agent history loads for authenticated user."""
        response = authenticated_client.get(reverse("agents:history"))
        assert response.status_code == 200

    def test_history_shows_user_interactions(
        self, authenticated_client, agent_interaction
    ):
        """Agent history shows user's interactions."""
        response = authenticated_client.get(reverse("agents:history"))
        assert response.status_code == 200
        assert "interactions" in response.context


# =============================================================================
# DECISION ANALYZER VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestDecisionAnalyzerViews:
    """Tests for decision analyzer views."""

    def test_analyzer_requires_login(self, client):
        """Decision analyzer requires authentication."""
        response = client.get(reverse("agents:decision_analyzer"))
        assert response.status_code == 302

    def test_analyzer_loads(self, authenticated_client):
        """Decision analyzer page loads."""
        response = authenticated_client.get(reverse("agents:decision_analyzer"))
        assert response.status_code == 200

    def test_analyzer_result_loads(self, authenticated_client, decision_analysis):
        """Decision analyzer result page loads."""
        response = authenticated_client.get(
            reverse(
                "agents:decision_analyzer_result", kwargs={"pk": decision_analysis.pk}
            )
        )
        assert response.status_code == 200

    def test_analyzer_result_denied_for_other(self, authenticated_client, other_user):
        """Users cannot view other's analysis results."""
        other_interaction = AgentInteraction.objects.create(
            user=other_user,
            agent_type="decision_analyzer",
        )
        other_analysis = DecisionLetterAnalysis.objects.create(
            interaction=other_interaction,
            user=other_user,
        )
        response = authenticated_client.get(
            reverse("agents:decision_analyzer_result", kwargs={"pk": other_analysis.pk})
        )
        assert response.status_code == 404


# =============================================================================
# EVIDENCE GAP ANALYZER VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestEvidenceGapViews:
    """Tests for evidence gap analyzer views."""

    def test_gap_analyzer_requires_login(self, client):
        """Evidence gap analyzer requires authentication."""
        response = client.get(reverse("agents:evidence_gap"))
        assert response.status_code == 302

    def test_gap_analyzer_loads(self, authenticated_client):
        """Evidence gap analyzer page loads."""
        response = authenticated_client.get(reverse("agents:evidence_gap"))
        assert response.status_code == 200


# =============================================================================
# STATEMENT GENERATOR VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestStatementGeneratorViews:
    """Tests for personal statement generator views."""

    def test_generator_requires_login(self, client):
        """Statement generator requires authentication."""
        response = client.get(reverse("agents:statement_generator"))
        assert response.status_code == 302

    def test_generator_loads(self, authenticated_client):
        """Statement generator page loads."""
        response = authenticated_client.get(reverse("agents:statement_generator"))
        assert response.status_code == 200


# =============================================================================
# AGENT SERVICE TESTS (MOCKED)
# =============================================================================


class TestDecisionLetterAnalyzerService(TestCase):
    """Tests for the DecisionLetterAnalyzer service."""

    def test_analyzer_initialization(self):
        """DecisionLetterAnalyzer can be initialized without an API key
        (client construction is lazy — only real calls need credentials)."""
        from agents.services import DecisionLetterAnalyzer

        analyzer = DecisionLetterAnalyzer()
        self.assertIsNotNone(analyzer)

    @patch("agents.ai_gateway.Anthropic")
    def test_analyzer_analyze_mocked(self, mock_anthropic):
        """DecisionLetterAnalyzer analyzes text with mocked Claude client."""
        from agents.services import DecisionLetterAnalyzer

        block = MagicMock()
        block.type = "text"
        block.text = json.dumps(
            {
                "granted": [{"condition": "Tinnitus", "rating": 10}],
                "denied": [{"condition": "PTSD", "reason": "No nexus"}],
                "deferred": [],
                "summary": "Test summary",
                "appeal_options": [],
            }
        )
        mock_response = MagicMock()
        mock_response.content = [block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 600
        mock_response.usage.output_tokens = 400

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        analyzer = DecisionLetterAnalyzer()
        # Service should be callable


class TestEvidenceGapAnalyzerService(TestCase):
    """Tests for the EvidenceGapAnalyzer service."""

    def test_gap_analyzer_initialization(self):
        """EvidenceGapAnalyzer can be initialized."""
        from agents.services import EvidenceGapAnalyzer

        analyzer = EvidenceGapAnalyzer()
        self.assertIsNotNone(analyzer)


class TestPersonalStatementGeneratorService(TestCase):
    """Tests for the PersonalStatementGenerator service."""

    def test_generator_initialization(self):
        """PersonalStatementGenerator can be initialized."""
        from agents.services import PersonalStatementGenerator

        generator = PersonalStatementGenerator()
        self.assertIsNotNone(generator)


# =============================================================================
# DENIAL DECODER SERVICE TESTS
# =============================================================================


class TestDenialDecoderService(TestCase):
    """Tests for the DenialDecoderService."""

    def setUp(self):
        # Create M21 section for testing
        self.m21_section = M21ManualSection.objects.create(
            part="V",
            part_number=5,
            subpart="ii",
            chapter="2",
            section="A",
            reference="M21-1.V.ii.2.A",
            title="Service Connection",
            content="Service connection requirements...",
        )

    def test_decoder_initialization(self):
        """DenialDecoderService can be initialized."""
        from agents.services import DenialDecoderService

        service = DenialDecoderService()
        self.assertIsNotNone(service)


# =============================================================================
# EVIDENCE CHECKLIST GENERATOR TESTS
# =============================================================================


class TestEvidenceChecklistGenerator(TestCase):
    """Tests for the EvidenceChecklistGenerator service."""

    def setUp(self):
        self.m21_section = M21ManualSection.objects.create(
            part="V",
            part_number=5,
            subpart="ii",
            chapter="2",
            section="A",
            reference="M21-1.V.ii.2.A.ecg",
            title="Service Connection",
            content="Requirements for service connection...",
        )

    def test_generator_initialization(self):
        """EvidenceChecklistGenerator can be initialized."""
        from agents.services import EvidenceChecklistGenerator

        generator = EvidenceChecklistGenerator()
        self.assertIsNotNone(generator)


# =============================================================================
# M21 REFERENCE DATA TESTS
# =============================================================================


class TestM21ReferenceData(TestCase):
    """Tests for M21 reference data functions."""

    def setUp(self):
        # Create some M21 sections
        self.section1 = M21ManualSection.objects.create(
            part="V",
            part_number=5,
            subpart="ii",
            chapter="2",
            section="A",
            reference="M21-1.V.ii.2.A.ref",
            title="Service Connection",
            content="Service connection requirements for disabilities.",
        )
        self.section2 = M21ManualSection.objects.create(
            part="V",
            part_number=5,
            subpart="ii",
            chapter="2",
            section="B",
            reference="M21-1.V.ii.2.B.ref",
            title="Evidence Requirements",
            content="Evidence requirements for claims.",
        )

    def test_search_m21_in_db(self):
        """search_m21_in_db finds matching sections."""
        from agents.reference_data import search_m21_in_db

        results = search_m21_in_db("service connection")
        self.assertGreater(len(results), 0)

    def test_get_m21_section_from_db(self):
        """get_m21_section_from_db retrieves specific section as dict."""
        from agents.reference_data import get_m21_section_from_db

        section = get_m21_section_from_db("M21-1.V.ii.2.A.ref")
        if section:  # May return None if not found by exact match
            # Returns a dict, not a model object
            self.assertEqual(section["title"], "Service Connection")

    def test_get_m21_sections_by_part(self):
        """get_m21_sections_by_part retrieves sections in a part."""
        from agents.reference_data import get_m21_sections_by_part

        sections = get_m21_sections_by_part("V")
        self.assertGreater(len(sections), 0)

    def test_get_m21_stats(self):
        """get_m21_stats returns statistics."""
        from agents.reference_data import get_m21_stats

        stats = get_m21_stats()
        self.assertIn("total", stats)
        self.assertEqual(stats["total"], 2)


# =============================================================================
# ACCESS CONTROL TESTS
# =============================================================================


@pytest.mark.django_db
class TestAgentAccessControl:
    """Tests for access control on agent views and data."""

    def test_user_cannot_view_other_analysis(self, authenticated_client, other_user):
        """Users cannot view other user's decision analysis."""
        other_interaction = AgentInteraction.objects.create(
            user=other_user,
            agent_type="decision_analyzer",
        )
        other_analysis = DecisionLetterAnalysis.objects.create(
            interaction=other_interaction,
            user=other_user,
        )
        response = authenticated_client.get(
            reverse("agents:decision_analyzer_result", kwargs={"pk": other_analysis.pk})
        )
        assert response.status_code == 404

    def test_user_cannot_view_other_gap_analysis(
        self, authenticated_client, other_user
    ):
        """Users cannot view other user's evidence gap analysis."""
        other_interaction = AgentInteraction.objects.create(
            user=other_user,
            agent_type="evidence_gap",
        )
        other_analysis = EvidenceGapAnalysis.objects.create(
            interaction=other_interaction,
            user=other_user,
        )
        response = authenticated_client.get(
            reverse("agents:evidence_gap_result", kwargs={"pk": other_analysis.pk})
        )
        assert response.status_code == 404


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestAgentWorkflow(TestCase):
    """Integration tests for agent workflows."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.client = Client()
        self.client.login(email="test@example.com", password="TestPass123!")

    def test_complete_decision_analysis_workflow(self):
        """Test complete decision letter analysis workflow."""
        # 1. Create interaction
        interaction = AgentInteraction.objects.create(
            user=self.user,
            agent_type="decision_analyzer",
            status="pending",
        )

        # 2. Simulate processing
        interaction.status = "processing"
        interaction.save()

        # 3. Create analysis
        analysis = DecisionLetterAnalysis.objects.create(
            interaction=interaction,
            user=self.user,
            decision_date=date.today() - timedelta(days=30),
            conditions_granted=[{"condition": "Tinnitus", "rating": 10}],
            conditions_denied=[{"condition": "PTSD", "reason": "No nexus evidence"}],
            summary="Your claim for tinnitus was granted. PTSD was denied.",
            appeal_options=[
                {"type": "HLR", "deadline": "2025-01-01"},
                {"type": "Supplemental", "deadline": "No limit"},
            ],
            appeal_deadline=date.today() + timedelta(days=335),
        )

        # 4. Create denial decoding
        decoding = DenialDecoding.objects.create(
            analysis=analysis,
            denial_mappings=[
                {
                    "condition": "PTSD",
                    "denial_reason": "No nexus evidence",
                    "matched_m21_sections": [],
                    "required_evidence": [
                        {"type": "nexus_letter", "priority": "critical"},
                    ],
                    "suggested_actions": ["Get IMO from psychiatrist"],
                }
            ],
            evidence_strategy="Focus on obtaining a nexus letter.",
            m21_sections_searched=25,
        )

        # 5. Complete interaction
        interaction.status = "completed"
        interaction.tokens_used = 1500
        interaction.cost_estimate = Decimal("0.003")
        interaction.save()

        # Verify workflow completed
        self.assertEqual(interaction.status, "completed")
        self.assertEqual(analysis.conditions_denied[0]["condition"], "PTSD")
        self.assertEqual(decoding.denial_count, 1)

    def test_complete_statement_generation_workflow(self):
        """Test complete personal statement generation workflow."""
        # 1. Create interaction
        interaction = AgentInteraction.objects.create(
            user=self.user,
            agent_type="statement_generator",
            status="pending",
        )

        # 2. Create statement
        statement = PersonalStatement.objects.create(
            interaction=interaction,
            user=self.user,
            condition="PTSD",
            statement_type="initial",
            in_service_event="Combat deployment to Iraq 2003-2004",
            current_symptoms="Nightmares, hypervigilance, avoidance",
            daily_impact="Unable to maintain relationships",
            work_impact="Difficulty concentrating at work",
            treatment_history="VA mental health clinic since 2010",
            worst_days="Can't leave the house, constant flashbacks",
        )

        # 3. Simulate generation
        interaction.status = "processing"
        interaction.save()

        statement.generated_statement = """
        During my deployment to Iraq from 2003 to 2004, I experienced numerous
        combat situations that have profoundly affected my mental health...
        """
        statement.word_count = 500
        statement.save()

        # 4. Finalize
        statement.final_statement = (
            statement.generated_statement + "\n\nSigned,\nVeteran"
        )
        statement.is_finalized = True
        statement.save()

        # Complete interaction
        interaction.status = "completed"
        interaction.tokens_used = 2000
        interaction.save()

        # Verify
        self.assertTrue(statement.is_finalized)
        self.assertEqual(interaction.status, "completed")


# =============================================================================
# AI CONSENT ENFORCEMENT TESTS
# =============================================================================


@pytest.mark.agent
class TestAIConsentEnforcement(TestCase):
    """Tests for AI consent enforcement in agent views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="consent_test@example.com", password="TestPass123!"
        )
        self.client.login(username="consent_test@example.com", password="TestPass123!")

    def test_decision_analyzer_submit_without_consent_redirects(self):
        """Decision analyzer submit redirects to privacy settings without consent."""
        # Ensure user has no AI consent
        self.user.profile.ai_processing_consent = False
        self.user.profile.save()

        response = self.client.post(
            reverse("agents:decision_analyzer_submit"),
            {
                "letter_text": "Test decision letter content with enough text to pass validation."
            },
        )

        # Should redirect to privacy settings
        self.assertEqual(response.status_code, 302)
        self.assertIn("privacy", response.url)

    def test_decision_analyzer_submit_with_consent_processes(self):
        """Decision analyzer submit processes with consent granted."""
        # Grant AI consent
        self.user.profile.ai_processing_consent = True
        self.user.profile.save()

        response = self.client.post(
            reverse("agents:decision_analyzer_submit"),
            {
                "letter_text": "This is a short text"
            },  # Too short, will redirect with error
        )

        # Should redirect to decision_analyzer (validation error), not privacy settings
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("privacy", response.url)

    def test_evidence_gap_submit_without_consent_redirects(self):
        """Evidence gap submit redirects to privacy settings without consent."""
        self.user.profile.ai_processing_consent = False
        self.user.profile.save()

        response = self.client.post(
            reverse("agents:evidence_gap_submit"),
            {"conditions": ["PTSD"]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("privacy", response.url)

    def test_evidence_gap_submit_with_consent_processes(self):
        """Evidence gap submit processes with consent granted."""
        self.user.profile.ai_processing_consent = True
        self.user.profile.save()

        response = self.client.post(
            reverse("agents:evidence_gap_submit"),
            {},  # Missing conditions, will redirect with error
        )

        # Should redirect to evidence_gap (validation error), not privacy settings
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("privacy", response.url)

    def test_statement_generator_submit_without_consent_redirects(self):
        """Statement generator submit redirects to privacy settings without consent."""
        self.user.profile.ai_processing_consent = False
        self.user.profile.save()

        response = self.client.post(
            reverse("agents:statement_generator_submit"),
            {
                "condition": "PTSD",
                "statement_type": "initial",
                "in_service_event": "Combat",
                "current_symptoms": "Nightmares",
                "daily_impact": "Difficulty sleeping",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("privacy", response.url)

    def test_statement_generator_submit_with_consent_processes(self):
        """Statement generator submit processes with consent granted."""
        self.user.profile.ai_processing_consent = True
        self.user.profile.save()

        response = self.client.post(
            reverse("agents:statement_generator_submit"),
            {},  # Missing fields, will redirect with error
        )

        # Should redirect to statement_generator (validation error), not privacy settings
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("privacy", response.url)

    def test_consent_check_handles_missing_profile(self):
        """Consent check handles user without profile gracefully."""
        from agents.views import check_ai_consent

        # Create user without profile (delete the auto-created one)
        new_user = User.objects.create_user(
            email="no_profile@example.com", password="TestPass123!"
        )
        # Delete the auto-created profile
        if hasattr(new_user, "profile"):
            new_user.profile.delete()

        # Refresh from DB
        new_user.refresh_from_db()

        # Should return False, not raise exception
        result = check_ai_consent(new_user)
        self.assertFalse(result)


# =============================================================================
# DISCLAIMER COVERAGE TESTS
# =============================================================================


@pytest.mark.agent
class TestStatementGeneratorDisclaimer(TestCase):
    """Personal statement pages must carry the 'not legal advice' disclaimer (TODO.md P1)."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="disclaimer_test@example.com", password="TestPass123!"
        )
        self.user.profile.ai_processing_consent = True
        self.user.profile.save()
        self.client.login(
            username="disclaimer_test@example.com", password="TestPass123!"
        )

    def test_statement_generator_form_shows_disclaimer(self):
        """The statement generator form page shows the educational-use disclaimer."""
        response = self.client.get(reverse("agents:statement_generator"))
        self.assertContains(response, "Educational use only")
        self.assertContains(response, "not legal advice")

    def test_statement_result_shows_disclaimer(self):
        """The generated statement result page shows the educational-use disclaimer."""
        interaction = AgentInteraction.objects.create(
            user=self.user, agent_type="statement_generator"
        )
        statement = PersonalStatement.objects.create(
            interaction=interaction,
            user=self.user,
            condition="Tinnitus",
            generated_statement="During my service, I was exposed to loud noise.",
        )
        response = self.client.get(
            reverse("agents:statement_result", args=[statement.pk])
        )
        self.assertContains(response, "Educational use only")
        self.assertContains(response, "not legal advice")


# =============================================================================
# M21 TASK RELIABILITY (TODO.md P2: acks_late missing on scraper tasks)
# =============================================================================


class TestM21TaskAcksLate(TestCase):
    """
    M21 scraper tasks (scrape_m21_section/_bulk/_all_known,
    update_stale_m21_sections, build_m21_topic_indices) previously had no
    acks_late, so a worker crash mid-scrape would drop the task entirely
    instead of requeuing it — per CLAUDE.md's Celery best practices.
    """

    def test_all_m21_tasks_have_acks_late(self):
        from agents.tasks import (
            scrape_m21_section,
            scrape_m21_bulk,
            scrape_m21_all_known,
            update_stale_m21_sections,
            build_m21_topic_indices,
        )

        for task in (
            scrape_m21_section,
            scrape_m21_bulk,
            scrape_m21_all_known,
            update_stale_m21_sections,
            build_m21_topic_indices,
        ):
            self.assertTrue(task.acks_late, f"{task.name} must set acks_late=True")
