"""
Exam Prep app models - C&P Exam preparation content and tracking
"""

from django.db import models
from django.conf import settings
from django.urls import reverse

from core.models import TimeStampedModel


class ExamGuidance(TimeStampedModel):
    """
    C&P Exam preparation guidance content
    Structured content for condition-specific exam preparation
    """

    CATEGORY_CHOICES = [
        ("general", "General Guidance"),
        ("ptsd", "PTSD"),
        ("tbi", "Traumatic Brain Injury"),
        ("musculoskeletal", "Musculoskeletal (Back, Knee, Shoulder)"),
        ("hearing", "Hearing Loss / Tinnitus"),
        ("respiratory", "Respiratory Conditions"),
        ("sleep_apnea", "Sleep Apnea"),
        ("mental_health", "Mental Health (non-PTSD)"),
        ("other", "Other Conditions"),
    ]

    # Basic info
    title = models.CharField("Title", max_length=200)
    slug = models.SlugField("URL slug", unique=True)
    category = models.CharField(
        "Category", max_length=30, choices=CATEGORY_CHOICES, default="general"
    )

    # Structured content sections
    introduction = models.TextField(
        "Introduction", help_text="Brief overview of this exam type", blank=True
    )
    what_exam_measures = models.TextField(
        "What This Exam Measures",
        help_text="Plain-language explanation of DBQ form",
        blank=True,
    )
    physical_tests = models.TextField(
        "Physical Tests Performed",
        help_text="Description of tests examiner will perform",
        blank=True,
    )
    questions_to_expect = models.TextField(
        "Questions to Expect", help_text="Sample questions examiner may ask", blank=True
    )
    preparation_tips = models.TextField(
        "Preparation Tips", help_text="How to prepare (before exam)", blank=True
    )
    day_of_guidance = models.TextField(
        "Day-of Guidance", help_text="What to do on exam day", blank=True
    )
    common_mistakes = models.TextField(
        "Common Mistakes", help_text="What NOT to do", blank=True
    )
    after_exam = models.TextField(
        "After the Exam", help_text="What to do post-exam", blank=True
    )

    # Checklist items (JSON array of task objects)
    checklist_items = models.JSONField(
        "Checklist Items",
        default=list,
        help_text="Array of preparation tasks",
        blank=True,
    )

    # Metadata
    order = models.IntegerField("Display order", default=0)
    is_published = models.BooleanField("Published", default=True)
    meta_description = models.CharField(
        "Meta Description", max_length=160, blank=True, help_text="For SEO"
    )

    class Meta:
        verbose_name = "Exam Guidance"
        verbose_name_plural = "Exam Guidance"
        ordering = ["order", "category", "title"]

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"

    def get_absolute_url(self):
        return reverse("examprep:guide_detail", kwargs={"slug": self.slug})


class GlossaryTerm(TimeStampedModel):
    """
    VA terminology glossary
    Plain-language translations of VA jargon
    """

    term = models.CharField(
        "VA Term", max_length=100, unique=True, help_text="Official VA term or acronym"
    )
    plain_language = models.TextField(
        "Plain Language Definition",
        help_text="Simple explanation anyone can understand",
    )
    context = models.TextField(
        "When/Why This Matters",
        blank=True,
        help_text="Additional context about importance",
    )
    example = models.TextField(
        "Example", blank=True, help_text="Example usage or scenario"
    )

    # Related terms
    related_terms = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=True,
        help_text="Other terms related to this one",
    )

    # Display options
    show_in_tooltips = models.BooleanField(
        "Show in Tooltips",
        default=True,
        help_text="Display as inline tooltip when term appears",
    )
    order = models.IntegerField("Display order", default=0)

    class Meta:
        verbose_name = "Glossary Term"
        verbose_name_plural = "Glossary Terms"
        ordering = ["term"]

    def __str__(self):
        return self.term


