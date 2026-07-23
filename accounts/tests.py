"""
Tests for the accounts app - User authentication, profiles, and subscriptions.

Covers:
- User model and custom manager
- UserProfile model and signals
- Subscription model and properties
- Rate-limited authentication views
- Data export (GDPR)
- Account deletion
- Privacy settings
"""

import json
import pytest
from datetime import date, timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import UserProfile, Subscription

User = get_user_model()


# =============================================================================
# USER MODEL TESTS
# =============================================================================


class TestUserModel(TestCase):
    """Tests for the custom User model."""

    def test_create_user_with_email(self):
        """User can be created with email as the primary identifier."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.assertEqual(user.email, "test@example.com")
        self.assertTrue(user.check_password("TestPass123!"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_user_email_normalized(self):
        """Email is normalized when creating user."""
        user = User.objects.create_user(
            email="Test@EXAMPLE.com", password="TestPass123!"
        )
        self.assertEqual(user.email, "Test@example.com")

    def test_create_user_without_email_raises_error(self):
        """Creating user without email raises ValueError."""
        with self.assertRaises(ValueError) as context:
            User.objects.create_user(email="", password="TestPass123!")
        self.assertIn("Email field must be set", str(context.exception))

    def test_create_superuser(self):
        """Superuser is created with correct permissions."""
        admin = User.objects.create_superuser(
            email="admin@example.com", password="AdminPass123!"
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_verified)

    def test_create_superuser_must_have_is_staff(self):
        """Superuser must have is_staff=True."""
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="admin@example.com", password="AdminPass123!", is_staff=False
            )

    def test_create_superuser_must_have_is_superuser(self):
        """Superuser must have is_superuser=True."""
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="admin@example.com", password="AdminPass123!", is_superuser=False
            )

    def test_user_str_returns_email(self):
        """User string representation is the email."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.assertEqual(str(user), "test@example.com")

    def test_user_full_name_with_names(self):
        """Full name returns first and last name when set."""
        user = User.objects.create_user(
            email="test@example.com",
            password="TestPass123!",
            first_name="John",
            last_name="Doe",
        )
        self.assertEqual(user.full_name, "John Doe")

    def test_user_full_name_without_names(self):
        """Full name returns email when names not set."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.assertEqual(user.full_name, "test@example.com")

    def test_user_is_premium_without_subscription(self):
        """is_premium returns False when no subscription exists."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.assertFalse(user.is_premium)

    def test_user_is_premium_with_active_subscription(self):
        """is_premium returns True with active premium subscription."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        Subscription.objects.create(user=user, plan_type="premium", status="active")
        self.assertTrue(user.is_premium)

    def test_user_is_premium_with_canceled_subscription(self):
        """is_premium returns False with canceled subscription."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        Subscription.objects.create(user=user, plan_type="premium", status="canceled")
        self.assertFalse(user.is_premium)


# =============================================================================
# PILOT MODE TESTS
# =============================================================================


class TestPilotModePremiumAccess(TestCase):
    """Tests for pilot mode premium access functionality."""

    def test_pilot_premium_access_grants_premium_to_all_users(self):
        """When PILOT_PREMIUM_ACCESS is True, all users get premium."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        # Without pilot mode, user is not premium
        self.assertFalse(user.is_premium)

        # Enable pilot premium access
        with self.settings(PILOT_PREMIUM_ACCESS=True):
            self.assertTrue(user.is_premium)
            self.assertTrue(user.is_pilot_user)

    def test_pilot_premium_emails_grants_premium_to_specific_users(self):
        """Users in PILOT_PREMIUM_EMAILS get premium access."""
        user = User.objects.create_user(
            email="pilot@tester.com", password="TestPass123!"
        )
        other_user = User.objects.create_user(
            email="other@example.com", password="TestPass123!"
        )

        with self.settings(PILOT_PREMIUM_EMAILS=["pilot@tester.com"]):
            self.assertTrue(user.is_premium)
            self.assertTrue(user.is_pilot_user)
            self.assertFalse(other_user.is_premium)
            self.assertFalse(other_user.is_pilot_user)

    def test_pilot_premium_emails_case_insensitive(self):
        """PILOT_PREMIUM_EMAILS comparison is case insensitive."""
        user = User.objects.create_user(
            email="Pilot@Tester.COM", password="TestPass123!"
        )

        with self.settings(PILOT_PREMIUM_EMAILS=["pilot@tester.com"]):
            self.assertTrue(user.is_premium)

    def test_pilot_premium_domains_grants_premium_to_domain_users(self):
        """Users with email in PILOT_PREMIUM_DOMAINS get premium."""
        user1 = User.objects.create_user(
            email="user1@pilotcompany.com", password="TestPass123!"
        )
        user2 = User.objects.create_user(
            email="user2@pilotcompany.com", password="TestPass123!"
        )
        other_user = User.objects.create_user(
            email="other@example.com", password="TestPass123!"
        )

        with self.settings(PILOT_PREMIUM_DOMAINS=["pilotcompany.com"]):
            self.assertTrue(user1.is_premium)
            self.assertTrue(user1.is_pilot_user)
            self.assertTrue(user2.is_premium)
            self.assertFalse(other_user.is_premium)

    def test_pilot_premium_domains_case_insensitive(self):
        """PILOT_PREMIUM_DOMAINS comparison is case insensitive."""
        user = User.objects.create_user(
            email="user@PilotCompany.COM", password="TestPass123!"
        )

        with self.settings(PILOT_PREMIUM_DOMAINS=["pilotcompany.com"]):
            self.assertTrue(user.is_premium)

    def test_is_pilot_user_false_without_pilot_settings(self):
        """is_pilot_user is False when no pilot settings are enabled."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.assertFalse(user.is_pilot_user)

    def test_is_pilot_user_false_for_regular_premium(self):
        """is_pilot_user is False for users with regular premium subscription."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        Subscription.objects.create(user=user, plan_type="premium", status="active")
        # User is premium via subscription, not pilot
        self.assertTrue(user.is_premium)
        self.assertFalse(user.is_pilot_user)

    def test_pilot_mode_priority_over_subscription_check(self):
        """Pilot mode grants premium even without checking subscription."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        # No subscription exists

        with self.settings(PILOT_PREMIUM_ACCESS=True):
            # Should be premium via pilot, not subscription
            self.assertTrue(user.is_premium)


