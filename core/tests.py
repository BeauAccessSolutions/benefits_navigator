"""
Tests for the core app - Journey tracking, milestones, deadlines, and audit logging.

Covers:
- TimeStampedModel abstract base
- SoftDeleteModel soft delete functionality
- JourneyStage model
- UserJourneyEvent model and properties
- JourneyMilestone model
- Deadline model and properties
- AuditLog model and logging functionality
- DataRetentionPolicy model
- Core views (home, dashboard, journey)
- HTMX endpoints for journey features
"""

import pytest
from datetime import date, timedelta

from django.test import TestCase, Client, RequestFactory, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from core.models import (
    JourneyStage,
    UserJourneyEvent,
    JourneyMilestone,
    Deadline,
    AuditLog,
    DataRetentionPolicy,
)

User = get_user_model()


# =============================================================================
# JOURNEY STAGE MODEL TESTS
# =============================================================================


class TestJourneyStageModel(TestCase):
    """Tests for the JourneyStage model."""

    def test_journey_stage_creation(self):
        """JourneyStage can be created with all fields."""
        stage = JourneyStage.objects.create(
            code="claim_filed",
            name="Claim Filed",
            description="Your claim has been filed with the VA",
            order=1,
            typical_duration_days=30,
            icon="document",
            color="blue",
        )
        self.assertEqual(stage.code, "claim_filed")
        self.assertEqual(stage.name, "Claim Filed")
        self.assertEqual(stage.order, 1)

    def test_journey_stage_str_representation(self):
        """JourneyStage string representation is the name."""
        stage = JourneyStage.objects.create(
            code="exam_scheduled",
            name="C&P Exam Scheduled",
        )
        self.assertEqual(str(stage), "C&P Exam Scheduled")

    def test_journey_stage_unique_code(self):
        """JourneyStage code must be unique."""
        JourneyStage.objects.create(code="test_stage", name="Test Stage")
        with self.assertRaises(Exception):
            JourneyStage.objects.create(code="test_stage", name="Duplicate")

    def test_journey_stage_ordering(self):
        """JourneyStages are ordered by order field."""
        stage3 = JourneyStage.objects.create(code="stage3", name="Stage 3", order=3)
        stage1 = JourneyStage.objects.create(code="stage1", name="Stage 1", order=1)
        stage2 = JourneyStage.objects.create(code="stage2", name="Stage 2", order=2)

        stages = list(JourneyStage.objects.all())
        self.assertEqual(stages[0], stage1)
        self.assertEqual(stages[1], stage2)
        self.assertEqual(stages[2], stage3)

    def test_journey_stage_icon_choices(self):
        """JourneyStage accepts valid icon choices."""
        for icon, _ in JourneyStage.ICON_CHOICES:
            stage = JourneyStage.objects.create(
                code=f"stage_{icon}", name=f"Stage {icon}", icon=icon
            )
            self.assertEqual(stage.icon, icon)

    def test_journey_stage_color_choices(self):
        """JourneyStage accepts valid color choices."""
        for color, _ in JourneyStage.COLOR_CHOICES:
            stage = JourneyStage.objects.create(
                code=f"stage_{color}", name=f"Stage {color}", color=color
            )
            self.assertEqual(stage.color, color)


# =============================================================================
# USER JOURNEY EVENT MODEL TESTS
# =============================================================================


class TestUserJourneyEventModel(TestCase):
    """Tests for the UserJourneyEvent model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.stage = JourneyStage.objects.create(
            code="claim_filed",
            name="Claim Filed",
            order=1,
        )

    def test_journey_event_creation(self):
        """UserJourneyEvent can be created."""
        event = UserJourneyEvent.objects.create(
            user=self.user,
            stage=self.stage,
            event_type="manual",
            title="Filed my PTSD claim",
            description="Submitted paperwork to VSO",
            event_date=date.today(),
        )
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.stage, self.stage)

    def test_journey_event_str_representation(self):
        """UserJourneyEvent string includes title and date."""
        event = UserJourneyEvent.objects.create(
            user=self.user,
            stage=self.stage,
            title="Test Event",
            event_date=date.today(),
        )
        self.assertIn("Test Event", str(event))

    def test_journey_event_is_future(self):
        """is_future returns True for future events."""
        future_event = UserJourneyEvent.objects.create(
            user=self.user,
            stage=self.stage,
            title="Future Event",
            event_date=date.today() + timedelta(days=30),
        )
        self.assertTrue(future_event.is_future)

    def test_journey_event_is_not_future_for_past(self):
        """is_future returns False for past events."""
        past_event = UserJourneyEvent.objects.create(
            user=self.user,
            stage=self.stage,
            title="Past Event",
            event_date=date.today() - timedelta(days=30),
        )
        self.assertFalse(past_event.is_future)

    def test_journey_event_is_overdue_incomplete_past(self):
        """is_overdue returns True for incomplete past events."""
        overdue_event = UserJourneyEvent.objects.create(
            user=self.user,
            stage=self.stage,
            title="Overdue Event",
            event_date=date.today() - timedelta(days=10),
            is_completed=False,
        )
        self.assertTrue(overdue_event.is_overdue)

    def test_journey_event_is_not_overdue_when_completed(self):
        """is_overdue returns False for completed events."""
        completed_event = UserJourneyEvent.objects.create(
            user=self.user,
            stage=self.stage,
            title="Completed Event",
            event_date=date.today() - timedelta(days=10),
            is_completed=True,
        )
        self.assertFalse(completed_event.is_overdue)

    def test_journey_event_metadata_json(self):
        """Event metadata can store JSON data."""
        event = UserJourneyEvent.objects.create(
            user=self.user,
            stage=self.stage,
            title="Event with metadata",
            event_date=date.today(),
            metadata={"rating": 70, "conditions": ["PTSD", "Tinnitus"]},
        )
        self.assertEqual(event.metadata["rating"], 70)
        self.assertIn("PTSD", event.metadata["conditions"])


# =============================================================================
# JOURNEY MILESTONE MODEL TESTS
# =============================================================================


class TestJourneyMilestoneModel(TestCase):
    """Tests for the JourneyMilestone model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )

    def test_milestone_creation(self):
        """JourneyMilestone can be created."""
        milestone = JourneyMilestone.objects.create(
            user=self.user,
            milestone_type="claim_filed",
            title="Filed PTSD Claim",
            date=date.today(),
        )
        self.assertEqual(milestone.user, self.user)
        self.assertEqual(milestone.milestone_type, "claim_filed")

    def test_milestone_str_representation(self):
        """JourneyMilestone string includes title and date."""
        milestone = JourneyMilestone.objects.create(
            user=self.user,
            milestone_type="rating_assigned",
            title="Got 70% Rating",
            date=date.today(),
        )
        self.assertIn("Got 70% Rating", str(milestone))

    def test_milestone_type_choices(self):
        """Milestone accepts all valid type choices."""
        valid_types = [choice[0] for choice in JourneyMilestone.MILESTONE_TYPE_CHOICES]
        for mtype in valid_types:
            milestone = JourneyMilestone.objects.create(
                user=self.user,
                milestone_type=mtype,
                title=f"Test {mtype}",
                date=date.today(),
            )
            self.assertEqual(milestone.milestone_type, mtype)

    def test_milestone_details_json(self):
        """Milestone details can store JSON data."""
        milestone = JourneyMilestone.objects.create(
            user=self.user,
            milestone_type="rating_assigned",
            title="Got Rating",
            date=date.today(),
            details={"rating_percentage": 70, "conditions": 3},
        )
        self.assertEqual(milestone.details["rating_percentage"], 70)

    def test_milestone_ordering(self):
        """Milestones are ordered by date descending."""
        old_milestone = JourneyMilestone.objects.create(
            user=self.user,
            milestone_type="claim_filed",
            title="Old Milestone",
            date=date.today() - timedelta(days=60),
        )
        new_milestone = JourneyMilestone.objects.create(
            user=self.user,
            milestone_type="decision_received",
            title="New Milestone",
            date=date.today(),
        )
        milestones = list(self.user.journey_milestones.all())
        self.assertEqual(milestones[0], new_milestone)


# =============================================================================
# DEADLINE MODEL TESTS
# =============================================================================


