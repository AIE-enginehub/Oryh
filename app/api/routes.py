"""What is left of `routes.py`: two names a frozen migration imports.

The 13,008-line module this file is named after was decomposed in v2026.8.14
into `common.py` and eleven endpoint modules, and deleted. This is not a
remnant of it — it is a compatibility shim with one caller.

`alembic/versions/20260804_0047_entity_reference_types.py` reaches for
`APPROVAL_ENTITY_TYPES` and `TODO_ENTITY_TYPES` through this path, inside
`upgrade()`. An applied migration's bytes are frozen: the release guard
(`ops/.../ensure-db-backup.sh`) compares the checksum of every migration in the
live release's tree against the target's and refuses a release that edits one.
`v2026.8.13` was tagged, built and withdrawn for exactly that, and this file
exists because v2026.8.14's first plan was refused the same way.

The import only ever runs on a FRESH database, where the container's
`alembic upgrade head` walks the chain from zero — a new environment, or the
standalone open-core install. Every deployed database is already past `0047`
and never executes it again. The test suite builds its schema with
`Base.metadata.create_all` and so never runs a migration at all, which is why
937 passing tests said nothing about a migration importing a deleted module;
`tests/test_migration_imports.py` is the guard that would have.

Nothing else may import this. Endpoints live in the eleven modules
`app/main.py` mounts; shared helpers live in `app/api/common.py`.
"""

from __future__ import annotations

from app.core.entity_types import APPROVAL_ENTITY_TYPES, TODO_ENTITY_TYPES

__all__ = ["APPROVAL_ENTITY_TYPES", "TODO_ENTITY_TYPES"]
