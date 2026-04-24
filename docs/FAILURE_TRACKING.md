# Failure Tracking Runbook

Operational guide for querying, triaging, and replaying `ProcessingFailure` records.

---

## Overview

`ProcessingFailure` (`core/models.py`) is the central failure log for all async document
processing tasks. Every task that exhausts retries or hits a non-retryable error calls
`ProcessingFailure.record_failure()`, which persists the failure and conditionally fires
an alert when ≥3 failures of the same type occur within an hour.

**Failure types:**

| `failure_type` | Source task |
|---|---|
| `ocr` | `process_document_task` — Tesseract/OCR stage |
| `document_processing` | `process_document_task` — AI analysis stage |
| `ai_analysis` | `decode_denial_letter_task`, `analyze_rating_decision_task` |

**Failure statuses:**

| Status | Meaning |
|---|---|
| `new` | Unacknowledged, needs triage |
| `investigating` | Assigned to someone |
| `resolved` | Root cause fixed |
| `ignored` | Known issue, not actionable |

---

## Querying Failures

### Django Admin

Navigate to **Admin → Core → Processing Failures**.

Useful filters:
- `Status = new` — unresolved failures
- `Failure type` — filter by stage
- `Created at` — date range

### Django Shell

```python
from django.utils import timezone
from core.models import ProcessingFailure

# All failures in the last 24 hours
since = timezone.now() - timezone.timedelta(hours=24)
failures = ProcessingFailure.objects.filter(created_at__gte=since)
print(failures.count())

# Breakdown by type
from django.db.models import Count
failures.values('failure_type').annotate(n=Count('id')).order_by('-n')

# Unresolved failures only
ProcessingFailure.objects.filter(status='new').order_by('-created_at')[:20]

# Failures for a specific document
ProcessingFailure.objects.filter(document_id=1234)

# Failures for a specific Celery task
ProcessingFailure.objects.filter(task_id='abc-123-...')

# Use the built-in stats helper (last 24h by default)
ProcessingFailure.get_stats()
ProcessingFailure.get_stats(since=timezone.now() - timezone.timedelta(hours=1))
```

### Sentry

Failures with `alert_sent=True` have a corresponding Sentry event. Search:
```
alert_type:system_health failure_type:<type>
```

---

## Replaying Failed Tasks

There is no automated replay UI. Use the Django shell to re-enqueue.

### 1. Identify the failed document

```python
from core.models import ProcessingFailure
f = ProcessingFailure.objects.get(id=<failure_id>)
print(f.document_id, f.failure_type, f.error_message)
```

### 2. Re-enqueue the appropriate task

```python
from claims.tasks import process_document_task, decode_denial_letter_task, analyze_rating_decision_task

# For ocr or document_processing failures
process_document_task.delay(document_id=f.document_id)

# For ai_analysis failures on denial letters
decode_denial_letter_task.delay(document_id=f.document_id)

# For ai_analysis failures on rating decisions
analyze_rating_decision_task.delay(document_id=f.document_id)
```

### 3. Mark the failure as resolved

```python
f.status = 'resolved'
f.save()
```

### Bulk replay

```python
from core.models import ProcessingFailure
from claims.tasks import process_document_task

# Replay all unresolved OCR failures from the last 6 hours
since = timezone.now() - timezone.timedelta(hours=6)
failures = ProcessingFailure.objects.filter(
    failure_type='ocr',
    status='new',
    created_at__gte=since
).exclude(document_id=None)

for f in failures:
    process_document_task.delay(document_id=f.document_id)
    f.status = 'investigating'
    f.save()

print(f"Re-enqueued {failures.count()} tasks")
```

> **Warning:** Do not bulk-replay more than ~20 tasks at once on a single basic-xxs worker
> (concurrency=2). Stagger if needed.

---

## Alert Thresholds

Alerts fire via `core/alerting.py` when these thresholds are crossed:

| Condition | Warning | Critical |
|---|---|---|
| Document processing success rate | < 90% | < 80% |
| Failures per hour (any type) | ≥ 5 | ≥ 10 |
| `record_failure()` internal trigger | — | ≥ 3 same type/hr |

Thresholds can be overridden in `settings.py`:
```python
ALERT_THRESHOLDS = {
    'failures_per_hour_warning': 5,
    'failures_per_hour_critical': 10,
    'processing_success_rate_warning': 90.0,
    'processing_success_rate_critical': 80.0,
}
```

Health check `/health/?full=1` shows current failure counts:
- 0–4 failures in window → `healthy`
- 5–9 → `degraded`
- 10+ → `unhealthy`

---

## Triage Decision Tree

```
New failure alert received
        │
        ▼
Is failure_type = 'ocr'?
  YES → Check if document is readable (scanned vs native PDF)
        Check Tesseract availability in worker logs
        If Tesseract OK → document may be corrupt, mark 'ignored'
        If Tesseract error → worker issue, see INCIDENT_RESPONSE.md
  NO  ▼
Is failure_type = 'ai_analysis' or 'document_processing'?
        │
        ▼
  Check error_message:
  - "OpenAI" / "rate limit" / "timeout" → OpenAI degradation
    → Check https://status.openai.com
    → Replay after OpenAI recovers
  - "AIConsentError" → User revoked AI consent mid-task
    → Mark 'ignored' (non-retryable by design)
  - "ValidationError" / "parse error" → Prompt/schema mismatch
    → Investigate agents/schemas.py for the relevant task
    → File a bug before replaying
  - Unknown → Check stack_trace field for full traceback
```

---

## Common Failure Scenarios

### OpenAI rate limits
- Failures pile up with `RateLimitError` in `error_message`
- Wait for OpenAI to recover, then bulk-replay
- Consider spreading replays over time to avoid hitting limits again

### Worker OOM restart
- Failures have no `task_id` or a partial one
- Check DO App Platform logs for OOM kills: `doctl apps logs <app-id> --type=run`
- Upgrade worker to `basic-xs` if recurring

### Corrupt document upload
- OCR failures on the same `document_id` repeatedly
- Mark as `ignored`, notify user to re-upload a clearer scan

### AI consent revoked mid-task
- `AIConsentError` — non-retryable, safe to mark `ignored`
- These are expected and not operational failures

---

## Monitoring Cadence

`run_all_monitoring_checks()` in `core/alerting.py` should run every 5 minutes via
a periodic Celery beat task. Verify it is scheduled:

```python
# In Celery beat schedule (settings.py or celery.py)
'run-monitoring-checks': {
    'task': 'core.tasks.run_monitoring_checks',
    'schedule': 300.0,  # every 5 minutes
},
```

If not yet scheduled, add it. Until then, trigger manually:
```python
from core.alerting import run_all_monitoring_checks
run_all_monitoring_checks()
```

---

## Related Docs

- `docs/INCIDENT_RESPONSE.md` — escalation paths and runbooks
- `docs/security-invariants.md` — PHI/PII protections in place
- `core/health.py` — health check implementation
- `core/alerting.py` — alerting thresholds and channels
