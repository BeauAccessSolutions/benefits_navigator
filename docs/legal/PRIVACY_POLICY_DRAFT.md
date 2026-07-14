# Privacy Policy (DRAFT)

> **STATUS: DRAFT — NOT LEGAL ADVICE. REQUIRES ATTORNEY REVIEW BEFORE
> PUBLICATION.** Written to be accurate against the codebase as of 2026-06-09;
> every operational statement below is backed by a control listed in
> docs/TRUST.md. Do not publish claims this draft does not contain.

---

## What we collect

- **Account information:** email, name, password (hashed), and optionally a
  phone number.
- **Veteran profile:** branch of service, disability rating, and optionally
  date of birth and VA file number.
- **Documents you upload:** VA decision letters, medical records, and other
  claim documents, plus text we extract from them (OCR) and AI-generated
  analyses of them.
- **Case data (if you work with a VSO):** case status, notes, conditions, and
  documents you choose to share.
- **Usage and security data:** log-ins, document views and downloads, feature
  usage, IP addresses, and device information.

## How we protect it

- **Encryption at rest.** Sensitive personal and medical fields — date of
  birth, VA file number, phone number, AI analyses, condition information, and
  case notes/descriptions — are encrypted with authenticated symmetric
  encryption (Fernet: AES-128-CBC with HMAC-SHA256) before storage. All data
  is also encrypted in transit (TLS).
- **Expiring links.** Document download links are cryptographically signed and
  expire automatically (30 minutes by default).
- **Staff access controls.** Our administrative tools do not display your
  document contents, medical details, or identifiers; staff access to your
  records is logged and visible to you (see "Your rights"). Staff and VSO
  accounts are protected with two-factor authentication [when
  VSO_MFA_REQUIRED/ADMIN_OTP_REQUIRED are enabled — confirm before publishing].

## Who can see your information

- **You.**
- **A VSO you choose to work with — only what you share.** Sharing is always
  initiated by you, per document. Sharing your document does not share its AI
  analysis unless you separately opt in. You can revoke any share at any time,
  effective immediately.
- **Our staff — minimally, and visibly.** Operational staff can see account
  and processing metadata. They cannot browse your document contents or
  medical details through our administrative tools, and every staff access to
  your records appears in your data activity log.
- **Service providers (subprocessors)** listed below.
- **No one else.** We do not sell your data. We do not share it with
  employers, insurers, data brokers, or government agencies except in response
  to valid legal process, and where lawful we will notify you before
  disclosing.

## AI processing and OpenAI

If you consent to AI processing, text from your documents is sent to
**OpenAI** (API) to generate analyses such as decision-letter summaries and
evidence recommendations. Under OpenAI's API terms [verify and date-stamp
before publication], API inputs and outputs are not used to train OpenAI's
models, and are retained by OpenAI for a limited abuse-monitoring period
[confirm current window] before deletion.

You can decline or withdraw AI-processing consent at any time in Privacy
Settings; without consent, no document text is sent to OpenAI. AI outputs are
educational drafts, not legal advice, and can be wrong — review them with an
accredited representative.

## Your rights

Available to every user, in the product, today:

- **See who's viewed your records** — Privacy Settings → "Your Data Activity"
  lists every access to your documents and case records by anyone other than
  you, including our staff, with name, organization, and timestamp.
- **Revoke sharing** — each document page lists who it's shared with and lets
  you revoke access immediately.
- **Withdraw AI consent** — Privacy Settings.
- **Export your data** — full JSON export from Privacy Settings.
- **Delete your account and data** — Privacy Settings; deletion is permanent.

[Counsel: add jurisdiction-specific rights sections as applicable —
CCPA/CPRA, state health-privacy statutes (e.g., WA My Health My Data),
GDPR if any EU users are accepted.]

## Retention

- Uploaded documents and analyses are retained while your account is active.
- [Pilot accounts: data is automatically deleted after the pilot retention
  window — confirm current window from core/tasks.py retention settings.]
- Audit logs are retained [N months — set a number; recommend ≥ 12 for the
  transparency feature to be meaningful].
- Backups expire on a rolling [N-day] schedule.

## Subprocessors

| Provider | Purpose | Data involved |
|----------|---------|---------------|
| DigitalOcean | Hosting, managed database, Redis | All service data (encrypted at rest) |
| OpenAI | AI document analysis (consent-gated) | Document text you submit for analysis |
| Stripe | Payments | Billing details (we never store card numbers) |
| Sentry | Error monitoring | Technical error data; PII capture disabled |
| [Email provider] | Transactional email | Email address, notification content |

## Not affiliated with the VA

Benefits Navigator is not affiliated with, endorsed by, or connected to the
U.S. Department of Veterans Affairs. Nothing in the Service is legal advice.

## Changes and contact

[Standard change-notification and contact sections — counsel to supply.]
