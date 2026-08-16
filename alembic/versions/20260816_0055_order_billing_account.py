"""orders may be charged to a billing account, occupying its credit at order time

Revision ID: 20260816_0055
Revises: 20260813_0054
Create Date: 2026-08-16 12:00:00

`invoices.billing_account_id` shipped with the accounts themselves and stayed
dead — no API accepted it. Charging starts at the ORDER, not the invoice,
because the gap between the two is where credit needs protecting: an e-commerce
order waits days for stock, a toB order waits months for delivery, and in that
window the same balance must not be spendable twice. The invoice takes the
occupation over when it is issued; these two columns are the order-side half.

Columns only. What "charged" means — the occupation math, the owner and
currency guards, the release-on-cancel paths — lives in the API layer, where it
can be tested; a CHECK cannot see across tables to say whose account this is.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision = "20260816_0055"
down_revision = "20260813_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema
    for table in ("sales_orders", "purchase_orders"):
        op.add_column(
            table,
            sa.Column("billing_account_id", sa.Uuid(as_uuid=False), nullable=True),
            schema=schema,
        )
        op.create_foreign_key(
            f"{table}_billing_account_id_fkey",
            table,
            "billing_accounts",
            ["billing_account_id"],
            ["id"],
            source_schema=schema,
            referent_schema=schema,
        )
        op.create_index(
            f"ix_{table}_billing_account_id",
            table,
            ["billing_account_id"],
            schema=schema,
        )


def downgrade() -> None:
    schema = settings.database_schema
    for table in ("sales_orders", "purchase_orders"):
        op.drop_index(f"ix_{table}_billing_account_id", table_name=table, schema=schema)
        op.drop_constraint(f"{table}_billing_account_id_fkey", table, schema=schema)
        op.drop_column(table, "billing_account_id", schema=schema)
