"""A dead scheduler must be visible in the health output.

Starting Beat is half the fix. The other half is that its absence was
*undetectable*: the deployment ran for months with no scheduler, and every
signal the team had — HTTP checks, worker logs, the dashboard — stayed green
while account purges and retention runs silently never happened.

``check_scheduler`` reads ``PeriodicTask.last_run_at``, which the database
scheduler stamps on each dispatch. If the newest one is stale, Beat is not
running, and ``/health/?full=1`` says so instead of reporting healthy.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.health import check_scheduler, get_full_health_status


@pytest.fixture
def periodic_task(db):
    """A minimal enabled PeriodicTask to hang last_run_at off."""
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=5, period=IntervalSchedule.MINUTES
    )
    return PeriodicTask.objects.create(
        name="record-health-metrics",
        task="core.tasks.record_health_metrics",
        interval=schedule,
        enabled=True,
    )


@pytest.mark.django_db
class TestSchedulerHealth:
    def test_recent_dispatch_is_healthy(self, periodic_task):
        periodic_task.last_run_at = timezone.now() - timedelta(minutes=3)
        periodic_task.save()

        result = check_scheduler()

        assert result["status"] == "healthy"
        assert result["last_task"] == "record-health-metrics"

    def test_a_stale_dispatch_is_unhealthy(self, periodic_task):
        """Beat died an hour ago; the most frequent task runs every 5 minutes."""
        periodic_task.last_run_at = timezone.now() - timedelta(hours=1)
        periodic_task.save()

        result = check_scheduler()

        assert result["status"] == "unhealthy"
        assert "not running" in result["message"]

    def test_never_having_run_is_unhealthy_not_healthy(self, periodic_task):
        """
        The exact production state: tasks registered, Beat never deployed.
        This must not read as 'fine because nothing is overdue'.
        """
        assert periodic_task.last_run_at is None

        result = check_scheduler()

        assert result["status"] == "unhealthy"
        assert "never" in result["message"].lower()

    def test_no_registered_tasks_is_unknown_rather_than_healthy(self, db):
        """
        Before Beat's first sync there are no PeriodicTask rows at all. That is
        genuinely 'cannot tell', and a check that guessed 'healthy' here would
        recreate the silence this exists to break.
        """
        result = check_scheduler()

        assert result["status"] == "unknown"

    def test_the_full_health_payload_includes_the_scheduler(self, periodic_task):
        periodic_task.last_run_at = timezone.now() - timedelta(hours=1)
        periodic_task.save()

        health = get_full_health_status()

        assert "scheduler" in health["checks"]
        assert health["status"] == "unhealthy"
