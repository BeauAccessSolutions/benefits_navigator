# Comprehensive Audit Prompt — Benefits Navigator

> Paste everything below this line into a fresh Claude Code session at the repo root.
> Output goes to `audits/<today's date>/comprehensive-audit.md`.

---

You are performing a full production-readiness audit of this repository (VA Benefits Navigator — Django 5.1 + Celery/Redis + PostgreSQL + OpenAI, deployed on DigitalOcean App Platform). This app serves veterans and VSO caseworkers and handles PII/PHI, so audit with that severity bar.

**Before you start:** Read `CLAUDE.md`, `TODO.md`, and the most recent report under `audits/`. Compare against the prior audit — explicitly note which previously-flagged items are now fixed, still open, or regressed. Do not re-litigate items marked fixed unless you find evidence the fix is wrong.

## Protocol

**Tier 1 — Automated scans (run these first, report raw results):**
1. `pytest -x -q` — full test suite; note failures and total count
2. `pip list --outdated` and check `requirements.txt` for known-vulnerable pins (`pip-audit` if available, else manual CVE check on Django, celery, redis, openai, stripe, Pillow, pytesseract)
3. `bandit -r . -x ./venv,./node_modules -ll` (install if missing)
4. Grep sweeps:
   - Secrets: `grep -rEn "(sk-[a-zA-Z0-9]|postgres://|rediss?://[^$]|SECRET_KEY *= *['\"])" --include="*.py" --include="*.yaml" --include="*.yml" --include="*.env*" .` (exclude templates with CHANGE_ME placeholders)
   - PII logging: `grep -rn "logger\.\|logging\." --include="*.py" | grep -iE "ssn|va_file|date_of_birth|dob|email|phone"`
   - Bare excepts: `grep -rn "except:" --include="*.py" .` and `except Exception:` with `pass`
   - Celery: every `@shared_task`/`@app.task` touching user data must have `acks_late=True`; task args must be IDs, never PII
   - Raw OpenAI usage bypassing the gateway: `grep -rn "openai\." --include="*.py" . | grep -v ai_gateway`
5. `python manage.py makemigrations --check --dry-run` — uncommitted model changes
6. `python manage.py check --deploy` — Django deployment checklist

**Tier 2 — Specialist deep reviews.** For each domain below, review the listed files plus anything Tier 1 flagged. Score each domain 1–5 and name the single worst finding.

1. **Security** — IDOR across `vso/views.py` (org scoping, `user=case.veteran` filters), `claims/views.py` (signed URLs, ownership checks), `agents/views.py`. Rate-limit coverage vs the table in CLAUDE.md (any new unrated endpoints?). CSRF, session config, CSP state (`unsafe-inline` still present?). Encryption coverage: every PII field uses `EncryptedCharField`/`EncryptedJSONField`.
2. **VA Regulatory Accuracy** — `examprep/va_math.py`, `examprep/va_special_compensation.py`, `appeals/models.py`. Verify compensation rates, bilateral factor, and rounding against 38 CFR § 4.25; appeal deadlines against 38 CFR § 20.202/20.204 (supplemental claims = no deadline). Check whether the December COLA update is due/overdue relative to today's date.
3. **AI Safety / Prompt Injection** — All paths from user input to OpenAI: `agents/services.py`, `claims/services/ai_service.py`. Every call goes through `agents/ai_gateway.py` with `sanitize_input()` and Pydantic validation? Model output never rendered as raw HTML or used in queries/file paths? Consent flow correct (no silent exception swallowing)?
4. **Celery / Async** — `claims/tasks.py`, `core/tasks.py`: acks_late, retries with exponential backoff, failed-status handling, stuck-task detection, Beat schedule sanity, replay path for dead-lettered work.
5. **Django / Backend Quality** — N+1 queries in dashboards and case lists (`select_related`/`prefetch_related`), untyped exception handlers, transaction boundaries on multi-model writes, missing DB indexes on new query paths.
6. **CI/CD & Deployment** — `.github/workflows/`, `Dockerfile.prod`, `.do/` templates: coverage threshold gate, bandit enforcement (not advisory), migration safety in pre-deploy job, secrets handling.
7. **Accessibility (WCAG AA)** — Templates: aria-required on required inputs, `aria-live` on HTMX targets, focus management after swaps, heading hierarchy, `role="alert"` on form errors, no color-only status indicators.
8. **UX / Veteran Safety** — Dollar figures labeled "estimated", legal/benefits disclaimers visible (not buried), deadline displays accurate and prominent, failure states give actionable next steps (not dead ends).
9. **Monitoring / Ops** — `core/alerting.py`, health checks, Sentry coverage, runbook accuracy in `docs/INCIDENT_RESPONSE.md`, whether alert thresholds in CLAUDE.md match the code.
10. **Documentation drift** — CLAUDE.md / TODO.md / docs vs actual code. Flag any claim in the docs the code contradicts.
11. **Test Coverage** — Coverage on security-critical paths (auth, org scoping, signed URLs, encryption, deadline calculation). Are the audit-driven regression tests still present and passing?

## Output requirements

Write the report to `audits/<YYYY-MM-DD>/comprehensive-audit.md` with:

1. **Scorecard table** — domain, score /5, worst finding (match the format of the prior audit so scores are comparable)
2. **Overall score and verdict** — SHIP / SHIP WITH CAVEATS / DO NOT SHIP, with the population caveat spelled out (pilot vs broad rollout)
3. **Delta from prior audit** — fixed / still open / regressed / new
4. **P0 / P1 / P2 findings** — each with file:line, evidence (the actual code or scan output, not paraphrase), impact, and a concrete fix
5. **Corrections section** — anything you initially flagged in Tier 1 that Tier 2 disproved (be honest about false positives)
6. **Update `TODO.md`** with new findings under the right priority sections (do not delete existing history)

Rules of engagement: read-only except for the report file and TODO.md — do not "fix while auditing." If a finding depends on runtime behavior you can't verify (e.g., DO Console config, credential rotation status), mark it UNVERIFIED rather than assuming. Cite file:line for every finding.
