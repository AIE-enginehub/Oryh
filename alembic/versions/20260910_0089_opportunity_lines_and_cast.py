"""an opportunity's lines, its cast, its close details, and its link on
quotations and orders

Revision ID: 20260910_0089
Revises: 20260910_0088
Create Date: 2026-09-10 14:00:00

A deal is more than a title and an estimate once it is real. Its LINES are
what it is expected to be for (a product, a quantity, a price when stated —
the quotation line's shape without its rigour); its CAST is who on the
customer's side matters and how (Salesforce's OpportunityContactRole); its
close details are the salesperson's read of the odds, why it was lost and
to whom, and where it came from when no lead preceded it. Quotations and
orders carry `opportunity_id`, so where the deal's money went is a filter,
and the quote bridge (`POST /opportunities/{id}/quote`) sets it.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20260910_0089"
down_revision = "20260910_0088"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for column, ddl in (
        ("probability", "integer"),
        ("lost_reason", "varchar(50)"),
        ("competitor", "varchar(200)"),
        ("source", "varchar(100)"),
    ):
        op.execute(f'alter table "{schema}".opportunities add column if not exists {column} {ddl}')
    op.execute(
        f"""
        create table if not exists "{schema}".opportunity_items (
          id uuid primary key,
          tenant_id uuid not null,
          opportunity_id uuid not null references "{schema}".opportunities (id),
          line_no integer,
          product_id uuid references "{schema}".products (id),
          sku_id uuid references "{schema}".product_skus (id),
          product_name_snapshot varchar(200),
          spec varchar(200),
          quantity numeric(12, 2) not null,
          unit varchar(50),
          unit_price numeric(12, 2),
          amount numeric(12, 2),
          notes text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint opportunity_items_names_a_product_check
            check (product_id is not null or product_name_snapshot is not null)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".opportunity_contacts (
          id uuid primary key,
          tenant_id uuid not null,
          opportunity_id uuid not null references "{schema}".opportunities (id),
          contact_id uuid not null references "{schema}".customer_contacts (id),
          role varchar(50),
          is_primary boolean not null default false,
          remarks text,
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint opportunity_contacts_uk unique (tenant_id, opportunity_id, contact_id)
        )
        """
    )
    for table, columns in (
        ("opportunity_items", ("tenant_id", "opportunity_id", "product_id", "sku_id")),
        ("opportunity_contacts", ("tenant_id", "opportunity_id", "contact_id")),
    ):
        for column in columns:
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
    for table in ("sales_quotations", "sales_orders"):
        op.execute(
            f'alter table "{schema}".{table} '
            f'add column if not exists opportunity_id uuid references "{schema}".opportunities (id)'
        )
        op.execute(
            f'create index if not exists {table}_opportunity_id_idx '
            f'on "{schema}".{table} (opportunity_id)'
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table in ("sales_quotations", "sales_orders"):
        op.execute(f'drop index if exists "{schema}".{table}_opportunity_id_idx')
        op.execute(f'alter table "{schema}".{table} drop column if exists opportunity_id')
    op.execute(f'drop table if exists "{schema}".opportunity_contacts')
    op.execute(f'drop table if exists "{schema}".opportunity_items')
    for column in ("probability", "lost_reason", "competitor", "source"):
        op.execute(f'alter table "{schema}".opportunities drop column if exists {column}')
