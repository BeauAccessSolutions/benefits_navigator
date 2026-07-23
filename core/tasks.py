"""
Celery tasks for core app - data retention enforcement, maintenance, and notifications.
"""

import logging
from datetime import timedelta, date

from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(acks_late=True)
def enforce_data_retention():
    """
    Periodic task to enforce data retention policies.

    Checks DataRetentionPolicy records and purges expired data accordingly.
    Should be scheduled via Celery Beat (e.g., daily at 2 AM).
    """
    from .models import DataRetentionPolicy

    policies = DataRetentionPolicy.objects.filter(is_active=True, retention_days__gt=0)
    results = {}

    for policy in policies:
        try:
            cutoff_date = timezone.now() - timedelta(days=policy.retention_days)
            deleted_count = 0

            if policy.data_type == "audit_logs":
                deleted_count = _purge_audit_logs(cutoff_date)
            elif policy.data_type == "documents":
                deleted_count = _purge_old_documents(cutoff_date)
            elif policy.data_type == "analyses":
                deleted_count = _purge_old_analyses(cutoff_date)
            elif policy.data_type == "session_data":
                deleted_count = _purge_session_data(cutoff_date)

            # Update last cleanup timestamp
            policy.last_cleanup = timezone.now()
            policy.save(update_fields=["last_cleanup"])

            results[policy.data_type] = deleted_count
            logger.info(
                f"Data retention: purged {deleted_count} {policy.data_type} "
                f"older than {policy.retention_days} days"
            )

        except Exception as e:
            logger.error(f"Data retention failed for {policy.data_type}: {e}")
            results[policy.data_type] = f"Error: {e}"

    return results


def _purge_audit_logs(cutoff_date):
    """Purge audit logs older than cutoff date."""
    from .models import AuditLog

    old_logs = AuditLog.objects.filter(timestamp__lt=cutoff_date)
    count = old_logs.count()
    old_logs.delete()
    return count


def _purge_old_documents(cutoff_date):
    """
    Purge soft-deleted documents older than cutoff date.
    Note: This only handles documents that are already soft-deleted.
    """
    from claims.models import Document

    # Only purge documents that were soft-deleted before the cutoff
    old_docs = Document.objects.filter(is_deleted=True, deleted_at__lt=cutoff_date)
    count = old_docs.count()

    for doc in old_docs:
        try:
            # Delete file from storage
            if doc.file:
                doc.file.delete(save=False)
            doc.hard_delete()
        except Exception as e:
            logger.error(f"Failed to purge document {doc.id}: {e}")

    return count


def _purge_old_analyses(cutoff_date):
    """Purge old AI analysis records."""
    try:
        from agents.models import (
            AgentInteraction,
            DecisionLetterAnalysis,
            DenialDecoding,
        )

        # Delete old denial decodings first (depends on analysis)
        old_decodings = DenialDecoding.objects.filter(
            analysis__created_at__lt=cutoff_date
        )
        decoding_count = old_decodings.count()
        old_decodings.delete()

        # Delete old analyses
        old_analyses = DecisionLetterAnalysis.objects.filter(created_at__lt=cutoff_date)
        analysis_count = old_analyses.count()
        old_analyses.delete()

        # Delete old agent interactions
        old_interactions = AgentInteraction.objects.filter(created_at__lt=cutoff_date)
        interaction_count = old_interactions.count()
        old_interactions.delete()

        return decoding_count + analysis_count + interaction_count

    except ImportError:
        logger.warning("agents app not available for analysis purge")
        return 0


def _purge_session_data(cutoff_date):
    """Purge expired session data."""
    from django.contrib.sessions.models import Session

    # Django sessions have an expire_date field
    old_sessions = Session.objects.filter(expire_date__lt=cutoff_date)
    count = old_sessions.count()
    old_sessions.delete()
    return count