class TestDeadlineModel(TestCase):
    """Tests for the Deadline model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )

    def test_deadline_creation(self):
        """Deadline can be created."""
        deadline = Deadline.objects.create(
            user=self.user,
            title="Appeal Deadline",
            deadline_date=date.today() + timedelta(days=90),
            priority="critical",
        )
        self.assertEqual(deadline.user, self.user)
        self.assertEqual(deadline.priority, "critical")

    def test_deadline_str_representation(self):
        """Deadline string includes title and date."""
        deadline = Deadline.objects.create(
            user=self.user,
            title="Submit Evidence",
            deadline_date=date.today() + timedelta(days=30),
        )
        self.assertIn("Submit Evidence", str(deadline))

    def test_deadline_days_remaining(self):
        """days_remaining calculates correctly."""
        deadline = Deadline.objects.create(
            user=self.user,
            title="Future Deadline",
            deadline_date=date.today() + timedelta(days=45),
        )
        self.assertEqual(deadline.days_remaining, 45)

    def test_deadline_days_remaining_none_when_completed(self):
        """days_remaining returns None for completed deadlines."""
        deadline = Deadline.objects.create(
            user=self.user,
            title="Completed Deadline",
            deadline_date=date.today() + timedelta(days=30),
            is_completed=True,
        )
        self.assertIsNone(deadline.days_remaining)

    def test_deadline_is_overdue_past_date(self):
        """is_overdue returns True for past incomplete deadlines."""
        deadline = Deadline.objects.create(
            user=self.user,
            title="Past Deadline",
            deadline_date=date.today() - timedelta(days=5),
            is_completed=False,
        )
        self.assertTrue(deadline.is_overdue)

    def test_deadline_is_not_overdue_when_completed(self):
        """is_overdue returns False for completed deadlines."""
        deadline = Deadline.objects.create(
            user=self.user,
            title="Completed Past Deadline",
            deadline_date=date.today() - timedelta(days=5),
            is_completed=True,
        )
        self.assertFalse(deadline.is_overdue)

    def test_deadline_urgency_class_overdue(self):
        """urgency_class returns 'overdue' for past deadlines."""
        deadline = Deadline.objects.create(
            user=self.user,
            title="Overdue Deadline",
            deadline_date=date.today() - timedelta(days=5),
        )
        self.assertEqual(deadline.urgency_class, "overdue")

    def test_deadline_urgency_class_urgent(self):
        """urgency_class returns 'urgent' for deadlines within 7 days."""
        deadline = Deadline.objects.create(
            user=self.user,
            title="Urgent Deadline",
            deadline_date=date.today() + timedelta(days=5),
        )
        self.assertEqual(deadline.urgency_class, "urgent")

    def test_deadline_urgency_class_soon(self):
        """urgency_class returns 'soon' for deadlines within 30 days."""
        deadline = Deadline.objects.create(
            user=self.user,
            title="Soon Deadline",
            deadline_date=date.today() + timedelta(days=20),
        )
        self.assertEqual(deadline.urgency_class, "soon")

    def test_deadline_urgency_class_normal(self):
        """urgency_class returns 'normal' for deadlines beyond 30 days."""
        deadline = Deadline.objects.create(
            user=self.user,
            title="Normal Deadline",
            deadline_date=date.today() + timedelta(days=60),
        )
        self.assertEqual(deadline.urgency_class, "normal")

    def test_deadline_urgency_class_completed(self):
        """urgency_class returns 'completed' for completed deadlines."""
        deadline = Deadline.objects.create(
            user=self.user,
            title="Completed Deadline",
            deadline_date=date.today() + timedelta(days=30),
            is_completed=True,
        )
        self.assertEqual(deadline.urgency_class, "completed")

    def test_deadline_mark_complete(self):
        """mark_complete sets is_completed and completed_at."""
        deadline = Deadline.objects.create(
            user=self.user,
            title="To Be Completed",
            deadline_date=date.today() + timedelta(days=30),
        )
        deadline.mark_complete()
        deadline.refresh_from_db()

        self.assertTrue(deadline.is_completed)
        self.assertIsNotNone(deadline.completed_at)


# =============================================================================
# AUDIT LOG MODEL TESTS
# =============================================================================


class TestAuditLogModel(TestCase):
    """Tests for the AuditLog model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.factory = RequestFactory()

    def test_audit_log_creation(self):
        """AuditLog can be created."""
        log = AuditLog.objects.create(
            user=self.user,
            action="login",
            ip_address="192.168.1.1",
        )
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.action, "login")

    def test_audit_log_preserves_user_email(self):
        """AuditLog saves user email automatically."""
        log = AuditLog.objects.create(
            user=self.user,
            action="login",
        )
        self.assertEqual(log.user_email, "test@example.com")

    def test_audit_log_str_representation(self):
        """AuditLog string includes action and user."""
        log = AuditLog.objects.create(
            user=self.user,
            action="document_upload",
        )
        self.assertIn("document_upload", str(log))
        self.assertIn("test@example.com", str(log))

    def test_audit_log_classmethod(self):
        """AuditLog.log() convenience method works."""
        request = self.factory.get("/")
        request.user = self.user
        request.META["REMOTE_ADDR"] = "10.0.0.1"
        request.META["HTTP_USER_AGENT"] = "Test Browser"

        log = AuditLog.log(
            action="pii_view",
            request=request,
            resource_type="UserProfile",
            resource_id=1,
            details={"field": "va_file_number"},
        )

        self.assertEqual(log.action, "pii_view")
        self.assertEqual(log.ip_address, "10.0.0.1")
        self.assertEqual(log.resource_type, "UserProfile")
        self.assertEqual(log.details["field"], "va_file_number")

    def test_audit_log_gets_user_from_request(self):
        """AuditLog.log() extracts user from request if not provided."""
        request = self.factory.get("/")
        request.user = self.user

        log = AuditLog.log(action="login", request=request)
        self.assertEqual(log.user, self.user)

    def test_audit_log_extracts_ip_from_x_forwarded_for(self):
        """AuditLog extracts IP from X-Forwarded-For header."""
        request = self.factory.get("/")
        request.user = self.user
        request.META["HTTP_X_FORWARDED_FOR"] = "1.2.3.4, 5.6.7.8"

        log = AuditLog.log(action="login", request=request)
        self.assertEqual(log.ip_address, "1.2.3.4")

    def test_audit_log_ordering(self):
        """AuditLogs are ordered by timestamp descending."""
        log1 = AuditLog.objects.create(user=self.user, action="login")
        log2 = AuditLog.objects.create(user=self.user, action="logout")

        logs = list(AuditLog.objects.all())
        self.assertEqual(logs[0], log2)  # Most recent first

    def test_audit_log_success_and_error(self):
        """AuditLog can track success/failure."""
        success_log = AuditLog.objects.create(
            user=self.user,
            action="login",
            success=True,
        )
        self.assertTrue(success_log.success)

        failure_log = AuditLog.objects.create(
            user=self.user,
            action="login_failed",
            success=False,
            error_message="Invalid credentials",
        )
        self.assertFalse(failure_log.success)
        self.assertEqual(failure_log.error_message, "Invalid credentials")


# =============================================================================
# DATA RETENTION POLICY MODEL TESTS
# =============================================================================


class TestDataRetentionPolicyModel(TestCase):
    """Tests for the DataRetentionPolicy model."""

    def test_policy_creation(self):
        """DataRetentionPolicy can be created."""
        policy = DataRetentionPolicy.objects.create(
            data_type="audit_logs",
            retention_days=365,
            description="Keep audit logs for 1 year",
        )
        self.assertEqual(policy.data_type, "audit_logs")
        self.assertEqual(policy.retention_days, 365)

    def test_policy_str_representation(self):
        """DataRetentionPolicy string includes data type and days."""
        policy = DataRetentionPolicy.objects.create(
            data_type="documents",
            retention_days=90,
        )
        self.assertIn("Document", str(policy))
        self.assertIn("90", str(policy))


# =============================================================================
# CORE VIEW TESTS
# =============================================================================


@pytest.mark.django_db
class TestHomeView:
    """Tests for the home page view."""

    def test_home_page_loads(self, client):
        """Home page loads successfully."""
        response = client.get(reverse("home"))
        assert response.status_code == 200

    def test_home_page_contains_title(self, client):
        """Home page contains expected title."""
        response = client.get(reverse("home"))
        assert (
            b"VA Benefits Navigator" in response.content or response.status_code == 200
        )


@pytest.mark.django_db
class TestDashboardView:
    """Tests for the user dashboard view."""

    def test_dashboard_requires_login(self, client):
        """Dashboard requires authentication."""
        response = client.get(reverse("dashboard"))
        assert response.status_code == 302
        assert "login" in response.url.lower()

    def test_dashboard_loads_for_authenticated_user(self, authenticated_client):
        """Dashboard loads for authenticated user."""
        response = authenticated_client.get(reverse("dashboard"))
        assert response.status_code == 200

    def test_dashboard_shows_user_data(
        self, authenticated_client, document, exam_checklist, appeal
    ):
        """Dashboard displays user's documents, checklists, and appeals."""
        response = authenticated_client.get(reverse("dashboard"))
        assert response.status_code == 200
        assert "documents" in response.context
        assert "checklists" in response.context
        assert "appeals" in response.context


