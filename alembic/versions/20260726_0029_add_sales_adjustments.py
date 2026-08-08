"""quotation and order adjustments — OFBiz Quote/OrderAdjustment, tenant-shaped

Revision ID: 20260726_0029
Revises: 20260725_0028
Create Date: 2026-07-26 10:00:00

Signed amounts that move a document's total beside the line math — 促销
discounts, tax, shipping, fees, 抹零. Many per quotation/order, each
optionally pinned to one line (item id null = header level). Where the
declared header total used to differ from computed_total implicitly, these
make the difference explicit and auditable. Soft-deleted like the item
families they sit beside.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260726_0029"
down_revision = "20260725_0028"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"

# (table, parent table, parent column, item table, item column)
TABLES = (
    ("sales_quotation_adjustments", "sales_quotations", "quotation_id", "sales_quotation_items", "quotation_item_id"),
    ("sales_order_adjustments", "sales_orders", "order_id", "sales_order_items", "order_item_id"),
)


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table, parent, parent_col, item_table, item_col in TABLES:
        op.execute(
            f"""
            create table if not exists "{schema}".{table} (
              id uuid primary key,
              tenant_id uuid not null,
              {parent_col} uuid not null references "{schema}".{parent} (id),
              {item_col} uuid references "{schema}".{item_table} (id),
              adjustment_type text not null,
              description varchar(500),
              amount numeric(12, 2) not null,
              source_percentage numeric(5, 2),
              metadata_jsonb jsonb not null default '{{}}'::jsonb,
              created_at timestamptz not null default now(),
              updated_at timestamptz not null default now(),
              deleted_at timestamptz
            )
            """
        )
        op.execute(f'create index if not exists {table}_tenant_idx on "{schema}".{table} (tenant_id)')
        op.execute(f'create index if not exists {table}_parent_idx on "{schema}".{table} ({parent_col})')
        op.execute(f'create index if not exists {table}_item_idx on "{schema}".{table} ({item_col})')
        op.execute(f'alter table "{schema}".{table} enable row level security')
        op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
        op.execute(
            f"""
            create policy tenant_isolation on "{schema}".{table}
              using ({TENANT_MATCH} or {PLATFORM_ON})
              with check ({TENANT_MATCH})
            """
        )
    op.execute(
        f"""
        do $$
        begin
          if exists (select 1 from pg_roles where rolname = 'oryh_app') then
            grant select, insert, update, delete on all tables in schema "{schema}" to oryh_app;
          end if;
        end $$
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table, *_ in TABLES:
        op.execute(f'drop table if exists "{schema}".{table}')