# =============================================================================
# USER PROFILE TESTS
# =============================================================================


class TestUserProfileModel(TestCase):
    """Tests for the UserProfile model and signals."""

    def test_profile_created_on_user_creation(self):
        """UserProfile is automatically created when User is created."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.assertTrue(hasattr(user, "profile"))
        self.assertIsInstance(user.profile, UserProfile)

    def test_profile_str_representation(self):
        """Profile string representation includes user email."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.assertEqual(str(user.profile), "Profile for test@example.com")

    def test_profile_branch_choices(self):
        """Profile branch_of_service accepts valid choices."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        user.profile.branch_of_service = "army"
        user.profile.save()
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.branch_of_service, "army")

    def test_profile_age_calculation(self):
        """Profile age property calculates correct age."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        # Set DOB to exactly 30 years ago (use year subtraction for accuracy)
        today = date.today()
        # Handle Feb 29 edge case - use Mar 1 if today is Feb 29 and target year isn't leap
        try:
            dob = today.replace(year=today.year - 30)
        except ValueError:
            # Feb 29 in non-leap year - use Mar 1
            dob = today.replace(year=today.year - 30, month=3, day=1)
        user.profile.date_of_birth = dob
        user.profile.save()
        self.assertEqual(user.profile.age, 30)

    def test_profile_age_none_without_dob(self):
        """Profile age returns None when DOB not set."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.assertIsNone(user.profile.age)

    def test_profile_disability_rating(self):
        """Profile can store disability rating."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        user.profile.disability_rating = 70
        user.profile.save()
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.disability_rating, 70)

    def test_profile_va_file_number(self):
        """Profile can store VA file number."""
        user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        user.profile.va_file_number = "123456789"
        user.profile.save()
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.va_file_number, "123456789")


# =============================================================================
# SUBSCRIPTION MODEL TESTS
# =============================================================================