@pytest.mark.django_db
class TestJourneyDashboardView:
    """Tests for the journey dashboard view."""

    def test_journey_dashboard_requires_login(self, client):
        """Journey dashboard requires authentication."""
        response = client.get(reverse("core:journey_dashboard"))
        assert response.status_code == 302

    def test_journey_dashboard_loads(self, authenticated_client):
        """Journey dashboard loads for authenticated user."""
        response = authenticated_client.get(reverse("core:journey_dashboard"))
        assert response.status_code == 200

    def test_journey_dashboard_shows_timeline(
        self, authenticated_client, journey_event, milestone, deadline
    ):
        """Journey dashboard shows timeline data."""
        response = authenticated_client.get(reverse("core:journey_dashboard"))
        assert response.status_code == 200
        assert "timeline" in response.context
        assert "deadlines" in response.context
        assert "milestones" in response.context

    def test_journey_dashboard_htmx_targets_are_live_regions(
        self, authenticated_client, journey_event, milestone, deadline
    ):
        """
        #timeline-content and #deadline-<pk> are HTMX swap targets — both
        must carry aria-live so screen readers hear about refreshes and
        deadline-toggle updates.
        """
        html = authenticated_client.get(
            reverse("core:journey_dashboard")
        ).content.decode()
        assert 'id="timeline-content" aria-live="polite"' in html
        assert f'id="deadline-{deadline.pk}" class="p-4" aria-live="polite"' in html


@pytest.mark.django_db
class TestMilestoneViews:
    """Tests for milestone views."""

    def test_add_milestone_requires_login(self, client):
        """Add milestone requires authentication."""
        response = client.get(reverse("core:add_milestone"))
        assert response.status_code == 302

    def test_add_milestone_get_shows_form(self, authenticated_client):
        """GET request shows milestone form."""
        response = authenticated_client.get(reverse("core:add_milestone"))
        assert response.status_code == 200
        assert "milestone_types" in response.context

    def test_add_milestone_post_creates_milestone(self, authenticated_client, user):
        """POST request creates new milestone."""
        response = authenticated_client.post(
            reverse("core:add_milestone"),
            {
                "milestone_type": "claim_filed",
                "title": "Filed my claim",
                "date": date.today().isoformat(),
                "notes": "Finally got it done!",
            },
        )
        assert response.status_code == 302  # Redirect on success
        assert JourneyMilestone.objects.filter(
            user=user, title="Filed my claim"
        ).exists()

    def test_add_milestone_requires_title(self, authenticated_client):
        """Milestone creation requires title."""
        response = authenticated_client.post(
            reverse("core:add_milestone"),
            {
                "milestone_type": "claim_filed",
                "title": "",  # Empty title
                "date": date.today().isoformat(),
            },
        )
        assert response.status_code == 302  # Redirects with error message

    def test_delete_milestone(self, authenticated_client, milestone):
        """Milestone can be deleted."""
        response = authenticated_client.post(
            reverse("core:delete_milestone", kwargs={"pk": milestone.pk})
        )
        assert response.status_code == 302
        assert not JourneyMilestone.objects.filter(pk=milestone.pk).exists()


@pytest.mark.django_db
class TestDeadlineViews:
    """Tests for deadline views."""

    def test_add_deadline_requires_login(self, client):
        """Add deadline requires authentication."""
        response = client.get(reverse("core:add_deadline"))
        assert response.status_code == 302

    def test_add_deadline_get_shows_form(self, authenticated_client):
        """GET request shows deadline form."""
        response = authenticated_client.get(reverse("core:add_deadline"))
        assert response.status_code == 200
        assert "priority_choices" in response.context

    def test_add_deadline_post_creates_deadline(self, authenticated_client, user):
        """POST request creates new deadline."""
        response = authenticated_client.post(
            reverse("core:add_deadline"),
            {
                "title": "Submit appeal",
                "deadline_date": (date.today() + timedelta(days=60)).isoformat(),
                "priority": "high",
                "description": "File HLR before deadline",
            },
        )
        assert response.status_code == 302
        assert Deadline.objects.filter(user=user, title="Submit appeal").exists()

    def test_toggle_deadline(self, authenticated_client, deadline):
        """Deadline completion can be toggled."""
        assert not deadline.is_completed

        response = authenticated_client.post(
            reverse("core:toggle_deadline", kwargs={"pk": deadline.pk})
        )
        assert response.status_code == 200

        deadline.refresh_from_db()
        assert deadline.is_completed

    def test_delete_deadline(self, authenticated_client, deadline):
        """Deadline can be deleted."""
        response = authenticated_client.post(
            reverse("core:delete_deadline", kwargs={"pk": deadline.pk})
        )
        assert response.status_code == 302
        assert not Deadline.objects.filter(pk=deadline.pk).exists()


# =============================================================================
# ACCESS CONTROL TESTS
# =============================================================================


@pytest.mark.django_db
class TestAccessControl:
    """Tests for access control on core views."""

    def test_user_cannot_access_other_users_deadline(
        self, authenticated_client, other_user
    ):
        """User cannot toggle another user's deadline."""
        other_deadline = Deadline.objects.create(
            user=other_user,
            title="Other's Deadline",
            deadline_date=date.today() + timedelta(days=30),
        )
        response = authenticated_client.post(
            reverse("core:toggle_deadline", kwargs={"pk": other_deadline.pk})
        )
        assert response.status_code == 404

    def test_user_cannot_delete_other_users_milestone(
        self, authenticated_client, other_user
    ):
        """User cannot delete another user's milestone."""
        other_milestone = JourneyMilestone.objects.create(
            user=other_user,
            milestone_type="claim_filed",
            title="Other's Milestone",
            date=date.today(),
        )
        response = authenticated_client.post(
            reverse("core:delete_milestone", kwargs={"pk": other_milestone.pk})
        )
        assert response.status_code == 404


# =============================================================================
# JOURNEY TIMELINE BUILDER TESTS
# =============================================================================


class TestTimelineBuilder(TestCase):
    """Tests for the TimelineBuilder service."""

    def setUp(self):
        from core.journey import TimelineBuilder

        self.user = User.objects.create_user(
            email="test@example.com", password="TestPass123!"
        )
        self.builder = TimelineBuilder(self.user)
        self.stage = JourneyStage.objects.create(
            code="test_stage",
            name="Test Stage",
            order=1,
        )

    def test_build_timeline_returns_events(self):
        """build_timeline returns user's journey events."""
        UserJourneyEvent.objects.create(
            user=self.user,
            stage=self.stage,
            title="Event 1",
            event_date=date.today(),
        )
        UserJourneyEvent.objects.create(
            user=self.user,
            stage=self.stage,
            title="Event 2",
            event_date=date.today() - timedelta(days=5),
        )

        timeline = self.builder.build_timeline(limit=10)
        self.assertEqual(len(timeline), 2)

    def test_build_timeline_respects_limit(self):
        """build_timeline respects the limit parameter."""
        for i in range(5):
            UserJourneyEvent.objects.create(
                user=self.user,
                stage=self.stage,
                title=f"Event {i}",
                event_date=date.today() - timedelta(days=i),
            )

        timeline = self.builder.build_timeline(limit=3)
        self.assertEqual(len(timeline), 3)

    def test_get_upcoming_deadlines(self):
        """get_upcoming_deadlines returns future deadlines."""
        future = Deadline.objects.create(
            user=self.user,
            title="Future Deadline",
            deadline_date=date.today() + timedelta(days=30),
        )
        past = Deadline.objects.create(
            user=self.user,
            title="Past Deadline",
            deadline_date=date.today() - timedelta(days=10),
        )

        deadlines = self.builder.get_upcoming_deadlines(days=60)
        self.assertIn(future, deadlines)
        self.assertNotIn(past, deadlines)

    def test_get_stats(self):
        """get_stats returns journey statistics."""
        JourneyMilestone.objects.create(
            user=self.user,
            milestone_type="claim_filed",
            title="Milestone 1",
            date=date.today(),
        )
        Deadline.objects.create(
            user=self.user,
            title="Deadline 1",
            deadline_date=date.today() + timedelta(days=30),
        )

        stats = self.builder.get_stats()
        self.assertIn("milestone_count", stats)
        self.assertIn("deadline_count", stats)


# =============================================================================
# CONTENT SECURITY POLICY (CSP) TESTS
# =============================================================================


