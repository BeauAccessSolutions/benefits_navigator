"""
Core models - Base models and utilities shared across all apps
"""

from django.db import models
from django.conf import settings
from django.utils import timezone


class TimeStampedModel(models.Model):
    """
    Abstract base model that provides self-updating
    'created_at' and 'updated_at' fields
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class SoftDeleteManager(models.Manager):
    """Manager that excludes soft-deleted objects by default."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    """Manager that includes all objects, even soft-deleted ones."""

    pass


class SoftDeleteModel(models.Model):
    """
    Abstract base model that implements soft deletion
    """

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Default manager excludes soft-deleted objects
    objects = SoftDeleteManager()
    # Access all objects including soft-deleted
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Soft delete - marks as deleted instead of removing from database"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(using=using)

    def hard_delete(self):
        """Permanently delete the record from database"""
        super().delete()

    def restore(self):
        """Restore a soft-deleted record"""
        self.is_deleted = False
        self.deleted_at = None
        self.save()


# =============================================================================
# JOURNEY MODELS
# =============================================================================


class JourneyStage(models.Model):
    """
    Defines stages in the VA claims journey.
    Pre-populated via fixture or migration.
    """

    ICON_CHOICES = [
        ("document", "Document"),
        ("clipboard", "Clipboard"),
        ("calendar", "Calendar"),
        ("check", "Check"),
        ("clock", "Clock"),
        ("mail", "Mail"),
        ("flag", "Flag"),
        ("alert", "Alert"),
    ]

    COLOR_CHOICES = [
        ("blue", "Blue"),
        ("green", "Green"),
        ("yellow", "Yellow"),
        ("red", "Red"),
        ("purple", "Purple"),
        ("gray", "Gray"),
    ]

    code = models.CharField(
        "Stage Code",
        max_length=30,
        unique=True,
        help_text="Unique identifier (e.g., claim_filed, exam_scheduled)",
    )
    name = models.CharField("Stage Name", max_length=100)
    description = models.TextField("Description", blank=True)
    order = models.IntegerField(
        "Display Order", default=0, help_text="Order in the journey timeline"
    )
    typical_duration_days = models.IntegerField(
        "Typical Duration (days)",
        null=True,
        blank=True,
        help_text="Expected time at this stage",
    )
    icon = models.CharField(
        "Icon", max_length=50, choices=ICON_CHOICES, default="document"
    )
    color = models.CharField(
        "Color", max_length=20, choices=COLOR_CHOICES, default="blue"
    )

    class Meta:
        verbose_name = "Journey Stage"
        verbose_name_plural = "Journey Stages"
        ordering = ["order"]

    def __str__(self):
        return self.name


class UserJourneyEvent(TimeStampedModel):
    """
    Tracks a user's events/milestones in their claims journey.
    Can be auto-generated from system events or manually added.
    """

    EVENT_TYPE_CHOICES = [
        ("auto", "Automatic (System)"),
        ("manual", "Manual (User)"),
        ("system", "System Notification"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="journey_events",
    )
    stage = models.ForeignKey(
        JourneyStage, on_delete=models.PROTECT, related_name="events"
    )
    event_type = models.CharField(
        "Event Type", max_length=20, choices=EVENT_TYPE_CHOICES, default="manual"
    )

    # Optional links to specific claims/appeals
    claim = models.ForeignKey(
        "claims.Claim",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journey_events",
    )
    appeal = models.ForeignKey(
        "appeals.Appeal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journey_events",
    )

    # Event details
    title = models.CharField("Event Title", max_length=200)
    description = models.TextField("Description", blank=True)
    event_date = models.DateField("Event Date")
    is_completed = models.BooleanField("Completed", default=False)

    # Optional metadata
    metadata = models.JSONField(
        "Metadata", default=dict, blank=True, help_text="Additional event data"
    )

    class Meta:
        verbose_name = "Journey Event"
        verbose_name_plural = "Journey Events"
        ordering = ["-event_date", "-created_at"]

    def __str__(self):
        return f"{self.title} - {self.event_date}"

    @property
    def is_future(self):
        """Check if event is in the future."""
        from datetime import date

        return self.event_date > date.today()

    @property
    def is_overdue(self):
        """Check if incomplete event is past due."""
        from datetime import date

        return not self.is_completed and self.event_date < date.today()


class JourneyMilestone(TimeStampedModel):
    """
    Major milestones in a user's VA benefits journey.
    Different from events - these are significant achievements.
    """

    MILESTONE_TYPE_CHOICES = [
        ("claim_filed", "Claim Filed"),
        ("exam_scheduled", "C&P Exam Scheduled"),
        ("exam_completed", "C&P Exam Completed"),
        ("decision_received", "Decision Received"),
        ("rating_assigned", "Rating Assigned"),
        ("appeal_filed", "Appeal Filed"),
        ("appeal_won", "Appeal Won"),
        ("increase_granted", "Increase Granted"),
        ("100_percent", "100% Rating Achieved"),
        ("tdiu_granted", "TDIU Granted"),
        ("custom", "Custom Milestone"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="journey_milestones",
    )
    milestone_type = models.CharField(
        "Milestone Type", max_length=30, choices=MILESTONE_TYPE_CHOICES
    )
    title = models.CharField("Title", max_length=200)
    date = models.DateField("Date")
    details = models.JSONField(
        "Details",
        default=dict,
        blank=True,
        help_text="Additional milestone data (e.g., rating percentage)",
    )
    notes = models.TextField("Notes", blank=True)

    class Meta:
        verbose_name = "Journey Milestone"
        verbose_name_plural = "Journey Milestones"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.title} - {self.date}"


class Deadline(TimeStampedModel):
    """
    Tracks important deadlines for a user's claims/appeals.
    """

    PRIORITY_CHOICES = [
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="deadlines"
    )

    # What this deadline is for
    title = models.CharField("Title", max_length=200)
    description = models.TextField("Description", blank=True)
    deadline_date = models.DateField("Deadline Date")
    priority = models.CharField(
        "Priority", max_length=20, choices=PRIORITY_CHOICES, default="medium"
    )

    # Optional links
    claim = models.ForeignKey(
        "claims.Claim",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deadlines",
    )
    appeal = models.ForeignKey(
        "appeals.Appeal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deadlines",
    )

    # Status tracking
    is_completed = models.BooleanField("Completed", default=False)
    completed_at = models.DateTimeField("Completed At", null=True, blank=True)
    reminder_sent = models.BooleanField("Reminder Sent", default=False)

    class Meta:
        verbose_name = "Deadline"
        verbose_name_plural = "Deadlines"
        ordering = ["deadline_date"]

    def __str__(self):
        return f"{self.title} - {self.deadline_date}"

    @property
    def days_remaining(self):
        """Calculate days until deadline."""
        from datetime import date

        if self.is_completed:
            return None
        delta = self.deadline_date - date.today()
        return delta.days

    @property
    def is_overdue(self):
        """Check if deadline has passed."""
        from datetime import date

        return not self.is_completed and self.deadline_date < date.today()

    @property
    def urgency_class(self):
        """Return CSS class based on urgency."""
        days = self.days_remaining
        if days is None:
            return "completed"
        if days < 0:
            return "overdue"
        if days <= 7:
            return "urgent"
        if days <= 30:
            return "soon"
        return "normal"

    def mark_complete(self):
        """Mark deadline as completed."""
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=["is_completed", "completed_at", "updated_at"])


# =============================================================================
# AUDIT LOGGING
# =============================================================================


class AuditLog(models.Model):
    """
    Audit trail for security-sensitive operations.
    Logs user actions, document access, and system events.
    """

    ACTION_CHOICES = [
        # Authentication
        ("login", "Login"),
        ("logout", "Logout"),
        ("login_failed", "Login Failed"),
        ("password_change", "Password Change"),
        ("password_reset", "Password Reset"),
        # Document operations
        ("document_upload", "Document Upload"),
        ("document_view", "Document View"),
        ("document_download", "Document Download"),
        ("document_delete", "Document Delete"),
        # PII access
        ("pii_view", "PII View"),
        ("pii_export", "PII Export"),
        # AI analysis
        ("ai_analysis", "AI Analysis"),
        ("denial_decode", "Denial Decode"),
        ("ai_decision_analyzer", "Decision Letter Analysis"),
        ("ai_evidence_gap", "Evidence Gap Analysis"),
        ("ai_statement_generator", "Statement Generation"),
        # VSO operations
        ('vso_case_create', 'Case Created'),
        ('vso_case_view', 'Case Viewed'),
        ('vso_case_update', 'Case Updated'),
        ('vso_document_share', 'Document Shared'),
        ('vso_document_unshare', 'Document Sharing Revoked'),
        ('vso_document_review', 'Document Reviewed'),
        ('vso_analysis_share', 'Analysis Shared'),
        ('vso_analysis_view', 'Analysis Viewed'),
        ('vso_note_add', 'Case Note Added'),
        ('vso_invitation_sent', 'Invitation Sent'),
        ('vso_invitation_accept', 'Invitation Accepted'),
        ('vso_case_archive', 'Case Archived'),
        ('vso_case_export', 'Cases Exported'),
        ('vso_report_export', 'Report Exported'),

        # Profile changes
        ("profile_update", "Profile Update"),
        ("account_delete", "Account Delete Request"),
        ("ai_consent_grant", "AI Consent Granted"),
        ("ai_consent_revoke", "AI Consent Revoked"),
        # Admin actions
        ("admin_action", "Admin Action"),
        # Other
        ("other", "Other"),
    ]

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    # User info (preserved even if user deleted)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    user_email = models.EmailField(
        "User Email", blank=True, help_text="Preserved email if user deleted"
    )

    # Action details
    action = models.CharField(
        "Action", max_length=30, choices=ACTION_CHOICES, db_index=True
    )

    # Request info
    ip_address = models.GenericIPAddressField("IP Address", null=True, blank=True)
    user_agent = models.TextField("User Agent", blank=True)
    request_path = models.CharField("Request Path", max_length=500, blank=True)
    request_method = models.CharField("Request Method", max_length=10, blank=True)

    # Resource being accessed
    resource_type = models.CharField(
        "Resource Type",
        max_length=50,
        blank=True,
        help_text="e.g., Document, Appeal, Claim",
    )
    resource_id = models.IntegerField("Resource ID", null=True, blank=True)

    # Additional details (JSON)
    details = models.JSONField(
        "Details", default=dict, blank=True, help_text="Additional action-specific data"
    )

    # Outcome
    success = models.BooleanField("Success", default=True)
    error_message = models.TextField("Error Message", blank=True)

    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "timestamp"]),
            models.Index(fields=["action", "timestamp"]),
            models.Index(fields=["resource_type", "resource_id"]),
        ]

    def __str__(self):
        return f"{self.action} by {self.user_email or 'anonymous'} at {self.timestamp}"

    def save(self, *args, **kwargs):
        # Preserve user email
        if self.user and not self.user_email:
            self.user_email = self.user.email
        super().save(*args, **kwargs)

    @classmethod
    def log(
        cls,
        action: str,
        request=None,
        user=None,
        resource_type: str = "",
        resource_id: int = None,
        details: dict = None,
        success: bool = True,
        error_message: str = "",
    ):
        """
        Convenience method to create audit log entries.

        Args:
            action: Action code (from ACTION_CHOICES)
            request: Django request object (optional)
            user: User instance (optional, will try to get from request)
            resource_type: Type of resource accessed
            resource_id: ID of resource accessed
            details: Additional details dict
            success: Whether action succeeded
            error_message: Error message if failed
        """
        log_entry = cls(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            success=success,
            error_message=error_message,
        )

        if request:
            # Get user from request if not provided
            if (
                user is None
                and hasattr(request, "user")
                and request.user.is_authenticated
            ):
                user = request.user

            # Extract request info
            log_entry.ip_address = cls._get_client_ip(request)
            log_entry.user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
            log_entry.request_path = request.path[:500]
            log_entry.request_method = request.method

        if user:
            log_entry.user = user
            log_entry.user_email = user.email

        log_entry.save()
        return log_entry

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request, handling proxies."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


# =============================================================================
# SUPPORTIVE MESSAGING
# =============================================================================


class SupportiveMessage(models.Model):
    """
    Encouraging messages displayed to veterans at key moments.
    Messages are contextual based on where the veteran is in their journey.
    """

    CONTEXT_CHOICES = [
        # Dashboard contexts
        ("dashboard_welcome", "Dashboard Welcome"),
        ("dashboard_progress", "Dashboard Progress"),
        # Exam preparation contexts
        ("exam_starting", "Starting Exam Prep"),
        ("exam_progress_25", "Exam Prep 25% Complete"),
        ("exam_progress_50", "Exam Prep 50% Complete"),
        ("exam_progress_75", "Exam Prep 75% Complete"),
        ("exam_ready", "Exam Prep Complete"),
        ("exam_upcoming_7_days", "Exam in 7 Days"),
        ("exam_upcoming_tomorrow", "Exam Tomorrow"),
        ("exam_completed", "Exam Completed"),
        # Claim contexts
        ("claim_filed", "Claim Filed"),
        ("claim_pending", "Claim Pending Review"),
        ("claim_waiting", "Long Wait Encouragement"),
        # Decision contexts
        ("decision_granted", "Claim Granted"),
        ("decision_denied", "Claim Denied"),
        ("decision_partial", "Partial Grant"),
        # Appeal contexts
        ("appeal_starting", "Starting Appeal"),
        ("appeal_filed", "Appeal Filed"),
        ("appeal_pending", "Appeal Pending"),
        # Deadline contexts
        ("deadline_30_days", "Deadline in 30 Days"),
        ("deadline_7_days", "Deadline in 7 Days"),
        ("deadline_urgent", "Deadline Urgent"),
        # Milestone contexts
        ("milestone_achieved", "Milestone Achieved"),
        ("first_login", "First Login"),
        # Evidence contexts
        ("evidence_uploaded", "Evidence Uploaded"),
        ("evidence_gap_found", "Evidence Gap Identified"),
        # General encouragement
        ("general", "General Encouragement"),
    ]

    TONE_CHOICES = [
        ("encouraging", "Encouraging"),
        ("informative", "Informative"),
        ("celebratory", "Celebratory"),
        ("urgent", "Urgent"),
        ("calming", "Calming"),
    ]

    context = models.CharField(
        "Context",
        max_length=30,
        choices=CONTEXT_CHOICES,
        db_index=True,
        help_text="When this message should be displayed",
    )
    message = models.TextField(
        "Message", help_text="The supportive message text (supports markdown)"
    )
    tone = models.CharField(
        "Tone", max_length=20, choices=TONE_CHOICES, default="encouraging"
    )
    icon = models.CharField(
        "Icon",
        max_length=50,
        default="heart",
        help_text="Icon name (e.g., heart, star, flag, shield)",
    )
    is_active = models.BooleanField("Active", default=True)
    order = models.IntegerField(
        "Order", default=0, help_text="Display order (lower = higher priority)"
    )

    class Meta:
        verbose_name = "Supportive Message"
        verbose_name_plural = "Supportive Messages"
        ordering = ["context", "order"]

    def __str__(self):
        return f"{self.get_context_display()}: {self.message[:50]}..."

    @classmethod
    def get_message_for_context(cls, context: str, random_select: bool = True):
        """
        Get a message for a specific context.

        Args:
            context: Context code from CONTEXT_CHOICES
            random_select: If True, randomly select from available messages

        Returns:
            SupportiveMessage instance or None
        """
        messages = cls.objects.filter(context=context, is_active=True)
        if not messages.exists():
            return None
        if random_select:
            import random

            return random.choice(list(messages))
        return messages.first()

    @classmethod
    def get_messages_for_contexts(cls, contexts: list) -> dict:
        """
        Get messages for multiple contexts.

        Args:
            contexts: List of context codes

        Returns:
            Dict mapping context to message
        """
        result = {}
        for context in contexts:
            msg = cls.get_message_for_context(context)
            if msg:
                result[context] = msg
        return result


# =============================================================================
# FEEDBACK MODELS
# =============================================================================


class Feedback(TimeStampedModel):
    """
    User feedback collected from in-app feedback widgets.
    Supports both thumbs up/down and optional text comments.
    """

    RATING_CHOICES = [
        ("positive", "Positive (Thumbs Up)"),
        ("negative", "Negative (Thumbs Down)"),
        ("neutral", "Neutral"),
    ]

    CATEGORY_CHOICES = [
        ("general", "General Feedback"),
        ("bug", "Bug Report"),
        ("feature", "Feature Request"),
        ("content", "Content Issue"),
        ("usability", "Usability"),
    ]

    STATUS_CHOICES = [
        ("new", "New"),
        ("reviewed", "Reviewed"),
        ("addressed", "Addressed"),
        ("wont_fix", "Won't Fix"),
    ]

    # Who submitted (optional - allow anonymous)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback",
    )

    # What page/feature
    page_url = models.CharField("Page URL", max_length=500)
    page_title = models.CharField("Page Title", max_length=200, blank=True)

    # The feedback itself
    rating = models.CharField(
        "Rating",
        max_length=10,
        choices=RATING_CHOICES,
        help_text="Quick thumbs up/down rating",
    )
    category = models.CharField(
        "Category", max_length=20, choices=CATEGORY_CHOICES, default="general"
    )
    comment = models.TextField(
        "Comment", blank=True, help_text="Optional detailed feedback"
    )

    # Metadata
    user_agent = models.CharField("User Agent", max_length=500, blank=True)
    session_key = models.CharField("Session Key", max_length=40, blank=True)

    # Admin tracking
    status = models.CharField(
        "Status", max_length=20, choices=STATUS_CHOICES, default="new"
    )
    admin_notes = models.TextField("Admin Notes", blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_feedback",
    )
    reviewed_at = models.DateTimeField("Reviewed At", null=True, blank=True)

    class Meta:
        verbose_name = "Feedback"
        verbose_name_plural = "Feedback"
        ordering = ["-created_at"]

    def __str__(self):
        user_str = self.user.email if self.user else "Anonymous"
        return f"{self.get_rating_display()} from {user_str} on {self.page_url}"

    @classmethod
    def get_summary_stats(cls):
        """Get summary statistics for feedback."""
        from django.db.models import Count

        total = cls.objects.count()
        by_rating = dict(
            cls.objects.values("rating")
            .annotate(count=Count("id"))
            .values_list("rating", "count")
        )
        by_status = dict(
            cls.objects.values("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )

        return {
            "total": total,
            "positive": by_rating.get("positive", 0),
            "negative": by_rating.get("negative", 0),
            "neutral": by_rating.get("neutral", 0),
            "new": by_status.get("new", 0),
            "reviewed": by_status.get("reviewed", 0),
            "addressed": by_status.get("addressed", 0),
        }


class SupportRequest(TimeStampedModel):
    """
    Support/contact form submissions from users.
    """

    CATEGORY_CHOICES = [
        ("general", "General Question"),
        ("bug", "Bug Report"),
        ("feature", "Feature Request"),
        ("account", "Account Issue"),
        ("billing", "Billing Question"),
        ("feedback", "Feedback"),
        ("other", "Other"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]

    STATUS_CHOICES = [
        ("new", "New"),
        ("in_progress", "In Progress"),
        ("waiting", "Waiting for Response"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]

    # Submitter info
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_requests",
    )
    email = models.EmailField("Email")
    name = models.CharField("Name", max_length=100)

    # Request details
    category = models.CharField(
        "Category", max_length=20, choices=CATEGORY_CHOICES, default="general"
    )
    subject = models.CharField("Subject", max_length=200)
    message = models.TextField("Message")

    # Context
    page_url = models.CharField("Page URL", max_length=500, blank=True)
    user_agent = models.CharField("User Agent", max_length=500, blank=True)

    # Admin tracking
    priority = models.CharField(
        "Priority", max_length=10, choices=PRIORITY_CHOICES, default="medium"
    )
    status = models.CharField(
        "Status", max_length=20, choices=STATUS_CHOICES, default="new"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_support_requests",
    )
    admin_notes = models.TextField("Admin Notes", blank=True)
    resolved_at = models.DateTimeField("Resolved At", null=True, blank=True)

    class Meta:
        verbose_name = "Support Request"
        verbose_name_plural = "Support Requests"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.subject} - {self.email}"

    def mark_resolved(self):
        """Mark the support request as resolved."""
        self.status = "resolved"
        self.resolved_at = timezone.now()
        self.save(update_fields=["status", "resolved_at", "updated_at"])


# =============================================================================
# HEALTH MONITORING MODELS
# =============================================================================


class SystemHealthMetric(models.Model):
    """
    Tracks system health metrics over time for monitoring.
    """

    METRIC_TYPE_CHOICES = [
        ("celery_queue", "Celery Queue Length"),
        ("celery_workers", "Celery Active Workers"),
        ("document_processing", "Document Processing"),
        ("ocr_success", "OCR Success Rate"),
        ("ai_analysis", "AI Analysis Success Rate"),
        ("response_time", "Response Time"),
    ]

    metric_type = models.CharField(
        "Metric Type", max_length=30, choices=METRIC_TYPE_CHOICES
    )
    value = models.FloatField("Value")
    timestamp = models.DateTimeField("Timestamp", auto_now_add=True)
    details = models.JSONField("Details", default=dict, blank=True)

    class Meta:
        verbose_name = "System Health Metric"
        verbose_name_plural = "System Health Metrics"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["metric_type", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.get_metric_type_display()}: {self.value} at {self.timestamp}"


class ProcessingFailure(TimeStampedModel):
    """
    Tracks document processing failures for monitoring and alerting.
    """

    FAILURE_TYPE_CHOICES = [
        ("ocr", "OCR Failure"),
        ("ai_analysis", "AI Analysis Failure"),
        ("timeout", "Processing Timeout"),
        ("file_error", "File Error"),
        ("unknown", "Unknown Error"),
    ]

    STATUS_CHOICES = [
        ("new", "New"),
        ("investigating", "Investigating"),
        ("resolved", "Resolved"),
        ("ignored", "Ignored"),
    ]

    failure_type = models.CharField(
        "Failure Type", max_length=20, choices=FAILURE_TYPE_CHOICES
    )
    document_id = models.IntegerField("Document ID", null=True, blank=True)
    task_id = models.CharField("Celery Task ID", max_length=50, blank=True)
    error_message = models.TextField("Error Message")
    stack_trace = models.TextField("Stack Trace", blank=True)
    retry_count = models.IntegerField("Retry Count", default=0)

    # Resolution tracking
    status = models.CharField(
        "Status", max_length=20, choices=STATUS_CHOICES, default="new"
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_failures",
    )
    resolution_notes = models.TextField("Resolution Notes", blank=True)
    resolved_at = models.DateTimeField("Resolved At", null=True, blank=True)

    # Alert tracking
    alert_sent = models.BooleanField("Alert Sent", default=False)
    alert_sent_at = models.DateTimeField("Alert Sent At", null=True, blank=True)

    class Meta:
        verbose_name = "Processing Failure"
        verbose_name_plural = "Processing Failures"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_failure_type_display()}] {self.error_message[:50]}"

    @classmethod
    def record_failure(
        cls,
        failure_type,
        error_message,
        document_id=None,
        task_id="",
        stack_trace="",
        retry_count=0,
    ):
        """Record a processing failure and optionally send alert."""
        failure = cls.objects.create(
            failure_type=failure_type,
            document_id=document_id,
            task_id=task_id,
            error_message=error_message,
            stack_trace=stack_trace,
            retry_count=retry_count,
        )

        # Check if we should alert (e.g., multiple failures in short time)
        recent_failures = cls.objects.filter(
            failure_type=failure_type,
            created_at__gte=timezone.now() - timezone.timedelta(hours=1),
            alert_sent=False,
        ).count()

        if recent_failures >= 3:  # Alert threshold
            failure.send_alert()

        return failure

    def send_alert(self):
        """Send alert for this failure (via Sentry and/or email)."""
        import sentry_sdk

        # Send to Sentry
        try:
            sentry_sdk.capture_message(
                f"Processing Failure Alert: {self.get_failure_type_display()}",
                level="error",
                extras={
                    "failure_id": self.id,
                    "failure_type": self.failure_type,
                    "document_id": self.document_id,
                    "error_message": self.error_message,
                },
            )
        except Exception:
            pass  # Sentry might not be configured

        self.alert_sent = True
        self.alert_sent_at = timezone.now()
        self.save(update_fields=["alert_sent", "alert_sent_at"])

    @classmethod
    def get_failure_stats(cls, hours=24):
        """Get failure statistics for the last N hours."""
        since = timezone.now() - timezone.timedelta(hours=hours)
        failures = cls.objects.filter(created_at__gte=since)

        return {
            "total": failures.count(),
            "by_type": dict(
                failures.values("failure_type")
                .annotate(count=models.Count("id"))
                .values_list("failure_type", "count")
            ),
            "unresolved": failures.filter(status="new").count(),
            "alert_sent": failures.filter(alert_sent=True).count(),
        }


class DataRetentionPolicy(models.Model):
    """
    Defines data retention policies for different data types.
    """

    DATA_TYPE_CHOICES = [
        ("audit_logs", "Audit Logs"),
        ("documents", "Documents"),
        ("analyses", "AI Analyses"),
        ("session_data", "Session Data"),
    ]

    data_type = models.CharField(
        "Data Type", max_length=30, choices=DATA_TYPE_CHOICES, unique=True
    )
    retention_days = models.IntegerField(
        "Retention Days", help_text="Number of days to retain data (0 = indefinite)"
    )
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Active", default=True)
    last_cleanup = models.DateTimeField("Last Cleanup", null=True, blank=True)

    class Meta:
        verbose_name = "Data Retention Policy"
        verbose_name_plural = "Data Retention Policies"

    def __str__(self):
        return f"{self.get_data_type_display()} - {self.retention_days} days"
