"""A project's status becomes the workspace's vocabulary

Revision ID: 20261116_0112
Revises: 20261116_0111
Create Date: 2026-11-16 16:00:00

Plan docs/plans/project-management-2026-11-15.md, phase 3. The fixed
`active` / `archived` CHECK goes; the status is now checked on write against
the tenant's `project_status` vocabulary (planning, active, on_hold, closed,
cancelled, archived, or the workspace's own words). Nothing on the server
reads a project's status, so a state machine would refuse moves for no rule
the server holds; the order of a project's life is the agent's and the
audit trail's.

Existing rows keep their value: both `active` and `archived` are in the
shipped vocabulary.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261116_0112"
down_revision = "20261116_0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".projects drop constraint if exists projects_status_chk')


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    # words the old CHECK never knew fold back to the two it did
    op.execute(f"update {s}.projects set status = 'archived' where status in ('closed', 'cancelled')")
    op.execute(f"update {s}.projects set status = 'active' where status not in ('active', 'archived')")
    op.execute(f"alter table {s}.projects add constraint projects_status_chk check (status in ('active', 'archived'))")