class TestSubscriptionModel(TestCase):
    """Tests for the Subscription model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )

    def test_subscription_str_representation(self):
        """Subscription string includes user, plan, and status."""
        sub = Subscription.objects.create(
            user=self.user, plan_type="premium", status="active"
        )
        self.assertIn("test@example.com", str(sub))
        self.assertIn("premium", str(sub))
        self.assertIn("active", str(sub))

    def test_subscription_is_active_with_active_status(self):
        """is_active returns True for active status."""
        sub = Subscription.objects.create(
            user=self.user, plan_type="premium", status="active"
        )
        self.assertTrue(sub.is_active)

    def test_subscription_is_active_with_trialing_status(self):
        """is_active returns True for trialing status."""
        sub = Subscription.objects.create(
            user=self.user, plan_type="premium", status="trialing"
        )
        self.assertTrue(sub.is_active)

    def test_subscription_is_not_active_when_canceled(self):
        """is_active returns False for canceled status."""
        sub = Subscription.objects.create(
            user=self.user, plan_type="premium", status="canceled"
        )
        self.assertFalse(sub.is_active)

    def test_subscription_is_not_active_when_past_due(self):
        """is_active returns False for past_due status."""
        sub = Subscription.objects.create(
            user=self.user, plan_type="premium", status="past_due"
        )
        self.assertFalse(sub.is_active)

    def test_subscription_is_trial(self):
        """is_trial returns True for trialing with future end date."""
        sub = Subscription.objects.create(
            user=self.user,
            plan_type="premium",
            status="trialing",
            trial_end=timezone.now() + timedelta(days=7),
        )
        self.assertTrue(sub.is_trial)

    def test_subscription_is_not_trial_when_expired(self):
        """is_trial returns False when trial end date has passed."""
        sub = Subscription.objects.create(
            user=self.user,
            plan_type="premium",
            status="trialing",
            trial_end=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(sub.is_trial)

    def test_subscription_days_until_renewal(self):
        """days_until_renewal calculates correctly."""
        # Add 15 days and a few hours to ensure we get 15 full days
        future_date = timezone.now() + timedelta(days=15, hours=1)
        sub = Subscription.objects.create(
            user=self.user,
            plan_type="premium",
            status="active",
            current_period_end=future_date,
        )
        self.assertEqual(sub.days_until_renewal, 15)

    def test_subscription_days_until_renewal_none_without_date(self):
        """days_until_renewal returns None without period end date."""
        sub = Subscription.objects.create(
            user=self.user, plan_type="premium", status="active"
        )
        self.assertIsNone(sub.days_until_renewal)


# =============================================================================
# AUTHENTICATION VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestAuthenticationViews:
    """Tests for rate-limited authentication views."""

    def test_login_page_loads(self, client):
        """Login page loads successfully."""
        response = client.get(reverse("account_login"))
        assert response.status_code == 200

    def test_signup_page_loads(self, client):
        """Signup page loads successfully."""
        response = client.get(reverse("account_signup"))
        assert response.status_code == 200

    def test_login_with_valid_credentials(self, client, user, user_password):
        """User can log in with valid credentials."""
        response = client.post(
            reverse("account_login"),
            {
                "login": user.email,
                "password": user_password,
            },
        )
        # Should redirect to dashboard on success
        assert response.status_code in [302, 200]

    def test_login_with_invalid_credentials(self, client, user):
        """Login fails with invalid credentials."""
        response = client.post(
            reverse("account_login"),
            {
                "login": user.email,
                "password": "WrongPassword123!",
            },
        )
        # Should not redirect (stays on login page with errors)
        assert response.status_code == 200

    def test_signup_creates_user(self, client, db):
        """Signup creates a new user."""
        response = client.post(
            reverse("account_signup"),
            {
                "email": "newuser@example.com",
                "password1": "NewPassword123!",
                "password2": "NewPassword123!",
            },
        )
        assert User.objects.filter(email="newuser@example.com").exists()


@pytest.mark.django_db
class TestStyledAllauthTemplates:
    """
    Every allauth account page must render the project's own styled template —
    not allauth's unstyled bundled default, which renders as raw, borderless
    inputs on mobile (the "signup/signin look merged" report). Each test mirrors
    test_signup_uses_custom_styled_template: GET the page and assert the custom
    template under templates/account/ is the one that rendered, so a regression
    back to the unstyled default fails the suite.
    """

    def _templates(self, response):
        return {t.name for t in response.templates if t.name}

    def test_password_reset_uses_custom_styled_template(self, client):
        response = client.get(reverse("account_reset_password"))
        assert response.status_code == 200
        assert "account/password_reset.html" in self._templates(response)
        html = response.content.decode()
        assert 'class="space-y-6"' in html
        assert 'name="email"' in html
        assert "px-4 py-3 border" in html

    def test_password_reset_done_uses_custom_styled_template(self, client):
        response = client.get(reverse("account_reset_password_done"))
        assert response.status_code == 200
        assert "account/password_reset_done.html" in self._templates(response)

    def test_password_reset_from_key_uses_custom_styled_template(self, client):
        # A bogus key drives the token_fail branch; allauth stashes the key in
        # session and redirects once, so follow the redirect to the rendered page.
        url = reverse(
            "account_reset_password_from_key",
            kwargs={"uidb36": "abc", "key": "invalid-key"},
        )
        response = client.get(url, follow=True)
        assert response.status_code == 200
        assert "account/password_reset_from_key.html" in self._templates(response)

    def test_password_reset_from_key_done_uses_custom_styled_template(self, client):
        response = client.get(reverse("account_reset_password_from_key_done"))
        assert response.status_code == 200
        assert "account/password_reset_from_key_done.html" in self._templates(response)

    def test_verification_sent_uses_custom_styled_template(self, client):
        response = client.get(reverse("account_email_verification_sent"))
        assert response.status_code == 200
        assert "account/verification_sent.html" in self._templates(response)

    def test_email_confirm_uses_custom_styled_template(self, client):
        # An invalid key renders the "expired or invalid" branch of the page.
        response = client.get(
            reverse("account_confirm_email", kwargs={"key": "invalid-key"})
        )
        assert response.status_code == 200
        assert "account/email_confirm.html" in self._templates(response)

    def test_manage_email_uses_custom_styled_template(self, authenticated_client):
        response = authenticated_client.get(reverse("account_email"))
        assert response.status_code == 200
        assert "account/email.html" in self._templates(response)
        html = response.content.decode()
        assert 'name="email"' in html
        assert "px-4 py-3 border" in html

    def test_password_change_uses_custom_styled_template(self, authenticated_client):
        response = authenticated_client.get(reverse("account_change_password"))
        assert response.status_code == 200
        assert "account/password_change.html" in self._templates(response)
        html = response.content.decode()
        assert 'class="space-y-6"' in html
        assert 'name="oldpassword"' in html
        assert 'name="password1"' in html
        assert 'name="password2"' in html
        assert "px-4 py-3 border" in html

    def test_logout_uses_custom_styled_template(self, authenticated_client):
        response = authenticated_client.get(reverse("account_logout"))
        assert response.status_code == 200
        assert "account/logout.html" in self._templates(response)


# =============================================================================
# DATA EXPORT VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestDataExportView:
    """Tests for GDPR data export functionality."""

    def test_data_export_requires_login(self, client):
        """Data export page requires authentication."""
        response = client.get(reverse("accounts:data_export"))
        assert response.status_code == 302
        assert "login" in response.url.lower()

    def test_data_export_page_loads(self, authenticated_client):
        """Data export page loads for authenticated user."""
        response = authenticated_client.get(reverse("accounts:data_export"))
        assert response.status_code == 200

    def test_data_export_generates_json(self, authenticated_client, user):
        """POST generates JSON export file."""
        response = authenticated_client.post(reverse("accounts:data_export"))
        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        assert "attachment" in response["Content-Disposition"]

        # Verify JSON is valid and contains user data
        data = json.loads(response.content)
        assert "user" in data
        assert data["user"]["email"] == user.email

    def test_data_export_includes_profile(self, authenticated_client, user):
        """Export includes user profile data."""
        user.profile.branch_of_service = "army"
        user.profile.disability_rating = 50
        user.profile.save()

        response = authenticated_client.post(reverse("accounts:data_export"))
        data = json.loads(response.content)

        assert "profile" in data
        assert data["profile"]["branch_of_service"] == "army"
        assert data["profile"]["disability_rating"] == 50

    def test_export_succeeds_with_claims_and_appeals(
        self, authenticated_client, user, claim, appeal
    ):
        """
        Regression: the export previously read nonexistent Claim/Appeal fields
        (condition, filed_date, appeal_lane) and 500'd for any user who had a
        claim or appeal. It must succeed and carry the real model fields.
        """
        response = authenticated_client.post(reverse("accounts:data_export"))
        assert response.status_code == 200

        data = json.loads(response.content)

        assert data["claims"][0]["title"] == claim.title
        assert data["claims"][0]["claim_type"] == claim.claim_type
        assert "submission_date" in data["claims"][0]

        assert data["appeals"][0]["conditions_appealed"] == appeal.conditions_appealed
        assert data["appeals"][0]["appeal_type"] == appeal.appeal_type

        # The nonexistent fields from the old buggy code must not reappear.
        assert "condition" not in data["claims"][0]
        assert "appeal_lane" not in data["appeals"][0]


# =============================================================================
# ACCOUNT DELETION VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestAccountDeletionView:
    """Tests for account deletion functionality."""

    def test_account_deletion_requires_login(self, client):
        """Account deletion page requires authentication."""
        response = client.get(reverse("accounts:account_deletion"))
        assert response.status_code == 302

    def test_account_deletion_page_loads(self, authenticated_client):
        """Account deletion page loads for authenticated user."""
        response = authenticated_client.get(reverse("accounts:account_deletion"))
        assert response.status_code == 200

    def test_account_deletion_requires_confirmation(self, authenticated_client):
        """Deletion requires typing DELETE to confirm."""
        response = authenticated_client.post(
            reverse("accounts:account_deletion"), {"confirm": "wrong"}
        )
        # Should stay on page with error
        assert response.status_code == 200

    def test_account_deletion_with_confirmation_schedules(
        self, authenticated_client, user
    ):
        """Confirming sets deletion_requested_at and schedules the purge."""
        response = authenticated_client.post(
            reverse("accounts:account_deletion"), {"confirm": "DELETE"}
        )
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.deletion_requested_at is not None

    def test_scheduling_keeps_account_active_for_cancellation(
        self, authenticated_client, user
    ):
        """
        The account must stay usable during the grace period — the whole point
        of 'cancel by logging in'. A scheduled user is still active.
        """
        authenticated_client.post(
            reverse("accounts:account_deletion"), {"confirm": "DELETE"}
        )
        user.refresh_from_db()
        assert user.is_active is True

    def test_wrong_confirmation_does_not_schedule(self, authenticated_client, user):
        """A wrong confirmation string must not set the deletion field."""
        authenticated_client.post(
            reverse("accounts:account_deletion"), {"confirm": "nope"}
        )
        user.refresh_from_db()
        assert user.deletion_requested_at is None

    def test_confirmation_is_idempotent(self, authenticated_client, user):
        """A second confirm must not reset the grace-period clock."""
        url = reverse("accounts:account_deletion")
        authenticated_client.post(url, {"confirm": "DELETE"})
        user.refresh_from_db()
        first = user.deletion_requested_at
        authenticated_client.post(url, {"confirm": "DELETE"})
        user.refresh_from_db()
        assert user.deletion_requested_at == first

    def test_cancel_clears_scheduled_deletion(self, authenticated_client, user):
        """The cancel intent clears deletion_requested_at."""
        url = reverse("accounts:account_deletion")
        authenticated_client.post(url, {"confirm": "DELETE"})
        user.refresh_from_db()
        assert user.deletion_requested_at is not None

        authenticated_client.post(url, {"intent": "cancel"})
        user.refresh_from_db()
        assert user.deletion_requested_at is None

    def test_scheduled_deletion_date_property(self, user):
        """scheduled_deletion_date is grace-days after the request, else None."""
        assert user.scheduled_deletion_date is None
        now = timezone.now()
        user.deletion_requested_at = now
        assert user.scheduled_deletion_date == now + timedelta(
            days=user.DELETION_GRACE_DAYS
        )


# =============================================================================
# ACCOUNT DELETION PURGE (Celery task) TESTS
# =============================================================================


@pytest.mark.django_db
class TestAccountDeletionPurge:
    """Tests for the account-purge task that runs after the grace period."""

    def test_purge_deletes_user_and_owned_data(self, user, document):
        """Purging a user removes the User row and cascades their data."""
        from core.tasks import purge_user_account
        from claims.models import Document

        user_id = user.id
        purge_user_account(user)

        assert not User.objects.filter(id=user_id).exists()
        assert not Document.all_objects.filter(user_id=user_id).exists()

    def test_purge_preserves_audit_record(self, user):
        """
        The purge must leave an audit trail: an account_delete_purge entry with
        the email preserved and the user FK nulled (erasure evidence).
        """
        from core.tasks import purge_user_account
        from core.models import AuditLog

        email = user.email
        purge_user_account(user)

        entry = AuditLog.objects.filter(
            action="account_delete_purge", user_email=email
        ).first()
        assert entry is not None
        assert entry.user is None

    def test_purge_deletes_file_from_storage(self, document_with_file):
        """DB cascade doesn't touch storage — the purge must delete the file."""
        from core.tasks import purge_user_account

        doc = document_with_file
        storage, name = doc.file.storage, doc.file.name
        assert storage.exists(name)

        purge_user_account(doc.user)
        assert not storage.exists(name)

    def test_scheduled_task_only_purges_past_grace(self, db, user_password):
        """Only accounts past the 30-day grace window are purged."""
        from core.tasks import process_scheduled_account_deletions

        past = User.objects.create_user(
            email="past@example.com", password=user_password
        )
        past.deletion_requested_at = timezone.now() - timedelta(days=31)
        past.save(update_fields=["deletion_requested_at"])

        within = User.objects.create_user(
            email="within@example.com", password=user_password
        )
        within.deletion_requested_at = timezone.now() - timedelta(days=5)
        within.save(update_fields=["deletion_requested_at"])

        not_scheduled = User.objects.create_user(
            email="keep@example.com", password=user_password
        )

        result = process_scheduled_account_deletions()

        assert not User.objects.filter(id=past.id).exists()
        assert User.objects.filter(id=within.id).exists()
        assert User.objects.filter(id=not_scheduled.id).exists()
        assert result["purged"] == 1

    def test_deleting_veteran_cascades_vso_case(self, db, user_password):
        """
        Deleting a veteran removes their VSO case and its notes/shared data —
        deletion stays complete, no VSO copies of the veteran's data survive.
        """
        from core.tasks import purge_user_account
        from accounts.models import Organization
        from vso.models import VeteranCase

        veteran = User.objects.create_user(
            email="vet@example.com", password=user_password
        )
        org = Organization.objects.create(name="Test VSO", slug="test-vso")
        case = VeteranCase.objects.create(
            organization=org, veteran=veteran, title="Test case"
        )
        case_id = case.id

        purge_user_account(veteran)
        assert not VeteranCase.objects.filter(id=case_id).exists()


