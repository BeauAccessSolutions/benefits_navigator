# Benefits Navigator — Claude Code Guide

**Last Audit:** 2026-02-11 | **Production-Readiness:** 8.0/10 | See `TODO.md` for prioritized issues

## Project Summary
Django 5.1.14 app deployed on DigitalOcean App Platform, using the Anthropic Claude API (claude-sonnet-5 default; model env-configurable).
Celery + Redis (DO Managed Valkey) for async document processing. PostgreSQL database. Stripe for subscriptions.

**Two user flows:**
- **Path A:** Veterans (B2C end-user flow) — document upload, AI analysis, denial decoding, statement generation
- **Path B:** VSOs (B2B caseworker/advocate flow) — case management, shared documents, veteran invitations

## Non-negotiables
- Treat all user data as sensitive. Avoid logging PII.
- Never store raw prompts/responses containing PII unless explicitly required and securely handled.
- Assume prompt injection is possible; sanitize/validate any model outputs before using them.
  - All user input goes through `sanitize_input()` from `agents/ai_gateway.py`
  - Use Pydantic schemas from `agents/schemas.py` for response validation
- Prefer small, test-backed changes. Avoid broad refactors.
- PII fields (`va_file_number`, `date_of_birth`) use `EncryptedCharField` from `core/encryption.py`
- **Never commit secrets** — .env, deployment YAMLs with credentials must stay out of git
- **All Celery tasks handling user data must use `acks_late=True`** — prevents message loss on worker crash
- **VA regulatory data must be verified against CFR** — rates, deadlines, eligibility criteria

## How to work (required workflow)
1. Find the exact entry points for Path A and Path B (routes/views/templates).
2. Identify the boundary contract(s) between the paths and any shared modules.
3. Use the **AI Gateway** (`agents/ai_gateway.py`) for all Claude calls:
   - `gateway.complete()` for raw completions
   - `gateway.complete_structured()` for Pydantic-validated responses
   - Returns `Result[T]` types — check `result.is_success` before accessing value
4. Before changing logic, add tests:
   - path-level tests (URLs/views)
   - unit tests for eligibility/routing logic
   - tests for the Claude wrapper parsing/validation (mock model output)
5. After changes: run `pytest` and lint.

## Output requirements for every task
- What changed and why
- Files modified
- Tests run and results
- Remaining risks / TODOs

---

# Architecture (current)

## Path A (Veterans)

### Entry Points
| Route | View | File |
|-------|------|------|
| `/` | `home()` | `core/views.py` |
| `/dashboard/` | `dashboard()` | `core/views.py` |
| `/journey/` | `journey_dashboard()` | `core/views.py` |
| `/claims/upload/` | `document_upload()` | `claims/views.py` |
| `/claims/` | `document_list()` | `claims/views.py` |
| `/claims/document/<pk>/` | `document_detail()` | `claims/views.py` |
| `/agents/decision-analyzer/` | `decision_analyzer()` | `agents/views.py` |
| `/agents/evidence-gap/` | `evidence_gap_analyzer()` | `agents/views.py` |
| `/agents/statement-generator/` | `statement_generator()` | `agents/views.py` |

### Data Flow
1. **Document Upload:** User uploads → `Document` model created → Celery task `process_document_task()` queued
2. **Processing Pipeline:** OCR (Tesseract) → AI Analysis (Claude) → Results stored in `Document.ai_summary`
3. **Agent Tools:** User input → `BaseAgent._call_openai()` → Parsed JSON response → stored in agent-specific models

### Models Used
- `claims/models.py`: `Document`, `Claim`
- `agents/models.py`: `AgentInteraction`, `DecisionLetterAnalysis`, `EvidenceGapAnalysis`, `PersonalStatement`, `RatingAnalysis`
- `core/models.py`: `JourneyStage`, `UserJourneyEvent`, `Milestone`
- `accounts/models.py`: `UsageTracking`, `Subscription`

### Claude Usage
- All calls go through **AI Gateway** (`agents/ai_gateway.py`)
- `agents/services.py`: `DecisionLetterAnalyzer`, `DenialDecoderService`, `EvidenceGapAnalyzer`, `PersonalStatementGenerator`
- `claims/services/ai_service.py`: Document analysis
- Gateway provides: timeout (60s), retry (3x exponential backoff), Result types, Pydantic validation

