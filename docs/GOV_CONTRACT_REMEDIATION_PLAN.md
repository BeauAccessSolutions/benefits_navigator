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

### 0.2 Honest, working data export (P1)
`accounts/views.py:150` crashes on nonexistent fields for any user with a claim or appeal.

- [ ] Fix field references: `claim.title`/`claim.submission_date`,
      `appeal.conditions_appealed`/`appeal.appeal_type`.
- [ ] Include what's currently silently omitted (assistant transcripts, agent analyses,
      case notes visible to the veteran) or list omissions explicitly in the export payload.
- [ ] Replace the silent 1,000-record truncation: paginate/stream, or at minimum emit
      `"truncated": true` per category.
- [ ] Decide PII policy: exporting *to the authenticated account holder* is the one place
      redaction is anti-user; either include decrypted PII fields behind a re-auth
      (session-age check), or keep redaction and say so in the payload. Document the choice.
- [ ] Tests: export for a user with claims + appeals + transcripts round-trips without error and
      contains each category.
- **Acceptance:** export succeeds for a fully-populated account and describes itself accurately.

### 0.3 Bind invitations to the invited email (P1)
`accounts/views.py:1145` + `OrganizationInvitation.accept()` — POST accepts from any account.

- [ ] `accept()` raises unless `user.email.lower() == invitation.email.lower()` **and** the
      address is verified (allauth `EmailAddress.verified`).
- [ ] Remove the accept-anyway POST path; mismatch page offers "log in with the invited
      account" only.
- [ ] Tests: mismatched-email POST rejected; unverified-email POST rejected; happy path.
- **Acceptance:** a forwarded invitation link is useless to any account but the invited one.

### 0.4 Rotate exposed credentials (manual, from 2026-02 audit — still open)
- [ ] Rotate `SECRET_KEY`, `FIELD_ENCRYPTION_KEY` (via `rotate_encryption_key`), `DATABASE_URL`,
      `REDIS_URL` in DO console; redeploy; verify.
- [ ] Compare prod `SECRET_KEY` prefix against `git show 9bff52e:.env.docker` (public repo
      history) — if it matches the committed dev key, treat as compromised.
- **Acceptance:** no credential that ever appeared in git history is live in production.

---

## Phase 1 — Authorization & data protection (~2 weeks)

### 1.1 VSO least-privilege scoping, everywhere (P1)
`scope_cases_for_member` is applied in 4 of ~13 endpoints; 9 org-only lookups let restricted
caseworkers act on colleagues' cases by ID.

- [ ] Add one helper — `get_scoped_case_or_404(user, org, pk, for_write=False)` — that applies
      org filter **and** `scope_cases_for_member`; convert every case endpoint to it:
      `case_update_status`, `case_archive`, `add_case_note`, `complete_action_item`,
      `shared_document_review`, `case_notes_partial`, `case_documents_partial`,
      `start_appeal_from_case`, and `bulk_case_action`'s queryset.
- [ ] Fix dashboard `recent_notes` (filter through scoped cases, not raw org).
- [ ] Fix `case_list` `archived=1` branch to re-apply scoping.
- [ ] Regression tests: for a `restrict_caseworker_visibility` org, a restricted worker probing
      another worker's case ID gets 404 on **every** endpoint (parameterized over the URL list —
      so a future endpoint that forgets the helper fails the test only if added to the list;
      also add a meta-test that greps `vso/views.py` for raw `VeteranCase.objects` lookups to
      catch new bypasses).
- **Acceptance:** one enforced code path for case access; the parameterized 404 suite passes.

### 1.2 Protected appeal-document lifecycle (P1)
- [ ] Land/merge the protected-media work already open (PR #36 for appeals, PR #37 for the
      claims-side affordance) rather than re-implementing — review, rebase onto this branch's
      successor, merge.
- [ ] Server-side upload validation on `AppealDocumentForm`: python-magic content check +
      size cap, mirroring `claims`' existing document validation.
- [ ] Delete the stored file when the row is deleted (post-delete signal or explicit
      `document.file.delete(save=False)`), on both appeals and any other `FileField` models.