# =============================================================================
# PRIVACY SETTINGS VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestPrivacySettingsView:
    """Tests for privacy settings page."""

    def test_privacy_settings_requires_login(self, client):
        """Privacy settings requires authentication."""
        response = client.get(reverse("accounts:privacy_settings"))
        assert response.status_code == 302

    def test_privacy_settings_page_loads(self, authenticated_client):
        """Privacy settings page loads for authenticated user."""
        response = authenticated_client.get(reverse("accounts:privacy_settings"))
        assert response.status_code == 200

    def test_privacy_settings_shows_counts(
        self, authenticated_client, document, claim, appeal
    ):
        """Privacy settings shows correct data counts."""
        response = authenticated_client.get(reverse("accounts:privacy_settings"))
        assert response.status_code == 200
        # Context should contain counts
        assert "document_count" in response.context
        assert "claim_count" in response.context
        assert "appeal_count" in response.context


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestUserWorkflow(TestCase):
    """Integration tests for complete user workflows."""

    def test_complete_user_signup_workflow(self):
        """Test complete signup to profile setup workflow."""
        client = Client()

        # 1. Sign up
        response = client.post(
            reverse("account_signup"),
            {
                "email": "workflow@example.com",
                "password1": "WorkflowPass123!",
                "password2": "WorkflowPass123!",
            },
        )

        # User should be created
        user = User.objects.get(email="workflow@example.com")
        self.assertIsNotNone(user)

        # Profile should exist
        self.assertTrue(hasattr(user, "profile"))

        # 2. User can log in
        login_success = client.login(
            email="workflow@example.com", password="WorkflowPass123!"
        )
        self.assertTrue(login_success)

    def test_user_with_all_related_data(self):
        """Test user with complete related data."""
        from claims.models import Claim
        from appeals.models import Appeal

        # Create user
        user = User.objects.create_user(
            email="complete@example.com", password="CompletePass123!"
        )

        # Add subscription
        Subscription.objects.create(user=user, plan_type="premium", status="active")

        # Add profile data
        user.profile.branch_of_service = "marines"
        user.profile.disability_rating = 80
        user.profile.save()

        # Create claim
        claim = Claim.objects.create(
            user=user, title="Test Claim", claim_type="initial", status="draft"
        )

        # Create appeal
        appeal = Appeal.objects.create(user=user, appeal_type="hlr", status="gathering")

        # Verify all relationships work
        self.assertTrue(user.is_premium)
        self.assertEqual(user.profile.disability_rating, 80)
        self.assertEqual(user.claims.count(), 1)
        self.assertEqual(user.appeals.count(), 1)


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================