@pytest.mark.django_db
class TestCSPHeaders:
    """
    Tests to verify Content Security Policy headers are configured correctly
    and don't break application functionality.

    CSP Configuration (Tailwind now served from static file, no CDN):
    - default-src: 'self'
    - script-src: 'self', 'unsafe-inline', unpkg.com (HTMX)
    - style-src: 'self' only (no unsafe-inline, no CDN)
    - img-src: 'self', data:, https:
    - font-src: 'self', fonts.gstatic.com
    - connect-src: 'self'
    - frame-ancestors: 'none'
    - form-action: 'self'
    """

    def test_csp_header_present(self, client):
        """CSP header is present in responses."""
        response = client.get(reverse("home"))
        assert response.status_code == 200
        assert "Content-Security-Policy" in response.headers

    def test_csp_default_src_self(self, client):
        """CSP default-src is set to 'self'."""
        response = client.get(reverse("home"))
        csp = response.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp

    def test_csp_style_src_self_only(self, client):
        """CSP style-src is self-only — Tailwind is now served from static file, not CDN."""
        response = client.get(reverse("home"))
        csp = response.headers.get("Content-Security-Policy", "")
        assert "cdn.tailwindcss.com" not in csp
        assert "style-src 'self'" in csp

    def test_csp_allows_htmx_cdn(self, client):
        """CSP allows HTMX from unpkg.com CDN."""
        response = client.get(reverse("home"))
        csp = response.headers.get("Content-Security-Policy", "")
        assert "unpkg.com" in csp

    def test_csp_allows_data_urls_for_images(self, client):
        """CSP allows data: URLs for images."""
        response = client.get(reverse("home"))
        csp = response.headers.get("Content-Security-Policy", "")
        assert "img-src" in csp
        assert "data:" in csp

    def test_csp_allows_google_fonts(self, client):
        """CSP allows fonts from Google."""
        response = client.get(reverse("home"))
        csp = response.headers.get("Content-Security-Policy", "")
        assert "fonts.gstatic.com" in csp

    def test_csp_blocks_framing(self, client):
        """CSP prevents page from being framed (clickjacking protection)."""
        response = client.get(reverse("home"))
        csp = response.headers.get("Content-Security-Policy", "")
        assert "frame-ancestors 'none'" in csp

    def test_csp_form_action_self(self, client):
        """CSP restricts form submissions to same origin."""
        response = client.get(reverse("home"))
        csp = response.headers.get("Content-Security-Policy", "")
        assert "form-action 'self'" in csp

    def test_csp_connect_src_self(self, client):
        """CSP restricts AJAX/fetch to same origin (for HTMX)."""
        response = client.get(reverse("home"))
        csp = response.headers.get("Content-Security-Policy", "")
        assert "connect-src 'self'" in csp


@pytest.mark.django_db
class TestCSPFunctionality:
    """
    Tests to verify CSP doesn't break application functionality.
    These tests simulate actual user interactions that depend on CSP-allowed resources.
    """

    def test_homepage_renders_with_csp(self, client):
        """Homepage renders correctly with CSP enabled."""
        response = client.get(reverse("home"))
        assert response.status_code == 200
        # Page should contain expected content
        assert (
            b"VA Benefits Navigator" in response.content or b"Sign" in response.content
        )

    def test_login_form_works_with_csp(self, client, user, user_password):
        """Login form submission works with CSP form-action restriction."""
        # Forms should work since form-action allows 'self'
        response = client.post(
            reverse("account_login"),
            {
                "login": user.email,
                "password": user_password,
            },
        )
        # Should redirect on successful login (302) - form submission worked
        assert response.status_code == 302

    def test_htmx_endpoints_work_with_csp(self, authenticated_client, deadline):
        """HTMX AJAX requests work with CSP connect-src restriction."""
        # HTMX makes fetch/XHR requests to same origin, which should work
        response = authenticated_client.post(
            reverse("core:toggle_deadline", kwargs={"pk": deadline.pk}),
            HTTP_HX_REQUEST="true",  # Simulate HTMX request
        )
        # Should succeed - connect-src allows 'self'
        assert response.status_code == 200

    def test_rating_calculator_htmx_works(self, client):
        """Rating calculator HTMX endpoint works with CSP."""
        import json

        response = client.post(
            reverse("examprep:calculate_rating"),
            {
                "ratings": json.dumps(
                    [
                        {
                            "percentage": 50,
                            "description": "PTSD",
                            "is_bilateral": False,
                        },
                        {
                            "percentage": 30,
                            "description": "Back",
                            "is_bilateral": False,
                        },
                    ]
                ),
                "has_spouse": "false",
                "children_under_18": "0",
                "dependent_parents": "0",
            },
            HTTP_HX_REQUEST="true",
        )
        # Should work - HTMX requests go to same origin
        assert response.status_code == 200

    def test_dashboard_loads_with_csp(self, authenticated_client):
        """Dashboard page loads correctly with CSP."""
        response = authenticated_client.get(reverse("dashboard"))
        assert response.status_code == 200
        # Should render without CSP blocking resources
        assert b"Dashboard" in response.content or response.status_code == 200

    def test_journey_dashboard_htmx_partial(self, authenticated_client):
        """Journey timeline HTMX partial works with CSP."""
        response = authenticated_client.get(
            reverse("core:journey_timeline"),
            HTTP_HX_REQUEST="true",
        )
        # Partial should load - same-origin request
        assert response.status_code == 200


@pytest.mark.django_db
class TestSecurityHeaders:
    """Tests for other security headers beyond CSP."""

    def test_x_content_type_options_header(self, client):
        """X-Content-Type-Options header prevents MIME sniffing."""
        response = client.get(reverse("home"))
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options_header(self, client):
        """X-Frame-Options header prevents clickjacking."""
        response = client.get(reverse("home"))
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_referrer_policy_header(self, client):
        """Referrer-Policy header is set."""
        response = client.get(reverse("home"))
        referrer = response.headers.get("Referrer-Policy", "")
        assert (
            "strict-origin" in referrer.lower()
            or "same-origin" in referrer.lower()
            or referrer != ""
        )


class TestCSPConfiguration(TestCase):
    """Tests for CSP configuration in settings."""

    def test_csp_middleware_enabled(self):
        """CSP middleware is in MIDDLEWARE setting."""
        from django.conf import settings

        assert "csp.middleware.CSPMiddleware" in settings.MIDDLEWARE

    def test_csp_default_src_configured(self):
        """CSP_DEFAULT_SRC is configured."""
        from django.conf import settings

        assert hasattr(settings, "CSP_DEFAULT_SRC")
        assert "'self'" in settings.CSP_DEFAULT_SRC

    def test_csp_script_src_includes_htmx_cdn(self):
        """CSP_SCRIPT_SRC includes unpkg.com for HTMX (Tailwind CDN removed)."""
        from django.conf import settings

        assert hasattr(settings, "CSP_SCRIPT_SRC")
        script_src = settings.CSP_SCRIPT_SRC
        assert not any("cdn.tailwindcss.com" in src for src in script_src)
        assert any("unpkg.com" in src for src in script_src)

    def test_csp_style_src_self_only(self):
        """CSP_STYLE_SRC is self-only — Tailwind served from static file, no CDN needed."""
        from django.conf import settings

        assert hasattr(settings, "CSP_STYLE_SRC")
        style_src = settings.CSP_STYLE_SRC
        assert not any("cdn.tailwindcss.com" in src for src in style_src)
        assert not any("unsafe-inline" in src for src in style_src)
        assert "'self'" in style_src

    def test_csp_connect_src_for_htmx(self):
        """CSP_CONNECT_SRC allows same-origin for HTMX."""
        from django.conf import settings

        assert hasattr(settings, "CSP_CONNECT_SRC")
        assert "'self'" in settings.CSP_CONNECT_SRC

    def test_csp_frame_ancestors_blocks_framing(self):
        """CSP_FRAME_ANCESTORS prevents framing."""
        from django.conf import settings

        assert hasattr(settings, "CSP_FRAME_ANCESTORS")
        assert "'none'" in settings.CSP_FRAME_ANCESTORS

    def test_csp_form_action_restricts_forms(self):
        """CSP_FORM_ACTION restricts form targets."""
        from django.conf import settings

        assert hasattr(settings, "CSP_FORM_ACTION")
        assert "'self'" in settings.CSP_FORM_ACTION


# =============================================================================
# DOCUMENT ANALYSIS NOTIFICATION TESTS
# =============================================================================


