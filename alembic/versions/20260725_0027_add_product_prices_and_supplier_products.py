"""product price book and supplier links, OFBiz-shaped, history via status

Revision ID: 20260725_0027
Revises: 20260725_0026
Create Date: 2026-07-25 17:00:00

Two tables modeled on OFBiz's ProductPrice and SupplierProduct, minus the
date-range machinery: history is status, not fromDate/thruDate. Superseding a
price archives the old row and creates the new active one, so the invariant
"one LIVE price per (product-or-sku, price_type, currency)" lives in partial
unique indexes and archived rows are the paper trail. A supplier link is one
row per (product, vendor) — hard-unique — whose last_price updates in place;
archiving marks a lapsed source and a re-import revives it.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260725_0027"
down_revision = "20260725_0026"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".product_prices (
          id uuid primary key,
          tenant_id uuid not null,
          product_id uuid not null references "{schema}".products (id),
          sku_id uuid references "{schema}".product_skus (id),
          price_type text not null,
          price numeric(12, 2) not null,
          currency varchar(3) not null default 'CNY',
          tax_in_price boolean not null default true,
          tax_percentage numeric(5, 2),
          status text not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".supplier_products (
          id uuid primary key,
          tenant_id uuid not null,
          product_id uuid not null references "{schema}".products (id),
          vendor_id uuid not null references "{schema}".vendors (id),
          supplier_product_code varchar(64),
          supplier_product_name varchar(200),
          last_price numeric(12, 2),
          currency varchar(3) not null default 'CNY',
          lead_time_days integer,
          min_order_quantity numeric(12, 2),
          order_increment numeric(12, 2),
          preference integer,
          status text not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint supplier_products_tenant_product_vendor_uk
            unique (tenant_id, product_id, vendor_id)
        )
        """
    )
    for table in ("product_prices", "supplier_products"):
        op.execute(f'create index if not exists {table}_tenant_idx on "{schema}".{table} (tenant_id)')
        op.execute(f'create index if not exists {table}_product_idx on "{schema}".{table} (product_id)')
        op.execute(f'alter table "{schema}".{table} enable row level security')
        op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
        op.execute(
            f"""
            create policy tenant_isolation on "{schema}".{table}
              using ({TENANT_MATCH} or {PLATFORM_ON})
              with check ({TENANT_MATCH})
            """
        )
    op.execute(f'create index if not exists product_prices_sku_idx on "{schema}".product_prices (sku_id)')
    op.execute(f'create index if not exists supplier_products_vendor_idx on "{schema}".supplier_products (vendor_id)')
    # one ACTIVE price per key; archiving frees the slot and keeps history
    op.execute(
        f"""
        create unique index if not exists product_prices_active_product_uq
          on "{schema}".product_prices (tenant_id, product_id, price_type, currency)
          where status = 'active' and sku_id is null
        """
    )
    op.execute(
        f"""
        create unique index if not exists product_prices_active_sku_uq
          on "{schema}".product_prices (tenant_id, sku_id, price_type, currency)
          where status = 'active' and sku_id is not null
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
    op.execute(f'drop table if exists "{schema}".product_prices')
    op.execute(f'drop table if exists "{schema}".supplier_products')
