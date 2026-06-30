<!--
PR title must follow Conventional Commits: feat: / fix: / docs: / refactor: / test: / chore:
Keep PRs focused — one feature or fix per PR.
-->

## What & why

<!-- What changed, and why it was needed. Link any issue: Closes #123 -->

## How to test

<!-- Steps to verify. Screenshots for UI changes. -->

## Author checklist

- [ ] Tests added/updated and `pytest` passes locally
- [ ] `ruff check .` and `black --check .` are clean
- [ ] Docs/`CLAUDE.md` updated if behavior or architecture changed
- [ ] No secrets, `.env`, or credentialed deploy YAML committed

## Security & data review

<!-- If you check ANY box below, request a security review (see CONTRIBUTING.md
     "Review & security gates") — a code review alone is not sufficient. -->

This PR touches one or more sensitive surfaces:

- [ ] PII/PHI fields (`va_file_number`, `date_of_birth`, `ai_summary`) or `core/encryption.py`
- [ ] Authentication, sessions, subscriptions, or Stripe/billing
- [ ] The AI gateway, prompts, or model-output handling (`agents/ai_gateway.py`, `agents/schemas.py`)
- [ ] Celery tasks that process user data
- [ ] Database migrations
- [ ] Config/secrets surface (`settings.py`, `.do/`, CI workflows, `requirements.txt`)
- [ ] **None of the above** (no security review required)

If any sensitive box is checked, confirm:

- [ ] User input passes through `sanitize_input()` and model output is validated against a Pydantic schema
- [ ] No PII is logged or stored in plaintext
- [ ] New Celery tasks handling user data use `acks_late=True`
- [ ] A `/security-review` was run (or requested from a code owner)
