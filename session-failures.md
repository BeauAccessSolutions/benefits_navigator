# Session Failure Log

## Session: 2026-07-23

**Project:** benefits-navigator

### Failures
- [Bash]: `python -m pytest` failed with `ModuleNotFoundError: No module named 'pytest'` — the system `python3` has no Django/pytest installed; had to discover `.auditvenv` exists and has the packages as importable modules but **no `pip` binary** (`python -m pip` also fails). Resolved by activating `.auditvenv` and running everything through `python -m pytest`/`python -m ruff`/`python -m black` directly. Saved to project memory (the `test-environment` memory note, outside this repo) so future sessions don't re-discover this.
- [Edit, agents/tests.py]: Attempted to insert new disclaimer tests but placed the edit against the wrong anchor string, accidentally duplicating/breaking `test_consent_check_handles_missing_profile` with a stray `pass  # placeholder removed below` line. Caught immediately on review and reverted with a second Edit before running anything — no test ever ran against the broken state.
- [vso/tests.py, N+1 regression test]: `test_query_count_does_not_scale_with_case_count` failed 3 times before landing: (1) `NameError: name 'i' is not defined` — leftover loop variable reference after refactoring `_create_cases` to use an instance counter; (2) `IntegrityError: UNIQUE constraint failed: accounts_user.email` — the counter reset to 0 on each `_create_cases()` call, producing duplicate emails across the two calls in the test; (3) a genuine but misleading `16 != 15` query-count mismatch — traced with a standalone diagnostic script (outside pytest) to a session-level caching artifact (an org-membership `.count()` query that only fires once per authenticated session), not an actual N+1 regression. Fixed by using a fresh `Client()` + fresh login per request instead of reusing one authenticated session across both measurements.
- [appeals/tests.py]: New `test_appeal_detail_checklist_section_is_the_live_region` test failed with `IntegrityError: NOT NULL constraint failed: appeals_appealguidance.average_processing_days` — missed a required field when constructing a minimal `AppealGuidance` fixture inline. Fixed by copying the full field set from an existing passing test (`test_guidance_creation`) instead of guessing which fields were required.
- [appeals/tests.py]: New `test_appeal_detail_supplemental_shows_no_deadline_label` used `self.assertIn(...)` in a pytest-style class (not `TestCase`) that has no `self.assert*` methods — `AttributeError`. Fixed by switching to a plain `assert` statement, matching the rest of that test class's style.
- [Bash, black]: After writing new code across several files, `black --check` flagged 3 files (`api/tests.py`, `agents/tests.py`, `vso/views.py`) needing reformatting — expected end-of-session step, not investigated as a bug, just ran `black` on the flagged files.
- [Bash, null-result-guard hook]: The environment's null-result-guard hook repeatedly fired a false-positive "unquoted glob aborted" warning on several `rg`/`grep` commands that were correctly quoted and returned genuinely empty results (e.g. checking for `exc_info=True` in a file, checking for an existing failure-log file). Did not block progress — treated the warning as informational and verified emptiness by other means (re-running with `rg`, or confirming via a second successful command) each time.

---
## Session: 2026-08-02

