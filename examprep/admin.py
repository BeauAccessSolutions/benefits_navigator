"""
Django admin configuration for examprep app
"""

from django.contrib import admin
from .models import ExamGuidance, ExamChecklist, GlossaryTerm


@admin.register(ExamGuidance)
class ExamGuidanceAdmin(admin.ModelAdmin):
    """Admin for ExamGuidance model"""

    list_display = ["title", "category", "order", "is_published", "created_at"]
    list_filter = ["category", "is_published", "created_at"]
    search_fields = ["title", "introduction", "preparation_tips"]
    prepopulated_fields = {"slug": ("title",)}
    list_editable = ["order", "is_published"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("title", "slug", "category", "order", "is_published")},
        ),
        (
            "Content Sections",
            {
                "fields": (
                    "introduction",
                    "what_exam_measures",
                    "physical_tests",
                    "questions_to_expect",
                    "preparation_tips",
                    "day_of_guidance",
                    "common_mistakes",
                    "after_exam",
                )
            },
        ),
        ("Interactive Elements", {"fields": ("checklist_items",)}),
        ("SEO & Metadata", {"fields": ("meta_description",), "classes": ("collapse",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(GlossaryTerm)
class GlossaryTermAdmin(admin.ModelAdmin):
    """Admin for GlossaryTerm model"""

    list_display = ["term", "show_in_tooltips", "order", "created_at"]
    list_filter = ["show_in_tooltips", "created_at"]
    search_fields = ["term", "plain_language", "context"]
    list_editable = ["show_in_tooltips", "order"]
    readonly_fields = ["created_at", "updated_at"]
    filter_horizontal = ["related_terms"]

    fieldsets = (
        ("Term Information", {"fields": ("term", "plain_language")}),
        ("Additional Context", {"fields": ("context", "example")}),
        (
            "Relationships & Display",
            {"fields": ("related_terms", "show_in_tooltips", "order")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(ExamChecklist)
class ExamChecklistAdmin(admin.ModelAdmin):
    """Admin for ExamChecklist model"""

    list_display = ["user", "condition", "exam_date", "exam_completed", "created_at"]
    list_filter = ["exam_completed", "exam_date", "created_at"]
    search_fields = ["user__email", "condition"]
    raw_id_fields = ["user", "guidance"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "days_until_exam",
        "completion_percentage",
    ]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("user", "condition", "exam_date", "guidance")},
        ),
        (
            "Progress Tracking",
            {"fields": ("tasks_completed", "days_until_exam", "completion_percentage")},
        ),
        (
            "Preparation Notes",
            {
                "fields": (
                    "symptom_notes",
                    "worst_day_description",
                    "functional_limitations",
                    "questions_for_examiner",
                )
            },
        ),
        (
            "Post-Exam",
            {"fields": ("exam_completed", "exam_notes"), "classes": ("collapse",)},
        ),
        ("Reminders", {"fields": ("reminder_sent",), "classes": ("collapse",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