@pytest.mark.django_db
class TestRateLimiting:
    """
    Tests for rate limiting on authentication views.

    Rate limits configured:
    - Login: 5/min, 20/h per IP
    - Signup: 3/h per IP
    - Password Reset: 3/h per IP
    """

    @pytest.fixture
    def enable_rate_limiting(self, settings):
        """Enable rate limiting for these tests."""
        settings.RATELIMIT_ENABLE = True
        yield
        settings.RATELIMIT_ENABLE = False

    @pytest.fixture
    def clear_cache(self):
        """Clear the cache before each test to reset rate limit counters."""
        from django.core.cache import cache

        cache.clear()
        yield
        cache.clear()

    def test_login_rate_limit_per_minute(
        self, client, user, enable_rate_limiting, clear_cache
    ):
        """Login should be rate limited to 5 attempts per minute."""
        url = reverse("account_login")

        # Make 5 failed login attempts (within limit)
        for i in range(5):
            response = client.post(
                url,
                {
                    "login": user.email,
                    "password": "WrongPassword123!",
                },
            )
            # Should get 200 (form re-displayed with error) not 403
            assert (
                response.status_code == 200
            ), f"Request {i+1} should succeed, got {response.status_code}"

        # 6th attempt should be rate limited
        response = client.post(
            url,
            {
                "login": user.email,
                "password": "WrongPassword123!",
            },
        )
        assert response.status_code == 403, "6th request should be rate limited (403)"

    def test_login_allows_successful_login_within_limit(
        self, client, user, user_password, enable_rate_limiting, clear_cache
    ):
        """Successful login should work within rate limit."""
        url = reverse("account_login")

        response = client.post(
            url,
            {
                "login": user.email,
                "password": user_password,
            },
        )
        # Should redirect on successful login
        assert response.status_code == 302

    def test_signup_rate_limit(self, client, db, enable_rate_limiting, clear_cache):
        """Signup should be rate limited to 3 per hour."""
        url = reverse("account_signup")

        # Make 3 signup attempts with INVALID data to not create users
        # This tests the rate limit on POST attempts, not successful signups
        for i in range(3):
            response = client.post(
                url,
                {
                    "email": f"ratelimit_test_{i}@example.com",
                    "password1": "short",  # Invalid password - too short
                    "password2": "short",
                },
            )
            # Should show form with validation errors (200)
            assert (
                response.status_code == 200
            ), f"Signup {i+1} should work, got {response.status_code}"

        # 4th attempt should be rate limited regardless of data validity
        response = client.post(
            url,
            {
                "email": "ratelimit_test_4@example.com",
                "password1": "short",
                "password2": "short",
            },
        )
        assert response.status_code == 403, "4th signup should be rate limited (403)"

    def test_password_reset_rate_limit(
        self, client, user, enable_rate_limiting, clear_cache
    ):
        """Password reset should be rate limited to 3 per hour."""
        url = reverse("account_reset_password")

        # Make 3 reset attempts (within limit)
        for i in range(3):
            response = client.post(
                url,
                {
                    "email": user.email,
                },
            )
            # Should succeed (200 or 302)
            assert response.status_code in [
                200,
                302,
            ], f"Reset {i+1} should work, got {response.status_code}"

        # 4th attempt should be rate limited
        response = client.post(
            url,
            {
                "email": user.email,
            },
        )
        assert (
            response.status_code == 403
        ), "4th password reset should be rate limited (403)"

    def test_rate_limit_different_ips(self, db, enable_rate_limiting, clear_cache):
        """Rate limits should be tracked per IP address."""
        from django.test import Client as DjangoClient

        url = reverse("account_signup")

        # Client 1 (default IP) - use invalid data to not create users
        client1 = DjangoClient()
        for i in range(3):
            response = client1.post(
                url,
                {
                    "email": f"ip1_test_{i}@example.com",
                    "password1": "short",
                    "password2": "short",
                },
            )
            assert response.status_code == 200  # Form validation error

        # Client 1 should be rate limited
        response = client1.post(
            url,
            {
                "email": "ip1_test_4@example.com",
                "password1": "short",
                "password2": "short",
            },
        )
        assert response.status_code == 403

        # Client 2 with different IP should still work
        client2 = DjangoClient(REMOTE_ADDR="192.168.1.100")
        response = client2.post(
            url,
            {
                "email": "ip2_test_1@example.com",
                "password1": "short",
                "password2": "short",
            },
        )
        # Should not be rate limited (different IP) - form error is 200
        assert response.status_code == 200, "Different IP should not be rate limited"

    def test_rate_limit_get_requests_not_limited(
        self, client, enable_rate_limiting, clear_cache
    ):
        """GET requests should not be rate limited (only POST)."""
        url = reverse("account_login")

        # Make many GET requests
        for i in range(20):
            response = client.get(url)
            assert response.status_code == 200, f"GET request {i+1} should succeed"

    def test_rate_limit_error_message(
        self, client, user, enable_rate_limiting, clear_cache
    ):
        """Rate limited response should indicate the issue."""
        url = reverse("account_login")

        # Exhaust rate limit
        for i in range(6):
            client.post(
                url,
                {
                    "login": user.email,
                    "password": "WrongPassword123!",
                },
            )

        # Check 403 response
        response = client.post(
            url,
            {
                "login": user.email,
                "password": "WrongPassword123!",
            },
        )
        assert response.status_code == 403

    def test_rate_limiting_disabled_in_debug(self, client, user, settings, clear_cache):
        """Rate limiting should be disabled when RATELIMIT_ENABLE is False."""
        settings.RATELIMIT_ENABLE = False
        url = reverse("account_login")

        # Make more than 5 requests
        for i in range(10):
            response = client.post(
                url,
                {
                    "login": user.email,
                    "password": "WrongPassword123!",
                },
            )
            # All should succeed (200 for form errors, not 403)
            assert (
                response.status_code == 200
            ), f"Request {i+1} should not be rate limited"