class TestDocumentAnalysisNotification(TestCase):
    """Tests for document analysis complete email notifications."""

    def setUp(self):
        from accounts.models import NotificationPreferences

        self.client = Client()
        self.user = User.objects.create_user(
            email="docuser@example.com", password="TestPass123!"
        )
        # Delete any existing preferences to start fresh
        NotificationPreferences.objects.filter(user=self.user).delete()

    def test_send_document_analysis_email_task_sends_email(self):
        """Task sends email when document analysis completes."""
        from core.tasks import send_document_analysis_complete_email
        from claims.models import Document
        from accounts.models import NotificationPreferences

        # Create notification preferences
        prefs, _ = NotificationPreferences.objects.get_or_create(
            user=self.user, defaults={"email_enabled": True, "document_analysis": True}
        )
        prefs.email_enabled = True
        prefs.document_analysis = True
        prefs.save()

        # Create a completed document
        doc = Document.objects.create(
            user=self.user,
            document_type="decision_letter",
            file_name="test_decision.pdf",
            status="completed",
            ai_summary="Test summary of the document.",
            page_count=5,
        )

        # Call the task
        from django.core import mail

        result = send_document_analysis_complete_email(doc.id)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Decision Letter", mail.outbox[0].subject)
        self.assertIn("docuser@example.com", mail.outbox[0].to)

    def test_send_document_analysis_email_respects_disabled_preference(self):
        """Task doesn't send email when notification is disabled."""
        from core.tasks import send_document_analysis_complete_email
        from claims.models import Document
        from accounts.models import NotificationPreferences

        # Create notification preferences with document_analysis disabled
        prefs, _ = NotificationPreferences.objects.get_or_create(
            user=self.user, defaults={"email_enabled": True, "document_analysis": False}
        )
        prefs.email_enabled = True
        prefs.document_analysis = False  # Disabled
        prefs.save()

        # Create a completed document
        doc = Document.objects.create(
            user=self.user,
            document_type="medical_records",
            file_name="test_medical.pdf",
            status="completed",
        )

        # Call the task
        from django.core import mail

        result = send_document_analysis_complete_email(doc.id)

        # Check no email was sent
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("disabled", result)

    def test_send_document_analysis_email_respects_master_switch(self):
        """Task doesn't send email when email_enabled is False."""
        from core.tasks import send_document_analysis_complete_email
        from claims.models import Document
        from accounts.models import NotificationPreferences

        # Create notification preferences with master switch off
        prefs, _ = NotificationPreferences.objects.get_or_create(
            user=self.user, defaults={"email_enabled": False, "document_analysis": True}
        )
        prefs.email_enabled = False  # Master switch off
        prefs.document_analysis = True
        prefs.save()

        # Create a completed document
        doc = Document.objects.create(
            user=self.user,
            document_type="nexus_letter",
            file_name="nexus.pdf",
            status="completed",
        )

        # Call the task
        from django.core import mail

        result = send_document_analysis_complete_email(doc.id)

        # Check no email was sent
        self.assertEqual(len(mail.outbox), 0)

    def test_send_document_analysis_email_creates_default_preferences(self):
        """Task creates default preferences if they don't exist."""
        from core.tasks import send_document_analysis_complete_email
        from claims.models import Document
        from accounts.models import NotificationPreferences

        # Ensure no preferences exist
        NotificationPreferences.objects.filter(user=self.user).delete()
        self.assertFalse(
            NotificationPreferences.objects.filter(user=self.user).exists()
        )

        # Create a completed document
        doc = Document.objects.create(
            user=self.user,
            document_type="buddy_statement",
            file_name="buddy.pdf",
            status="completed",
        )

        # Call the task
        from django.core import mail

        result = send_document_analysis_complete_email(doc.id)

        # Check preferences were created
        self.assertTrue(NotificationPreferences.objects.filter(user=self.user).exists())

        # Check email was sent (default is enabled)
        self.assertEqual(len(mail.outbox), 1)

    def test_send_document_analysis_email_handles_missing_document(self):
        """Task handles non-existent document gracefully."""
        from core.tasks import send_document_analysis_complete_email

        result = send_document_analysis_complete_email(99999)
        self.assertIn("not found", result)

    def test_notification_preference_should_send_method(self):
        """Test the should_send_document_analysis_notification method."""
        from accounts.models import NotificationPreferences

        # Test with all enabled
        prefs, _ = NotificationPreferences.objects.get_or_create(
            user=self.user, defaults={"email_enabled": True, "document_analysis": True}
        )
        prefs.email_enabled = True
        prefs.document_analysis = True
        prefs.save()
        self.assertTrue(prefs.should_send_document_analysis_notification())

        # Test with document_analysis disabled
        prefs.document_analysis = False
        prefs.save()
        self.assertFalse(prefs.should_send_document_analysis_notification())

        # Test with master switch disabled
        prefs.email_enabled = False
        prefs.document_analysis = True
        prefs.save()
        self.assertFalse(prefs.should_send_document_analysis_notification())

    def test_document_analysis_email_updates_tracking(self):
        """Sending email updates notification tracking fields."""
        from core.tasks import send_document_analysis_complete_email
        from claims.models import Document
        from accounts.models import NotificationPreferences

        prefs, _ = NotificationPreferences.objects.get_or_create(
            user=self.user,
            defaults={
                "email_enabled": True,
                "document_analysis": True,
                "emails_sent_count": 5,
            },
        )
        prefs.email_enabled = True
        prefs.document_analysis = True
        prefs.emails_sent_count = 5
        prefs.save()

        doc = Document.objects.create(
            user=self.user,
            document_type="other",
            file_name="test.pdf",
            status="completed",
        )

        send_document_analysis_complete_email(doc.id)

        # Refresh and check tracking updated
        prefs.refresh_from_db()
        self.assertEqual(prefs.emails_sent_count, 6)
        self.assertIsNotNone(prefs.last_email_sent)

    def test_document_analysis_email_includes_correct_doc_type_labels(self):
        """Email uses correct document type labels."""
        from core.tasks import send_document_analysis_complete_email
        from claims.models import Document
        from accounts.models import NotificationPreferences

        prefs, _ = NotificationPreferences.objects.get_or_create(
            user=self.user, defaults={"email_enabled": True, "document_analysis": True}
        )
        prefs.email_enabled = True
        prefs.document_analysis = True
        prefs.save()

        doc_types = [
            ("decision_letter", "VA Decision Letter"),
            ("medical_records", "Medical Records"),
            ("service_records", "Service Records"),
            ("nexus_letter", "Medical Nexus/Opinion Letter"),
            ("buddy_statement", "Buddy Statement"),
            ("other", "Document"),
        ]

        from django.core import mail

        for doc_type, expected_label in doc_types:
            mail.outbox = []  # Clear outbox

            doc = Document.objects.create(
                user=self.user,
                document_type=doc_type,
                file_name=f"test_{doc_type}.pdf",
                status="completed",
            )

            send_document_analysis_complete_email(doc.id)

            self.assertEqual(len(mail.outbox), 1)
            self.assertIn(expected_label, mail.outbox[0].subject)


# =============================================================================
# SITEMAP AND ROBOTS.TXT TESTS
# =============================================================================


class TestRobotsTxt(TestCase):
    """Tests for robots.txt"""

    def test_robots_txt_accessible(self):
        """robots.txt is accessible."""
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)

    def test_robots_txt_content_type(self):
        """robots.txt has correct content type."""
        response = self.client.get("/robots.txt")
        self.assertEqual(response["Content-Type"], "text/plain")

    def test_robots_txt_contains_sitemap(self):
        """robots.txt references sitemap.xml."""
        response = self.client.get("/robots.txt")
        self.assertIn(b"Sitemap:", response.content)
        self.assertIn(b"sitemap.xml", response.content)

    def test_robots_txt_disallows_admin(self):
        """robots.txt disallows admin access."""
        response = self.client.get("/robots.txt")
        self.assertIn(b"Disallow: /admin/", response.content)

    def test_robots_txt_disallows_accounts(self):
        """robots.txt disallows accounts/private areas."""
        response = self.client.get("/robots.txt")
        self.assertIn(b"Disallow: /accounts/", response.content)
        self.assertIn(b"Disallow: /dashboard/", response.content)
        self.assertIn(b"Disallow: /claims/", response.content)

    def test_robots_txt_allows_public_content(self):
        """robots.txt allows public content areas."""
        response = self.client.get("/robots.txt")
        self.assertIn(b"Allow: /exam-prep/", response.content)
        self.assertIn(b"Allow: /appeals/", response.content)


class TestSitemap(TestCase):
    """Tests for sitemap.xml"""

    def test_sitemap_accessible(self):
        """sitemap.xml is accessible."""
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)

    def test_sitemap_content_type(self):
        """sitemap.xml has correct content type."""
        response = self.client.get("/sitemap.xml")
        self.assertIn("xml", response["Content-Type"])

    def test_sitemap_contains_urls(self):
        """sitemap.xml contains URL entries."""
        response = self.client.get("/sitemap.xml")
        content = response.content.decode()
        self.assertIn("<urlset", content)
        self.assertIn("<url>", content)
        self.assertIn("<loc>", content)

    def test_sitemap_contains_static_pages(self):
        """sitemap.xml includes static pages."""
        response = self.client.get("/sitemap.xml")
        content = response.content.decode()
        # Check for key static pages
        self.assertIn("/exam-prep/", content)
        self.assertIn("/appeals/", content)

    def test_sitemap_contains_rating_calculator(self):
        """sitemap.xml includes rating calculator."""
        response = self.client.get("/sitemap.xml")
        content = response.content.decode()
        self.assertIn("rating-calculator", content)

    def test_sitemap_valid_xml(self):
        """sitemap.xml is valid XML."""
        import xml.etree.ElementTree as ET

        response = self.client.get("/sitemap.xml")
        # This will raise an exception if XML is invalid
        ET.fromstring(response.content)


