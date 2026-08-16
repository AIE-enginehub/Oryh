"""Every module a migration imports must still be importable.

Migrations are frozen once applied — the release guard compares the checksum of
every migration in the live release's tree against the target's and refuses a
release that edits one. So a migration's imports cannot be updated when the code
moves; the code has to keep the path resolvable instead.

Nothing else notices. The container runs `alembic upgrade head` at every start,
but a deployed database is already past these revisions and never executes them
again, so a broken import surfaces only on a FRESH database — a new environment,
or the standalone open-core install — long after the release that broke it. And
the suite builds its schema with `Base.metadata.create_all`, so it never runs a
migration either: 937 tests passed over a migration importing `app.api.routes`
the same week that module was deleted.

This walks the imports rather than the SQL. It will not tell you a migration is
correct; it tells you the interpreter can still reach what it names, which is
the failure that made this file.
"""

from __future__ import annotations

import ast
import importlib
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "alembic" / "versions"


def _imports(source: str) -> set[str]:
    """Module names imported anywhere in the file, including inside functions —
    which is where migrations put the ones that reach into application code."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def _application_imports() -> list[tuple[str, str]]:
    """(migration filename, module) for every `app.*` or `scripts.*` import."""
    pairs = []
    for path in sorted(VERSIONS.glob("*.py")):
        for module in sorted(_imports(path.read_text(encoding="utf-8"))):
            if module.split(".")[0] in {"app", "scripts", "flow_runner"}:
                pairs.append((path.name, module))
    return pairs


def test_migrations_were_found() -> None:
    """Guard the guard: a glob that stops matching must fail, not pass."""
    assert len(list(VERSIONS.glob("*.py"))) > 20
    assert _application_imports(), "no migration imports application code any more"


@pytest.mark.parametrize("migration, module", _application_imports())
def test_the_module_a_migration_imports_still_exists(migration: str, module: str) -> None:
    try:
        importlib.import_module(module)
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"{migration} imports {module}, which no longer exists ({exc}).\n"
            "An applied migration's bytes are frozen — the release guard refuses "
            "a release that edits one — so this is fixed by keeping the path "
            "importable, not by updating the migration. See app/api/routes.py "
            "for the shim that does it for 20260804_0047.",
            pytrace=False,
        )


@pytest.mark.parametrize("migration, module", _application_imports())
def test_the_names_a_migration_imports_still_exist(migration: str, module: str) -> None:
    """A module that imports but has lost the name is the same failure, later."""
    source = (VERSIONS / migration).read_text(encoding="utf-8")
    wanted = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module == module
        for alias in node.names
    }
    if not wanted:
        pytest.skip(f"{migration} imports {module} as a whole module")
    loaded = importlib.import_module(module)
    missing = sorted(name for name in wanted if not hasattr(loaded, name))
    assert not missing, f"{migration} imports {missing} from {module}, which no longer defines them"
