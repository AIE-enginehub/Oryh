"""a register line may settle a batch of payments

Revision ID: 20260903_0082
Revises: 20260903_0081
Create Date: 2026-09-03 14:00:00

Payroll leaves the bank as ONE debit for ten payments; a supplier payment
run does the same. `payment_id` links a line to one payment; this column
links it to the batch — the reference_no the payments share, which the
payroll skill already teaches IS the batch, with no batch object. The
server accepts the link only when the members sum to the line exactly.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20260903_0082"
down_revision = "20260903_0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".fin_account_transactions add column if not exists '
        f"payment_reference_no varchar(100)"
    )
    op.execute(
        f'create index if not exists fin_account_transactions_payment_reference_no_idx '
        f'on "{schema}".fin_account_transactions (payment_reference_no)'
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop index if exists "{schema}".fin_account_transactions_payment_reference_no_idx')
    op.execute(f'alter table "{schema}".fin_account_transactions drop column if exists payment_reference_no')