### Outputs (what the user gets)
- OCR text extraction with confidence scores
- AI-generated document summaries (JSON in `Document.ai_summary`)
- Decision letter analysis: conditions granted/denied, appeal options, deadlines
- Evidence gap analysis: missing evidence, readiness score (0-100), recommendations
- Personal statement drafts for VA claims

---

## Path B (VSOs)

### Entry Points
| Route | View | File |
|-------|------|------|
| `/vso/` | `dashboard()` | `vso/views.py` |
| `/vso/cases/` | `case_list()` | `vso/views.py` |
| `/vso/cases/new/` | `case_create()` | `vso/views.py` |
| `/vso/cases/<pk>/` | `case_detail()` | `vso/views.py` |
| `/vso/cases/<pk>/notes/add/` | `add_case_note()` | `vso/views.py` |
| `/vso/invitations/` | `invitations_list()` | `vso/views.py` |
| `/vso/invitations/new/` | `invite_veteran()` | `vso/views.py` |
| `/vso/invite/<token>/` | `accept_invitation()` | `vso/views.py` |

### Data Flow
1. **Case Creation:** VSO creates case → links to veteran user → assigns caseworker
2. **Document Sharing:** Veteran shares document → `SharedDocument` created → VSO reviews
3. **Analysis Sharing:** Veteran shares AI analysis → `SharedAnalysis` created → VSO adds notes

### Models Used
- `vso/models.py`: `VeteranCase`, `CaseNote`, `SharedDocument`, `SharedAnalysis`
- `accounts/models.py`: `Organization`, `OrganizationMembership`, `OrganizationInvitation`

