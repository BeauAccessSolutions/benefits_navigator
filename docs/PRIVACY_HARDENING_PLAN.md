# Privacy Hardening Plan — Anti-Surveillance Lockdown

**Created:** 2026-06-09
**Goal:** Make Benefits Navigator structurally resistant to use as a veteran-surveillance tool before marketing, and make every marketing privacy claim traceable to an enforcing control.
**Threat model:** Not external attackers (see `audits/2026-06-09/comprehensive-audit.md`) — *authorized* parties: VSO org staff, the platform operator, and the AI vendor.

Each phase is one PR: tests added with the change, `pytest` green before merge, conventional commits.

---

## Phase 0 — Pre-marketing table stakes (~1 day + manual ops)

Blockers that undermine every claim if left open.

1. **Deploy fix:** add `'django.contrib.postgres'` to INSTALLED_APPS (`benefits_navigator/settings.py:86`); add `python manage.py check --deploy` step to `.github/workflows/tests.yml`.
2. **Credential rotation (manual):** rotate SECRET_KEY, FIELD_ENCRYPTION_KEY, DATABASE_URL, REDIS_URL in DO Console; run `manage.py rotate_encryption_key --execute`; redeploy. Open since 2026-02 — every encryption claim is hollow until done.
3. **Encrypt remaining PII/PHI fields** (one migration per app, following the `0005_encrypt_ai_summary` pattern):
   - `accounts/models.py:48` `phone_number` → EncryptedCharField
   - `vso/models.py` `description`, `conditions`, `c_and_p_exam_notes`, `closure_notes` → EncryptedTextField/EncryptedJSONField
   - `claims/models.py:116` `condition_tags` → EncryptedJSONField
4. **PII out of ops channels:** `core/alerting.py:348` — replace `user__email` with user ID in anomaly alerts.
5. **Throttle signed-URL endpoints:** `@ratelimit(key='ip', rate='30/m', block=True)` on `claims/views.py:547,629`.
6. **Security regression tests** (prove the controls work): signed-URL expiry/tampering/wrong-user (`claims/tests.py`), encryption round-trip incl. EncryptedJSONField (`core/tests.py`), GraphQL PII redaction (`benefits_navigator/schema.py` patterns).

## Phase 1 — Revocable sharing (~1–2 days)

Sharing is currently a one-way door: veteran shares via `claims/views.py:855`, nothing un-shares.

