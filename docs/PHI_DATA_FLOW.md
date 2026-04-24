# PHI/PII Data Flow & Boundary Map

Documents where Protected Health Information (PHI) and Personally Identifiable
Information (PII) travel through the system, what is persisted, what is ephemeral,
and what encryption is applied.

---

## Definitions

- **PHI** — Protected Health Information: medical conditions, disability ratings, C&P exam
  details, VA file numbers, service records. Subject to HIPAA-adjacent obligations.
- **PII** — Personally Identifiable Information: name, email, date of birth, phone number,
  SSN. Subject to standard data protection requirements.
- **Ephemeral** — exists only in-process memory during a single task execution; never
  written to database, logs, or external storage.

---

## System Boundary Map

```
User Browser
    │
    │ HTTPS (TLS 1.2+)
    ▼
DigitalOcean App Platform (NYC region)
┌─────────────────────────────────────────────────────┐
│                                                     │
│  Django Web Process                                 │
│  ┌─────────────────────────────────────────────┐   │
│  │  View Layer                                 │   │
│  │  - Auth check (session/JWT)                 │   │
│  │  - AI consent check                         │   │
│  │  - Rate limiting                            │   │
│  │  - Document scoped to request.user          │   │
│  └──────────────────┬──────────────────────────┘   │
│                     │ Celery task dispatch           │
│                     │ (document_id only, no PHI)    │
│  ┌──────────────────▼──────────────────────────┐   │
│  │  Celery Worker                              │   │
│  │  - Fetches Document record by ID            │   │
│  │  - OCR: text extracted to memory [EPHEMERAL]│   │
│  │  - AI analysis: text sent to OpenAI         │   │
│  │  - AI response parsed and persisted         │   │
│  │  - OCR text discarded (never saved)         │   │
│  └──────────────────┬──────────────────────────┘   │
│                     │                               │
└─────────────────────┼───────────────────────────────┘
                      │
        ┌─────────────┼──────────────┐
        ▼             ▼              ▼
   PostgreSQL       Redis          OpenAI API
   (managed DO)   (broker)       (external)
```

---

## Data Inventory

### What Leaves the Platform

| Data | Destination | What is Sent | Retained by Destination |
|---|---|---|---|
| OCR-extracted document text | OpenAI API | Full text of VA document (contains PHI) | Per OpenAI data retention policy; not used for training (API usage) |
| AI analysis prompts | OpenAI API | Structured prompt without raw PII fields | Same as above |
| Error events | Sentry | Stack traces, no PII (`send_default_pii=False`) | 90 days (Sentry default) |
| Alerts | Email / Slack | Error metadata, document_id, failure_type — no PHI | Depends on email/Slack retention |

> **Critical Note:** OCR text sent to OpenAI is the highest-risk data boundary. The
> document files themselves (PDFs) are processed in-worker and not sent; only the
> extracted text is forwarded.

### What is Persisted in PostgreSQL

| Model | Field | Contains | Encrypted |
|---|---|---|---|
| `accounts.UserProfile` | `va_file_number` | PII (VA identifier) | Yes (`EncryptedCharField`) |
| `accounts.UserProfile` | `date_of_birth` | PII | Yes (`EncryptedDateField`) |
| `accounts.User` | `email` | PII | No (used as login key) |
| `claims.Document` | `file` (S3/local path) | File reference only | At-rest via storage provider |
| `claims.Document` | `ocr_length`, `ocr_status` | Metadata only | No |
| `claims.Document` | ~~`ocr_text`~~ | **REMOVED** — PHI, ephemeral only | N/A |
| `agents.DecisionLetterAnalysis` | `conditions_granted`, `conditions_denied` | AI-extracted, sanitized | No |
| `agents.DecisionLetterAnalysis` | ~~`raw_text`~~ | **REMOVED** — PHI, ephemeral only | N/A |
| `agents.RatingAnalysis` | `conditions`, `insights` | AI-extracted, sanitized | No |
| `agents.RatingAnalysis` | ~~`raw_text`~~ | **REMOVED** — PHI, ephemeral only | N/A |
| `core.AuditLog` | `action`, `ip_address`, `user_id` | Access metadata | No |
| `core.ProcessingFailure` | `error_message`, `stack_trace` | Error text (no PHI by design) | No |

