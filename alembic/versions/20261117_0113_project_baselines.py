"""Project baselines: the plan as it stood, frozen

Revision ID: 20261117_0113
Revises: 20261116_0112
Create Date: 2026-11-17 10:00:00

Plan docs/plans/project-management-2026-11-15.md, after phase 3. Planned
dates move whenever the agent replans; until now the original plan survived
only in the audit trail. A baseline copies every task's planned dates and
hours and every milestone's due date into one row, numbered per project.
It never changes and is never removed: re-baselining is the next number.
How far the plan has moved from it is derived on read.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261117_0113"
down_revision = "20261116_0112"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(
        f"""
        create table if not exists {s}.project_baselines (
          id uuid primary key,
          tenant_id uuid not null,
          project_id uuid not null references {s}.projects (id),
          baseline_no integer not null,
          name varchar(200) not null,
          note text,
          snapshot jsonb not null,
          captured_by varchar(200) not null,
          captured_at timestamptz not null default now(),
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint project_baselines_no_uk unique (tenant_id, project_id, baseline_no),
          constraint project_baselines_no_chk check (baseline_no >= 1)
        )
        """
    )
    for column in ("tenant_id", "project_id"):
        op.execute(f"create index if not exists project_baselines_{column}_idx on {s}.project_baselines ({column})")
    op.execute(f"alter table {s}.project_baselines enable row level security")
    op.execute(f"drop policy if exists tenant_isolation on {s}.project_baselines")
    op.execute(
        f"""
        create policy tenant_isolation on {s}.project_baselines
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".project_baselines')
