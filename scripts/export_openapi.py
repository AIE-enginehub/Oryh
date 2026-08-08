#!/usr/bin/env python3
"""Export the FastAPI contract consumed by the React console.

The export is deterministic and does not connect to the database. Keeping a
snapshot beside the frontend lets its generated TypeScript client build in an
isolated container without requiring a running API service.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from app.main import app


def _schema_references(value: object) -> set[str]:
    references: set[str] = set()
    if isinstance(value, dict):
        reference = value.get("$ref")
        prefix = "#/components/schemas/"
        if isinstance(reference, str) and reference.startswith(prefix):
            references.add(reference.removeprefix(prefix))
        for child in value.values():
            references.update(_schema_references(child))
    elif isinstance(value, list):
        for child in value:
            references.update(_schema_references(child))
    return references


def console_contract() -> dict:
    """Return only the public JSON API and the schemas reachable from it."""

    # `app.openapi()` memoizes and hands back the very dict it caches, so the
    # pruning below would otherwise narrow the app's own schema for everything
    # else in the process — including tests that read `app.openapi()`.
    contract = copy.deepcopy(app.openapi())
    contract["paths"] = {
        path: definition
        for path, definition in contract.get("paths", {}).items()
        if path.startswith("/api/v1/")
    }

    components = contract.get("components", {})
    schemas = components.get("schemas", {})
    reachable = _schema_references(contract["paths"])
    pending = list(reachable)
    while pending:
        name = pending.pop()
        for reference in _schema_references(schemas.get(name, {})) - reachable:
            reachable.add(reference)
            pending.append(reference)
    components["schemas"] = {
        name: schema for name, schema in schemas.items() if name in reachable
    }
    return contract


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path("frontend/openapi.json"),
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(console_contract(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
