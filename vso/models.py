"""
VSO App Models - Case Management for Veterans Service Organizations

This module provides models for VSOs to manage veteran cases, track progress,
and collaborate on claims and appeals.
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
from core.models import TimeStampedModel
from core.encryption import EncryptedTextField, EncryptedJSONField


class VeteranCase(TimeStampedModel):
    """
    A case representing a VSO's work with a specific veteran.

    Cases are created when a VSO invites a veteran or a veteran requests
    assistance from an organization. Each case tracks the overall status
    and progress of the veteran's claims journey.
    """

    STATUS_CHOICES = [
        ("intake", "Intake"),
        ("gathering_evidence", "Gathering Evidence"),
        ("claim_filed", "Claim Filed"),
        ("pending_decision", "Pending VA Decision"),
        ("decision_received", "Decision Received"),
        ("appeal_in_progress", "Appeal in Progress"),
        ("closed_won", "Closed - Won"),
        ("closed_denied", "Closed - Denied"),
        ("closed_withdrawn", "Closed - Withdrawn"),
        ("on_hold", "On Hold"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("normal", "Normal"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]

    # Core relationships
    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.CASCADE, related_name="cases"
    )
    veteran = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vso_cases",
        help_text="The veteran this case is for",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_cases",
        help_text="VSO caseworker assigned to this case",
    )

    # Case info
    title = models.CharField(
        "Case title", max_length=200, help_text="Brief description of the case"
    )
    description = EncryptedTextField(
        "Description",
        blank=True,
        help_text="Detailed notes about the case (encrypted at rest)",
    )
    status = models.CharField(
        "Status", max_length=30, choices=STATUS_CHOICES, default="intake"
    )
    priority = models.CharField(
        "Priority", max_length=20, choices=PRIORITY_CHOICES, default="normal"
    )

    # Claimed conditions being worked on
    # Format: [{"condition": "PTSD", "status": "pending", "current_rating": 0, "target_rating": 70}]
    conditions = EncryptedJSONField(
        "Conditions",
        default=list,
        blank=True,
        help_text="List of conditions being claimed (encrypted at rest)",
    )

    # Key dates
    intake_date = models.DateField("Intake date", default=timezone.now)
    claim_filed_date = models.DateField("Claim filed date", null=True, blank=True)
    decision_date = models.DateField("Decision date", null=True, blank=True)
    appeal_deadline = models.DateField("Appeal deadline", null=True, blank=True)
    next_action_date = models.DateField("Next action date", null=True, blank=True)

    # Outcome tracking
    initial_combined_rating = models.IntegerField(
        "Initial combined rating",
        null=True,
        blank=True,
        help_text="Rating at start of case",
    )
    final_combined_rating = models.IntegerField(
        "Final combined rating",
        null=True,
        blank=True,
        help_text="Rating at end of case",
    )
    retroactive_pay = models.DecimalField(
        "Retroactive pay",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Retroactive compensation awarded",
    )

    # Veteran consent
    veteran_consent_date = models.DateTimeField(
        "Consent date",
        null=True,
        blank=True,
        help_text="When veteran consented to VSO access",
    )
    consent_document = models.ForeignKey(
        "claims.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consent_cases",
        help_text="Uploaded VA Form 21-22 or 21-22a",
    )

    # Case closure
    closed_at = models.DateTimeField("Closed at", null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_cases",
    )
    closure_notes = EncryptedTextField("Closure notes", blank=True)

    # Activity tracking for lifecycle hygiene
    last_activity_at = models.DateTimeField("Last Activity", null=True, blank=True)

    # C&P Exam tracking
    c_and_p_exam_date = models.DateField(
        "C&P Exam Date",
        null=True,
        blank=True,
        help_text="Scheduled Compensation & Pension exam date",
    )
    c_and_p_exam_location = models.CharField(
        "C&P Exam Location",
        max_length=255,
        blank=True,
        help_text="Location/facility for the exam",
    )
    c_and_p_exam_notes = EncryptedTextField(
        "C&P Exam Notes",
        blank=True,
        help_text="Notes about the exam (conditions being evaluated, etc.; encrypted at rest)",
    )

    # Archive functionality
    is_archived = models.BooleanField("Archived", default=False)
    archived_at = models.DateTimeField("Archived At", null=True, blank=True)

    class Meta:
        verbose_name = "Veteran Case"
        verbose_name_plural = "Veteran Cases"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["veteran", "organization"]),
            models.Index(fields=["last_activity_at"]),
            models.Index(fields=["is_archived"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.veteran.email}"

    @property
    def is_open(self):
        """Check if case is still open"""
        return not self.status.startswith("closed")

    @property
    def is_overdue(self):
        """Check if next action is overdue"""
        if self.next_action_date:
            return self.next_action_date < timezone.now().date()
        return False

    @property
    def days_open(self):
        """Calculate days since intake"""
        end_date = self.closed_at.date() if self.closed_at else timezone.now().date()
        return (end_date - self.intake_date).days

    @property
    def rating_increase(self):
        """Calculate rating increase achieved"""
        if (
            self.initial_combined_rating is not None
            and self.final_combined_rating is not None
        ):
            return self.final_combined_rating - self.initial_combined_rating
        return None

    def close(self, status, notes="", closed_by=None):
        """Close the case with a final status"""
        self.status = status
        self.closure_notes = notes
        self.closed_at = timezone.now()
        self.closed_by = closed_by
        self.save()


class CaseNote(TimeStampedModel):
    """
    Notes and updates on a veteran case.

    Used by VSO staff to document interactions, progress, and action items.
    """

    NOTE_TYPE_CHOICES = [
        ("general", "General Note"),
        ("phone_call", "Phone Call"),
        ("email", "Email"),
        ("meeting", "Meeting"),
        ("document_review", "Document Review"),
        ("action_item", "Action Item"),
        ("milestone", "Milestone"),
        ("veteran_update", "Veteran Update"),
    ]

    case = models.ForeignKey(
        VeteranCase, on_delete=models.CASCADE, related_name="notes"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="case_notes",
    )

    note_type = models.CharField(
        "Type", max_length=20, choices=NOTE_TYPE_CHOICES, default="general"
    )
    subject = models.CharField("Subject", max_length=200)
    content = models.TextField("Content")

    # For action items
    is_action_item = models.BooleanField("Is action item", default=False)
    action_due_date = models.DateField("Due date", null=True, blank=True)
    action_completed = models.BooleanField("Completed", default=False)
    action_completed_at = models.DateTimeField("Completed at", null=True, blank=True)
    action_completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_actions",
    )

    # Visibility
    visible_to_veteran = models.BooleanField(
        "Visible to veteran",
        default=False,
        help_text="Whether the veteran can see this note",
    )

    class Meta:
        verbose_name = "Case Note"
        verbose_name_plural = "Case Notes"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} - {self.case.title}"

    def mark_complete(self, completed_by=None):
        """Mark action item as complete"""
        self.action_completed = True
        self.action_completed_at = timezone.now()
        self.action_completed_by = completed_by
        self.save()


class SharedDocument(TimeStampedModel):
    """
    Links a veteran's document to a case for VSO access.

    Veterans must explicitly share documents with their VSO. This model
    tracks what has been shared and when.
    """

    SHARE_STATUS_CHOICES = [
        ("pending", "Pending Review"),
        ("reviewed", "Reviewed"),
        ("action_needed", "Action Needed"),
        ("archived", "Archived"),
    ]

    case = models.ForeignKey(
        VeteranCase, on_delete=models.CASCADE, related_name="shared_documents"
    )
    document = models.ForeignKey(
        "claims.Document", on_delete=models.CASCADE, related_name="case_shares"
    )
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="documents_shared",
    )
    shared_at = models.DateTimeField("Shared at", auto_now_add=True)

    # VSO review tracking
    status = models.CharField(
        "Status", max_length=20, choices=SHARE_STATUS_CHOICES, default="pending"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents_reviewed",
    )
    reviewed_at = models.DateTimeField("Reviewed at", null=True, blank=True)
    review_notes = models.TextField("Review notes", blank=True)

    # Include AI analysis? (opt-in for privacy)
    include_ai_analysis = models.BooleanField(
        "Include AI analysis",
        default=False,
        help_text="Explicitly share AI analysis results with VSO (opt-in)",
    )

    class Meta:
        verbose_name = "Shared Document"
        verbose_name_plural = "Shared Documents"
        unique_together = ["case", "document"]
        ordering = ["-shared_at"]

    def __str__(self):
        return f"{self.document.file_name} - {self.case.title}"

    def mark_reviewed(self, reviewed_by, notes=""):
        """Mark document as reviewed by VSO"""
        self.status = "reviewed"
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save()


class SharedAnalysis(TimeStampedModel):
    """
    Links a rating analysis or denial decoding to a case for VSO access.

    Allows VSOs to see the AI-generated insights for a veteran's documents.
    """

    ANALYSIS_TYPE_CHOICES = [
        ("rating_analysis", "Rating Analysis"),
        ("denial_decoding", "Denial Decoding"),
        ("decision_analysis", "Decision Letter Analysis"),
    ]

    # Defense-in-depth: direct org FK for query validation
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="shared_analyses",
        null=True,  # Allow null for migration, will be populated from case
        blank=True,
        help_text="Organization (auto-populated from case for defense-in-depth)",
    )

    case = models.ForeignKey(
        VeteranCase, on_delete=models.CASCADE, related_name="shared_analyses"
    )
    analysis_type = models.CharField(
        "Type", max_length=30, choices=ANALYSIS_TYPE_CHOICES
    )

    # Link to the actual analysis (flexible foreign keys)
    rating_analysis = models.ForeignKey(
        "agents.RatingAnalysis",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="case_shares",
    )
    decision_analysis = models.ForeignKey(
        "agents.DecisionLetterAnalysis",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="case_shares",
    )
    denial_decoding = models.ForeignKey(
        "agents.DenialDecoding",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="case_shares",
    )

    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="analyses_shared",
    )
    shared_at = models.DateTimeField("Shared at", auto_now_add=True)

    # VSO review
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analyses_reviewed",
    )
    reviewed_at = models.DateTimeField("Reviewed at", null=True, blank=True)
    vso_notes = models.TextField(
        "VSO notes",
        blank=True,
        help_text="VSO notes and recommendations based on analysis",
    )

    class Meta:
        verbose_name = "Shared Analysis"
        verbose_name_plural = "Shared Analyses"
        ordering = ["-shared_at"]

    def __str__(self):
        return f"{self.get_analysis_type_display()} - {self.case.title}"

    def save(self, *args, **kwargs):
        """Auto-populate organization from case for defense-in-depth."""
        if self.case_id and not self.organization_id:
            self.organization_id = self.case.organization_id
        super().save(*args, **kwargs)

    @property
    def analysis_object(self):
        """Return the actual analysis object"""
        if self.rating_analysis:
            return self.rating_analysis
        elif self.decision_analysis:
            return self.decision_analysis
        elif self.denial_decoding:
            return self.denial_decoding
        return None


class CaseChecklist(TimeStampedModel):
    """
    Checklist of required items for a case.

    VSOs can create checklists to track what evidence and forms are needed.
    """

    case = models.ForeignKey(
        VeteranCase, on_delete=models.CASCADE, related_name="checklists"
    )
    title = models.CharField("Title", max_length=200)
    description = models.TextField("Description", blank=True)

    class Meta:
        verbose_name = "Case Checklist"
        verbose_name_plural = "Case Checklists"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.title} - {self.case.title}"

    @property
    def completion_percentage(self):
        """Calculate checklist completion percentage"""
        items = self.items.all()
        if not items:
            return 0
        completed = items.filter(completed=True).count()
        return int((completed / items.count()) * 100)


class ChecklistItem(TimeStampedModel):
    """
    Individual item in a case checklist.
    """

    ITEM_TYPE_CHOICES = [
        ("document", "Document"),
        ("form", "VA Form"),
        ("medical", "Medical Evidence"),
        ("statement", "Statement"),
        ("other", "Other"),
    ]

    checklist = models.ForeignKey(
        CaseChecklist, on_delete=models.CASCADE, related_name="items"
    )
    item_type = models.CharField(
        "Type", max_length=20, choices=ITEM_TYPE_CHOICES, default="document"
    )
    title = models.CharField("Title", max_length=200)
    description = models.TextField("Description", blank=True)
    order = models.IntegerField("Order", default=0)

    # Status
    completed = models.BooleanField("Completed", default=False)
    completed_at = models.DateTimeField("Completed at", null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklist_completions",
    )

    # Link to document when uploaded
    document = models.ForeignKey(
        "claims.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklist_items",
    )

    # Visibility to veteran
    visible_to_veteran = models.BooleanField(
        "Visible to veteran",
        default=True,
        help_text="Whether veteran sees this in their checklist",
    )

    class Meta:
        verbose_name = "Checklist Item"
        verbose_name_plural = "Checklist Items"
        ordering = ["order", "created_at"]

    def __str__(self):
        return self.title

    def mark_complete(self, completed_by=None, document=None):
        """Mark item as complete"""
        self.completed = True
        self.completed_at = timezone.now()
        self.completed_by = completed_by
        if document:
            self.document = document
        self.save()


class CaseCondition(TimeStampedModel):
    """
    Normalized condition-level tracking for a veteran case.

    Tracks each condition being worked on, its workflow status, and evidence gaps.
    Conditions can be auto-derived from AI analyses or manually added.
    """

    WORKFLOW_STATUS_CHOICES = [
        ("identified", "Identified"),
        ("gathering_evidence", "Gathering Evidence"),
        ("evidence_complete", "Evidence Complete"),
        ("claim_filed", "Claim Filed"),
        ("pending_decision", "Pending Decision"),
        ("granted", "Granted"),
        ("denied", "Denied"),
        ("appealing", "Appealing"),
    ]

    SERVICE_CONNECTION_TYPE_CHOICES = [
        ("direct", "Direct Service Connection"),
        ("secondary", "Secondary Service Connection"),
        ("presumptive", "Presumptive"),
        ("aggravation", "Aggravation"),
    ]

    SOURCE_CHOICES = [
        ("manual", "Manually Added"),
        ("rating_analysis", "Rating Analysis"),
        ("decision_analysis", "Decision Letter Analysis"),
    ]

    case = models.ForeignKey(
        VeteranCase, on_delete=models.CASCADE, related_name="case_conditions"
    )
    condition_name = models.CharField("Condition Name", max_length=200)
    diagnostic_code = models.CharField(
        "Diagnostic Code",
        max_length=20,
        blank=True,
        help_text="VA diagnostic code (e.g., 9411 for PTSD)",
    )
    workflow_status = models.CharField(
        "Workflow Status",
        max_length=30,
        choices=WORKFLOW_STATUS_CHOICES,
        default="identified",
    )

    # Rating information
    current_rating = models.IntegerField(
        "Current Rating",
        null=True,
        blank=True,
        help_text="Current VA rating percentage (0-100)",
    )
    target_rating = models.IntegerField(
        "Target Rating",
        null=True,
        blank=True,
        help_text="Target rating percentage for this claim",
    )
    service_connection_type = models.CharField(
        "Service Connection Type",
        max_length=30,
        choices=SERVICE_CONNECTION_TYPE_CHOICES,
        blank=True,
    )

    # Gap checker fields - tracks evidence completeness
    has_diagnosis = models.BooleanField(
        "Has Diagnosis",
        default=False,
        help_text="Medical diagnosis documentation exists",
    )
    has_in_service_event = models.BooleanField(
        "Has In-Service Event",
        default=False,
        help_text="Service treatment records or incident documentation exists",
    )
    has_nexus = models.BooleanField(
        "Has Nexus",
        default=False,
        help_text="Medical opinion linking condition to service exists",
    )

    # Source tracking
    source = models.CharField(
        "Source", max_length=30, choices=SOURCE_CHOICES, default="manual"
    )
    source_analysis = models.ForeignKey(
        SharedAnalysis,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_conditions",
        help_text="The analysis this condition was derived from",
    )
    notes = models.TextField("Notes", blank=True)

    class Meta:
        verbose_name = "Case Condition"
        verbose_name_plural = "Case Conditions"
        unique_together = ["case", "condition_name"]
        ordering = ["condition_name"]

    def __str__(self):
        return f"{self.condition_name} - {self.case.title}"

    @property
    def gap_count(self):
        """Count of missing evidence elements (0-3)."""
        return sum(
            [not self.has_diagnosis, not self.has_in_service_event, not self.has_nexus]
        )

    @property
    def is_evidence_complete(self):
        """Check if all evidence elements are present."""
        return self.has_diagnosis and self.has_in_service_event and self.has_nexus

    @property
    def evidence_status(self):
        """Return a label for evidence completeness."""
        if self.is_evidence_complete:
            return "complete"
        elif self.gap_count == 3:
            return "needs_all"
        elif self.gap_count == 2:
            return "needs_most"
        else:
            return "needs_some"
