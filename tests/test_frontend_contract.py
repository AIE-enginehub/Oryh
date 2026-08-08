"""Pin the console's checked-in API contract to the real API.

The React console does not read the API to type itself; it reads a snapshot.
`scripts/export_openapi.py` writes `frontend/openapi.json`, `npm run
api:generate` turns that into `frontend/src/api/schema.d.ts`, and
`frontend/src/api/client.ts` aliases its whole public surface out of the result
(`export type Role = RoleRead;`). Both files are generated, both are committed,
and nothing made either of them a build input — so a contract change compiled,
passed, and shipped while the snapshot beside it stayed at whatever the last
person to remember had exported.

It rotted for months. When this guard was written the snapshot was missing the
entire purchase-order family, bulk document import for orders and quotations,
and skill assignment/audience/reach; it still carried the hand-named
`RoleEnvelope` schemas from before the generic `Envelope[T]` refactor, and the
server-rendered `/web` and `/admin` form routes that `console_contract()`
exists to exclude. The console was typed against an API that no longer existed,
and `tsc` had no way to know.

`tests/test_skill_docs.py` is this guard for the hand-written skill corpus.
This is the generated one. No DB and no client fixture — both tests compare
committed files against `app.openapi()`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.export_openapi import console_contract

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO_ROOT / "frontend" / "openapi.json"
GENERATED_TYPES = REPO_ROOT / "frontend" / "src" / "api" / "schema.d.ts"

REGENERATE = (
    "Regenerate both, from the repository root:\n"
    "    uv run python scripts/export_openapi.py\n"
    "    npm --prefix frontend run api:generate"
)


def _operations(spec: dict) -> set[str]:
    """`METHOD /path` for every operation, for a diffable failure message."""
    return {
        f"{method.upper()} {path}"
        for path, item in spec.get("paths", {}).items()
        for method in item
        if method != "parameters"
    }


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _listing(names: list[str], limit: int = 12) -> str:
    """Enough names to recognize what moved without pasting a wall of them."""
    head = ", ".join(names[:limit])
    return head if len(names) <= limit else f"{head}, … and {len(names) - limit} more"


def _summarize(committed: dict, current: dict) -> str:
    """Name what drifted. The specs are tens of thousands of lines each; a bare
    `assert committed == current` reports that two dicts differ and leaves the
    reader to find out how."""
    lines: list[str] = []

    stale, fresh = _operations(committed), _operations(current)
    for label, ops in (("missing from the snapshot", fresh - stale), ("no longer served", stale - fresh)):
        if ops:
            lines.append(f"  {_count(len(ops), 'operation')} {label}:")
            lines += [f"    {op}" for op in sorted(ops)[:20]]
            if len(ops) > 20:
                lines.append(f"    … and {len(ops) - 20} more")

    stale_schemas = committed.get("components", {}).get("schemas", {})
    fresh_schemas = current.get("components", {}).get("schemas", {})
    added = sorted(set(fresh_schemas) - set(stale_schemas))
    removed = sorted(set(stale_schemas) - set(fresh_schemas))
    changed = sorted(
        name
        for name in set(stale_schemas) & set(fresh_schemas)
        if stale_schemas[name] != fresh_schemas[name]
    )
    for label, names in (("added", added), ("removed", removed), ("changed", changed)):
        if names:
            lines.append(f"  {_count(len(names), 'schema')} {label}: {_listing(names)}")

    # Neither view above covers `info`/`openapi` version keys.
    if not lines:
        lines.append("  paths and schemas agree; a top-level key differs (info, openapi version)")
    return "\n".join(lines)


def test_frontend_snapshot_matches_app() -> None:
    """The committed snapshot must be exactly what the exporter produces now.

    Except in a standalone assembly, where it must be a SUPERSET. The snapshot
    and the generated types are build inputs produced from the cloud edition,
    and regenerating them needs npm — so a standalone tree ships a console
    typed against a few endpoints it never calls. What still has to hold is
    the direction that matters: nothing the server serves may be missing from
    the types the console was compiled against.
    """
    from app.core.config import settings

    committed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    current = console_contract()

    if settings.resolved_edition == "standalone" and committed != current:
        missing = sorted(set(current["paths"]) - set(committed["paths"]))
        assert not missing, (
            "the standalone assembly serves paths the console's types do not "
            f"know: {missing}"
        )
        return

    # `pytest.fail` rather than `assert ==`: the specs run to tens of thousands
    # of lines, and pytest's own dict introspection would bury the summary under
    # a truncated dump of both.
    if committed != current:
        pytest.fail(
            f"{SNAPSHOT.relative_to(REPO_ROOT)} is stale — the console is typed against "
            f"an API the server no longer serves.\n"
            + _summarize(committed, current)
            + "\n"
            + REGENERATE,
            pytrace=False,
        )


def _declared_schema_names(source: str) -> set[str]:
    """Schema names in the generated `components.schemas` block.

    openapi-typescript indents that block's members by eight spaces; a schema's
    own properties sit deeper, so the anchor picks out exactly the top level.
    """
    block = re.search(r"^    schemas: \{$(.*?)^    \};$", source, re.S | re.M)
    assert block is not None, (
        f"no `schemas` block in {GENERATED_TYPES.relative_to(REPO_ROOT)} — the "
        f"generator's output shape changed and this test can no longer read it."
    )
    return set(re.findall(r'^        "?([A-Za-z_$][\w$]*)"?\??: ', block.group(1), re.M))


def test_generated_types_match_snapshot() -> None:
    """`api:generate` is a second, separate step: exporting the snapshot without
    rerunning it leaves `client.ts` aliasing types the console cannot see."""
    snapshot_names = set(json.loads(SNAPSHOT.read_text(encoding="utf-8"))["components"]["schemas"])
    generated_names = _declared_schema_names(GENERATED_TYPES.read_text(encoding="utf-8"))

    missing = sorted(snapshot_names - generated_names)
    extra = sorted(generated_names - snapshot_names)
    if missing or extra:
        pytest.fail(
            f"{GENERATED_TYPES.relative_to(REPO_ROOT)} does not match "
            f"{SNAPSHOT.relative_to(REPO_ROOT)}.\n"
            + (f"  {_count(len(missing), 'schema')} in the snapshot but not generated: {_listing(missing)}\n" if missing else "")
            + (f"  {_count(len(extra), 'schema')} generated but not in the snapshot: {_listing(extra)}\n" if extra else "")
            + REGENERATE,
            pytrace=False,
        )
