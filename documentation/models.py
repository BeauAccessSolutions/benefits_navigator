"""
Models for the VA Documentation and Forms system.

Provides searchable documentation for veterans including:
- VA Forms with instructions and workflow mapping
- C&P Exam preparation guides by condition
- Legal references (CAVC decisions, VAOPGCPREC opinions)
"""

from django.db import models
from django.urls import reverse
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField


class DocumentCategory(models.Model):
    """Categories for organizing searchable documents."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon class name (e.g., 'document-text' for Heroicons)",
    )
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Document Categories"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class VAForm(models.Model):
    """VA forms with metadata, instructions, and workflow mapping."""

    WORKFLOW_STAGES = [
        ("initial_claim", "Initial Claim"),
        ("supplemental_claim", "Supplemental Claim"),
        ("higher_level_review", "Higher-Level Review"),
        ("board_appeal", "Board Appeal"),
        ("evidence_submission", "Evidence Submission"),
        ("dependency", "Dependency Claims"),
        ("special_monthly", "Special Monthly Compensation"),
    ]

    form_number = models.CharField(
        max_length=20, unique=True, help_text="VA form number (e.g., '21-526EZ')"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(
        help_text="Brief description of what this form is used for"
    )
    instructions = models.TextField(
        help_text="Simplified instructions for completing the form"
    )
    official_url = models.URLField(help_text="Link to the official VA form PDF")
    instructions_url = models.URLField(
        blank=True, help_text="Link to official VA instructions (if separate)"
    )
    workflow_stages = models.JSONField(
        default=list, help_text="List of workflow stages where this form is used"
    )
    deadline_info = models.TextField(
        blank=True, help_text="Deadline requirements and time limits"
    )
    tips = models.TextField(
        blank=True, help_text="User-friendly tips for completing the form"
    )
    common_mistakes = models.TextField(
        blank=True, help_text="Common mistakes to avoid when filling out this form"
    )
    related_forms = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=True,
        help_text="Other forms commonly used together",
    )
    category = models.ForeignKey(
        DocumentCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="forms",
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this form is currently in use by VA"
    )
    last_updated = models.DateField(help_text="When this form was last updated by VA")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Full-text search vector
    search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        verbose_name = "VA Form"
        verbose_name_plural = "VA Forms"
        ordering = ["form_number"]
        indexes = [
            GinIndex(fields=["search_vector"]),
        ]

    def __str__(self):
        return f"{self.form_number}: {self.title}"

    def get_absolute_url(self):
        return reverse(
            "documentation:form_detail", kwargs={"form_number": self.form_number}
        )


class CPExamGuideCondition(models.Model):
    """
    C&P exam preparation guides organized by medical condition.

    These guides help veterans understand what to expect during
    their Compensation & Pension examination and how to prepare.
    """

    CONDITION_CATEGORIES = [
        ("mental_health", "Mental Health"),
        ("musculoskeletal", "Musculoskeletal"),
        ("respiratory", "Respiratory"),
        ("cardiovascular", "Cardiovascular"),
        ("neurological", "Neurological"),
        ("auditory", "Auditory/Hearing"),
        ("digestive", "Digestive"),
        ("skin", "Skin"),
        ("endocrine", "Endocrine"),
        ("other", "Other"),
    ]

    condition_name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Name of the medical condition (e.g., 'PTSD', 'Sleep Apnea')",
    )
    slug = models.SlugField(unique=True)
    category = models.CharField(
        max_length=20, choices=CONDITION_CATEGORIES, default="other"
    )
    dbq_form = models.CharField(
        max_length=50,
        blank=True,
        help_text="Associated Disability Benefits Questionnaire number",
    )
    what_to_expect = models.TextField(
        help_text="Description of what happens during the C&P exam"
    )
    key_questions = models.JSONField(
        default=list, help_text="List of questions the examiner will likely ask"
    )
    documentation_needed = models.JSONField(
        default=list, help_text="Documents you should bring to the exam"
    )
    how_to_prepare = models.TextField(help_text="Steps to prepare for the examination")
    tips = models.TextField(help_text="Helpful tips for the exam")
    red_flags = models.TextField(
        blank=True, help_text="Common mistakes or things to avoid"
    )
    rating_criteria_summary = models.TextField(
        blank=True, help_text="Summary of how VA rates this condition"
    )
    related_conditions = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=True,
        help_text="Related conditions often claimed together",
    )
    related_form = models.ForeignKey(
        VAForm,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exam_guides",
        help_text="Primary form used for this condition",
    )
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Full-text search vector
    search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        verbose_name = "C&P Exam Guide"
        verbose_name_plural = "C&P Exam Guides"
        ordering = ["category", "condition_name"]
        indexes = [
            GinIndex(fields=["search_vector"]),
        ]

    def __str__(self):
        return f"C&P Guide: {self.condition_name}"

    def get_absolute_url(self):
        return reverse("documentation:exam_guide_detail", kwargs={"slug": self.slug})


class LegalReference(models.Model):
    """
    CAVC decisions and VAOPGCPREC opinions for reference.

    IMPORTANT: These are for informational purposes only and
    do not constitute legal advice.
    """

    REFERENCE_TYPES = [
        ("cavc", "CAVC Decision"),
        ("vaopgcprec", "VA General Counsel Opinion"),
        ("cfr", "Code of Federal Regulations"),
        ("statute", "U.S. Code/Statute"),
    ]

    reference_type = models.CharField(max_length=20, choices=REFERENCE_TYPES)
    citation = models.CharField(
        max_length=150,
        unique=True,
        help_text="Full legal citation (e.g., 'Caluza v. Brown, 7 Vet. App. 498 (1995)')",
    )
    short_name = models.CharField(
        max_length=100, help_text="Short reference name (e.g., 'Caluza')"
    )
    title = models.CharField(
        max_length=300, help_text="Descriptive title of what this reference establishes"
    )
    summary = models.TextField(
        help_text="Plain-language summary of the holding/opinion"
    )
    key_points = models.JSONField(
        default=list, help_text="Bullet points of key takeaways"
    )
    relevance = models.TextField(help_text="When and how this applies to VA claims")
    date_issued = models.DateField()
    url = models.URLField(blank=True, help_text="Link to the full decision/opinion")
    related_conditions = models.JSONField(
        default=list,
        blank=True,
        help_text="Conditions this reference is particularly relevant to",
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this reference is still good law"
    )
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supersedes",
        help_text="If overruled, link to the superseding reference",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Full-text search vector
    search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        verbose_name = "Legal Reference"
        verbose_name_plural = "Legal References"
        ordering = ["-date_issued"]
        indexes = [
            GinIndex(fields=["search_vector"]),
        ]

    def __str__(self):
        return f"{self.short_name} ({self.get_reference_type_display()})"

    def get_absolute_url(self):
        return reverse("documentation:legal_reference_detail", kwargs={"pk": self.pk})

    @property
    def disclaimer(self):
        """Return the standard legal disclaimer."""
        return (
            "This information is provided for educational purposes only and does not "
            "constitute legal advice. For legal matters related to your VA claim, "
            "consult with an accredited VA claims agent, Veterans Service Organization "
            "representative, or attorney."
        )
