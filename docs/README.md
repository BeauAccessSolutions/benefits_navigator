# Documentation

Complete documentation for the VA Benefits Navigator project.

## Quick Reference

- **[PROJECT_STATUS.md](./PROJECT_STATUS.md)** - Current project state, what's built, what's pending
- **[DEVELOPMENT_SETUP.md](./DEVELOPMENT_SETUP.md)** - How to set up and run the project locally
- **[PHASE_3_EXAM_PREP.md](./PHASE_3_EXAM_PREP.md)** - Detailed Phase 3 implementation documentation
- **[CONTENT_PROMPTS.md](./CONTENT_PROMPTS.md)** - Ready-to-use prompts for generating guides and glossary content
- **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)** - Common issues and solutions

## Operations & Security

- **[FAILURE_TRACKING.md](./FAILURE_TRACKING.md)** - Querying, triaging, and replaying `ProcessingFailure` records
- **[PHI_DATA_FLOW.md](./PHI_DATA_FLOW.md)** - Where PHI/PII travels, what is persisted vs ephemeral, encryption boundaries
- **[CAPACITY_SCALING.md](./CAPACITY_SCALING.md)** - When and how to scale workers, web, and database on DigitalOcean
- **[INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md)** - Severity levels, escalation paths, runbooks, post-mortem template
- **[security-invariants.md](./security-invariants.md)** - Automated enforcement of PHI/PII protections

## Architecture Decision Records

- **[adr/001-celery-retry-strategy.md](./adr/001-celery-retry-strategy.md)** - 3-retry/exponential-backoff decision, no-DLQ trade-offs
- **[adr/002-ai-consent-model.md](./adr/002-ai-consent-model.md)** - Dual-check AI consent pattern (view + task layer)

## When to Use Each Document

### Starting a New Session?
→ Start with **[PROJECT_STATUS.md](./PROJECT_STATUS.md)** to understand where we are

### Setting Up Development Environment?
→ Follow **[DEVELOPMENT_SETUP.md](./DEVELOPMENT_SETUP.md)** step by step

### Working on Phase 3?
→ Reference **[PHASE_3_EXAM_PREP.md](./PHASE_3_EXAM_PREP.md)** for architecture and details

### Creating Content (Guides & Glossary)?
→ Use **[CONTENT_PROMPTS.md](./CONTENT_PROMPTS.md)** with your research session

### Encountering an Error?
→ Check **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)** first

### Document processing task failed?
→ See **[FAILURE_TRACKING.md](./FAILURE_TRACKING.md)** to query, triage, and replay

### Production incident?
→ See **[INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md)** for runbooks and escalation

### Scaling workers or hitting memory limits?
→ See **[CAPACITY_SCALING.md](./CAPACITY_SCALING.md)**

### PHI/compliance question?
→ See **[PHI_DATA_FLOW.md](./PHI_DATA_FLOW.md)** and **[security-invariants.md](./security-invariants.md)**

## Document Details

### PROJECT_STATUS.md
**Purpose:** High-level overview of project state

**Contains:**
- What's built and working (Phase 1, 2, 3)
- What's pending (content creation, future phases)
- Technology stack
- Recent major changes
- Known issues
- Access points (URLs)
- Next session recommendations

**When to Update:**
- After completing a major phase
- After fixing critical bugs
- When project scope changes

---

### DEVELOPMENT_SETUP.md
**Purpose:** Complete guide to running the project

**Contains:**
- Prerequisites
- Quick start guide
- Docker commands reference
- Environment variables
- Database management
- Testing instructions
- Troubleshooting basics
- Common tasks checklist

**When to Update:**
- When setup process changes
- When new dependencies are added
- When Docker configuration changes

---

### PHASE_3_EXAM_PREP.md
**Purpose:** Detailed Phase 3 technical documentation

**Contains:**
- Architecture overview
- Database models (3 models, detailed)
- Views (10 views, all documented)
- Forms and templates
- URL routing
- Admin interface
- Accessibility features
- Content strategy
- Implementation status
- Next steps with examples

**When to Update:**
- When models change
- When adding new views or templates
- When content strategy evolves
- After completing pending tasks

---

### CONTENT_PROMPTS.md
**Purpose:** Generate content for exam guides and glossary

**Contains:**
- 5 ready-to-use prompts for research session
- Glossary terms prompt (30 VA terms)
- General C&P exam guide prompt
- PTSD exam guide prompt (Priority 1)
- Musculoskeletal exam guide prompt (Priority 2)
- Tinnitus/Hearing exam guide prompt (Priority 3)
- Database field mapping guide
- Quality checklist
- Time estimates

**When to Update:**
- When adding new condition guides
- When schema changes require different content structure
- After discovering better prompt formats

---

### TROUBLESHOOTING.md
**Purpose:** Solutions to common problems

**Contains:**
- Docker issues (7 issues documented)
- Python dependency conflicts (3 issues)
- Database & migration errors (5 issues)
- Authentication problems (2 issues)
- URL & routing issues (2 issues)
- Template issues (2 issues)
- Permission errors (2 issues)
- Celery issues (2 issues)
- Performance tips

**When to Update:**
- After encountering and solving new bugs
- When discovering better solutions
- When adding new integrations

## Keeping Documentation Updated

**General Rule:** Update docs immediately after making significant changes

**Significant Changes Include:**
- Completing a phase or major feature
- Fixing critical bugs
- Changing project structure
- Adding new dependencies
- Modifying setup process
- Discovering new issues

**Minor Changes (Don't Need Doc Updates):**
- Small bug fixes
- Content additions (exam guides, glossary terms)
- CSS/styling tweaks
- Minor refactoring

## Documentation Standards

### Writing Style
- **Clear and concise** - No fluff
- **Action-oriented** - Tell readers what to do
- **Code examples** - Show, don't just tell
- **Current** - Always reflect actual state
- **Accessible** - Assume fresh reader

### Code Blocks
Always specify language:
```python
# Python code
```

```bash
# Shell commands
```

```yaml
# YAML files
```

### File References
Always include line numbers when referencing specific code:
- `accounts/models.py:13-38` - UserManager class
- `docker-compose.yml:15` - Database healthcheck

### Status Indicators
Use clear status markers:
- ✅ COMPLETE - Fully implemented and tested
- ⏳ PENDING - Not yet started
- 🚧 IN PROGRESS - Currently being worked on
- ⚠️ BLOCKED - Waiting on something

## Contributing to Documentation

When adding new features:
1. Update relevant docs BEFORE marking feature complete
2. Add troubleshooting entries for issues you encountered
3. Include code examples and file references
4. Test documentation by having someone else follow it

## Questions?

If documentation is unclear or missing something:
1. Note what's confusing
2. Update the docs with what you learned
3. Commit documentation improvements

**Remember:** Good documentation = Smooth session transitions
