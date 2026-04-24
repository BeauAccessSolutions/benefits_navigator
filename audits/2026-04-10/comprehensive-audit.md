# Comprehensive Audit — Benefits Navigator
**Date:** 2026-04-10
**Protocol:** Tier 1 automated scans + Tier 2 six-specialist review
**Auditors:** Claude Code + 5 specialist agents (VA Regulatory, AI Safety, CI/CD, Code Quality, Accessibility, UX/Safety, Docs, Monitoring)

---

## Scorecard

| Domain | Score | Worst Finding |
|--------|-------|---------------|
| CI/CD | 3/5 | No coverage threshold gate; bandit advisory only |
| Django/Backend | 3/5 | N+1 counts in dashboard; unrated download endpoints |
| Celery/Async | 4/5 | acks_late correct on user-data tasks; no replay mgmt command |
| Security | 2/5 | Silent bare except in consent decorator (agents/views.py:49) |
| Documentation | 4/5 | Strong ops/PHI docs; no CLAUDE.md in project root |
| Monitoring/Ops | 2/5 | No stuck-task detection; Beat placement undocumented |
| VA Regulatory | 4/5 | All rates/deadlines correct; no auto-sync for annual COLA |
| AI Safety | 4/5 | OCR sanitized ✅; consent bare except masks errors |
| Code Quality | 2/5 | Rate limit gaps on downloads; 8+ untyped exception handlers |
| Accessibility | 2/5 | 21 required inputs missing aria-required; 0 HTMX focus mgmt |
| UX/Safety | 2/5 | Dollar amounts shown without "estimated"; disclaimers buried |
| **Overall** | **2.9/5** | |

**Verdict: ⚠️ SHIP WITH CAVEATS** — Not suitable for scaling to broader veteran population until P0 and P1 items are resolved. Current pilot use (known users) acceptable with documented limitations.

---

## Corrections from Tier 1

> **VA 2026 100% rate ($3,938.58)** — Tier 1 flagged this as a discrepancy. Tier 2 confirmed it is **CORRECT**. The baseline error was mine: 2025 rate = $3,831.30 (not $3,737.85 which was the 2024 rate). $3,831.30 × 1.028 = $3,938.58. ✅

> **OCR sanitization** — Confirmed present at `claims/services/ai_service.py:134`. ✅

> **IDOR protection** — Confirmed sound across all views. ✅

---

## P0 — Fix Before Broader Rollout

### 1. Silent bare except in AI consent decorator
**File:** `agents/views.py:49`
**Issue:** `except Exception: return False` — any error in `user.profile.ai_processing_consent` lookup (DB error, missing profile) silently returns False. This makes consent failures impossible to debug and could mask relationship corruption.
**Fix:** Replace with `except (AttributeError, RelatedObjectDoesNotExist) as e: logger.warning("Consent check failed: %s", e); return False`

### 2. No rate limit on document download endpoints
**Files:** `claims/views.py:412` (`document_download`), `claims/views.py:491` (`document_view_inline`)
**Issue:** A user can request the same document file thousands of times per second. IDOR protection is correct (each request checks ownership), but no throttle means DoS risk against filesystem and memory.
**Fix:** Add `@ratelimit(key='user', rate='60/m', method='GET', block=True)` to both views.

### 3. Legal disclaimers missing from AI result pages
**Files:** `agents/decision_analyzer_result.html`, `claims/denial_decoder_result.html`, `agents/evidence_gap_result.html`
**Issue:** These pages show appeal recommendations, evidence requirements, and condition ratings with no "not legal advice" disclaimer. The homepage has the disclaimer but users arriving directly at result pages never see it.
**Fix:** Add inline disclaimer adjacent to recommendation sections: *"These are educational estimates only. Not legal advice. Consult an accredited VSO before filing."*

### 4. Compensation estimates shown without "estimated" label
**File:** `templates/examprep/rating_calculator.html`
**Issue:** Dollar amounts (e.g., "$1,234/mo") displayed in bold green without any qualifier. Veterans in distress can make high-stakes decisions based on false precision.
**Fix:** Change display to "~$1,234/mo (estimated)" and move the existing disclaimer from page bottom to adjacent to the compensation display.

---

## P1 — Fix Within 1 Week

### 5. aria-required missing on 21 required form inputs
**Scope:** Multiple templates — rating_calculator.html, document_upload.html, and others
**Issue:** HTML `required` attribute present but `aria-required="true"` absent. Screen reader users don't know fields are required until form submission fails. WCAG 3.3.2 violation.
**Fix:** Add `aria-required="true"` to every input/select/textarea with `required`.

### 6. Zero HTMX after-swap focus management
**Scope:** `appeals/partials/checklist.html`, `claims/denial_decoder_result.html` (5s polling), all HTMX targets
**Issue:** After any HTMX swap, focus is not programmatically managed. Keyboard users lose context. WCAG 2.4.3 and 4.1.3 violations.
**Fix:** Add `hx-on::after-swap="document.getElementById('target-id').focus()"` or equivalent to all dynamic update targets.

