"""The deploy checks must catch a DEBUG=False process with dev defaults.

The staging deployment ran with no ANTHROPIC_API_KEY, no SENTRY_DSN, the
console email backend, and SITE_URL=http://localhost:8000 — all AI features
down, errors invisible, signups unable to verify, invitation emails linking
to localhost — and nothing anywhere failed. ``core.checks`` turns that state
into a halted rollout via the PRE_DEPLOY job's ``check --deploy`` run.

These tests exercise the check function directly (it only ever runs under
``check --deploy``, never during the test suite) and pin the deployment
wiring: the check must be registered as a deploy check, and the spec
template's migrate job must actually invoke it.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.core.checks.registry import registry
from django.test import override_settings

from core.checks import check_deployed_configuration

pytestmark = pytest.mark.unit

# A fully deployment-shaped configuration; individual tests break one piece.
DEPLOYED = dict(
    DEBUG=False,
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    ANTHROPIC_API_KEY="sk-ant-real-enough",
    SENTRY_DSN="https://key@sentry.example/1",
    SITE_URL="https://vabenefitsnavigator.org",
)


def error_ids(**overrides):
    with override_settings(**{**DEPLOYED, **overrides}):
        return {e.id for e in check_deployed_configuration(None)}


class TestDeployedConfigurationCheck:
    def test_fully_configured_deployment_passes(self):
        assert error_ids() == set()

    def test_debug_mode_is_exempt(self):
        """Dev defaults are fine in dev — the check must not fire there."""
        assert (
            error_ids(
                DEBUG=True,
                EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
                ANTHROPIC_API_KEY="",
                SENTRY_DSN="",
                SITE_URL="http://localhost:8000",
            )
            == set()
        )

    @pytest.mark.parametrize(
        "backend",
        [
            "django.core.mail.backends.console.EmailBackend",
            "django.core.mail.backends.filebased.EmailBackend",
            "django.core.mail.backends.locmem.EmailBackend",
            "django.core.mail.backends.dummy.EmailBackend",
        ],
    )
    def test_dev_email_backend_fails(self, backend):
        assert "core.E001" in error_ids(EMAIL_BACKEND=backend)

    def test_empty_anthropic_api_key_fails(self):
        assert "core.E002" in error_ids(ANTHROPIC_API_KEY="")

    def test_empty_sentry_dsn_fails(self):
        assert "core.E003" in error_ids(SENTRY_DSN="")

    @pytest.mark.parametrize("url", ["http://localhost:8000", "http://127.0.0.1:8000"])
    def test_localhost_site_url_fails(self, url):
        assert "core.E004" in error_ids(SITE_URL=url)

    def test_the_original_outage_reports_every_defect_at_once(self):
        """One deploy failure should name all four problems, not the first."""
        assert error_ids(
            EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
            ANTHROPIC_API_KEY="",
            SENTRY_DSN="",
            SITE_URL="http://localhost:8000",
        ) == {"core.E001", "core.E002", "core.E003", "core.E004"}


class TestDeploymentWiring:
    """A check that never runs is dead code — pin the wiring on both ends."""

    def test_check_is_registered_as_a_deploy_check(self):
        assert check_deployed_configuration in registry.deployment_checks, (
            "check_deployed_configuration is not registered with deploy=True; "
            "`manage.py check --deploy` will never run it."
        )

    def test_check_does_not_run_outside_deploy_mode(self):
        assert check_deployed_configuration not in registry.registered_checks, (
            "The deploy check is registered as an ordinary check, so it would "
            "fire during every management command and the test suite."
        )


@pytest.fixture(scope="module")
def spec_text():
    spec = Path(settings.BASE_DIR) / "app-spec.yaml.template"
    assert spec.exists(), f"deployment spec template missing at {spec}"
    return spec.read_text(encoding="utf-8")


class TestSpecTemplateWiring:
    def test_predeploy_job_runs_the_deploy_check(self, spec_text):
        migrate_block = spec_text.split("- name: migrate", 1)[-1]
        run_command = re.search(r"run_command:.*", migrate_block)
        assert run_command, "migrate job has no run_command"
        assert "check --deploy --fail-level ERROR" in run_command.group(0), (
            "The PRE_DEPLOY migrate job does not run `manage.py check "
            "--deploy`, so core/checks.py never gates a rollout."
        )

    @pytest.mark.parametrize(
        "key", ["SITE_URL", "EMAIL_BACKEND", "EMAIL_HOST_PASSWORD"]
    )
    def test_spec_declares_the_delivery_critical_envs(self, spec_text, key):
        assert re.search(rf"^\s*-\s*key:\s*{key}\s*$", spec_text, re.MULTILINE), (
            f"{key} is missing from app-spec.yaml.template — the console gets "
            "provisioned from this file, and this exact omission is how the "
            "deployed app ended up emailing localhost links."
        )
