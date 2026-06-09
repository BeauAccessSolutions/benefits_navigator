# Comprehensive Audit — Benefits Navigator
**Date:** 2026-06-09
**Protocol:** Tier 1 automated scans + Tier 2 seven-specialist review (per `audits/AUDIT_PROMPT.md`)
**Prior audit:** 2026-04-10 (overall 2.9/5, "SHIP WITH CAVEATS")
**Auditors:** Claude Code + 7 specialist agents (Security, VA Regulatory, AI Safety, Celery/Monitoring, Backend/CI-CD, Accessibility/UX, Docs/Tests). All specialist findings were spot-verified by the lead auditor; corrections noted below.

---

## Scorecard

| Domain | 2026-04-10 | 2026-06-09 | Worst Finding |
|--------|-----------|-----------|---------------|
| CI/CD & Deployment | 3/5 | **2/5** | `django.contrib.postgres` missing from INSTALLED_APPS — `manage.py check`/`migrate` fail (deploy-blocking) |
| Django/Backend | 3/5 | **3/5** | N+1 queries in VSO case list/CSV export/reports; no `transaction.atomic` on invitation acceptance |
| Celery/Async | 4/5 | **4/5** | M21 scraper tasks missing `acks_late`/retry config (non-user-data, so policy-compliant but fragile) |
| Security | 2/5 | **3/5** | CSP `unsafe-inline` in script-src (carried over); signed-URL endpoints unthrottled |
| Documentation | 4/5 | **4/5** | CLAUDE.md route table attributes project-level routes to core/urls.py; feature-flag list lists 6 of 14 flags |
| Monitoring/Ops | 2/5 | **4/5** | `core/health.py:77` except/pass hides Redis failure → queue alerts can't fire when Redis is down |
| VA Regulatory | 4/5 | **4/5** | All rates/deadlines verified correct; deadline `save()` logic correct but fragile (order-dependent) |
| AI Safety | 4/5 | **4/5** | No HTML sanitization of AI output before storage (defense-in-depth gap; Django autoescape is the only layer) |
| Test Coverage | — | **3/5** | No tests for signed-URL expiry/tampering or encryption round-trip; 6 tests fail without OPENAI_API_KEY locally |
| Accessibility | 2/5 | **3/5** | 5 required inputs still missing `aria-required`; 10+ HTMX targets missing `aria-live`; zero focus management |
| UX/Safety | 2/5 | **4/5** | 3 AI agent pages (statement generator, condition discovery, evidence gap) missing disclaimers |
| **Overall** | **2.9/5** | **3.4/5** | |

**Verdict: ⚠️ SHIP WITH CAVEATS — and DO NOT DEPLOY until the INSTALLED_APPS fix lands.**
Current pilot use (known users) remains acceptable. The codebase has improved measurably since April (monitoring, UX safety, and security posture all up). However, P0-1 below means the next deployment's pre-deploy `migrate` job will fail system checks, and the manual credential rotation from February is still outstanding. Broader-rollout caveats from the prior audit still apply until P1 items are resolved.

---

## Tier 1 Results (raw)

- **pytest:** 846 passed, 6 failed, 386 warnings (25.6s, sqlite). All 6 failures are environment coupling — `agents/tests.py` service-initialization tests construct a real OpenAI client and fail without `OPENAI_API_KEY`. With a dummy key: **852/852 pass**. CI sets `OPENAI_API_KEY: sk-test-fake-key` (tests.yml:40), so CI is green; only local runs without the var break.
- **bandit (`-ll`):** 1 High — MD5 at `core/encryption.py:79` (cache fingerprint of the key, not crypto; fix is `usedforsecurity=False`). 9 Medium — `mark_safe` in `core/templatetags/supportive_tags.py:78`, f-string SQL in `core/management/commands/rotate_encryption_key.py:154` (identifiers are introspected from Django models, values parameterized — acceptable), `ET.fromstring` in tests.
- **pip-audit:** lxml 5.1.0 → PYSEC-2026-87 (fix: 6.1.0); pytest 7.4.4 → CVE-2025-71176 (dev-only).
- **Secrets grep:** clean — only templates with placeholders and local-dev docker-compose URLs.
- **PII-in-logging grep:** clean.
- **Gateway-bypass grep:** clean — no OpenAI calls outside `agents/ai_gateway.py`.
- **Bare `except:`:** only in `tests/agents/` harnesses. `except Exception: pass` in app code: `core/health.py:77`, `core/views.py:711,719`, `api/views.py:165,177,230`, `claims/forms.py:83` (see P2-6).
- **`manage.py check --deploy` / `makemigrations --check`:** **FAILS** — postgres.E005 ×3 (see P0-1).

