Risk Register (Top 10)
======================

1) Prompt injection & untrusted text handled inconsistently  
   - Files: `claims/services/ai_service.py:sanitize_document_text`, `claims/services/rating_analysis_service.py:sanitize_document_text`, `agents/services.py:sanitize_user_input`.  
   - Issue: Multiple sanitizers with overlapping but not comprehensive patterns; system/user prompts rely on LLM compliance; no output schema validation beyond `json.loads`, so injected instructions or malformed JSON can slip through and get stored.  
   - Mitigation: Consolidate sanitization into one hardened helper (allowlist characters, strip headers/footers), add JSON schema validation for each agent output and reject/flag unsafe content before saving or showing it.

2) AI consent not enforced for pasted-text agent flows  
   - Files: `agents/views.py:decision_analyzer_submit`, `evidence_gap_submit`, `statement_generator_submit`.  
   - Issue: Users can run OpenAI-backed analyses without `UserProfile.ai_processing_consent`; only upload flows enforce it.  
   - Mitigation: Require consent check in agent views (reuse `claims.tasks.require_ai_consent`) and gate UI with consent banner.

3) Sensitive OCR/AI data exposed via GraphQL without redaction/limits  
   - Files: `benefits_navigator/schema.py:document_analysis` returns raw `ocr_text` and `ai_summary` for any authenticated owner.  
   - Issue: No length throttling or masking; tokens can be exfiltrated if session compromised.  
   - Mitigation: Truncate/strip PII (file numbers/SSN patterns), add pagination/size caps, consider feature flag to disable returning full text via GraphQL.

4) OpenAI calls lack timeouts/retries and may hang tasks  
   - Files: `agents/services.py:BaseAgent._call_openai`, `claims/services/ai_service.py:analyze_document`.  
   - Issue: No explicit timeout or retry/backoff; Celery retries wrap whole task but a stuck HTTP request can block workers; OpenAI errors bubble to user-facing failures.  
   - Mitigation: Set request timeouts, implement limited retries with idempotent behavior, and capture/return structured failure states to the UI.

5) Unvalidated AI outputs persisted directly to DB  
   - Files: `claims/tasks.py:decode_denial_letter_task` (DecisionLetterAnalysis/DenialDecoding), `claims/tasks.py:analyze_rating_decision_task` (RatingAnalysis), `claims/services/ai_service.py` (Document.ai_summary).  
   - Issue: No schema validation or bounds checking on JSON fields; malformed or adversarial output can break templates or downstream logic.  
   - Mitigation: Define JSON schemas for each model field and validate before save; store raw text separately and discard/flag invalid structures.

6) VSO org scoping depends on first membership, not explicit selection  
   - Files: `vso/views.py:get_user_organization` uses first active membership; `dashboard/case_list/case_detail` queries by that org.  
   - Issue: Users in multiple orgs may see the wrong org’s data if membership ordering changes; no per-request org selector.  
   - Mitigation: Require explicit org slug in URLs/session, validate membership per-request, and deny access when ambiguous.

7) Shared document review may leak AI analyses by default  
   - Files: `claims/views.py:document_share` sets `include_ai_analysis` default True; `vso/views.shared_document_review` auto-pulls analyses.  
   - Issue: Veterans may unintentionally expose AI-derived insights (potentially incorrect/PII) to VSOs without granular control.  
   - Mitigation: Default include_ai_analysis to False, add explicit consent checkbox with explanation, log sharing in `AuditLog`.

8) Audit logging and retention not consistently applied  
   - Files: `core/models.AuditLog` exists but many views (agent submissions, VSO actions) do not log; retention policy optional (`core/tasks.create_default_retention_policies` not enforced).  
   - Issue: Security events and PII access may be untracked or retained indefinitely.  
   - Mitigation: Add AuditLog entries for AI runs, case access, and shares; run retention task on schedule; expose admin checks for stale policies.

9) File upload validation depends on python-magic and PyMuPDF availability  
   - Files: `claims/forms.py:DocumentUploadForm` rejects uploads when magic missing; OCR service assumes PyMuPDF/Pillow present.  
   - Issue: Deploys without these libs break uploads entirely; user receives generic error, no monitoring.  
   - Mitigation: Add startup health check for dependencies, fail fast with clear admin alert, and provide graceful fallback (extension + content_type) until fixed.

10) Limited automated test coverage for critical flows  
   - Files: tests focus on `agents/tests.py`; minimal coverage for claims uploads/tasks, VSO permissions, invitations, GraphQL, or Celery pipelines.  
   - Issue: Regression risk in core Path A/B flows and AI consent/permissions; no end-to-end checks for background tasks.  
   - Mitigation: Add tests for claims upload → task dispatch, VSO access control, invitation acceptance, and OpenAI wrapper mocks; include contract tests for GraphQL resolvers and HTMX endpoints.