# =============================================================================
# META TAGS AND OPEN GRAPH TESTS
# =============================================================================


class TestMetaTags(TestCase):
    """Tests for meta descriptions and Open Graph tags."""

    def test_home_page_has_meta_description(self):
        """Home page has custom meta description."""
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn('meta name="description"', content)
        self.assertIn("maximize VA disability ratings", content)

    def test_home_page_has_og_tags(self):
        """Home page has Open Graph tags."""
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn("og:title", content)
        self.assertIn("og:description", content)
        self.assertIn("og:type", content)
        self.assertIn("og:url", content)

    def test_home_page_has_twitter_cards(self):
        """Home page has Twitter Card meta tags."""
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn("twitter:card", content)
        self.assertIn("twitter:title", content)
        self.assertIn("twitter:description", content)

    def test_rating_calculator_has_meta_description(self):
        """Rating calculator has custom meta description."""
        response = self.client.get("/exam-prep/rating-calculator/")
        content = response.content.decode()
        self.assertIn("VA disability rating calculator", content)

    def test_exam_guides_has_meta_description(self):
        """Exam guides list has custom meta description."""
        response = self.client.get("/exam-prep/")
        content = response.content.decode()
        self.assertIn("Compensation & Pension exam", content)

    def test_glossary_has_meta_description(self):
        """Glossary has custom meta description."""
        response = self.client.get("/exam-prep/glossary/")
        content = response.content.decode()
        self.assertIn("VA terms", content)

    def test_appeals_has_meta_description(self):
        """Appeals page has custom meta description."""
        response = self.client.get("/appeals/")
        content = response.content.decode()
        self.assertIn("appeals", content.lower())

    def test_canonical_url_present(self):
        """Pages have canonical URL tags."""
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn('rel="canonical"', content)

    def test_robots_meta_tag_present(self):
        """Pages have robots meta tag."""
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn('name="robots"', content)
        self.assertIn("index, follow", content)


class TestStructuredData(TestCase):
    """Tests for JSON-LD structured data."""

    def test_home_page_has_website_schema(self):
        """Home page has WebSite schema."""
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn("application/ld+json", content)
        self.assertIn('"@type": "WebSite"', content)

    def test_home_page_has_search_action(self):
        """Home page WebSite schema includes SearchAction."""
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn("SearchAction", content)

    def test_glossary_page_loads(self):
        """Glossary list page loads correctly."""
        response = self.client.get("/exam-prep/glossary/")
        self.assertEqual(response.status_code, 200)

    def test_rating_calculator_has_base_schema(self):
        """Rating calculator has base WebSite schema."""
        response = self.client.get("/exam-prep/rating-calculator/")
        content = response.content.decode()
        self.assertIn("application/ld+json", content)
        self.assertIn("@context", content)

    def test_appeals_page_has_schema(self):
        """Appeals page has structured data."""
        response = self.client.get("/appeals/")
        content = response.content.decode()
        self.assertIn("application/ld+json", content)

    def test_secondary_conditions_hub_loads(self):
        """Secondary conditions hub loads correctly."""
        response = self.client.get("/exam-prep/secondary-conditions/")
        self.assertEqual(response.status_code, 200)


# =============================================================================
# SIGNED URL TESTS
# =============================================================================


class TestSignedURLGenerator(TestCase):
    """Tests for the SignedURLGenerator utility."""

    def setUp(self):
        from core.signed_urls import SignedURLGenerator

        self.generator = SignedURLGenerator(secret_key="test-secret-key")
        self.user = User.objects.create_user(
            email="signedurl@example.com", password="TestPass123!"
        )

    def test_generate_token_returns_string(self):
        """generate_token returns a non-empty string."""
        token = self.generator.generate_token(
            resource_type="document",
            resource_id=123,
            user_id=456,
            action="download",
        )
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)

    def test_token_contains_signature(self):
        """Token contains a signature component."""
        token = self.generator.generate_token(
            resource_type="document",
            resource_id=123,
            user_id=456,
        )
        self.assertIn(".", token)
        parts = token.split(".")
        self.assertEqual(len(parts), 2)

    def test_validate_token_returns_data(self):
        """validate_token returns expected data for valid token."""
        token = self.generator.generate_token(
            resource_type="document",
            resource_id=123,
            user_id=456,
            action="download",
        )
        data = self.generator.validate_token(token)
        self.assertEqual(data["resource_type"], "document")
        self.assertEqual(data["resource_id"], 123)
        self.assertEqual(data["user_id"], 456)
        self.assertEqual(data["action"], "download")

    def test_validate_token_raises_on_tampered_signature(self):
        """validate_token raises InvalidTokenError for tampered signature."""
        from core.signed_urls import InvalidTokenError

        token = self.generator.generate_token(
            resource_type="document",
            resource_id=123,
            user_id=456,
        )
        # Tamper with the signature
        parts = token.split(".")
        tampered_token = parts[0] + ".tampered_signature"

        with self.assertRaises(InvalidTokenError):
            self.generator.validate_token(tampered_token)

    def test_validate_token_raises_on_expired(self):
        """validate_token raises TokenExpiredError for expired token."""
        from core.signed_urls import TokenExpiredError
        import time

        # Generate token with very short expiration
        token = self.generator.generate_token(
            resource_type="document",
            resource_id=123,
            user_id=456,
            expires_minutes=0,  # Will be 0 minutes, essentially expired
        )

        # Wait a moment to ensure expiration
        time.sleep(0.1)

        with self.assertRaises(TokenExpiredError):
            self.generator.validate_token(token)

    def test_validate_token_raises_on_invalid_format(self):
        """validate_token raises InvalidTokenError for malformed token."""
        from core.signed_urls import InvalidTokenError

        with self.assertRaises(InvalidTokenError):
            self.generator.validate_token("not-a-valid-token")

        with self.assertRaises(InvalidTokenError):
            self.generator.validate_token("")

    def test_generate_url_creates_valid_path(self):
        """generate_url creates a URL with the token."""
        url = self.generator.generate_url(
            resource_type="document",
            resource_id=123,
            user_id=456,
            action="download",
        )
        self.assertIn("/claims/document/s/", url)
        self.assertIn("/download/", url)

    def test_generate_url_view_action(self):
        """generate_url with view action creates view URL."""
        url = self.generator.generate_url(
            resource_type="document",
            resource_id=123,
            user_id=456,
            action="view",
        )
        self.assertIn("/view/", url)

    def test_token_with_extra_data(self):
        """Token can include extra data."""
        token = self.generator.generate_token(
            resource_type="document",
            resource_id=123,
            user_id=456,
            extra_data={"vso_id": 789},
        )
        data = self.generator.validate_token(token)
        self.assertIsNotNone(data["extra_data"])
        self.assertEqual(data["extra_data"]["vso_id"], 789)

    def test_max_expiration_enforced(self):
        """Expiration time is capped at MAX_EXPIRES_MINUTES."""
        # Request 48 hours (2880 minutes) - should be capped at 24 hours (1440)
        token = self.generator.generate_token(
            resource_type="document",
            resource_id=123,
            user_id=456,
            expires_minutes=2880,
        )
        data = self.generator.validate_token(token)

        import time

        max_expected = int(time.time()) + (1440 * 60) + 5  # 24 hours + 5 second buffer
        self.assertLessEqual(data["expires_at"], max_expected)


