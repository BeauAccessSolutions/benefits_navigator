# Government-Contract Remediation Plan

**Created:** 2026-07-23
**Goal:** Take Benefits Navigator from "promising pilot with verified security defects" to an app
we can credibly pitch for a government (VA-adjacent / state veterans-services) contract: every
known trust-breaking defect fixed, authorization airtight, data lifecycle honest, and a
documented compliance posture that survives a contracting officer's technical review.

**Inputs:** the 2026-07-23 external audit (all findings independently verified — see TODO.md top
section), open items from the 2026-06-09 and 2026-02-09 audits, `docs/PHI_DATA_FLOW.md`,
`docs/security-invariants.md`, and the BAS platform invariants (layered sessions, honest
deletion/export, no third-party tracking).

**How to read this:** Phases 0–3 are engineering work in this repo, ordered by risk. Phase 4 is
the compliance/procurement layer — mostly documents, process, and two strategic decisions that
are cheaper to make early. Each item has acceptance criteria; nothing counts as done without a
test or an artifact.

**Status reconciled 2026-07-26.** Every unchecked box below was re-verified against the working
tree on that date, because the plan was written 2026-07-23 and a dozen PRs merged after it —
several items it lists as open had in fact shipped. Items marked ✅ were confirmed in code, not
taken from a changelog. What is genuinely still open is now, and only, what is still unchecked.

---

## Guiding principle

A government evaluator's first question is not "is it secure?" but "**can you prove what it
does with a veteran's data?**" Every phase below either closes a gap between what the app
*promises* and what it *does* (deletion, export, deadlines), or produces the proof
(tests, audit logs, policy docs, third-party attestation).

---

## Phase 0 — Broken promises (stop-the-bleeding, ~1 week)

Defects where the app tells users something untrue. These are disqualifying in any
government due-diligence review because they're *integrity* failures, not just bugs.

### 0.1 Real account deletion (P0) — the single most important item — ✅ DONE (this PR)
`accounts/views.py` previously promised permanent deletion in 30 days but only audit-logged and
logged out.

- [x] Add `deletion_requested_at` (nullable datetime) to `User`; migration
      (`accounts/migrations/0012`).
- [x] On confirmed request: set the field; **keep the account active** during the grace period.
      Decided against immediate `is_active=False` precisely so "cancel by logging in" (the
      existing UX promise) works — the account stays usable, a prominent banner shows the
      scheduled date, and a Cancel button clears the field. No ADR needed; the copy and behavior
      now agree.
- [x] Celery Beat task (daily 4 AM, `acks_late=True`, idempotent, per-account transaction):
      `process_scheduled_account_deletions` purges accounts past the 30-day grace period —
      deletes Document + AppealDocument files from storage, best-effort Stripe customer detach,
      then `user.delete()` cascades every owned record.
- [x] VSO entanglement: `VeteranCase.veteran` is `CASCADE`, so deleting a veteran removes their
      case and its notes/shared docs/analyses — deletion stays *complete*. Where the user is a
      VSO caseworker instead, `assigned_to` is `SET_NULL`, so colleagues' cases survive
      unassigned. Documented in `purge_user_account`'s docstring + covered by a test.
- [x] Audit log the request, the cancellation, and the purge (new `account_delete_cancel` /
      `account_delete_purge` actions; purge entry preserves `user_email` with the FK nulled).
- [x] Tests (14 view + purge): schedule/cancel/idempotency, grace-period arithmetic, purge
      cascade, file-removed-from-storage, past-grace-only selection, veteran→VSO cascade.
- **Acceptance met:** a purged user's email returns nothing across tables + storage; the purge
  leaves an audit record; `AssistantTurn`'s "account-deletable" docstring is now true.

### 0.2 Honest, working data export (P1) — ✅ DONE 2026-07-26 (PR #77)
`accounts/views.py:150` crashed on nonexistent fields for any user with a claim or appeal.

