"""
Appeals app models - VA appeals workflow and guidance
Phase 4 implementation with step-by-step workflow tracking
"""

from django.db import models
from django.conf import settings
from django.urls import reverse
from datetime import date, timedelta

from core.models import TimeStampedModel


class AppealGuidance(TimeStampedModel):
    """
    Step-by-step guidance content for each appeal type.
    Similar to ExamGuidance but tailored for appeals process.
    """

    APPEAL_TYPE_CHOICES = [
        ("hlr", "Higher-Level Review"),
        ("supplemental", "Supplemental Claim"),
        ("board", "Board Appeal"),
    ]

    # Basic info
    title = models.CharField("Title", max_length=200)
    slug = models.SlugField("URL slug", unique=True)
    appeal_type = models.CharField(
        "Appeal Type", max_length=20, choices=APPEAL_TYPE_CHOICES, unique=True
    )

    # Key info
    va_form_number = models.CharField(
        "VA Form Number", max_length=50, help_text="e.g., VA Form 20-0995"
    )
    average_processing_days = models.IntegerField(
        "Average Processing Time (days)",
        help_text="Average time from submission to decision",
    )

    # When to use this appeal type
    when_to_use = models.TextField(
        "When to Use This Appeal Type",
        help_text="Criteria for choosing this appeal path",
    )
    when_not_to_use = models.TextField(
        "When NOT to Use This Appeal Type",
        help_text="Situations where another appeal type is better",
    )

    # Content sections
    overview = models.TextField(
        "Overview", help_text="Plain-language explanation of this appeal type"
    )
    requirements = models.TextField(
        "Requirements", help_text="What you need to file this appeal"
    )
    step_by_step = models.TextField(
        "Step-by-Step Process", help_text="Detailed steps to complete this appeal"
    )
    evidence_guidance = models.TextField(
        "Evidence Guidance", help_text="What evidence to include (or not)", blank=True
    )
    common_mistakes = models.TextField(
        "Common Mistakes", help_text="What veterans often get wrong"
    )
    after_submission = models.TextField(
        "After Submission", help_text="What to expect after filing"
    )
    tips = models.TextField(
        "Tips for Success", help_text="Pro tips from VSOs and veterans"
    )

    # Checklist items (JSON array)
    checklist_items = models.JSONField(
        "Preparation Checklist",
        default=list,
        help_text="Steps to complete before filing",
    )

    # Metadata
    order = models.IntegerField("Display order", default=0)
    is_published = models.BooleanField("Published", default=True)

    class Meta:
        verbose_name = "Appeal Guidance"
        verbose_name_plural = "Appeal Guidance"
        ordering = ["order", "appeal_type"]

    def __str__(self):
        return f"{self.title}"

    def get_absolute_url(self):
        return reverse("appeals:guidance_detail", kwargs={"slug": self.slug})


