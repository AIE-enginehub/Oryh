"""Cash accounts: which ledger accounts hold the money the cash summary follows

Revision ID: 20261127_0117
Revises: 20261126_0116
Create Date: 2026-11-27 09:00:00

Plan docs/plans/financial-statements-2026-11-25.md, phase 3 (Q1: a flag,
not a link to fin_accounts — a petty cash box has no bank feed). The person
marks bank and cash accounts; the cash summary reads money into and out of
them, grouped by the other side of each entry. Only an asset holds cash.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261127_0117"
down_revision = "20261126_0116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(f"alter table {s}.ledger_accounts add column if not exists is_cash boolean not null default false")
    op.execute(f"alter table {s}.ledger_accounts drop constraint if exists ledger_accounts_cash_asset_chk")
    op.execute(
        f"alter table {s}.ledger_accounts add constraint ledger_accounts_cash_asset_chk "
        f"check ((is_cash = false) OR (account_type = 'asset'))"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(f"alter table {s}.ledger_accounts drop constraint if exists ledger_accounts_cash_asset_chk")
    op.execute(f"alter table {s}.ledger_accounts drop column if exists is_cash")
