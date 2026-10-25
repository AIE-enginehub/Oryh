"""A contract's side is stored, not guessed from which counterparty is set

Revision ID: 20261024_0101
Revises: 20261019_0100
Create Date: 2026-10-24 10:00:00

Contract review 2026-10-24, finding 1. The side was `purchase if vendor_id
else sales`, so a contract filed with only a name snapshot — a factory not
yet in master data — was a sales contract: the purchase desk could not file
it, the sales desk read its prices, and nothing could correct it later.

* `contracts.side` (`purchase` / `sales`), backfilled from the counterparty
  exactly as the old derivation read it, so every existing contract keeps
  the side it had and no desk gains or loses one on upgrade.
* `contracts_side_chk` (the two values) and `contracts_side_counterparty_chk`
  (a vendor only on the purchase side, a customer only on the sales side).

The backfill cannot know what a snapshot-only contract really was. Their
count per tenant is printed: those rows read `sales` as before, and a desk
holding both sides corrects one with `PATCH {"side": "purchase"}` (or by
linking its vendor) while it still names no counterparty.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261024_0101"
down_revision = "20261019_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    bind = op.get_bind()
    op.execute(f'alter table "{schema}".contracts add column if not exists side varchar(10)')
    op.execute(
        f'update "{schema}".contracts set side = case when vendor_id is not null '
        f"then 'purchase' else 'sales' end where side is null"
    )
    op.execute(f'alter table "{schema}".contracts alter column side set not null')
    op.execute(f'alter table "{schema}".contracts drop constraint if exists contracts_side_chk')
    op.execute(
        f'alter table "{schema}".contracts add constraint contracts_side_chk '
        f"check (side in ('purchase', 'sales'))"
    )
    op.execute(f'alter table "{schema}".contracts drop constraint if exists contracts_side_counterparty_chk')
    op.execute(
        f'alter table "{schema}".contracts add constraint contracts_side_counterparty_chk '
        f"check ((side = 'purchase' and customer_id is null) or (side = 'sales' and vendor_id is null))"
    )
    rows = bind.exec_driver_sql(f"""
        select t.slug, count(*) from "{schema}".contracts c
          join "{schema}".tenants t on t.id = c.tenant_id
         where c.vendor_id is null and c.customer_id is null and c.deleted_at is null
         group by t.slug order by t.slug
    """).all()
    if rows:
        listed = "; ".join(f"tenant {slug}: {count}" for slug, count in rows)
        print(f"0101: contracts naming no counterparty kept side=sales — review them ({listed})")


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".contracts drop constraint if exists contracts_side_counterparty_chk')
    op.execute(f'alter table "{schema}".contracts drop constraint if exists contracts_side_chk')
    op.execute(f'alter table "{schema}".contracts drop column if exists side')