### Claude Usage
- VSOs view shared AI analyses (read-only access to veteran's `DecisionLetterAnalysis`, `RatingAnalysis`, etc.)
- No direct Claude calls from VSO views

### Outputs
- Case dashboard with status metrics, priority cases, win rates
- Case detail with veteran info, conditions, shared documents, notes, deadlines
- Case notes with action items and due dates

---

## Shared Modules / Boundary Contracts

### Shared Functions/Classes
| Module | Purpose |
|--------|---------|
| `core/models.py` | `TimeStampedModel`, `SoftDeleteModel` base classes |
| `core/encryption.py` | `EncryptedCharField`, `EncryptedDateField` for PII |
| `core/middleware.py` | `AuditMiddleware` (logs sensitive operations), `SecurityHeadersMiddleware` |
| `core/context_processors.py` | `user_usage()`, `feature_flags()`, `vso_access()` |
| `agents/ai_gateway.py` | **AIGateway** — centralized Claude calls with retry, timeout, validation |
| `agents/schemas.py` | Pydantic schemas for all AI response types |
| `agents/services.py` | `BaseAgent` class — uses AIGateway internally |
| `agents/m21_matcher.py` | M21 manual section matching for denial analysis |

### AI Gateway Architecture
```
┌─────────────────────────────────────────────────────────┐
│                      AI Gateway                          │
│  - sanitize_input()     - 60s timeout                   │
│  - Result[T] types      - 3x retry with backoff         │
│  - Pydantic validation  - Token/cost tracking           │
└─────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   BaseAgent         AIService      RatingDecisionAnalyzer
   (agents/)         (claims/)           (claims/)
```

**Usage:**
```python
from agents.ai_gateway import get_gateway, sanitize_input
from agents.schemas import DecisionLetterAnalysisResponse

gateway = get_gateway()
result = gateway.complete_structured(
    system_prompt="...",
    user_prompt=sanitize_input(user_text),
    response_schema=DecisionLetterAnalysisResponse,
)
if result.is_success:
    analysis = result.value.data  # Validated Pydantic model
else:
    handle_error(result.error)    # GatewayError with code, message
```

### Request/Response Schemas
- **Claude calls:** Return `Result[CompletionResponse]` or `Result[StructuredResponse[T]]`
- **Agent outputs:** Validated via Pydantic schemas in `agents/schemas.py`
- **Document processing:** Status progression: `uploading` → `processing` → `analyzing` → `completed`/`failed`

### Where Parsing/Validation Occurs
- `agents/ai_gateway.py`: Input sanitization, JSON extraction, Pydantic validation
- `agents/services.py`: Agent-specific prompt building, uses gateway
- `claims/tasks.py`: Document status updates, error handling
- `vso/views.py`: Permission checks for organization membership

### Feature Flags (in `settings.py`)
```python
FEATURES = {
    'organizations': env.bool('FEATURE_ORGANIZATIONS', default=False),
    'org_roles': env.bool('FEATURE_ORG_ROLES', default=False),
    'org_invitations': env.bool('FEATURE_ORG_INVITATIONS', default=False),
    'caseworker_assignment': env.bool('FEATURE_CASEWORKER_ASSIGNMENT', default=False),
    'org_billing': env.bool('FEATURE_ORG_BILLING', default=False),
    'org_admin_dashboard': env.bool('FEATURE_ORG_ADMIN', default=False),
}
```

---

# Development

## Running Tests
```bash
pytest                    # All tests
pytest -m "not slow"      # Skip slow tests
pytest -m agent           # Agent tests only
pytest core/              # Specific app
pytest --cov=.            # With coverage
pytest -n auto            # Parallel execution
```

## Test Markers
- `slow` — Long-running tests
- `e2e` — End-to-end tests
- `bdd` — Behavior-driven tests
- `agent` — AI agent tests
- `integration` — Integration tests
- `unit` — Unit tests

## Key Fixtures (`conftest.py`)
- `user` — Standard test user
- `premium_user` — User with active premium subscription
- `authenticated_client` — Logged-in client
- `premium_client` — Premium logged-in client
- `mock_ai_gateway` — Mocked Anthropic client for gateway
- `ai_gateway` — Gateway instance with mocked client

---

# Deployment (DigitalOcean)

## Services (`.do/app.yaml`)
1. **Web:** Gunicorn Django (basic-xxs, port 8000)
2. **Worker:** Celery (basic-xxs, concurrency=2)
3. **Pre-deploy job:** `python manage.py migrate --noinput`

## Required Environment Variables
```
SECRET_KEY
DATABASE_URL              # postgresql://...?sslmode=require
REDIS_URL                 # rediss://... (SSL)
CELERY_BROKER_URL         # Same as REDIS_URL
FIELD_ENCRYPTION_KEY      # Fernet key for PII encryption
ANTHROPIC_API_KEY
SENTRY_DSN
ALLOWED_HOSTS
```

## Health Check
- `/health/` — Liveness check
- `/health/?full=1` — Full status (database, cache, etc.)

---

# Key Files Reference

| Category | File | Purpose |
|----------|------|---------|
| Config | `benefits_navigator/settings.py` | All Django config, feature flags, Claude setup |
| Config | `.do/app.yaml` | DigitalOcean deployment |
| Models | `core/models.py` | Base models, journey, audit |
| Models | `accounts/models.py` | User, subscription, organization |
| Models | `claims/models.py` | Document, Claim |
| Models | `agents/models.py` | AI interactions, M21 manual |
| Models | `vso/models.py` | Case, CaseNote, SharedDocument |
| Views | `core/views.py` | Home, dashboard, journey |
| Views | `claims/views.py` | Document upload/download |
| Views | `agents/views.py` | AI agent interfaces |
| Views | `vso/views.py` | VSO case management |
| Services | `agents/services.py` | **BaseAgent**, all AI agents |
| Services | `claims/services/ai_service.py` | Document analysis |
| Services | `claims/services/ocr_service.py` | Tesseract OCR |
| Tasks | `claims/tasks.py` | Document processing pipeline |
| Tasks | `core/tasks.py` | Maintenance, reminders |
| Security | `core/encryption.py` | Field-level encryption |
| Security | `core/middleware.py` | Audit logging, security headers |
| Security | `core/signed_urls.py` | HMAC-SHA256 signed URLs for media |

---

# Security Hardening (implemented)

## Rate Limiting
Rate limits use `django_ratelimit`. Auth endpoints use IP-based keys (pre-auth);
authenticated endpoints use user-based keys.

| Endpoint | Rate | Key | File |
|----------|------|-----|------|
| Login | 5/min + 20/hr | IP | `accounts/views.py` |
| Signup | 3/hr | IP | `accounts/views.py` |
| Password Reset | 3/hr | IP | `accounts/views.py` |
| Document Upload | 10/min | user | `claims/views.py` |
| Status Polling | 60/min | user | `claims/views.py` |
| AI Agent Submit | 20/hr | user | `agents/views.py` |

## Signed URLs for Media Access
Protected file access uses time-limited cryptographically signed URLs:

```python
from core.signed_urls import get_signed_url_generator

generator = get_signed_url_generator()
url = generator.generate_url(
    resource_type='document',
    resource_id=doc.pk,
    user_id=doc.user_id,
    action='download',  # or 'view'
    expires_minutes=30,
)
```

- HMAC-SHA256 signing with Django SECRET_KEY
- Default 30 min expiration, max 24 hours
- Routes: `/claims/document/s/<token>/download/`, `/claims/document/s/<token>/view/`

## GraphQL PII Redaction
`benefits_navigator/schema.py` redacts PII from `document_analysis` resolver:

- SSN patterns (xxx-xx-xxxx, xxx xx xxxx, xxxxxxxxx)
- VA file numbers (8-9 digits, C-prefixed)
- Phone numbers, credit cards, labeled DOB
- Text truncation: 50KB OCR, 10KB AI summary

## VSO Multi-Org Scoping
Users with multiple organization memberships must explicitly select:

```python
from vso.views import get_user_organization, requires_org_selection

if requires_org_selection(user, request):
    return redirect('vso:select_organization')

org = get_user_organization(user, org_slug=slug, request=request)
```

## Audit Logging
`core/models.AuditLog` tracks sensitive operations:

- Document: upload, view, download, delete, share
- AI: analysis runs, consent grant/revoke
- VSO: case create/view/update, document review, notes
- Auth: login, logout, password changes

## HTMX Polling
Status endpoints use 5-second polling with early-exit:

- Templates: `hx-trigger="{% if document.is_processing %}load, every 5s{% endif %}"`
- Views: Return `HX-Refresh: true` header when complete

## MFA for VSO Staff
MFA is supported via `django-allauth-2fa`. The `VSOStaffMFAMiddleware` warns VSO staff
without MFA enabled. Configure in settings:

```python
INSTALLED_APPS += ['django_otp', 'django_otp.plugins.otp_totp', 'allauth_2fa']
MIDDLEWARE += ['django_otp.middleware.OTPMiddleware', 'vso.middleware.VSOStaffMFAMiddleware']
```

## Monitoring & Alerting
The `core/alerting.py` module provides configurable monitoring with alerts:

**Alert Channels:**
- Email (configured via `ALERT_EMAIL_RECIPIENTS`)
- Slack (configured via `SLACK_ALERT_WEBHOOK`)
- Sentry (automatic if configured)

**Monitored Thresholds:**
| Metric | Warning | Critical |
|--------|---------|----------|
| Processing success rate | < 90% | < 80% |
| Failures per hour | > 5 | > 10 |
| Celery workers | <= 1 | = 0 |
| Queue length | > 50 | > 100 |
| Task age | > 5 min | > 10 min |
| Downloads per user/hour | > 50 | > 100 |

**Periodic Tasks (Celery Beat):**
```python
'run-monitoring-checks': every 5 minutes
'check-download-anomalies': hourly
```

**Incident Response:** See `docs/INCIDENT_RESPONSE.md` for runbooks and escalation procedures.

## Remaining Security TODOs
- [ ] Revoke and rotate all exposed secrets (manual — DO Console, OpenAI, Sentry dashboards)
- [ ] Scrub git history with `git-filter-repo` or BFG (secrets were in committed files)
- [x] Fix VSO IDOR — added org validation + `user=case.veteran` filter to analysis queries (2026-02-11)
- [x] Encrypt `ai_summary` field — `EncryptedJSONField` with Fernet AES-256 (2026-02-11)
- [ ] Build Tailwind to static CSS, remove `unsafe-inline` CSP (P2)
- [ ] Object storage migration (S3/DO Spaces)
- [ ] Additional invitation verification (beyond email matching)

---

# Celery Task Best Practices (Audit-Driven)

When creating or modifying Celery tasks:

```python
@shared_task(bind=True, max_retries=3, acks_late=True)
def my_task(self, resource_id):
    """
    - bind=True: enables self.retry()
    - max_retries=3: limits retry attempts
    - acks_late=True: CRITICAL — message requeued if worker crashes mid-execution
    """
    try:
        # Use IDs only in task args, never PII
        resource = MyModel.objects.get(pk=resource_id)
        # ... process ...
    except SomeExpectedError as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    except Exception:
        resource.mark_failed("Processing failed")
        raise  # Let Sentry capture it
```

**Rules:**
1. Pass only IDs as task arguments — never PII values
2. Always set `acks_late=True` for tasks that process user data
3. Use exponential backoff for retries: `countdown=60 * (2 ** self.request.retries)`
4. Set document/resource to 'failed' status in exception handler
5. Global limits: `CELERY_TASK_SOFT_TIME_LIMIT=25min`, `CELERY_TASK_TIME_LIMIT=30min`

---

# VA Regulatory Data Maintenance

## Compensation Rates (Annual Update Required)

VA compensation rates change annually with COLA, effective December 1.

**Update Checklist (run each December):**
1. Check https://www.va.gov/disability/compensation-rates/veteran-rates/ for new rates
2. Update `examprep/va_math.py` — add new `VA_COMPENSATION_RATES_{YEAR}` and `DEPENDENT_RATES_{YEAR}`
3. Update `examprep/va_special_compensation.py` — SMC rates
4. Update `AVAILABLE_RATE_YEARS` list and default year
5. Add tests for new rate year
6. Verify bilateral factor and rounding still match 38 CFR § 4.25

**Current rate coverage:** 2020-2026 (updated 2026-02-11, includes dependent rates for 2024-2026)

## Appeal Deadlines

| Type | Deadline | CFR |
|------|----------|-----|
| Higher-Level Review | 1 year from decision | 38 CFR § 20.202 |
| Supplemental Claim | **No time limit** | 38 CFR § 20.204 |
| Board of Veterans' Appeals | 1 year from decision | 38 CFR § 20.202 |

**Fixed (2026-02-11):** `appeals/models.py:293-301` now correctly exempts supplemental claims from deadline auto-calculation.

---

# Accessibility Requirements (WCAG AA)

Templates must follow these patterns:

```html
<!-- HTMX dynamic content: always wrap targets in aria-live -->
<div id="my-target" aria-live="polite" aria-atomic="false">
  <!-- HTMX will swap content here -->
</div>

<!-- Loading states: always include sr-only text -->
<div role="status" aria-live="polite">
  <span class="sr-only">Loading...</span>
  <svg class="animate-spin" aria-hidden="true">...</svg>
</div>

<!-- Form inputs: always associate labels and mark required -->
<label for="my-input">Field Name</label>
<input id="my-input" aria-required="true" aria-describedby="my-input-error">
<p id="my-input-error" role="alert" class="text-red-600">Error message</p>

<!-- Interactive elements: use buttons, not divs with onclick -->
<button type="button" aria-label="Descriptive action">...</button>
```

**Key rules:**
- All heading levels must follow h1→h2→h3 hierarchy (no skipping)
- All interactive elements must be keyboard-accessible (no `<div onclick>`)
- All HTMX-updated regions need `aria-live="polite"`
- All form errors must use `role="alert"` and `aria-describedby`
- All loading spinners must have `role="status"` with sr-only text
- Status indicators must not rely solely on color

---

# Known Audit Issues (2026-02-11)

See `TODO.md` for full prioritized list. **All P0 code fixes completed 2026-02-11.**

| Priority | Issue | Status |
|----------|-------|--------|
| ~~P0~~ | ~~Secrets in version control~~ | Code fix done — .gitignore + templates. **Manual rotation still needed.** |
| ~~P0~~ | ~~Compensation rates outdated~~ | Fixed — 2020-2026 rates in `examprep/va_math.py` |
| ~~P0~~ | ~~Supplemental claim deadline~~ | Fixed — `appeals/models.py:293-301` + tests |
| ~~P0~~ | ~~Celery tasks missing `acks_late`~~ | Fixed — all user-data tasks |
| ~~P0~~ | ~~No pytest in CI~~ | Fixed — `.github/workflows/tests.yml` |
| ~~P1~~ | ~~VSO IDOR (cross-org access)~~ | Fixed — org validation + security tests (2026-02-11) |
| ~~P1~~ | ~~`ai_summary` unencrypted~~ | Fixed — `EncryptedJSONField` + data migration (2026-02-11) |
| ~~P1~~ | ~~Missing agent model indexes~~ | Fixed — 5 composite indexes added (2026-02-11) |

## Git & Save Practices
- **Commit message format**: Conventional Commits — `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- **Commit subject**: Imperative mood, concise (<72 chars)
- **Commit body**: Explain *why*, not *what*
- **When to commit**: After each logical unit of work, tests passing
- **What NOT to commit**: `.env`, `.do/app.yaml` with credentials, `db.sqlite3`, `venv/`, `__pycache__/`, media uploads
- **Branch strategy**: Feature branches off `main`; PR for significant changes
- **Before pushing**: Run `pytest` — all tests must pass, no security regressions
- **Secrets**: See "Remaining Security TODOs" — never commit API keys, encryption keys, or DSNs

---
<!-- Shared cross-project lessons. Edit the canonical file, not here. -->
@~/.claude/shared/LESSONS.md
<!-- BAS-platform-only lessons. Canonical file lives in bas-platform. -->
@~/projects/bas-platform/LESSONS.md
