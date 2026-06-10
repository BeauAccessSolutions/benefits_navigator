import csv
from django.contrib import admin
from django.http import HttpResponse
from django.utils import timezone
from .models import (
    JourneyStage,
    UserJourneyEvent,
    JourneyMilestone,
    Deadline,
    AuditLog,
    DataRetentionPolicy,
    SupportiveMessage,
    Feedback,
    SupportRequest,
    SystemHealthMetric,
    ProcessingFailure,
)


@admin.register(JourneyStage)
class JourneyStageAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'order', 'icon', 'color']
    list_filter = ['color', 'icon']
    search_fields = ['code', 'name']
    ordering = ['order']


@admin.register(UserJourneyEvent)
class UserJourneyEventAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'stage', 'event_date', 'is_completed', 'event_type']
    list_filter = ['is_completed', 'event_type', 'stage']
    search_fields = ['title', 'user__email']
    date_hierarchy = 'event_date'
    raw_id_fields = ['user', 'claim', 'appeal']


@admin.register(JourneyMilestone)
class JourneyMilestoneAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'milestone_type', 'date']
    list_filter = ['milestone_type']
    search_fields = ['title', 'user__email']
    date_hierarchy = 'date'
    raw_id_fields = ['user']


@admin.register(Deadline)
class DeadlineAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'deadline_date', 'priority', 'is_completed', 'reminder_sent']
    list_filter = ['priority', 'is_completed', 'reminder_sent']
    search_fields = ['title', 'user__email']
    date_hierarchy = 'deadline_date'
    raw_id_fields = ['user', 'claim', 'appeal']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'user_email', 'action', 'resource_type', 'success', 'ip_address']
    list_filter = ['action', 'success', 'resource_type']
    search_fields = ['user_email', 'ip_address', 'request_path']
    date_hierarchy = 'timestamp'
    readonly_fields = [
        'timestamp', 'user', 'user_email', 'action', 'ip_address',
        'user_agent', 'request_path', 'request_method', 'resource_type',
        'resource_id', 'details', 'success', 'error_message'
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(DataRetentionPolicy)
class DataRetentionPolicyAdmin(admin.ModelAdmin):
    list_display = ['data_type', 'retention_days', 'is_active', 'last_cleanup']
    list_filter = ['is_active', 'data_type']


@admin.register(SupportiveMessage)
class SupportiveMessageAdmin(admin.ModelAdmin):
    list_display = ['context', 'message_preview', 'tone', 'icon', 'is_active', 'order']
    list_filter = ['context', 'tone', 'is_active']
    search_fields = ['message']
    ordering = ['context', 'order']
    list_editable = ['is_active', 'order']

    fieldsets = (
        (None, {
            'fields': ('context', 'message', 'tone')
        }),
        ('Display', {
            'fields': ('icon', 'order', 'is_active')
        }),
    )

    def message_preview(self, obj):
        return obj.message[:75] + '...' if len(obj.message) > 75 else obj.message
    message_preview.short_description = 'Message'


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'rating_icon', 'category', 'page_title_short',
        'user_display', 'status', 'has_comment'
    ]
    list_filter = ['rating', 'category', 'status', 'created_at']
    search_fields = ['page_url', 'page_title', 'comment', 'user__email']
    date_hierarchy = 'created_at'
    readonly_fields = [
        'created_at', 'updated_at', 'user', 'page_url', 'page_title',
        'rating', 'category', 'comment', 'user_agent', 'session_key'
    ]
    raw_id_fields = ['reviewed_by']
    actions = ['export_to_csv', 'mark_reviewed', 'mark_addressed']

    fieldsets = (
        ('Feedback Details', {
            'fields': ('rating', 'category', 'comment', 'page_url', 'page_title')
        }),
        ('Submitter', {
            'fields': ('user', 'user_agent', 'session_key')
        }),
        ('Admin', {
            'fields': ('status', 'admin_notes', 'reviewed_by', 'reviewed_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def rating_icon(self, obj):
        icons = {
            'positive': '👍',
            'negative': '👎',
            'neutral': '➖',
        }
        return icons.get(obj.rating, '?')
    rating_icon.short_description = 'Rating'

    def page_title_short(self, obj):
        if obj.page_title:
            return obj.page_title[:40] + '...' if len(obj.page_title) > 40 else obj.page_title
        return obj.page_url[:40]
    page_title_short.short_description = 'Page'

    def user_display(self, obj):
        return obj.user.email if obj.user else 'Anonymous'
    user_display.short_description = 'User'

    def has_comment(self, obj):
        return bool(obj.comment)
    has_comment.boolean = True
    has_comment.short_description = 'Comment?'

    @admin.action(description='Export selected feedback to CSV')
    def export_to_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="feedback_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Date', 'Rating', 'Category', 'Page URL', 'Page Title',
            'Comment', 'User', 'Status', 'Admin Notes'
        ])

        for feedback in queryset:
            writer.writerow([
                feedback.created_at.strftime('%Y-%m-%d %H:%M'),
                feedback.get_rating_display(),
                feedback.get_category_display(),
                feedback.page_url,
                feedback.page_title,
                feedback.comment,
                feedback.user.email if feedback.user else 'Anonymous',
                feedback.get_status_display(),
                feedback.admin_notes,
            ])

        return response

    @admin.action(description='Mark selected as Reviewed')
    def mark_reviewed(self, request, queryset):
        queryset.update(
            status='reviewed',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )

    @admin.action(description='Mark selected as Addressed')
    def mark_addressed(self, request, queryset):
        queryset.update(
            status='addressed',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'status_badge', 'priority_badge', 'category',
        'subject_short', 'email', 'assigned_to'
    ]
    list_filter = ['status', 'priority', 'category', 'created_at']
    search_fields = ['subject', 'message', 'email', 'name']
    date_hierarchy = 'created_at'
    readonly_fields = [
        'created_at', 'updated_at', 'user', 'email', 'name',
        'category', 'subject', 'message', 'page_url', 'user_agent'
    ]
    raw_id_fields = ['assigned_to']
    actions = ['mark_in_progress', 'mark_resolved', 'mark_closed', 'export_to_csv']

    fieldsets = (
        ('Request Details', {
            'fields': ('category', 'subject', 'message')
        }),
        ('Submitter', {
            'fields': ('user', 'name', 'email')
        }),
        ('Context', {
            'fields': ('page_url', 'user_agent'),
            'classes': ('collapse',)
        }),
        ('Admin', {
            'fields': ('status', 'priority', 'assigned_to', 'admin_notes', 'resolved_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        colors = {
            'new': '🔵',
            'in_progress': '🟡',
            'waiting': '🟠',
            'resolved': '🟢',
            'closed': '⚫',
        }
        return f"{colors.get(obj.status, '⚪')} {obj.get_status_display()}"
    status_badge.short_description = 'Status'

    def priority_badge(self, obj):
        colors = {
            'low': '🟢',
            'medium': '🟡',
            'high': '🟠',
            'urgent': '🔴',
        }
        return f"{colors.get(obj.priority, '⚪')} {obj.get_priority_display()}"
    priority_badge.short_description = 'Priority'

    def subject_short(self, obj):
        return obj.subject[:50] + '...' if len(obj.subject) > 50 else obj.subject
    subject_short.short_description = 'Subject'

    @admin.action(description='Mark as In Progress')
    def mark_in_progress(self, request, queryset):
        queryset.update(status='in_progress', assigned_to=request.user)

    @admin.action(description='Mark as Resolved')
    def mark_resolved(self, request, queryset):
        queryset.update(status='resolved', resolved_at=timezone.now())

    @admin.action(description='Mark as Closed')
    def mark_closed(self, request, queryset):
        queryset.update(status='closed')

    @admin.action(description='Export to CSV')
    def export_to_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="support_requests_{timezone.now().strftime("%Y%m%d")}.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Date', 'Status', 'Priority', 'Category', 'Subject',
            'Email', 'Name', 'Message', 'Assigned To'
        ])

        for req in queryset:
            writer.writerow([
                req.created_at.strftime('%Y-%m-%d %H:%M'),
                req.get_status_display(),
                req.get_priority_display(),
                req.get_category_display(),
                req.subject,
                req.email,
                req.name,
                req.message[:500],
                req.assigned_to.email if req.assigned_to else '',
            ])

        return response


# =============================================================================
# HEALTH MONITORING ADMIN
# =============================================================================

@admin.register(SystemHealthMetric)
class SystemHealthMetricAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'metric_type', 'value', 'details_preview']
    list_filter = ['metric_type', 'timestamp']
    date_hierarchy = 'timestamp'
    readonly_fields = ['timestamp', 'metric_type', 'value', 'details']

    def details_preview(self, obj):
        import json
        if obj.details:
            return json.dumps(obj.details)[:50]
        return '-'
    details_preview.short_description = 'Details'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProcessingFailure)
class ProcessingFailureAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'status_badge', 'failure_type', 'error_preview',
        'document_id', 'retry_count', 'alert_sent'
    ]
    list_filter = ['status', 'failure_type', 'alert_sent', 'created_at']
    search_fields = ['error_message', 'task_id', 'document_id']
    date_hierarchy = 'created_at'
    readonly_fields = [
        'created_at', 'updated_at', 'failure_type', 'document_id',
        'task_id', 'error_message', 'stack_trace', 'retry_count',
        'alert_sent', 'alert_sent_at'
    ]
    raw_id_fields = ['resolved_by']
    actions = ['mark_resolved', 'mark_ignored', 'send_alert']

    fieldsets = (
        ('Failure Details', {
            'fields': ('failure_type', 'error_message', 'stack_trace')
        }),
        ('Context', {
            'fields': ('document_id', 'task_id', 'retry_count')
        }),
        ('Alert', {
            'fields': ('alert_sent', 'alert_sent_at')
        }),
        ('Resolution', {
            'fields': ('status', 'resolved_by', 'resolution_notes', 'resolved_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        colors = {
            'new': '🔴',
            'investigating': '🟡',
            'resolved': '🟢',
            'ignored': '⚫',
        }
        return f"{colors.get(obj.status, '⚪')} {obj.get_status_display()}"
    status_badge.short_description = 'Status'

    def error_preview(self, obj):
        return obj.error_message[:60] + '...' if len(obj.error_message) > 60 else obj.error_message
    error_preview.short_description = 'Error'

    @admin.action(description='Mark as Resolved')
    def mark_resolved(self, request, queryset):
        queryset.update(
            status='resolved',
            resolved_by=request.user,
            resolved_at=timezone.now()
        )

    @admin.action(description='Mark as Ignored')
    def mark_ignored(self, request, queryset):
        queryset.update(status='ignored')

    @admin.action(description='Send Alert for Selected')
    def send_alert(self, request, queryset):
        for failure in queryset:
            if not failure.alert_sent:
                failure.send_alert()


class PIIRedactedAdminMixin:
    """
    Operator access minimization (privacy plan Phase 4).

    - Set `pii_redacted_fields` to hide PII fields from admin forms on
      models without explicit fieldsets (uses get_exclude). Admins with
      fieldsets must simply omit PII fields from them.
    - Every admin change/history view writes an AuditLog row, so operator
      access to veteran records appears in the same ledger veterans see
      on /data-activity/ (for Document and VeteranCase resource types).
    """

    pii_redacted_fields = ()
    audit_resource_type = None  # defaults to the model class name

    def get_exclude(self, request, obj=None):
        exclude = super().get_exclude(request, obj) or ()
        return tuple(exclude) + tuple(self.pii_redacted_fields)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        self._log_admin_access(request, object_id, 'admin_change_view')
        return super().change_view(request, object_id, form_url, extra_context)

    def history_view(self, request, object_id, extra_context=None):
        self._log_admin_access(request, object_id, 'admin_history_view')
        return super().history_view(request, object_id, extra_context)

    def _log_admin_access(self, request, object_id, event):
        try:
            resource_id = int(object_id)
        except (TypeError, ValueError):
            resource_id = None
        AuditLog.log(
            action='admin_action',
            request=request,
            resource_type=self.audit_resource_type or self.model.__name__,
            resource_id=resource_id,
            details={'event': event, 'model': self.model._meta.label},
        )
