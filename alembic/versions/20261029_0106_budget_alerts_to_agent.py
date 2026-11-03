"""Budget alerts move to the agent

Revision ID: 20261029_0106
Revises: 20261028_0105
Create Date: 2026-10-29 10:00:00

Plan docs/plans/budgets-2026-10-27.md §12.2, revised. When a line's progress
warrants telling someone, and whom, is the workspace's rule, not the
record's: the execution read reports each line's `percent_consumed` and
`percent_achieved`, and the agent reads the rule and raises the todo. The
server no longer stores alert percents or raises alerts, so this drops:

* `budget_alerts` — what the retired sweep raised. The todos it gave people
  stay; they are ordinary todos.
* `budgets.alert_percents`.

The downgrade restores both, empty.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261029_0106"
down_revision = "20261028_0105"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".budget_alerts')
    op.execute(f'alter table "{schema}".budgets drop column if exists alert_percents')


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".budgets add column if not exists alert_percents jsonb')
    op.execute(
        f"""
        create table if not exists "{schema}".budget_alerts (
          id uuid primary key,
          tenant_id uuid not null,
          budget_id uuid not null references "{schema}".budgets (id),
          budget_line_id uuid not null references "{schema}".budget_lines (id),
          percent integer not null,
          measure varchar(20) not null,
          reached_percent numeric(9, 1) not null,
          recipient_employee_id uuid references "{schema}".employees (id),
          todo_id uuid references "{schema}".todos (id),
          raised_at timestamptz not null,
          cleared_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint budget_alerts_measure_chk check (measure in ('achieved', 'consumed')),
          constraint budget_alerts_percent_chk check (percent > 0)
        )
        """
    )
    op.execute(
        f'create unique index if not exists budget_alerts_open_uk on "{schema}".budget_alerts '
        f"(tenant_id, budget_line_id, percent) where cleared_at is null"
    )
    for column in ("tenant_id", "budget_id", "budget_line_id", "recipient_employee_id"):
        op.execute(f'create index if not exists budget_alerts_{column}_idx on "{schema}".budget_alerts ({column})')
    op.execute(f'alter table "{schema}".budget_alerts enable row level security')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".budget_alerts
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )
