"""customer price agreements: SupplierProduct's sell-side mirror

Revision ID: 20260830_0070
Revises: 20260829_0069
Create Date: 2026-08-30 10:00:00

One customer's standing terms for one product: THEIR code and name for it —
the join key against their purchase orders, where "货号 KH-3301" means
nothing until this table says which product it is — plus the agreed price
and order rules. One row per (product, customer), status archives a lapsed
agreement, agreed_price updates in place; the paper trail is the documents
that quoted it. The price book stays the general answer — this row is the
exception one named customer negotiated.

Unlike supplier_products (which predates the convention), the status CHECK
ships in the DDL and the constraint registry pins it.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260830_0070"
down_revision = "20260829_0069"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".customer_products (
          id uuid primary key,
          tenant_id uuid not null,
          product_id uuid not null references "{schema}".products (id),
          customer_id uuid not null references "{schema}".customers (id),
          customer_product_code varchar(64),
          customer_product_name varchar(200),
          agreed_price numeric(12, 2),
          currency varchar(3) not null default 'CNY',
          min_order_quantity numeric(12, 2),
          order_increment numeric(12, 2),
          status varchar(20) not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint customer_products_tenant_product_customer_uk
            unique (tenant_id, product_id, customer_id),
          constraint customer_products_status_chk check (status in ('active', 'archived'))
        )
        """
    )
    op.execute(
        f'create index if not exists customer_products_tenant_idx '
        f'on "{schema}".customer_products (tenant_id)'
    )
    op.execute(
        f'create index if not exists customer_products_product_id_idx '
        f'on "{schema}".customer_products (product_id)'
    )
    op.execute(
        f'create index if not exists customer_products_customer_id_idx '
        f'on "{schema}".customer_products (customer_id)'
    )
    op.execute(f'alter table "{schema}".customer_products enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".customer_products')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".customer_products
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".customer_products')
