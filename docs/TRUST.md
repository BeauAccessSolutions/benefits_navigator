# Trust Claims Register

**Rule: no privacy or security claim ships in marketing, the website, or sales
material without a row in this table.** Every row maps a public claim to the
code that enforces it and the test that proves it. If a control changes, update
the row before the claim is repeated; if a claim has no row, it doesn't get made.

**Last verified:** 2026-06-09 (branch `feat/privacy-hardening-phase0-1`, 905 tests passing)

## Claims you may make

| # | Public claim | Enforcing control | Proof (tests) | Caveats |
|---|--------------|-------------------|----------------|---------|
| 1 | "You control what's shared. VSOs only see documents you choose to share." | Sharing is veteran-initiated only: `claims/views.py document_share` creates `SharedDocument` with `shared_by=request.user`; no VSO-side pull path exists | `vso/tests.py TestCrossOrgSecurity`; `tests/test_document_unshare.py` | — |
| 2 | "You can revoke access at any time, and it takes effect immediately." | `claims/views.py document_unshare` — owner-only POST deletes the share; all VSO access joins through `SharedDocument` | `tests/test_document_unshare.py` (9 tests incl. VSO-loses-access) | VSO retains their own case notes (their work product) |
| 3 | "AI analysis is shared only if you opt in, per document." | `SharedDocument.include_ai_analysis` defaults False (`vso/models.py`); review view checks it before querying analyses | `vso/tests.py`; share-flow tests | — |
| 4 | "You can see everyone who has viewed your records — including our own staff." | `/data-activity/` (`core/views.py data_activity`); VSO views log in `vso/views.py case_detail`/`shared_document_review`; admin views log via `core/admin.py PIIRedactedAdminMixin` | `tests/test_data_activity.py` (8), `tests/test_admin_redaction.py TestAdminAccessLogging` | Shows accesses from 2026-06-09 onward (logging added then) |
| 5 | "Your personal and medical information is encrypted at rest." | Fernet AES-128-CBC+HMAC field encryption (`core/encryption.py`): DOB, VA file number, phone, AI summaries, condition tags, case descriptions/conditions/notes | `tests/test_security_controls.py TestEncryptionRoundTrip` (ciphertext-at-rest assertions) | Metadata (file names, statuses, dates) is not encrypted; say "personal and medical information," not "all data" |
| 6 | "AI processing happens only with your explicit consent, and you can withdraw it." | `ai_processing_consent` + consent date (`accounts/models.py`); `@require_ai_consent_view` on every AI endpoint; check fails closed (`agents/views.py`) | consent-gated view tests in `claims/tests.py`, `agents/tests.py` | — |
| 7 | "Document links expire automatically and can't be forged." | HMAC-SHA256 signed URLs, 30-min default / 24-h max expiry (`core/signed_urls.py`); 30/min IP rate limit on token endpoints | `tests/test_security_controls.py TestSignedURLSecurity` (7 tests) | — |
| 8 | "Organizations can enforce least-privilege access for their staff." | `Organization.restrict_caseworker_visibility` + `scope_cases_for_member` (`vso/permissions.py`) applied to case list/detail/dashboard/reports | `tests/test_least_privilege.py TestCaseworkerScoping` | Per-org opt-in; default is org-wide visibility — phrase as "can enforce," not "enforces" |
| 9 | "Bulk export of veteran data is restricted, rate-limited, and monitored." | Org-admin-only CSV export, 5/h limit, ops alert per export, no veteran emails in output (`vso/views.py _export_cases_csv`) | `tests/test_least_privilege.py TestExportPrivilege` | — |
| 10 | "Two-factor authentication is enforced for staff handling veteran data." | `VSOStaffMFAMiddleware` with `VSO_MFA_REQUIRED`; `ADMIN_OTP_REQUIRED` (OTPAdminSite) for /admin | `tests/test_least_privilege.py TestMFAEnforcement` | **Only claimable once both flags are True in production** — verify DO config first |
| 11 | "Our own staff cannot browse your documents or medical details through admin tools." | Admin renders no PII/PHI content: `claims/admin.py`, `vso/admin.py`, `accounts/admin.py` redactions | `tests/test_admin_redaction.py TestAdminPIIRedaction` (4 tests) | Database-level access still exists for operators with credentials — see claim 12 phrasing |
| 12 | "Operator access is minimized, logged, and visible to you." | Claims 4 + 11 combined; Sentry `send_default_pii=False`; alerts carry user IDs not emails (`core/alerting.py`) | as above | This is the honest version of "we can't see your data" — never make the stronger claim |
| 13 | "Every sensitive action is audit-logged." | `core/models.AuditLog` + `AuditMiddleware`; VSO and admin instrumentation | audit assertions across test suites | — |

## Claims you may NOT make (and what to say instead)

| Forbidden claim | Why | Say instead |
|-----------------|-----|-------------|
| "HIPAA compliant" | Benefits Navigator is almost certainly not a HIPAA covered entity or business associate; the claim creates liability without obligation | "Designed to HIPAA-aligned safeguards" (pending counsel sign-off) |
| "We can't see your data" / "zero-knowledge" | Operators with database credentials and the encryption key can decrypt PII; this is standard server-side encryption, not E2E | Claim 12 |
| "Your data never leaves our servers" | Document text is sent to OpenAI's API for analysis | "AI analysis uses OpenAI's API under terms that prohibit training on your data" — **only after the API terms are contractually pinned (see Open items)** |
| "Bank-level / military-grade encryption" | Marketing fluff that invites scrutiny; Fernet is AES-128-CBC + HMAC-SHA256 | Claim 5, or name the actual algorithms |
| "Your data is never used for surveillance" (absolute) | A platform cannot fully control authorized-user misuse | "Built to resist surveillance use: veteran-controlled sharing, full access transparency, and Terms that prohibit monitoring uses" + claims 1–4 |
| Anything implying VA affiliation or endorsement | Not affiliated; also a 38 CFR § 14.633 adjacent risk for VSO partners | Existing footer disclaimer language |

## Open items blocking specific claims

- [ ] **Credential rotation in DO Console** (outstanding since 2026-02) — until done, internal confidence in claim 5 is weakened; rotate before launch.
- [ ] **Pin OpenAI API data-use terms** — confirm/document that API inputs are not used for training (OpenAI API default) and data retention window; record the terms version/date here. Blocks the "no training on your data" phrasing.
- [ ] **Set `VSO_MFA_REQUIRED=True` and `ADMIN_OTP_REQUIRED=True` in production** — blocks claim 10.
- [ ] **Counsel review** of docs/legal/TERMS_DRAFT.md and PRIVACY_POLICY_DRAFT.md, and of "HIPAA-aligned safeguards" phrasing.
- [ ] **Publish the privacy policy and ToS** at /terms/ and /privacy/ once approved (no pages exist yet).
