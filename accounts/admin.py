"""
Django admin configuration for accounts app
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import Sum, Count
from django.utils.html import format_html

from core.admin import PIIRedactedAdminMixin
from .models import (
    User, UserProfile, Subscription, NotificationPreferences, UsageTracking,
    Organization, OrganizationMembership, OrganizationInvitation
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for User model"""
    list_display = ['email', 'first_name', 'last_name', 'is_verified', 'is_premium', 'is_staff', 'date_joined']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'is_verified', 'date_joined']
    search_fields = ['email', 'first_name', 'last_name']
    ordering = ['-date_joined']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        # phone_number removed for PII protection (encrypted at rest)
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'is_verified', 'groups', 'user_permissions')}),
        ('Stripe', {'fields': ('stripe_customer_id',)}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
    )


@admin.register(UserProfile)
class UserProfileAdmin(PIIRedactedAdminMixin, admin.ModelAdmin):
    """Admin for UserProfile — encrypted PII never rendered in admin."""
    pii_redacted_fields = ('date_of_birth', 'va_file_number')
    # 'age' (derived from DOB) removed from list_display for PII protection
    list_display = ['user', 'branch_of_service', 'disability_rating']
    list_filter = ['branch_of_service']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user']


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Admin for Subscription"""
    list_display = ['user', 'plan_type', 'status', 'current_period_end', 'cancel_at_period_end']
    list_filter = ['plan_type', 'status', 'cancel_at_period_end']
    search_fields = ['user__email', 'stripe_subscription_id', 'stripe_customer_id']
    raw_id_fields = ['user']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(NotificationPreferences)
class NotificationPreferencesAdmin(admin.ModelAdmin):
    """Admin for NotificationPreferences"""
    list_display = [
        'user', 'email_enabled', 'deadline_reminders', 'exam_reminders', 'document_analysis',
        'deadline_reminder_days', 'emails_sent_count', 'last_email_sent'
    ]
    list_filter = ['email_enabled', 'deadline_reminders', 'exam_reminders', 'document_analysis', 'weekly_summary']
    search_fields = ['user__email']
    raw_id_fields = ['user']
    readonly_fields = ['last_email_sent', 'emails_sent_count', 'created_at', 'updated_at']

    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Email Toggles', {
            'fields': ('email_enabled', 'deadline_reminders', 'exam_reminders', 'claim_updates', 'document_analysis', 'weekly_summary')
        }),
        ('Timing Preferences', {
            'fields': ('deadline_reminder_days', 'exam_reminder_days')
        }),
        ('Statistics', {
            'fields': ('last_email_sent', 'emails_sent_count'),
            'classes': ('collapse',)
        }),
    )


@admin.register(UsageTracking)
class UsageTrackingAdmin(admin.ModelAdmin):
    """Admin for UsageTracking with reporting features"""
    list_display = [
        'user',
        'is_premium_display',
        'documents_uploaded_this_month',
        'storage_used_display',
        'denial_decodes_this_month',
        'ai_analyses_this_month',
        'month_reset_date',
    ]
    list_filter = [
        'month_reset_date',
        ('user__subscription__plan_type', admin.AllValuesFieldListFilter),
    ]
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user']
    readonly_fields = [
        'storage_used_display',
        'is_premium_display',
        'usage_summary_display',
        'created_at',
        'updated_at',
    ]

    fieldsets = (
        ('User', {
            'fields': ('user', 'is_premium_display')
        }),
        ('Monthly Usage (Resets Each Month)', {
            'fields': (
                'documents_uploaded_this_month',
                'denial_decodes_this_month',
                'ai_analyses_this_month',
                'tokens_used_this_month',
                'month_reset_date',
            )
        }),
        ('Storage', {
            'fields': ('total_storage_bytes', 'storage_used_display')
        }),
        ('Lifetime Statistics', {
            'fields': (
                'total_documents_uploaded',
                'total_denial_decodes',
                'total_ai_analyses',
                'total_tokens_used',
            ),
            'classes': ('collapse',)
        }),
        ('Usage Summary', {
            'fields': ('usage_summary_display',),
            'classes': ('collapse',)
        }),
    )

    def is_premium_display(self, obj):
        """Display premium status with color coding."""
        if obj.user.is_premium:
            return format_html(
                '<span style="color: #10b981; font-weight: bold;">Premium</span>'
            )
        return format_html(
            '<span style="color: #6b7280;">Free</span>'
        )
    is_premium_display.short_description = 'Plan'

    def storage_used_display(self, obj):
        """Display storage used in MB with progress bar for free users."""
        mb_used = obj.storage_used_mb
        if obj.user.is_premium:
            return f"{mb_used} MB (Unlimited)"

        from django.conf import settings
        limit = getattr(settings, 'FREE_TIER_MAX_STORAGE_MB', 100)
        percentage = min(100, (mb_used / limit) * 100)

        color = '#10b981' if percentage < 70 else '#f59e0b' if percentage < 90 else '#ef4444'
        return format_html(
            '<div style="width:100px; background:#e5e7eb; border-radius:4px;">'
            '<div style="width:{}%; background:{}; height:10px; border-radius:4px;"></div>'
            '</div>'
            '<small>{:.1f} / {} MB</small>',
            percentage, color, mb_used, limit
        )
    storage_used_display.short_description = 'Storage Used'

    def usage_summary_display(self, obj):
        """Display full usage summary."""
        summary = obj.get_usage_summary()
        lines = []
        for key, value in summary.items():
            lines.append(f"<strong>{key}:</strong> {value}")
        return format_html('<br>'.join(lines))
    usage_summary_display.short_description = 'Full Usage Summary'

    actions = ['reset_monthly_counters']

    @admin.action(description='Reset monthly counters for selected users')
    def reset_monthly_counters(self, request, queryset):
        """Admin action to manually reset monthly counters."""
        from datetime import date
        count = queryset.update(
            documents_uploaded_this_month=0,
            denial_decodes_this_month=0,
            ai_analyses_this_month=0,
            tokens_used_this_month=0,
            month_reset_date=date.today().replace(day=1)
        )
        self.message_user(request, f'Reset monthly counters for {count} users.')


# =============================================================================
# ORGANIZATION ADMIN (Path B)
# =============================================================================

class OrganizationMembershipInline(admin.TabularInline):
    """Inline for managing org members."""
    model = OrganizationMembership
    extra = 0
    fields = ['user', 'role', 'is_active', 'invited_by', 'accepted_at']
    readonly_fields = ['invited_by', 'accepted_at']
    raw_id_fields = ['user']


class OrganizationInvitationInline(admin.TabularInline):
    """Inline for pending invitations."""
    model = OrganizationInvitation
    extra = 0
    fields = ['email', 'role', 'invited_by', 'expires_at', 'is_pending_display']
    readonly_fields = ['invited_by', 'is_pending_display']

    def is_pending_display(self, obj):
        if obj.accepted_at:
            return format_html('<span style="color: #10b981;">Accepted</span>')
        if obj.is_expired:
            return format_html('<span style="color: #ef4444;">Expired</span>')
        return format_html('<span style="color: #f59e0b;">Pending</span>')
    is_pending_display.short_description = 'Status'


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Admin for Organizations (Path B)."""
    list_display = [
        'name',
        'org_type',
        'plan',
        'seats_display',
        'is_active',
        'created_at',
    ]
    list_filter = ['org_type', 'plan', 'is_active', 'created_at']
    search_fields = ['name', 'slug', 'contact_email']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['seats_used', 'created_at', 'updated_at', 'verified_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'org_type', 'description', 'is_active')
        }),
        ('Contact', {
            'fields': ('contact_email', 'contact_phone', 'website')
        }),
        ('Plan & Billing', {
            'fields': ('plan', 'seats', 'seats_used', 'stripe_customer_id', 'stripe_subscription_id')
        }),
        ('Settings', {
            'fields': ('settings',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'verified_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [OrganizationMembershipInline, OrganizationInvitationInline]

    def seats_display(self, obj):
        """Display seats used/total with color coding."""
        percentage = (obj.seats_used / obj.seats * 100) if obj.seats > 0 else 0
        color = '#10b981' if percentage < 80 else '#f59e0b' if percentage < 100 else '#ef4444'
        return format_html(
            '<span style="color: {};">{} / {}</span>',
            color, obj.seats_used, obj.seats
        )
    seats_display.short_description = 'Seats'


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    """Admin for Organization Memberships."""
    list_display = [
        'user',
        'organization',
        'role',
        'is_active',
        'accepted_at',
    ]
    list_filter = ['role', 'is_active', 'organization']
    search_fields = ['user__email', 'organization__name']
    raw_id_fields = ['user', 'organization', 'invited_by', 'deactivated_by']
    readonly_fields = ['invited_at', 'accepted_at', 'deactivated_at', 'created_at', 'updated_at']

    fieldsets = (
        ('Membership', {
            'fields': ('user', 'organization', 'role', 'is_active')
        }),
        ('Invitation', {
            'fields': ('invited_by', 'invited_at', 'accepted_at')
        }),
        ('Deactivation', {
            'fields': ('deactivated_at', 'deactivated_by'),
            'classes': ('collapse',)
        }),
    )

    actions = ['deactivate_memberships', 'reactivate_memberships']

    @admin.action(description='Deactivate selected memberships')
    def deactivate_memberships(self, request, queryset):
        for membership in queryset.filter(is_active=True):
            membership.deactivate(deactivated_by=request.user)
        self.message_user(request, f'Deactivated {queryset.count()} memberships.')

    @admin.action(description='Reactivate selected memberships')
    def reactivate_memberships(self, request, queryset):
        reactivated = 0
        for membership in queryset.filter(is_active=False):
            try:
                membership.reactivate()
                reactivated += 1
            except ValueError:
                pass
        self.message_user(request, f'Reactivated {reactivated} memberships.')


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(admin.ModelAdmin):
    """Admin for Organization Invitations."""
    list_display = [
        'email',
        'organization',
        'role',
        'status_display',
        'expires_at',
        'created_at',
    ]
    list_filter = ['role', 'organization', 'created_at']
    search_fields = ['email', 'organization__name']
    raw_id_fields = ['organization', 'invited_by', 'accepted_by']
    readonly_fields = ['token', 'accepted_at', 'accepted_by', 'created_at', 'updated_at']

    def status_display(self, obj):
        if obj.accepted_at:
            return format_html('<span style="color: #10b981;">Accepted</span>')
        if obj.is_expired:
            return format_html('<span style="color: #ef4444;">Expired</span>')
        return format_html('<span style="color: #f59e0b;">Pending</span>')
    status_display.short_description = 'Status'

    actions = ['resend_invitations']

    @admin.action(description='Resend selected invitations (extend expiry)')
    def resend_invitations(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(accepted_at__isnull=True).update(
            expires_at=timezone.now() + timezone.timedelta(days=7)
        )
        self.message_user(request, f'Extended expiry for {count} invitations.')
