# Platform membership — Benefits Navigator in the Beau Access Solutions platform

Benefits Navigator (BN) is a member app of the **Beau Access Solutions (BAS)** platform.
This file is the local pointer to the platform governance and the fallback copy of the
platform invariants, per BAS ADR-002 §3 (reference governance by URL; inline the
invariants as a local fallback; no committed cross-repo symlinks).

## Governance home (canonical, by URL)

Governance repo: <https://github.com/Beaudoin0zach/Beau-Access-Solutions>

- `PLATFORM.md` — shared architecture (standalone Keycloak identity, layered sessions, shared design system).
- `INVARIANTS.md` — the five platform invariants (mirrored below as a fallback).
- `docs/adr/001` — standalone Keycloak identity decision.
- `docs/adr/002` — umbrella org, repo topology, no committed cross-repo symlinks.
- `docs/adr/003` — pairwise subject identifiers (no cross-app correlation).
- `docs/adr/004` — migrating existing per-app users into Keycloak.
- `docs/adr/005` — **Benefits Navigator data posture** (Privacy Act / VA vs HIPAA) — this app's regulatory gate.
- `CONTRIBUTING.md` — how an app joins the platform; the PHI/sensitive-data contribution boundary.

Never reference those docs by filesystem path or symlink — always by the URLs above.

## Benefits Navigator's role

**Full identity member, sensitive resource-server tier** — the same handling tier as
CIT, per the conservative working assumption in **ADR-005**. BN handles veteran
benefits-claim data plus PII (`va_file_number`, `date_of_birth` via `EncryptedCharField`),
across two flows:

- **Path A — Veterans (B2C).** End users working their own VA claim: document upload,
  AI decision analysis, denial decoding, statement generation.
- **Path B — VSOs (B2B).** Caseworkers/advocates acting on *another identified person's*
  claim data (shared documents, veteran invitations). This third-party-access flow is
  why BN needs **step-up** on sensitive actions, not just authentication.

BN authenticates through the platform's **Keycloak** IdP rather than its hand-rolled
Django auth, and — because it is a sensitive tenant — exchanges the identity token for
its **own** short-lived, revocable Django session. The identity token is never itself a
data-access credential (invariant #1).

**Regulatory posture is not yet final.** BN is engineered to Member spec, but stays a
**Candidate** in the platform tracker until BAS LLC obtains the legal determination
scoped in ADR-005 (whether 38 U.S.C. § 5701 / 38 CFR §§ 1.500–1.527 and/or Privacy Act
flow-down reach BN's Path A/B data). Promotion Candidate → Member is gated on that
determination, not on any remaining code.

## Current status (2026-07-08)

The identity half is on paper because the platform IdP is Phase 0 (not stood up). What
already holds vs. what waits on Keycloak:

- [x] Governance pointer + invariants fallback (this file).
- [x] **Sensitive backend isolated in its own repo** (invariant #4) — trust boundary =
  repo boundary. BN's sensitive paths never move into shared `ui`/`auth`/`config`.
- [x] **Decoupled deletion / export** (invariant #3) — self-service
  `/accounts/export/` (`data_export`) and `/accounts/delete/` (`account_deletion`)
  routes exist on `main`, with an export-audit trail
  (`core/migrations/0009_add_export_audit_actions.py`). Keyed by the BN user today; the
  Keycloak pairwise `sub` resolves to it later with no change to the lifecycle.
- [x] **PII encryption at rest** — `va_file_number`, `date_of_birth` use
  `EncryptedCharField` (`core/encryption.py`); non-negotiable in `CLAUDE.md`.
- [x] **AI-output safety** (supports invariant #2's "no leakage" spirit) — all model
  I/O goes through the AI Gateway (`agents/ai_gateway.py`): `sanitize_input()` on the
  way in, Pydantic schema validation on the way out; no raw PII prompts/responses stored.
- [~] **CODEOWNERS + required review on sensitive paths** (invariant #4) — landing via
  PR #22 (`chore/review-governance`); enable "Require review from Code Owners" in branch
  protection once merged.
- [x] **Security CI gate** — `.github/workflows/security-checks.yml` runs on the repo.
- [ ] Register an OIDC client for BN on Keycloak — `aud`/`azp` isolation, pairwise `sub`
  per ADR-003 (when the IdP exists).
- [ ] Verify Keycloak OIDC (JWKS, `iss`/`aud`/`azp`) — port CIT's resource-server
  pattern (`feat/oidc-session-endpoint`, 177 tests) to Django.
- [ ] Exchange the verified identity token → BN's own revocable Django session
  (invariant #1); replace hand-rolled login as the entry point.
- [ ] **Step-up (ACR) on sensitive actions** — export, account deletion, statement
  generation, and *any Path B action on another veteran's data*.
- [ ] Existing-user migration into Keycloak — on-login (lazy), per ADR-004; BN follows
  the CIT reference runbook.
- [ ] Retire the Django password login path once Keycloak is live.
- [ ] Legal determination per ADR-005 → promote Candidate → Member in the tracker.

## The five platform invariants (fallback copy — canonical version in governance `INVARIANTS.md`)

1. **Layered sessions.** The identity service proves *who you are* (short-lived OIDC
   token). Sensitive apps **exchange** it for their **own** short-lived, revocable,
   rate-limited data-access session and require **step-up** for sensitive actions. An
   identity token is never itself a data credential. (BN is a sensitive tenant: it
   exchanges for its own Django session and steps up on Path B + destructive actions.)
2. **No platform tracking on sensitive pages.** The shared `ui` is telemetry-free; an
   import-boundary lint makes importing analytics into a sensitive route a build
   failure; each app owns its own CSP. (BN avoids logging PII and gates model I/O
   through the AI Gateway.)
3. **Decoupled deletion / export.** Identity stores identity only, keyed by `sub`. Each
   app owns its data lifecycle; delete/export stay independently callable and complete.
   (BN owns its Django/Postgres lifecycle — self-service export + deletion already ship.)
4. **Contribution boundary.** Sensitive backends stay in their own repos — trust
   boundary = repo boundary. Shared `ui`/`auth`/`config` stay open; sensitive paths get
   CODEOWNERS + required review. (BN's veteran-data backend stays in this repo.)
5. **i18n ownership.** Shared `ui` components carry zero hardcoded copy; string
   catalogs are per-app owned with per-app human-review gates. The platform never
   injects strings. (BN owns its copy; human-reviewed Spanish is a store-launch prereq.)

These map onto BN's own non-negotiables (`CLAUDE.md`) and never relax them. If a
platform requirement ever conflicts with a BN non-negotiable, the more conservative
(more private, more accessible) rule wins and the conflict is raised as a BAS ADR.