class ExamChecklist(TimeStampedModel):
    """
    User's personalized exam preparation checklist
    Tracks completion of preparation tasks
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="exam_checklists",
    )
    condition = models.CharField(
        "Condition", max_length=100, help_text="Condition for which exam is scheduled"
    )
    exam_date = models.DateField("Exam date", null=True, blank=True)

    # Link to guidance used
    guidance = models.ForeignKey(
        ExamGuidance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Associated exam guidance",
    )

    # Tasks completed (stored as JSON list of task IDs)
    tasks_completed = models.JSONField(
        "Completed tasks",
        default=list,
        help_text="List of task IDs that have been completed",
    )

    # User notes and preparation
    symptom_notes = models.TextField(
        "Symptom Notes", blank=True, help_text="Notes on symptoms to discuss"
    )
    worst_day_description = models.TextField(
        "Worst Day Description",
        blank=True,
        help_text="Description of worst days with this condition",
    )
    functional_limitations = models.TextField(
        "Functional Limitations",
        blank=True,
        help_text="How condition affects daily life/work",
    )
    questions_for_examiner = models.TextField("Questions for Examiner", blank=True)

    # Post-exam documentation
    exam_completed = models.BooleanField("Exam Completed", default=False)
    exam_notes = models.TextField(
        "Post-Exam Notes", blank=True, help_text="What happened during exam"
    )

    # Reminders
    reminder_sent = models.BooleanField("Reminder Sent", default=False)

    class Meta:
        verbose_name = "Exam Checklist"
        verbose_name_plural = "Exam Checklists"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.condition} exam for {self.user.email}"

    @property
    def is_upcoming(self):
        """Check if exam is upcoming (within 30 days) and not yet completed"""
        if self.exam_completed:
            return False
        if self.exam_date:
            from datetime import date, timedelta

            today = date.today()
            return today <= self.exam_date <= today + timedelta(days=30)
        return False

    @property
    def days_until_exam(self):
        """Calculate days until exam"""
        if self.exam_date:
            from datetime import date

            delta = self.exam_date - date.today()
            return delta.days
        return None

    @property
    def completion_percentage(self):
        """Calculate checklist completion percentage"""
        if self.guidance and self.guidance.checklist_items:
            total_tasks = len(self.guidance.checklist_items)
            if total_tasks == 0:
                return 0
            completed = len(self.tasks_completed)
            return int((completed / total_tasks) * 100)
        return 0


class SavedRatingCalculation(TimeStampedModel):
    """
    User's saved VA disability rating calculation.
    Allows veterans to save and compare different scenarios.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rating_calculations",
    )
    name = models.CharField(
        "Calculation Name",
        max_length=100,
        help_text='e.g., "Current Rating" or "If I add sleep apnea"',
    )

    # Individual ratings stored as JSON
    # Format: [{"percentage": 50, "description": "PTSD", "is_bilateral": false}, ...]
    ratings = models.JSONField(
        "Disability Ratings",
        default=list,
        help_text="List of individual disability ratings",
    )

    # Calculated results
    combined_raw = models.FloatField("Combined (raw)", default=0)
    combined_rounded = models.IntegerField("Combined (rounded)", default=0)
    bilateral_factor = models.FloatField("Bilateral Factor", default=0)

    # Dependent info for compensation estimate
    has_spouse = models.BooleanField("Has Spouse", default=False)
    children_under_18 = models.IntegerField("Children Under 18", default=0)
    dependent_parents = models.IntegerField("Dependent Parents", default=0)

    # Estimated compensation
    estimated_monthly = models.FloatField("Estimated Monthly", default=0)

    # Notes
    notes = models.TextField("Notes", blank=True)

    class Meta:
        verbose_name = "Saved Rating Calculation"
        verbose_name_plural = "Saved Rating Calculations"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.name} - {self.combined_rounded}% ({self.user.email})"

    def recalculate(self):
        """Recalculate combined rating from stored ratings"""
        from .va_math import (
            DisabilityRating,
            calculate_combined_rating,
            estimate_monthly_compensation,
        )

        if not self.ratings:
            self.combined_raw = 0
            self.combined_rounded = 0
            self.bilateral_factor = 0
            self.estimated_monthly = 0
            return

        # Convert JSON to DisabilityRating objects
        rating_objects = [
            DisabilityRating(
                percentage=r.get("percentage", 0),
                description=r.get("description", ""),
                is_bilateral=r.get("is_bilateral", False),
            )
            for r in self.ratings
        ]

        # Calculate combined rating
        result = calculate_combined_rating(rating_objects)

        self.combined_raw = result.combined_raw
        self.combined_rounded = result.combined_rounded
        self.bilateral_factor = result.bilateral_factor_applied

        # Estimate monthly compensation
        self.estimated_monthly = estimate_monthly_compensation(
            self.combined_rounded,
            spouse=self.has_spouse,
            children_under_18=self.children_under_18,
            dependent_parents=self.dependent_parents,
        )


