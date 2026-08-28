"""returns live in the order tables: order_kind splits them, kind picks the machine

Revision ID: 20260828_0066
Revises: 20260828_0065
Create Date: 2026-08-28 20:00:00

A sales return and a purchase return are rows in `sales_orders` and
`purchase_orders` (退单跟订单一张表 — the deciding requirement), not tables of
their own. `order_kind` ('order' | 'return') is the split; `original_order_id`
is the self-referential link a return carries to the order it reverses, and
one order carrying MANY returns is simply many rows naming the same original.
Nullable, because reality outruns paperwork — the parcel arrives before anyone
matches it — and the API refuses an original that is itself a return.

Two CHECKs hold the shape: the kind vocabulary is closed, and only returns may
carry an original. What the row's kind buys is the LIFECYCLE: a return runs
the e-commerce-shaped sales_return / purchase_return machine (申请 → 发出 →
收到 → 验货入库 → 退款) seeded alongside this migration by
sync_tenant_defaults, while orders keep theirs. Every existing row backfills
to order_kind='order' via the column default — which is exactly what every
row written before this migration was.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260828_0066"
down_revision = "20260828_0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table in ("sales_orders", "purchase_orders"):
        op.execute(
            f'alter table "{schema}".{table} '
            "add column if not exists order_kind varchar(20) not null default 'order'"
        )
        op.execute(
            f'alter table "{schema}".{table} '
            f'add column if not exists original_order_id uuid references "{schema}".{table} (id)'
        )
        op.execute(
            f'create index if not exists {table}_original_order_idx '
            f'on "{schema}".{table} (original_order_id)'
        )
        op.execute(
            f'alter table "{schema}".{table} '
            f"drop constraint if exists {table}_order_kind_chk"
        )
        op.execute(
            f'alter table "{schema}".{table} '
            f"add constraint {table}_order_kind_chk "
            "check (order_kind in ('order', 'return'))"
        )
        op.execute(
            f'alter table "{schema}".{table} '
            f"drop constraint if exists {table}_original_only_on_returns_check"
        )
        op.execute(
            f'alter table "{schema}".{table} '
            f"add constraint {table}_original_only_on_returns_check "
            "check (order_kind = 'return' or original_order_id is null)"
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table in ("sales_orders", "purchase_orders"):
        op.execute(
            f'alter table "{schema}".{table} '
            f"drop constraint if exists {table}_original_only_on_returns_check"
        )
        op.execute(
            f'alter table "{schema}".{table} drop constraint if exists {table}_order_kind_chk'
        )
        op.execute(f'drop index if exists "{schema}".{table}_original_order_idx')
        op.execute(f'alter table "{schema}".{table} drop column if exists original_order_id')
        op.execute(f'alter table "{schema}".{table} drop column if exists order_kind')
