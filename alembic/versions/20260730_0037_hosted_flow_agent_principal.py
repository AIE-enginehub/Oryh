"""hosted flow agent principal

Revision ID: 20260730_0037
Revises: 20260730_0036
Create Date: 2026-07-29 10:00:00

`api_keys.principal_kind` splits "whose machine holds this key" from
`Actor.kind` ("is a person behind it"). A tenant's own service key keeps every
bit of its behaviour — it bypasses the permission layer because the tenant
issued it to itself. The new value, `hosted_flow_agent`, is issued only by the
platform and is permission-checked, attribution-locked and non-renamable, so a
customer can enumerate what their supplier's agent may do instead of having to
trust it. Every existing row backfills to `tenant_service`, which is what they
all are.

No schema change is needed for the other half of that work — the open-todo
assignment constraint the hosted runner's concurrency depends on
(`todos_open_entity_assignee_uk`) has guarded Postgres since the baseline
migration. It was simply never declared on the ORM model, so test databases
built from `create_all` ran without it; that is fixed in `app/models.py`, not
here.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260730_0037"
down_revision = "20260730_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        alter table "{schema}".api_keys
          add column if not exists principal_kind varchar(30) not null
          default 'tenant_service'
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".api_keys drop column if exists principal_kind')
