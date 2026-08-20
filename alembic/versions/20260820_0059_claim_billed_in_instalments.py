"""a claim may be billed in instalments; a claim LINE only once

Revision ID: 20260820_0059
Revises: 20260820_0058
Create Date: 2026-08-20 14:00:00

The previous migration made one reimbursement invoice per claim a database
fact, and used that to make raising it idempotent. That is the wrong rule: a
claim is billed the way a purchase order is billed — some lines now, the
disputed ones once they are settled, a second currency on its own document.
One invoice per claim forbids all of it.

So the uniqueness moves down a level, to `invoice_items.expense_item_id`. A
claim may carry any number of invoices; an expense LINE is billed exactly
once. That is the rule worth enforcing in the database, because breaking it
means the employee is reimbursed twice for one taxi — and the thing that
would break it is a retry, the same call arriving again after a timeout.

It is the same shape `InvoiceItem.sales_order_item_id` already has, described
there as OFBiz's `OrderItemBilling` collapsed into an explicit FK and as what
makes 已开票数量 answerable per order line. The question here is the same
question: what on this claim is still unbilled.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision = "20260820_0059"
down_revision = "20260820_0058"
branch_labels = None
depends_on = None

SCHEMA = settings.database_schema


def upgrade() -> None:
    op.drop_index("invoices_expense_claim_uk", "invoices", schema=SCHEMA)
    op.add_column(
        "invoice_items",
        sa.Column("expense_item_id", sa.Uuid(as_uuid=False), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "invoice_items_expense_item_id_fkey",
        "invoice_items", "expense_items",
        ["expense_item_id"], ["id"],
        source_schema=SCHEMA, referent_schema=SCHEMA,
    )
    op.create_index(
        "ix_invoice_items_expense_item_id", "invoice_items", ["expense_item_id"], schema=SCHEMA
    )
    op.create_index(
        "invoice_items_expense_item_uk",
        "invoice_items",
        ["tenant_id", "expense_item_id"],
        unique=True,
        postgresql_where=sa.text("expense_item_id IS NOT NULL AND deleted_at IS NULL"),
        sqlite_where=sa.text("expense_item_id IS NOT NULL AND deleted_at IS NULL"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("invoice_items_expense_item_uk", "invoice_items", schema=SCHEMA)
    op.drop_index("ix_invoice_items_expense_item_id", "invoice_items", schema=SCHEMA)
    op.drop_constraint(
        "invoice_items_expense_item_id_fkey", "invoice_items", type_="foreignkey", schema=SCHEMA
    )
    op.drop_column("invoice_items", "expense_item_id", schema=SCHEMA)
    op.create_index(
        "invoices_expense_claim_uk",
        "invoices",
        ["tenant_id", "expense_claim_id"],
        unique=True,
        postgresql_where=sa.text("expense_claim_id IS NOT NULL AND deleted_at IS NULL"),
        sqlite_where=sa.text("expense_claim_id IS NOT NULL AND deleted_at IS NULL"),
        schema=SCHEMA,
    )