class EvidenceChecklist(TimeStampedModel):
    """
    Personalized evidence checklist for a specific condition claim.
    Generated from M21 requirements to help veterans gather the right evidence.
    """

    CLAIM_TYPE_CHOICES = [
        ("initial", "Initial Claim"),
        ("increase", "Rating Increase"),
        ("secondary", "Secondary Condition"),
        ("appeal", "Appeal / Supplemental Claim"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="evidence_checklists",
    )

    # What condition this checklist is for
    condition = models.CharField(
        "Condition", max_length=200, help_text="Medical condition this evidence is for"
    )
    claim_type = models.CharField(
        "Claim Type", max_length=20, choices=CLAIM_TYPE_CHOICES, default="initial"
    )

    # For secondary claims
    primary_condition = models.CharField(
        "Primary Condition",
        max_length=200,
        blank=True,
        help_text="For secondary claims: the primary service-connected condition",
    )

    # M21 sections used to generate this checklist
    m21_sections_used = models.JSONField(
        "M21 Sections Used",
        default=list,
        blank=True,
        help_text="M21 section references used in generation",
    )

    # The checklist items
    # Format: [
    #     {
    #         "id": "nexus_letter",
    #         "category": "Medical Evidence",
    #         "title": "Nexus Letter / IMO",
    #         "description": "Medical opinion linking condition to service",
    #         "priority": "critical",
    #         "m21_reference": "M21-1.V.ii.2.A",
    #         "tips": ["Ask treating doctor", "Include rationale"],
    #         "completed": false,
    #         "completed_at": null,
    #         "notes": ""
    #     }
    # ]
    checklist_items = models.JSONField(
        "Checklist Items",
        default=list,
        help_text="Evidence items with completion status",
    )

    # Progress tracking (cached, updated on toggle)
    completion_percentage = models.IntegerField("Completion %", default=0)

    # Link to denial analysis (if generated from denial decoder)
    from_denial_analysis = models.ForeignKey(
        "agents.DecisionLetterAnalysis",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_checklists",
        help_text="If generated from a denial analysis",
    )

    # User notes
    notes = models.TextField(
        "Notes", blank=True, help_text="User notes about this evidence gathering"
    )

    class Meta:
        verbose_name = "Evidence Checklist"
        verbose_name_plural = "Evidence Checklists"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Evidence for {self.condition} ({self.get_claim_type_display()}) - {self.user.email}"

    def update_completion(self):
        """Recalculate completion percentage."""
        if not self.checklist_items:
            self.completion_percentage = 0
        else:
            completed = sum(1 for item in self.checklist_items if item.get("completed"))
            self.completion_percentage = int(
                (completed / len(self.checklist_items)) * 100
            )
        self.save(update_fields=["completion_percentage", "updated_at"])

    def toggle_item(self, item_id: str) -> bool:
        """
        Toggle completion status of an item.
        Returns new completion status.
        """
        from django.utils import timezone

        for item in self.checklist_items:
            if item.get("id") == item_id:
                item["completed"] = not item.get("completed", False)
                item["completed_at"] = (
                    timezone.now().isoformat() if item["completed"] else None
                )
                self.save(update_fields=["checklist_items", "updated_at"])
                self.update_completion()
                return item["completed"]
        return False

    @property
    def total_items(self):
        """Total number of checklist items."""
        return len(self.checklist_items) if self.checklist_items else 0

    @property
    def completed_items(self):
        """Number of completed items."""
        if not self.checklist_items:
            return 0
        return sum(1 for item in self.checklist_items if item.get("completed"))

    @property
    def critical_items_remaining(self):
        """Number of incomplete critical items."""
        if not self.checklist_items:
            return 0
        return sum(
            1
            for item in self.checklist_items
            if item.get("priority") == "critical" and not item.get("completed")
        )

    def get_items_by_category(self):
        """Group items by category."""
        categories = {}
        for item in self.checklist_items or []:
            category = item.get("category", "Other")
            if category not in categories:
                categories[category] = []
            categories[category].append(item)
        return categories


class SharedCalculation(TimeStampedModel):
    """
    Shareable rating calculation with unique token.
    Allows anyone (logged in or anonymous) to share their calculation.
    """

    import secrets

    # Unique share token
    share_token = models.CharField(
        "Share Token",
        max_length=32,
        unique=True,
        db_index=True,
        help_text="Unique token for sharing this calculation",
    )

    # Optional link to user if logged in
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shared_calculations",
    )

    # Optional link to saved calculation if created from one
    saved_calculation = models.ForeignKey(
        "SavedRatingCalculation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shares",
    )

    # Calculation name
    name = models.CharField(
        "Name", max_length=100, default="Shared VA Rating Calculation"
    )

    # Individual ratings stored as JSON
    ratings = models.JSONField(
        "Disability Ratings",
        default=list,
        help_text="List of individual disability ratings",
    )

    # Calculated results
    combined_raw = models.FloatField("Combined (raw)", default=0)
    combined_rounded = models.IntegerField("Combined (rounded)", default=0)
    bilateral_factor = models.FloatField("Bilateral Factor", default=0)

    # Dependent info
    has_spouse = models.BooleanField("Has Spouse", default=False)
    children_under_18 = models.IntegerField("Children Under 18", default=0)
    dependent_parents = models.IntegerField("Dependent Parents", default=0)

    # Estimated compensation
    estimated_monthly = models.FloatField("Estimated Monthly", default=0)

    # Expiration (optional - for cleanup)
    expires_at = models.DateTimeField(
        "Expires At", null=True, blank=True, help_text="When this share link expires"
    )

    # View tracking
    view_count = models.PositiveIntegerField("View Count", default=0)

    class Meta:
        verbose_name = "Shared Calculation"
        verbose_name_plural = "Shared Calculations"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.name} - {self.combined_rounded}% (token: {self.share_token[:8]}...)"
        )

    def save(self, *args, **kwargs):
        if not self.share_token:
            import secrets

            self.share_token = secrets.token_urlsafe(16)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse(
            "examprep:shared_calculation", kwargs={"token": self.share_token}
        )

    @property
    def is_expired(self):
        """Check if this share link has expired."""
        if not self.expires_at:
            return False
        from django.utils import timezone

        return timezone.now() > self.expires_at

    def increment_views(self):
        """Increment view count."""
        self.view_count += 1
        self.save(update_fields=["view_count"])

    @classmethod
    def create_from_data(
        cls,
        ratings,
        combined_raw,
        combined_rounded,
        bilateral_factor,
        estimated_monthly,
        has_spouse=False,
        children_under_18=0,
        dependent_parents=0,
        name="Shared VA Rating Calculation",
        user=None,
        saved_calculation=None,
        expires_in_days=30,
    ):
        """
        Create a new shared calculation from calculation data.

        Args:
            expires_in_days: Number of days until link expires (None for no expiry)
        """
        from django.utils import timezone
        from datetime import timedelta

        expires_at = None
        if expires_in_days:
            expires_at = timezone.now() + timedelta(days=expires_in_days)

        return cls.objects.create(
            user=user,
            saved_calculation=saved_calculation,
            name=name,
            ratings=ratings,
            combined_raw=combined_raw,
            combined_rounded=combined_rounded,
            bilateral_factor=bilateral_factor,
            estimated_monthly=estimated_monthly,
            has_spouse=has_spouse,
            children_under_18=children_under_18,
            dependent_parents=dependent_parents,
            expires_at=expires_at,
        )
