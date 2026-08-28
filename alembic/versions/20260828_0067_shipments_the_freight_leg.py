"""shipments: the freight leg, OFBiz Shipment/ShipmentItem in agent-native shape

Revision ID: 20260828_0067
Revises: 20260828_0066
Create Date: 2026-08-28 23:00:00

Goods physically moving get their own document: one leg, one `direction` —
outbound (shipping a sales order, sending a purchase return back) or inbound
(receiving a purchase order, a customer return's parcel). The linked order
row rides the same header-level FK pattern the inventory ledger uses, and
because returns live in the order tables, a return's parcel links the RETURN
row through the same column.

ShipmentItem carries `inventory_item_id` — OFBiz's ItemIssuance /
ShipmentReceipt association collapsed to its core: which stock POSITION the
goods leave or land in. The shipment is the freight document, never the
stock truth: /post-stock posts one ledger movement per positioned line,
exactly once (`stock_posted_at` is the idempotence stamp).

Shipments are a document family, so todos and approval facts may point at
them — the two entity-type CHECKs widen accordingly, importing the live
declaration the way 0047 established.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260828_0067"
down_revision = "20260828_0066"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def _quoted(values) -> str:
    return ", ".join(f"'{value}'" for value in sorted(values))


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".shipments (
          id uuid primary key,
          tenant_id uuid not null,
          shipment_no varchar(64) not null,
          direction varchar(20) not null,
          title varchar(200),
          sales_order_id uuid references "{schema}".sales_orders (id),
          purchase_order_id uuid references "{schema}".purchase_orders (id),
          facility varchar(100),
          address varchar(500),
          carrier varchar(100),
          tracking_no varchar(100),
          expected_date date,
          status varchar(30) not null default 'draft',
          shipped_at timestamptz,
          received_at timestamptz,
          stock_posted_at timestamptz,
          remarks text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint shipments_shipment_no_uk unique (tenant_id, shipment_no),
          constraint shipments_direction_chk check (direction in ('inbound', 'outbound')),
          constraint shipments_one_order_side_check
            check (sales_order_id is null or purchase_order_id is null)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".shipment_items (
          id uuid primary key,
          tenant_id uuid not null,
          shipment_id uuid not null references "{schema}".shipments (id),
          line_no integer,
          product_id uuid not null references "{schema}".products (id),
          sku_id uuid references "{schema}".product_skus (id),
          quantity numeric(12, 2) not null,
          inventory_item_id uuid references "{schema}".inventory_items (id),
          description varchar(500),
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        )
        """
    )
    for table in ("shipments", "shipment_items"):
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
    op.execute(
        f'create index if not exists shipments_sales_order_idx '
        f'on "{schema}".shipments (sales_order_id)'
    )
    op.execute(
        f'create index if not exists shipments_purchase_order_idx '
        f'on "{schema}".shipments (purchase_order_id)'
    )
    op.execute(
        f'create index if not exists shipment_items_shipment_idx '
        f'on "{schema}".shipment_items (shipment_id)'
    )
    op.execute(
        f'create index if not exists shipment_items_product_idx '
        f'on "{schema}".shipment_items (product_id)'
    )
    op.execute(
        f'create index if not exists shipment_items_inventory_item_idx '
        f'on "{schema}".shipment_items (inventory_item_id)'
    )

    # Imported here rather than at module scope, the 0047 convention: alembic
    # loads every revision on startup, and a migration that drags the app in
    # at import time makes the whole history hostage to it.
    from app.core.entity_types import APPROVAL_ENTITY_TYPES, TODO_ENTITY_TYPES

    for table, constraint, allowed in (
        ("todos", "todos_entity_type_chk", TODO_ENTITY_TYPES),
        ("approval_records", "approval_records_entity_type_chk", APPROVAL_ENTITY_TYPES),
    ):
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {constraint}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {constraint} '
            f"check (entity_type in ({_quoted(allowed)}))"
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    from app.core.entity_types import APPROVAL_ENTITY_TYPES, TODO_ENTITY_TYPES

    for table, constraint, allowed in (
        ("todos", "todos_entity_type_chk", TODO_ENTITY_TYPES),
        ("approval_records", "approval_records_entity_type_chk", APPROVAL_ENTITY_TYPES),
    ):
        keep = sorted(set(allowed) - {"shipment"})
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {constraint}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {constraint} '
            f"check (entity_type in ({_quoted(keep)}))"
        )
    op.execute(f'drop table if exists "{schema}".shipment_items')
    op.execute(f'drop table if exists "{schema}".shipments')