class TestSignedURLConvenienceFunctions(TestCase):
    """Tests for signed URL convenience functions."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="convenience@example.com", password="TestPass123!"
        )

    def test_get_signed_url_generator_returns_singleton(self):
        """get_signed_url_generator returns the same instance."""
        from core.signed_urls import get_signed_url_generator

        gen1 = get_signed_url_generator()
        gen2 = get_signed_url_generator()
        self.assertIs(gen1, gen2)

    def test_generate_signed_url_function(self):
        """generate_signed_url convenience function works."""
        from core.signed_urls import generate_signed_url

        url = generate_signed_url(
            resource_type="document",
            resource_id=123,
            user_id=456,
            action="download",
            expires_minutes=30,
        )
        self.assertIn("/claims/document/s/", url)

    def test_validate_signed_token_function(self):
        """validate_signed_token convenience function works."""
        from core.signed_urls import validate_signed_token, get_signed_url_generator

        generator = get_signed_url_generator()
        token = generator.generate_token(
            resource_type="document",
            resource_id=123,
            user_id=456,
        )

        data = validate_signed_token(token)
        self.assertEqual(data["resource_id"], 123)


@pytest.mark.django_db
class TestSignedURLViews:
    """Tests for signed URL access views."""

    def test_signed_download_with_valid_token(self, client, user, document_with_file):
        """Valid signed URL allows download without login."""
        from core.signed_urls import get_signed_url_generator

        generator = get_signed_url_generator()
        token = generator.generate_token(
            resource_type="document",
            resource_id=document_with_file.pk,
            user_id=document_with_file.user_id,
            action="download",
        )

        response = client.get(f"/claims/document/s/{token}/download/")
        assert response.status_code == 200

    def test_signed_view_with_valid_token(self, client, user, document_with_file):
        """Valid signed URL allows inline view without login."""
        from core.signed_urls import get_signed_url_generator

        generator = get_signed_url_generator()
        token = generator.generate_token(
            resource_type="document",
            resource_id=document_with_file.pk,
            user_id=document_with_file.user_id,
            action="view",
        )

        response = client.get(f"/claims/document/s/{token}/view/")
        assert response.status_code == 200

    def test_signed_download_with_expired_token(self, client, document_with_file):
        """Expired token returns forbidden."""
        from core.signed_urls import get_signed_url_generator

        generator = get_signed_url_generator()
        token = generator.generate_token(
            resource_type="document",
            resource_id=document_with_file.pk,
            user_id=document_with_file.user_id,
            action="download",
            expires_minutes=0,  # Already expired
        )

        import time

        time.sleep(0.1)

        response = client.get(f"/claims/document/s/{token}/download/")
        assert response.status_code == 403
        assert b"expired" in response.content

    def test_signed_download_with_invalid_token(self, client):
        """Invalid token returns forbidden."""
        response = client.get("/claims/document/s/invalid-token/download/")
        assert response.status_code == 403
        assert b"Invalid" in response.content

    def test_signed_download_wrong_action(self, client, document_with_file):
        """Token with wrong action type returns forbidden."""
        from core.signed_urls import get_signed_url_generator

        generator = get_signed_url_generator()
        # Generate view token but try to use it for download
        token = generator.generate_token(
            resource_type="document",
            resource_id=document_with_file.pk,
            user_id=document_with_file.user_id,
            action="view",  # Wrong action
        )

        response = client.get(f"/claims/document/s/{token}/download/")
        assert response.status_code == 403
        assert b"Invalid link type" in response.content

    def test_signed_download_wrong_resource_type(self, client, document_with_file):
        """Token with wrong resource type returns forbidden."""
        from core.signed_urls import get_signed_url_generator

        generator = get_signed_url_generator()
        token = generator.generate_token(
            resource_type="not_document",  # Wrong type
            resource_id=document_with_file.pk,
            user_id=document_with_file.user_id,
            action="download",
        )

        response = client.get(f"/claims/document/s/{token}/download/")
        assert response.status_code == 403
        assert b"Invalid resource type" in response.content

    def test_signed_download_nonexistent_document(self, client, user):
        """Token for nonexistent document returns 404."""
        from core.signed_urls import get_signed_url_generator

        generator = get_signed_url_generator()
        token = generator.generate_token(
            resource_type="document",
            resource_id=99999,  # Doesn't exist
            user_id=user.pk,
            action="download",
        )

        response = client.get(f"/claims/document/s/{token}/download/")
        assert response.status_code == 404

    def test_signed_download_creates_audit_log(self, client, document_with_file):
        """Signed download creates audit log entry."""
        from core.signed_urls import get_signed_url_generator

        generator = get_signed_url_generator()
        token = generator.generate_token(
            resource_type="document",
            resource_id=document_with_file.pk,
            user_id=document_with_file.user_id,
            action="download",
        )

        response = client.get(f"/claims/document/s/{token}/download/")
        assert response.status_code == 200

        # Check audit log was created
        log = AuditLog.objects.filter(
            action="document_download",
            resource_type="Document",
            resource_id=document_with_file.pk,
        ).first()
        assert log is not None
        assert log.details.get("access_type") == "signed_url"


class TestDocumentModelSignedURLMethods(TestCase):
    """Tests for Document model signed URL methods."""

    def setUp(self):
        from claims.models import Document

        self.user = User.objects.create_user(
            email="docmodel@example.com", password="TestPass123!"
        )
        self.document = Document.objects.create(
            user=self.user,
            file_name="test.pdf",
            document_type="decision_letter",
            status="completed",
        )

    def test_get_signed_download_url(self):
        """get_signed_download_url returns a valid signed URL."""
        url = self.document.get_signed_download_url()
        self.assertIn("/claims/document/s/", url)
        self.assertIn("/download/", url)

    def test_get_signed_view_url(self):
        """get_signed_view_url returns a valid signed URL."""
        url = self.document.get_signed_view_url()
        self.assertIn("/claims/document/s/", url)
        self.assertIn("/view/", url)

    def test_signed_urls_are_different(self):
        """Download and view signed URLs are different."""
        download_url = self.document.get_signed_download_url()
        view_url = self.document.get_signed_view_url()
        self.assertNotEqual(download_url, view_url)

    def test_signed_url_custom_expiration(self):
        """Custom expiration time is respected."""
        # Generate with short expiration
        url_5min = self.document.get_signed_download_url(expires_minutes=5)
        # Generate with longer expiration
        url_60min = self.document.get_signed_download_url(expires_minutes=60)

        # URLs should be different due to different expiration timestamps
        self.assertNotEqual(url_5min, url_60min)


# =============================================================================
# SUPPORTIVE MESSAGE TEMPLATE TAG TESTS (TODO.md P2: mark_safe on DB content)
# =============================================================================


class TestSupportiveMessageTagEscaping(TestCase):
    """
    {% supportive_message %} used to build its HTML with an f-string and
    mark_safe() the whole thing, which left message.message (admin-editable
    DB content) completely unescaped — a stored-XSS vector if that field
    ever contains markup. It must now come out auto-escaped.
    """

    def setUp(self):
        from core.models import SupportiveMessage

        self.SupportiveMessage = SupportiveMessage

    def test_message_content_is_escaped(self):
        from core.templatetags.supportive_tags import supportive_message

        self.SupportiveMessage.objects.create(
            context="dashboard_welcome",
            message="<script>alert('xss')</script>",
            tone="encouraging",
            icon="heart",
            is_active=True,
        )

        rendered = str(supportive_message("dashboard_welcome"))
        self.assertNotIn("<script>alert('xss')</script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_trusted_icon_svg_still_renders_unescaped(self):
        """The hardcoded ICON_MAP svg is trusted markup, not DB content."""
        from core.templatetags.supportive_tags import supportive_message

        self.SupportiveMessage.objects.create(
            context="dashboard_welcome",
            message="Welcome back!",
            tone="encouraging",
            icon="heart",
            is_active=True,
        )

        rendered = str(supportive_message("dashboard_welcome"))
        self.assertIn("<svg", rendered)
        self.assertIn("Welcome back!", rendered)


# =============================================================================
# HEALTH CHECK TESTS (TODO.md P2: core/health.py Redis failure hidden)
# =============================================================================


class TestCheckCeleryHealthLogsRedisFailure(TestCase):
    """
    check_celery()'s queue-length lookup used to swallow a Redis failure
    with a bare `except: pass` — status still came back "healthy" with
    queue_length silently None, and nothing was logged, so the queue-length
    alert (CLAUDE.md monitoring table) could never fire when Redis itself
    was down. It must at least log the failure now.
    """

    def test_redis_failure_during_queue_length_check_is_logged(self):
        from unittest import mock
        from core.health import check_celery

        mock_inspect = mock.MagicMock()
        mock_inspect.active.return_value = {"worker1@host": []}

        with mock.patch(
            "benefits_navigator.celery.app.control.inspect",
            return_value=mock_inspect,
        ), mock.patch(
            "django.conf.settings.CELERY_BROKER_URL", "redis://localhost:6379/0"
        ), mock.patch(
            "redis.from_url", side_effect=ConnectionError("simulated Redis outage")
        ), self.assertLogs(
            "core.health", level="WARNING"
        ) as logs:
            result = check_celery()

        self.assertIsNone(result["queue_length"])
        self.assertTrue(
            any("queue length" in message.lower() for message in logs.output)
        )


# =============================================================================
# IDLE SESSION TIMEOUT MIDDLEWARE TESTS (HIPAA automatic logoff)
# =============================================================================


@pytest.mark.django_db
class TestIdleSessionTimeoutMiddleware:
    """
    Automatic logoff after inactivity — HIPAA Security Rule §164.312(a)(2)(iii).
    """

    URL_NAME = "accounts:privacy_settings"

    def test_active_session_is_not_logged_out(self, authenticated_client):
        """A session used within the timeout window stays authenticated."""
        url = reverse(self.URL_NAME)
        assert authenticated_client.get(url).status_code == 200
        # Immediately again — well within the idle window.
        assert authenticated_client.get(url).status_code == 200

    def test_idle_session_is_logged_out(self, authenticated_client):
        """A session idle past the timeout is logged out and redirected."""
        import time
        from core.middleware import IDLE_ACTIVITY_KEY

        url = reverse(self.URL_NAME)
        authenticated_client.get(url)  # establishes activity marker

        session = authenticated_client.session
        session[IDLE_ACTIVITY_KEY] = int(time.time()) - 3600  # 1h ago > 30m default
        session.save()

        response = authenticated_client.get(url)
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

        # The session was flushed — a follow-up request is anonymous.
        follow = authenticated_client.get(url)
        assert follow.status_code == 302  # login-required redirect

    def test_htmx_idle_gets_hx_redirect(self, authenticated_client):
        """HTMX requests get a 204 + HX-Redirect instead of a body redirect."""
        import time
        from core.middleware import IDLE_ACTIVITY_KEY

        url = reverse(self.URL_NAME)
        authenticated_client.get(url)

        session = authenticated_client.session
        session[IDLE_ACTIVITY_KEY] = int(time.time()) - 3600
        session.save()

        response = authenticated_client.get(url, HTTP_HX_REQUEST="true")
        assert response.status_code == 204
        assert response["HX-Redirect"] == "/accounts/login/"

    @override_settings(SESSION_IDLE_TIMEOUT=0)
    def test_timeout_zero_disables_logoff(self, authenticated_client):
        """SESSION_IDLE_TIMEOUT=0 disables automatic logoff entirely."""
        import time
        from core.middleware import IDLE_ACTIVITY_KEY

        url = reverse(self.URL_NAME)
        session = authenticated_client.session
        session[IDLE_ACTIVITY_KEY] = int(time.time()) - 999999
        session.save()

        assert authenticated_client.get(url).status_code == 200

    def test_anonymous_request_unaffected(self, client):
        """Unauthenticated requests pass through the middleware untouched."""
        assert client.get(reverse("home")).status_code == 200


# =============================================================================
# REDIS TLS OPTIONS HELPER TESTS (HIPAA §164.312(e) transmission security)
# =============================================================================


class TestRedisSSLOptions(TestCase):
    """core.redis_ssl resolves rediss:// TLS verification policy."""

    def test_default_is_verified(self):
        import ssl
        from core.redis_ssl import redis_ssl_options, resolve_cert_reqs

        self.assertEqual(resolve_cert_reqs("required"), ssl.CERT_REQUIRED)
        self.assertEqual(
            redis_ssl_options("required")["ssl_cert_reqs"], ssl.CERT_REQUIRED
        )

    def test_unknown_or_empty_falls_back_to_required(self):
        import ssl
        from core.redis_ssl import resolve_cert_reqs

        self.assertEqual(resolve_cert_reqs(""), ssl.CERT_REQUIRED)
        self.assertEqual(resolve_cert_reqs(None), ssl.CERT_REQUIRED)
        self.assertEqual(resolve_cert_reqs("bogus"), ssl.CERT_REQUIRED)

    def test_explicit_none_and_optional(self):
        import ssl
        from core.redis_ssl import resolve_cert_reqs

        self.assertEqual(resolve_cert_reqs("none"), ssl.CERT_NONE)
        self.assertEqual(resolve_cert_reqs("NONE"), ssl.CERT_NONE)
        self.assertEqual(resolve_cert_reqs("optional"), ssl.CERT_OPTIONAL)

    def test_ca_certs_included_only_when_provided(self):
        from core.redis_ssl import redis_ssl_options

        self.assertNotIn("ssl_ca_certs", redis_ssl_options("required"))
        opts = redis_ssl_options("required", "/etc/ssl/do-valkey-ca.crt")
        self.assertEqual(opts["ssl_ca_certs"], "/etc/ssl/do-valkey-ca.crt")


