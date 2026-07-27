"""The periodic-task schedule must actually be wired to a running scheduler.

The deployment defined ten periodic tasks and no Beat component. The worker's
run command has no ``-B``, no Procfile exists, and nothing else started a
scheduler — so every entry in ``CELERY_BEAT_SCHEDULE`` was dead code in
production. Health metrics, pilot data retention, reminder emails and, most
seriously, ``process_scheduled_account_deletions`` never ran. The app told
users their data would be permanently deleted within 30 days, recorded the
request, and then did nothing, indefinitely.

Nothing failed. That is the whole problem: the settings module *looked*
correct, its comment claimed Beat ran on the worker, and no test compared that
claim against the deployment spec. These tests close that gap from both ends —
the spec must define a scheduler, and every task the schedule names must exist.

Note the limit of a repo-side test: the authoritative spec lives in the
DigitalOcean console, not in git (``.do/app.yaml`` is gitignored). This checks
the template that the console is provisioned from. The runtime counterpart is
``core.health.check_scheduler``, which reports on the real deployment.
"""

import re
from pathlib import Path

import pytest

from django.conf import settings

SPEC = Path(settings.BASE_DIR) / "app-spec.yaml.template"


@pytest.fixture(scope="module")
def spec_text():
    assert SPEC.exists(), f"deployment spec template missing at {SPEC}"
    return SPEC.read_text(encoding="utf-8")


class TestSchedulerIsDeployed:
    def test_the_spec_defines_a_beat_component(self, spec_text):
        assert re.search(r"^\s*-\s*name:\s*beat\s*$", spec_text, re.MULTILINE), (
            "No 'beat' component in the deployment spec. Without it nothing in "
            "CELERY_BEAT_SCHEDULE runs — including account deletion, which the "
            "product promises happens within 30 days."
        )

    def test_something_actually_runs_celery_beat(self, spec_text):
        assert re.search(r"run_command:.*celery.*\bbeat\b", spec_text), (
            "No component runs `celery beat`. Defining the component is not "
            "enough; it has to start the scheduler."
        )

    def test_beat_is_pinned_to_a_single_instance(self, spec_text):
        """Two schedulers means two of every scheduled side effect."""
        beat_block = spec_text.split("- name: beat", 1)[-1].split("\njobs:", 1)[0]

        assert re.search(r"instance_count:\s*1\b", beat_block), (
            "The beat component must be pinned to instance_count: 1. Two "
            "schedulers double-fire everything — duplicate reminder emails, "
            "two retention passes, two account-purge runs."
        )

    def test_the_worker_does_not_also_run_beat(self, spec_text):
        """
        ``-B`` on the worker is the tempting one-character fix and the wrong
        one: it ties the scheduler's lifetime to the worker and double-fires
        every task as soon as the worker scales past one instance.
        """
        worker_block = spec_text.split("- name: worker", 1)[-1].split(
            "- name: beat", 1
        )[0]
        run_command = re.search(r"run_command:.*", worker_block)

        assert run_command, "worker component has no run_command"
        assert " -B" not in run_command.group(0), (
            "The worker must not run Beat with -B; use the dedicated beat "
            "component so scheduling survives worker scaling."
        )


@pytest.mark.django_db
class TestScheduleIsCoherent:
    def test_every_scheduled_task_can_be_imported(self):
        """
        A schedule entry naming a task that no longer exists fails at dispatch
        time, inside Beat, where nobody is reading the logs. Catch it here.
        """
        from celery import current_app

        current_app.loader.import_default_modules()
        registered = set(current_app.tasks)

        missing = [
            entry["task"]
            for entry in settings.CELERY_BEAT_SCHEDULE.values()
            if entry["task"] not in registered
        ]

        assert not missing, f"scheduled tasks not registered with Celery: {missing}"

    def test_the_deletion_purge_is_scheduled(self):
        """
        The specific promise: accounts/views.py tells users their data is
        permanently deleted after 30 days. That is only true if this task runs.
        """
        tasks = {e["task"] for e in settings.CELERY_BEAT_SCHEDULE.values()}

        assert "core.tasks.process_scheduled_account_deletions" in tasks

    def test_the_database_scheduler_is_configured(self):
        """
        File-based scheduling loses its state on every deploy (ephemeral disks)
        and records nothing that health checks can read. The database scheduler
        is what makes a dead Beat detectable.
        """
        assert "DatabaseScheduler" in settings.CELERY_BEAT_SCHEDULER
