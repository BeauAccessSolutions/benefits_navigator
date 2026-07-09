# VA Benefits Navigator — TODO & Audit Tracker

**Last Updated:** 2026-06-09
**Updated By:** Claude Code Comprehensive Audit (see `audits/2026-06-09/comprehensive-audit.md`)

---

## Audit Summary (2026-06-09)

Tier 1 scans + 7-specialist review. Overall **3.4/5** (up from 2.9/5 on 2026-04-10). Verdict: SHIP WITH CAVEATS — **do not deploy until P0 below is fixed**. Full findings, evidence, and delta: `audits/2026-06-09/comprehensive-audit.md`.

### P0 — NEW (Deploy-blocking)
- [x] **Add `django.contrib.postgres` to INSTALLED_APPS** — fixed 2026-06-09; CI now runs `check --deploy --fail-level ERROR`.

### P1 — NEW (Fix within 1–2 weeks)
- [x] **Rate-limit signed-URL endpoints** — 30/m per IP added 2026-06-09.
- [x] **Encrypt `phone_number`** — EncryptedCharField + data migration 2026-06-09. Also encrypted: VeteranCase description/conditions/closure_notes/c_and_p_exam_notes, Document.condition_tags (privacy hardening Phase 0).
- [ ] **Bump lxml to >=6.1.0** — 5.1.0 has PYSEC-2026-87; parses scraped M21 HTML.
- [ ] **Disclaimers on remaining AI pages** — statement_generator, condition_discovery, evidence_gap_result templates (decision analyzer pattern exists).
- [ ] **WCAG: 5 aria-required + 10+ aria-live gaps** — contact.html:47,60,89,102, decision_analyzer.html:38; HTMX targets in search/journey/appeals/claims partials.
- [ ] **N+1 in VSO views** — `vso/views.py:365-370` (triage per case), `:430-445` (CSV export), `:1407-1468` (reports). select_related/prefetch/annotate.
- [ ] **transaction.atomic on accept_invitation** — `vso/views.py:1245-1280` (3 writes, no boundary).
- [x] **Security tests: signed-URL expiry/tampering + encryption round-trip + GraphQL PII redaction** — `tests/test_security_controls.py` (18 tests) 2026-06-09.

