"""
Django admin configuration for appeals app
"""

from django.contrib import admin
from .models import Appeal, AppealGuidance, AppealDocument, AppealNote


@admin.register(AppealGuidance)
class AppealGuidanceAdmin(admin.ModelAdmin):
    """Admin for AppealGuidance model - step-by-step appeal guides."""

    list_display = [
        "title",
        "appeal_type",
        "va_form_number",
        "average_processing_days",
        "is_published",
        "order",
    ]
    list_filter = ["appeal_type", "is_published"]
    search_fields = ["title", "overview"]
    prepopulated_fields = {"slug": ("title",)}
    ordering = ["order", "appeal_type"]

    fieldsets = (
        (
            "Basic Info",
            {
                "fields": (
                    "title",
                    "slug",
                    "appeal_type",
                    "va_form_number",
                    "average_processing_days",
                )
            },
        ),
        (
            "When to Use",
            {
                "fields": ("when_to_use", "when_not_to_use"),
                "classes": ("collapse",),
            },
        ),
        (
            "Content",
            {
                "fields": (
                    "overview",
                    "requirements",
                    "step_by_step",
                    "evidence_guidance",
                    "common_mistakes",
                    "after_submission",
                    "tips",
                )
            },
        ),
        (
            "Checklist",
            {
                "fields": ("checklist_items",),
                "classes": ("collapse",),
            },
        ),
        ("Settings", {"fields": ("order", "is_published")}),
    )


class AppealDocumentInline(admin.TabularInline):
    """Inline for appeal documents."""

    model = AppealDocument
    extra = 0
    fields = ["document_type", "title", "file", "is_submitted"]


class AppealNoteInline(admin.TabularInline):
    """Inline for appeal notes."""

    model = AppealNote
    extra = 0
    fields = ["note_type", "content", "is_important", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(Appeal)
class AppealAdmin(admin.ModelAdmin):
    """Admin for Appeal model - user appeal cases."""

    list_display = [
        "user",
        "appeal_type",
        "status",
        "original_decision_date",
        "deadline",
        "days_until_deadline",
        "created_at",
    ]
    list_filter = ["appeal_type", "status", "decision_outcome", "created_at"]
    search_fields = ["user__email", "conditions_appealed"]
    raw_id_fields = ["user"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "days_until_deadline",
        "is_deadline_urgent",
        "recommended_appeal_type",
    ]
    date_hierarchy = "created_at"
    inlines = [AppealDocumentInline, AppealNoteInline]

    fieldsets = (
        ("User & Status", {"fields": ("user", "appeal_type", "status")}),
        (
            "Original Decision",
            {
                "fields": (
                    "original_decision_date",
                    "deadline",
                    "days_until_deadline",
                    "is_deadline_urgent",
                )
            },
        ),
        (
            "What's Being Appealed",
            {"fields": ("conditions_appealed", "denial_reasons")},
        ),
        (
            "Decision Tree Answers",
            {
                "fields": (
                    "has_new_evidence",
                    "believes_va_error",
                    "wants_hearing",
                    "recommended_appeal_type",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Workflow",
            {
                "fields": ("current_step", "steps_completed", "workflow_state"),
                "classes": ("collapse",),
            },
        ),
        (
            "Submission",
            {
                "fields": ("submission_date", "va_confirmation_number"),
                "classes": ("collapse",),
            },
        ),
        (
            "Decision",
            {
                "fields": (
                    "decision_received_date",
                    "decision_outcome",
                    "decision_notes",
                ),
                "classes": ("collapse",),
            },
        ),
        ("Notes", {"fields": ("notes",)}),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def days_until_deadline(self, obj):
        days = obj.days_until_deadline
        if days is None:
            return "-"
        if days < 0:
            return f"{abs(days)} days OVERDUE"
        if days <= 30:
            return f"{days} days (URGENT)"
        return f"{days} days"

    days_until_deadline.short_description = "Days Until Deadline"


@admin.register(AppealDocument)
class AppealDocumentAdmin(admin.ModelAdmin):
    """Admin for AppealDocument model."""

    list_display = ["title", "appeal", "document_type", "is_submitted", "created_at"]
    list_filter = ["document_type", "is_submitted"]
    search_fields = ["title", "appeal__user__email"]
    raw_id_fields = ["appeal"]


@admin.register(AppealNote)
class AppealNoteAdmin(admin.ModelAdmin):
    """Admin for AppealNote model."""

    list_display = ["appeal", "note_type", "is_important", "created_at"]
    list_filter = ["note_type", "is_important"]
    search_fields = ["content", "appeal__user__email"]
    raw_id_fields = ["appeal"]
