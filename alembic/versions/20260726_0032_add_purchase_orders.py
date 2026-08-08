"""purchase orders — the commitment to a vendor, split from the sales side

Revision ID: 20260726_0032
Revises: 20260726_0031
Create Date: 2026-07-26 18:00:00

Where OFBiz shares one OrderHeader between sales and purchase, oryh splits:
the counterparty (vendor, required), the direction (receiving, not shipping)
and the closure (goods into the inventory ledger) all differ. Three tables
mirror the sales-order trio — header, items (with received_quantity and the
按单采购 link to purchase_request_items), and signed adjustments.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260726_0032"
down_revision = "20260726_0031"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".purchase_orders (
          id uuid primary key,
          tenant_id uuid not null,
          po_number varchar(64) not null,
          vendor_id uuid not null references "{schema}".vendors (id),
          vendor_name_snapshot varchar(200),
          employee_id uuid not null references "{schema}".employees (id),
          title varchar(200),
          contract_no varchar(64),
          order_date date,
          promised_date date,
          currency varchar(3) not null default 'CNY',
          payment_terms text,
          delivery_terms text,
          total_amount numeric(12, 2),
          status text not null default 'draft',
          remarks text,
          source_report_text text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz,
          constraint purchase_orders_po_number_uk unique (tenant_id, po_number)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".purchase_order_items (
          id uuid primary key,
          tenant_id uuid not null,
          po_id uuid not null references "{schema}".purchase_orders (id),
          line_no integer,
          product_id uuid references "{schema}".products (id),
          sku_id uuid references "{schema}".product_skus (id),
          product_name_snapshot varchar(200),
          spec varchar(200),
          quantity numeric(12, 2) not null,
          unit varchar(50),
          unit_price numeric(12, 2),
          amount numeric(12, 2),
          tax_rate numeric(5, 2),
          promised_date date,
          purchase_request_item_id uuid references "{schema}".purchase_request_items (id),
          received_quantity numeric(12, 2) not null default 0,
          attachment_id uuid references "{schema}".attachments (id),
          notes text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".purchase_order_adjustments (
          id uuid primary key,
          tenant_id uuid not null,
          po_id uuid not null references "{schema}".purchase_orders (id),
          po_item_id uuid references "{schema}".purchase_order_items (id),
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
    for table in ("purchase_orders", "purchase_order_items", "purchase_order_adjustments"):
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
    op.execute(f'create index if not exists purchase_orders_vendor_idx on "{schema}".purchase_orders (vendor_id)')
    op.execute(f'create index if not exists purchase_orders_employee_idx on "{schema}".purchase_orders (employee_id)')
    op.execute(f'create index if not exists purchase_order_items_po_idx on "{schema}".purchase_order_items (po_id)')
    op.execute(
        f'create index if not exists purchase_order_items_request_item_idx on "{schema}".purchase_order_items (purchase_request_item_id)'
    )
    op.execute(f'create index if not exists purchase_order_adjustments_po_idx on "{schema}".purchase_order_adjustments (po_id)')
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
    for table in ("purchase_order_adjustments", "purchase_order_items", "purchase_orders"):
        op.execute(f'drop table if exists "{schema}".{table}')
