"""High-stakes agent outputs must be schema-validated before they are stored.

Four agents used to build their result with ``_parse_json_response``: find a
markdown fence, ``json.loads`` whatever is inside, and on failure return ``{}``.
Nothing checked that the parsed object had the fields the model, the templates
and the veteran expected. Two consequences, both live:

* **Unvalidated shapes reached the database.** A response missing
  ``conditions_denied``, or carrying a rating as the string ``"ten"``, was
  stored and rendered as though it were a real analysis.
* **A parse failure was indistinguishable from an empty analysis.** ``{}`` went
  through the same success path — the interaction was marked ``completed``, the
  row saved, and the veteran was shown a blank analysis of their decision
  letter with no indication anything had gone wrong.

They now go through ``BaseAgent._call_structured``, which uses the gateway's
``messages.parse`` (schema enforced API-side, validated with Pydantic) and
raises on failure so the view marks the interaction failed.

These tests mock at the Anthropic client boundary rather than at
``_call_structured``, so they exercise the real gateway path — the previous
service tests mocked a client and then never called anything, which is how
this went uncovered.
"""

from unittest.mock import MagicMock

import pytest

from agents.schemas import (
    DecisionLetterAnalysisResponse,
    DenialDecoderResponse,
    EvidenceGapAnalysisResponse,
    PersonalStatementResponse,
)
from agents.services import (
    DecisionLetterAnalyzer,
    DenialDecoderService,
    EvidenceGapAnalyzer,
    PersonalStatementGenerator,
)


def _parsed(schema_instance, *, input_tokens=600, output_tokens=400):
    """An Anthropic response whose parsed_output is an already-valid model."""
    block = MagicMock()
    block.type = "text"
    block.text = schema_instance.model_dump_json()

    response = MagicMock()
    response.content = [block]
    response.stop_reason = "end_turn"
    response.parsed_output = schema_instance
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


def _unsatisfiable(stop_reason="refusal"):
    """The schema could not be satisfied — parsed_output is None."""
    response = MagicMock()
    response.content = []
    response.stop_reason = stop_reason
    response.parsed_output = None
    response.usage.input_tokens = 100
    response.usage.output_tokens = 0
    return response


@pytest.fixture(autouse=True)
def _fresh_gateway(mock_ai_gateway):
    """Every test drives the real gateway over a mocked Anthropic client."""
    from agents.ai_gateway import reset_gateway

    reset_gateway()
    yield mock_ai_gateway
    reset_gateway()


class TestDecisionLetterAnalyzer:
    def test_returns_the_validated_payload(self, _fresh_gateway):
        _fresh_gateway.messages.parse.return_value = _parsed(
            DecisionLetterAnalysisResponse(
                summary="Tinnitus granted at 10%. PTSD denied for nexus.",
                conditions_granted=[{"condition": "Tinnitus", "rating": 10}],
                evidence_issues=["No nexus letter"],
            )
        )

        result = DecisionLetterAnalyzer().analyze("... decision letter text ...")

        assert result["summary"].startswith("Tinnitus granted")
        assert result["conditions_granted"][0]["condition"] == "Tinnitus"
        assert result["_tokens_used"] == 1000

    def test_every_schema_key_is_present_even_when_the_model_omits_it(
        self, _fresh_gateway
    ):
        """Templates index into these lists; they must not be missing."""
        _fresh_gateway.messages.parse.return_value = _parsed(
            DecisionLetterAnalysisResponse(summary="Terse response.")
        )

        result = DecisionLetterAnalyzer().analyze("...")

        for key in (
            "conditions_granted",
            "conditions_denied",
            "conditions_deferred",
            "appeal_options",
            "action_items",
            "evidence_issues",
        ):
            assert result[key] == [], f"{key} missing from the payload"

    def test_it_goes_through_the_schema_enforced_endpoint(self, _fresh_gateway):
        """parse(), not create() — the schema is enforced API-side."""
        _fresh_gateway.messages.parse.return_value = _parsed(
            DecisionLetterAnalysisResponse(summary="ok")
        )

        DecisionLetterAnalyzer().analyze("...")

        assert _fresh_gateway.messages.parse.called
        assert not _fresh_gateway.messages.create.called
        kwargs = _fresh_gateway.messages.parse.call_args.kwargs
        assert kwargs["output_format"] is DecisionLetterAnalysisResponse

    def test_an_unusable_response_raises_instead_of_saving_an_empty_analysis(
        self, _fresh_gateway
    ):
        """
        The regression that matters. This used to return {}, which the view
        stored as a completed analysis and showed the veteran as blank.
        """
        _fresh_gateway.messages.parse.return_value = _unsatisfiable()

        with pytest.raises(Exception, match="AI API error"):
            DecisionLetterAnalyzer().analyze("...")