- [x] Fix field references: `claim.title`/`claim.submission_date`,
      `appeal.conditions_appealed`/`appeal.appeal_type`. *(Landed separately in PR #50.)*
- [x] Include what was silently omitted — `assistant_threads`, `assistant_turns`,
      `decision_letter_analyses`, `evidence_gap_analyses`, `personal_statements`,
      `rating_analyses`, `vso_cases`, `vso_case_notes_shared_with_me` (visible-to-veteran only),
      `appeal_documents`. What is still excluded is *named* in `about_this_export.not_included`
      (document files, audit log, a rep's internal notes) rather than dropped in silence.
- [x] Replace the silent 1,000-record truncation: a `collect()` helper fetches `limit + 1` and
      records per-category truncation in a `truncated` map; `about_this_export.truncated_categories`
      lists whatever hit the cap.
- [x] **PII policy decided: include, behind step-up.** Identifiers export in full and
      `data_export` carries `@reauthentication_required(allow_get=True)` — the explanation page
      renders on GET, the POST that produces the file needs a fresh password. Redacting the
      account holder's own DOB and VA file number made the export useless to the one person
      entitled to it; a stale session is not enough proof to hand over the whole record. Matches
      the platform's layered-session invariant. Users with no usable password (external provider)
      pass through, per allauth's `did_recently_authenticate`.
- [x] Tests: 12 in `TestDataExportView` — step-up redirect, identifiers present with no
      `[REDACTED]` anywhere, truncation flag flipping under a lowered cap, transcript/analysis/
      shared-note round-trip, internal note absent.
- **Acceptance met:** the export succeeds for a fully-populated account and describes itself
  accurately — including its own limits.

### 0.3 Bind invitations to the invited email (P1) — ✅ DONE 2026-07-23
`accounts/views.py` `org_invite_accept` + `OrganizationInvitation.accept()` previously let a POST
accept from any logged-in account. Now closed:

- [x] `accept()` raises unless `user.email.lower() == invitation.email.lower()` **and** the
      address is verified. Verification is checked via allauth `EmailAddress.verified` — NOT
      `User.is_verified`, because django-otp's `OTPMiddleware` shadows `request.user.is_verified`
      with a truthy 2FA-status method in every request context (documented in `_email_is_verified`).
- [x] Removed the accept-anyway POST path in `org_invite_accept`; the mismatch page (and template)
      now offer "log in as the invited account" only — no accept button.
- [x] Enforcement lives in the model, so BOTH accept flows are covered: `org_invite_accept` (staff)
      and `vso.views.accept_invitation` (veterans).
- [x] Tests (`accounts/tests.py`): `TestInvitationEmailBinding` (mismatch → ValueError, unverified →
      ValueError, invited+verified → membership, verified-via-allauth, case-insensitive) and
      `TestOrgInviteAcceptView` (foreign-account POST grants nothing, invited+verified POST accepts,
      invited-but-unverified POST rejected). Full accounts/vso/core/api suites: 315 passed.
- **Acceptance met:** a forwarded invitation link is useless to any account but the invited,
  email-verified one.

### 0.4 Rotate exposed credentials (manual, from 2026-02 audit — still open)
- [ ] Rotate `SECRET_KEY`, `FIELD_ENCRYPTION_KEY` (via `rotate_encryption_key`), `DATABASE_URL`,
      `REDIS_URL` in DO console; redeploy; verify.
- [ ] Compare prod `SECRET_KEY` prefix against `git show 9bff52e:.env.docker` (public repo
      history) — if it matches the committed dev key, treat as compromised.
- **Acceptance:** no credential that ever appeared in git history is live in production.

---

## Phase 1 — Authorization & data protection (~2 weeks)

### 1.1 VSO least-privilege scoping, everywhere (P1) — ✅ DONE 2026-07-23
`scope_cases_for_member` was applied in 4 of ~13 endpoints; org-only lookups let restricted
caseworkers act on colleagues' cases by ID. Now closed:

- [x] Added `get_scoped_case_or_404(user, organization, pk, queryset=None)` (`vso/permissions.py`)
      applying the org filter **and** `scope_cases_for_member`; every case-by-pk endpoint routes
      through it: `case_detail`, `case_update_status`, `case_archive`, `add_case_note`,
      `complete_action_item`, `shared_document_review`, `case_notes_partial`,
      `case_documents_partial`, `start_appeal_from_case`, `evidence_packet_builder`.
      `bulk_case_action`'s `pk__in` queryset is built from the scoped queryset.
- [x] Fixed dashboard `recent_notes` (filters through scoped cases via `case__in`, not raw org).
- [x] Fixed `case_list` `archived=1` branch to re-apply scoping.
- [x] Regression tests: for a `restrict_caseworker_visibility` org, a restricted worker probing
      another worker's case ID gets 404 on **every** endpoint — parameterized over the URL list
      (`TestIntraOrgCaseworkerIsolation`) — plus an AST meta-test
      (`test_no_unscoped_case_by_pk_lookups_in_views`) that fails on any raw
      `get_object_or_404(VeteranCase)` / `VeteranCase.objects` pk lookup in `vso/views.py`, and
      unit tests for the helper (`TestScopedCaseHelper`). Admin + unrestricted-org regressions
      confirmed. Full `vso/` suite: 68 passed.
- **Acceptance:** one enforced code path for case access; the parameterized 404 suite passes. ✅

### 1.2 Protected appeal-document lifecycle (P1) — ✅ DONE (PR #36/#37 merged; rest in PR #79)
- [x] Land/merge the protected-media work already open — PR #36 (appeals) and #37 (claims-side
      affordance) both merged; `appeals.views._serve_appeal_document` is the single serving path.
- [x] Server-side upload validation on `AppealDocumentForm`: size cap, extension, declared
      content type, then libmagic on the leading bytes — via the new shared
      `core.file_validation.validate_document_upload`. `claims/forms.py` had two near-identical
      copies of these checks; both now delegate to the same helper, since that duplication is
      precisely how appeals ended up with none.
- [x] Delete the stored file when the row is deleted — `post_delete` receivers in
      `core/file_cleanup.py`, registered from `CoreConfig.ready()`. Signal rather than a call in
      the delete view because files must also go on *cascades* (appeal→documents, account purge),
      which never reach a view. `Document` soft-deletes, so it fires only on `hard_delete` and
      cascades — the reversible everyday delete is deliberately untouched.
- [x] Tests: `tests/test_upload_integrity.py` (14) — a shell script named `evidence.pdf` with a
      PDF `Content-Type` is rejected on its bytes; oversized/bad-extension/bad-type rejected;
      file gone from storage after row delete and after cascade; delete survives an
      already-missing file.
- [x] **Acceptance met:** no template renders a raw `doc.file.url` — verified by scan.

### 1.3 Storage that actually works (P1) — code ✅ (PR #58/#65/#66); bucket still to stand up
- [x] Migrate `DEFAULT_FILE_STORAGE`/`STATICFILES_STORAGE` → the `STORAGES` dict — done in PR #58;
      `USE_S3=True` backend selection covered by tests (PR #66 made file access storage-agnostic,
      #65 stopped requiring a collectstatic manifest under tests/runserver).
- [x] Replace `document.file.path` uses — none remain in `claims/tasks.py` (verified 2026-07-26).
- [ ] **Stand up DO Spaces (or S3) bucket, private ACL, server-side encryption; move media.**
      This is the only part left, and it is infrastructure, not code — the app is ready for it.
- [x] Signed-URL generator continues to front all access.
- [x] Tests: storage-backend selection under `USE_S3`; OCR against a non-filesystem storage double.
- **Acceptance:** *pending the bucket.* Code no longer blocks it.

### 1.4 Encryption sweep for narratives (P1) — ✅ DONE (PR #42/#47/#48)
- [x] `CaseNote.content` → `EncryptedTextField` (`vso/models.py:255`).
- [x] `AssistantTurn.content` → `EncryptedTextField` (`agents/models.py:912`).
- [x] Agent analysis JSON → `EncryptedJSONField` across `DecisionLetterAnalysis`,
      `DenialDecoding`, `EvidenceGapAnalysis`, `RatingAnalysis`, plus the `PersonalStatement`
      narrative fields — ~25 fields in `agents/models.py`.
- [x] Query-impact review done per field alongside each migration.
- [x] Tests: round-trip per field; migration on populated data.
- **Acceptance met:** every free-text field that can hold a veteran's medical narrative is
  encrypted at rest. *(Confirm `docs/PHI_DATA_FLOW.md` reflects this.)*

---

## Phase 2 — Correctness a veteran can rely on (~1 week)

### 2.1 Supplemental-claim eligibility (P1) — intake ✅ (PR #69); analyzer still open
- [x] `appeals/forms.py`: intake no longer rejects >1-year-old decisions; the one-year
      implications surface as non-blocking guidance via `decision_is_over_a_year_old`, with the
      38 CFR § 20.204 citation in the code comment.
- [ ] **`agents/services.py:324`: still stamps a blanket `decision_date + 365` as
      `appeal_deadline`** regardless of lane. Replace with per-lane deadlines (HLR/Board: 1 year;
      Supplemental: none + effective-date note) in the analyzer output schema. *Verified still
      present 2026-07-26.*
- [ ] Tests: analyzer output distinguishes lanes. *(Intake side is covered.)*
- **Acceptance:** no code path tells a veteran they cannot file a Supplemental Claim after a
  year. **Not yet met — the analyzer is the remaining path.**

### 2.2 Structured AI outputs on the legacy path (P2 → promoted)
For a government pitch, "the AI can emit unvalidated JSON that we store and show veterans" is a
findings-report line item.

- [ ] Migrate remaining `_parse_json_response` call sites in `agents/services.py` to
      `gateway.complete_structured()` with Pydantic schemas (schemas largely exist in
      `agents/schemas.py`).
- [ ] Sanitize-on-output check: model text rendered into templates is escaped (verify no
      `|safe`/`mark_safe` on AI content — add a template-scan test alongside 1.2's).
- [ ] Tests: malformed-model-output paths return graceful errors, mock-based.
- **Acceptance:** every Claude response that reaches storage or a template passed schema
  validation.

### 2.3 Regulatory-data process hardening
- [ ] The December COLA update checklist (CLAUDE.md) becomes a management command + calendar'd
      task with a failing test if `AVAILABLE_RATE_YEARS` lacks the current year after Dec 1.
- [ ] Document the CFR-verification provenance for rates/deadlines (who checked, when, against
      what URL) in a `docs/regulatory-provenance.md` — evaluators ask.
- **Acceptance:** rate-currency is enforced by CI, not memory.

---

## Phase 3 — Hardening & operational maturity (~1–2 weeks)

### 3.1 Authentication hardening
- [x] Flip `VSO_MFA_REQUIRED` default → `True` — done in PR #44 (`settings.py:742`).
- [ ] Flip `ADMIN_OTP_REQUIRED` → `True` in prod once superusers are enrolled. *(Still `False`
      at `settings.py:753` — this one is gated on enrolment, not on code.)*
- [ ] Account lockout after repeated failed logins (django-axes or allauth rate-limit) — open
      TECHNICAL DEBT item; required by NIST 800-53 AC-7.
- [ ] JWT refresh lifetime 7d → 24h (open P2).

### 3.2 Transport & platform security
- [x] Redis TLS: `CERT_NONE` → defaults to `CERT_REQUIRED` (verified), env-var escape hatch for
      local — done in PR #43 (`settings.py:297`).
- [ ] CSP: build Tailwind to static CSS (open P2), self-host HTMX (drop unpkg), remove
      `unsafe-inline` — CSP tests already exist to extend.
- [ ] Fix `/health/?full=1` (middleware path check must forward querystring requests or move the
      full check to an authenticated `/health/full/` — evaluator-visible monitoring must work).
- [ ] Pin dependencies: upper-bound Django (`>=5.2,<6.0`), full `pip-compile` lockfile; enable
      `pip-audit` in CI.
- [ ] Enforce bandit in CI (drop `continue-on-error`); ratchet coverage floor above 60.

### 3.3 Resilience & DR (open infra items, now contract-relevant)
- [ ] Automated database backups + restore drill (documented, timed).
- [ ] Disaster-recovery plan doc: RTO/RPO targets, runbook.
- [ ] Worker/web sizing bump (`basic-xs`) — OOM risk at concurrency=2 is an availability
      finding.
- [ ] Task idempotency guards + `replay_failed_tasks` command (open P2s).
- [ ] Circuit breaker on AI-gateway calls (open P2).

---

## Phase 4 — Compliance & procurement readiness (VSO / non-profit market)

**Target market (decided 2026-07-23): DAV, county VSOs (CVSOs), state veterans departments, and
accredited veteran non-profits — NOT the federal VA directly.** This is the entry market the app's
Path B (Organizations, caseworkers, `VeteranCase`, shared documents) is already built for, and it
**sidesteps FedRAMP entirely** — FedRAMP is triggered by a *federal agency* consuming a cloud
service; a county office or non-profit buying SaaS is ordinary B2B procurement. That drops the
authorization cost from ~$250k–$500k (federal ATO) to a SOC 2 program in the ~$15k–50k/yr range,
and keeps hosting on commercial infrastructure (~$150–300/mo on AWS or current DigitalOcean).

> **Consequence for engineering priority:** in this market, tenant isolation *is* the product.
> A DAV/CVSO security reviewer's first questions are role-based access and cross-org data
> separation — so **Phase 1.1 (VSO scoping) and 0.3 (invitation binding) are promoted to
> top-tier priority, alongside the Phase 0 integrity items.** See the reordered sequencing below.

### Decision A — Hosting (RESOLVED for the VSO market)
- Commercial AWS or staying on DigitalOcean is fine; **no GovCloud / FedRAMP needed** unless/until
  a *direct federal VA* contract is pursued (a later, separate decision — keep the option open but
  don't pay for it now).
- [ ] Confirm the hosting provider will sign a **BAA** (Business Associate Agreement) — see the
      HIPAA section; this is the one hosting item that can force a move (AWS signs a BAA at no
      extra cost; DigitalOcean's BAA availability must be confirmed and may be the deciding factor).
- [ ] Record the market + hosting decision as ADR-006.

### Decision B — The AI data boundary
- Current posture ("Not HIPAA compliant — educational use only") must be replaced with a real,
  documented boundary before handling live veteran records for a paying VSO.
- [ ] Get a **BAA / zero-data-retention agreement from Anthropic** (offered) so AI processing of
      PHI is contractually covered. Commercial Claude API with a BAA is sufficient for this market
      — no GovCloud/Bedrock required.
- [ ] Update `docs/PHI_DATA_FLOW.md` and the user-facing consent copy to match reality.

### Artifacts to produce (VSO pitch binder)
- [ ] **SOC 2 Type I → II** — the anchor credential for this market. Controls are largely the
      Phases 0–3 outputs; start with a readiness self-assessment (compliance-automation tooling
      ~$10–25k/yr), then a Type I audit, then Type II over an observation window.
- [ ] **Security questionnaire pack** — pre-answer a SIG-lite / CAIQ so each buyer's questionnaire
      is a copy-paste, not a fire drill. Tenant isolation and RBAC answers come straight from
      Phase 1.1.
- [ ] **Data Processing Agreement (DPA) + BAA template** — what a VSO signs; covers PHI handling,
      subprocessors (hosting, Anthropic), breach notification, deletion/export (Phase 0.1/0.2).
- [ ] **Section 508 / WCAG 2.2 AA conformance + VPAT/ACR** — these orgs serve disabled veterans;
      accessibility is a differentiator and sometimes a requirement. Existing a11y work feeds in.
- [ ] **Cyber-liability insurance** — routinely required by procurement; get a quote early (a real
      recurring cost, but modest for a small vendor).
- [ ] **Third-party penetration test** — schedule *after* Phase 1 authz fixes land; keep the
      letter for the binder. (Smaller/cheaper scope than a federal assessment.)
- [ ] **Privacy Impact Assessment (PIA)** — extend `PHI_DATA_FLOW.md`; the deletion/export answers
      are now honest (Phase 0.1 done, 0.2 pending).
- [ ] **Data-retention & deletion policy** doc — written from the Phase 0.1 implementation.
- [ ] **Incident response** — existing `INCIDENT_RESPONSE.md` + a dated tabletop exercise log.
- [ ] **Accessibility, privacy, and security statements** on the public site.
- [ ] Fix `AGENTS.md` — it still says git-history scrub is pending; it was done 2026-02-12.

### Positioning notes (VSO market)
- The app is a **tool used by** VA-accredited reps, not the accredited entity — reps keep their VA
  obligations; the product's job is to be secure and auditable. Keep the "assists, not legal
  advice, doesn't replace professional judgment" framing.
- **Entry point:** land a single **county VSO or state DVA pilot** first (light procurement), use
  it as a reference to approach **DAV national** (bigger enterprise deal, real security review).
- VSOs generally aren't HIPAA *covered entities*, so HIPAA may not strictly bind the app — but the
  data is veteran medical narratives, so we adopt the HIPAA Security Rule as the best-practice
  framework anyway (below). It also future-proofs against a covered-entity buyer.

---

## HIPAA Security Rule — safeguards baseline (do the free parts now)

Goal: get **as close to HIPAA Security Rule conformance as possible using code + config + policy
docs**, deferring only the items that genuinely cost money. Honest framing: "HIPAA compliant" is a
legal status that ultimately requires **signed BAAs with every entity that touches PHI** (hosting,
AI) plus a documented risk analysis — so the accurate near-term claim is *"we implement the HIPAA
Security Rule technical and administrative safeguards,"* not *"we are HIPAA compliant."* The BAAs
themselves are typically **free** (AWS, Anthropic); the paid part is SOC 2 and insurance above.

### Technical safeguards (§164.312) — mostly free, do these first
- [x] **Automatic logoff** §164.312(a)(2)(iii) — done in PR #41; `SESSION_IDLE_TIMEOUT` defaults
      to 30 min (`settings.py:422`) enforced by middleware.
- [x] **Encryption at rest** §164.312(a)(2)(iv) — Phase 1.4 sweep complete (PR #42/#47/#48).
- [x] **Transmission security** §164.312(e) — Redis/Celery TLS verified by default, env-
      configurable (PR #43); HSTS/secure-cookies already in place.
- [~] **Person/entity authentication** §164.312(d) — VSO staff MFA on by default (PR #44);
      `ADMIN_OTP_REQUIRED` still off pending superuser enrolment. Unique per-user accounts
      enforced (email is `USERNAME_FIELD`).
- [x] **Access control** §164.312(a)(1) — Phase 1.1 VSO least-privilege scoping, with the
      parameterized 404 suite and the AST meta-test as evidence.
- [x] **Audit controls** §164.312(b) — `core.models.AuditLog` already logs PHI access, AI runs,
      VSO actions, auth events; account-purge writes an erasure record (Phase 0.1).
- [x] **Integrity** §164.312(c) — shared upload validation (size/extension/content-type/magic
      bytes) now covers every upload path, and deleted rows take their stored files with them
      (Phase 1.2, PR #79).

### Administrative safeguards (§164.308) — free to write (docs, not code)
- [ ] **Risk analysis & risk management** §164.308(a)(1) — a written risk assessment (this plan +
      the audit findings are 80% of the raw material).
- [ ] **Sanction policy**, **information-access management**, **security-awareness training**
      outline, **contingency plan** (backup + DR from Phase 3.3), **breach-notification procedure**
      — short policy docs under `docs/compliance/`.
- [ ] **Workforce clearance / termination procedures** — how staff access is granted/revoked
      (ties to `OrganizationMembership.is_active`).

### Physical safeguards (§164.310)
- [ ] Largely **inherited from the hosting provider** — documented via their SOC 2 / BAA, not
      something we implement. Note the inheritance in the SSP.

### The honest gaps (what still costs money or a signature)
- BAAs with hosting + Anthropic (usually free, but require signing and may constrain hosting).
- SOC 2 audit + compliance tooling (~$15–50k/yr) — the real recurring spend.
- Cyber-liability insurance.
- A formal, signed-off risk assessment (we can *draft* it free; a review adds cost).

---

## Sequencing & effort summary (reordered for the VSO market)

| Priority | Content | Effort (focused) | Why this order |
|---|---|---|---|
| **0** | Account deletion ✅, export fix, **invitation binding**, credential rotation | ~1 week | Integrity + the invitation authz gap a VSO reviewer checks first |
| **1** | **VSO least-privilege scoping**, protected media, storage, encryption sweep | ~2 weeks | Tenant isolation *is* the product in this market; feeds SOC 2 + pen test |
| **HIPAA baseline** | Automatic logoff (**starting now**), then encryption sweep, TLS, MFA, admin-safeguard docs | rolling, ~free | Overlaps Phases 1 & 3; cheap trust signal for VSO buyers |
| **2** | Appeal rules, structured AI, regulatory process | ~1 week | Correctness |
| **3** | MFA/lockout, TLS/CSP, backups/DR, CI gates | ~1–2 weeks | SOC 2 readiness, HIPAA transmission/auth |
| **4** | Market = VSO/DAV (decided); BAAs + SOC 2 + VPAT + insurance | rolling | The pitch itself |

**Order of operations:** Phase 0 first (0.1 done). **Invitation binding (0.3) and VSO scoping
(1.1) next** — tenant isolation is the VSO product and the first thing a buyer probes. The HIPAA
technical safeguards run in parallel and mostly overlap Phases 1 & 3 (starting with automatic
logoff). Get the free **BAAs** (hosting, Anthropic) in flight early — they gate the honest HIPAA
claim and can influence hosting. Pen test after Phase 1. SOC 2 readiness once Phases 0–3 land.

**Definition of done for "pitchable" (VSO market):** every TODO.md P0/P1 checked; VSO tenant
isolation proven (Phase 1.1 test suite); deletion/export demonstrably honest end-to-end; BAAs
signed; SOC 2 Type I in hand (Type II underway); VPAT; pen-test letter with criticals remediated;
cyber-liability insurance bound; and no doc in the repo that contradicts reality.

---

## What is actually left (verified 2026-07-26)

Phases 0 and 1 are **code-complete** except for standing up the object-storage bucket. Every
P0 and P1 engineering item in this plan is now closed and test-backed. The remaining work:

### Code — ready to pick up
| Item | Where | Note |
|---|---|---|
| 2.1 per-lane appeal deadlines | `agents/services.py:324` | Analyzer still stamps a blanket 1-year deadline; a Supplemental Claim has none |
| 2.2 structured AI outputs | `agents/services.py` ×5 | `_parse_json_response` on unconstrained JSON at lines 312, 464, 546, 790, 974 |
| 2.3 rate-currency CI gate | `examprep/va_math.py` | Failing test if `AVAILABLE_RATE_YEARS` lacks the current year after Dec 1 |
| 3.1 account lockout | — | No `django-axes` or equivalent; NIST 800-53 AC-7 |
| 3.1 JWT refresh 7d → 24h | `settings.py:873` | |
| 3.2 `/health/?full=1` unreachable | `core/middleware.py:34` | Path-only check short-circuits before the querystring is seen; the detailed health endpoint cannot be reached in production |
| 3.2 CSP `unsafe-inline` + unpkg | `settings.py:444` | Self-host HTMX, build Tailwind to static CSS |
| 3.2 dependency pins | `requirements.txt:2` | `Django>=5.2.13` unbounded — local resolves 6.0, CI resolves 5.2 |
| 3.2 bandit advisory-only | `.github/workflows/security-checks.yml:141` | `continue-on-error: true` |
| 3.3 resilience/DR | — | Backups + restore drill, DR doc, sizing, task idempotency, circuit breaker |

### Not code — needs a decision, a signature, or money
- **0.4 credential rotation** (DO console) — still open, and still the oldest item here.
- **1.3 object storage bucket** — DO Spaces/S3, private ACL, SSE.
- **3.1 `ADMIN_OTP_REQUIRED` → True** — gated on enrolling superusers first.
- **Phase 4 in full** — BAAs (hosting + Anthropic), SOC 2, VPAT, pen test, insurance, policy docs.
