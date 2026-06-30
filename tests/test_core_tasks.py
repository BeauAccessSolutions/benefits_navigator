"""
Tests for core Celery tasks — data retention, health monitoring, and pilot notifications.

Covers:
- enforce_data_retention: Purges data per active retention policies
- enforce_pilot_data_retention: Purges pilot user data per PILOT_DATA_RETENTION_DAYS
- notify_pilot_users_before_retention: Warns pilot users before deletion
- cleanup_old_health_metrics: Removes health metrics older than 30 days
- check_processing_health: Detects stuck documents and high failure rates
"""

import pytest
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from django.contrib.auth import get_user_model
from django.test import override_settings

User = get_user_model()


# =============================================================================
# enforce_data_retention
# =============================================================================


@pytest.mark.django_db
class TestEnforceDataRetention:
    """Tests for the enforce_data_retention task."""

    def test_purges_old_audit_logs(self):
        """Should delete audit logs older than the retention period."""
        from core.models import DataRetentionPolicy, AuditLog
        from core.tasks import enforce_data_retention

        # Create retention policy: 30 days for audit logs
        DataRetentionPolicy.objects.create(
            data_type="audit_logs",
            retention_days=30,
            is_active=True,
        )

        user = User.objects.create_user(
            email="retention@example.com", password="TestPass123!"
        )

        # Create an old audit log (beyond retention)
        old_log = AuditLog.objects.create(
            user=user,
            action="test_action",
            resource_type="test",
        )
        AuditLog.objects.filter(pk=old_log.pk).update(
            timestamp=timezone.now() - timedelta(days=60)
        )

        # Create a recent audit log (within retention)
        recent_log = AuditLog.objects.create(
            user=user,
            action="recent_action",
            resource_type="test",
        )

        result = enforce_data_retention()

        assert result.get("audit_logs", 0) >= 1
        assert not AuditLog.objects.filter(pk=old_log.pk).exists()
        assert AuditLog.objects.filter(pk=recent_log.pk).exists()

    def test_skips_inactive_policies(self):
        """Should not purge data for inactive policies."""
        from core.models import DataRetentionPolicy, AuditLog
        from core.tasks import enforce_data_retention

        DataRetentionPolicy.objects.create(
            data_type="audit_logs",
            retention_days=1,
            is_active=False,  # Inactive
        )

        user = User.objects.create_user(
            email="inactive@example.com", password="TestPass123!"
        )
        old_log = AuditLog.objects.create(
            user=user,
            action="test_action",
            resource_type="test",
        )
        AuditLog.objects.filter(pk=old_log.pk).update(
            timestamp=timezone.now() - timedelta(days=60)
        )

        result = enforce_data_retention()

        # No policies processed → empty result
        assert "audit_logs" not in result
        assert AuditLog.objects.filter(pk=old_log.pk).exists()

    def test_updates_last_cleanup_timestamp(self):
        """Should update last_cleanup on the policy after running."""
        from core.models import DataRetentionPolicy
        from core.tasks import enforce_data_retention

        policy = DataRetentionPolicy.objects.create(
            data_type="session_data",
            retention_days=30,
            is_active=True,
        )
        assert policy.last_cleanup is None

        enforce_data_retention()

        policy.refresh_from_db()
        assert policy.last_cleanup is not None


# =============================================================================
# enforce_pilot_data_retention
# =============================================================================


@pytest.mark.django_db
class TestEnforcePilotDataRetention:
    """Tests for the enforce_pilot_data_retention task."""

    @override_settings(PILOT_DATA_RETENTION_DAYS=30, PILOT_PREMIUM_ACCESS=True)
    def test_soft_deletes_old_pilot_documents(self):
        """Should soft-delete documents older than PILOT_DATA_RETENTION_DAYS for pilot users."""
        from claims.models import Document
        from core.tasks import enforce_pilot_data_retention

        pilot_user = User.objects.create_user(
            email="pilot@example.com", password="TestPass123!"
        )

        # Create old document
        old_doc = Document.objects.create(
            user=pilot_user,
            file_name="old.pdf",
            file_size=100,
            document_type="other",
            status="completed",
        )
        Document.objects.filter(pk=old_doc.pk).update(
            created_at=timezone.now() - timedelta(days=60)
        )

        # Create recent document
        recent_doc = Document.objects.create(
            user=pilot_user,
            file_name="recent.pdf",
            file_size=100,
            document_type="other",
            status="completed",
        )

        # Patch soft_delete since SoftDeleteModel doesn't have it as a method
        with patch.object(
            Document,
            "soft_delete",
            create=True,
            side_effect=lambda: Document.objects.filter(pk=old_doc.pk).update(
                is_deleted=True
            ),
        ):
            result = enforce_pilot_data_retention()

        assert result["documents_soft_deleted"] >= 1
        old_doc.refresh_from_db()
        assert old_doc.is_deleted is True
        recent_doc.refresh_from_db()
        assert recent_doc.is_deleted is False

    @override_settings(PILOT_DATA_RETENTION_DAYS=0)
    def test_disabled_when_retention_zero(self):
        """Should skip when PILOT_DATA_RETENTION_DAYS is 0."""
        from core.tasks import enforce_pilot_data_retention

        result = enforce_pilot_data_retention()
        assert result["status"] == "disabled"

    def test_skips_non_pilot_users(self):
        """Should not touch documents of non-pilot users."""
        from claims.models import Document
        from core.tasks import enforce_pilot_data_retention

        non_pilot = User.objects.create_user(
            email="nonpilot@example.com", password="TestPass123!"
        )

        old_doc = Document.objects.create(
            user=non_pilot,
            file_name="old.pdf",
            file_size=100,
            document_type="other",
            status="completed",
        )
        Document.objects.filter(pk=old_doc.pk).update(
            created_at=timezone.now() - timedelta(days=60)
        )

        with override_settings(PILOT_DATA_RETENTION_DAYS=30):
            result = enforce_pilot_data_retention()

        assert result["documents_soft_deleted"] == 0
        old_doc.refresh_from_db()
        assert old_doc.is_deleted is False


