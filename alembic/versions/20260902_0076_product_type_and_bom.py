"""the manufacturing role on products, and bills of materials

Revision ID: 20260902_0076
Revises: 20260901_0075
Create Date: 2026-09-02 10:00:00

One products table, one closed axis: `product_type` (finished_good |
raw_material | semi_finished | service) says what a thing IS in the
factory's eyes, universal like customer_kind and not the tenant's to
extend, because constraints branch on it — a bill of materials is built
for a finished or semi-finished good only. Everything that HAPPENS to a
material already keys on products.id (stock ledger, supplier links,
purchase lines, receipts, picks, categories), which is why materials are a
column and not a table: a second table would mean a second ledger.
Existing rows backfill as finished goods — what a catalog held before it
knew the word.

Bills of materials are a header (version, output quantity, life) and lines
(component, quantity per that output, scrap rate). One ACTIVE recipe per
product; multi-level recipes are derived at read time.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260902_0076"
down_revision = "20260901_0075"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".products add column if not exists '
        f"product_type varchar(20) not null default 'finished_good'"
    )
    op.execute(
        f'alter table "{schema}".products drop constraint if exists products_product_type_chk'
    )
    op.execute(
        f'alter table "{schema}".products add constraint products_product_type_chk '
        f"check (product_type in ('finished_good', 'raw_material', 'semi_finished', 'service'))"
    )
    op.execute(
        f"""
        create table if not exists "{schema}".bills_of_materials (
          id uuid primary key,
          tenant_id uuid not null,
          product_id uuid not null references "{schema}".products (id),
          bom_code varchar(64),
          version varchar(50),
          output_quantity numeric(14, 4) not null default 1,
          status varchar(20) not null default 'draft',
          remarks text,
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint bills_of_materials_status_chk check (status in ('active', 'archived', 'draft'))
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".bom_items (
          id uuid primary key,
          tenant_id uuid not null,
          bom_id uuid not null references "{schema}".bills_of_materials (id),
          line_no integer,
          component_product_id uuid not null references "{schema}".products (id),
          quantity numeric(14, 4) not null,
          unit varchar(50),
          scrap_rate numeric(5, 2),
          description varchar(500),
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        )
        """
    )
    for table, indexed in (
        ("bills_of_materials", ("product_id",)),
        ("bom_items", ("bom_id", "component_product_id")),
    ):
        op.execute(
            f'create index if not exists {table}_tenant_idx '
            f'on "{schema}".{table} (tenant_id)'
        )
        for column in indexed:
            op.execute(
                f'create index if not exists {table}_{column}_idx '
                f'on "{schema}".{table} ({column})'
            )
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
        create unique index if not exists bills_of_materials_tenant_code_uq
          on "{schema}".bills_of_materials (tenant_id, bom_code)
          where bom_code IS NOT NULL
        """
    )
    op.execute(
        f"""
        create unique index if not exists bills_of_materials_active_product_uq
          on "{schema}".bills_of_materials (tenant_id, product_id)
          where status = 'active'
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".bom_items')
    op.execute(f'drop table if exists "{schema}".bills_of_materials')
    op.execute(
        f'alter table "{schema}".products drop constraint if exists products_product_type_chk'
    )
    op.execute(f'alter table "{schema}".products drop column if exists product_type')
