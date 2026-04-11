"""
Health check utilities for monitoring system status.

Provides health checks for:
- Database connectivity
- Redis connectivity
- Celery worker status
- Queue length
- Processing success rates
"""

import logging
from datetime import timedelta
from django.utils import timezone
from django.db import connection
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def check_database():
    """Check database connectivity."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return {'status': 'healthy', 'message': 'Database connection OK'}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {'status': 'unhealthy', 'message': str(e)}


def check_redis():
    """Check Redis connectivity."""
    try:
        cache.set('health_check', 'ok', 10)
        value = cache.get('health_check')
        if value == 'ok':
            return {'status': 'healthy', 'message': 'Redis connection OK'}
        return {'status': 'unhealthy', 'message': 'Redis read/write failed'}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {'status': 'unhealthy', 'message': str(e)}


def check_celery():
    """Check Celery worker status and queue length."""
    try:
        from benefits_navigator.celery import app

        # Check if we can connect to broker
        inspect = app.control.inspect()

        # Get active workers (with timeout)
        active = inspect.active()

        if active is None:
            return {
                'status': 'unhealthy',
                'message': 'No Celery workers responding',
                'workers': 0,
                'queue_length': None,
            }

        # Count active workers and tasks
        worker_count = len(active)
        active_tasks = sum(len(tasks) for tasks in active.values())

        # Get queue length (if using Redis)
        queue_length = None
        try:
            import redis
            redis_url = getattr(settings, 'CELERY_BROKER_URL', None)
            if redis_url and 'redis' in redis_url:
                r = redis.from_url(redis_url)
                queue_length = r.llen('celery')
        except Exception:
            pass

        status = 'healthy' if worker_count > 0 else 'degraded'

        return {
            'status': status,
            'message': f'{worker_count} workers active',
            'workers': worker_count,
            'active_tasks': active_tasks,
            'queue_length': queue_length,
        }

    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
        return {
            'status': 'unhealthy',
            'message': str(e),
            'workers': 0,
            'queue_length': None,
        }


def check_document_processing(hours=24):
    """Check document processing success rate."""
    try:
        from claims.models import Document

        since = timezone.now() - timedelta(hours=hours)
        recent_docs = Document.objects.filter(created_at__gte=since)

        total = recent_docs.count()
        if total == 0:
            return {
                'status': 'healthy',
                'message': 'No recent documents to process',
                'total': 0,
                'success_rate': None,
            }

        completed = recent_docs.filter(status='completed').count()
        failed = recent_docs.filter(status='failed').count()
        processing = recent_docs.filter(status__in=['processing', 'analyzing']).count()

        success_rate = (completed / total) * 100 if total > 0 else 0

        # Determine health status
        if success_rate >= 95:
            status = 'healthy'
        elif success_rate >= 80:
            status = 'degraded'
        else:
            status = 'unhealthy'

        return {
            'status': status,
            'message': f'{success_rate:.1f}% success rate ({completed}/{total})',
            'total': total,
            'completed': completed,
            'failed': failed,
            'processing': processing,
            'success_rate': round(success_rate, 1),
        }

    except Exception as e:
        logger.error(f"Document processing health check failed: {e}")
        return {
            'status': 'unknown',
            'message': str(e),
            'success_rate': None,
        }


def check_stuck_tasks(stuck_after_hours=2):
    """Check for documents stuck in processing state beyond the expected window."""
    try:
        from claims.models import Document

        cutoff = timezone.now() - timedelta(hours=stuck_after_hours)
        stuck = Document.objects.filter(
            status__in=['processing', 'analyzing'],
            updated_at__lt=cutoff,
        )
        stuck_count = stuck.count()

        if stuck_count == 0:
            return {
                'status': 'healthy',
                'message': f'No documents stuck in processing (>{stuck_after_hours}h)',
                'stuck_count': 0,
            }

        # Surface oldest stuck task for ops triage
        oldest = stuck.order_by('updated_at').values('id', 'updated_at').first()
        oldest_age_hours = round(
            (timezone.now() - oldest['updated_at']).total_seconds() / 3600, 1
        ) if oldest else None

        status = 'unhealthy' if stuck_count >= 3 else 'degraded'
        return {
            'status': status,
            'message': f'{stuck_count} document(s) stuck in processing for >{stuck_after_hours}h',
            'stuck_count': stuck_count,
            'oldest_document_id': oldest['id'] if oldest else None,
            'oldest_age_hours': oldest_age_hours,
        }

    except Exception as e:
        logger.error(f"Stuck task health check failed: {e}")
        return {'status': 'unknown', 'message': str(e), 'stuck_count': None}


def check_failure_rate(hours=24):
    """Check recent processing failure rate."""
    try:
        from core.models import ProcessingFailure

        stats = ProcessingFailure.get_failure_stats(hours=hours)

        if stats['total'] == 0:
            return {
                'status': 'healthy',
                'message': 'No failures in the last 24 hours',
                **stats
            }

        # Determine severity
        if stats['total'] >= 10:
            status = 'unhealthy'
        elif stats['total'] >= 5:
            status = 'degraded'
        else:
            status = 'healthy'

        return {
            'status': status,
            'message': f"{stats['total']} failures in the last {hours} hours",
            **stats
        }

    except Exception as e:
        logger.error(f"Failure rate health check failed: {e}")
        return {
            'status': 'unknown',
            'message': str(e),
        }


def get_full_health_status():
    """Get comprehensive health status for all systems."""
    checks = {
        'database': check_database(),
        'redis': check_redis(),
        'celery': check_celery(),
        'document_processing': check_document_processing(),
        'stuck_tasks': check_stuck_tasks(),
        'failures': check_failure_rate(),
    }

    # Determine overall status
    statuses = [c['status'] for c in checks.values()]

    if 'unhealthy' in statuses:
        overall = 'unhealthy'
    elif 'degraded' in statuses:
        overall = 'degraded'
    elif 'unknown' in statuses:
        overall = 'degraded'
    else:
        overall = 'healthy'

    return {
        'status': overall,
        'timestamp': timezone.now().isoformat(),
        'checks': checks,
    }


def record_metrics():
    """Record current metrics to database for historical tracking."""
    from core.models import SystemHealthMetric

    health = get_full_health_status()

    # Record Celery metrics
    celery = health['checks']['celery']
    if celery.get('workers') is not None:
        SystemHealthMetric.objects.create(
            metric_type='celery_workers',
            value=celery['workers'],
            details={'active_tasks': celery.get('active_tasks', 0)}
        )

    if celery.get('queue_length') is not None:
        SystemHealthMetric.objects.create(
            metric_type='celery_queue',
            value=celery['queue_length'],
        )

    # Record document processing metrics
    doc_proc = health['checks']['document_processing']
    if doc_proc.get('success_rate') is not None:
        SystemHealthMetric.objects.create(
            metric_type='document_processing',
            value=doc_proc['success_rate'],
            details={
                'total': doc_proc.get('total', 0),
                'completed': doc_proc.get('completed', 0),
                'failed': doc_proc.get('failed', 0),
            }
        )

    return health
