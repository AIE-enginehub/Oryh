"""an idempotency key names a call, not a row

Revision ID: 20260803_0043
Revises: 20260803_0042
Create Date: 2026-08-03 16:00:00

Both money ledgers accept several lines in one call and stamp the caller's
idempotency key on every row they write. Their partial unique indexes, however,
were on `(tenant, parent, idempotency_key)` — per ROW. So any call that carried
a key AND more than one line collided with itself on the second row and 500'd.

The unit tests missed it because they only ever combined a key with a single
line; the Postgres black-box regression caught it on a two-line points grant.

The fix is to make the row's position in the call part of the uniqueness. The
index still refuses a genuinely duplicated call — the concurrent retry it exists
for — while a multi-line call writes its rows as 0, 1, 2…
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260803_0043"
down_revision = "20260803_0042"
branch_labels = None
depends_on = None

# table -> the parent column its idempotency scope hangs off
LEDGERS = {
    "payment_applications": "payment_id",
    "billing_account_entries": "billing_account_id",
}


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table, parent in LEDGERS.items():
        op.execute(
            f'alter table "{schema}".{table} add column if not exists idempotency_seq integer'
        )
        # rows written before this migration were single-line calls by
        # definition — a multi-line one could not have been stored
        op.execute(
            f'update "{schema}".{table} set idempotency_seq = 0 '
            "where idempotency_key is not null and idempotency_seq is null"
        )
        op.execute(f'drop index if exists "{schema}".{table}_idempotency_uk')
        op.execute(
            f'create unique index if not exists {table}_idempotency_uk on '
            f'"{schema}".{table} (tenant_id, {parent}, idempotency_key, idempotency_seq) '
            "where idempotency_key is not null"
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table, parent in LEDGERS.items():
        op.execute(f'drop index if exists "{schema}".{table}_idempotency_uk')
        op.execute(
            f'create unique index if not exists {table}_idempotency_uk on '
            f'"{schema}".{table} (tenant_id, {parent}, idempotency_key) '
            "where idempotency_key is not null"
        )
        op.execute(f'alter table "{schema}".{table} drop column if exists idempotency_seq')