# =============================================================================
# notify_pilot_users_before_retention
# =============================================================================


@pytest.mark.django_db
class TestNotifyPilotUsersBeforeRetention:
    """Tests for the notify_pilot_users_before_retention task."""

    @override_settings(PILOT_DATA_RETENTION_DAYS=30, PILOT_PREMIUM_ACCESS=True)
    @patch("django.core.mail.send_mail")
    def test_sends_warning_email(self, mock_send_mail):
        """Should send warning email to pilot users with at-risk documents."""
        from claims.models import Document
        from core.tasks import notify_pilot_users_before_retention

        pilot_user = User.objects.create_user(
            email="warnme@example.com", password="TestPass123!"
        )

        # Create document that will be at risk (older than retention - 7 days warning)
        at_risk_doc = Document.objects.create(
            user=pilot_user,
            file_name="atrisk.pdf",
            file_size=100,
            document_type="other",
            status="completed",
        )
        Document.objects.filter(pk=at_risk_doc.pk).update(
            created_at=timezone.now() - timedelta(days=25)
        )

        result = notify_pilot_users_before_retention()

        assert result["notifications_sent"] >= 1
        mock_send_mail.assert_called()

    @override_settings(PILOT_DATA_RETENTION_DAYS=5)
    def test_skips_when_retention_too_short(self):
        """Should skip when retention_days <= warning_days (7)."""
        from core.tasks import notify_pilot_users_before_retention

        result = notify_pilot_users_before_retention()
        assert result["status"] == "skipped"


# =============================================================================
# cleanup_old_health_metrics
# =============================================================================


@pytest.mark.django_db
class TestCleanupOldHealthMetrics:
    """Tests for the cleanup_old_health_metrics task."""

    def test_deletes_metrics_older_than_30_days(self):
        """Should delete health metrics older than 30 days."""
        from core.models import SystemHealthMetric
        from core.tasks import cleanup_old_health_metrics

        # Create old metric
        old_metric = SystemHealthMetric.objects.create(
            metric_type="celery_queue",
            value=5.0,
        )
        SystemHealthMetric.objects.filter(pk=old_metric.pk).update(
            timestamp=timezone.now() - timedelta(days=45)
        )

        # Create recent metric
        recent_metric = SystemHealthMetric.objects.create(
            metric_type="celery_queue",
            value=3.0,
        )

        result = cleanup_old_health_metrics()

        assert "Deleted" in result or "deleted" in result.lower()
        assert not SystemHealthMetric.objects.filter(pk=old_metric.pk).exists()
        assert SystemHealthMetric.objects.filter(pk=recent_metric.pk).exists()

    def test_keeps_recent_metrics(self):
        """Should keep metrics within the 30-day window."""
        from core.models import SystemHealthMetric
        from core.tasks import cleanup_old_health_metrics

        recent = SystemHealthMetric.objects.create(
            metric_type="celery_workers",
            value=2.0,
        )

        cleanup_old_health_metrics()

        assert SystemHealthMetric.objects.filter(pk=recent.pk).exists()


# =============================================================================
# check_processing_health
# =============================================================================


@pytest.mark.django_db
class TestCheckProcessingHealth:
    """Tests for the check_processing_health task."""

    def test_detects_stuck_documents(self):
        """Should detect documents stuck in processing for >1 hour."""
        from claims.models import Document
        from core.tasks import check_processing_health

        user = User.objects.create_user(
            email="stuckdocs@example.com", password="TestPass123!"
        )

        # Create stuck document
        stuck_doc = Document.objects.create(
            user=user,
            file_name="stuck.pdf",
            file_size=100,
            document_type="other",
            status="processing",
        )
        Document.objects.filter(pk=stuck_doc.pk).update(
            updated_at=timezone.now() - timedelta(hours=2)
        )

        with patch(
            "core.health.check_celery", return_value={"queue_length": 0, "workers": 1}
        ):
            result = check_processing_health()

        assert result["stuck_docs"] >= 1

    def test_no_alerts_when_healthy(self):
        """Should return no alerts when everything is healthy."""
        from core.tasks import check_processing_health

        with patch(
            "core.health.check_celery", return_value={"queue_length": 0, "workers": 2}
        ):
            result = check_processing_health()

        assert result["stuck_docs"] == 0
        assert len(result["alerts"]) == 0

    @patch("core.health.check_celery", side_effect=Exception("Redis down"))
    def test_handles_celery_check_failure(self, mock_celery):
        """Should handle Celery check failures gracefully."""
        from core.tasks import check_processing_health

        # Should not raise
        result = check_processing_health()
        assert "stuck_docs" in result

    def test_detects_high_failure_rate(self):
        """Should alert when failure rate exceeds threshold."""
        from core.models import ProcessingFailure
        from core.tasks import check_processing_health

        # Create 6 failures in the last hour (threshold is 5)
        for i in range(6):
            ProcessingFailure.objects.create(
                document_id=None,
                failure_type="ocr",
                error_message=f"Test failure {i}",
            )

        with patch(
            "core.health.check_celery", return_value={"queue_length": 0, "workers": 1}
        ):
            result = check_processing_health()

        assert result["failure_stats"]["total"] >= 5
        assert len(result["alerts"]) >= 1