### P2 — NEW (Fix before scaling)
- [ ] M21 scraper tasks lack acks_late/retry config — `agents/tasks.py:23,86,186,197,222`
- [ ] `core/health.py:77` except/pass hides Redis failure (queue alerts can't fire when Redis is down)
- [x] Download-anomaly alerts include user email — fixed 2026-06-09 (user ID only)
- [ ] No per-user token-spend cap — `accounts/models.py:895` counts analyses, not tokens
- [ ] `exc_info=True` may leak PII into logs — `agents/ai_gateway.py:400`
- [ ] Silent except/pass handlers — `core/views.py:711,719`, `api/views.py:65,165,177,230`, `claims/forms.py:83` (audit-log write failures swallowed)
- [ ] `mark_safe` on DB content — `core/templatetags/supportive_tags.py:78` (use format_html/escape)
- [ ] bandit High: use `hashlib.md5(key, usedforsecurity=False)` — `core/encryption.py:79`
- [ ] Enforce bandit in CI (currently `continue-on-error: true`, security-checks.yml:141); ratchet coverage floor above 60
- [ ] "(estimated)" label on rates table — `rating_calculator.html:170-180` (also verify year label isn't hardcoded "2024")
- [ ] Supplemental appeal: render "No deadline (can file anytime)" instead of "—" — `appeal_detail.html:99-100`
- [ ] HTMX focus management after swaps (carried over from 2026-04-10, still zero instances)
- [ ] JWT refresh lifetime 7d → consider 24-48h — `settings.py:724`
- [ ] CLAUDE.md drift: route table app attribution; FEATURES lists 6 of 14 flags; archive stale root docs to docs/archive/
- [ ] conftest guard/dummy key so `agents/tests.py` doesn't need real env var locally (6 tests fail without OPENAI_API_KEY)

### Fixed since 2026-04-10 (verified this audit)
Download endpoint rate limits, consent-check logging (fails closed), CI coverage gate (60) + lint gate (ruff/black), acks_late on core tasks, stuck-task detection, replay_failed_documents command, Beat placement docs, Django >=5.2.13, aria-required 21→5, decision-analyzer disclaimer, rating-result "(est.)" labels.

---

## Audit Summary (2026-02-09)

Full audit performed across 7 areas. See `docs/AUDIT_2026_02_09.md` for complete findings.

| Area | Status | Critical | Needs Work |
|------|--------|----------|------------|
| Security | CRITICAL | 4 | 3 |
| Data Integrity | CRITICAL | 2 | 1 |
| Test Coverage | NEEDS WORK | 0 | 4 |
| Production Readiness | NEEDS WORK | 1 | 2 |
| Accessibility (WCAG AA) | NEEDS WORK | 3 | 4 |
| Code Quality & Deployment | CRITICAL | 2 | 5 |
| **Totals** | | **12** | **19** |

**Production-Readiness Score: 8.5 / 10** (8.0 after P1 fixes, 8.5 after git history scrub on 2026-02-12; reaches 9.0 after manual credential rotation)

---

## P0 — CRITICAL (Fix Before Veterans Use This)

All P0 code fixes completed 2026-02-11. Git history scrubbed 2026-02-12. Manual credential rotation in DO Console still required.

### Security: Secrets Exposure
- [x] **Add deployment configs to .gitignore** — `.env.docker`, `app-spec-fixed.yaml`, `.do/app.yaml`, `docker-compose.yml` (2026-02-11)
- [x] **Create deployment config templates** — `app-spec.yaml.template` and `docker-compose.yml.template` with `CHANGE_ME` placeholders (2026-02-11)
- [x] **Scrub git history** — `git-filter-repo --replace-text` removed 12 secret values from all 141 commits, force-pushed (2026-02-12)
- [x] **Add key rotation command** — `python manage.py rotate_encryption_key --old-key X --new-key Y --execute` (2026-02-12)
- [ ] **Revoke all exposed credentials** — SECRET_KEY, FIELD_ENCRYPTION_KEY, DATABASE_URL, REDIS_URL
  - Action: Rotate in DO Console, run `rotate_encryption_key` to re-encrypt PII, then deploy
  - Note: OpenAI key and Sentry DSN were never committed (placeholder only)

### Data Integrity: Regulatory Accuracy
- [x] **Add 2025 & 2026 VA compensation rates** — `examprep/va_math.py` (2026-02-11)
  - 2025: 2.5% COLA (verified against va.gov), 2026: 2.8% COLA
  - Base rates, dependent rates (2024-2026), SMC rates all updated
  - `AVAILABLE_RATE_YEARS` updated to [2026..2020], default year = 2026
  - Year-aware dependent rate lookup via `DEPENDENT_RATES_BY_YEAR`
  - SMC rates updated in `examprep/va_special_compensation.py` with `SMC_RATES_BY_YEAR`
- [x] **Fix supplemental claim deadline** — `appeals/models.py:293-301` (2026-02-11)
  - `save()` now checks `appeal_type == 'supplemental'` → sets `deadline = None`
  - HLR and Board appeals still get 1-year auto-deadline
  - Tests added: `test_supplemental_no_deadline`, `test_supplemental_clears_existing_deadline`

### Production Readiness: Crash Safety
- [x] **Add `acks_late=True` to Celery tasks** — `claims/tasks.py`, `core/tasks.py` (2026-02-11)
  - All 3 claims tasks and 6 core user-data tasks now have `acks_late=True`

### Code Quality: CI Pipeline
- [x] **Add pytest job to GitHub Actions** — `.github/workflows/tests.yml` (2026-02-11)
  - Runs `pytest --cov=. --cov-report=xml -x -q` on push/PR to main
  - PostgreSQL 15 service, pip caching, coverage artifact upload

---

## P1 — HIGH PRIORITY (Fix Within 1 Week)

All P1 code fixes completed 2026-02-11.

### Security
- [x] **Fix VSO IDOR risk** — `vso/views.py` (2026-02-11)
  - Added org validation to AI analysis lookups in `shared_document_review()`
  - Verify `document.user_id == case.veteran_id` before querying analyses
  - Added `user=case.veteran` filter to RatingAnalysis and DecisionLetterAnalysis queries
  - Added 6 cross-organization security tests in `vso/tests.py`
- [x] **Encrypt `ai_summary` field** — `claims/models.py` (2026-02-11)
  - Created `EncryptedJSONField` in `core/encryption.py` (Fernet AES-256)
  - Changed `ai_summary` from `JSONField` to `EncryptedJSONField`
  - Data migration `claims/migrations/0005_encrypt_ai_summary.py` encrypts existing data
- [x] **Resolve conflicting deployment configs** (2026-02-11)
  - Both `.do/app.yaml` and `app-spec-fixed.yaml` removed from git in P0 commit
  - Templates with `CHANGE_ME` placeholders are the canonical configs
  - **Note:** DO Console worker command needs manual update to actual Celery command

### Database
- [x] **Add indexes to agent models** — `agents/models.py` (2026-02-11)
  - `AgentInteraction`: indexes on `[user, created_at]`, `[user, agent_type]`, `[user, status]`
  - `DecisionLetterAnalysis`: index on `[user, created_at]`
  - `EvidenceGapAnalysis`: index on `[user, created_at]`
  - Migration: `agents/migrations/0009_add_indexes.py`

### Testing
- [x] **Add Celery task tests** — `tests/test_core_tasks.py` (2026-02-11)
  - 14 tests covering: `enforce_data_retention`, `enforce_pilot_data_retention`,
    `notify_pilot_users_before_retention`, `cleanup_old_health_metrics`, `check_processing_health`
- [x] **Add TDIU/SMC boundary tests** — `examprep/tests.py` (2026-02-11)
  - 8 TDIU boundary tests (59%/60% single, 69%+40/70%+40 combined, extraschedular)
  - 4 SMC boundary tests (100%+50%/60%, combined others, no 100%)
- [x] **Add supplemental claim deadline test** — `appeals/tests.py` (2026-02-11)

### Accessibility (WCAG AA Critical)
- [x] **Fix rating calculator form labels** — `templates/examprep/rating_calculator.html` (2026-02-11)
  - Added `for="has-spouse"` to label element
- [x] **Fix feedback widget keyboard access** — `templates/core/partials/feedback_widget.html` (2026-02-11)
  - Changed `<div onclick>` to `<button>` with `aria-label="Open feedback form"`
  - Added `aria-hidden="true"` to decorative SVG icon
- [x] **Add aria-live to HTMX updates** — `templates/appeals/partials/checklist.html` (2026-02-11)
  - Added `aria-live="polite" aria-atomic="false"` to checklist container
- [x] **Add accessible loading states** — `templates/examprep/rating_calculator.html` (2026-02-11)
  - Added `role="status" aria-live="polite"` to loading spinner
  - Added `<span class="sr-only">Loading scenario results...</span>`
  - Added `aria-hidden="true"` to spinner SVG

---

## P2 — MEDIUM PRIORITY (Fix Before Scaling)

### Security & Infrastructure
- [ ] **Build Tailwind to static CSS** — Remove `unsafe-inline` from CSP and CDN SPOF
  - Settings.py:396 has TODO comment about this
  - Use PostCSS/Tailwind CLI to generate minified CSS
  - Include fallback styles for error pages (500.html depends on CDN)
- [ ] **Upgrade web instance sizing** — `basic-xxs` (512MB) at 80-95% utilization
  - Upgrade web service to `basic-xs` (1GB) in deployment config
- [ ] **Fix hardcoded domain fallbacks**
  - `core/tasks.py:362,411,535`: `SITE_URL` falls back to `benefitsnavigator.com` (should be `vabenefitsnavigator.org`)
  - `settings.py:694`: `SUPPORT_EMAIL` hardcoded, make configurable via env var
- [ ] **Consolidate Docker Compose config** — Hardcoded credentials repeated in 4 services
  - Move all secrets to `.env.docker`, use `env_file` only

### Code Quality
- [ ] **Fix bare exception handlers** — 21 instances of `except Exception:` across views
  - `core/views.py`, `agents/views.py`, `claims/views.py`
  - Replace with specific exception types
- [ ] **Standardize import style** — Mixed relative/absolute imports across apps
- [ ] **Add code linting to CI** — black, ruff, isort checks

### Accessibility (WCAG AA Improvements)
- [ ] **Add `aria-required="true"` to required form fields** — All form templates
- [ ] **Add `aria-describedby` for form errors** — Link errors to inputs
- [ ] **Add focus management after HTMX swaps** — Appeals checklist, calculator
- [ ] **Add Escape key handler to feedback widget**

### Performance
- [ ] Add Redis caching for glossary terms
- [ ] Add Redis caching for exam guides
- [ ] Optimize database queries (select_related/prefetch_related in remaining views)
- [ ] Lazy load images in templates

### Content Accuracy
- [ ] **Refine sleep apnea guide language** — `examprep/fixtures/exam_guides_sleep_apnea.json`
  - Change "should receive at least 50%" to "may qualify for 50% if documented CPAP compliance"
- [ ] **Create annual rate update process**
  - Management command or Celery Beat task for Dec 1 annual COLA updates
  - Include SMC and dependent rates

### Monitoring
- [ ] Add usage analytics (privacy-respecting)
- [ ] Create admin dashboard with stats
- [ ] Add daily alert for documents stuck in 'failed' status >24 hours
- [ ] Schedule `run_all_monitoring_checks` as Celery Beat task (every 5 min) — currently must be called manually

### Infrastructure (from 2026-03-26 system design audit)
- [ ] **Upgrade Celery worker to `basic-xs` (1GB RAM)** — basic-xxs (512MB) is undersized for concurrent OCR+LLM; OOM risk at concurrency=2
- [ ] **Add `replay_failed_tasks` management command** — manual shell replay is the only option today; see `docs/FAILURE_TRACKING.md`
- [ ] **Add task idempotency check** — tasks don't guard against duplicate execution on worker restart; add existence check at task start
- [ ] **Add circuit breaker on OpenAI calls** — sustained OpenAI outage floods queue with retries; gateway has backoff but no global shed

### Documentation (P2 — remaining gaps)
- [ ] **API contract docs** — GraphQL schema + REST v1 endpoints undocumented for consumers
- [ ] **Celery task catalog** — all tasks, schedules, retry configs, and inter-task dependencies in one place
- [ ] **Security runbook** — prompt injection response playbook, anomalous download investigation steps (referenced in INCIDENT_RESPONSE but not written)
- [ ] **VSO onboarding guide** — invitation flow, org permissions model, case sharing mechanics

---

## LOW PRIORITY (Future Features)

### Premium Features
- [ ] Implement Stripe subscription flow
- [ ] Add premium tier limits enforcement
- [ ] GPT-4 access for premium users

### AI Enhancements
- [ ] Chat assistant for claims questions
- [ ] Auto-suggest conditions based on documents
- [ ] Generate personal statements
- [ ] Nexus letter template generator

### Community Features
- [ ] Forum for veterans to share experiences
- [ ] Success stories section
- [ ] VSO directory/finder
- [ ] Buddy statement templates

### Mobile
- [ ] Progressive Web App (PWA) support
- [ ] Mobile-optimized views
- [ ] Push notifications

---

## TECHNICAL DEBT

### Code Quality
- [ ] Add type hints to all Python files
- [ ] Set up pre-commit hooks (black, ruff)
- [ ] Create REST API documentation

### Security
- [ ] Add CAPTCHA to signup (if spam becomes issue)
- [ ] Implement account lockout after failed logins
- [ ] Object storage migration (S3/DO Spaces) for secure file serving
- [ ] Additional VSO invitation verification (beyond email matching)

### Infrastructure
- [ ] Set up database backups
- [ ] Create disaster recovery plan
- [ ] Load test document processing pipeline

---

## COMPLETED

### Pilot/Test User Readiness ✅
- [x] Define and script pilot funnels (2026-01-12)
- [x] Stand up staging environment on DO App Platform (2026-01-12)
- [x] Enable Sentry DSN (2026-01-12)
- [x] Add in-app feedback widget (2026-01-12)
- [x] Provide visible support channel (2026-01-12)
- [x] Disable real billing, gate premium features, 30-day data retention (2026-02-09)
- [x] Add health checks/alerts for Celery and document processing (2026-01-12)

### Testing & Quality ✅
- [x] VA Math calculator unit tests — 80 tests (2026-01-11)
- [x] Rating calculator integration tests — 45 tests (2026-01-11)
- [x] Document upload E2E tests — 25 tests (2026-01-11)
- [x] Lighthouse accessibility audit — 95-96% (2026-01-11)
- [x] Rate limiting tests — 11 tests (2026-01-11)
- [x] CSP header tests — 25 tests (2026-01-11)

### Content ✅
- [x] 7 C&P exam guides: General, PTSD, Musculoskeletal, Hearing, TBI, Sleep Apnea, Mental Health
- [x] 86 VA glossary terms (2026-01-11)
- [x] Secondary conditions hub — 40+ relationships (2026-01-11)
- [x] M21 manual content — comprehensive, updated Jan 2026

### Features ✅
- [x] SMC calculator (2026-01-11)
- [x] TDIU eligibility checker (2026-01-11)
- [x] Historical compensation rates 2020-2026 (2026-02-11, was 2020-2024)
- [x] Compare scenarios side-by-side (2026-02-05)
- [x] Import ratings from VA letter OCR (2026-02-09)
- [x] Email notifications — deadlines, exams, analysis complete (2026-01-11)
- [x] PDF export for rating calculations (2026-01-11)
- [x] Supportive messaging system (2026-01-11)

### SEO & Marketing ✅
- [x] Meta descriptions, sitemap.xml, robots.txt, JSON-LD, Open Graph (2026-01-12)

### Security Hardening ✅
- [x] Content-Security-Policy headers (2026-01-09)
- [x] Rate limiting on all public endpoints (2026-01-09)
- [x] File content validation with python-magic (2026-01-09)
- [x] Field-level PII encryption (EncryptedCharField) (2026-01-09)
- [x] Signed URLs for media access (2026-01-12)
- [x] GraphQL PII redaction (2026-01-12)
- [x] Audit logging middleware (2026-01-12)

### P0 Fixes (2026-02-11) ✅
- [x] Deployment configs added to .gitignore, templates created with CHANGE_ME placeholders
- [x] 2025/2026 VA compensation rates added (base, dependent, SMC) — verified against va.gov
- [x] Supplemental claim deadline bug fixed (38 CFR § 20.204) with tests
- [x] `acks_late=True` added to all Celery tasks handling user data
- [x] pytest CI workflow added (`.github/workflows/tests.yml`)
- [x] Supplemental claim deadline tests added to `appeals/tests.py`

### Infrastructure ✅
- [x] Staging environment on DigitalOcean (2026-01-12)
- [x] Switch to DO Managed Valkey (2026-02-05)
- [x] CELERY_RESULT_EXPIRES auto-cleanup (2026-02-05)
- [x] Celery Beat monitoring tasks scheduled (2026-02-09)

### Documentation ✅ (2026-03-26)
- [x] System design evaluation — architecture gaps, failure tracking gaps, scaling risks identified
- [x] `docs/FAILURE_TRACKING.md` — runbook for querying, triaging, and replaying ProcessingFailure records
- [x] `docs/PHI_DATA_FLOW.md` — PHI/PII boundary map, what's ephemeral vs persisted, OpenAI data boundary
- [x] `docs/adr/001-celery-retry-strategy.md` — retry/backoff/no-DLQ decision record
- [x] `docs/adr/002-ai-consent-model.md` — dual-check consent pattern decision record
- [x] `docs/CAPACITY_SCALING.md` — when/how to scale workers and web on DO, memory sizing rationale
- [x] `docs/README.md` updated with all new docs and when-to-use guidance

---

## KNOWN LIMITATIONS

- Rating calculator supports 2020-2026 rates (current as of Feb 2026)
- Dependent rate additions available for 2024-2026
- Bilateral factor only supports simple bilateral, not complex multi-limb groupings
- Document OCR may struggle with handwritten text
- OpenAI costs not tracked per-user
- Not HIPAA compliant — educational use only
- Pilot mode with 30-day data retention

---

## CONTRIBUTING

When working on this project:
1. Always run `pytest` before committing
2. Update this TODO.md when completing tasks
3. Follow existing code patterns (see CLAUDE.md)
4. Maintain WCAG AA accessibility
5. All OpenAI calls must go through AI Gateway (`agents/ai_gateway.py`)
6. PII fields must use `EncryptedCharField` from `core/encryption.py`
7. Never commit secrets — use environment variables only
8. Add `acks_late=True` to any new Celery tasks handling user data
