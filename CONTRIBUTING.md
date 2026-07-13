# Contributing to VA Benefits Navigator

Thank you for your interest in contributing to VA Benefits Navigator! This project helps veterans navigate VA disability claims, and every contribution makes a difference.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Pull Request Process](#pull-request-process)
- [Review & Security Gates](#review--security-gates)
- [Style Guidelines](#style-guidelines)
- [Testing](#testing)
- [Documentation](#documentation)

## Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/Beaudoin0zach/benefits_navigator.git
   cd benefits_navigator
   ```

2. **Copy environment template**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start with Docker Compose**
   ```bash
   docker compose up -d
   ```

4. **Run migrations**
   ```bash
   docker compose exec web python manage.py migrate
   ```

5. **Load fixtures**
   ```bash
   docker compose exec web python manage.py loaddata examprep/fixtures/*.json
   ```

6. **Create a superuser**
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

## How to Contribute

### Reporting Bugs

- Check existing issues first to avoid duplicates
- Use the bug report template if available
- Include steps to reproduce, expected vs actual behavior
- Include browser/OS information for frontend issues

### Suggesting Features

- Open an issue with the "enhancement" label
- Describe the use case and why it helps veterans
- Be open to discussion about implementation approaches

### Contributing Code

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Write/update tests
5. Ensure all tests pass
6. Commit with clear messages
7. Push to your fork
8. Open a Pull Request

### Content Contributions

We welcome contributions to:

- **Exam Guides**: C&P exam preparation content
- **Glossary Terms**: VA terminology explanations
- **Secondary Conditions**: Documented condition relationships
- **Appeals Guidance**: Step-by-step appeal instructions

Content should be:
- Accurate and based on official VA sources
- Written in plain, accessible language
- Helpful without providing legal/medical advice

## Pull Request Process

1. **Update documentation** if you change functionality
2. **Add tests** for new features
3. **Follow style guidelines** (see below)
4. **Keep PRs focused** - one feature/fix per PR
5. **Write clear commit messages**

### PR Title Format

```
type: brief description

Examples:
feat: Add TBI exam guide
fix: Correct bilateral factor calculation
docs: Update installation instructions
test: Add rating calculator tests
```

### PR Description

Include:
- What changes were made
- Why the changes were needed
- How to test the changes
- Screenshots for UI changes

The repository ships a PR template (`.github/PULL_REQUEST_TEMPLATE.md`) that
includes the security checklist described below — fill it in rather than
deleting it.

## Review & Security Gates

This app handles veterans' PHI/PII, so review depth scales with what a change
touches. Two layers enforce this:

### Code owners (automated reviewer routing)

`.github/CODEOWNERS` auto-requests a maintainer's review whenever a PR edits a
security-sensitive surface — encryption, the AI gateway, auth/billing, Celery
tasks handling user data, migrations, settings, or CI. This is the equivalent
of a "review trigger": you don't have to remember to flag these files, the
change itself does. (For owner review to *block* merge, "Require review from
Code Owners" must be enabled in branch protection on `main`.)

### When a security review is required

A normal code review is enough for most PRs. A **`/security-review`** (not just
a code review) is additionally required — and is a hard merge gate — when a PR
touches any of:

- PII/PHI fields or `core/encryption.py`
- Authentication, sessions, subscriptions, or Stripe/billing
- The AI gateway, prompts, or model-output handling
- Celery tasks that process user data
- Database migrations, or the config/secrets surface (`settings.py`, `.do/`, CI)

### Severity & merge blocking

Review findings are triaged by severity, and severity gates the merge:

| Severity | Meaning | Gate |
|----------|---------|------|
| **P0** | Security/data-loss/regulatory risk, or breaks a `CLAUDE.md` non-negotiable | **Blocks merge** |
| **P1** | Significant correctness or maintainability issue | Fix before merge, or file a tracked follow-up with owner sign-off |
| **P2** | Minor / stylistic | Non-blocking |

For broad or high-risk changes, run the multi-agent cloud review with
`/code-review ultra` before requesting human review.

### Re-trigger policy

Re-run the relevant review when any of these happen, even if the code didn't
change much:
- A dependency bump touching crypto, auth, parsing (e.g. `lxml`), or the AI SDK
- A change to a shared security primitive (`encryption.py`, `ai_gateway.py`,
  `middleware.py`) — re-validate every consumer, not just the edited file
- VA regulatory data updates (rates, deadlines) — verify against CFR
- Any change to PII handling, logging, or what gets persisted

## Style Guidelines

### Python

- Follow PEP 8
- Use meaningful variable names
- Add docstrings to functions and classes
- Keep functions focused and small

### Django

- Follow Django conventions for models, views, templates
- Use class-based views where appropriate
- Keep business logic out of views (use services/utilities)

### Templates

- Maintain WCAG AA accessibility
- Use semantic HTML
- Follow existing Tailwind CSS patterns

### JavaScript

- Prefer vanilla JS or HTMX over heavy frameworks
- Keep it simple and accessible

## Testing

### Running Tests

```bash
# All tests
docker compose exec web pytest

# Specific app
docker compose exec web pytest examprep/

# With coverage
docker compose exec web pytest --cov=. --cov-report=html
```

### Writing Tests

- Test file naming: `test_*.py`
- Use pytest fixtures
- Test both success and failure cases
- Mock external services (Anthropic, Stripe)

## Documentation

### Code Documentation

- Add docstrings to public functions/methods
- Comment complex logic
- Update README for new features

### User Documentation

- Write for veterans who may not be tech-savvy
- Use plain language (no jargon)
- Include examples where helpful

## Questions?

- Open an issue for general questions
- Check existing documentation first
- Be patient - maintainers are volunteers

## Recognition

Contributors will be recognized in:
- GitHub contributors list
- Release notes for significant contributions

Thank you for helping veterans navigate their benefits!
