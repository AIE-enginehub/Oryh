"""按单采购: a purchase line may pin to the sales order line it fulfils

Revision ID: 20260726_0031
Revises: 20260726_0030
Create Date: 2026-07-26 15:00:00

Zero-inventory tenants procure to order: a confirmed sales order line drives
a purchase request line. The link lives on the PURCHASE side because the
sales order is already confirmed — and therefore locked — by the time
procurement files the request; several purchase lines may point at one sales
line (split across vendors or deliveries). Null = an ordinary stock purchase.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260726_0031"
down_revision = "20260726_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        alter table "{schema}".purchase_request_items
        add column if not exists sales_order_item_id uuid
          references "{schema}".sales_order_items (id)
        """
    )
    op.execute(
        f"""
        create index if not exists purchase_request_items_sales_order_item_idx
          on "{schema}".purchase_request_items (sales_order_item_id)
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".purchase_request_items drop column if exists sales_order_item_id'
    )
