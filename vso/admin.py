from django.contrib import admin
from django.utils.html import format_html
from .models import (
    VeteranCase,
    CaseNote,
    SharedDocument,
    SharedAnalysis,
    CaseChecklist,
    ChecklistItem,
)


class CaseNoteInline(admin.TabularInline):
    model = CaseNote
    extra = 0
    readonly_fields = ("created_at", "author")
    fields = (
        "note_type",
        "subject",
        "is_action_item",
        "action_due_date",
        "action_completed",
        "visible_to_veteran",
        "author",
        "created_at",
    )
    ordering = ("-created_at",)


class SharedDocumentInline(admin.TabularInline):
    model = SharedDocument
    extra = 0
    readonly_fields = ("shared_at", "shared_by")
    fields = ("document", "status", "include_ai_analysis", "shared_by", "shared_at")


class SharedAnalysisInline(admin.TabularInline):
    model = SharedAnalysis
    extra = 0
    readonly_fields = ("shared_at", "shared_by")
    fields = (
        "analysis_type",
        "rating_analysis",
        "shared_by",
        "shared_at",
        "reviewed_by",
    )


class CaseChecklistInline(admin.TabularInline):
    model = CaseChecklist
    extra = 0
    readonly_fields = ("created_at",)
    fields = ("title", "description", "created_at")


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0
    readonly_fields = ("created_at", "completed_at")
    fields = (
        "item_type",
        "title",
        "order",
        "completed",
        "visible_to_veteran",
        "document",
    )