class Appeal(TimeStampedModel):
    """
    User's appeal case with workflow state tracking.
    Tracks progress through the appeals process.
    """

    APPEAL_TYPE_CHOICES = [
        ("hlr", "Higher-Level Review"),
        ("supplemental", "Supplemental Claim"),
        ("board_direct", "Board Appeal - Direct Review"),
        ("board_evidence", "Board Appeal - Evidence Submission"),
        ("board_hearing", "Board Appeal - Hearing Request"),
    ]

    STATUS_CHOICES = [
        ("deciding", "Deciding Appeal Path"),
        ("gathering", "Gathering Materials"),
        ("preparing", "Preparing Submission"),
        ("ready", "Ready to Submit"),
        ("submitted", "Submitted to VA"),
        ("acknowledged", "VA Acknowledged Receipt"),
        ("in_review", "Under VA Review"),
        ("decision_pending", "Decision Pending"),
        ("decided", "Decision Received"),
        ("closed", "Closed"),
    ]

    DECISION_CHOICES = [
        ("pending", "Pending"),
        ("granted", "Granted (Favorable)"),
        ("partial", "Partially Granted"),
        ("denied", "Denied"),
        ("remanded", "Remanded"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="appeals"
    )

    # Link to VSO case (optional - appeals can exist without a case)
    veteran_case = models.ForeignKey(
        "vso.VeteranCase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appeals",
        help_text="VSO case this appeal is related to",
    )

    appeal_type = models.CharField(
        "Appeal type",
        max_length=20,
        choices=APPEAL_TYPE_CHOICES,
        blank=True,  # Blank until user decides
        help_text="Type of appeal being filed",
    )

    status = models.CharField(
        "Status", max_length=30, choices=STATUS_CHOICES, default="deciding"
    )

    # Original decision info
    original_decision_date = models.DateField(
        "Original Decision Date",
        null=True,
        blank=True,
        help_text="Date of the VA decision being appealed",
    )

    deadline = models.DateField(
        "Filing Deadline",
        blank=True,
        null=True,
        help_text="Deadline to file this appeal (auto-calculated)",
    )

    # What's being appealed
    conditions_appealed = models.TextField(
        "Conditions Being Appealed",
        blank=True,
        help_text="List the conditions/ratings you are appealing",
    )

    denial_reasons = models.TextField(
        "Reasons for Denial/Low Rating",
        blank=True,
        help_text="Why was your claim denied or rated low?",
    )

    # Decision tree answers (for recommending appeal type)
    has_new_evidence = models.BooleanField(
        "Do you have new evidence?",
        null=True,
        blank=True,
        help_text="Evidence VA has not seen before",
    )

    believes_va_error = models.BooleanField(
        "Do you believe VA made an error?",
        null=True,
        blank=True,
        help_text="Error based on existing evidence",
    )

    wants_hearing = models.BooleanField(
        "Do you want to present your case in person?", null=True, blank=True
    )

    # Workflow tracking
    current_step = models.IntegerField(
        "Current Step", default=1, help_text="Current step in the appeal process"
    )

    workflow_state = models.JSONField(
        "Workflow State", default=dict, help_text="Tracks completed steps and data"
    )

    steps_completed = models.JSONField(
        "Completed Steps", default=list, help_text="List of completed step IDs"
    )

    # Submission tracking
    submission_date = models.DateField("Submission Date", null=True, blank=True)

    va_confirmation_number = models.CharField(
        "VA Confirmation Number", max_length=100, blank=True
    )

    # Outcome
    decision_received_date = models.DateField(
        "Decision Received Date", null=True, blank=True
    )

    decision_outcome = models.CharField(
        "Decision Outcome", max_length=20, choices=DECISION_CHOICES, default="pending"
    )

    decision_notes = models.TextField("Decision Notes", blank=True)

    # User notes
    notes = models.TextField("Personal Notes", blank=True)

    class Meta:
        verbose_name = "Appeal"
        verbose_name_plural = "Appeals"
        ordering = ["-created_at"]

    def __str__(self):
        if self.appeal_type:
            return f"{self.get_appeal_type_display()} - {self.user.email}"
        return f"Appeal (deciding) - {self.user.email}"

    def get_absolute_url(self):
        return reverse("appeals:appeal_detail", kwargs={"pk": self.pk})

    def save(self, *args, **kwargs):
        # Auto-calculate deadline based on appeal type
        if self.appeal_type == "supplemental":
            # Supplemental claims have no filing deadline (38 CFR § 20.204)
            self.deadline = None
        elif self.original_decision_date and not self.deadline:
            # HLR and Board appeals: 1 year from decision (38 CFR § 20.202)
            self.deadline = self.original_decision_date + timedelta(days=365)
        super().save(*args, **kwargs)

    @property
    def days_until_deadline(self):
        """Calculate days remaining until filing deadline."""
        if self.deadline:
            delta = self.deadline - date.today()
            return delta.days
        return None

    @property
    def is_deadline_urgent(self):
        """Check if deadline is within 30 days."""
        days = self.days_until_deadline
        return days is not None and days <= 30

    @property
    def is_past_deadline(self):
        """Check if deadline has passed."""
        days = self.days_until_deadline
        return days is not None and days < 0

    @property
    def recommended_appeal_type(self):
        """
        Recommend appeal type based on decision tree answers.
        Based on research: new evidence → Supplemental, VA error → HLR
        """
        if self.has_new_evidence:
            return "supplemental"
        elif self.believes_va_error and not self.wants_hearing:
            return "hlr"
        elif self.wants_hearing:
            return "board_hearing"
        elif self.believes_va_error is False and self.has_new_evidence is False:
            return "board_direct"
        return None

    @property
    def completion_percentage(self):
        """Calculate progress through appeal workflow."""
        if not self.workflow_state:
            return 0
        total_steps = self.workflow_state.get("total_steps", 10)
        completed = len(self.steps_completed)
        return int((completed / total_steps) * 100) if total_steps > 0 else 0

    def get_guidance(self):
        """Get the guidance content for this appeal type."""
        if self.appeal_type:
            # Map board subtypes to main board type
            appeal_type = self.appeal_type
            if appeal_type.startswith("board_"):
                appeal_type = "board"
            try:
                return AppealGuidance.objects.get(appeal_type=appeal_type)
            except AppealGuidance.DoesNotExist:
                return None
        return None


class AppealDocument(TimeStampedModel):
    """
    Documents uploaded or generated for an appeal.
    """

    DOCUMENT_TYPE_CHOICES = [
        ("decision_letter", "VA Decision Letter"),
        ("new_evidence", "New Evidence"),
        ("medical_record", "Medical Record"),
        ("nexus_letter", "Nexus Letter"),
        ("buddy_statement", "Buddy Statement"),
        ("personal_statement", "Personal Statement"),
        ("form", "VA Form"),
        ("other", "Other"),
    ]

    appeal = models.ForeignKey(
        Appeal, on_delete=models.CASCADE, related_name="documents"
    )

    document_type = models.CharField(
        "Document Type", max_length=30, choices=DOCUMENT_TYPE_CHOICES
    )

    title = models.CharField("Title", max_length=200)

    file = models.FileField(
        "File", upload_to="appeals/documents/%Y/%m/", blank=True, null=True
    )

    notes = models.TextField("Notes", blank=True)

    is_submitted = models.BooleanField("Included in Submission", default=False)

    class Meta:
        verbose_name = "Appeal Document"
        verbose_name_plural = "Appeal Documents"
        ordering = ["document_type", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_document_type_display()})"


class AppealNote(TimeStampedModel):
    """
    Timeline notes and updates for an appeal.
    """

    NOTE_TYPE_CHOICES = [
        ("user", "User Note"),
        ("status", "Status Update"),
        ("reminder", "Reminder"),
        ("va_communication", "VA Communication"),
    ]

    appeal = models.ForeignKey(
        Appeal, on_delete=models.CASCADE, related_name="timeline_notes"
    )

    note_type = models.CharField(
        "Note Type", max_length=20, choices=NOTE_TYPE_CHOICES, default="user"
    )

    content = models.TextField("Content")

    is_important = models.BooleanField("Mark as Important", default=False)

    class Meta:
        verbose_name = "Appeal Note"
        verbose_name_plural = "Appeal Notes"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.get_note_type_display()} - {self.created_at.strftime('%Y-%m-%d')}"
        )
