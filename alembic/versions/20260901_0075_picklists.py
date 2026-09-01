"""picklists: which product, from which position, how many

Revision ID: 20260901_0075
Revises: 20260901_0074
Create Date: 2026-09-01 14:00:00

OFBiz Picklist/PicklistItem reduced to the agent-native core. Whether a
workspace picks at all is the admin's one sentence where the fulfilment
agents read it — never a stored switch; where picking is the practice, the
run is warehouse work like the shipment (inventory.manage files and
advances, everyone reads). Lines REQUIRE a stock position — that is what a
picking list is for — and the picklist is never the stock truth: stock
moves when the shipment posts, and shipments gain a nullable picklist_id
to say which run they fulfil (copying its lines on create when none are
given). Inventory items gain a nullable facility_id: the registered
pointer beside the free-text identity string, which stays unchanged under
the live ledger. The todo/approval entity CHECKs re-derive so work can
point at a picklist the day the family exists.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings
from app.core.entity_types import APPROVAL_ENTITY_TYPES, TODO_ENTITY_TYPES


revision = "20260901_0075"
down_revision = "20260901_0074"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".picklists (
          id uuid primary key,
          tenant_id uuid not null,
          picklist_no varchar(64) not null,
          sales_order_id uuid references "{schema}".sales_orders (id),
          facility_id uuid references "{schema}".facilities (id),
          status varchar(50) not null default 'draft',
          remarks text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint picklists_picklist_no_uk unique (tenant_id, picklist_no)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".picklist_items (
          id uuid primary key,
          tenant_id uuid not null,
          picklist_id uuid not null references "{schema}".picklists (id),
          line_no integer,
          product_id uuid not null references "{schema}".products (id),
          sku_id uuid references "{schema}".product_skus (id),
          inventory_item_id uuid not null references "{schema}".inventory_items (id),
          quantity numeric(12, 2) not null,
          picked_quantity numeric(12, 2),
          description varchar(500),
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        )
        """
    )
    for table, indexed in (
        ("picklists", ("sales_order_id", "facility_id")),
        ("picklist_items", ("picklist_id", "product_id", "inventory_item_id")),
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
        f'alter table "{schema}".inventory_items add column if not exists '
        f'facility_id uuid references "{schema}".facilities (id)'
    )
    op.execute(
        f'create index if not exists inventory_items_facility_id_idx '
        f'on "{schema}".inventory_items (facility_id)'
    )
    op.execute(
        f'alter table "{schema}".shipments add column if not exists '
        f'picklist_id uuid references "{schema}".picklists (id)'
    )
    op.execute(
        f'create index if not exists shipments_picklist_id_idx '
        f'on "{schema}".shipments (picklist_id)'
    )
    for table, name, allowed in (
        ("todos", "todos_entity_type_chk", TODO_ENTITY_TYPES),
        ("approval_records", "approval_records_entity_type_chk", APPROVAL_ENTITY_TYPES),
    ):
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {name}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {name} '
            f"check (entity_type in ({_quoted(allowed)}))"
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    keep_todo = tuple(t for t in TODO_ENTITY_TYPES if t != "picklist")
    keep_approval = tuple(t for t in APPROVAL_ENTITY_TYPES if t != "picklist")
    for table, name, keep in (
        ("todos", "todos_entity_type_chk", keep_todo),
        ("approval_records", "approval_records_entity_type_chk", keep_approval),
    ):
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {name}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {name} '
            f"check (entity_type in ({_quoted(keep)}))"
        )
    op.execute(f'alter table "{schema}".shipments drop column if exists picklist_id')
    op.execute(f'alter table "{schema}".inventory_items drop column if exists facility_id')
    op.execute(f'drop table if exists "{schema}".picklist_items')
    op.execute(f'drop table if exists "{schema}".picklists')
