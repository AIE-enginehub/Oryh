"""Credit and debit notes: an invoice that corrects another, and names it

Revision ID: 20261109_0109
Revises: 20261108_0108
Create Date: 2026-11-09 10:00:00

Plan docs/plans/accounting-core-2026-11-08.md, phase 2. Additive only:

* `invoices.invoice_kind` — `invoice` (every existing row), `credit_note`,
  `debit_note`; and `original_invoice_id`, the invoice a note corrects,
  required on a note and absent on an invoice
  (`invoices_note_original_chk`).
* `invoice_items.original_invoice_item_id` — the line a note's line corrects.
* `invoice_offsets` — a credit note applied against an open invoice of the
  same party. Immutable, like payment applications: a mistake is a
  counter-row with a negative amount.

A credit note's lines keep the sign they carry today (negative for what is
given back), so every sum that already nets invoice lines nets notes too.
Existing negative invoices stay `invoice`: nothing is backfilled.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261109_0109"
down_revision = "20261108_0108"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(f"alter table {s}.invoices add column if not exists invoice_kind varchar(20) not null default 'invoice'")
    op.execute(f"alter table {s}.invoices add column if not exists original_invoice_id uuid references {s}.invoices (id)")
    op.execute(
        f"alter table {s}.invoices add constraint invoices_invoice_kind_chk "
        f"check (invoice_kind in ('credit_note', 'debit_note', 'invoice'))"
    )
    op.execute(
        f"alter table {s}.invoices add constraint invoices_note_original_chk "
        f"check ((invoice_kind = 'invoice' and original_invoice_id is null) "
        f"or (invoice_kind <> 'invoice' and original_invoice_id is not null))"
    )
    op.execute(f"create index if not exists invoices_original_invoice_id_idx on {s}.invoices (original_invoice_id)")
    op.execute(
        f"alter table {s}.invoice_items add column if not exists original_invoice_item_id uuid "
        f"references {s}.invoice_items (id)"
    )
    op.execute(
        f"create index if not exists invoice_items_original_invoice_item_id_idx "
        f"on {s}.invoice_items (original_invoice_item_id)"
    )
    op.execute(
        f"""
        create table if not exists {s}.invoice_offsets (
          id uuid primary key,
          tenant_id uuid not null,
          credit_note_id uuid not null references {s}.invoices (id),
          invoice_id uuid not null references {s}.invoices (id),
          amount numeric(14, 2) not null,
          note text,
          created_by varchar(200),
          created_at timestamptz not null default now(),
          constraint invoice_offsets_amount_chk check (amount <> 0),
          constraint invoice_offsets_distinct_chk check (credit_note_id <> invoice_id)
        )
        """
    )
    for column in ("tenant_id", "credit_note_id", "invoice_id"):
        op.execute(f"create index if not exists invoice_offsets_{column}_idx on {s}.invoice_offsets ({column})")
    op.execute(f"alter table {s}.invoice_offsets enable row level security")
    op.execute(f"drop policy if exists tenant_isolation on {s}.invoice_offsets")
    op.execute(
        f"""
        create policy tenant_isolation on {s}.invoice_offsets
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(f"drop table if exists {s}.invoice_offsets")
    op.execute(f"alter table {s}.invoice_items drop column if exists original_invoice_item_id")
    op.execute(f"alter table {s}.invoices drop constraint if exists invoices_note_original_chk")
    op.execute(f"alter table {s}.invoices drop constraint if exists invoices_invoice_kind_chk")
    op.execute(f"alter table {s}.invoices drop column if exists original_invoice_id")
    op.execute(f"alter table {s}.invoices drop column if exists invoice_kind")