---

## Delta from 2026-04-10 Audit

### Fixed since last audit ✅
| Prior finding | Status |
|---|---|
| P0-1 Silent bare except in consent decorator (`agents/views.py:49`) | Fixed — now logs exception type, fails closed (`agents/views.py:47-51`) |
| P0-2 No rate limit on document download endpoints | Fixed — `60/m` on `document_download` (claims/views.py:411) and `document_view_inline` (:491) |
| P0-3 Disclaimers missing on AI result pages | Partially fixed — decision analyzer result now has disclaimer; statement generator, condition discovery, evidence gap result still missing (→ P1-7) |
| P0-4 Compensation shown without "estimated" | Partially fixed — rating result partial labels "(est.)" with disclaimer; rates reference table in `rating_calculator.html:170-180` still unlabeled (→ P2-9) |
| P1-5 aria-required missing on 21 inputs | Mostly fixed — 21 → 5 remaining (→ P1-8) |
| P1-8 `acks_late` missing on core/tasks.py | Fixed — all user-data tasks verified (`core/tasks.py:17,193,263,440,457,728,894`) |
| P1-9 No CI coverage threshold | Fixed — `--cov-fail-under=60` (tests.yml:81) |
| P1-10 No CI lint gate | Fixed — `ruff check . && black --check .` (tests.yml:76-77) |
| P2 Stuck-task detection | Fixed — `check_stuck_tasks()` in `core/health.py:150-186`, surfaced in full health check |
| P2 Replay management command | Fixed — `core/management/commands/replay_failed_documents.py` (dry-run default, `--execute`) |
| P2 Beat placement undocumented | Fixed — documented at `settings.py:267-272` |
| P2 Django 5.2.11 → 5.2.13 | Fixed — requirements.txt pins `Django>=5.2.13` |

### Still open from last audit ⏳
| Prior finding | Status |
|---|---|
| CSP `unsafe-inline` (script-src `settings.py:381`, style-src) | OPEN — still blocked on Tailwind build (→ P1-4) |
| Zero HTMX after-swap focus management | OPEN — still zero instances codebase-wide (→ P2-10) |
| N+1 queries in dashboards | OPEN — and worse: VSO case_list, CSV export, reports (→ P1-5) |
| Manual credential rotation (DO Console) | OPEN since 2026-02 — UNVERIFIED from code; still listed in TODO.md |
| Object storage migration (S3/Spaces) | OPEN |
| Worker sizing basic-xxs | UNVERIFIED (DO Console) |

