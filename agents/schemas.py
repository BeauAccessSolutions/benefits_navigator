"""
Pydantic schemas for AI agent responses.

These schemas define the expected structure of AI-generated responses,
enabling validation and type safety.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# =============================================================================
# DECISION LETTER ANALYZER SCHEMAS
# =============================================================================


class GrantedCondition(BaseModel):
    """A condition that was granted in a VA decision."""

    condition: str
    rating: int = Field(ge=0, le=100)
    effective_date: Optional[str] = None
    diagnostic_code: Optional[str] = None
    notes: Optional[str] = None


class DeniedCondition(BaseModel):
    """A condition that was denied in a VA decision."""

    condition: str
    denial_reason: str
    denial_category: Literal[
        "service_connection", "rating_level", "evidence", "procedural"
    ] = "evidence"
    evidence_issue: Optional[str] = None
    appealable: bool = True
    best_appeal_lane: Literal["supplemental", "hlr", "board"] = "supplemental"
    appeal_rationale: Optional[str] = None


class DeferredCondition(BaseModel):
    """A condition that was deferred in a VA decision."""

    condition: str
    reason: str
    expected_action: Optional[str] = None


class AppealOption(BaseModel):
    """An appeal option available to the veteran."""

    type: str
    best_for: str
    deadline: str
    recommended: bool = False
    recommendation_reason: Optional[str] = None


class DecisionLetterAnalysisResponse(BaseModel):
    """Complete response from decision letter analysis."""

    decision_date: Optional[str] = None
    conditions_granted: List[GrantedCondition] = Field(default_factory=list)
    conditions_denied: List[DeniedCondition] = Field(default_factory=list)
    conditions_deferred: List[DeferredCondition] = Field(default_factory=list)
    combined_rating: Optional[int] = None
    evidence_issues: List[str] = Field(default_factory=list)
    appeal_options: List[AppealOption] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    summary: str = ""
    m21_references: List[str] = Field(default_factory=list)


# =============================================================================
# EVIDENCE GAP ANALYZER SCHEMAS
# =============================================================================


class EvidenceGap(BaseModel):
    """An identified gap in evidence."""

    condition: str
    gap_type: str
    m21_requirement: Optional[str] = None
    description: str
    priority: Literal["critical", "important", "helpful"]
    how_to_obtain: str
    estimated_impact: Optional[str] = None


class ConditionStrength(BaseModel):
    """Strength assessment for a specific condition."""

    current_strength: Literal["strong", "moderate", "weak"]
    current_disability_evidence: Literal["strong", "moderate", "weak"] = "moderate"
    in_service_evidence: Literal["strong", "moderate", "weak"] = "moderate"
    nexus_evidence: Literal["strong", "moderate", "weak"] = "moderate"
    severity_evidence: Literal["strong", "moderate", "weak"] = "moderate"
    key_issue: Optional[str] = None
    m21_reference: Optional[str] = None


class EvidenceRecommendation(BaseModel):
    """A recommendation for gathering evidence."""

    action: str
    priority: int
    condition: str
    expected_benefit: str
    how_to_request: Optional[str] = None


class TemplateSuggestion(BaseModel):
    """A suggested template for the veteran."""

    template: str
    for_condition: str
    purpose: str


class EvidenceGapAnalysisResponse(BaseModel):
    """Complete response from evidence gap analysis."""

    evidence_gaps: List[EvidenceGap] = Field(default_factory=list)
    strength_assessment: Dict[str, ConditionStrength] = Field(default_factory=dict)
    recommendations: List[EvidenceRecommendation] = Field(default_factory=list)
    templates_suggested: List[TemplateSuggestion] = Field(default_factory=list)
    readiness_score: int = Field(ge=0, le=100, default=0)
    readiness_explanation: str = ""
    m21_references_used: List[str] = Field(default_factory=list)


# =============================================================================
# PERSONAL STATEMENT GENERATOR SCHEMAS
# =============================================================================


class PersonalStatementResponse(BaseModel):
    """Response from personal statement generation."""

    statement: str
    word_count: int = 0
    key_points_covered: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    strength_assessment: Literal["strong", "moderate", "needs_work"] = "moderate"
    m21_elements_addressed: List[str] = Field(default_factory=list)


# =============================================================================
# DENIAL DECODER SCHEMAS
# =============================================================================


class RequiredEvidence(BaseModel):
    """Evidence required to overcome a denial."""

    type: str
    description: str
    priority: Literal["critical", "important", "helpful"]
    tips: List[str] = Field(default_factory=list)
    m21_reference: Optional[str] = None


class DenialDecoderResponse(BaseModel):
    """Response from denial decoder enhanced guidance."""

    required_evidence: List[RequiredEvidence] = Field(default_factory=list)
    suggested_actions: List[str] = Field(default_factory=list)
    va_standard: str = ""
    common_mistakes: List[str] = Field(default_factory=list)


# =============================================================================
# RATING DECISION ANALYZER SCHEMAS
# =============================================================================


class RatedCondition(BaseModel):
    """A condition with its rating from a rating decision."""

    name: str
    diagnostic_code: Optional[str] = None
    rating_percentage: int = Field(ge=0, le=100)
    effective_date: Optional[str] = None
    rating_criteria_cited: Optional[str] = None
    criteria_for_next_higher: Optional[str] = None
    service_connection_type: Literal[
        "direct", "secondary", "presumptive", "aggravation"
    ] = "direct"
    linked_to_condition: Optional[str] = None


class IncreaseOpportunity(BaseModel):
    """An opportunity to increase a rating."""

    condition: str
    current_rating: int
    current_diagnostic_code: Optional[str] = None
    target_rating: int
    strategy: str
    key_symptoms_to_document: List[str] = Field(default_factory=list)
    relevant_diagnostic_codes: List[str] = Field(default_factory=list)
    dual_rating_opportunity: Optional[str] = None
    flare_up_documentation: Optional[str] = None
    evidence_needed: List[str] = Field(default_factory=list)
    secondary_conditions_to_claim: List[str] = Field(default_factory=list)


class SecondaryCondition(BaseModel):
    """A potential secondary condition to claim."""

    potential_condition: str
    connect_to: str
    medical_rationale: str
    evidence_needed: List[str] = Field(default_factory=list)
    typical_rating_range: str = ""


class RatingError(BaseModel):
    """A potential error in a rating decision."""

    condition: str
    error_type: Literal["procedural", "factual", "legal"]
    description: str
    remedy: str
    strength: Literal["strong", "moderate", "weak"]


class EffectiveDateIssue(BaseModel):
    """A potential effective date issue."""

    condition: str
    current_effective_date: str
    potential_earlier_date: str
    basis: str
    evidence_needed: List[str] = Field(default_factory=list)


class DeadlineTracker(BaseModel):
    """Deadline tracking information."""

    decision_date: Optional[str] = None
    appeal_deadline: Optional[str] = None
    appeal_deadline_passed: bool = False
    days_remaining: Optional[int] = None
    hlr_available: bool = True
    board_appeal_available: bool = True
    supplemental_claim_note: str = "Can file anytime with new evidence"


class BenefitUnlocked(BaseModel):
    """A benefit unlocked by the current rating."""

    benefit: str
    eligibility_basis: str
    how_to_claim: str
    estimated_value: Optional[str] = None


class ExamPrepTip(BaseModel):
    """C&P exam preparation guidance."""

    condition: str
    exam_type: str
    what_examiner_looks_for: List[str] = Field(default_factory=list)
    do_before_exam: List[str] = Field(default_factory=list)
    common_mistakes: List[str] = Field(default_factory=list)
    documentation_to_bring: List[str] = Field(default_factory=list)


class PriorityAction(BaseModel):
    """A prioritized action item."""

    priority: int
    action: str
    why: str
    deadline: Optional[str] = None
    difficulty: Literal["easy", "moderate", "complex"] = "moderate"


class ConfidenceFactor(BaseModel):
    """A factor affecting confidence in the analysis."""

    type: Literal["info", "warning", "limitation"]
    aspect: str
    message: str


class ConfidenceScoring(BaseModel):
    """Confidence scoring for the analysis."""

    overall_confidence: int = Field(ge=0, le=100, default=0)
    extraction_quality: int = Field(ge=0, le=100, default=0)
    document_completeness: int = Field(ge=0, le=100, default=0)
    analysis_reliability: int = Field(ge=0, le=100, default=0)
    confidence_factors: List[ConfidenceFactor] = Field(default_factory=list)


class RatingExtractionResponse(BaseModel):
    """Response from rating decision extraction (phase 1)."""

    veteran_name: Optional[str] = None
    file_number: Optional[str] = None
    decision_date: Optional[str] = None
    combined_rating: Optional[int] = None
    conditions: List[RatedCondition] = Field(default_factory=list)
    evidence_list: List[str] = Field(default_factory=list)
    monthly_compensation: Optional[float] = None
    dependents_status: Optional[str] = None


class RatingAnalysisResponse(BaseModel):
    """Response from rating decision analysis (phase 2)."""

    confidence_scoring: ConfidenceScoring = Field(default_factory=ConfidenceScoring)
    increase_opportunities: List[IncreaseOpportunity] = Field(default_factory=list)
    secondary_conditions: List[SecondaryCondition] = Field(default_factory=list)
    rating_errors: List[RatingError] = Field(default_factory=list)
    effective_date_issues: List[EffectiveDateIssue] = Field(default_factory=list)
    deadline_tracker: DeadlineTracker = Field(default_factory=DeadlineTracker)
    benefits_unlocked: List[BenefitUnlocked] = Field(default_factory=list)
    exam_prep_tips: List[ExamPrepTip] = Field(default_factory=list)
    priority_actions: List[PriorityAction] = Field(default_factory=list)


# =============================================================================
# DOCUMENT ANALYSIS SCHEMA (for AIService)
# =============================================================================


class DocumentAnalysisResponse(BaseModel):
    """Generic document analysis response."""

    summary: str
    key_points: List[str] = Field(default_factory=list)
    document_type: Optional[str] = None
    extracted_dates: List[str] = Field(default_factory=list)
    extracted_conditions: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
