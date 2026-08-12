"""Spec test: everything under tests/e2e/ must carry the `e2e` marker.

The marker is applied by pytest_collection_modifyitems in tests/e2e/conftest.py.
Before that hook existed, `pytest -m "not e2e"` excluded nothing, so a bare
`pytest` run collected the Playwright tests and they failed at page.goto()
whenever no dev server was listening on :8000 — looking like a code regression
when it was an environment gap. CI never caught the drift because it runs with
--ignore=tests/e2e.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _collect(marker_expr):
    env = dict(os.environ)
    env.setdefault("DEBUG", "True")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/e2e",
            "--collect-only",
            "-q",
            "-m",
            marker_expr,
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=120,
    )
    # pytest <9 prints flat `path::test` node ids for `--collect-only -q`;
    # pytest 9 prints a `<Function ...>` tree. Accept either.
    selected = [
        line
        for line in result.stdout.splitlines()
        if "::" in line or "<Function" in line
    ]
    return result, selected


def test_e2e_tests_all_carry_the_marker():
    result, selected = _collect("e2e")
    assert selected, (
        "pytest -m e2e selected nothing under tests/e2e — the auto-marker hook "
        f"in tests/e2e/conftest.py is not applying.\n{result.stdout}\n{result.stderr}"
    )


def test_not_e2e_deselects_everything_under_tests_e2e():
    result, selected = _collect("not e2e")
    assert not selected, (
        "pytest -m 'not e2e' still collected browser tests under tests/e2e/ — "
        "these fail without a dev server on :8000 and must be opt-in.\n"
        + "\n".join(selected)
    )
