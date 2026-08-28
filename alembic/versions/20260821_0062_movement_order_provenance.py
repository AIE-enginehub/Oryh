"""a stock movement names the order it fulfils

Revision ID: 20260821_0062
Revises: 20260820_0061
Create Date: 2026-08-21 12:00:00

Movements come from three worlds and the ledger could only record one of them
well. The generic (entity_type, entity_id) pair holds any in-system record —
but a bare uuid can point at an order that does not exist, and "every movement
this purchase order caused" meant knowing to query by the ITEM type and then
joining lines to headers by hand. And an external order — a workspace that
runs only inventory here, fulfilling Tmall or JD — could not be recorded at
all: `entity_id` is uuid-typed, and "TM2026…" is not a uuid.

So the two closed order chains get real foreign keys (header-level: the pair
keeps the line), and external references get `custom_fields_jsonb`, the
tenant's own fields, where a claim this database cannot check belongs.

The backfill closes the split brain: every existing `purchase_order_item`
movement gets its header FK derived from the line, so "this order's
movements" answers the same for rows written before and after this release.
Sales-side rows do not exist yet — nothing in the codebase issued stock
against a sales order before this.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision = "20260821_0062"
down_revision = "20260820_0061"
branch_labels = None
depends_on = None

SCHEMA = settings.database_schema


def upgrade() -> None:
    op.add_column(
        "inventory_item_details",
        sa.Column("sales_order_id", sa.Uuid(as_uuid=False), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "inventory_item_details",
        sa.Column("purchase_order_id", sa.Uuid(as_uuid=False), nullable=True),
        schema=SCHEMA,
    )
    op.execute(sa.text(
        f'alter table "{SCHEMA}".inventory_item_details '
        "add column if not exists custom_fields_jsonb jsonb not null default '{}'::jsonb"
    ))
    op.create_foreign_key(
        "inventory_item_details_sales_order_id_fkey",
        "inventory_item_details", "sales_orders",
        ["sales_order_id"], ["id"],
        source_schema=SCHEMA, referent_schema=SCHEMA,
    )
    op.create_foreign_key(
        "inventory_item_details_purchase_order_id_fkey",
        "inventory_item_details", "purchase_orders",
        ["purchase_order_id"], ["id"],
        source_schema=SCHEMA, referent_schema=SCHEMA,
    )
    op.create_index("ix_inventory_item_details_sales_order_id",
                    "inventory_item_details", ["sales_order_id"], schema=SCHEMA)
    op.create_index("ix_inventory_item_details_purchase_order_id",
                    "inventory_item_details", ["purchase_order_id"], schema=SCHEMA)

    op.execute(sa.text(
        f'update "{SCHEMA}".inventory_item_details d '
        f'set purchase_order_id = i.po_id '
        f'from "{SCHEMA}".purchase_order_items i '
        f"where d.entity_type = 'purchase_order_item' "
        f'and d.entity_id = i.id and d.purchase_order_id is null'
    ))


def downgrade() -> None:
    op.drop_index("ix_inventory_item_details_purchase_order_id",
                  "inventory_item_details", schema=SCHEMA)
    op.drop_index("ix_inventory_item_details_sales_order_id",
                  "inventory_item_details", schema=SCHEMA)
    op.drop_constraint("inventory_item_details_purchase_order_id_fkey",
                       "inventory_item_details", type_="foreignkey", schema=SCHEMA)
    op.drop_constraint("inventory_item_details_sales_order_id_fkey",
                       "inventory_item_details", type_="foreignkey", schema=SCHEMA)
    op.drop_column("inventory_item_details", "custom_fields_jsonb", schema=SCHEMA)
    op.drop_column("inventory_item_details", "purchase_order_id", schema=SCHEMA)
    op.drop_column("inventory_item_details", "sales_order_id", schema=SCHEMA)
