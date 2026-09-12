"""an order names the order it replaces

Revision ID: 20260909_0087
Revises: 20260906_0086
Create Date: 2026-09-09 14:00:00

A confirmed channel order the warehouse cannot ship as written is past its
machine's editable states. The tenant's answer was "cancel it and raise a
new one" — and the new one had nowhere to say which order it replaced, so
the link lived in a remark, if anywhere. `supersedes_order_id` is that link
as a fact: `POST /sales-orders/{id}/revise` copies the order into a fresh
draft naming its source and moves the source to the machine's cancelled
state in the same transaction. Orders only — a return is reversed, never
revised — held by a check constraint like the one on `original_order_id`.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20260909_0087"
down_revision = "20260906_0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".sales_orders '
        f'add column if not exists supersedes_order_id uuid references "{schema}".sales_orders (id)'
    )
    op.execute(
        f"create index if not exists sales_orders_supersedes_order_idx "
        f'on "{schema}".sales_orders (supersedes_order_id)'
    )
    op.execute(
        f'alter table "{schema}".sales_orders '
        f"drop constraint if exists sales_orders_supersedes_only_on_orders_check"
    )
    op.execute(
        f'alter table "{schema}".sales_orders '
        f"add constraint sales_orders_supersedes_only_on_orders_check "
        "check (order_kind = 'order' or supersedes_order_id is null)"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".sales_orders '
        f"drop constraint if exists sales_orders_supersedes_only_on_orders_check"
    )
    op.execute(f'drop index if exists "{schema}".sales_orders_supersedes_order_idx')
    op.execute(f'alter table "{schema}".sales_orders drop column if exists supersedes_order_id')
