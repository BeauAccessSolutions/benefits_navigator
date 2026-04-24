# ADR 001: Celery Task Retry and Failure Strategy

**Status:** Accepted
**Date:** 2026-03-26
**Deciders:** Engineering

---

## Context

Benefits Navigator processes VA documents asynchronously via Celery tasks. These tasks
call external services (Tesseract OCR, OpenAI API) that can fail transiently. We needed
a retry strategy that balances user experience, cost, and system stability.

Tasks in scope:
- `process_document_task` — OCR + AI document analysis
- `decode_denial_letter_task` — multi-stage denial letter analysis
- `analyze_rating_decision_task` — rating decision extraction and insights

---

## Decision

### Max retries: 3

Each task retries up to 3 times. After 3 failures, the task raises its final exception
and Celery marks it as `FAILURE`. A `ProcessingFailure` record is created at each
failure, with the final retry having the most useful stack trace.

```python
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_document_task(self, document_id: int):
    ...
    except SomeRetryableError as e:
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
```

### Exponential backoff

Retry delays: 60s → 120s → 240s. This avoids thundering-herd on OpenAI rate limits.

### Non-retryable failures

`AIConsentError` is not retried — if the user has revoked AI consent, retrying would
violate their explicit preference. These are recorded as `ProcessingFailure` with status
`new` but are expected and can be triaged as `ignored`.

### No dead letter queue

Failed tasks are logged to `ProcessingFailure` and can be manually replayed via the
Django shell (see `docs/FAILURE_TRACKING.md`). A formal DLQ (e.g., a separate Redis
list or SQS queue) was not implemented.

---

## Consequences

### Accepted trade-offs

- **Data loss on exhaustion:** If all 3 retries fail, the task is dropped. The user
  sees a failed status on their document. No automatic recovery occurs.
  - *Mitigation:* `ProcessingFailure` records enable manual replay. An on-call engineer
    can identify failed tasks and re-enqueue them.

- **No automatic replay:** Engineers must manually trigger replays via the Django shell.
  This adds operational burden during incidents.
  - *Future mitigation:* A `replay_failed_tasks` management command or admin action
    would reduce friction. Not yet implemented.

- **No DLQ:** Unlike a proper DLQ, failed tasks don't have guaranteed redelivery or
  ordering. Manual replay can trigger duplicate processing if the task partially
  succeeded before failing.
  - *Mitigation:* Tasks check for existing analysis records before re-running to
    avoid duplicate AI calls.

### What went well

- Simple to reason about — engineers understand Celery retry mechanics
- `ProcessingFailure` provides a full audit trail with stack traces
- Alert threshold (≥3 failures/hr) provides early warning before user impact is broad

---

## Alternatives Considered

### Dead letter queue (SQS or Redis list)

Would provide automatic replay, ordering guarantees, and visibility into dropped tasks.
Rejected because: adds infrastructure complexity for current scale; manual replay via
`ProcessingFailure` is sufficient for the current failure rate; DigitalOcean App Platform
doesn't natively support SQS.

**Revisit when:** Failure volume exceeds what's manageable manually (>20 failures/day),
or when task replay SLA is formalized.

### Infinite retries with circuit breaker

A circuit breaker pattern on the OpenAI client would stop retrying during sustained
outages without exhausting the queue. Rejected because it adds significant complexity;
the current 3-retry limit naturally bounds queue saturation.

**Revisit when:** OpenAI outages consistently exhaust all retries and flood the failure
log.

---

## Related

- `docs/FAILURE_TRACKING.md` — operational runbook
- `claims/tasks.py` — retry implementation
- `agents/ai_gateway.py` — OpenAI gateway with its own retry logic (note: two retry
  layers exist — the gateway retries at the HTTP level, tasks retry at the task level)
