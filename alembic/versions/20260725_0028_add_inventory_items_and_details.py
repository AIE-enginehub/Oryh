"""inventory items over an append-only movement ledger

Revision ID: 20260725_0028
Revises: 20260725_0027
Create Date: 2026-07-25 19:00:00

Modeled on OFBiz InventoryItem / InventoryItemDetail, minus serialized items,
owner parties and accounting quantities. The item's quantity_on_hand and
available_to_promise are DERIVED — running sums of the detail ledger, moved
only by the application's single write path — so details have no update or
delete anywhere, and a stock-take import records a differing count as an
`import_override` movement instead of editing the item.

facility and lot_id are NOT NULL with '' meaning "unspecified", which lets the
stock-position identity (product-or-sku, facility, lot) live in the same
partial-unique-index pattern the price book uses.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260725_0028"
down_revision = "20260725_0027"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".inventory_items (
          id uuid primary key,
          tenant_id uuid not null,
          product_id uuid not null references "{schema}".products (id),
          sku_id uuid references "{schema}".product_skus (id),
          facility varchar(100) not null default '',
          lot_id varchar(64) not null default '',
          bin_number varchar(64),
          expire_date date,
          received_at timestamptz,
          quantity_on_hand numeric(12, 2) not null default 0,
          available_to_promise numeric(12, 2) not null default 0,
          unit_cost numeric(12, 2),
          currency varchar(3) not null default 'CNY',
          status text not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".inventory_item_details (
          id uuid primary key,
          tenant_id uuid not null,
          inventory_item_id uuid not null references "{schema}".inventory_items (id),
          quantity_on_hand_diff numeric(12, 2) not null,
          available_to_promise_diff numeric(12, 2) not null,
          reason varchar(30) not null,
          description varchar(500),
          entity_type varchar(50),
          entity_id uuid,
          unit_cost numeric(12, 2),
          effective_at timestamptz not null default now(),
          created_by varchar(100),
          created_at timestamptz not null default now()
        )
        """
    )
    for table in ("inventory_items", "inventory_item_details"):
        op.execute(f'create index if not exists {table}_tenant_idx on "{schema}".{table} (tenant_id)')
        op.execute(f'alter table "{schema}".{table} enable row level security')
        op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
        op.execute(
            f"""
            create policy tenant_isolation on "{schema}".{table}
              using ({TENANT_MATCH} or {PLATFORM_ON})
              with check ({TENANT_MATCH})
            """
        )
    op.execute(f'create index if not exists inventory_items_product_idx on "{schema}".inventory_items (product_id)')
    op.execute(f'create index if not exists inventory_items_sku_idx on "{schema}".inventory_items (sku_id)')
    op.execute(
        f'create index if not exists inventory_item_details_item_idx '
        f'on "{schema}".inventory_item_details (inventory_item_id)'
    )
    # the stock-position identity: one item per (product-or-sku, facility, lot)
    op.execute(
        f"""
        create unique index if not exists inventory_items_product_tuple_uq
          on "{schema}".inventory_items (tenant_id, product_id, facility, lot_id)
          where sku_id is null
        """
    )
    op.execute(
        f"""
        create unique index if not exists inventory_items_sku_tuple_uq
          on "{schema}".inventory_items (tenant_id, sku_id, facility, lot_id)
          where sku_id is not null
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
    op.execute(f'drop table if exists "{schema}".inventory_item_details')
    op.execute(f'drop table if exists "{schema}".inventory_items')
