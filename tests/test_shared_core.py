"""`common.py` may only hold what is actually shared.

The decomposition of `routes.py` fed this module for seven commits, and a
shared-core module has one failure mode: it becomes the drawer. A helper lands
there because at the time several *domains* called it, the domains later become
*modules*, and nobody re-asks whether the reason still holds. It costs a reader
a file hop and it makes the shared surface look larger than it is.

The test for "shared" is narrow on purpose. A definition earns its place if it
is imported by two or more `app/api` modules, OR `common.py` itself uses it —
`CENT` is imported only by `billing.py`, but `ensure_nothing_applied` here reads
it, so `claims.py` reaches it through this module rather than around it. What
fails is the third case: exactly one module imports it, nothing here touches it,
and nothing outside `app/api` wants it either. That one belongs in its caller.

Two were found the first time this ran — `ensure_code_available` and
`_run_bulk_upsert`, both pure master-data, both promoted on a call graph taken
before `master_data.py` existed.
"""

from __future__ import annotations

import ast
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMON = ROOT / "app/api/common.py"
SKIP = {".venv", "node_modules", "__pycache__", ".claude", "dist", "build"}


def _top_level(source: str) -> dict[str, ast.AST]:
    found: dict[str, ast.AST] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            found[node.name] = node
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                if isinstance(target, ast.Name):
                    found[target.id] = node
    return found


def _importers() -> dict[str, set[str]]:
    """Which files import each name from `app.api.common`."""
    found: dict[str, set[str]] = defaultdict(set)
    for path in sorted(ROOT.rglob("*.py")):
        if set(path.relative_to(ROOT).parts) & SKIP or path == COMMON:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.api.common":
                for alias in node.names:
                    found[alias.name].add(str(path.relative_to(ROOT)))
    return found


def _used_inside(definitions: dict[str, ast.AST]) -> set[str]:
    """Names `common.py` reaches for from its own definitions."""
    used: set[str] = set()
    for owner, node in definitions.items():
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id in definitions and child.id != owner:
                used.add(child.id)
    return used


def test_the_shared_core_was_found() -> None:
    """Guard the guard: an analysis that stops seeing the module must fail."""
    definitions = _top_level(COMMON.read_text(encoding="utf-8"))
    assert len(definitions) > 50, f"only {len(definitions)} definitions parsed from common.py"
    assert _importers(), "nothing imports app.api.common any more"


def test_nothing_in_common_is_used_by_only_one_module() -> None:
    definitions = _top_level(COMMON.read_text(encoding="utf-8"))
    importers = _importers()
    inside = _used_inside(definitions)

    lonely = []
    for name in definitions:
        everyone = importers.get(name, set())
        api = {user for user in everyone if user.startswith("app/api/")}
        if len(api) == 1 and name not in inside and not (everyone - api):
            lonely.append(f"{name} — only {next(iter(api))} imports it")

    assert not lonely, (
        "these live in the shared core but nothing shares them; move each into "
        "the module that uses it:\n  " + "\n  ".join(sorted(lonely))
        + "\n\nIf one genuinely belongs here — a seam a second module is about "
        "to need — say so where it is defined and add it to this test."
    )
