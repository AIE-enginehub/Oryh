"""add sales orders builtin

Revision ID: 20260722_0023
Revises: 20260721_0022
Create Date: 2026-07-22 18:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260722_0023"
down_revision = "20260721_0022"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".sales_orders (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          order_no text not null,
          quotation_id uuid references "{schema}".sales_quotations(id),
          source_quote_number text,
          employee_id uuid not null references "{schema}".employees(id),
          customer_id uuid references "{schema}".customers(id),
          customer_name_snapshot text,
          contact_name text,
          contact_phone text,
          ship_to_address text,
          title text not null,
          project_id uuid references "{schema}".projects(id),
          contract_no text,
          order_date date,
          promised_date date,
          currency text not null default 'CNY',
          payment_terms text,
          delivery_terms text,
          total_amount numeric(12,2),
          status text not null default 'draft',
          submitted_at timestamptz,
          shipped_at timestamptz,
          signed_at timestamptz,
          logistics_company text,
          logistics_tracking_no text,
          remarks text,
          source_report_text text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz,
          deleted_by text,
          delete_reason text,
          constraint sales_orders_order_no_uk unique (tenant_id, order_no),
          constraint sales_orders_total_amount_chk check (total_amount is null or total_amount >= 0)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".sales_order_items (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          order_id uuid not null references "{schema}".sales_orders(id),
          line_no integer,
          product_id uuid references "{schema}".products(id),
          sku_id uuid references "{schema}".product_skus(id),
          product_name_snapshot text,
          spec text,
          quantity numeric(12,2) not null,
          unit text,
          list_price_snapshot numeric(12,2),
          unit_price numeric(12,2),
          amount numeric(12,2),
          tax_rate numeric(5,2),
          is_gift boolean not null default false,
          promised_date date,
          attachment_id uuid references "{schema}".attachments(id),
          notes text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz,
          constraint sales_order_items_quantity_chk check (quantity > 0),
          constraint sales_order_items_list_price_chk check (list_price_snapshot is null or list_price_snapshot >= 0),
          constraint sales_order_items_unit_price_chk check (unit_price is null or unit_price >= 0),
          constraint sales_order_items_amount_chk check (amount is null or amount >= 0),
          constraint sales_order_items_tax_rate_chk check (tax_rate is null or (tax_rate >= 0 and tax_rate <= 100))
        )
        """
    )
    op.execute(
        f"""
        create index if not exists sales_orders_tenant_status_idx
          on "{schema}".sales_orders (tenant_id, status, created_at desc)
        """
    )
    op.execute(
        f"""
        create index if not exists sales_orders_employee_idx
          on "{schema}".sales_orders (employee_id)
        """
    )
    op.execute(
        f"""
        create index if not exists sales_orders_customer_idx
          on "{schema}".sales_orders (customer_id)
        """
    )
    op.execute(
        f"""
        create index if not exists sales_orders_quotation_idx
          on "{schema}".sales_orders (quotation_id)
        """
    )
    op.execute(
        f"""
        create index if not exists sales_order_items_order_idx
          on "{schema}".sales_order_items (order_id)
        """
    )
    # legacy check constraints predate the order builtin: admit sales_order
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
          check (entity_type in ('timesheet_header', 'expense_claim', 'purchase_request', 'sales_quotation', 'sales_order', 'approval_target', 'business_object'))
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
          check (entity_type in ('timesheet_header', 'expense_claim', 'purchase_request', 'sales_quotation', 'sales_order', 'project', 'approval_target', 'business_object'))
        """
    )
    for table in ("sales_orders", "sales_order_items"):
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
    # order facts cannot survive without the type in the constraints —
    # downgrading is destructive for them, like the table drops below
    op.execute(f"delete from \"{schema}\".approval_records where entity_type = 'sales_order'")
    op.execute(f"delete from \"{schema}\".todos where entity_type = 'sales_order'")
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
          check (entity_type in ('timesheet_header', 'expense_claim', 'purchase_request', 'sales_quotation', 'approval_target', 'business_object'))
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
          check (entity_type in ('timesheet_header', 'expense_claim', 'purchase_request', 'sales_quotation', 'project', 'approval_target', 'business_object'))
        """
    )
    op.execute(f'drop table if exists "{schema}".sales_order_items')
    op.execute(f'drop table if exists "{schema}".sales_orders')
