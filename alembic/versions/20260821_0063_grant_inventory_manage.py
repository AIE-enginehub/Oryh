"""whoever managed the stock ledger yesterday still can

Revision ID: 20260821_0063
Revises: 20260821_0062
Create Date: 2026-08-21 14:00:00

`inventory.manage` is split out of `master_data.manage`: a warehouse keeper
is not a catalog administrator, and under one capability a warehouse role held
every product, vendor and customer record or nothing at all.

A split that only adds a capability takes something away. The stock endpoints
now refuse `master_data.manage`, so every role that posted movements through
it would 403 on upgrade — the exact shape of 0060, where a scope shipped and
nobody held it, found by a finance user who could raise every other kind of
invoice. Admins are covered by the deploy-time top-up to ALL_PERMISSIONS;
nothing covers a custom role, by design ("we ship no defaults for a role a
tenant invented"), so this migration is the named, reviewed grant.

Narrow on purpose: only roles holding `master_data.manage` today. That is not
a widening — those roles could already do everything this capability gates —
and it is what makes the split usable: a workspace can now REMOVE it from
the catalog roles that should not touch stock, which was impossible while the
two were one word.

Idempotent: a role already holding the scope is skipped.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision = "20260821_0063"
down_revision = "20260821_0062"
branch_labels = None
depends_on = None

SCHEMA = settings.database_schema
NEW = "inventory.manage"
QUALIFIES = "master_data.manage"


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f'select id, permissions_jsonb from "{SCHEMA}".roles')
    ).fetchall()
    granted = 0
    for role_id, permissions in rows:
        current = permissions if isinstance(permissions, list) else json.loads(permissions or "[]")
        if NEW in current or QUALIFIES not in current:
            continue
        bind.execute(
            sa.text(
                f'update "{SCHEMA}".roles set permissions_jsonb = :perms, '
                "updated_at = now() where id = :id"
            ),
            {"perms": json.dumps(sorted([*current, NEW])), "id": role_id},
        )
        granted += 1
    print(f"granted {NEW} to {granted} role(s) holding {QUALIFIES}")


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f'select id, permissions_jsonb from "{SCHEMA}".roles')
    ).fetchall()
    for role_id, permissions in rows:
        current = permissions if isinstance(permissions, list) else json.loads(permissions or "[]")
        if NEW not in current:
            continue
        bind.execute(
            sa.text(
                f'update "{SCHEMA}".roles set permissions_jsonb = :perms, '
                "updated_at = now() where id = :id"
            ),
            {"perms": json.dumps([p for p in current if p != NEW]), "id": role_id},
        )