@admin.register(VeteranCase)
class VeteranCaseAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "veteran_email",
        "organization",
        "status_badge",
        "priority_badge",
        "assigned_to",
        "days_open_display",
        "created_at",
    )
    list_filter = ("status", "priority", "organization", "created_at")
    search_fields = (
        "title",
        "veteran__email",
        "veteran__first_name",
        "veteran__last_name",
        "description",
    )
    readonly_fields = ("created_at", "updated_at", "closed_at", "closed_by")
    date_hierarchy = "created_at"

    fieldsets = (
        (
            "Case Information",
            {"fields": ("title", "description", "status", "priority")},
        ),
        ("Relationships", {"fields": ("organization", "veteran", "assigned_to")}),
        ("Conditions", {"fields": ("conditions",), "classes": ("collapse",)}),
        (
            "Key Dates",
            {
                "fields": (
                    "intake_date",
                    "claim_filed_date",
                    "decision_date",
                    "appeal_deadline",
                    "next_action_date",
                )
            },
        ),
        (
            "Outcome Tracking",
            {
                "fields": (
                    "initial_combined_rating",
                    "final_combined_rating",
                    "retroactive_pay",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Veteran Consent",
            {
                "fields": ("veteran_consent_date", "consent_document"),
                "classes": ("collapse",),
            },
        ),
        (
            "Closure",
            {
                "fields": ("closed_at", "closed_by", "closure_notes"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    inlines = [
        CaseNoteInline,
        SharedDocumentInline,
        SharedAnalysisInline,
        CaseChecklistInline,
    ]

    def veteran_email(self, obj):
        return obj.veteran.email

    veteran_email.short_description = "Veteran"
    veteran_email.admin_order_field = "veteran__email"

    def status_badge(self, obj):
        colors = {
            "intake": "blue",
            "gathering_evidence": "yellow",
            "claim_filed": "purple",
            "pending_decision": "orange",
            "decision_received": "teal",
            "appeal_in_progress": "indigo",
            "closed_won": "green",
            "closed_denied": "red",
            "closed_withdrawn": "gray",
            "on_hold": "gray",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"

    def priority_badge(self, obj):
        colors = {
            "low": "#6b7280",
            "normal": "#3b82f6",
            "high": "#f59e0b",
            "urgent": "#ef4444",
        }
        color = colors.get(obj.priority, "#6b7280")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_priority_display(),
        )

    priority_badge.short_description = "Priority"
    priority_badge.admin_order_field = "priority"

    def days_open_display(self, obj):
        days = obj.days_open
        if obj.is_overdue:
            return format_html(
                '<span style="color: red; font-weight: bold;">{} days (OVERDUE)</span>',
                days,
            )
        return f"{days} days"

    days_open_display.short_description = "Days Open"


@admin.register(CaseNote)
class CaseNoteAdmin(admin.ModelAdmin):
    list_display = (
        "subject",
        "case",
        "note_type",
        "author",
        "is_action_item",
        "action_status",
        "visible_to_veteran",
        "created_at",
    )
    list_filter = (
        "note_type",
        "is_action_item",
        "action_completed",
        "visible_to_veteran",
        "created_at",
    )
    search_fields = ("subject", "content", "case__title", "author__email")
    readonly_fields = ("created_at", "updated_at", "action_completed_at")
    date_hierarchy = "created_at"

    fieldsets = (
        (
            "Note Details",
            {"fields": ("case", "author", "note_type", "subject", "content")},
        ),
        (
            "Action Item",
            {
                "fields": (
                    "is_action_item",
                    "action_due_date",
                    "action_completed",
                    "action_completed_at",
                    "action_completed_by",
                ),
                "classes": ("collapse",),
            },
        ),
        ("Visibility", {"fields": ("visible_to_veteran",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def action_status(self, obj):
        if not obj.is_action_item:
            return "-"
        if obj.action_completed:
            return format_html('<span style="color: green;">✓ Completed</span>')
        if obj.action_due_date:
            from django.utils import timezone

            if obj.action_due_date < timezone.now().date():
                return format_html(
                    '<span style="color: red; font-weight: bold;">OVERDUE</span>'
                )
            return format_html(
                '<span style="color: orange;">Due {}</span>',
                obj.action_due_date.strftime("%m/%d"),
            )
        return format_html('<span style="color: blue;">Pending</span>')

    action_status.short_description = "Action Status"


@admin.register(SharedDocument)
class SharedDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "document",
        "case",
        "status",
        "shared_by",
        "shared_at",
        "reviewed_by",
        "include_ai_analysis",
    )
    list_filter = ("status", "include_ai_analysis", "shared_at")
    search_fields = ("document__file_name", "case__title", "shared_by__email")
    readonly_fields = ("shared_at", "reviewed_at", "created_at", "updated_at")
    date_hierarchy = "shared_at"

    fieldsets = (
        (
            "Document Sharing",
            {
                "fields": (
                    "case",
                    "document",
                    "shared_by",
                    "shared_at",
                    "include_ai_analysis",
                )
            },
        ),
        (
            "Review Status",
            {"fields": ("status", "reviewed_by", "reviewed_at", "review_notes")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(SharedAnalysis)
class SharedAnalysisAdmin(admin.ModelAdmin):
    list_display = ("analysis_type", "case", "shared_by", "shared_at", "reviewed_by")
    list_filter = ("analysis_type", "shared_at")
    search_fields = ("case__title", "shared_by__email", "vso_notes")
    readonly_fields = ("shared_at", "reviewed_at", "created_at", "updated_at")
    date_hierarchy = "shared_at"

    fieldsets = (
        (
            "Analysis Sharing",
            {"fields": ("case", "analysis_type", "shared_by", "shared_at")},
        ),
        (
            "Linked Analysis",
            {
                "fields": ("rating_analysis", "decision_analysis", "denial_decoding"),
                "classes": ("collapse",),
            },
        ),
        ("VSO Review", {"fields": ("reviewed_by", "reviewed_at", "vso_notes")}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(CaseChecklist)
class CaseChecklistAdmin(admin.ModelAdmin):
    list_display = ("title", "case", "item_count", "completion_display", "created_at")
    list_filter = ("created_at",)
    search_fields = ("title", "description", "case__title")
    readonly_fields = ("created_at", "updated_at")

    inlines = [ChecklistItemInline]

    fieldsets = (
        ("Checklist Details", {"fields": ("case", "title", "description")}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def item_count(self, obj):
        return obj.items.count()

    item_count.short_description = "# Items"

    def completion_display(self, obj):
        pct = obj.completion_percentage
        if pct == 100:
            color = "green"
        elif pct >= 50:
            color = "orange"
        else:
            color = "gray"
        return format_html('<span style="color: {};">{pct}%</span>', color, pct=pct)

    completion_display.short_description = "Completion"


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "checklist",
        "item_type",
        "completed",
        "visible_to_veteran",
        "order",
    )
    list_filter = ("item_type", "completed", "visible_to_veteran")
    search_fields = ("title", "description", "checklist__title")
    readonly_fields = ("created_at", "updated_at", "completed_at")
    ordering = ("checklist", "order")

    fieldsets = (
        (
            "Item Details",
            {"fields": ("checklist", "item_type", "title", "description", "order")},
        ),
        (
            "Status",
            {"fields": ("completed", "completed_at", "completed_by", "document")},
        ),
        ("Visibility", {"fields": ("visible_to_veteran",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