### Regressed / New ❗
- **NEW P0:** `django.contrib.postgres` missing from INSTALLED_APPS (deploy-blocking; likely introduced with the `documentation` app's search models).
- New findings below (P1-1 … P2-12) were not in the prior report.

---

## P0 — Fix Before Next Deploy

### P0-1: `django.contrib.postgres` missing from INSTALLED_APPS — deployments will fail
**File:** `benefits_navigator/settings.py:86-127`; consumers at `documentation/models.py:12-13` (SearchVectorField, GinIndex), `documentation/views.py:9`, `documentation/migrations/0001_initial.py`
**Evidence (reproduced):**
```
$ python manage.py check --deploy   # also fails with sqlite AND postgres DATABASE_URL
ERRORS:
documentation.CPExamGuideCondition.search_vector: (postgres.E005) 'django.contrib.postgres' must be in INSTALLED_APPS in order to use SearchVectorField.
documentation.LegalReference.search_vector: (postgres.E005) ...
documentation.VAForm.search_vector: (postgres.E005) ...
```
**Impact:** Any management command that runs system checks — including the DigitalOcean pre-deploy job `python manage.py migrate --noinput` — exits with SystemCheckError. The next deployment will fail. (Tests pass because pytest-django skips system checks.)
**Fix:** Add `'django.contrib.postgres',` to INSTALLED_APPS. One line. Then `python manage.py check --deploy` must pass; add that command as a CI step so this class of error can't recur (see P2-12).

---

## P1 — Fix Within 1–2 Weeks

### P1-1: Signed-URL endpoints have no rate limit (token brute-force / scraping surface)
**Files:** `claims/views.py:547` (`document_download_signed`), `:629` (`document_view_signed`)
**Evidence:** Both views are unauthenticated by design (token IS the credential) and carry no `@ratelimit`, unlike every other document endpoint (60/m).
**Impact:** Unthrottled token-guessing attempts against HMAC tokens; also lets a leaked link be hammered for DoS. HMAC-SHA256 makes forgery impractical, but throttling is the cheap second layer.
**Fix:** `@ratelimit(key='ip', rate='30/m', block=True)` on both, plus audit-log failed token validations.

### P1-2: `phone_number` stored unencrypted
**File:** `accounts/models.py:48` — `phone_number = models.CharField('Phone number', max_length=20, blank=True)`
**Impact:** Veteran phone numbers are PII; policy says PII fields use encrypted fields. `va_file_number`/`date_of_birth` are encrypted; this one was missed.
**Fix:** Migrate to `EncryptedCharField(max_length=255)` + data migration (pattern already exists from the `ai_summary` migration).

### P1-3: lxml 5.1.0 — known vulnerability PYSEC-2026-87
**File:** `requirements.txt:96`
**Impact:** lxml parses scraped M21 HTML (via beautifulsoup4); malicious/poisoned markup is a realistic input. pip-audit in CI has `continue-on-error: false`, so this will start blocking PRs as soon as the advisory propagates — fix proactively.
**Fix:** Bump to `lxml>=6.1.0`, run the M21 scraper tests.

### P1-4: CSP still allows `unsafe-inline` for scripts (carried over)
**File:** `benefits_navigator/settings.py:381` — `CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "https://unpkg.com")`
**Impact:** Neutralizes CSP as an XSS backstop. Compounded by `mark_safe` usage (P2-7) and AI output rendering (P2-8). Known TODO ("Build Tailwind to static CSS") since February.
**Fix:** Build Tailwind statically, move inline scripts to files or nonces, drop `unsafe-inline`; also pin or self-host the unpkg HTMX bundle (supply-chain).

### P1-5: N+1 queries across VSO views
**Files:** `vso/views.py:365-370` (case_list calls `GapCheckerService.get_triage_label(case)` per case in a loop), `:430-445` (CSV export: `case.veteran.email`, `case.assigned_to.email`, `case.case_conditions.count()` per row without select_related/prefetch), `:1407-1468` (reports: Python-side iteration over all closed cases + per-caseworker counts)
**Impact:** Page latency scales linearly with caseload; CSV export of 100 cases ≈ 300+ queries. This is the B2B growth path.
**Fix:** `select_related('veteran','assigned_to')` + `prefetch_related('case_conditions')`; compute triage inputs via annotations; replace report loops with `aggregate(Avg(F('closed_at') - F('intake_date')))`-style DB aggregation.

### P1-6: `accept_invitation` multi-model write has no transaction boundary
**File:** `vso/views.py:1245-1280` — `invitation.accept(...)`, `VeteranCase.objects.create(...)`, `CaseNote.objects.create(...)` as three separate commits
**Impact:** Crash between writes leaves an accepted invitation with no case, or a case with no initial note — partial state that confuses both veteran and VSO. Audit other multi-write flows (case_create, webhook handlers) for the same pattern.
**Fix:** Wrap in `with transaction.atomic():`.

### P1-7: Three AI output pages lack disclaimers
**Files:** `templates/agents/statement_generator.html`, `templates/agents/condition_discovery.html`, `templates/agents/evidence_gap_result.html` (decision analyzer result has one — copy that pattern)
**Impact:** Veterans may submit AI-generated statements to the VA believing they're vetted/legal advice. This was P0-3 last audit and is only partially closed.
**Fix:** Add the "AI-generated — review with an accredited VSO; not legal advice" banner used on `decision_analyzer_result.html:14-21`.

### P1-8: Remaining WCAG gaps — 5 `aria-required` + 10+ HTMX targets without `aria-live`
**Files:** `templates/core/contact.html:47,60,89,102`, `templates/agents/decision_analyzer.html:38` (aria-required); `templates/documentation/search.html:54`, `templates/core/journey_dashboard.html:84`, `templates/appeals/partials/document_list.html`, `templates/appeals/partials/checklist.html`, `templates/claims/partials/document_tags.html`, `templates/examprep/saved_calculations.html`, +4 more (aria-live)
**Impact:** Screen-reader users get no announcement when search results/timeline/checklists update (WCAG 4.1.3), and can't identify required fields (WCAG 3.3.2). Veteran population skews higher on AT usage.
**Fix:** ~25 minutes of template edits per the a11y agent's table; spinner at `templates/examprep/partials/checklist_task.html:18-23` also needs `role="status"` + sr-only text.

### P1-9: No tests for signed-URL security or encryption round-trip
**Files:** absent from `claims/tests.py` and `core/tests.py`
**Impact:** The two most security-critical mechanisms (HMAC media tokens, Fernet PII encryption incl. `EncryptedJSONField`) have zero regression coverage. A refactor could silently break token expiry or decryption.
**Fix:** Add `TestSignedURLSecurity` (expiry, tampered signature, wrong user binding) and `TestEncryption` (round-trip, DB persist, JSON structure preservation). Also add GraphQL PII-redaction tests for `benefits_navigator/schema.py:28-70` (SSN ×3 formats, VA file numbers, truncation).

---

## P2 — Fix Within a Month

1. **M21 scraper tasks fragile** — `agents/tasks.py:23` (`scrape_m21_section` lacks `acks_late`), `:86,186,197,222` (four tasks with no retry/acks config at all). Not user data (policy-compliant) but a worker crash mid-scrape silently drops M21 sections used by the decision analyzer. Add standard task config.
2. **`core/health.py:77` except/pass** — Redis failure during queue-length check is swallowed; `queue_length=None` means queue alerts can never fire exactly when Redis is unhealthy. Log + propagate None.
3. **Download-anomaly alerts include user email** — `core/alerting.py:348-350`. Use user ID; keeps PII out of email/Slack channels.
4. **Token-spend cap absent** — `accounts/models.py:895` `can_use_ai_analysis()` counts analyses, not tokens. A premium user (20/hr limit) can still drive unbounded token cost. Add monthly token ceiling to `UsageTracking`.
5. **`exc_info=True` in gateway error logging** — `agents/ai_gateway.py:400`. Stack traces can capture in-flight user text. Log `type(e).__name__` or gate on DEBUG.
6. **Silent `except Exception: pass` handlers** — `core/views.py:711,719` (admin stats), `api/views.py:165,177,230` + `:65` (audit-log writes swallowed — an attacker whose actions fail to audit-log goes unrecorded), `claims/forms.py:83` (consent lookup). Log every one; alert on audit-log write failures.
7. **`mark_safe` on DB content** — `core/templatetags/supportive_tags.py:78` interpolates `SupportiveMessage.message` (admin-curated) into HTML unescaped. Stored XSS if admin account is compromised. Use `format_html()`/`escape(message.message)`.
8. **AI output rendered with autoescape as the only layer** — `templates/agents/statement_result.html:44,52`. Django escaping currently protects it (no `|safe` found), but storing bleach-cleaned text adds defense-in-depth given P1-4.
9. **Rates reference table lacks "(estimated)"** — `templates/examprep/rating_calculator.html:170-180`; header also says "2024 VA Compensation Rates" — verify it renders the selected year, not a stale label.
10. **Zero HTMX focus management** (carried over) — add `hx-on::after-swap` focus to search, checklist, and polling targets.
11. **Supplemental "no deadline" display** — `templates/appeals/appeal_detail.html:99-100` shows "—" for `deadline=None`; render "No deadline — supplemental claims can be filed anytime" so veterans don't read it as missing data. Also: the `save()` logic at `appeals/models.py:293-301` is **correct** (supplemental branch runs first, unconditionally clears) but order-dependent — a comment or restructure would prevent a future regression; tests cover it today.
12. **CI gaps** — bandit is advisory (`security-checks.yml:141 continue-on-error: true`): enforce at high-severity at minimum. Add `python manage.py check --deploy` as a CI step (would have caught P0-1). Coverage floor is 60 — ratchet upward. Pin Python patch version across CI (3.11) and Dockerfile.
13. **bandit High: MD5 fingerprint** — `core/encryption.py:79`: switch to `hashlib.md5(key, usedforsecurity=False)` or sha256 to clear the scanner.
14. **JWT refresh lifetime 7 days** (`settings.py:724`) — consider 24-48h for an app serving medical/benefits PII; `ROTATE_REFRESH_TOKENS` already on.
15. **Docs drift** — CLAUDE.md: route table attributes `/`, `/dashboard/`, `/journey/` to core/urls.py (they're project-level in `benefits_navigator/urls.py:50-79`); FEATURES table lists 6 of 14 flags (missing `doc_search`, `sso_saml`, `mfa`, `audit_export`, …); root-level stale docs (PHASE2/3_*, SESSION_HANDOFF_*, CODEX_*) should move to `docs/archive/`.
16. **Local test ergonomics** — 6 `agents/tests.py` tests need `OPENAI_API_KEY` because services eagerly construct the client. Add a conftest autouse guard/dummy-key fixture so local `pytest` matches CI and accidental real API calls are impossible.

---

## Corrections (Tier 2 claims disproved by lead-auditor verification)

> **"No signup / password-reset rate limits" (Security agent)** — FALSE. Both present: `accounts/views.py:45` (signup 3/h IP), `:56` (password reset 3/h IP). Login also correct (5/m + 20/h, `:33-34`).
> **"Consent check fails open / can be bypassed" (Security agent, P0)** — FALSE. `agents/views.py:47-51` returns False on error → AI access is *denied*. Fail-closed. It's an observability concern (P2-6), not a bypass. This also closes prior-audit P0-1.
> **"No rate limit on API JWT login" (Security agent, P0)** — OVERSTATED. DRF `DEFAULT_THROTTLE_CLASSES` applies `AnonRateThrottle` at 20/hour (`settings.py:712-718`), matching the web login's hourly cap. No dedicated finding; noted under JWT config review only.
> **"Appeal deadline not cleared when switching to supplemental" (Regulatory agent, its own worst finding)** — FALSE. Verified `appeals/models.py:293-301`: the supplemental branch runs first and unconditionally sets `deadline=None`; `test_supplemental_clears_existing_deadline` covers it. Kept only as a fragility note (P2-11).
> **"No coverage threshold enforcement" (Backend agent)** — FALSE. `--cov-fail-under=60` at `tests.yml:81`. Kept as "ratchet the floor," not "missing."
> **"conftest/CI doesn't set OPENAI_API_KEY" (Docs/Tests agent)** — HALF-FALSE. CI sets `sk-test-fake-key` (`tests.yml:40`); the gap is local-only + missing global mock guard (P2-16).
> **Tier 1 pytest "6 failures"** — environment coupling, not product bugs; all pass with a dummy key.

---

## What's Working Well

- **852/852 tests green** (with env), 25s wall-clock, parallel-capable; security regression tests from February (VSO cross-org ×6, rate limiting ×8, supplemental deadline ×2) all present and passing.
- **AI Gateway remains exemplary** — zero bypass call sites, 14-pattern injection sanitizer, Pydantic-validated structured outputs, Result types, prompt-level "treat document text as untrusted data" instructions.
- **Celery user-data tasks fully compliant** — acks_late/bind/retries/backoff/failed-status on all claims + core tasks; replay command and stuck-task detection both landed since last audit.
- **Monitoring matured significantly** — alerting thresholds match docs exactly, three channels wired, Beat placement documented, Sentry `send_default_pii=False`.
- **VA regulatory data verified accurate** — 2026 rates (2.8% COLA math checks out), bilateral factor and rounding per 38 CFR § 4.25/4.26, SMC-K stacking correct, TDIU thresholds per § 4.16(a). Next COLA update due **December 2026**.
- **No secrets, no PII logging, IDOR protections intact.**

## UNVERIFIED (cannot confirm from code)
- Manual credential rotation in DO Console (outstanding since 2026-02).
- Worker sizing / concurrency in the live DO app spec.
- `ALERT_EMAIL_RECIPIENTS` / `SLACK_ALERT_WEBHOOK` set in production env.
- Exact official 2025 SMC(R1) rate ($9,559.22) — math is internally consistent (×1.028 → 2026), but cross-check against VA tables.

## Recommended sequence
1. **Today:** P0-1 (one line) + add `manage.py check --deploy` to CI.
2. **This week:** P1-1, P1-2, P1-3 (security/PII), P1-7 + P1-8 (~2h of template work).
3. **Next sprint:** P1-4 (Tailwind/CSP), P1-5/P1-6 (VSO scale), P1-9 (security tests), then P2 batch.
4. **Standing:** DO credential rotation (Feb TODO), November calendar reminder for the December 2026 COLA update.
