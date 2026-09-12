"""The migration entrypoint imports the tree in a different order from the
API process, and a cycle that the API never sees can leave `alembic upgrade`
dead on the deploy host. Each of these modules must import cleanly FIRST, in
a fresh interpreter — the way a migration script, a one-off ops script or a
shell `python -c` reaches it."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("module", [
    "app.services.audit_trail",
    "app.services.provisioning",
    "app.services.flow_subscriptions",
    "app.models",
    "app.main",
])
def test_the_module_imports_first_in_a_fresh_interpreter(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"], cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"import {module} first:\n{result.stderr[-1500:]}"


def test_alembic_can_read_its_own_heads() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"], cwd=ROOT, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr[-1500:]
    assert "(head)" in result.stdout