1. **AuditLog actions:** add `document_unshare`, `analysis_unshare` to `ACTION_CHOICES` (`core/models.py`).
2. **Views (veteran-side, `claims/views.py`):** `document_unshare(request, pk, share_pk)` — POST only, owner check (`document.user == request.user`), deletes the `SharedDocument` row, writes AuditLog. Same for `SharedAnalysis`. Hard delete, not soft: post-revocation, data minimization beats VSO convenience; the AuditLog row is the permanent record that a share existed. VSO `CaseNote`s they wrote remain theirs.
3. **URLs:** `document/<pk>/share/<share_pk>/revoke/` in `claims/urls.py`.
4. **UI:** "Shared with" section on `document_detail.html` listing active shares (org name, date, AI-analysis flag) with a Revoke button; confirmation dialog; `role="alert"` success message; follow CLAUDE.md a11y patterns.
5. **VSO side needs no changes** — all VSO access joins through `SharedDocument`, so deletion removes access automatically. Verify with tests.
6. **Tests:** veteran revokes → VSO `case_detail`/`shared_document_review` lose access (404); non-owner cannot revoke (404, not 403 — don't leak existence); revoke is audit-logged; re-share after revoke works (`unique_together` freed by delete).

## Phase 2 — Access transparency: "Your data activity" (~1–2 days)

Kills the information asymmetry surveillance depends on. AuditLog already records everything; it's just not surfaced to veterans.

1. **Query helper (`core/services/` or model manager):** accesses *of* a veteran's records *by others*: AuditLog rows where `resource_type='Document'` and `resource_id` in the veteran's documents, plus case-view/note actions on `VeteranCase` rows where `veteran=user` — excluding rows where `user == request.user`. Add the composite AuditLog indexes from the audit (`['user','timestamp']`, `['action','timestamp']`) in the same PR; this page needs them.
2. **View + template:** `/account/data-activity/` — paginated table: who (name + org), what (humanized action), which record, when. Plain-language header: "Every time someone at your VSO views your records, it's recorded here."
3. **Surface it:** link from dashboard and from the document "Shared with" section (Phase 1).
4. **Tests:** veteran sees VSO accesses of own docs; never sees other veterans' activity; own actions excluded; pagination.

Optional fast-follow (separate PR): weekly digest email "your records were viewed N times" via existing reminder task pattern (`acks_late=True`).

## Phase 3 — Least privilege + export controls in the VSO path (~2–3 days)

1. **Caseworker scoping:** add `restrict_caseworker_visibility` BooleanField (default False) to `Organization`. When True, non-admin members (`OrganizationMembership.role != 'admin'`, helpers at `accounts/models.py:595-615`) get `cases.filter(Q(assigned_to=user) | Q(assigned_to__isnull=True))` in `case_list`, `case_detail`, `reports`, and the dashboard. Per-org opt-in avoids breaking current pilots; marketing can still say the control exists.
2. **Export as a privilege:** CSV export (`vso/views.py:373,417,555,1515`) requires org-admin role; `@ratelimit(key='user', rate='5/h')`; fire an alert through `core/alerting.py` on each export (count + org, no PII) so bulk pulls are visible to ops the way bulk downloads already are.
3. **Minimize export contents:** drop veteran email from the default CSV columns (case title + status suffice for casework; full export stays admin-only).
4. **MFA enforcement:** flip `VSOStaffMFAMiddleware` from warn to enforce for VSO staff (the redirect-to-`two-factor-setup` path already exists at `vso/middleware.py:100-113`); settings flag + 7-day grace period message before the cutover date.
5. **Tests:** caseworker in restricted org can't reach unassigned case (404); export denied for caseworker; export rate limit; MFA redirect for un-enrolled staff.

## Phase 4 — Operator access minimization (~1–2 days)

1. **Admin PII redaction:** in `claims/admin.py` DocumentAdmin exclude/readonly `ai_summary` + OCR text; `accounts/admin.py` UserProfileAdmin exclude `va_file_number`, `date_of_birth`, `phone_number` from list_display and forms (read shows "•••• encrypted"); same treatment for VSO case admin. Staff debugging needs metadata, not content.
2. **OTP-protected admin:** switch to `django_otp.admin.OTPAdminSite` so /admin requires a TOTP device (django-otp already installed).
3. **Admin access audit:** override `ModelAdmin.change_view`/`history_view` on PII-bearing models to write `AuditLog(action='admin_action')` rows — operator access shows up in the same ledger as VSO access (and on the veteran's Phase 2 page, listed as "Benefits Navigator staff").
4. **Tests:** admin pages render without decrypted PII; admin views logged.

## Phase 5 — Policy + marketing claims register (drafting, parallel to any phase)

Not code, but the deliverable marketing actually ships on.

1. **`docs/TRUST.md` — claims register.** Every public claim mapped to its enforcing control and test, e.g. "You control sharing and can revoke it anytime" → Phase 1 views + tests. Rule: no claim ships without a row here.
2. **ToS anti-surveillance clauses (counsel review):** prohibit platform use by/for employers, insurers, or any third party to monitor veterans; prohibit org re-export/resale of veteran data; revocation honored within X hours; breach = termination.
3. **Privacy policy:** name OpenAI as subprocessor; pin API no-training terms contractually; state retention windows (tasks already enforce them — cite them).
4. **Language guardrails:** never "HIPAA compliant" (almost certainly not a covered entity) — "designed to HIPAA-aligned safeguards" pending counsel; never "we can't see your data" — "operator access is minimized, MFA-protected, and visible to you in your activity log" (true after Phase 4).

---

## Sequencing and effort

| Phase | Effort | Unblocks | Status |
|-------|--------|----------|--------|
| 0 — Table stakes | ~1 day + manual rotation | Everything; deploy is broken without item 1 | ✅ Done 2026-06-09 (credential rotation still manual) |
| 1 — Revocable sharing | 1–2 days | "You can revoke access anytime" | ✅ Done 2026-06-09 |
| 2 — Access transparency | 1–2 days | "See everyone who's viewed your records" | ✅ Done 2026-06-09 |
| 3 — Least privilege + exports | 2–3 days | B2B security questionnaires | ✅ Done 2026-06-09 |
| 4 — Operator minimization | 1–2 days | "Operator access is logged and minimized" | ✅ Done 2026-06-09 (set ADMIN_OTP_REQUIRED=True in prod after superusers enroll TOTP) |
| 5 — Policy/claims register | drafting | Marketing copy itself | Pending |

Total: roughly **6–10 dev-days**. Phases 1+2 are the marketing-differentiating pair; 0 is non-negotiable; 3–4 can land after launch if pilot orgs are trusted, but before any self-serve org signup.

**Out of scope here** (tracked in TODO.md from the 2026-06-09 audit): CSP/Tailwind work, N+1 fixes, transaction boundaries, lxml bump — do them, but they're general hardening, not surveillance-specific.