### What is Ephemeral (In-Memory Only)

| Data | Where | Lifetime |
|---|---|---|
| Raw OCR text from document | Celery worker memory | Single task execution |
| Document binary during OCR | Celery worker memory | Single task execution |
| OpenAI request payload | Celery worker memory | Single task execution |

---

## OCR Ephemeral Boundary — Detail

This is the most critical PHI boundary in the system.

```
claims/tasks.py: process_document_task()
                    │
                    ▼
         [1] Fetch document record (ID only in task args)
                    │
                    ▼
         [2] Read file from storage into memory
             local var: file_content (bytes)
                    │
                    ▼
         [3] Tesseract OCR → local var: ocr_text (str)
             ← PHI ENTERS MEMORY HERE
                    │
                    ├──► Save ocr_length, ocr_status to DB (metadata only)
                    │    ← PHI does NOT enter DB
                    │
                    ▼
         [4] Pass ocr_text to ai_gateway.complete_structured()
             → sent to OpenAI API
             ← PHI LEAVES PLATFORM HERE (see note above)
                    │
                    ▼
         [5] AI response (no raw PHI) persisted to DB
                    │
                    ▼
         [6] Task returns — ocr_text goes out of scope
             ← PHI DISCARDED FROM MEMORY HERE
```

**Enforcement:** Tripwire tests in `tests/test_regression_tripwires.py` verify that
`ocr_text`, `raw_text` fields do not exist on relevant models. CI blocks merge if
these fields reappear.

---

## Access Control Boundaries

| Resource | Who Can Access | Enforcement |
|---|---|---|
| Document files | Owner only | All queries filter `user=request.user` |
| Analysis results | Owner + explicitly shared VSOs | `SharedDocument` / `SharedAnalysis` join |
| VSO case data | VSO org members only | `@vso_required` + org-scoped querysets |
| Admin interface | Django staff only | `is_staff=True` |
| Health endpoint | Public (no auth) | `/health/` — no sensitive data returned |
| Full health status | No auth required | `/health/?full=1` — only operational metrics |

> **Note:** `/health/?full=1` is public. It returns celery worker counts, queue depths,
> and processing success rates. No user data or PHI is exposed. Consider adding IP
> allowlist if this becomes a concern.

---

## Data Retention

Managed by `core/tasks.py: enforce_data_retention()` (periodic Celery task).

| Data | Retention Period | Deletion Method |
|---|---|---|
| Audit logs | 365 days | Hard delete |
| Documents (soft-deleted) | 90 days | Hard delete + file cleanup |
| Analysis records | 180 days | Hard delete |
| Sessions | 30 days | Hard delete |
| Pilot mode override | 30 days (`PILOT_DATA_RETENTION_DAYS`) | Same as above |

---

## Known Gaps

1. **OpenAI data retention:** We rely on OpenAI's API data handling policy (no training
   on API data). This should be reviewed periodically and documented in vendor contracts.
2. **S3/local file encryption:** Document files at rest depend on the storage backend.
   DigitalOcean Spaces encrypts at rest by default. Local development does not.
3. **Redis:** Task payloads in the Celery broker contain `document_id` only (no PHI).
   Redis itself is not encrypted at rest in the current DO configuration.
4. **`/health/?full=1` is unauthenticated:** Low risk today; revisit if operational
   metrics become sensitive.

---

## Related Docs

- `docs/security-invariants.md` — automated enforcement of PHI protections
- `docs/INCIDENT_RESPONSE.md` — data breach response (SEV1 escalation)
- `agents/ai_gateway.py` — OpenAI boundary implementation
- `core/encryption.py` — encrypted field implementation
