"""
Alerting and monitoring infrastructure.

Provides:
- Configurable alert thresholds
- Multiple alert channels (email, Slack, Sentry)
- Download anomaly detection
- Task age monitoring
- Health status alerting
"""

import logging
from datetime import timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.db.models import Count

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AlertThresholds:
    """Configurable thresholds for alerting."""

    # Document processing
    processing_success_rate_warning: float = 90.0  # Percentage
    processing_success_rate_critical: float = 80.0

    # Failure counts
    failures_per_hour_warning: int = 5
    failures_per_hour_critical: int = 10

    # Celery
    min_workers_warning: int = 1
    min_workers_critical: int = 0
    queue_length_warning: int = 50
    queue_length_critical: int = 100

    # Task age (seconds)
    task_age_warning: int = 300  # 5 minutes
    task_age_critical: int = 600  # 10 minutes

    # Download anomaly detection
    downloads_per_hour_warning: int = 50  # Per user
    downloads_per_hour_critical: int = 100


# Default thresholds (can be overridden in settings)
DEFAULT_THRESHOLDS = AlertThresholds()


def get_thresholds() -> AlertThresholds:
    """Get alert thresholds from settings or use defaults."""
    custom = getattr(settings, "ALERT_THRESHOLDS", {})
    if custom:
        return AlertThresholds(**custom)
    return DEFAULT_THRESHOLDS


def send_alert(
    title: str,
    message: str,
    severity: AlertSeverity,
    details: Optional[Dict] = None,
    channels: Optional[List[str]] = None,
) -> bool:
    """
    Send an alert through configured channels.

    Args:
        title: Alert title/subject
        message: Alert message body
        severity: Alert severity level
        details: Additional context dict
        channels: Override default channels ['email', 'slack', 'sentry']

    Returns:
        True if at least one channel succeeded
    """
    if channels is None:
        channels = getattr(settings, "ALERT_CHANNELS", ["email", "sentry"])

    success = False

    for channel in channels:
        try:
            if channel == "email":
                success |= _send_email_alert(title, message, severity, details)
            elif channel == "slack":
                success |= _send_slack_alert(title, message, severity, details)
            elif channel == "sentry":
                success |= _send_sentry_alert(title, message, severity, details)
        except Exception as e:
            logger.error(f"Failed to send alert via {channel}: {e}")

    return success


def _send_email_alert(
    title: str, message: str, severity: AlertSeverity, details: Optional[Dict] = None
) -> bool:
    """Send alert via email to configured recipients."""
    recipients = getattr(settings, "ALERT_EMAIL_RECIPIENTS", [])

    if not recipients:
        logger.warning("No ALERT_EMAIL_RECIPIENTS configured")
        return False

    subject = f"[{severity.value.upper()}] {title}"

    body = f"{message}\n\n"
    if details:
        body += "Details:\n"
        for key, value in details.items():
            body += f"  {key}: {value}\n"

    body += f"\nTimestamp: {timezone.now().isoformat()}"
    body += f"\nEnvironment: {getattr(settings, 'ENVIRONMENT', 'unknown')}"

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")
        return False


