"""add purchase requests and product master data

Revision ID: 20260711_0017
Revises: 20260711_0016
Create Date: 2026-07-11 14:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260711_0017"
down_revision = "20260711_0016"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".products (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          product_code text,
          name text not null,
          spec text,
          unit text,
          list_price numeric(12,2),
          currency text not null default 'CNY',
          status text not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint products_status_chk check (status in ('active', 'archived')),
          constraint products_list_price_chk check (list_price is null or list_price >= 0)
        )
        """
    )
    op.execute(
        f"""
        create index if not exists products_tenant_idx
          on "{schema}".products (tenant_id, status, created_at desc)
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".product_skus (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          product_id uuid not null references "{schema}".products(id),
          sku_code text,
          variant_attrs jsonb not null default '{{}}'::jsonb,
          list_price numeric(12,2),
          status text not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint product_skus_status_chk check (status in ('active', 'archived')),
          constraint product_skus_list_price_chk check (list_price is null or list_price >= 0)
        )
        """
    )
    op.execute(
        f"""
        create index if not exists product_skus_product_idx
          on "{schema}".product_skus (product_id, status)
        """
    )
    op.execute(
        f"""
        create index if not exists product_skus_tenant_idx
          on "{schema}".product_skus (tenant_id)
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".purchase_requests (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          employee_id uuid not null references "{schema}".employees(id),
          title text not null,
          request_date date,
          needed_by date,
          vendor_id uuid references "{schema}".vendors(id),
          vendor_name_snapshot text,
          currency text not null default 'CNY',
          status text not null default 'draft',
          submitted_at timestamptz,
          source_report_text text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz,
          deleted_by text,
          delete_reason text
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".purchase_request_items (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          request_id uuid not null references "{schema}".purchase_requests(id),
          product_id uuid references "{schema}".products(id),
          sku_id uuid references "{schema}".product_skus(id),
          product_name_snapshot text,
          spec text,
          quantity numeric(12,2) not null,
          unit text,
          unit_price numeric(12,2),
          amount numeric(12,2),
          attachment_id uuid references "{schema}".attachments(id),
          notes text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz,
          constraint purchase_request_items_quantity_chk check (quantity > 0),
          constraint purchase_request_items_unit_price_chk check (unit_price is null or unit_price >= 0),
          constraint purchase_request_items_amount_chk check (amount is null or amount >= 0)
        )
        """
    )
    op.execute(
        f"""
        create index if not exists purchase_requests_tenant_status_idx
          on "{schema}".purchase_requests (tenant_id, status, created_at desc)
        """
    )
    op.execute(
        f"""
        create index if not exists purchase_requests_employee_idx
          on "{schema}".purchase_requests (employee_id)
        """
    )
    op.execute(
        f"""
        create index if not exists purchase_request_items_request_idx
          on "{schema}".purchase_request_items (request_id)
        """
    )
    # legacy check constraints predate the purchase builtin: admit purchase_request
    op.execute(
        f"""
        alter table "{schema}".approval_records
          drop constraint if exists approval_records_entity_type_chk
        """
    )
    op.execute(
        f"""
        alter table "{schema}".approval_records
          add constraint approval_records_entity_type_chk
          check (entity_type in ('timesheet_header', 'expense_claim', 'purchase_request', 'approval_target', 'business_object'))
        """
    )
    op.execute(
        f"""
        alter table "{schema}".todos
          drop constraint if exists todos_entity_type_chk
        """
    )
    op.execute(
        f"""
        alter table "{schema}".todos
          add constraint todos_entity_type_chk
          check (entity_type in ('timesheet_header', 'expense_claim', 'purchase_request', 'project', 'approval_target', 'business_object'))
        """
    )
    for table in ("products", "product_skus", "purchase_requests", "purchase_request_items"):
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
    # purchase facts cannot survive without the type in the constraints —
    # downgrading is destructive for them, like the table drops below
    op.execute(f"delete from \"{schema}\".approval_records where entity_type = 'purchase_request'")
    op.execute(f"delete from \"{schema}\".todos where entity_type = 'purchase_request'")
    op.execute(
        f"""
        alter table "{schema}".approval_records
          drop constraint if exists approval_records_entity_type_chk
        """
    )
    op.execute(
        f"""
        alter table "{schema}".approval_records
          add constraint approval_records_entity_type_chk
          check (entity_type in ('timesheet_header', 'expense_claim', 'approval_target', 'business_object'))
        """
    )
    op.execute(
        f"""
        alter table "{schema}".todos
          drop constraint if exists todos_entity_type_chk
        """
    )
    op.execute(
        f"""
        alter table "{schema}".todos
          add constraint todos_entity_type_chk
          check (entity_type in ('timesheet_header', 'expense_claim', 'project', 'approval_target', 'business_object'))
        """
    )
    op.execute(f'drop table if exists "{schema}".purchase_request_items')
    op.execute(f'drop table if exists "{schema}".purchase_requests')
    op.execute(f'drop table if exists "{schema}".product_skus')
    op.execute(f'drop table if exists "{schema}".products')
