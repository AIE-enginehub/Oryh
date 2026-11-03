"""Budgets phase 2: sales sub-targets and alert percents

Revision ID: 20261027_0103
Revises: 20261027_0102
Create Date: 2026-10-27 18:00:00

Plan docs/plans/budgets-2026-10-27.md, phase 2. Additive only:

* `budget_lines` gains `parent_line_id` and four dimension columns. A
  sub-target hangs under the sales line and names exactly one of a
  salesperson, a territory, a customer or a product category
  (`budget_lines_dimension_chk`), once per parent while active
  (`budget_lines_sub_target_uk`). The collector index now counts top-level
  lines only, since a sub-target shares its parent's category.
* `budgets.alert_percents` — the percents of plan at which a line's owner is
  told; null keeps the shipped default.
* `budget_alerts` — what the alert sweep raised, one open row per line and
  percent (`budget_alerts_open_uk`).

Nothing to backfill: existing lines are top-level, and no alert has been
raised before this.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261027_0103"
down_revision = "20261027_0102"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"
DIMENSIONS = ("employee_id", "territory_id", "customer_id", "product_category_id")
DIMENSION_TABLES = {
    "employee_id": "employees",
    "territory_id": "territories",
    "customer_id": "customers",
    "product_category_id": "product_categories",
}


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    lines = f'"{schema}".budget_lines'
    op.execute(f'alter table {lines} add column if not exists parent_line_id uuid references {lines} (id)')
    for column, table in DIMENSION_TABLES.items():
        op.execute(f'alter table {lines} add column if not exists {column} uuid references "{schema}".{table} (id)')
    for column in ("parent_line_id", *DIMENSIONS):
        op.execute(f"create index if not exists budget_lines_{column}_idx on {lines} ({column})")
    op.execute(f"alter table {lines} drop constraint if exists budget_lines_dimension_chk")
    # spelled as plain AND/OR — no num_nonnulls (Postgres-only), no CASE
    # (pg_dump wraps it over lines) — so the registry's copy builds on SQLite
    none = " and ".join(f"{column} is null" for column in DIMENSIONS)
    exactly_one = " or ".join(
        "(" + " and ".join(f"{other} is {'not ' if other == column else ''}null" for other in DIMENSIONS) + ")"
        for column in DIMENSIONS
    )
    op.execute(
        f"alter table {lines} add constraint budget_lines_dimension_chk check ("
        f"(parent_line_id is null and {none}) or (parent_line_id is not null and ({exactly_one})))"
    )
    op.execute(f'drop index if exists "{schema}".budget_lines_collector_uk')
    op.execute(
        f"create unique index if not exists budget_lines_collector_uk on {lines} "
        f"(tenant_id, budget_id, category) "
        f"where status = 'active' and parent_line_id is null and category in ('labour', 'marketing', 'sales')"
    )
    op.execute(
        f"create unique index if not exists budget_lines_sub_target_uk on {lines} "
        f"(tenant_id, parent_line_id, coalesce({', '.join(DIMENSIONS)})) "
        f"where status = 'active' and parent_line_id is not null"
    )

    op.execute(f'alter table "{schema}".budgets add column if not exists alert_percents jsonb')
    op.execute(
        f"""
        create table if not exists "{schema}".budget_alerts (
          id uuid primary key,
          tenant_id uuid not null,
          budget_id uuid not null references "{schema}".budgets (id),
          budget_line_id uuid not null references {lines} (id),
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
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".budget_alerts')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".budget_alerts
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    lines = f'"{schema}".budget_lines'
    op.execute(f'drop table if exists "{schema}".budget_alerts')
    op.execute(f'alter table "{schema}".budgets drop column if exists alert_percents')
    op.execute(f'drop index if exists "{schema}".budget_lines_sub_target_uk')
    op.execute(f'drop index if exists "{schema}".budget_lines_collector_uk')
    op.execute(f"alter table {lines} drop constraint if exists budget_lines_dimension_chk")
    for column in (*DIMENSIONS, "parent_line_id"):
        op.execute(f"alter table {lines} drop column if exists {column}")
    op.execute(
        f"create unique index if not exists budget_lines_collector_uk on {lines} "
        f"(tenant_id, budget_id, category) "
        f"where status = 'active' and category in ('labour', 'marketing', 'sales')"
    )