@shared_task(acks_late=True)
def create_default_retention_policies():
    """
    Create default data retention policies if they don't exist.
    Run this once during initial setup.
    """
    from .models import DataRetentionPolicy

    defaults = [
        {
            "data_type": "audit_logs",
            "retention_days": 365,  # 1 year
            "description": "Security audit logs retained for compliance",
        },
        {
            "data_type": "documents",
            "retention_days": 90,  # 90 days after soft delete
            "description": "Soft-deleted documents purged after 90 days",
        },
        {
            "data_type": "analyses",
            "retention_days": 180,  # 6 months
            "description": "AI analysis results retained for 6 months",
        },
        {
            "data_type": "session_data",
            "retention_days": 30,  # 30 days
            "description": "Expired sessions cleaned up after 30 days",
        },
    ]

    created = 0
    for policy_data in defaults:
        policy, was_created = DataRetentionPolicy.objects.get_or_create(
            data_type=policy_data["data_type"],
            defaults={
                "retention_days": policy_data["retention_days"],
                "description": policy_data["description"],
                "is_active": True,
            },
        )
        if was_created:
            created += 1
            logger.info(f"Created retention policy: {policy_data['data_type']}")

    return f"Created {created} new retention policies"


# =============================================================================
# EMAIL NOTIFICATION TASKS
# =============================================================================


@shared_task(acks_late=True)
def send_deadline_reminders():
    """
    Send email reminders for upcoming deadlines.

    Checks all users with upcoming deadlines and sends reminder emails
    based on their notification preferences.

    Should be scheduled via Celery Beat (e.g., daily at 9 AM).
    """
    from .models import Deadline
    from accounts.models import NotificationPreferences

    today = date.today()
    reminders_sent = 0
    errors = []

    # Get all incomplete deadlines that haven't had reminders sent
    upcoming_deadlines = Deadline.objects.filter(
        is_completed=False,
        reminder_sent=False,
        deadline_date__gte=today,
    ).select_related("user", "claim", "appeal")

    for deadline in upcoming_deadlines:
        try:
            # Get user's notification preferences
            try:
                prefs = deadline.user.notification_preferences
            except NotificationPreferences.DoesNotExist:
                # Create default preferences if they don't exist
                prefs = NotificationPreferences.objects.create(user=deadline.user)

            # Check if we should send based on days remaining and user preferences
            days_remaining = deadline.days_remaining
            if days_remaining is None:
                continue

            if not prefs.should_send_deadline_reminder(days_remaining):
                continue

            # Send the email
            success = _send_deadline_reminder_email(deadline, days_remaining)

            if success:
                # Mark reminder as sent
                deadline.reminder_sent = True
                deadline.save(update_fields=["reminder_sent", "updated_at"])

                # Update user's notification tracking
                prefs.last_email_sent = timezone.now()
                prefs.emails_sent_count += 1
                prefs.save(
                    update_fields=["last_email_sent", "emails_sent_count", "updated_at"]
                )

                reminders_sent += 1
                logger.info(
                    f"Sent deadline reminder to user_id={deadline.user_id} for deadline_id={deadline.id}"
                )

        except Exception as e:
            error_msg = f"Failed to send reminder for deadline {deadline.id}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

    result = f"Sent {reminders_sent} deadline reminders"
    if errors:
        result += f" ({len(errors)} errors)"

    logger.info(result)
    return result


@shared_task(acks_late=True)
def send_exam_reminders():
    """
    Send email reminders for upcoming C&P exams.

    Checks all exam checklists with upcoming exam dates and sends reminder emails
    based on their notification preferences.

    Should be scheduled via Celery Beat (e.g., daily at 9 AM).
    """
    from examprep.models import ExamChecklist
    from accounts.models import NotificationPreferences

    today = date.today()
    reminders_sent = 0
    errors = []

    # Get all incomplete exam checklists with upcoming dates
    upcoming_exams = ExamChecklist.objects.filter(
        exam_completed=False,
        exam_date__gte=today,
    ).select_related("user", "guidance")

    for exam in upcoming_exams:
        try:
            # Get user's notification preferences
            try:
                prefs = exam.user.notification_preferences
            except NotificationPreferences.DoesNotExist:
                prefs = NotificationPreferences.objects.create(user=exam.user)

            # Check days until exam
            days_until = (exam.exam_date - today).days
            if days_until is None or days_until < 0:
                continue

            if not prefs.should_send_exam_reminder(days_until):
                continue

            # Check if we already sent a reminder for this timing window
            # (We track this in the exam's metadata)
            reminder_key = f"reminder_sent_{days_until}_days"
            metadata = exam.metadata or {}
            if metadata.get(reminder_key):
                continue

            # Send the email
            success = _send_exam_reminder_email(exam, days_until)

            if success:
                # Mark this reminder window as sent
                metadata[reminder_key] = timezone.now().isoformat()
                exam.metadata = metadata
                exam.save(update_fields=["metadata", "updated_at"])

                # Update user's notification tracking
                prefs.last_email_sent = timezone.now()
                prefs.emails_sent_count += 1
                prefs.save(
                    update_fields=["last_email_sent", "emails_sent_count", "updated_at"]
                )

                reminders_sent += 1
                logger.info(
                    f"Sent exam reminder to user_id={exam.user_id} for exam_id={exam.id}"
                )

        except Exception as e:
            error_msg = f"Failed to send reminder for exam {exam.id}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

    result = f"Sent {reminders_sent} exam reminders"
    if errors:
        result += f" ({len(errors)} errors)"

    logger.info(result)
    return result


def _send_deadline_reminder_email(deadline, days_remaining: int) -> bool:
    """
    Send a deadline reminder email to the user.

    Returns True if email was sent successfully, False otherwise.
    """
    user = deadline.user

    # Determine urgency for email tone
    if days_remaining <= 3:
        urgency = "critical"
    elif days_remaining <= 7:
        urgency = "urgent"
    else:
        urgency = "upcoming"

    # Build email context
    context = {
        "user": user,
        "deadline": deadline,
        "days_remaining": days_remaining,
        "urgency": urgency,
        "site_name": getattr(settings, "SITE_NAME", "Benefits Navigator"),
        "site_url": getattr(settings, "SITE_URL", "https://benefitsnavigator.com"),
    }

    # Render email templates
    subject = f"{'URGENT: ' if urgency == 'critical' else ''}Deadline Reminder: {deadline.title}"
    text_content = render_to_string("emails/deadline_reminder.txt", context)
    html_content = render_to_string("emails/deadline_reminder.html", context)

    try:
        send_mail(
            subject=subject,
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send email to user_id={user.id}: {e}")
        return False


def _send_exam_reminder_email(exam, days_until: int) -> bool:
    """
    Send a C&P exam reminder email to the user.

    Returns True if email was sent successfully, False otherwise.
    """
    user = exam.user

    # Determine urgency
    if days_until <= 1:
        urgency = "tomorrow"
    elif days_until <= 3:
        urgency = "critical"
    elif days_until <= 7:
        urgency = "upcoming"
    else:
        urgency = "scheduled"

    # Build email context
    context = {
        "user": user,
        "exam": exam,
        "days_until": days_until,
        "urgency": urgency,
        "completion_percentage": exam.completion_percentage,
        "site_name": getattr(settings, "SITE_NAME", "Benefits Navigator"),
        "site_url": getattr(settings, "SITE_URL", "https://benefitsnavigator.com"),
    }

    # Render email templates
    if days_until <= 1:
        subject = f"TOMORROW: Your {exam.condition} C&P Exam"
    elif days_until <= 3:
        subject = f"URGENT: {exam.condition} C&P Exam in {days_until} days"
    else:
        subject = f"Reminder: {exam.condition} C&P Exam in {days_until} days"

    text_content = render_to_string("emails/exam_reminder.txt", context)
    html_content = render_to_string("emails/exam_reminder.html", context)

    try:
        send_mail(
            subject=subject,
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send email to user_id={user.id}: {e}")
        return False


@shared_task(acks_late=True)
def send_all_reminders():
    """
    Master task that sends all types of reminders.

    Calls both deadline and exam reminder tasks.
    Should be scheduled via Celery Beat (e.g., daily at 9 AM).
    """
    deadline_result = send_deadline_reminders()
    exam_result = send_exam_reminders()

    return {
        "deadlines": deadline_result,
        "exams": exam_result,
    }


@shared_task(acks_late=True)
def send_document_analysis_complete_email(document_id: int):
    """
    Send email notification when document analysis is complete.

    Called from claims/tasks.py after process_document_task or
    decode_denial_letter_task completes successfully.
    """
    from claims.models import Document
    from accounts.models import NotificationPreferences

    try:
        document = Document.objects.select_related("user").get(id=document_id)
        user = document.user

        # Get user's notification preferences
        try:
            prefs = user.notification_preferences
        except NotificationPreferences.DoesNotExist:
            prefs = NotificationPreferences.objects.create(user=user)

        # Check if user wants document analysis notifications
        if not prefs.should_send_document_analysis_notification():
            logger.info(
                f"User user_id={user.id} has disabled document analysis notifications"
            )
            return "Notification disabled by user preferences"

        # Send the email
        success = _send_document_analysis_email(document)

        if success:
            # Update notification tracking
            prefs.last_email_sent = timezone.now()
            prefs.emails_sent_count += 1
            prefs.save(
                update_fields=["last_email_sent", "emails_sent_count", "updated_at"]
            )

            logger.info(
                f"Sent document analysis complete email to user_id={user.id} for document_id={document_id}"
            )
            return f"Email sent to user_id={user.id}"

        return "Email sending failed"

    except Document.DoesNotExist:
        logger.error(f"Document {document_id} not found")
        return "Document not found"
    except Exception as e:
        logger.error(f"Error sending document analysis email for {document_id}: {e}")
        return f"Error: {e}"


def _send_document_analysis_email(document) -> bool:
    """
    Send a document analysis complete email to the user.

    Returns True if email was sent successfully, False otherwise.
    """
    user = document.user

    # Determine document type label for email (matches Document.DOCUMENT_TYPE_CHOICES)
    doc_type_labels = {
        "medical_records": "Medical Records",
        "service_records": "Service Records",
        "decision_letter": "VA Decision Letter",
        "buddy_statement": "Buddy Statement",
        "lay_statement": "Lay Statement",
        "nexus_letter": "Medical Nexus/Opinion Letter",
        "employment_records": "Employment Records",
        "personal_statement": "Personal Statement",
        "other": "Document",
    }
    doc_type_label = doc_type_labels.get(document.document_type, "Document")

    # Build email context
    context = {
        "user": user,
        "document": document,
        "doc_type_label": doc_type_label,
        "has_summary": bool(document.ai_summary),
        "page_count": document.page_count or 0,
        "site_name": getattr(settings, "SITE_NAME", "Benefits Navigator"),
        "site_url": getattr(settings, "SITE_URL", "https://benefitsnavigator.com"),
    }

    # Render email templates
    subject = f"Your {doc_type_label} Analysis is Ready"
    text_content = render_to_string("emails/document_analysis_complete.txt", context)
    html_content = render_to_string("emails/document_analysis_complete.html", context)

    try:
        send_mail(
            subject=subject,
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send email to user_id={user.id}: {e}")
        return False


# =============================================================================
# HEALTH MONITORING TASKS
# =============================================================================


@shared_task
def record_health_metrics():
    """
    Record system health metrics for historical tracking.

    Should be scheduled via Celery Beat (e.g., every 5 minutes).
    """
    from .health import record_metrics

    try:
        health = record_metrics()
        logger.info(f"Recorded health metrics: status={health['status']}")
        return {
            "status": health["status"],
            "timestamp": health["timestamp"],
        }
    except Exception as e:
        logger.error(f"Failed to record health metrics: {e}")
        return {"error": str(e)}


@shared_task
def check_processing_health():
    """
    Check for processing issues and alert if needed.

    Looks for:
    - High failure rates
    - Documents stuck in processing
    - Celery queue backlog

    Should be scheduled via Celery Beat (e.g., every 15 minutes).
    """
    from .models import ProcessingFailure
    from claims.models import Document

    alerts = []

    # Check failure rate in last hour
    failure_stats = ProcessingFailure.get_failure_stats(hours=1)
    if failure_stats["total"] >= 5:
        alerts.append(
            f"High failure rate: {failure_stats['total']} failures in last hour"
        )

    # Check for documents stuck in processing
    stuck_threshold = timezone.now() - timezone.timedelta(hours=1)
    stuck_docs = Document.objects.filter(
        status__in=["processing", "analyzing"], updated_at__lt=stuck_threshold
    ).count()

    if stuck_docs > 0:
        alerts.append(f"{stuck_docs} documents stuck in processing for >1 hour")

    # Check Celery queue length
    try:
        from .health import check_celery

        celery_status = check_celery()
        if celery_status.get("queue_length", 0) > 100:
            alerts.append(
                f"High Celery queue: {celery_status['queue_length']} tasks waiting"
            )
        if celery_status.get("workers", 0) == 0:
            alerts.append("No Celery workers available")
    except Exception as e:
        logger.error(f"Failed to check Celery status: {e}")

    # Send alert if issues found
    if alerts:
        import sentry_sdk

        alert_message = "Processing Health Alert:\n" + "\n".join(
            f"- {a}" for a in alerts
        )

        try:
            sentry_sdk.capture_message(
                alert_message,
                level="warning",
                extras={
                    "failure_stats": failure_stats,
                    "stuck_docs": stuck_docs,
                },
            )
        except Exception:
            pass  # Sentry might not be configured

        logger.warning(alert_message)

    return {
        "alerts": alerts,
        "failure_stats": failure_stats,
        "stuck_docs": stuck_docs,
    }


@shared_task
def cleanup_old_health_metrics():
    """
    Clean up old health metrics to prevent database bloat.

    Keeps last 30 days of metrics.
    Should be scheduled via Celery Beat (e.g., daily).
    """
    from .models import SystemHealthMetric

    threshold = timezone.now() - timezone.timedelta(days=30)
    deleted, _ = SystemHealthMetric.objects.filter(timestamp__lt=threshold).delete()

    logger.info(f"Cleaned up {deleted} old health metrics")
    return f"Deleted {deleted} old metrics"


@shared_task
def run_monitoring_checks():
    """
    Run all monitoring checks and send alerts if thresholds exceeded.

    Checks:
    - System health (database, Redis, Celery, document processing)
    - Download anomalies (potential data exfiltration)
    - Task age (stale/long-running tasks)

    Should be scheduled via Celery Beat (e.g., every 5 minutes).
    """
    from core.alerting import run_all_monitoring_checks

    results = run_all_monitoring_checks()

    total_alerts = (
        len(results.get("health_alerts", []))
        + len(results.get("download_anomalies", []))
        + len(results.get("stale_tasks", []))
    )

    return {
        "total_alerts": total_alerts,
        "results": results,
    }


@shared_task
def check_download_anomalies_task(hours: int = 1):
    """
    Check for unusual download patterns.

    Detects potential data exfiltration by monitoring:
    - High download volume per user
    - Multiple users from same IP
    - Unusual download patterns

    Should be scheduled via Celery Beat (e.g., hourly).
    """
    from core.alerting import check_download_anomalies

    anomalies = check_download_anomalies(hours=hours)

    if anomalies:
        logger.warning(f"Detected {len(anomalies)} download anomalies")

    return {
        "anomalies_detected": len(anomalies),
        "details": anomalies,
    }


# =============================================================================
# PILOT USER DATA RETENTION
# =============================================================================


@shared_task(acks_late=True)
def enforce_pilot_data_retention():
    """
    Enforce data retention specifically for pilot users.

    Pilot users have a shorter retention period (default 30 days) to:
    - Keep test data clean
    - Ensure compliance during pilot phases
    - Prevent accumulation of test data

    This task:
    1. Identifies pilot users (via is_pilot_user property)
    2. Soft-deletes their documents older than PILOT_DATA_RETENTION_DAYS
    3. Deletes their AI analyses older than retention period
    4. Logs all retention actions for audit

    Should be scheduled via Celery Beat (e.g., daily at 3 AM).
    """
    from accounts.models import User
    from claims.models import Document
    from .models import AuditLog

    retention_days = getattr(settings, "PILOT_DATA_RETENTION_DAYS", 30)

    # Skip if retention is disabled (set to 0)
    if retention_days <= 0:
        logger.info("Pilot data retention disabled (PILOT_DATA_RETENTION_DAYS=0)")
        return {
            "status": "disabled",
            "reason": "PILOT_DATA_RETENTION_DAYS is 0 or negative",
        }

    cutoff_date = timezone.now() - timedelta(days=retention_days)
    results = {
        "pilot_users_checked": 0,
        "documents_soft_deleted": 0,
        "analyses_deleted": 0,
        "statements_deleted": 0,
        "errors": [],
    }

    # Get all users and check if they're pilot users
    # Note: We check is_pilot_user property which considers:
    # - PILOT_PREMIUM_ACCESS setting
    # - PILOT_PREMIUM_EMAILS list
    # - PILOT_PREMIUM_DOMAINS list
    users = User.objects.all()

    for user in users:
        try:
            # Check if user is a pilot user
            if not getattr(user, "is_pilot_user", False):
                continue

            results["pilot_users_checked"] += 1

            # Soft-delete old documents for this pilot user
            old_docs = Document.objects.filter(
                user=user, is_deleted=False, created_at__lt=cutoff_date
            )

            doc_count = old_docs.count()
            if doc_count > 0:
                for doc in old_docs:
                    doc.soft_delete()

                results["documents_soft_deleted"] += doc_count

                # Log the retention action
                AuditLog.objects.create(
                    user=user,
                    action="pilot_retention_documents",
                    resource_type="document",
                    details={
                        "count": doc_count,
                        "retention_days": retention_days,
                        "reason": "pilot_data_retention",
                    },
                )

            # Delete old AI analyses for this pilot user
            analysis_count = _purge_pilot_user_analyses(user, cutoff_date)
            results["analyses_deleted"] += analysis_count

            # Delete old personal statements for this pilot user
            statement_count = _purge_pilot_user_statements(user, cutoff_date)
            results["statements_deleted"] += statement_count

        except Exception as e:
            error_msg = f"Error processing pilot retention for user {user.id}: {e}"
            logger.error(error_msg)
            results["errors"].append(error_msg)

    # Log summary
    logger.info(
        f"Pilot data retention complete: "
        f"{results['pilot_users_checked']} users checked, "
        f"{results['documents_soft_deleted']} documents soft-deleted, "
        f"{results['analyses_deleted']} analyses deleted, "
        f"{results['statements_deleted']} statements deleted"
    )

    return results


def _purge_pilot_user_analyses(user, cutoff_date) -> int:
    """
    Delete AI analyses for a specific pilot user older than cutoff date.

    Returns count of deleted records.
    """
    total_deleted = 0

    try:
        from agents.models import (
            AgentInteraction,
            DecisionLetterAnalysis,
            EvidenceGapAnalysis,
        )

        # Delete decision letter analyses
        dla_deleted, _ = DecisionLetterAnalysis.objects.filter(
            user=user, created_at__lt=cutoff_date
        ).delete()
        total_deleted += dla_deleted

        # Delete evidence gap analyses
        ega_deleted, _ = EvidenceGapAnalysis.objects.filter(
            user=user, created_at__lt=cutoff_date
        ).delete()
        total_deleted += ega_deleted

        # Delete agent interactions
        ai_deleted, _ = AgentInteraction.objects.filter(
            user=user, created_at__lt=cutoff_date
        ).delete()
        total_deleted += ai_deleted

    except ImportError:
        logger.warning("agents app not available for pilot analysis purge")

    return total_deleted


def _purge_pilot_user_statements(user, cutoff_date) -> int:
    """
    Delete personal statements for a specific pilot user older than cutoff date.

    Returns count of deleted records.
    """
    try:
        from agents.models import PersonalStatement

        deleted, _ = PersonalStatement.objects.filter(
            user=user, created_at__lt=cutoff_date
        ).delete()
        return deleted

    except ImportError:
        logger.warning("agents app not available for pilot statement purge")
        return 0


@shared_task(acks_late=True)
def notify_pilot_users_before_retention():
    """
    Send notification to pilot users before their data is deleted.

    Warns users 7 days before their data reaches the retention limit.
    This gives them time to export or save any important information.

    Should be scheduled via Celery Beat (e.g., daily).
    """
    from accounts.models import User
    from claims.models import Document
    from django.core.mail import send_mail

    retention_days = getattr(settings, "PILOT_DATA_RETENTION_DAYS", 30)
    warning_days = 7  # Warn 7 days before deletion

    if retention_days <= warning_days:
        return {"status": "skipped", "reason": "retention_days too short for warning"}

    # Calculate the date when data will be at risk
    warning_cutoff = timezone.now() - timedelta(days=retention_days - warning_days)

    users = User.objects.all()
    notifications_sent = 0
    errors = []

    for user in users:
        try:
            if not getattr(user, "is_pilot_user", False):
                continue

            # Check if user has documents that will be deleted soon
            at_risk_docs = Document.objects.filter(
                user=user, is_deleted=False, created_at__lt=warning_cutoff
            ).count()

            if at_risk_docs == 0:
                continue

            # Send warning email
            subject = f"[{settings.SITE_NAME}] Your pilot data will be deleted in {warning_days} days"
            message = f"""Hello,

As part of our pilot program data retention policy, documents and analyses older than {retention_days} days are automatically removed.

You have {at_risk_docs} document(s) that will be deleted in approximately {warning_days} days.

If you need to keep this information, please:
1. Download any important documents
2. Export your rating calculations
3. Save any AI analysis results you want to keep

Thank you for participating in our pilot program!

Best regards,
The {settings.SITE_NAME} Team
"""

            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )

            notifications_sent += 1
            logger.info(f"Sent retention warning to pilot user {user.id}")

        except Exception as e:
            error_msg = f"Error notifying user {user.id}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

    return {
        "notifications_sent": notifications_sent,
        "errors": errors,
    }


# =============================================================================
# ACCOUNT DELETION (GDPR / right-to-erasure)
# =============================================================================


def _delete_user_files(user):
    """
    Delete a user's uploaded files from storage before the DB rows cascade away.

    Database cascade removes the rows but NOT the underlying files in the storage
    backend, so those must be deleted explicitly. Covers claims Documents and
    appeal AppealDocuments. Returns the number of files removed.
    """
    from claims.models import Document
    from appeals.models import AppealDocument

    removed = 0

    # Claims documents (include soft-deleted — everything the user owns goes)
    for doc in Document.all_objects.filter(user=user):
        try:
            if doc.file:
                doc.file.delete(save=False)
                removed += 1
        except Exception as e:
            logger.error(f"Account purge: failed to delete document file {doc.id}: {e}")

    # Appeal documents (reached through the user's appeals)
    for appeal_doc in AppealDocument.objects.filter(appeal__user=user):
        try:
            if appeal_doc.file:
                appeal_doc.file.delete(save=False)
                removed += 1
        except Exception as e:
            logger.error(
                f"Account purge: failed to delete appeal document file "
                f"{appeal_doc.id}: {e}"
            )

    return removed


def _detach_stripe_customer(user):
    """Best-effort deletion of the user's Stripe customer record. Non-blocking."""
    customer_id = getattr(user, "stripe_customer_id", "")
    if not customer_id:
        return
    api_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    if not api_key:
        return
    try:
        import stripe

        stripe.api_key = api_key
        stripe.Customer.delete(customer_id)
    except Exception as e:
        # Don't block account deletion on a Stripe hiccup — log for follow-up.
        logger.error(
            f"Account purge: failed to delete Stripe customer for user {user.id}: {e}"
        )


def purge_user_account(user):
    """
    Permanently and completely erase a single user account and all its data.

    Order matters:
      1. Record the purge in the audit log while the user still exists (the
         AuditLog FK is SET_NULL and preserves user_email, so the entry
         survives the deletion as the erasure record).
      2. Delete files from storage (DB cascade won't touch the storage backend).
      3. Best-effort detach the Stripe customer.
      4. Delete the User row — Django cascades every owned record (profile,
         documents, claims, appeals, agent analyses, assistant transcripts,
         VSO cases where the user is the veteran, journey data, etc.).

    Deleting a veteran cascades their VeteranCase and its notes/shared
    documents/analyses — deletion stays complete rather than leaving VSO copies
    of the veteran's data behind. Where the user is instead a VSO caseworker,
    VeteranCase.assigned_to is SET_NULL, so colleagues' cases are preserved and
    merely unassigned.
    """
    from .models import AuditLog

    user_id = user.id
    user_email = user.email

    AuditLog.log(
        action="account_delete_purge",
        user=user,
        details={
            "requested_at": (
                user.deletion_requested_at.isoformat()
                if user.deletion_requested_at
                else None
            ),
        },
    )

    files_removed = _delete_user_files(user)
    _detach_stripe_customer(user)
    user.delete()

    logger.info(
        f"Account purge complete for user id={user_id} "
        f"({files_removed} file(s) removed)"
    )
    return {"user_id": user_id, "user_email": user_email, "files_removed": files_removed}


@shared_task(bind=True, max_retries=3, acks_late=True)
def process_scheduled_account_deletions(self):
    """
    Permanently purge accounts whose 30-day deletion grace period has elapsed.

    Scheduled daily via Celery Beat. Idempotent: purged users no longer match
    the query, so redelivery after a crash simply reprocesses whatever remains
    due. Each account is purged in its own transaction so one failure doesn't
    strand the rest.
    """
    from django.contrib.auth import get_user_model
    from django.db import transaction

    User = get_user_model()

    now = timezone.now()
    purged = 0
    errors = []

    due_users = User.objects.filter(deletion_requested_at__isnull=False).filter(
        deletion_requested_at__lte=now - timedelta(days=User.DELETION_GRACE_DAYS)
    )

    for user in due_users:
        try:
            with transaction.atomic():
                purge_user_account(user)
            purged += 1
        except Exception as e:
            logger.error(f"Failed to purge account id={user.id}: {e}")
            errors.append(user.id)

    logger.info(
        f"Scheduled account deletions: purged {purged}, {len(errors)} error(s)"
    )
    return {"purged": purged, "errors": errors}
