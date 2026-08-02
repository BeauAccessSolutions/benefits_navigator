"""Production deploys must be gated on CI.

Commit ``a6d8f98`` shipped to production with ``Tests: failure``. Nobody
bypassed a gate; there was no gate. Every component in the App Platform spec
carried ``deploy_on_push: true``, so DigitalOcean built whatever landed on
``main`` the moment it landed, and no part of the pipeline ever asked whether
the build was green.

Two halves, both checked here:

* the spec must not auto-deploy on push, and
* a deploy workflow must exist that waits for checks and refuses on failure.

The workflow deliberately inspects the **merge commit** rather than trusting
branch protection. Protection verifies the PR branch; squash-merge produces a
new commit that nothing has run, and ``strict: false`` means the branch need
not have been current. The commit that ships is the one that has to be green.

These read the repo, not the live platform. The authoritative spec lives in the
DigitalOcean console, so this guards the template the console is provisioned
from — same limitation as ``test_beat_deployment.py``, same reason.
"""

import re
from pathlib import Path

import pytest
import yaml

from django.conf import settings

ROOT = Path(settings.BASE_DIR)
SPEC = ROOT / "app-spec.yaml.template"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"


@pytest.fixture(scope="module")
def spec_text():
    assert SPEC.exists(), f"deployment spec template missing at {SPEC}"
    return SPEC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def deploy_workflow():
    assert DEPLOY_WORKFLOW.exists(), (
        "No .github/workflows/deploy.yml. With deploy_on_push off and no deploy "
        "workflow, nothing ships at all."
    )
    return yaml.safe_load(DEPLOY_WORKFLOW.read_text(encoding="utf-8"))


class TestSpecDoesNotAutoDeploy:
    def test_no_component_deploys_on_push(self, spec_text):
        offenders = re.findall(r"deploy_on_push:\s*true", spec_text)

        assert not offenders, (
            f"{len(offenders)} component(s) still set deploy_on_push: true. That "
            f"bypasses CI entirely — it is how a build with failing tests reached "
            f"production. Deploys go through the Deploy workflow."
        )

    def test_the_flag_is_present_rather_than_merely_absent(self, spec_text):
        """
        Absent means DO's default applies, which is not obviously false. The
        intent has to be written down.
        """
        assert "deploy_on_push: false" in spec_text


class TestDeployWorkflowGates:
    def test_it_runs_on_pushes_to_main(self, deploy_workflow):
        # PyYAML parses a bare `on:` key as the boolean True.
        triggers = deploy_workflow.get("on") or deploy_workflow.get(True)

        assert "push" in triggers
        assert "main" in triggers["push"]["branches"]

    def test_it_can_also_be_run_by_hand(self, deploy_workflow):
        """A manual deploy must exist, and must still go through the gate."""
        triggers = deploy_workflow.get("on") or deploy_workflow.get(True)

        assert "workflow_dispatch" in triggers

    def test_it_waits_for_checks_before_deploying(self, deploy_workflow):
        steps = deploy_workflow["jobs"]["deploy"]["steps"]
        names = [s.get("name", "") for s in steps]

        wait_index = next(
            (i for i, n in enumerate(names) if "Wait for all checks" in n), None
        )
        deploy_index = next(
            (i for i, n in enumerate(names) if "Trigger the DigitalOcean" in n), None
        )

        assert wait_index is not None, "no step waits for checks"
        assert deploy_index is not None, "no step triggers a deployment"
        assert wait_index < deploy_index, "the deploy must come after the wait"

    def test_the_wait_step_fails_on_a_bad_conclusion(self, deploy_workflow):
        """
        Waiting is not gating. The step has to exit non-zero when a check
        failed, or it just delays the same bad deploy.
        """
        steps = deploy_workflow["jobs"]["deploy"]["steps"]
        wait = next(s for s in steps if "Wait for all checks" in s.get("name", ""))
        script = wait["run"]

        assert "Refusing to deploy" in script
        assert "exit 1" in script

    def test_a_timeout_refuses_rather_than_proceeds(self, deploy_workflow):
        """Unfinished checks must not read as passing checks."""
        steps = deploy_workflow["jobs"]["deploy"]["steps"]
        wait = next(s for s in steps if "Wait for all checks" in s.get("name", ""))

        assert "did not finish within the deadline" in wait["run"]

    def test_deploys_do_not_run_concurrently(self, deploy_workflow):
        assert deploy_workflow.get("concurrency", {}).get("group")

    def test_the_rollout_waits_for_the_result(self, deploy_workflow):
        """
        `doctl apps create-deployment --wait`: without it a failed rollout looks
        like a successful deploy while DO silently keeps the old container.
        """
        steps = deploy_workflow["jobs"]["deploy"]["steps"]
        trigger = next(
            s for s in steps if "Trigger the DigitalOcean" in s.get("name", "")
        )

        assert "--wait" in trigger["run"]


class TestOtherWorkflowsStillGuardMain:
    def test_the_required_checks_run_on_push_to_main(self):
        """
        The gate waits for whatever checks exist on the commit. If the CI
        workflows stopped running on push, it would wait for nothing and pass
        vacuously.
        """
        expected = {"tests.yml", "security-checks.yml", "benchmarks.yml"}

        for filename in expected:
            path = ROOT / ".github" / "workflows" / filename
            assert path.exists(), f"{filename} is missing"

            workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
            triggers = workflow.get("on") or workflow.get(True)

            assert "push" in triggers, f"{filename} no longer runs on push"
            assert "main" in triggers["push"]["branches"], (
                f"{filename} no longer runs on pushes to main, so the deploy "
                f"gate would not wait for it"
            )