- [ ] Tests: direct `MEDIA_URL` fetch of an appeal doc is impossible (or 404); oversized/wrong
      type rejected server-side; file gone from storage after delete.
- **Acceptance:** no template anywhere renders a raw `doc.file.url` for protected content
  (add a template-scan test).

### 1.3 Storage that actually works (P1)
- [ ] Migrate `DEFAULT_FILE_STORAGE`/`STATICFILES_STORAGE` → the `STORAGES` dict (Django ≥5.1);
      test with `USE_S3=True` that `default_storage` really is S3/Spaces.
- [ ] Replace `document.file.path` uses (`claims/tasks.py:97` and any siblings) with
      `file.open()`/temp-file streaming so OCR works on object storage.
- [ ] Stand up DO Spaces (or S3) bucket, private ACL, server-side encryption; move media.
- [ ] Signed-URL generator continues to front all access (already built).
- [ ] Tests: storage-backend selection under `USE_S3`; OCR pipeline against a non-filesystem
      storage double.
- **Acceptance:** production media lives in private object storage; local `MEDIA_ROOT` is
  dev-only.

### 1.4 Encryption sweep for narratives (P1)
- [ ] `CaseNote.content` → `EncryptedTextField` + data migration.
- [ ] `AssistantTurn.content` (PHI-flagged transcript) → `EncryptedTextField` + data migration.
- [ ] Agent analysis JSON (`conditions_granted/denied/deferred`, evidence-gap payloads) →
      `EncryptedJSONField` + data migrations (pattern exists from `ai_summary`, 2026-02-11).
- [ ] Measure query impact: encrypted fields can't be filtered/searched server-side — audit call
      sites first (the `case_list` search already excludes encrypted description; repeat that
      review per field).
- [ ] Tests: round-trip per field; migration on populated data.
- **Acceptance:** every free-text field that can contain a veteran's medical narrative is
  encrypted at rest; `docs/PHI_DATA_FLOW.md` updated to say so truthfully.

---

## Phase 2 — Correctness a veteran can rely on (~1 week)

### 2.1 Supplemental-claim eligibility (P1)
- [ ] `appeals/forms.py:60`: stop rejecting >1-year-old decisions at intake. Warn instead:
      HLR/Board are time-barred, Supplemental remains available; effective-date consequences
      (wording pattern already established in `appeal_detail.html`, 2026-07-23).
- [ ] `agents/services.py:314`: replace the blanket 1-year `appeal_deadline` with per-lane
      deadlines (HLR/Board: 1 year; Supplemental: none + effective-date note) in the analyzer
      output schema.
- [ ] Tests: intake accepts an 18-month-old decision; analyzer output distinguishes lanes.
- **Acceptance:** no code path tells a veteran they cannot file a Supplemental Claim after a
  year; CFR citations in code comments.

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
- [ ] Flip `VSO_MFA_REQUIRED` default → `True` (grace period stays); enroll existing staff.
- [ ] Flip `ADMIN_OTP_REQUIRED` → `True` in prod once superusers are enrolled.
- [ ] Account lockout after repeated failed logins (django-axes or allauth rate-limit) — open
      TECHNICAL DEBT item; required by NIST 800-53 AC-7.
- [ ] JWT refresh lifetime 7d → 24h (open P2).

### 3.2 Transport & platform security
- [ ] Redis TLS: replace `ssl.CERT_NONE` with `CERT_REQUIRED` + CA bundle (DO Managed Valkey
      supports verified TLS); env-var escape hatch for local only.
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

## Phase 4 — Compliance & procurement readiness (parallel track, start now)

Engineering fixes alone don't win contracts. Two **strategic decisions** gate everything else
here — make them first, they change the infrastructure work above:

### Decision A — Hosting: DigitalOcean is not FedRAMP-authorized
- Federal (VA direct): requires FedRAMP-authorized infrastructure → plan a migration path to
  AWS GovCloud / Azure Government, or partner through a FedRAMP-authorized reseller platform.