class TestEvidenceGapAnalyzer:
    def test_returns_the_validated_payload(self, _fresh_gateway):
        _fresh_gateway.messages.parse.return_value = _parsed(
            EvidenceGapAnalysisResponse(
                readiness_score=42,
                readiness_explanation="Nexus evidence missing.",
                evidence_gaps=[
                    {
                        "condition": "Knee",
                        "gap_type": "nexus",
                        "description": "No medical opinion linking to service",
                        "priority": "critical",
                        "how_to_obtain": "Ask your treating physician",
                    }
                ],
            )
        )

        result = EvidenceGapAnalyzer().analyze(["Knee"], [])

        assert result["readiness_score"] == 42
        assert result["evidence_gaps"][0]["priority"] == "critical"

    def test_an_unusable_response_raises(self, _fresh_gateway):
        _fresh_gateway.messages.parse.return_value = _unsatisfiable()

        with pytest.raises(Exception, match="AI API error"):
            EvidenceGapAnalyzer().analyze(["Knee"], [])


class TestPersonalStatementGenerator:
    def test_returns_the_validated_payload(self, _fresh_gateway):
        _fresh_gateway.messages.parse.return_value = _parsed(
            PersonalStatementResponse(
                statement="On patrol in 2004 I was exposed to...",
                word_count=9,
                strength_assessment="strong",
            )
        )

        result = PersonalStatementGenerator().generate(
            condition="PTSD",
            in_service_event="Convoy ambush",
            current_symptoms="Nightmares",
            daily_impact="Cannot sleep",
        )

        assert result["statement"].startswith("On patrol")
        assert result["strength_assessment"] == "strong"

    def test_an_unusable_response_raises(self, _fresh_gateway):
        _fresh_gateway.messages.parse.return_value = _unsatisfiable()

        with pytest.raises(Exception, match="AI API error"):
            PersonalStatementGenerator().generate(
                condition="PTSD",
                in_service_event="Convoy ambush",
                current_symptoms="Nightmares",
                daily_impact="Cannot sleep",
            )


class TestDenialDecoder:
    def test_returns_the_validated_payload(self, _fresh_gateway):
        _fresh_gateway.messages.parse.return_value = _parsed(
            DenialDecoderResponse(
                va_standard="at least as likely as not",
                suggested_actions=["Request a nexus letter"],
            )
        )

        result = DenialDecoderService()._generate_enhanced_guidance(
            {"condition": "Knee", "denial_reason": "No nexus"},
            matched_sections=[],
            base_evidence=[],
        )

        assert result["va_standard"] == "at least as likely as not"
        assert result["suggested_actions"] == ["Request a nexus letter"]

    def test_it_still_falls_back_to_base_evidence_on_failure(self, _fresh_gateway):
        """
        This agent deliberately degrades rather than raising — its caller
        decodes a list of denials and one bad response must not lose the rest.
        That existing contract has to survive the migration.
        """
        _fresh_gateway.messages.parse.return_value = _unsatisfiable()
        base_evidence = [{"type": "nexus", "description": "Nexus letter"}]

        result = DenialDecoderService()._generate_enhanced_guidance(
            {"condition": "Knee", "denial_reason": "No nexus"},
            matched_sections=[],
            base_evidence=base_evidence,
        )

        assert result["required_evidence"] == base_evidence
        assert result["suggested_actions"]


class TestRemainingFreeTextPath:
    """
    ``generate_strategy`` returns prose and legitimately keeps the legacy
    parser — there is no schema for 3-5 paragraphs of advice. Pinned so the
    exception stays deliberate rather than becoming an oversight again.
    """

    def test_strategy_is_returned_as_text(self, _fresh_gateway):
        response = MagicMock()
        block = MagicMock()
        block.type = "text"
        block.text = "Address the knee denial first, then the back."
        response.content = [block]
        response.stop_reason = "end_turn"
        response.usage.input_tokens = 10
        response.usage.output_tokens = 20
        _fresh_gateway.messages.create.return_value = response

        strategy = DenialDecoderService().generate_strategy(
            [{"condition": "Knee", "denial_reason": "No nexus"}]
        )

        assert strategy.startswith("Address the knee denial")

    def test_only_one_legacy_parser_call_site_remains(self):
        """
        A tripwire: new agents must not reach for the unvalidated path.

        Counts invocations (``self._parse_json_response(``) rather than every
        mention, so the docstrings explaining why it is deprecated do not make
        the check meaningless.
        """
        import inspect

        import agents.services

        source = inspect.getsource(agents.services)
        call_sites = source.count("self._parse_json_response(")

        assert call_sites == 1, (
            f"{call_sites} call sites — anything storing or rendering a model "
            f"response should use _call_structured with a schema instead."
        )
