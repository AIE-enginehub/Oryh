"""Cost centres, and budgets scoped to one

Revision ID: 20261027_0104
Revises: 20261027_0103
Create Date: 2026-10-27 22:00:00

Plan docs/plans/budgets-2026-10-27.md, phase 3 (§13). Additive only:

* `cost_centers` — master data, a tree (`parent_id`), unique code per
  workspace.
* `cost_center_id` on employees (the home centre) and on the four spending
  headers: expense claims, purchase requests, purchase orders, invoices.
* `budgets.cost_center_id` — a spend budget scoped to a centre reads that
  centre's share of what the company budget collects.

Nothing is backfilled: existing documents carry no centre and stay in the
company budget only, which is where they were.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261027_0104"
down_revision = "20261027_0103"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"
CARRIERS = ("employees", "expense_claims", "purchase_requests", "purchase_orders", "invoices", "budgets")


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    centres = f'"{schema}".cost_centers'
    op.execute(
        f"""
        create table if not exists {centres} (
          id uuid primary key,
          tenant_id uuid not null,
          cost_center_code varchar(64) not null,
          name varchar(200) not null,
          parent_id uuid references {centres} (id),
          description text,
          status varchar(20) not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint cost_centers_code_uk unique (tenant_id, cost_center_code),
          constraint cost_centers_status_chk check (status in ('active', 'archived')),
          constraint cost_centers_not_own_parent_chk check (parent_id is null or parent_id <> id)
        )
        """
    )
    for column in ("tenant_id", "parent_id"):
        op.execute(f"create index if not exists cost_centers_{column}_idx on {centres} ({column})")
    op.execute(f"alter table {centres} enable row level security")
    op.execute(f"drop policy if exists tenant_isolation on {centres}")
    op.execute(
        f"""
        create policy tenant_isolation on {centres}
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )
    for table in CARRIERS:
        op.execute(
            f'alter table "{schema}".{table} '
            f"add column if not exists cost_center_id uuid references {centres} (id)"
        )
        op.execute(
            f'create index if not exists {table}_cost_center_id_idx on "{schema}".{table} (cost_center_id)'
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table in CARRIERS:
        op.execute(f'alter table "{schema}".{table} drop column if exists cost_center_id')
    op.execute(f'drop table if exists "{schema}".cost_centers')
