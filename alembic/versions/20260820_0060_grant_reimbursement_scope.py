"""whoever bills suppliers may bill an approved expense claim

Revision ID: 20260820_0060
Revises: 20260820_0059
Create Date: 2026-08-20 05:10:00

`invoice.manage:reimbursement` arrived with the reimbursement direction two
migrations ago, and nothing gave it to anybody. A workspace upgrading into
that release finds its payables desk holding `:sales` and `:purchase` — the
scopes it was deliberately granted — and 403 on the one route the new
payables instructions send it to first. Nothing announces a scope; the failure
surfaces as an agent stuck mid-task.

Found by running the deployment e2e against the release: the seeded
`finance_reviewer` could bill a supplier and could not bill a colleague.

The grant is narrow on purpose. It goes to roles that already hold
`invoice.manage:purchase` or `invoice.manage:*` — the desks that already file
money going OUT — and to nobody else. A role scoped to `:sales` alone is an
应收会计, and receivables is not where reimbursements are paid; widening that
would hand out an authority its workspace never granted.

Idempotent: a role that already holds the scope is skipped, so a re-run and a
freshly seeded tenant converge on the same set.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision = "20260820_0060"
down_revision = "20260820_0059"
branch_labels = None
depends_on = None

SCHEMA = settings.database_schema
SCOPE = "invoice.manage:reimbursement"
QUALIFIES = ("invoice.manage:purchase", "invoice.manage:*")


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f'select id, permissions_jsonb from "{SCHEMA}".roles')
    ).fetchall()
    granted = 0
    for role_id, permissions in rows:
        current = permissions if isinstance(permissions, list) else json.loads(permissions or "[]")
        if SCOPE in current:
            continue
        if not any(p in current for p in QUALIFIES):
            continue
        bind.execute(
            sa.text(
                f'update "{SCHEMA}".roles set permissions_jsonb = :perms, '
                "updated_at = now() where id = :id"
            ),
            {"perms": json.dumps(sorted([*current, SCOPE])), "id": role_id},
        )
        granted += 1
    print(f"granted {SCOPE} to {granted} role(s)")


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f'select id, permissions_jsonb from "{SCHEMA}".roles')
    ).fetchall()
    for role_id, permissions in rows:
        current = permissions if isinstance(permissions, list) else json.loads(permissions or "[]")
        if SCOPE not in current:
            continue
        bind.execute(
            sa.text(
                f'update "{SCHEMA}".roles set permissions_jsonb = :perms, '
                "updated_at = now() where id = :id"
            ),
            {"perms": json.dumps([p for p in current if p != SCOPE]), "id": role_id},
        )
