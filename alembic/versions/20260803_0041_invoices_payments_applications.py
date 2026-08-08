"""invoices, payments and the 核销 ledger — closing the order-to-cash gap

Revision ID: 20260803_0041
Revises: 20260730_0040
Create Date: 2026-08-03 10:00:00

The document chain used to stop at the orders: nothing recorded that a bill was
raised, that money moved, or which money settled which bill. Four tables close
it, modeled on OFBiz's accounting entities with this codebase's usual folding.

`invoices` keeps BOTH directions in one table, as OFBiz's `Invoice` does with
`invoiceTypeId`. The orders were split because their counterparty, direction and
closure all differ; an invoice fails that test — the closure mechanic (apply
money until nothing is outstanding) is identical on both sides, and splitting
would duplicate the settlement machinery, which is the expensive half.
`direction` is a constrained column rather than a type option because every
guard in the settlement path branches on it.

`payment_applications` is OFBiz's `PaymentApplication`: the 核销 ledger. It is
append-only — no update, no delete, corrections are counter-entries with a
negative amount — the same contract `inventory_item_details` keeps, for the same
reason. Its target is the generic (entity_type, entity_id) pair this codebase
already uses in place of OFBiz's parallel per-source id columns, which is what
lets a payment settle an expense claim as naturally as an invoice.

Settlement progress is deliberately NOT a status: `applied_amount` is a running
sum of the ledger, and outstanding is derived from it. A partly-paid invoice has
no state of its own, exactly as a partly-received purchase order has none.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260803_0041"
down_revision = "20260730_0040"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"

TABLES = ("invoices", "invoice_items", "payments", "payment_applications")


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')

    op.execute(
        f"""
        create table if not exists "{schema}".invoices (
          id uuid primary key,
          tenant_id uuid not null,
          -- this system's document number; the tax document's own number is
          -- tax_invoice_number below and is absent until the invoice exists
          invoice_no varchar(64) not null,
          -- 'sales' = 销项 (we issued it), 'purchase' = 进项 (we received it)
          direction varchar(10) not null,
          invoice_type varchar(30),
          employee_id uuid not null references "{schema}".employees (id),
          customer_id uuid references "{schema}".customers (id),
          vendor_id uuid references "{schema}".vendors (id),
          counterparty_name_snapshot varchar(200),
          title varchar(200) not null,
          invoice_date date,
          due_date date,
          currency varchar(3) not null default 'CNY',
          total_amount numeric(12, 2),
          tax_amount numeric(12, 2),
          applied_amount numeric(12, 2) not null default 0,
          tax_invoice_code varchar(32),
          tax_invoice_number varchar(64),
          extracted_fields_jsonb jsonb not null default '{{}}'::jsonb,
          attachment_id uuid references "{schema}".attachments (id),
          sales_order_id uuid references "{schema}".sales_orders (id),
          purchase_order_id uuid references "{schema}".purchase_orders (id),
          project_id uuid references "{schema}".projects (id),
          status text not null default 'draft',
          submitted_at timestamptz,
          issued_at timestamptz,
          remarks text,
          source_report_text text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz,
          deleted_by varchar(100),
          delete_reason text,
          constraint invoices_invoice_no_uk unique (tenant_id, invoice_no),
          -- the counterparty side must agree with the direction; the API says
          -- so with a message that names the fix, this is the backstop for
          -- imports and direct writes
          constraint invoices_direction_counterparty_ck check (
            (direction = 'sales' and customer_id is not null and vendor_id is null)
            or (direction = 'purchase' and vendor_id is not null and customer_id is null)
          )
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".invoice_items (
          id uuid primary key,
          tenant_id uuid not null,
          invoice_id uuid not null references "{schema}".invoices (id),
          line_no integer,
          -- OFBiz invoiceItemTypeId: 运费/折扣/税/抹零 are line types here,
          -- which is why this family needs no adjustments table
          invoice_item_type varchar(30) not null default 'goods',
          product_id uuid references "{schema}".products (id),
          sku_id uuid references "{schema}".product_skus (id),
          product_name_snapshot varchar(200),
          spec varchar(200),
          -- both optional: a pure charge line (运费 300) has neither
          quantity numeric(12, 2),
          unit varchar(50),
          unit_price numeric(12, 2),
          amount numeric(12, 2),
          tax_rate numeric(5, 2),
          tax_amount numeric(12, 2),
          -- OFBiz OrderItemBilling, collapsed to explicit FKs like the rest of
          -- this codebase's document chains; the anchor of the three-way match
          sales_order_item_id uuid references "{schema}".sales_order_items (id),
          purchase_order_item_id uuid references "{schema}".purchase_order_items (id),
          notes text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".payments (
          id uuid primary key,
          tenant_id uuid not null,
          payment_no varchar(64) not null,
          -- 'inbound' = 收款, 'outbound' = 付款
          direction varchar(10) not null,
          payment_method varchar(30),
          employee_id uuid not null references "{schema}".employees (id),
          customer_id uuid references "{schema}".customers (id),
          vendor_id uuid references "{schema}".vendors (id),
          -- 报销付款: the counterparty is one of our own people
          payee_employee_id uuid references "{schema}".employees (id),
          counterparty_name_snapshot varchar(200),
          payment_date date,
          amount numeric(12, 2) not null,
          currency varchar(3) not null default 'CNY',
          -- amount - applied_amount is 预收款/预付款: the unallocated balance IS
          -- the advance, so no billing-account entity is needed
          applied_amount numeric(12, 2) not null default 0,
          bank_account varchar(200),
          -- the standing check against 改单诈骗 compares this with the vendor's
          -- master record; storing it makes that check auditable afterwards
          counterparty_account varchar(200),
          reference_no varchar(100),
          attachment_id uuid references "{schema}".attachments (id),
          status text not null default 'draft',
          submitted_at timestamptz,
          paid_at timestamptz,
          remarks text,
          source_report_text text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz,
          constraint payments_payment_no_uk unique (tenant_id, payment_no),
          constraint payments_amount_positive_ck check (amount > 0),
          -- exactly one counterparty: a payment to nobody cannot be applied,
          -- and a payment to two parties cannot be reconciled
          constraint payments_single_counterparty_ck check (
            (case when customer_id is null then 0 else 1 end)
            + (case when vendor_id is null then 0 else 1 end)
            + (case when payee_employee_id is null then 0 else 1 end) = 1
          )
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".payment_applications (
          id uuid primary key,
          tenant_id uuid not null,
          payment_id uuid not null references "{schema}".payments (id),
          -- The target, as OFBiz's PaymentApplication names it: one nullable
          -- column per kind, exactly one set. Real foreign keys rather than the
          -- generic (entity_type, entity_id) pair used for ledger provenance
          -- elsewhere, because a settlement IS a document chain and because
          -- money rows are worth database-level referential integrity — a bare
          -- uuid can point at a document that does not exist, and only the API
          -- would ever notice.
          invoice_id uuid references "{schema}".invoices (id),
          -- OFBiz invoiceItemSeqId. Usually absent: in practice money arrives
          -- against an invoice, not against one of its lines.
          invoice_item_id uuid references "{schema}".invoice_items (id),
          expense_claim_id uuid references "{schema}".expense_claims (id),
          -- OFBiz toPaymentId: netting a refund against the receipt it repays
          to_payment_id uuid references "{schema}".payments (id),
          -- signed: negative is the counter-entry that reverses an earlier
          -- application. Rows are never updated or deleted.
          amount_applied numeric(12, 2) not null,
          note varchar(500),
          -- money-writing endpoint, and agents retry: a repeat with the same key
          -- returns what was recorded instead of applying twice
          idempotency_key varchar(64),
          applied_at timestamptz not null default now(),
          created_by varchar(100),
          created_at timestamptz not null default now(),
          -- a row settling nothing is money that vanished; a row settling two
          -- documents cannot be reconciled against either
          constraint payment_applications_single_target_ck check (
            (case when invoice_id is null then 0 else 1 end)
            + (case when expense_claim_id is null then 0 else 1 end)
            + (case when to_payment_id is null then 0 else 1 end) = 1
          ),
          constraint payment_applications_item_needs_invoice_ck check (
            invoice_item_id is null or invoice_id is not null
          )
        )
        """
    )

    for table in TABLES:
        op.execute(f'create index if not exists {table}_tenant_idx on "{schema}".{table} (tenant_id)')
        op.execute(f'alter table "{schema}".{table} enable row level security')
        op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
        op.execute(
            f"""
            create policy tenant_isolation on "{schema}".{table}
              using ({TENANT_MATCH} or {PLATFORM_ON})
              with check ({TENANT_MATCH})
            """
        )

    for statement in (
        # the work queues: open receivables/payables by direction and due date
        f'create index if not exists invoices_direction_status_idx on "{schema}".invoices (tenant_id, direction, status)',
        f'create index if not exists invoices_due_date_idx on "{schema}".invoices (tenant_id, due_date)',
        f'create index if not exists invoices_customer_idx on "{schema}".invoices (customer_id)',
        f'create index if not exists invoices_vendor_idx on "{schema}".invoices (vendor_id)',
        f'create index if not exists invoices_employee_idx on "{schema}".invoices (employee_id)',
        # duplicate-invoice control reads by tax number across live rows
        f'create index if not exists invoices_tax_invoice_number_idx on "{schema}".invoices (tenant_id, tax_invoice_number)',
        f'create index if not exists invoices_sales_order_idx on "{schema}".invoices (sales_order_id)',
        f'create index if not exists invoices_purchase_order_idx on "{schema}".invoices (purchase_order_id)',
        f'create index if not exists invoice_items_invoice_idx on "{schema}".invoice_items (invoice_id)',
        # 已开票数量 per order line — the three-way match reads these
        f'create index if not exists invoice_items_sales_order_item_idx on "{schema}".invoice_items (sales_order_item_id)',
        f'create index if not exists invoice_items_purchase_order_item_idx on "{schema}".invoice_items (purchase_order_item_id)',
        f'create index if not exists payments_direction_status_idx on "{schema}".payments (tenant_id, direction, status)',
        f'create index if not exists payments_payment_date_idx on "{schema}".payments (tenant_id, payment_date)',
        f'create index if not exists payments_customer_idx on "{schema}".payments (customer_id)',
        f'create index if not exists payments_vendor_idx on "{schema}".payments (vendor_id)',
        f'create index if not exists payments_payee_employee_idx on "{schema}".payments (payee_employee_id)',
        f'create index if not exists payments_reference_no_idx on "{schema}".payments (tenant_id, reference_no)',
        f'create index if not exists payment_applications_payment_idx on "{schema}".payment_applications (payment_id)',
        # one index per target column: "what settled this invoice" is the
        # question the detail endpoints and the integrity audit both ask
        f'create index if not exists payment_applications_invoice_idx on "{schema}".payment_applications (invoice_id)',
        f'create index if not exists payment_applications_invoice_item_idx on "{schema}".payment_applications (invoice_item_id)',
        f'create index if not exists payment_applications_expense_claim_idx on "{schema}".payment_applications (expense_claim_id)',
        f'create index if not exists payment_applications_to_payment_idx on "{schema}".payment_applications (to_payment_id)',
        # retry protection for the apply endpoint
        'create unique index if not exists payment_applications_idempotency_uk on '
        f'"{schema}".payment_applications (tenant_id, payment_id, idempotency_key) '
        "where idempotency_key is not null",
    ):
        op.execute(statement)

    # the expense claim becomes settleable: `paid` stays as the flow's marker,
    # but how much actually went out now comes from the payment ledger.
    # Historical `paid` claims predate the ledger and are NOT backfilled — that
    # is a data-migration decision, not a schema one.
    op.execute(
        f'alter table "{schema}".expense_claims '
        "add column if not exists applied_amount numeric(12, 2) not null default 0"
    )

    op.execute(
        f"""
        do $$
        begin
          if exists (select 1 from pg_roles where rolname = 'oryh_app') then
            grant select, insert, update, delete on all tables in schema "{schema}" to oryh_app;
          end if;
        end $$
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".expense_claims drop column if exists applied_amount')
    for table in reversed(TABLES):
        op.execute(f'drop table if exists "{schema}".{table}')
