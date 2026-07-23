from django.contrib import admin
from django.utils.html import format_html
from .models import (
    AgentInteraction,
    AssistantThread,
    AssistantTurn,
    DecisionLetterAnalysis,
    EvidenceGapAnalysis,
    PersonalStatement,
    M21ManualSection,
    M21TopicIndex,
    M21ScrapeJob,
)


@admin.register(AssistantThread)
class AssistantThreadAdmin(admin.ModelAdmin):
    # Metadata only — the transcript is PHI, so no content is surfaced here and
    # only the owner's email is searchable (never turn content).
    list_display = ["id", "user", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user__email"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(AssistantTurn)
class AssistantTurnAdmin(admin.ModelAdmin):
    # PHI: content is not shown in the list and is not searchable.
    list_display = ["id", "thread", "user", "role", "stopped", "created_at"]
    list_filter = ["role", "stopped", "created_at"]
    search_fields = ["user__email"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(AgentInteraction)
class AgentInteractionAdmin(admin.ModelAdmin):
    list_display = ["id", "agent_type", "user", "status", "tokens_used", "created_at"]
    list_filter = ["agent_type", "status", "created_at"]
    search_fields = ["user__email", "error_message"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(DecisionLetterAnalysis)
class DecisionLetterAnalysisAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "decision_date", "created_at"]
    list_filter = ["created_at", "decision_date"]
    # raw_text removed from search_fields for PHI protection
    search_fields = ["user__email", "summary"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(EvidenceGapAnalysis)
class EvidenceGapAnalysisAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "readiness_score", "created_at"]
    list_filter = ["created_at", "readiness_score"]
    search_fields = ["user__email", "service_branch"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(PersonalStatement)
class PersonalStatementAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "condition",
        "statement_type",
        "is_finalized",
        "word_count",
        "created_at",
    ]
    list_filter = ["statement_type", "is_finalized", "created_at"]
    # generated_statement / final_statement are encrypted at rest, not searchable.
    search_fields = [
        "user__email",
        "condition",
    ]
    readonly_fields = ["created_at", "updated_at", "word_count"]
    date_hierarchy = "created_at"


@admin.register(M21ManualSection)
class M21ManualSectionAdmin(admin.ModelAdmin):
    list_display = [
        "reference",
        "title_short",
        "part",
        "scrape_status",
        "last_scraped",
        "knowva_link",
    ]
    list_filter = ["part", "scrape_status", "part_number", "last_scraped"]
    search_fields = ["reference", "title", "content", "search_text", "article_id"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "scraped_at",
        "last_scraped",
        "search_text",
    ]
    fieldsets = (
        (
            "Reference Information",
            {
                "fields": (
                    "reference",
                    "full_reference",
                    "part",
                    "part_number",
                    "part_title",
                    "subpart",
                    "chapter",
                    "section",
                )
            },
        ),
        (
            "Content",
            {"fields": ("title", "overview", "content", "topics", "references")},
        ),
        (
            "KnowVA Metadata",
            {"fields": ("article_id", "knowva_url", "last_updated_va")},
        ),
        (
            "Scraping Metadata",
            {
                "fields": (
                    "scrape_status",
                    "scrape_error",
                    "scraped_at",
                    "last_scraped",
                ),
                "classes": ("collapse",),
            },
        ),
    )
    date_hierarchy = "last_scraped"

    def title_short(self, obj):
        """Truncate title for list display."""
        if len(obj.title) > 60:
            return obj.title[:57] + "..."
        return obj.title

    title_short.short_description = "Title"

    def knowva_link(self, obj):
        """Create clickable link to KnowVA."""
        if obj.knowva_url:
            return format_html(
                '<a href="{}" target="_blank">View on KnowVA</a>', obj.knowva_url
            )
        return "-"

    knowva_link.short_description = "KnowVA"


@admin.register(M21TopicIndex)
class M21TopicIndexAdmin(admin.ModelAdmin):
    list_display = ["topic", "title", "section_count", "priority"]
    list_filter = ["topic", "priority"]
    search_fields = ["title", "description", "keywords"]
    filter_horizontal = ["sections"]
    readonly_fields = ["created_at", "updated_at"]

    def section_count(self, obj):
        """Display number of associated sections."""
        return obj.sections.count()

    section_count.short_description = "Sections"


@admin.register(M21ScrapeJob)
class M21ScrapeJobAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "status",
        "progress",
        "started_at",
        "duration_display",
        "force_update",
    ]
    list_filter = ["status", "force_update", "started_at"]
    search_fields = ["error_log", "summary"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "duration_seconds",
        "progress_percentage",
    ]
    fieldsets = (
        ("Job Information", {"fields": ("status", "target_parts", "force_update")}),
        (
            "Progress",
            {
                "fields": (
                    "total_sections",
                    "sections_completed",
                    "sections_failed",
                    "progress_percentage",
                )
            },
        ),
        ("Timing", {"fields": ("started_at", "completed_at", "duration_seconds")}),
        ("Results", {"fields": ("summary", "error_log")}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    date_hierarchy = "started_at"

    def progress(self, obj):
        """Display progress bar."""
        if obj.total_sections == 0:
            return "0%"
        pct = obj.progress_percentage
        color = (
            "green"
            if obj.status == "completed"
            else "blue" if obj.status == "running" else "red"
        )
        return format_html(
            '<div style="width:100px; background:#f0f0f0; border:1px solid #ccc;">'
            '<div style="width:{}%; background:{}; height:20px; text-align:center; color:white;">{:.0f}%</div>'
            "</div>",
            pct,
            color,
            pct,
        )

    progress.short_description = "Progress"

    def duration_display(self, obj):
        """Display duration in human-readable format."""
        if obj.duration_seconds:
            hours = obj.duration_seconds // 3600
            minutes = (obj.duration_seconds % 3600) // 60
            seconds = obj.duration_seconds % 60
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        return "-"

    duration_display.short_description = "Duration"
