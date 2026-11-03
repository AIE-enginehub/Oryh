"""Points redeemed on an order: the discount names the points that paid it

Revision ID: 20261028_0105
Revises: 20261027_0104
Create Date: 2026-10-28 10:00:00

docs/billing-accounts.md, "Redeeming points on an order". Additive only:

* `sales_order_adjustments.billing_account_entry_id` — a `points` discount
  names the `redeemed` entry that paid for it; one live discount per
  redemption (`sales_order_adjustments_redemption_uk`).
* `invoice_items.billing_account_entry_id` — the same discount billed on the
  sales invoice names the same redemption; billing it moves no points.

Points given back name the redemption through the entry's own provenance
pair, as an expiry names its batch, so the ledger needs no new column.
Nothing is backfilled: a points discount recorded before this as a plain
`discount` stays one.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261028_0105"
down_revision = "20261027_0104"
branch_labels = None
depends_on = None

CARRIERS = ("sales_order_adjustments", "invoice_items")


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table in CARRIERS:
        op.execute(
            f'alter table "{schema}".{table} add column if not exists billing_account_entry_id uuid '
            f'references "{schema}".billing_account_entries (id)'
        )
        op.execute(
            f'create index if not exists {table}_billing_account_entry_id_idx '
            f'on "{schema}".{table} (billing_account_entry_id)'
        )
    op.execute(
        f'create unique index if not exists sales_order_adjustments_redemption_uk '
        f'on "{schema}".sales_order_adjustments (tenant_id, billing_account_entry_id) '
        f"where deleted_at is null and billing_account_entry_id is not null"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop index if exists "{schema}".sales_order_adjustments_redemption_uk')
    for table in CARRIERS:
        op.execute(f'alter table "{schema}".{table} drop column if exists billing_account_entry_id')