class TestRateLimitingConfiguration(TestCase):
    """Tests for rate limiting configuration."""

    def test_rate_limit_decorators_applied(self):
        """Verify rate limit decorators are applied to views."""
        from accounts.views import (
            RateLimitedLoginView,
            RateLimitedSignupView,
            RateLimitedPasswordResetView,
        )

        # Check that the classes exist and have post methods
        self.assertTrue(hasattr(RateLimitedLoginView, "post"))
        self.assertTrue(hasattr(RateLimitedSignupView, "post"))
        self.assertTrue(hasattr(RateLimitedPasswordResetView, "post"))

    def test_rate_limit_uses_cache_backend(self):
        """Verify rate limiting is configured to use cache."""
        from django.conf import settings

        self.assertEqual(settings.RATELIMIT_USE_CACHE, "default")

    def test_rate_limit_toggle_exists(self):
        """Verify RATELIMIT_ENABLE setting exists."""
        from django.conf import settings

        self.assertTrue(hasattr(settings, "RATELIMIT_ENABLE"))


# =============================================================================
# PILOT MODE CHECKOUT TESTS
# =============================================================================


class TestPilotModeCheckout(TestCase):
    """Tests for checkout behavior in pilot mode."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.client.login(email="test@example.com", password="TestPass123!")

    def test_checkout_blocked_when_pilot_billing_disabled(self):
        """Checkout should redirect with message when PILOT_BILLING_DISABLED is True."""
        from django.urls import reverse

        with self.settings(PILOT_BILLING_DISABLED=True):
            response = self.client.post(reverse("accounts:checkout"))

            # Should redirect to upgrade page
            self.assertEqual(response.status_code, 302)
            self.assertIn("/accounts/upgrade/", response.url)

            # Check for info message
            from django.contrib.messages import get_messages

            messages = list(get_messages(response.wsgi_request))
            self.assertEqual(len(messages), 1)
            self.assertIn("disabled during the pilot", str(messages[0]))

    def test_checkout_allowed_when_pilot_billing_not_disabled(self):
        """Checkout should proceed normally when PILOT_BILLING_DISABLED is False."""
        from django.urls import reverse

        with self.settings(
            PILOT_BILLING_DISABLED=False,
            STRIPE_SECRET_KEY="",  # Empty to trigger config error
            STRIPE_PRICE_ID="",
        ):
            response = self.client.post(reverse("accounts:checkout"))

            # Should redirect due to missing Stripe config, not pilot mode
            self.assertEqual(response.status_code, 302)

            # Message should be about payment config, not pilot mode
            from django.contrib.messages import get_messages

            messages = list(get_messages(response.wsgi_request))
            self.assertEqual(len(messages), 1)
            self.assertIn("not configured", str(messages[0]))


class TestPilotModeUpgradePage(TestCase):
    """Tests for upgrade page in pilot mode."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.client.login(email="test@example.com", password="TestPass123!")

    def test_upgrade_page_shows_pilot_mode_context(self):
        """Upgrade page should include pilot mode context variables."""
        from django.urls import reverse

        with self.settings(PILOT_MODE=True, PILOT_BILLING_DISABLED=True):
            response = self.client.get(reverse("accounts:upgrade"))

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["pilot_mode"])
            self.assertTrue(response.context["pilot_billing_disabled"])

    def test_upgrade_page_shows_pilot_user_status(self):
        """Upgrade page should show is_pilot_user when user has pilot access."""
        from django.urls import reverse

        with self.settings(PILOT_PREMIUM_ACCESS=True):
            response = self.client.get(reverse("accounts:upgrade"))

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["is_pilot_user"])


