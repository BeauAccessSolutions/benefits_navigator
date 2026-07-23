"""
AI Agents for VA Benefits Navigator

Models for storing agent interactions, analyses, and generated content.
"""

from django.db import models
from django.conf import settings
from core.models import TimeStampedModel
from core.encryption import EncryptedCharField, EncryptedTextField


class AgentInteraction(TimeStampedModel):
    """
    Base model for tracking all agent interactions.
    Stores input, output, and metadata for each agent use.
    """

    AGENT_TYPES = [
        ("decision_analyzer", "Decision Letter Analyzer"),
        ("evidence_gap", "Evidence Gap Analyzer"),
        ("statement_generator", "Personal Statement Generator"),
        ("rating_analyzer", "Rating Decision Analyzer"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_interactions",
    )
    agent_type = models.CharField(max_length=50, choices=AGENT_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    # Token usage tracking
    tokens_used = models.IntegerField(default=0)
    cost_estimate = models.DecimalField(max_digits=10, decimal_places=6, default=0)

    # Error tracking
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "agent_type"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return (
            f"{self.get_agent_type_display()} - {self.user.email} - {self.created_at}"
        )


class DecisionLetterAnalysis(TimeStampedModel):
    """
    Stores analysis of VA decision letters.
    """

    interaction = models.OneToOneField(
        AgentInteraction, on_delete=models.CASCADE, related_name="decision_analysis"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="decision_analyses",
    )

    # Input
    document = models.ForeignKey(
        "claims.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Linked uploaded document",
    )
    # NOTE: raw_text field removed for PHI protection (Ephemeral OCR Refactor PR 6)
    # Raw text is no longer persisted - only structured analysis is stored
    decision_date = models.DateField(null=True, blank=True)

    # Parsed Results (stored as JSON)
    conditions_granted = models.JSONField(
        default=list, help_text="List of granted conditions with ratings"
    )
    conditions_denied = models.JSONField(
        default=list, help_text="List of denied conditions with reasons"
    )
    conditions_deferred = models.JSONField(
        default=list, help_text="List of deferred conditions"
    )

    # Analysis
    summary = models.TextField(blank=True, help_text="Plain-English summary")
    appeal_options = models.JSONField(
        default=list, help_text="Available appeal paths with deadlines"
    )
    evidence_issues = models.JSONField(
        default=list, help_text="Evidence problems identified"
    )
    action_items = models.JSONField(default=list, help_text="Recommended next steps")

    # Deadlines
    appeal_deadline = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Decision Letter Analysis"
        verbose_name_plural = "Decision Letter Analyses"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"Decision Analysis - {self.user.email} - {self.created_at.date()}"


class DenialDecoding(TimeStampedModel):
    """
    Enhanced analysis linking VA denial reasons to M21 manual sections
    with specific evidence guidance for overcoming each denial.

    This model extends DecisionLetterAnalysis with M21 matching and
    evidence requirements to help veterans understand exactly what
    they need to prove their case.
    """

    analysis = models.OneToOneField(
        DecisionLetterAnalysis, on_delete=models.CASCADE, related_name="denial_decoding"
    )

    # Each denial mapped to M21 sections with evidence guidance
    # Format: [
    #     {
    #         "condition": "PTSD",
    #         "denial_reason": "No nexus to service",
    #         "denial_category": "nexus",
    #         "matched_m21_sections": [
    #             {"reference": "M21-1.V.ii.2.A", "title": "...", "relevance_score": 0.95, "key_excerpt": "..."}
    #         ],
    #         "required_evidence": [
    #             {"type": "nexus_letter", "description": "...", "priority": "critical", "tips": ["..."]}
    #         ],
    #         "suggested_actions": ["Get IMO from treating psychiatrist", "..."],
    #         "va_standard": "At least as likely as not (50%+)",
    #         "common_mistakes": ["Using unqualified medical opinion", "..."]
    #     }
    # ]
    denial_mappings = models.JSONField(
        "Denial Mappings",
        default=list,
        help_text="Denials with M21 matches and evidence requirements",
    )

    # AI-generated overall strategy for addressing all denials
    evidence_strategy = models.TextField(
        "Evidence Strategy",
        blank=True,
        help_text="AI-generated overall strategy for addressing denials",
    )

    # Priority ranking of which denial to address first
    priority_order = models.JSONField(
        "Priority Order",
        default=list,
        blank=True,
        help_text="Recommended order to address denials",
    )

    # Processing metadata
    m21_sections_searched = models.IntegerField(
        "M21 Sections Searched", default=0, help_text="Number of M21 sections searched"
    )
    processing_time_seconds = models.FloatField(
        "Processing Time", default=0, help_text="Time taken to decode denials"
    )

    class Meta:
        verbose_name = "Denial Decoding"
        verbose_name_plural = "Denial Decodings"
        ordering = ["-created_at"]

    def __str__(self):
        denial_count = len(self.denial_mappings) if self.denial_mappings else 0
        return f"Denial Decoding ({denial_count} denials) - {self.analysis.user.email}"

    @property
    def denial_count(self):
        """Number of denials analyzed."""
        return len(self.denial_mappings) if self.denial_mappings else 0

    @property
    def critical_evidence_count(self):
        """Count of critical evidence items needed across all denials."""
        count = 0
        for denial in self.denial_mappings or []:
            for evidence in denial.get("required_evidence", []):
                if evidence.get("priority") == "critical":
                    count += 1
        return count


class EvidenceGapAnalysis(TimeStampedModel):
    """
    Stores evidence gap analysis for claims.
    """

    interaction = models.OneToOneField(
        AgentInteraction, on_delete=models.CASCADE, related_name="evidence_analysis"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="evidence_analyses",
    )

    # Input
    claimed_conditions = models.JSONField(
        default=list, help_text="Conditions being claimed"
    )
    existing_evidence = models.JSONField(
        default=list, help_text="Evidence already gathered"
    )
    service_dates = models.CharField(max_length=100, blank=True)
    service_branch = models.CharField(max_length=50, blank=True)

    # Analysis Results
    evidence_gaps = models.JSONField(default=list, help_text="Missing evidence items")
    strength_assessment = models.JSONField(
        default=dict, help_text="Current evidence strength by condition"
    )
    recommendations = models.JSONField(
        default=list, help_text="Prioritized recommendations"
    )
    templates_suggested = models.JSONField(
        default=list, help_text="Relevant templates/forms"
    )

    # Overall Score
    readiness_score = models.IntegerField(
        default=0, help_text="0-100 claim readiness score"
    )

    class Meta:
        verbose_name = "Evidence Gap Analysis"
        verbose_name_plural = "Evidence Gap Analyses"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"Evidence Analysis - {self.user.email} - {self.created_at.date()}"


class PersonalStatement(TimeStampedModel):
    """
    Stores generated personal statements.
    """

    interaction = models.OneToOneField(
        AgentInteraction, on_delete=models.CASCADE, related_name="personal_statement"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_statements",
    )

    # Input - Veteran's Story
    condition = models.CharField(
        max_length=200, help_text="Condition this statement supports"
    )
    # PHI: the veteran's own service/medical narrative. Encrypted at rest.
    in_service_event = EncryptedTextField(help_text="What happened during service")
    current_symptoms = EncryptedTextField(help_text="Current symptoms and limitations")
    daily_impact = EncryptedTextField(help_text="How condition affects daily life")
    work_impact = EncryptedTextField(blank=True, help_text="How condition affects work")
    treatment_history = EncryptedTextField(blank=True, help_text="Treatment received")
    worst_days = EncryptedTextField(
        blank=True, help_text="Description of worst days/flare-ups"
    )

    # Generated Output
    generated_statement = EncryptedTextField(
        blank=True, help_text="AI-generated statement"
    )

    # User Edits
    final_statement = EncryptedTextField(
        blank=True, help_text="User-edited final version"
    )
    is_finalized = models.BooleanField(default=False)

    # Metadata
    word_count = models.IntegerField(default=0)
    statement_type = models.CharField(
        max_length=50,
        choices=[
            ("initial", "Initial Claim"),
            ("increase", "Increase Request"),
            ("secondary", "Secondary Condition"),
            ("appeal", "Appeal Statement"),
        ],
        default="initial",
    )

    class Meta:
        verbose_name = "Personal Statement"
        verbose_name_plural = "Personal Statements"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Statement: {self.condition} - {self.user.email}"

    def save(self, *args, **kwargs):
        # Update word count
        text = self.final_statement or self.generated_statement
        self.word_count = len(text.split()) if text else 0
        super().save(*args, **kwargs)


class RatingAnalysis(TimeStampedModel):
    """
    Stores actionable analysis of VA rating decisions.

    This model captures the enhanced analysis that goes beyond basic
    extraction to identify increase opportunities, secondary conditions,
    potential errors, and strategic next steps.
    """

    interaction = models.OneToOneField(
        AgentInteraction,
        on_delete=models.CASCADE,
        related_name="rating_analysis",
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rating_analyses",
    )

    # Input
    document = models.ForeignKey(
        "claims.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Linked uploaded document",
    )
    # NOTE: raw_text field removed for PHI protection (Ephemeral OCR Refactor PR 6)
    # Raw text is no longer persisted - only structured analysis is stored
    decision_date = models.DateField(null=True, blank=True)

    # Extracted Data (from extraction phase)
    veteran_name = models.CharField(max_length=200, blank=True)
    file_number = EncryptedCharField(
        max_length=255,  # Larger to accommodate encrypted data
        blank=True,
        help_text="VA file number (encrypted)",
    )
    combined_rating = models.IntegerField(
        null=True, blank=True, help_text="Combined disability rating percentage"
    )
    monthly_compensation = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Monthly compensation amount",
    )

    # Extracted conditions with ratings
    # Format: [{"name": "...", "diagnostic_code": "DC XXXX", "rating_percentage": 30,
    #          "effective_date": "YYYY-MM-DD", "rating_criteria_cited": "...",
    #          "criteria_for_next_higher": "...", "service_connection_type": "direct|secondary|presumptive"}]
    conditions = models.JSONField(
        "Rated Conditions",
        default=list,
        help_text="List of conditions with ratings and diagnostic codes",
    )
    evidence_list = models.JSONField(
        "Evidence Reviewed", default=list, help_text="List of evidence VA reviewed"
    )

    # Analysis Results
    # Format: [{"condition": "...", "current_rating": 10, "target_rating": 20,
    #          "strategy": "...", "key_symptoms_to_document": [...],
    #          "dual_rating_opportunity": "...", "evidence_needed": [...]}]
    increase_opportunities = models.JSONField(
        "Increase Opportunities",
        default=list,
        help_text="Opportunities to increase ratings for each condition",
    )

    # Format: [{"potential_condition": "...", "connect_to": "...",
    #          "medical_rationale": "...", "evidence_needed": [...], "typical_rating_range": "..."}]
    secondary_conditions = models.JSONField(
        "Secondary Conditions",
        default=list,
        help_text="Potential secondary conditions to claim",
    )

    # Format: [{"condition": "...", "error_type": "procedural|factual|legal",
    #          "description": "...", "remedy": "...", "strength": "strong|moderate|weak"}]
    rating_errors = models.JSONField(
        "Potential Rating Errors",
        default=list,
        help_text="Potential errors in the rating decision",
    )

    # Format: [{"condition": "...", "current_effective_date": "...",
    #          "potential_earlier_date": "...", "basis": "...", "evidence_needed": [...]}]
    effective_date_issues = models.JSONField(
        "Effective Date Issues",
        default=list,
        help_text="Potential issues with effective dates",
    )

    # Deadline tracking
    # Format: {"decision_date": "...", "appeal_deadline": "...", "appeal_deadline_passed": bool,
    #         "days_remaining": int, "hlr_available": bool, "supplemental_claim_note": "..."}
    deadline_tracker = models.JSONField(
        "Deadline Tracker", default=dict, help_text="Appeal deadlines and availability"
    )

    # Format: [{"benefit": "...", "eligibility_basis": "...", "how_to_claim": "...", "estimated_value": "..."}]
    benefits_unlocked = models.JSONField(
        "Benefits Unlocked",
        default=list,
        help_text="Benefits veteran is eligible for at current rating",
    )

    # Format: [{"condition": "...", "exam_type": "...", "what_examiner_looks_for": [...],
    #          "do_before_exam": [...], "common_mistakes": [...], "documentation_to_bring": [...]}]
    exam_prep_tips = models.JSONField(
        "Exam Prep Tips", default=list, help_text="C&P exam preparation guidance"
    )

    # Format: [{"priority": 1, "action": "...", "why": "...", "deadline": "...", "difficulty": "easy|moderate|complex"}]
    priority_actions = models.JSONField(
        "Priority Actions",
        default=list,
        help_text="Prioritized list of recommended actions",
    )

    # Simple markdown analysis (alternative output format)
    markdown_analysis = models.TextField(
        "Markdown Analysis",
        blank=True,
        help_text="Human-readable markdown-formatted analysis",
    )

    # AI Confidence Scoring
    # Overall confidence in the analysis quality (0-100)
    overall_confidence = models.IntegerField(
        "Overall Confidence",
        default=0,
        help_text="AI confidence score for overall analysis quality (0-100)",
    )
    # Format: {"extraction_quality": 85, "document_completeness": 70, "analysis_reliability": 80}
    confidence_breakdown = models.JSONField(
        "Confidence Breakdown",
        default=dict,
        help_text="Detailed confidence scores for different aspects",
    )
    # Factors that may affect analysis quality
    confidence_factors = models.JSONField(
        "Confidence Factors",
        default=list,
        help_text="Factors that influenced confidence scoring",
    )

    # Processing metadata
    processing_time_seconds = models.FloatField(
        "Processing Time",
        default=0,
        help_text="Time taken to analyze the rating decision",
    )
    tokens_used = models.IntegerField(
        "Tokens Used", default=0, help_text="Total OpenAI tokens used"
    )
    cost_estimate = models.DecimalField(
        "Cost Estimate",
        max_digits=10,
        decimal_places=6,
        default=0,
        help_text="Estimated API cost",
    )

    class Meta:
        verbose_name = "Rating Analysis"
        verbose_name_plural = "Rating Analyses"
        ordering = ["-created_at"]

    def __str__(self):
        rating_str = f"{self.combined_rating}%" if self.combined_rating else "Unknown"
        return f"Rating Analysis ({rating_str}) - {self.user.email} - {self.created_at.date()}"

    @property
    def condition_count(self):
        """Number of rated conditions."""
        return len(self.conditions) if self.conditions else 0

    @property
    def increase_opportunity_count(self):
        """Number of increase opportunities identified."""
        return len(self.increase_opportunities) if self.increase_opportunities else 0

    @property
    def secondary_condition_count(self):
        """Number of potential secondary conditions identified."""
        return len(self.secondary_conditions) if self.secondary_conditions else 0

    @property
    def has_appeal_deadline_passed(self):
        """Check if the 1-year appeal window has closed."""
        if self.deadline_tracker:
            return self.deadline_tracker.get("appeal_deadline_passed", True)
        return True

    @property
    def days_until_deadline(self):
        """Days remaining until appeal deadline."""
        if self.deadline_tracker:
            return self.deadline_tracker.get("days_remaining")
        return None

    def get_priority_actions(self, limit=5):
        """Return top priority actions."""
        actions = self.priority_actions or []
        sorted_actions = sorted(actions, key=lambda x: x.get("priority", 99))
        return sorted_actions[:limit]

    def get_critical_actions(self):
        """Return actions that have deadlines or are marked critical."""
        actions = self.priority_actions or []
        return [a for a in actions if a.get("deadline") or a.get("priority", 99) <= 2]

    @property
    def confidence_level(self):
        """Return confidence level as a human-readable string."""
        if self.overall_confidence >= 85:
            return "high"
        elif self.overall_confidence >= 70:
            return "medium"
        elif self.overall_confidence >= 50:
            return "low"
        else:
            return "very_low"

    @property
    def confidence_display(self):
        """Return confidence with display label."""
        labels = {
            "high": "High Confidence",
            "medium": "Medium Confidence",
            "low": "Low Confidence",
            "very_low": "Very Low Confidence",
        }
        return labels.get(self.confidence_level, "Unknown")

    def get_confidence_warnings(self):
        """Return any warnings based on confidence factors."""
        warnings = []
        factors = self.confidence_factors or []

        for factor in factors:
            if factor.get("type") == "warning":
                warnings.append(factor.get("message", ""))

        if self.overall_confidence < 70:
            warnings.append(
                "This analysis has lower confidence. Consider consulting a VSO "
                "or accredited claims agent for verification."
            )

        return warnings


class M21ManualSection(TimeStampedModel):
    """
    M21-1 Adjudication Procedures Manual sections scraped from KnowVA.

    The M21-1 is VA's internal manual for processing claims. It contains critical
    information about how VA applies laws and regulations.
    """

    # Hierarchical identifiers
    part = models.CharField(
        "Part (Roman numeral)", max_length=10, help_text="Part number: I, II, III, etc."
    )
    part_number = models.IntegerField(
        "Part (integer)", help_text="Numeric version of part for sorting"
    )
    part_title = models.CharField("Part Title", max_length=200, blank=True)
    subpart = models.CharField(
        "Subpart (lowercase Roman)",
        max_length=10,
        help_text="Subpart: i, ii, iii, etc.",
    )
    chapter = models.CharField("Chapter", max_length=10, help_text="Chapter number")
    section = models.CharField(
        "Section (Letter)", max_length=5, help_text="Section letter: A, B, C, etc."
    )

    # Content
    title = models.CharField("Section Title", max_length=500)
    reference = models.CharField(
        "Reference Code", max_length=50, unique=True, help_text="Format: M21-1.I.i.1.A"
    )
    full_reference = models.CharField(
        "Full Reference",
        max_length=200,
        blank=True,
        help_text="Format: M21-1, Part I, Subpart i, Chapter 1, Section A",
    )

    # Main content
    overview = models.TextField(
        "Overview", blank=True, help_text="Introduction/overview of this section"
    )
    content = models.TextField(
        "Full Content", help_text="Complete section content in HTML/markdown"
    )

    # Topics within section (stored as JSON)
    # Format: [{"code": "I.i.1.A.1.a", "title": "...", "content": "..."}]
    topics = models.JSONField(
        "Topics",
        default=list,
        blank=True,
        help_text="Structured topics within this section",
    )

    # Cross-references (stored as JSON list)
    references = models.JSONField(
        "Cross References",
        default=list,
        blank=True,
        help_text="Referenced M21-1 sections and CFR citations",
    )

    # KnowVA metadata
    article_id = models.CharField(
        "KnowVA Article ID",
        max_length=50,
        blank=True,
        unique=True,
        null=True,
        help_text="Original KnowVA article identifier",
    )
    knowva_url = models.URLField("KnowVA URL", max_length=1000, blank=True)
    last_updated_va = models.DateTimeField(
        "Last Updated (VA)",
        null=True,
        blank=True,
        help_text="Last updated date from KnowVA",
    )

    # Scraping metadata
    scraped_at = models.DateTimeField(
        "Scraped At", auto_now_add=True, help_text="When we scraped this content"
    )
    last_scraped = models.DateTimeField(
        "Last Scraped", auto_now=True, help_text="Last time we updated this from KnowVA"
    )
    scrape_status = models.CharField(
        "Scrape Status",
        max_length=20,
        choices=[
            ("success", "Success"),
            ("failed", "Failed"),
            ("stale", "Stale (needs update)"),
            ("pending", "Pending"),
        ],
        default="success",
    )
    scrape_error = models.TextField("Scrape Error", blank=True)

    # Search optimization
    search_text = models.TextField(
        "Search Text", blank=True, help_text="Denormalized full text for search"
    )

    class Meta:
        verbose_name = "M21-1 Manual Section"
        verbose_name_plural = "M21-1 Manual Sections"
        ordering = ["part_number", "subpart", "chapter", "section"]
        indexes = [
            models.Index(fields=["part_number", "subpart", "chapter", "section"]),
            models.Index(fields=["reference"]),
            models.Index(fields=["article_id"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.title}"

    def save(self, *args, **kwargs):
        # Auto-populate search_text for full-text search
        if not self.search_text:
            search_parts = [
                self.reference,
                self.title,
                self.overview,
                self.content,
            ]
            # Add topic content
            for topic in self.topics:
                search_parts.append(topic.get("title", ""))
                search_parts.append(topic.get("content", ""))

            self.search_text = " ".join(filter(None, search_parts))

        super().save(*args, **kwargs)


class M21TopicIndex(TimeStampedModel):
    """
    Topic-based index for M21 sections.
    Allows agents to quickly find relevant M21 sections by topic.
    """

    TOPIC_CHOICES = [
        ("service_connection", "Service Connection"),
        ("rating_process", "Rating Process"),
        ("evidence", "Evidence Requirements"),
        ("examinations", "C&P Examinations"),
        ("effective_dates", "Effective Dates"),
        ("appeals", "Appeals Process"),
        ("mental_health", "Mental Health Conditions"),
        ("musculoskeletal", "Musculoskeletal Conditions"),
        ("special_monthly_compensation", "Special Monthly Compensation (SMC)"),
        ("tdiu", "Total Disability Individual Unemployability (TDIU)"),
        ("presumptive", "Presumptive Service Connection"),
        ("secondary", "Secondary Service Connection"),
        ("nexus", "Nexus / Medical Opinion"),
        ("duty_to_assist", "Duty to Assist"),
        ("errors", "Clear and Unmistakable Error (CUE)"),
        ("dependents", "Dependents and Dependency"),
        ("combined_ratings", "Combined Ratings"),
        ("extraschedular", "Extraschedular Ratings"),
    ]

    topic = models.CharField("Topic", max_length=50, choices=TOPIC_CHOICES)
    title = models.CharField("Topic Title", max_length=200)
    description = models.TextField("Description", help_text="What this topic covers")

    # Keywords for matching
    keywords = models.JSONField(
        "Keywords",
        default=list,
        help_text="Keywords used to identify relevant sections",
    )

    # Related M21 sections
    sections = models.ManyToManyField(
        M21ManualSection, related_name="topic_indices", blank=True
    )

    # Priority for agents
    priority = models.IntegerField(
        "Priority", default=0, help_text="Higher priority topics shown first to agents"
    )

    class Meta:
        verbose_name = "M21 Topic Index"
        verbose_name_plural = "M21 Topic Indices"
        ordering = ["-priority", "topic"]

    def __str__(self):
        return f"{self.title} ({self.sections.count()} sections)"


class M21ScrapeJob(TimeStampedModel):
    """
    Tracks M21 scraping jobs.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("partial", "Partial Success"),
    ]

    status = models.CharField(
        "Status", max_length=20, choices=STATUS_CHOICES, default="pending"
    )

    # Job parameters
    target_parts = models.JSONField(
        "Target Parts",
        default=list,
        help_text="Which parts to scrape (empty = all)",
        blank=True,
    )
    force_update = models.BooleanField(
        "Force Update", default=False, help_text="Re-scrape even if content exists"
    )

    # Progress tracking
    total_sections = models.IntegerField("Total Sections", default=0)
    sections_completed = models.IntegerField("Sections Completed", default=0)
    sections_failed = models.IntegerField("Sections Failed", default=0)

    # Results
    started_at = models.DateTimeField("Started At", null=True, blank=True)
    completed_at = models.DateTimeField("Completed At", null=True, blank=True)
    error_log = models.TextField("Error Log", blank=True)
    summary = models.JSONField(
        "Summary", default=dict, blank=True, help_text="Summary of what was scraped"
    )

    # Performance
    duration_seconds = models.IntegerField("Duration (seconds)", default=0)

    class Meta:
        verbose_name = "M21 Scrape Job"
        verbose_name_plural = "M21 Scrape Jobs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Scrape Job {self.id} - {self.status} ({self.created_at.date()})"

    @property
    def progress_percentage(self):
        """Calculate completion percentage."""
        if self.total_sections == 0:
            return 0
        return int((self.sections_completed / self.total_sections) * 100)


# =============================================================================
# STREAMING ASSISTANT — persisted conversation (docs/ux/assistant-interactions.md)
# =============================================================================


class AssistantThread(TimeStampedModel):
    """A persisted conversation with the streaming assistant, scoped to one user.

    PHI posture (docs/PHI_DATA_FLOW.md, docs/security-invariants.md): the whole
    transcript is treated as PHI. It inherits user-scoped access controls (the
    ``user`` FK; all queries filter by ``user=request.user``) and is deleted with
    the account (``on_delete=CASCADE``). Turn *content* is never logged. Note the
    assistant answer is model output (allowed to persist) — this is NOT raw OCR
    source text, which remains ephemeral and unpersisted.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistant_threads",
    )

    class Meta:
        verbose_name = "Assistant Thread"
        verbose_name_plural = "Assistant Threads"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"Assistant Thread {self.pk} - {self.user.email}"


class AssistantTurn(TimeStampedModel):
    """One turn in an :class:`AssistantThread` — a user prompt or an assistant answer.

    ``content`` holds either the veteran's typed prompt (``role="user"``) or the
    model's answer (``role="assistant"``). It is treated as PHI: user-scoped,
    account-deletable, never logged. ``stopped`` marks an assistant answer that was
    cut short by the veteran (the partial is kept on purpose — docs/ux §3.3).
    """

    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
    ]

    thread = models.ForeignKey(
        AssistantThread,
        on_delete=models.CASCADE,
        related_name="turns",
    )
    # Denormalized owner FK so ownership can be enforced (and the row deleted with
    # the account) without a join through the thread.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistant_turns",
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    # PHI — see class docstring. Field-level encrypted at rest (Fernet), in
    # addition to user-scoping and account-deletion.
    content = EncryptedTextField(blank=True)
    # True when an assistant answer was interrupted by Stop (partial kept).
    stopped = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Assistant Turn"
        verbose_name_plural = "Assistant Turns"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["thread", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_role_display()} turn {self.pk} (thread {self.thread_id})"
