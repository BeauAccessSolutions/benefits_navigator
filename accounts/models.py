"""
Accounts app models - User authentication, profiles, and subscriptions
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from datetime import date

from core.models import TimeStampedModel
from core.encryption import EncryptedCharField, EncryptedDateField


class UserManager(BaseUserManager):
    """Custom user manager for email-based authentication"""

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular user with email and password"""
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        extra_fields.setdefault("username", email)  # Set username to email as fallback
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a superuser with email and password"""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser
    Uses email as the primary identifier instead of username
    """
    email = models.EmailField('Email address', unique=True)
    phone_number = EncryptedCharField('Phone number', max_length=255, blank=True)
    is_verified = models.BooleanField('Email verified', default=False)
    stripe_customer_id = models.CharField('Stripe customer ID', max_length=255, blank=True)

    # Make username optional since we're using email
    username = models.CharField("Username", max_length=150, blank=True, null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # Remove email from required fields since it's USERNAME_FIELD

    # Use custom manager
    objects = UserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email

    @property
    def is_premium(self):
        """
        Check if user has premium access.

        Returns True if:
        - Pilot mode grants all users premium (PILOT_PREMIUM_ACCESS=True), OR
        - User's email/domain is in pilot premium list, OR
        - User has an active premium subscription, OR
        - User is a veteran linked to an active VSO organization
          (VSO org covers their access)
        """
        from django.conf import settings

        # Check pilot mode premium access first
        if getattr(settings, "PILOT_PREMIUM_ACCESS", False):
            return True

        # Check if user's email is in pilot premium list
        pilot_emails = getattr(settings, "PILOT_PREMIUM_EMAILS", [])
        if self.email and self.email.lower() in [e.lower() for e in pilot_emails]:
            return True

        # Check if user's email domain is in pilot premium domains
        pilot_domains = getattr(settings, "PILOT_PREMIUM_DOMAINS", [])
        if self.email and pilot_domains:
            email_domain = self.email.split("@")[-1].lower()
            if email_domain in [d.lower() for d in pilot_domains]:
                return True

        # Check personal subscription
        try:
            if self.subscription.is_active:
                return True
        except Subscription.DoesNotExist:
            pass

        # Check if veteran is linked to an active VSO organization
        # VSO-connected veterans get premium access (org covers them)
        return self.memberships.filter(
            role="veteran", is_active=True, organization__is_active=True
        ).exists()

    @property
    def is_pilot_user(self):
        """
        Check if user has premium access specifically through pilot program.
        Useful for displaying pilot-specific messaging.
        """
        from django.conf import settings

        if getattr(settings, "PILOT_PREMIUM_ACCESS", False):
            return True

        pilot_emails = getattr(settings, "PILOT_PREMIUM_EMAILS", [])
        if self.email and self.email.lower() in [e.lower() for e in pilot_emails]:
            return True

        pilot_domains = getattr(settings, "PILOT_PREMIUM_DOMAINS", [])
        if self.email and pilot_domains:
            email_domain = self.email.split("@")[-1].lower()
            if email_domain in [d.lower() for d in pilot_domains]:
                return True

        return False

    @property
    def full_name(self):
        """Return user's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.email


class UserProfile(TimeStampedModel):
    """
    Extended user profile information
    One-to-one relationship with User
    """

    BRANCH_CHOICES = [
        ("army", "Army"),
        ("navy", "Navy"),
        ("air_force", "Air Force"),
        ("marines", "Marines"),
        ("coast_guard", "Coast Guard"),
        ("space_force", "Space Force"),
        ("national_guard", "National Guard"),
        ("reserves", "Reserves"),
        ("other", "Other"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    branch_of_service = models.CharField(
        "Branch of service", max_length=20, choices=BRANCH_CHOICES, blank=True
    )
    date_of_birth = EncryptedDateField(
        "Date of birth", null=True, blank=True, help_text="Encrypted for privacy"
    )
    va_file_number = EncryptedCharField(
        "VA file number",
        max_length=255,  # Larger to accommodate encrypted data
        blank=True,
        help_text="Optional - Your VA claim number (encrypted)",
    )
    disability_rating = models.IntegerField(
        "Current disability rating (%)",
        null=True,
        blank=True,
        help_text="Your current combined VA disability rating",
    )
    bio = models.TextField(
        "Biography", blank=True, help_text="Optional personal information"
    )

    # Consent tracking
    ai_processing_consent = models.BooleanField(
        "AI processing consent",
        default=False,
        help_text="User has consented to AI/OCR processing of their documents",
    )
    ai_consent_date = models.DateTimeField(
        "AI consent date",
        null=True,
        blank=True,
        help_text="When the user provided AI processing consent",
    )

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"Profile for {self.user.email}"

    @property
    def age(self):
        """Calculate user's age"""
        if self.date_of_birth:
            today = date.today()
            return (
                today.year
                - self.date_of_birth.year
                - (
                    (today.month, today.day)
                    < (self.date_of_birth.month, self.date_of_birth.day)
                )
            )
        return None


class Subscription(TimeStampedModel):
    """
    User subscription management
    Tracks Stripe subscription information
    """

    PLAN_CHOICES = [
        ("free", "Free"),
        ("premium", "Premium"),
    ]

    STATUS_CHOICES = [
        ("active", "Active"),
        ("canceled", "Canceled"),
        ("past_due", "Past Due"),
        ("unpaid", "Unpaid"),
        ("incomplete", "Incomplete"),
        ("trialing", "Trialing"),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="subscription"
    )
    stripe_subscription_id = models.CharField(
        "Stripe subscription ID", max_length=255, blank=True
    )
    stripe_customer_id = models.CharField(
        "Stripe customer ID", max_length=255, blank=True
    )
    plan_type = models.CharField(
        "Plan type", max_length=20, choices=PLAN_CHOICES, default="free"
    )
    status = models.CharField(
        "Status", max_length=20, choices=STATUS_CHOICES, default="active"
    )
    current_period_end = models.DateTimeField(
        "Current period end",
        null=True,
        blank=True,
        help_text="When the current billing period ends",
    )
    cancel_at_period_end = models.BooleanField(
        "Cancel at period end",
        default=False,
        help_text="Whether subscription is set to cancel at end of current period",
    )
    trial_end = models.DateTimeField(
        "Trial end", null=True, blank=True, help_text="When free trial ends"
    )

    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"

    def __str__(self):
        return f"{self.user.email} - {self.plan_type} ({self.status})"

    @property
    def is_active(self):
        """Check if subscription is currently active"""
        return self.status in ["active", "trialing"]

    @property
    def is_trial(self):
        """Check if subscription is in trial period"""
        return (
            self.status == "trialing"
            and self.trial_end
            and self.trial_end > timezone.now()
        )

    @property
    def days_until_renewal(self):
        """Calculate days until subscription renews or expires"""
        if self.current_period_end:
            delta = self.current_period_end - timezone.now()
            return delta.days
        return None


class NotificationPreferences(TimeStampedModel):
    """
    User notification preferences for email reminders and alerts.
    """

    REMINDER_TIMING_CHOICES = [
        (30, "30 days before"),
        (14, "14 days before"),
        (7, "7 days before"),
        (3, "3 days before"),
        (1, "1 day before"),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="notification_preferences"
    )

    # Email notification toggles
    email_enabled = models.BooleanField(
        "Enable email notifications",
        default=True,
        help_text="Master switch for all email notifications",
    )
    deadline_reminders = models.BooleanField(
        "Deadline reminders",
        default=True,
        help_text="Receive reminders about upcoming deadlines",
    )
    exam_reminders = models.BooleanField(
        "C&P exam reminders",
        default=True,
        help_text="Receive reminders about upcoming C&P exams",
    )
    claim_updates = models.BooleanField(
        "Claim status updates",
        default=True,
        help_text="Receive updates about claim status changes",
    )
    document_analysis = models.BooleanField(
        "Document analysis complete",
        default=True,
        help_text="Receive notification when document analysis is finished",
    )
    weekly_summary = models.BooleanField(
        "Weekly summary",
        default=False,
        help_text="Receive a weekly summary of your claims journey",
    )

    # Timing preferences
    deadline_reminder_days = models.IntegerField(
        "Remind me before deadline",
        choices=REMINDER_TIMING_CHOICES,
        default=7,
        help_text="How many days before a deadline to send reminder",
    )
    exam_reminder_days = models.IntegerField(
        "Remind me before exam",
        choices=REMINDER_TIMING_CHOICES,
        default=7,
        help_text="How many days before a C&P exam to send reminder",
    )

    # Tracking
    last_email_sent = models.DateTimeField("Last email sent", null=True, blank=True)
    emails_sent_count = models.IntegerField("Total emails sent", default=0)

    class Meta:
        verbose_name = "Notification Preferences"
        verbose_name_plural = "Notification Preferences"

    def __str__(self):
        status = "enabled" if self.email_enabled else "disabled"
        return f"Notifications for {self.user.email} ({status})"

    def should_send_deadline_reminder(self, days_until_deadline: int) -> bool:
        """Check if a deadline reminder should be sent based on user preferences."""
        if not self.email_enabled or not self.deadline_reminders:
            return False
        return days_until_deadline <= self.deadline_reminder_days

    def should_send_exam_reminder(self, days_until_exam: int) -> bool:
        """Check if an exam reminder should be sent based on user preferences."""
        if not self.email_enabled or not self.exam_reminders:
            return False
        return days_until_exam <= self.exam_reminder_days

    def should_send_document_analysis_notification(self) -> bool:
        """Check if document analysis notification should be sent based on user preferences."""
        return self.email_enabled and self.document_analysis


# =============================================================================
# ORGANIZATION MODELS (Path B - VSO Platform)
# =============================================================================


class Organization(TimeStampedModel):
    """
    Organization for VSOs, law firms, and other groups that manage multiple veterans.

    Part of Path B (VSO Platform) - only active when 'organizations' feature flag is enabled.
    """

    ORG_TYPE_CHOICES = [
        ("vso", "Veteran Service Organization"),
        ("law_firm", "Law Firm"),
        ("nonprofit", "Nonprofit Organization"),
        ("government", "Government Agency"),
        ("other", "Other"),
    ]

    PLAN_CHOICES = [
        ("starter", "Starter"),
        ("pro", "Professional"),
        ("enterprise", "Enterprise"),
    ]

    # Basic info
    name = models.CharField("Organization name", max_length=200)
    slug = models.SlugField("URL slug", unique=True, max_length=100)
    org_type = models.CharField(
        "Organization type", max_length=20, choices=ORG_TYPE_CHOICES, default="vso"
    )
    description = models.TextField("Description", blank=True)

    # Contact
    contact_email = models.EmailField("Contact email", blank=True)
    contact_phone = models.CharField("Contact phone", max_length=20, blank=True)
    website = models.URLField("Website", blank=True)

    # Billing
    stripe_customer_id = models.CharField(
        "Stripe customer ID", max_length=255, blank=True
    )
    stripe_subscription_id = models.CharField(
        "Stripe subscription ID", max_length=255, blank=True
    )
    plan = models.CharField(
        "Plan", max_length=20, choices=PLAN_CHOICES, default="starter"
    )
    seats = models.IntegerField("Number of seats", default=5)
    seats_used = models.IntegerField("Seats used", default=0)

    # Privacy: least-privilege mode for caseworkers
    restrict_caseworker_visibility = models.BooleanField(
        'Restrict caseworker visibility',
        default=False,
        help_text=(
            'When enabled, caseworkers see only cases assigned to them '
            '(or unassigned); org admins see all cases.'
        ),
    )

    # Settings (JSON for flexibility)
    settings = models.JSONField(
        "Organization settings",
        default=dict,
        blank=True,
        help_text="Settings like require_mfa, allowed_domains, retention_days",
    )

    # Status
    is_active = models.BooleanField("Active", default=True)
    verified_at = models.DateTimeField("Verified at", null=True, blank=True)

    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def seats_remaining(self):
        """Number of available seats."""
        return max(0, self.seats - self.seats_used)

    @property
    def is_at_seat_limit(self):
        """Check if org has reached seat limit."""
        return self.seats_used >= self.seats

    def get_setting(self, key, default=None):
        """Get a setting value."""
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        """Set a setting value."""
        self.settings[key] = value
        self.save(update_fields=["settings", "updated_at"])

    @property
    def require_mfa(self):
        """Check if org requires MFA."""
        return self.get_setting("require_mfa", False)

    @property
    def retention_days(self):
        """Get data retention period in days."""
        return self.get_setting("retention_days", 365)

    @property
    def allowed_email_domains(self):
        """Get list of allowed email domains for invites."""
        return self.get_setting("allowed_domains", [])


class OrganizationMembership(TimeStampedModel):
    """
    Links users to organizations with roles.

    A user can belong to multiple organizations with different roles.
    """

    ROLE_CHOICES = [
        ("admin", "Administrator"),
        ("caseworker", "Caseworker"),
        ("veteran", "Veteran"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(
        "Role", max_length=20, choices=ROLE_CHOICES, default="veteran"
    )

    # Invitation tracking
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations_sent",
    )
    invited_at = models.DateTimeField("Invited at", auto_now_add=True)
    accepted_at = models.DateTimeField("Accepted at", null=True, blank=True)

    # Status
    is_active = models.BooleanField("Active", default=True)
    deactivated_at = models.DateTimeField("Deactivated at", null=True, blank=True)
    deactivated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deactivations_made",
    )

    class Meta:
        verbose_name = "Organization Membership"
        verbose_name_plural = "Organization Memberships"
        unique_together = ["user", "organization"]
        ordering = ["organization", "role", "user__email"]

    def __str__(self):
        return (
            f"{self.user.email} - {self.organization.name} ({self.get_role_display()})"
        )

    @property
    def is_admin(self):
        """Check if user is org admin."""
        return self.role == "admin"

    @property
    def is_caseworker(self):
        """Check if user is caseworker."""
        return self.role == "caseworker"

    @property
    def is_veteran(self):
        """Check if user is veteran member."""
        return self.role == "veteran"

    @property
    def can_manage_users(self):
        """Check if user can manage other users."""
        return self.role == "admin"

    @property
    def can_view_all_data(self):
        """Check if user can view all org data."""
        return self.role in ["admin", "caseworker"]

    def deactivate(self, deactivated_by=None):
        """Deactivate membership."""
        self.is_active = False
        self.deactivated_at = timezone.now()
        self.deactivated_by = deactivated_by
        self.save()

        # Update org seat count
        self.organization.seats_used = max(0, self.organization.seats_used - 1)
        self.organization.save(update_fields=["seats_used", "updated_at"])

    def reactivate(self):
        """Reactivate membership."""
        if self.organization.is_at_seat_limit:
            raise ValueError("Organization has reached seat limit")

        self.is_active = True
        self.deactivated_at = None
        self.deactivated_by = None
        self.save()

        # Update org seat count
        self.organization.seats_used += 1
        self.organization.save(update_fields=["seats_used", "updated_at"])


class OrganizationInvitation(TimeStampedModel):
    """
    Pending invitation to join an organization.

    Invitations expire after a configurable period.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invitations"
    )
    email = models.EmailField("Invitee email")
    role = models.CharField(
        "Role",
        max_length=20,
        choices=OrganizationMembership.ROLE_CHOICES,
        default="veteran",
    )
    invited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="org_invitations_sent"
    )

    # Token for accepting invitation
    token = models.CharField("Invitation token", max_length=64, unique=True)
    expires_at = models.DateTimeField("Expires at")

    # Status
    accepted_at = models.DateTimeField("Accepted at", null=True, blank=True)
    accepted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_invitations",
    )

    class Meta:
        verbose_name = "Organization Invitation"
        verbose_name_plural = "Organization Invitations"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite {self.email} to {self.organization.name}"

    def save(self, *args, **kwargs):
        if not self.token:
            import secrets

            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        """Check if invitation has expired."""
        return timezone.now() > self.expires_at

    @property
    def is_pending(self):
        """Check if invitation is still pending."""
        return not self.accepted_at and not self.is_expired

    def accept(self, user):
        """Accept the invitation and create membership."""
        if self.is_expired:
            raise ValueError("Invitation has expired")
        if self.accepted_at:
            raise ValueError("Invitation already accepted")
        if self.organization.is_at_seat_limit:
            raise ValueError("Organization has reached seat limit")

        # Create membership
        membership, created = OrganizationMembership.objects.get_or_create(
            user=user,
            organization=self.organization,
            defaults={
                "role": self.role,
                "invited_by": self.invited_by,
                "accepted_at": timezone.now(),
            },
        )

        if not created:
            # User already a member, update role if different
            membership.role = self.role
            membership.accepted_at = timezone.now()
            membership.save()

        # Mark invitation as accepted
        self.accepted_at = timezone.now()
        self.accepted_by = user
        self.save()

        # Update seat count
        if created:
            self.organization.seats_used += 1
            self.organization.save(update_fields=["seats_used", "updated_at"])

        return membership


# =============================================================================
# USAGE TRACKING
# =============================================================================


class UsageTracking(TimeStampedModel):
    """
    Track user's usage of premium features for freemium enforcement.

    Tracks:
    - Document uploads (count and storage)
    - AI analysis tasks
    - Denial decoder uses
    - Token consumption

    Resets monthly for document count limits.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="usage")

    # Monthly document tracking (resets each month)
    documents_uploaded_this_month = models.IntegerField(
        "Documents uploaded this month", default=0
    )
    month_reset_date = models.DateField(
        "Month reset date",
        auto_now_add=True,
        help_text="First day of the current tracking month",
    )

    # Storage tracking (cumulative, not reset)
    total_storage_bytes = models.BigIntegerField(
        "Total storage used (bytes)", default=0
    )

    # AI/Feature usage tracking (monthly)
    denial_decodes_this_month = models.IntegerField(
        "Denial decodes this month", default=0
    )
    ai_analyses_this_month = models.IntegerField("AI analyses this month", default=0)
    tokens_used_this_month = models.IntegerField("AI tokens used this month", default=0)

    # Lifetime stats
    total_documents_uploaded = models.IntegerField(
        "Total documents uploaded (lifetime)", default=0
    )
    total_denial_decodes = models.IntegerField(
        "Total denial decodes (lifetime)", default=0
    )
    total_ai_analyses = models.IntegerField("Total AI analyses (lifetime)", default=0)
    total_tokens_used = models.IntegerField(
        "Total AI tokens used (lifetime)", default=0
    )

    class Meta:
        verbose_name = "Usage Tracking"
        verbose_name_plural = "Usage Tracking"

    def __str__(self):
        return f"Usage for {self.user.email}"

    @property
    def storage_used_mb(self):
        """Return storage used in megabytes."""
        return round(self.total_storage_bytes / (1024 * 1024), 2)

    def check_and_reset_monthly(self):
        """
        Check if we need to reset monthly counters.
        Called before any usage check.
        """
        from datetime import date

        today = date.today()
        first_of_month = today.replace(day=1)

        if self.month_reset_date < first_of_month:
            self.documents_uploaded_this_month = 0
            self.denial_decodes_this_month = 0
            self.ai_analyses_this_month = 0
            self.tokens_used_this_month = 0
            self.month_reset_date = first_of_month
            self.save()

    def can_upload_document(self, file_size_bytes: int = 0) -> tuple[bool, str]:
        """
        Check if user can upload a document.

        Args:
            file_size_bytes: Size of the file to be uploaded

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        from django.conf import settings

        self.check_and_reset_monthly()

        # Premium users have no limits
        if self.user.is_premium:
            return True, ""

        # Check monthly document limit
        limit = getattr(settings, "FREE_TIER_DOCUMENTS_PER_MONTH", 3)
        if self.documents_uploaded_this_month >= limit:
            return (
                False,
                f"You have reached your free tier limit of {limit} documents per month.",
            )

        # Check storage limit
        storage_limit_mb = getattr(settings, "FREE_TIER_MAX_STORAGE_MB", 100)
        storage_limit_bytes = storage_limit_mb * 1024 * 1024
        if self.total_storage_bytes + file_size_bytes > storage_limit_bytes:
            return (
                False,
                f"You have reached your free tier storage limit of {storage_limit_mb} MB.",
            )

        return True, ""

    def can_use_denial_decoder(self) -> tuple[bool, str]:
        """Check if user can use the denial decoder."""
        from django.conf import settings

        self.check_and_reset_monthly()

        if self.user.is_premium:
            return True, ""

        limit = getattr(settings, "FREE_TIER_DENIAL_DECODES_PER_MONTH", 2)
        if self.denial_decodes_this_month >= limit:
            return (
                False,
                f"You have reached your free tier limit of {limit} denial decodes per month.",
            )

        return True, ""

    def can_use_ai_analysis(self) -> tuple[bool, str]:
        """Check if user can run AI analysis."""
        from django.conf import settings

        self.check_and_reset_monthly()

        if self.user.is_premium:
            return True, ""

        limit = getattr(settings, "FREE_TIER_AI_ANALYSES_PER_MONTH", 5)
        if self.ai_analyses_this_month >= limit:
            return (
                False,
                f"You have reached your free tier limit of {limit} AI analyses per month.",
            )

        return True, ""

    def record_document_upload(self, file_size_bytes: int):
        """Record a document upload."""
        self.check_and_reset_monthly()
        self.documents_uploaded_this_month += 1
        self.total_documents_uploaded += 1
        self.total_storage_bytes += file_size_bytes
        self.save()

    def record_denial_decode(self):
        """Record a denial decode usage."""
        self.check_and_reset_monthly()
        self.denial_decodes_this_month += 1
        self.total_denial_decodes += 1
        self.save()

    def record_ai_analysis(self, tokens_used: int = 0):
        """Record an AI analysis usage."""
        self.check_and_reset_monthly()
        self.ai_analyses_this_month += 1
        self.total_ai_analyses += 1
        self.tokens_used_this_month += tokens_used
        self.total_tokens_used += tokens_used
        self.save()

    def record_storage_freed(self, file_size_bytes: int):
        """Record storage freed when a document is deleted."""
        self.total_storage_bytes = max(0, self.total_storage_bytes - file_size_bytes)
        self.save()

    def get_usage_summary(self) -> dict:
        """Get a summary of current usage for display."""
        from django.conf import settings

        self.check_and_reset_monthly()
        is_premium = self.user.is_premium

        return {
            "is_premium": is_premium,
            # Document limits
            "documents_used": self.documents_uploaded_this_month,
            "documents_limit": (
                None
                if is_premium
                else getattr(settings, "FREE_TIER_DOCUMENTS_PER_MONTH", 3)
            ),
            "documents_remaining": (
                None
                if is_premium
                else max(
                    0,
                    getattr(settings, "FREE_TIER_DOCUMENTS_PER_MONTH", 3)
                    - self.documents_uploaded_this_month,
                )
            ),
            # Storage limits
            "storage_used_mb": self.storage_used_mb,
            "storage_limit_mb": (
                None
                if is_premium
                else getattr(settings, "FREE_TIER_MAX_STORAGE_MB", 100)
            ),
            "storage_percentage": (
                None
                if is_premium
                else min(
                    100,
                    round(
                        self.storage_used_mb
                        / getattr(settings, "FREE_TIER_MAX_STORAGE_MB", 100)
                        * 100,
                        1,
                    ),
                )
            ),
            # Denial decoder limits
            "denial_decodes_used": self.denial_decodes_this_month,
            "denial_decodes_limit": (
                None
                if is_premium
                else getattr(settings, "FREE_TIER_DENIAL_DECODES_PER_MONTH", 2)
            ),
            "denial_decodes_remaining": (
                None
                if is_premium
                else max(
                    0,
                    getattr(settings, "FREE_TIER_DENIAL_DECODES_PER_MONTH", 2)
                    - self.denial_decodes_this_month,
                )
            ),
            # AI analysis limits
            "ai_analyses_used": self.ai_analyses_this_month,
            "ai_analyses_limit": (
                None
                if is_premium
                else getattr(settings, "FREE_TIER_AI_ANALYSES_PER_MONTH", 5)
            ),
            "ai_analyses_remaining": (
                None
                if is_premium
                else max(
                    0,
                    getattr(settings, "FREE_TIER_AI_ANALYSES_PER_MONTH", 5)
                    - self.ai_analyses_this_month,
                )
            ),
            # Lifetime stats
            "total_documents": self.total_documents_uploaded,
            "total_denial_decodes": self.total_denial_decodes,
            "total_ai_analyses": self.total_ai_analyses,
        }


# =============================================================================
# SIGNALS
# =============================================================================

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile, NotificationPreferences, and UsageTracking when a new User is created"""
    if created:
        UserProfile.objects.create(user=instance)
        NotificationPreferences.objects.create(user=instance)
        UsageTracking.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save the UserProfile whenever the User is saved"""
    if hasattr(instance, "profile"):
        instance.profile.save()