# =============================================================================
# INVITATION EMAIL-BINDING TESTS (remediation 0.3)
# =============================================================================
# An organization invitation carries a role (veteran / caseworker / admin) and
# is sent to a specific address. A forwarded or leaked link must be useless to
# any account other than the invited, email-verified one — otherwise anyone
# could claim a caseworker/admin role by opening the link.


def _verify_email(user):
    """Mark ``user``'s email verified the way allauth does on confirmation."""
    from allauth.account.models import EmailAddress

    return EmailAddress.objects.create(
        user=user, email=user.email, verified=True, primary=True
    )


@pytest.mark.django_db
class TestInvitationEmailBinding:
    """OrganizationInvitation.accept() is the single enforcement point."""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        from accounts.models import Organization, OrganizationInvitation

        self.org = Organization.objects.create(
            name="Bind Org", slug="bind-org", org_type="vso"
        )
        self.inviter = User.objects.create_user(
            email="admin@bind-org.example.com",
            password="TestPass123!",
            is_verified=True,
        )
        # A privileged (caseworker) invitation — the dangerous case.
        self.invitation = OrganizationInvitation.objects.create(
            organization=self.org,
            email="invited@example.com",
            role="caseworker",
            invited_by=self.inviter,
        )

    def _make_user(self, email, verified):
        user = User.objects.create_user(email=email, password="TestPass123!")
        if verified:
            _verify_email(user)
        return user

    def test_accept_rejects_mismatched_email(self):
        from accounts.models import OrganizationMembership

        attacker = self._make_user("attacker@evil.example.com", verified=True)
        with pytest.raises(ValueError, match="sent to invited@example.com"):
            self.invitation.accept(attacker)

        self.invitation.refresh_from_db()
        assert self.invitation.accepted_at is None
        assert not OrganizationMembership.objects.filter(user=attacker).exists()

    def test_accept_rejects_unverified_invited_user(self):
        from accounts.models import OrganizationMembership

        invited = self._make_user("invited@example.com", verified=False)
        with pytest.raises(ValueError, match="verify your email"):
            self.invitation.accept(invited)

        assert not OrganizationMembership.objects.filter(user=invited).exists()

    def test_accept_allows_invited_verified_user(self):
        from accounts.models import OrganizationMembership

        invited = self._make_user("invited@example.com", verified=True)
        membership = self.invitation.accept(invited)

        assert membership.role == "caseworker"
        self.invitation.refresh_from_db()
        assert self.invitation.accepted_at is not None
        assert OrganizationMembership.objects.filter(
            user=invited, organization=self.org, role="caseworker"
        ).exists()

    def test_accept_allows_verified_via_allauth_emailaddress(self):
        """`User.is_verified` False but a verified allauth EmailAddress → OK."""
        from allauth.account.models import EmailAddress
        from accounts.models import OrganizationMembership

        invited = self._make_user("invited@example.com", verified=False)
        EmailAddress.objects.create(
            user=invited, email=invited.email, verified=True, primary=True
        )
        membership = self.invitation.accept(invited)
        assert OrganizationMembership.objects.filter(
            user=invited, organization=self.org
        ).exists()
        assert membership.role == "caseworker"

    def test_case_insensitive_email_match(self):
        invited = self._make_user("Invited@Example.com", verified=True)
        # Should not raise despite case differences.
        self.invitation.accept(invited)
        self.invitation.refresh_from_db()
        assert self.invitation.accepted_at is not None


