# ADR 002: AI Consent Model — Dual-Check Pattern

**Status:** Accepted
**Date:** 2026-03-26
**Deciders:** Engineering, Legal/Compliance

---

## Context

Benefits Navigator uses OpenAI to analyze VA documents that contain Protected Health
Information. Veterans must explicitly consent before their documents are processed by
an AI system. We needed a consent model that is robust against both bugs and
intentional bypasses.

---

## Decision

AI consent is checked at **two independent layers**:

### Layer 1: View / Form (entry point)

Before a document upload or AI analysis request is accepted, the view checks
`user.profile.ai_consent`. If not granted, the user is redirected to the consent
flow before the task is enqueued.

```python
# Example in views.py
if not request.user.profile.ai_consent:
    return redirect('consent_required')
```

### Layer 2: Celery task (execution point)

The Celery task re-checks consent via `verify_ai_consent()` before calling OpenAI.
If consent was revoked between enqueue time and execution time, the task raises
`AIConsentError` and records a `ProcessingFailure`.

```python
# claims/tasks.py
@shared_task(bind=True, max_retries=3)
def process_document_task(self, document_id):
    require_ai_consent(document.user)  # raises AIConsentError if not granted
    ...
```

`AIConsentError` is **non-retryable** — retrying after a consent revocation would
violate the user's explicit choice.

---

## Rationale

A single check at the view layer is insufficient because:

1. **Race condition:** A user could revoke consent immediately after submitting a
   document. The task may already be queued and would execute without the task-level
   check.

2. **Defense in depth:** View-layer checks can be bypassed by direct API calls or
   bugs in form logic. The task-level check is the last line of defense before PHI
   is sent to an external service.

3. **Auditability:** `AIConsentError` producing a `ProcessingFailure` creates an
   auditable record that consent was absent at execution time.

---

## Consequences

### Accepted trade-offs

- **User experience:** In the rare race-condition case, the user submits a document,
  revokes consent, and sees a failure status on their document (rather than a graceful
  cancellation). This is acceptable — the failure is recorded and the user can re-consent
  and retry.

- **Operational noise:** `AIConsentError` failures appear in `ProcessingFailure` and
  could trigger alerts. They should be triaged as `ignored` — they are expected and
  represent correct system behavior, not bugs.
  - *Mitigation:* Consider filtering `AIConsentError` out of the failure-rate health
    check threshold calculation in a future iteration.

### What went well

- No PHI has ever been sent to OpenAI without valid consent
- The pattern is simple and easy to audit in code review

---

## Alternatives Considered

### Single check at view layer only

Simpler, but creates the race condition described above. Rejected as insufficient for
a system handling PHI.

### Consent token in task payload

Pass a consent timestamp in the task args; task validates that consent was granted
before that timestamp. More precise but adds coupling between consent model and task
serialization. Overkill for current scale.

### Celery task-level check only (skip view layer)

Would allow users to enqueue tasks without consent being surfaced immediately. Poor UX
and would clutter the task queue with tasks that immediately fail. Rejected.

---

## Related

- `claims/tasks.py` — `require_ai_consent()`, `verify_ai_consent()`
- `accounts/models.py` — `UserProfile.ai_consent` field
- `docs/PHI_DATA_FLOW.md` — full PHI boundary map
- `docs/security-invariants.md` — other security enforcement patterns