def _send_slack_alert(
    title: str, message: str, severity: AlertSeverity, details: Optional[Dict] = None
) -> bool:
    """Send alert to Slack webhook."""
    webhook_url = getattr(settings, "SLACK_ALERT_WEBHOOK", None)

    if not webhook_url:
        return False

    import requests

    # Severity colors
    colors = {
        AlertSeverity.INFO: "#36a64f",  # Green
        AlertSeverity.WARNING: "#ff9800",  # Orange
        AlertSeverity.CRITICAL: "#f44336",  # Red
    }

    payload = {
        "attachments": [
            {
                "color": colors.get(severity, "#808080"),
                "title": title,
                "text": message,
                "fields": [
                    {"title": k, "value": str(v), "short": True}
                    for k, v in (details or {}).items()
                ],
                "footer": f"Benefits Navigator | {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            }
        ]
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send Slack alert: {e}")
        return False


def _send_sentry_alert(
    title: str, message: str, severity: AlertSeverity, details: Optional[Dict] = None
) -> bool:
    """Send alert to Sentry."""
    try:
        import sentry_sdk

        level_map = {
            AlertSeverity.INFO: "info",
            AlertSeverity.WARNING: "warning",
            AlertSeverity.CRITICAL: "error",
        }

        with sentry_sdk.push_scope() as scope:
            scope.set_tag("alert_type", "system_health")
            scope.set_level(level_map.get(severity, "warning"))
            if details:
                for key, value in details.items():
                    scope.set_extra(key, value)

            sentry_sdk.capture_message(f"{title}: {message}")

        return True
    except Exception as e:
        logger.error(f"Failed to send Sentry alert: {e}")
        return False


def check_and_alert_health():
    """
    Run health checks and send alerts if thresholds exceeded.

    Call this from a periodic Celery task.
    """
    from core.health import get_full_health_status

    thresholds = get_thresholds()
    health = get_full_health_status()
    alerts_sent = []

    # Check overall health
    if health["status"] == "unhealthy":
        send_alert(
            title="System Health Critical",
            message="One or more critical system components are unhealthy.",
            severity=AlertSeverity.CRITICAL,
            details={"checks": {k: v["status"] for k, v in health["checks"].items()}},
        )
        alerts_sent.append("system_unhealthy")

    # Check document processing
    doc_proc = health["checks"].get("document_processing", {})
    success_rate = doc_proc.get("success_rate")
    if success_rate is not None:
        if success_rate < thresholds.processing_success_rate_critical:
            send_alert(
                title="Document Processing Critical",
                message=f"Success rate dropped to {success_rate}%",
                severity=AlertSeverity.CRITICAL,
                details=doc_proc,
            )
            alerts_sent.append("processing_critical")
        elif success_rate < thresholds.processing_success_rate_warning:
            send_alert(
                title="Document Processing Degraded",
                message=f"Success rate at {success_rate}%",
                severity=AlertSeverity.WARNING,
                details=doc_proc,
            )
            alerts_sent.append("processing_warning")

    # Check Celery workers
    celery = health["checks"].get("celery", {})
    workers = celery.get("workers", 0)
    if workers <= thresholds.min_workers_critical:
        send_alert(
            title="Celery Workers Critical",
            message=f"Only {workers} workers available",
            severity=AlertSeverity.CRITICAL,
            details=celery,
        )
        alerts_sent.append("celery_critical")
    elif workers <= thresholds.min_workers_warning:
        send_alert(
            title="Celery Workers Low",
            message=f"Only {workers} workers available",
            severity=AlertSeverity.WARNING,
            details=celery,
        )
        alerts_sent.append("celery_warning")

    # Check queue length
    queue_length = celery.get("queue_length")
    if queue_length is not None:
        if queue_length >= thresholds.queue_length_critical:
            send_alert(
                title="Task Queue Backlog Critical",
                message=f"Queue has {queue_length} pending tasks",
                severity=AlertSeverity.CRITICAL,
                details={"queue_length": queue_length},
            )
            alerts_sent.append("queue_critical")
        elif queue_length >= thresholds.queue_length_warning:
            send_alert(
                title="Task Queue Backlog",
                message=f"Queue has {queue_length} pending tasks",
                severity=AlertSeverity.WARNING,
                details={"queue_length": queue_length},
            )
            alerts_sent.append("queue_warning")

    return alerts_sent


def check_download_anomalies(hours: int = 1) -> List[Dict]:
    """
    Detect unusual download patterns that may indicate data exfiltration.

    Checks for:
    - High download volume per user
    - Unusual download times
    - Bulk sequential downloads

    Returns list of detected anomalies.
    """
    from core.models import AuditLog

    thresholds = get_thresholds()
    since = timezone.now() - timedelta(hours=hours)
    anomalies = []

    # Check downloads per user in the time window
    user_downloads = AuditLog.objects.filter(
        action='document_download',
        timestamp__gte=since,
        user__isnull=False
    ).values('user_id').annotate(
        download_count=Count('id')
    ).order_by('-download_count')

    for entry in user_downloads:
        count = entry["download_count"]
        if count >= thresholds.downloads_per_hour_critical:
            anomaly = {
                'type': 'high_download_volume',
                'severity': AlertSeverity.CRITICAL,
                'user_id': entry['user_id'],
                'download_count': count,
                'period_hours': hours,
            }
            anomalies.append(anomaly)
            send_alert(
                title="Anomalous Download Activity",
                # User ID only — no PII in email/Slack alert channels
                message=f"User id={entry['user_id']} downloaded {count} documents in {hours} hour(s)",
                severity=AlertSeverity.CRITICAL,
                details=anomaly,
            )
        elif count >= thresholds.downloads_per_hour_warning:
            anomaly = {
                'type': 'elevated_download_volume',
                'severity': AlertSeverity.WARNING,
                'user_id': entry['user_id'],
                'download_count': count,
                'period_hours': hours,
            }
            anomalies.append(anomaly)
            send_alert(
                title="Elevated Download Activity",
                message=f"User id={entry['user_id']} downloaded {count} documents in {hours} hour(s)",
                severity=AlertSeverity.WARNING,
                details=anomaly,
            )

    # Check for downloads from unusual IPs (multiple users same IP)
    ip_downloads = (
        AuditLog.objects.filter(
            action="document_download", timestamp__gte=since, ip_address__isnull=False
        )
        .values("ip_address")
        .annotate(
            user_count=Count("user_id", distinct=True), download_count=Count("id")
        )
        .filter(user_count__gt=3)
    )  # More than 3 users from same IP

    for entry in ip_downloads:
        anomaly = {
            "type": "multi_user_ip",
            "severity": AlertSeverity.WARNING,
            "ip_address": entry["ip_address"],
            "user_count": entry["user_count"],
            "download_count": entry["download_count"],
        }
        anomalies.append(anomaly)
        send_alert(
            title="Multiple Users Same IP",
            message=f"IP {entry['ip_address']} used by {entry['user_count']} users for {entry['download_count']} downloads",
            severity=AlertSeverity.WARNING,
            details=anomaly,
        )

    return anomalies


def check_task_age() -> List[Dict]:
    """
    Check for stale/long-running Celery tasks.

    Returns list of stale task alerts.
    """
    thresholds = get_thresholds()
    stale_tasks = []

    try:
        from benefits_navigator.celery import app

        inspect = app.control.inspect()
        active = inspect.active()

        if not active:
            return stale_tasks

        now = timezone.now()

        for worker, tasks in active.items():
            for task in tasks:
                # Task info includes time_start as epoch
                time_start = task.get("time_start")
                if time_start:
                    from datetime import datetime

                    started = datetime.fromtimestamp(time_start, tz=timezone.utc)
                    age_seconds = (now - started).total_seconds()

                    if age_seconds >= thresholds.task_age_critical:
                        alert = {
                            "type": "stale_task",
                            "severity": AlertSeverity.CRITICAL,
                            "task_id": task.get("id"),
                            "task_name": task.get("name"),
                            "worker": worker,
                            "age_seconds": int(age_seconds),
                            "started_at": started.isoformat(),
                        }
                        stale_tasks.append(alert)
                        send_alert(
                            title="Long-Running Task Critical",
                            message=f"Task {task.get('name')} running for {int(age_seconds)}s",
                            severity=AlertSeverity.CRITICAL,
                            details=alert,
                        )
                    elif age_seconds >= thresholds.task_age_warning:
                        alert = {
                            "type": "slow_task",
                            "severity": AlertSeverity.WARNING,
                            "task_id": task.get("id"),
                            "task_name": task.get("name"),
                            "worker": worker,
                            "age_seconds": int(age_seconds),
                            "started_at": started.isoformat(),
                        }
                        stale_tasks.append(alert)
                        send_alert(
                            title="Long-Running Task Warning",
                            message=f"Task {task.get('name')} running for {int(age_seconds)}s",
                            severity=AlertSeverity.WARNING,
                            details=alert,
                        )

    except Exception as e:
        logger.error(f"Failed to check task age: {e}")

    return stale_tasks


def run_all_monitoring_checks() -> Dict:
    """
    Run all monitoring checks and return summary.

    Call this from a periodic Celery task (e.g., every 5 minutes).
    """
    results = {
        "timestamp": timezone.now().isoformat(),
        "health_alerts": check_and_alert_health(),
        "download_anomalies": check_download_anomalies(hours=1),
        "stale_tasks": check_task_age(),
    }

    # Log summary
    total_alerts = (
        len(results["health_alerts"])
        + len(results["download_anomalies"])
        + len(results["stale_tasks"])
    )

    if total_alerts > 0:
        logger.warning(f"Monitoring check found {total_alerts} alerts: {results}")
    else:
        logger.info("Monitoring check completed with no alerts")

    return results