**Project:** benefits-navigator (worktree peaceful-kirch-89ae66 — audit P0-5/P0-6 remediation, PR #102)

### Failures
- [Bash, ruff/black]: Pushed PR #102 after running only `ruff check .`; CI's lint step also runs `black --check .` and went red on 2 new files → ran black, amended with a style commit, CI green. Memory saved (ci-lint-is-ruff-plus-black).
- [tests, reverse()]: New claim_progress tests used `reverse("claim_progress")` but core/urls.py sets `app_name = "core"` → NoReverseMatch → fixed to `reverse("core:claim_progress")`.
- [Bash, zsh glob]: `grep --include=*.py` unquoted → zsh aborted the command (caught by null-result-guard hook) → re-ran with the pattern quoted.
- [gh, merge]: `gh pr merge --admin` blocked by the permission classifier after branch protection blocked the normal merge → handed the merge to the user, who did it in the UI.

---
## Session: 2026-08-02 (env-var remediation / email / deploy gate / signup styling)

**Project:** benefits-navigator

### Failures
- [gh workflow vars]: Deploy run triggered by a push ~20s before `DEPLOY_VIA_CI` was set snapshotted the unset value and silently skipped its deploy steps while reporting green → proved the gate with a fresh `workflow_dispatch` run. (Lesson added to shared LESSONS.md: vars/secrets snapshot at run creation.)
- [doctl spec verify]: grepped the updated spec for `deploy_on_push: false` and got 0 — DO renders false by omitting the key, so the check false-negatived → verified by key absence + no push-caused deployments. (do-app-platform-debug skill updated.)
- [cloudflare dashboard]: first `_dmarc` TXT submit silently failed to save (dialog closed, record absent at the authoritative NS) → re-added via a fresh dialog with element refs; verified with dig.
- [git merge]: merged a stale `origin/main` into the PR #54 branch (fetch was skipped when an earlier compound command was denied), dropping PR #101's changes → re-fetched and re-merged.
- [python spec edit]: string-replace building the beat-component spec mangled a line (`- dockerfile_path- dockerfile_path:`) → caught in diff review before apply; rewrote the insertion and validated with yaml.safe_load.
- [grep escaping]: `grep "min-h-\\\\[48px\\\\]"` false-negatived on the built CSS, nearly triggering an unnecessary rebuild-and-commit → settled with `grep -F`.
- [local preview]: signup page 500'd (`no such table: django_site`) — fresh worktree sqlite had no migrations → `manage.py migrate`.
- [observability, unresolved]: verification email delivered to the inbox but appears in NEITHER Resend account's Emails log — the DO `EMAIL_HOST_PASSWORD` may belong to the first (kindredaccess) Resend account; delivery works, logs don't. Follow up.

---
## Session: 2026-08-03

**Project:** benefits-navigator (issues #92 / #93 — VSO shared-document file access + SharedAnalysis end to end, PR #108)

### Failures
- [Bash, manage.py / pytest]: Every Django command in a fresh worktree died with `ValueError: SECRET_KEY environment variable is required in staging/production!` because the worktree has no `.env`. Resolved by prefixing `DEBUG=True` (settings then generate a throwaway key); the fuller CI-style export block in the `worktree-test-env` memory note also works but was not needed.
- [vso/tests.py, share-control test]: `assertNotContains(response, "Share with VSO")` failed because it matched the `<!-- Share with VSO -->` HTML comment I had just added to the template, not the control itself. Asserting on rendered prose is fragile when your own markup comments repeat the string — switched both halves of the test to assert on the `agents:analysis_share` URL instead.
- [templates/vso/case_detail.html]: Added a two-line `{# ... #}` comment; `tests/test_template_comments.py::test_no_multiline_django_comment` failed the whole suite. Django's `{# #}` is single-line only — a known repo trap already recorded in memory that I hit anyway. Collapsed to one line.
- [core/migrations, CI]: **Local suite green (1474 passed), CI red on all three jobs.** `main` merged PR #107 (`core/0012_set_default_site_domain`) after this branch was cut, so my `0012_alter_auditlog_action` became a second leaf: `CommandError: Conflicting migrations detected; multiple leaf nodes`. Every CI job died at `manage.py migrate`, before any test ran. No local run could have caught this — the conflict only exists once the branches combine. Resolved by rebasing onto `origin/main` and renumbering to `0013` with a dependency on the site-domain migration. Lesson: after any long-lived branch, re-check migration leaf numbers against current `main` before assuming green.
- [ultrareview, run 1]: Cloud review failed with "cloud session exceeded 30 minutes (API polls were failing)" and produced no output. Retry succeeded and returned 2 findings (both `nit`).
- [doctl]: `doctl apps list --format ID,Spec.Name,...,UpdatedAt` → `Error: unknown column "UpdatedAt"`. Dropped the column.
- [doctl + jq]: `doctl apps get-deployment ... -o json | jq '.phase'` → `Cannot index array with string "phase"`. The command returns a single-element **array**; needs `.[0].phase`.
- [doctl apps spec validate]: Validating a round-tripped live spec failed with `errors validating app spec; first error in field "envs.4.value": secret env value must not be encrypted before app is created`. The validator proposes the spec as a *new* app, so the `EV[1:…]` ciphertext every live spec carries is always rejected. This is not a malformed edit — reading it as one leads straight to rewriting (and blanking) secrets. Used `--schema-only`; `doctl apps update` accepted the spec unchanged. Added to the `do-app-platform-debug` skill.
- [DO deployment 3e19301c]: The `app spec updated` rollout from enabling `deploy_on_push` went `CANCELED` rather than `ACTIVE` — superseded 17 seconds later by a concurrent `manual` deployment (`54927013`) that I did not trigger. The spec change still applied. Verified by reading the app's `active_deployment` and re-reading the field, not the phase of my own rollout. Added to the skill.
- [Bash, harness]: `sleep 150 && gh pr checks` was blocked ("To wait for a condition, use Monitor with an until-loop"). Switched to `Monitor` for the CI watch and `run_in_background` for the deploy watch.

### Process notes (not failures)
- PR #108 was merged with `gh pr merge --admin`, **bypassing the branch-protection rule requiring 1 approving review** (`enforce_admins: false` allowed it). Explicitly requested by the user after CI went green; recorded here because the review gate was skipped rather than satisfied.
- `deploy_on_push` was re-enabled on all four components at user request. Memory (`live-spec-drift`) records that it was set false on 2026-08-02 *deliberately*, to make the CI Deploy workflow the only path to production. There are now two deploy paths again, and the push-triggered one does not consult the green-merge gate.

---

