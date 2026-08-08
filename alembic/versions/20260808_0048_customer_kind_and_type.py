"""a customer book holds retail and B2B at once, on one table

Revision ID: 20260808_0048
Revises: 20260804_0047
Create Date: 2026-08-08 12:00:00

`customers` had no way to say what kind of customer a row was. That reads as a
missing field and is really a missing decision: the alternative on the table was
a second table (retail_customers) or a full OFBiz Party layer, and both were
refused for the same reason — a 会员 and a 集团客户 differ in what their FILE
holds, never in what happens to them. Quotation, order, invoice, settlement and
standing balance are identical on both sides, which is the test `Invoice`
passes and the orders fail. Splitting would have duplicated the settlement half
and taken the counterparty count on payments, invoices and billing accounts
from three to four, which is how a Party layer arrives by the back door.

So two columns on two different axes, and the difference between them is the
point:

`customer_kind` is CLOSED — 'person' or 'company', OFBiz's Person/PartyGroup
distinction with the Party table not built. A constrained column rather than a
type option because the distinction is universal rather than the tenant's to
extend; that closure is what would let a constraint branch on it later (a phone
unique per person), and it is the discriminator a Party layer would need
unchanged if one is ever built.

`customer_type` is OPEN — 零售/批发/经销/电商/政企, the tenant's own segmentation,
validated against the `customer_type` type-option family that ships with this
revision and seeds into existing workspaces on the next catalog refresh.

Neither gates anything, and that is deliberate. Whether a 经销商 gets a price
break or a member has to prepay is a judgment, and judgments live in agents and
workflow definitions.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260808_0048"
down_revision = "20260804_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".customers'

    # `text`, matching every other string column on this table. The ORM's
    # String(n) is the request-shape bound; what actually guards these two is
    # the CHECK below for the closed axis and the type-option vocabulary for the
    # open one, so a varchar length would add a third answer and no safety.
    op.execute(f"alter table {table} add column if not exists customer_kind text")
    op.execute(f"alter table {table} add column if not exists customer_type text")

    op.execute(f"alter table {table} drop constraint if exists customers_kind_ck")
    op.execute(
        f"alter table {table} add constraint customers_kind_ck "
        "check (customer_kind is null or customer_kind in ('person', 'company'))"
    )

    # Backfill only where the evidence is unambiguous. A 统一社会信用代码 on the
    # record means this customer is filed as an organization — for invoicing
    # purposes that is what the number IS, not an inference from it. Every other
    # row stays null rather than being guessed into 'company': null says nobody
    # has stated a kind, which is true, and an agent can ask. A wrong stated
    # fact is worse than an absent one, and ten thousand rows silently asserting
    # 'company' is exactly the kind of derived truth this codebase refuses.
    op.execute(
        f"update {table} set customer_kind = 'company' "
        "where tax_id is not null and customer_kind is null"
    )

    # The retail lookup is by phone and the retail case is the one where this
    # table gets long. Not unique on purpose: a shared household number is an
    # ordinary fact, and a duplicate member record costs a merge, not money.
    op.execute(
        f"create index if not exists customers_tenant_phone_idx on {table} (tenant_id, phone)"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".customers'

    op.execute(f'drop index if exists "{schema}".customers_tenant_phone_idx')
    op.execute(f"alter table {table} drop constraint if exists customers_kind_ck")
    op.execute(f"alter table {table} drop column if exists customer_type")
    op.execute(f"alter table {table} drop column if exists customer_kind")
