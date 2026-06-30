"""
Django admin configuration for claims app
"""

from django.contrib import admin
from .models import Document, Claim


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Admin for Document model"""

    list_display = [
        "file_name",
        "user",
        "document_type",
        "status",
        "file_size_mb",
        "page_count",
        "created_at",
    ]
    list_filter = ["status", "document_type", "created_at"]
    search_fields = ["file_name", "user__email"]
    raw_id_fields = ["user", "claim"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "processed_at",
        "file_size",
        "ocr_status",
        "ocr_length",
        "ocr_confidence",
    ]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("user", "claim", "file", "file_name", "document_type")},
        ),
        ("File Details", {"fields": ("file_size", "mime_type", "page_count")}),
        (
            "Processing Status",
            {
                "fields": (
                    "status",
                    "processed_at",
                    "processing_duration",
                    "error_message",
                )
            },
        ),
        (
            "OCR Results",
            {
                # ocr_text removed for PHI protection - only metadata displayed
                "fields": ("ocr_status", "ocr_length", "ocr_confidence"),
                "classes": ("collapse",),
            },
        ),
        (
            "AI Analysis",
            {
                "fields": ("ai_summary", "ai_model_used", "ai_tokens_used"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    """Admin for Claim model"""

    list_display = [
        "title",
        "user",
        "claim_type",
        "status",
        "submission_date",
        "document_count",
    ]
    list_filter = ["claim_type", "status", "created_at"]
    search_fields = ["title", "user__email", "description"]
    raw_id_fields = ["user"]
    readonly_fields = ["created_at", "updated_at"]