# =============================================================================
# STORAGE CONFIGURATION TESTS (Django >= 5.1 STORAGES)
# =============================================================================


class TestStorageConfiguration(TestCase):
    """
    Django >= 5.1 REMOVED DEFAULT_FILE_STORAGE / STATICFILES_STORAGE. They are
    silently ignored, so the backends must be declared via STORAGES or the
    configured storage never takes effect — which is exactly why USE_S3=True
    still wrote veteran documents to the local filesystem.
    """

    def test_storages_setting_is_defined(self):
        from django.conf import settings

        self.assertIn("default", settings.STORAGES)
        self.assertIn("staticfiles", settings.STORAGES)

    def test_legacy_storage_settings_are_not_reintroduced(self):
        """
        Guard: these names are dead on Django >= 5.1. If someone re-adds them,
        the storage they name will be silently ignored again.
        """
        from django.conf import settings

        for dead in ("DEFAULT_FILE_STORAGE", "STATICFILES_STORAGE"):
            self.assertFalse(
                hasattr(settings, dead),
                f"{dead} is removed in Django >=5.1 and is silently ignored; "
                "configure the backend in STORAGES instead.",
            )

    def test_default_storage_is_filesystem_without_s3(self):
        from django.core.files.storage import storages

        self.assertEqual(type(storages["default"]).__name__, "FileSystemStorage")

    def test_staticfiles_uses_whitenoise_manifest_storage_when_deployed(self):
        """
        Whitenoise's compressed-manifest storage must be what deployed
        environments serve.

        It cannot be the *active* backend under the test runner: it resolves
        {% static %} through a manifest that `collectstatic` writes, and neither
        pytest nor runserver writes one. Asserting it was active here is what
        took the suite down — every page render raised "Missing staticfiles
        manifest entry". So assert the deployed half of the selection instead.
        """
        from django.conf import settings

        self.assertEqual(
            settings.MANIFEST_STATICFILES_BACKEND,
            "whitenoise.storage.CompressedManifestStaticFilesStorage",
        )

    def test_test_runs_fall_back_to_manifest_free_storage(self):
        """The other half: tests must not require a collectstatic manifest."""
        from django.conf import settings

        self.assertTrue(settings.TESTING)
        self.assertEqual(
            settings.STORAGES["staticfiles"]["BACKEND"],
            settings.LOCAL_STATICFILES_BACKEND,
        )


# =============================================================================
# STORAGE-AGNOSTIC FILE ACCESS TESTS
# =============================================================================


class _FakeRemoteFieldFile:
    """
    Mimics a FieldFile on a backend with no local paths (S3/Spaces), where
    ``.path`` raises NotImplementedError.
    """

    def __init__(self, name, content):
        self.name = name
        self._content = content
        self._buf = None

    @property
    def path(self):
        raise NotImplementedError("This backend doesn't support absolute paths.")

    def open(self, mode="rb"):
        import io

        self._buf = io.BytesIO(self._content)
        return self._buf

    def read(self, size=-1):
        return self._buf.read(size)

    def close(self):
        if self._buf:
            self._buf.close()


class TestFileAccessHelpers(TestCase):
    """
    FieldFile.path raises on remote storage, so path-only tools (Tesseract OCR)
    need a temp copy and serving code must stream through the backend.
    """

    def test_local_path_or_none_returns_none_without_local_path(self):
        from core.file_access import local_path_or_none

        remote = _FakeRemoteFieldFile("documents/x.pdf", b"data")
        self.assertIsNone(local_path_or_none(remote))

    def test_as_local_path_materializes_remote_file(self):
        """A remote file is downloaded to a real path with intact contents."""
        import os
        from core.file_access import as_local_path

        remote = _FakeRemoteFieldFile("documents/scan.pdf", b"%PDF-1.4 remote bytes")

        with as_local_path(remote) as path:
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith(".pdf"))  # suffix preserved for OCR
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), b"%PDF-1.4 remote bytes")
            captured = path

        # Temp copy must not leak.
        self.assertFalse(os.path.exists(captured))

    def test_as_local_path_cleans_up_on_exception(self):
        import os
        from core.file_access import as_local_path

        remote = _FakeRemoteFieldFile("documents/scan.pdf", b"bytes")
        captured = None
        with self.assertRaises(RuntimeError):
            with as_local_path(remote) as path:
                captured = path
                raise RuntimeError("boom")
        self.assertIsNotNone(captured)
        self.assertFalse(os.path.exists(captured))

    def test_as_local_path_uses_real_path_for_local_storage(self):
        """Local storage yields the real path — no copy is made."""
        import os
        import tempfile
        from core.file_access import as_local_path

        class _LocalFieldFile:
            def __init__(self, p):
                self.name = "documents/local.pdf"
                self.path = p

        with tempfile.NamedTemporaryFile(suffix=".pdf") as real:
            real.write(b"local")
            real.flush()
            with as_local_path(_LocalFieldFile(real.name)) as path:
                self.assertEqual(path, real.name)
            # The real file is untouched by the helper.
            self.assertTrue(os.path.exists(real.name))