- State/county veterans agencies (often the realistic first contract): **StateRAMP** or plain
  SOC 2 + contract security terms may suffice — dramatically cheaper.
- [ ] **Decide the target market first** (federal vs state/local vs VSO-org B2B with government
      funding). Everything in this phase scales to that choice. Record as ADR-006.

### Decision B — The AI data boundary
- Current posture ("Not HIPAA compliant — educational use only", TODO.md) is incompatible with
  a government pitch involving real veteran records.
- [ ] Anthropic offers zero-data-retention and BAA options, and Claude is available through
      FedRAMP-High-authorized channels (AWS Bedrock in GovCloud). Pick the channel that matches
      Decision A; get the DPA/BAA in writing.
- [ ] Update `docs/PHI_DATA_FLOW.md` and the user-facing consent copy to match reality.

### Artifacts to produce (checklist for the pitch binder)
- [ ] **System Security Plan (SSP) lite** — NIST 800-53 rev5 moderate-baseline control mapping;
      most technical controls map to work in Phases 0–3 (AC → 1.1/3.1, AU → existing AuditLog,
      SC → 1.3/1.4/3.2, IR → INCIDENT_RESPONSE.md, CP → 3.3).
- [ ] **Privacy Impact Assessment (PIA)** — data inventory exists in PHI_DATA_FLOW.md; extend to
      full PIA format (what's collected, why, retention, sharing, deletion — Phase 0.1 makes the
      deletion answer honest).
- [ ] **Section 508 / WCAG 2.2 AA conformance**: run a full audit (axe + manual AT pass — the
      `bas-design-review` skill's checklist), fix findings, and produce a **VPAT/ACR** document.
      The a11y work already done (aria-live fixes, target sizes) feeds straight in.
- [ ] **Third-party penetration test** — schedule after Phase 1 lands (testing before the known
      authz fixes wastes the engagement); remediate; keep the letter.
- [ ] **SOC 2 Type I → II path** (if pursuing state/B2B): controls largely = Phases 0–3 outputs;
      engage an auditor for readiness assessment.
- [ ] **SBOM** (CycloneDX via `pip-audit`/`cyclonedx-bom`) generated in CI — increasingly a
      federal solicitation requirement (EO 14028).
- [ ] **Data-retention & deletion policy** doc — written from the Phase 0.1 implementation, not
      aspiration.
- [ ] **Incident response**: existing INCIDENT_RESPONSE.md + a tabletop exercise log (do one,
      date it).
- [ ] **Accessibility, privacy, and security statements** on the public site.
- [ ] Complete the two open security-invariant items: git-history secrets are scrubbed (done
      2026-02-12) but **AGENTS.md still says otherwise — fix the doc**; credential rotation is
      Phase 0.4.

---

## Sequencing & effort summary

| Phase | Content | Effort (focused) | Blocks |
|---|---|---|---|
| 0 | Deletion, export, invitations, credential rotation | ~1 week | Everything — these are the integrity items |
| 1 | VSO scoping, protected media, storage, encryption | ~2 weeks | Pen test, SSP technical controls |
| 2 | Appeal rules, structured AI, regulatory process | ~1 week | — |
| 3 | MFA/lockout, TLS/CSP, backups/DR, CI gates | ~1–2 weeks | SOC 2 readiness |
| 4 | Decisions A & B now; artifacts alongside 1–3 | rolling | The pitch itself |

**Order of operations:** Phase 0 first and alone (small, test-backed PRs per item — 0.1 is its
own PR). Decisions A & B in parallel this week since they may redirect Phase 1.3 (storage
choice) and the AI gateway config. Phases 1–3 as sequenced PRs. Third-party pen test after
Phase 1. Pitch binder assembles as artifacts complete.

**Definition of done for "pitchable":** every TODO.md P0/P1 checked; pen-test letter with
criticals remediated; VPAT; PIA; deletion/export demonstrably honest end-to-end; hosting + AI
channel matched to the chosen market; and no doc in the repo that contradicts reality.