### 7. Escape key missing on rating calculator share modal
**File:** `templates/examprep/rating_calculator.html`
**Issue:** `saved_calculations.html` has Escape handler but `rating_calculator.html` share modal does not. WCAG 2.1.1 violation.
**Fix:** Add Escape keydown listener to share modal in rating_calculator.html (matching pattern in saved_calculations.html:195-199).

### 8. acks_late=True missing on core/tasks.py data tasks
**File:** `core/tasks.py`
**Issue:** `enforce_data_retention` (deletes user data) and several notification tasks lack `acks_late=True`. Worker crash mid-task risks data deletion without confirmation or notification without delivery.
**Fix:** Add `acks_late=True` to all tasks in core/tasks.py that touch user data or send user-facing notifications.

### 9. No CI coverage threshold
**File:** `.github/workflows/tests.yml:71`
**Issue:** Coverage artifact uploaded but `--cov-fail-under` not set. Coverage can drop to 0% without CI failing.
**Fix:** Add `--cov-fail-under=70` (or current measured baseline) to pytest invocation.

### 10. No CI linting gate
**File:** `.github/workflows/tests.yml`
**Issue:** `ruff` and `black` are in requirements.txt but not run in CI. Code style drift accumulates silently.
**Fix:** Add a lint step: `ruff check . && black --check .`

---

## P2 — Already Tracked in TODO.md (Status Confirmed Open)

| Item | Location | Status |
|------|----------|--------|
| CSP unsafe-inline STYLE in prod | settings.py:398 | OPEN — Tailwind CDN dependency |
| N+1 query counts in dashboard | core/views.py:155-162 | OPEN |
| Worker sizing basic-xxs → basic-xs | DO Console | OPEN — 512MB OOM risk |
| Stuck task detection in health.py | core/health.py | OPEN — queue depth only, not task age |
| Beat scheduler placement docs | settings.py / docs/ | OPEN — undocumented which instance runs Beat |
| Replay management command | — | OPEN — shell-only today |
| django_csp 3.8 → 4.0 (major) | requirements.txt | OPEN — potential breaking changes to CSP middleware API |
| Django 5.2.11 → 5.2.13 | requirements.txt | OPEN — security patch |
| Supportive messaging on denial results | rating_analyzer_result.html | OPEN |
| aria-describedby for form errors | all form templates | OPEN |

---

## What's Working Well

- **IDOR protection: Exemplary** — Every `get_object_or_404` filters by user ownership. VSO path adds org validation. Signed URLs validated with user_id. No vulnerabilities found.
- **Celery durability on user data tasks: Strong** — `acks_late=True` correctly applied to all claims tasks. Idempotency guards via metadata tracking prevent duplicate reminders.
- **Encryption implementation: Sound** — Fernet AES-256, EncryptedCharField/JSONField transparent, key rotation utility present. Sentry configured `send_default_pii=False`.
- **VA regulatory accuracy: Strong** — All 2026 rates verified correct (2.8% COLA from $3,831.30). TDIU thresholds, appeal deadlines, CFR citations all accurate. No absolute language found in fixtures.
- **AI gateway: Well-designed** — OCR sanitized before model call, Pydantic schemas constrain all numeric outputs (ge=0, le=100), Result[T] .value accesses all guarded by is_success checks.
- **Operational documentation: Strong** — FAILURE_TRACKING.md, PHI_DATA_FLOW.md, CAPACITY_SCALING.md, and 2 ADRs all current and actionable.
- **Security workflow: Gating correctly** — pip-audit blocks on CVEs, schema-consistency and security-invariants gate on errors. Bandit advisory-only is appropriate.

---

## Dependency Notes

| Package | Installed | Latest | Action |
|---------|-----------|--------|--------|
| Django | 5.2.11 | 5.2.13 | Update — likely security patch |
| django_csp | 3.8 | 4.0 | Caution — major version, review changelog before updating |
| celery | 5.3.6 | 5.6.3 | Update — 3 minor versions behind |
| django-htmx | 1.17.2 | 1.27.0 | Update |
| django-otp | 1.3.0 | 1.7.0 | Update |
| django-crispy-forms | 2.1 | 2.6 | Update |

---

## Recommended Ship Sequence

1. Fix P0 items 1–4 (1–2 hours of work)
2. Fix P1 items 5–8 (2–4 hours of work, accessibility-heavy)
3. Run `/peer-review release` to verify fixes
4. Fix P1 items 9–10 (CI — 30 min)
5. Run `/ship` sequence for deploy

**Do not** fix all P2 items before shipping — they are known and tracked. P0 and P1 are the gate.

---

## Next Audit

Trigger: After P0/P1 fixes, or quarterly (2026-07-10)
Run: `/infra-audit` + `/peer-review release`
