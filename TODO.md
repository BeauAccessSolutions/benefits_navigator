# VA Benefits Navigator — TODO & Audit Tracker

**Last Updated:** 2026-07-23
**Updated By:** Claude Code — logged the 2026-07-23 external (Codex) audit findings below; every finding was independently verified against the current working tree before recording. No fixes applied yet.

---

## Audit Summary (2026-07-23 — external Codex audit, verified line-by-line)

Verdict: **not production-ready for sensitive veteran data.** 1 critical + 7 high findings, all
confirmed against current code on `fix/seed-documentation-content`. Remediation order recommended
by the auditor: deletion/export lifecycle → VSO authorization scoping → invitation binding →
protected media & storage → appeal-rule correction → encryption/AI/config hardening.

### P0 — CRITICAL
- [x] **Account deletion is a no-op** — Fixed & merged (PR #40, `feat/account-deletion-lifecycle`).
  `User.deletion_requested_at` + migration 0012, `core.tasks.purge_user_account` +
  `process_scheduled_account_deletions` (daily Beat, 30-day grace, cancel-by-login), and
  `account_delete_purge` / `_cancel` audit actions. 14 tests pass. This checkbox was stale — the
  work landed but the box was never ticked.

### P1 — HIGH
- [x] **VSO: restricted caseworkers can act on other workers' cases** — Fixed 2026-07-23. Added
  `get_scoped_case_or_404()` (`vso/permissions.py`), which applies the org filter **and**
  `scope_cases_for_member`; every case-by-pk endpoint now routes through it (`case_detail`,
  `case_update_status`, `case_archive`, `add_case_note`, `complete_action_item`,
  `shared_document_review`, `case_notes_partial`, `case_documents_partial`, `start_appeal_from_case`,
  `evidence_packet_builder`). `bulk_case_action` scopes its `pk__in` queryset; dashboard
  `recent_notes` filters through scoped cases; `case_list`'s `archived=1` branch re-applies the
  scope. Tests: parameterized 404 suite over every endpoint + AST meta-test that fails on any raw
  `get_object_or_404(VeteranCase)` / `VeteranCase.objects` pk lookup in `vso/views.py`
  (`TestIntraOrgCaseworkerIsolation`, `TestScopedCaseHelper`,
  `test_no_unscoped_case_by_pk_lookups_in_views`). *Distinct from the cross-org IDOR fixed
  2026-02-11 — that fix (analysis queries in `shared_document_review`) is still in place.*
- [x] **Org invitations not bound to invited email** — Fixed 2026-07-23 (branch
  `claude/bind-invitation-email`). `OrganizationInvitation.accept()` now raises unless
  `user.email == invitation.email` (case-insensitive) **and** the address is verified via allauth
  `EmailAddress` — the single enforcement point for both accept flows (`org_invite_accept` for staff
  and `vso.accept_invitation` for veterans). Removed the accept-anyway POST path in
  `org_invite_accept`; the mismatch page now offers "log in as the invited account" only.
  *Gotcha found & documented:* django-otp's `OTPMiddleware` replaces `request.user.is_verified` with
  a truthy 2FA-status method, so the model checks allauth `EmailAddress.verified` (collision-free),
  not the `User.is_verified` field. Tests: `TestInvitationEmailBinding`, `TestOrgInviteAcceptView`
  (mismatch/unverified/verified/allauth/case-insensitive).
- [ ] **"Export my data" crashes for real users** — `accounts/views.py:150-182` reads
  `claim.condition` / `claim.filed_date` (Claim has `title` / `submission_date` —
  `claims/models.py:299`) and `appeal.condition` / `appeal.appeal_lane` (Appeal has
  `conditions_appealed` / `appeal_type`). Any user with a claim or appeal gets a 500. Also
  silently truncates at 1,000 records/category and omits/redacts data while calling itself a
  complete export.
- [ ] **Appeal documents: unsafe serving, deletion, and upload validation** —
  `templates/appeals/partials/document_list.html:17` links `doc.file.url` directly (404 today;
  auth bypass if media becomes public); `appeal_delete_document` (`appeals/views.py:487`)
  deletes only the DB row, not the stored file; `AppealDocumentForm` (`appeals/forms.py:275`)
  has no server-side type/size validation (client-side `accept=` only). Protected-media fix
  exists on branch (PR #36) but is unmerged.
- [ ] **S3 storage config is silently ignored** — `settings.py:523+` sets `DEFAULT_FILE_STORAGE`
  and `STATICFILES_STORAGE`, both removed in Django ≥5.1 (project pins `Django>=5.2.13`); with
  `USE_S3=True` Django still uses local `FileSystemStorage`. Must migrate to the `STORAGES` dict.
  Additionally `claims/tasks.py:97` uses `document.file.path`, which remote storage doesn't support.
- [ ] **Appeal eligibility wrongly blocks valid Supplemental Claims** — `appeals/forms.py:60`
  (`clean_original_decision_date`) rejects any decision >1 year old before the user picks a lane,
  but Supplemental Claims have no time limit (the model-level fix from 2026-02-11 covered
  `Appeal.save()` only, not the intake form). The AI analyzer also stamps a blanket 1-year
  `appeal_deadline` (`agents/services.py:314-323`).
- [ ] **Sensitive narratives inconsistently encrypted** — `VeteranCase` narrative fields ARE
  encrypted, but: `CaseNote.content` is plain `TextField` (`vso/models.py:254`), agent analyses
  store conditions granted/denied as plain `JSONField` (`agents/models.py:88+`), and
  `AssistantTurn.content` (PHI-flagged transcript, `agents/models.py:876+`) is plain `TextField`
  whose deletion story depends on the nonexistent account deletion above.

### P2 — from the same audit (some already tracked elsewhere in this file)
- [ ] Legacy high-stakes AI analyses use `_parse_json_response` on unconstrained JSON instead of
  the gateway's Pydantic `complete_structured` path (`agents/services.py:308`)
- [ ] Redis/Celery TLS uses `ssl.CERT_NONE` (`settings.py:263`) — no cert verification
- [ ] `VSO_MFA_REQUIRED` and `ADMIN_OTP_REQUIRED` both default False (`settings.py:660+`)
- [ ] `HealthCheckMiddleware` intercepts `/health/` by path only (`core/middleware.py:26`), so
  `/health/?full=1` never reaches the full-status view — detailed health check is unreachable
  in production
- [ ] Open-ended dependency pins: local Python resolves Django 6.0 while CI/prod (3.11) resolves
  5.2 — pin an upper bound
- [ ] CSP `unsafe-inline` + unpkg.com script-src (`settings.py:388`) — already tracked in P2 below
- [ ] AGENTS.md:379 still says git-history scrub is pending — stale; scrub completed 2026-02-12
  per this file. Credential rotation in DO Console genuinely still open.

### Verification notes (2026-07-23)
- All line references above re-checked against the working tree this date; none were stale.
- Auditor ran: ruff pass, security-invariant script pass, 1013 passed / 112 setup errors (all
  Playwright-not-installed, matching the known sandbox limitation; CI excludes E2E).

---

## Audit Summary (2026-06-09)

Tier 1 scans + 7-specialist review. Overall **3.4/5** (up from 2.9/5 on 2026-04-10). Verdict: SHIP WITH CAVEATS — **do not deploy until P0 below is fixed**. Full findings, evidence, and delta: `audits/2026-06-09/comprehensive-audit.md`.

### P0 — NEW (Deploy-blocking)
- [x] **Add `django.contrib.postgres` to INSTALLED_APPS** — fixed 2026-06-09; CI now runs `check --deploy --fail-level ERROR`.

### P1 — NEW (Fix within 1–2 weeks)
- [x] **Rate-limit signed-URL endpoints** — 30/m per IP added 2026-06-09.
- [x] **Encrypt `phone_number`** — EncryptedCharField + data migration 2026-06-09. Also encrypted: VeteranCase description/conditions/closure_notes/c_and_p_exam_notes, Document.condition_tags (privacy hardening Phase 0).
- [x] **Bump lxml to >=6.1.0** — already at 6.1.0 in `requirements.txt` (verified 2026-07-22).
- [x] **Disclaimers on remaining AI pages** — added to `statement_generator.html` and `statement_result.html`; `condition_discovery.html` and `evidence_gap_result.html` already had one (2026-07-22).
- [x] **WCAG: aria-required + aria-live gaps** — `contact.html` (4 required fields), `decision_analyzer.html:38`; aria-live added to 9 HTMX swap targets across appeals/claims/core/examprep/documentation partials, placed on the actual persistent `hx-target` (not the fragment that gets destroyed on swap — `appeals/appeal_detail.html`'s `#checklist-section` was previously missing it entirely, with aria-live misplaced on the inner div that gets replaced) (2026-07-22).
- [x] **N+1 in VSO views** — `GapCheckerService.get_triage_label` now filters in Python over `case_conditions.all()` (works with `prefetch_related`) instead of `.exclude()` on the manager; `prefetch_related("case_conditions")` added to case_list/bulk_case_action querysets; `reports()` caseworker urgent/overdue counts now one annotated query instead of 2 queries per caseworker. Also fixed a related template bug found via the regression test: `case.assigned_to.get_full_name|default:case.assigned_to.email` 500s when `assigned_to` is null (Django doesn't safely resolve filter *arguments* the way it does the base variable) — fixed in `case_list.html`, `case_detail.html`, `document_share.html` (2026-07-22).
- [x] **transaction.atomic on accept_invitation** — wrapped invitation.accept() + case creation + milestone note in `transaction.atomic()` (2026-07-22).
- [x] **Security tests: signed-URL expiry/tampering + encryption round-trip + GraphQL PII redaction** — `tests/test_security_controls.py` (18 tests) 2026-06-09.

### P2 — NEW (Fix before scaling)
- [x] M21 scraper tasks lack acks_late/retry config — `acks_late=True` initially added to all 5 tasks
  in `agents/tasks.py` (2026-07-22), then **partially reverted after peer review (2026-07-23)**:
  `scrape_m21_bulk` creates/mutates a job record per run (not idempotent — Celery requires late-ack
  tasks to be idempotent), so it and its two synchronous callers (`scrape_m21_all_known`,
  `update_stale_m21_sections`) are back to early ack. `scrape_m21_section` (update_or_create) and
  `build_m21_topic_indices` (get_or_create) are idempotent and keep `acks_late=True`.
- [x] `core/health.py` except/pass hides Redis failure — now logs a warning instead of silently swallowing (2026-07-22)
- [x] Download-anomaly alerts include user email — fixed 2026-06-09 (user ID only)
- [ ] No per-user token-spend cap — `accounts/models.py:895` counts analyses, not tokens
- [x] `exc_info=True` leaking PII — not present in `agents/ai_gateway.py` anymore; current error logging only logs `type(e).__name__`, already sanitized (verified 2026-07-22, appears already fixed in an earlier pass)
- [x] Silent except/pass handlers — the two genuine audit-log-write swallows (`api/views.py` login/logout `AuditLog.objects.create()`) now `logger.exception()` instead of `pass`. The other referenced lines (`core/views.py`, `claims/forms.py`) turned out on inspection to be unrelated defensive `RelatedObjectDoesNotExist` guards, not audit-log writes — left as-is (2026-07-22)
- [x] `mark_safe` on DB content — `core/templatetags/supportive_tags.py` now uses `format_html()`, so `message.message` is auto-escaped while the trusted hardcoded SVG stays unescaped (2026-07-22)
- [x] bandit High: `hashlib.md5(key, usedforsecurity=False)` — `core/encryption.py:83` (2026-07-22)
- [ ] Enforce bandit in CI (currently `continue-on-error: true`, security-checks.yml:141); ratchet coverage floor above 60
- [ ] "(estimated)" label on rates table — `rating_calculator.html:170-180` (also verify year label isn't hardcoded "2024")
- [x] Supplemental appeal: render "No deadline (can file anytime)" instead of "—" — `appeal_detail.html` (2026-07-22)
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