@pytest.mark.django_db
class TestOrgInviteAcceptView:
    """The staff-invitation accept view must never accept from a foreign account."""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        from accounts.models import Organization, OrganizationInvitation

        self.org = Organization.objects.create(
            name="View Org", slug="view-org", org_type="vso"
        )
        self.inviter = User.objects.create_user(
            email="admin@view-org.example.com",
            password="TestPass123!",
            is_verified=True,
        )
        self.invitation = OrganizationInvitation.objects.create(
            organization=self.org,
            email="invited@example.com",
            role="caseworker",
            invited_by=self.inviter,
        )
        self.url = reverse("accounts:org_invite_accept", args=[self.invitation.token])

    def test_mismatched_account_post_does_not_grant_role(self, client):
        """A logged-in foreign account POSTing the form gains nothing."""
        from accounts.models import OrganizationMembership

        attacker = User.objects.create_user(
            email="attacker@evil.example.com", password="TestPass123!"
        )
        _verify_email(attacker)
        client.force_login(attacker)
        response = client.post(self.url)

        # Renders the mismatch page rather than accepting.
        assert response.status_code == 200
        self.invitation.refresh_from_db()
        assert self.invitation.accepted_at is None
        assert not OrganizationMembership.objects.filter(user=attacker).exists()

    def test_invited_verified_account_post_accepts(self, client):
        from accounts.models import OrganizationMembership

        invited = User.objects.create_user(
            email="invited@example.com", password="TestPass123!"
        )
        _verify_email(invited)
        client.force_login(invited)
        response = client.post(self.url)

        assert response.status_code == 302
        self.invitation.refresh_from_db()
        assert self.invitation.accepted_at is not None
        assert OrganizationMembership.objects.filter(
            user=invited, organization=self.org, role="caseworker"
        ).exists()

    def test_invited_unverified_account_post_rejected(self, client):
        """Emails match but address unproven → model backstop blocks it."""
        from accounts.models import OrganizationMembership

        # No verified EmailAddress created → email unproven.
        invited = User.objects.create_user(
            email="invited@example.com", password="TestPass123!"
        )
        client.force_login(invited)
        response = client.post(self.url, follow=False)

        # accept() raises ValueError; view catches → redirect, no membership.
        assert response.status_code == 302
        self.invitation.refresh_from_db()
        assert self.invitation.accepted_at is None
        assert not OrganizationMembership.objects.filter(user=invited).exists()
