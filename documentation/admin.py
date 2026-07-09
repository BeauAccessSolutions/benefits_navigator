"""
Admin configuration for the documentation app.

Provides management interface for VA Forms, C&P Exam Guides, and Legal References.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.contrib.postgres.search import SearchVector

from .models import DocumentCategory, VAForm, CPExamGuideCondition, LegalReference


@admin.register(DocumentCategory)
class DocumentCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "order", "is_active", "form_count"]
    list_editable = ["order", "is_active"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name", "description"]

    def form_count(self, obj):
        return obj.forms.count()

    form_count.short_description = "Forms"


@admin.register(VAForm)
class VAFormAdmin(admin.ModelAdmin):
    list_display = [
        "form_number",
        "title",
        "category",
        "is_active",
        "last_updated",
        "view_official",
    ]
    list_filter = ["is_active", "category", "workflow_stages"]
    search_fields = ["form_number", "title", "description", "instructions"]
    readonly_fields = ["created_at", "updated_at", "search_vector"]
    filter_horizontal = ["related_forms"]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("form_number", "title", "description", "category")},
        ),
        ("URLs", {"fields": ("official_url", "instructions_url")}),
        (
            "Instructions & Tips",
            {"fields": ("instructions", "tips", "common_mistakes", "deadline_info")},
        ),
        (
            "Workflow",
            {
                "fields": ("workflow_stages",),
                "description": "Select which workflow stages use this form",
            },
        ),
        ("Relationships", {"fields": ("related_forms",)}),
        ("Status", {"fields": ("is_active", "last_updated")}),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at", "search_vector"),
                "classes": ("collapse",),
            },
        ),
    )

    def view_official(self, obj):
        return format_html(
            '<a href="{}" target="_blank">View Form</a>', obj.official_url
        )

    view_official.short_description = "Official Form"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Update search vector after save
        VAForm.objects.filter(pk=obj.pk).update(
            search_vector=SearchVector("form_number", weight="A")
            + SearchVector("title", weight="A")
            + SearchVector("description", weight="B")
            + SearchVector("instructions", weight="C")
            + SearchVector("tips", weight="C")
        )


@admin.register(CPExamGuideCondition)
class CPExamGuideConditionAdmin(admin.ModelAdmin):
    list_display = [
        "condition_name",
        "category",
        "dbq_form",
        "is_published",
        "updated_at",
    ]
    list_filter = ["category", "is_published"]
    search_fields = ["condition_name", "what_to_expect", "tips"]
    prepopulated_fields = {"slug": ("condition_name",)}
    readonly_fields = ["created_at", "updated_at", "search_vector"]
    filter_horizontal = ["related_conditions"]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("condition_name", "slug", "category", "dbq_form")},
        ),
        (
            "Exam Information",
            {"fields": ("what_to_expect", "key_questions", "documentation_needed")},
        ),
        ("Preparation", {"fields": ("how_to_prepare", "tips", "red_flags")}),
        ("Rating Information", {"fields": ("rating_criteria_summary",)}),
        ("Relationships", {"fields": ("related_conditions", "related_form")}),
        ("Status", {"fields": ("is_published",)}),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at", "search_vector"),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Update search vector after save
        CPExamGuideCondition.objects.filter(pk=obj.pk).update(
            search_vector=SearchVector("condition_name", weight="A")
            + SearchVector("what_to_expect", weight="B")
            + SearchVector("tips", weight="B")
            + SearchVector("how_to_prepare", weight="C")
        )


@admin.register(LegalReference)
class LegalReferenceAdmin(admin.ModelAdmin):
    list_display = [
        "short_name",
        "reference_type",
        "date_issued",
        "is_active",
        "has_superseding",
    ]
    list_filter = ["reference_type", "is_active"]
    search_fields = ["citation", "short_name", "title", "summary"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "search_vector",
        "disclaimer_display",
    ]
    raw_id_fields = ["superseded_by"]

    fieldsets = (
        (
            "Citation",
            {
                "fields": (
                    "reference_type",
                    "citation",
                    "short_name",
                    "title",
                    "date_issued",
                )
            },
        ),
        ("Content", {"fields": ("summary", "key_points", "relevance")}),
        ("Links & Related", {"fields": ("url", "related_conditions")}),
        ("Status", {"fields": ("is_active", "superseded_by")}),
        ("Legal Notice", {"fields": ("disclaimer_display",), "classes": ("wide",)}),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at", "search_vector"),
                "classes": ("collapse",),
            },
        ),
    )

    def has_superseding(self, obj):
        return obj.superseded_by is not None

    has_superseding.boolean = True
    has_superseding.short_description = "Superseded"

    def disclaimer_display(self, obj):
        return format_html(
            '<div style="background: #fff3cd; padding: 10px; border-radius: 4px;">'
            "<strong>Legal Disclaimer:</strong><br>{}</div>",
            obj.disclaimer,
        )

    disclaimer_display.short_description = "Disclaimer"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Update search vector after save
        LegalReference.objects.filter(pk=obj.pk).update(
            search_vector=SearchVector("citation", weight="A")
            + SearchVector("short_name", weight="A")
            + SearchVector("title", weight="A")
            + SearchVector("summary", weight="B")
            + SearchVector("relevance", weight="C")
        )
