"""billing accounts: a standing balance, in money or in points

Revision ID: 20260803_0042
Revises: 20260803_0041
Create Date: 2026-08-03 14:00:00

An unapplied payment answers "whose money is this in transit"; it cannot answer
"how much may this customer still charge to us" or "how many points does this
member hold". Both are accounts: a balance in some unit, with a floor, owned by
one party.

OFBiz's `BillingAccount` is the money half of that (accountLimit + a balance
derived from the invoices charged to it). This widens it: `unit_type` puts
loyalty points, stored value and coupon quotas in the same table, because the
mechanics — balance, limit, owner, movements, expiry — are identical and only
the unit differs. OFBiz has no equivalent for the non-money case.

`billing_account_entries` is the append-only ledger the balance is a running sum
of, the third instance of the shape this codebase already uses for stock
(`inventory_item_details`) and for settlement (`payment_applications`).

Two existing tables gain a reference, both of which OFBiz also has:
`invoices.billing_account_id` (an invoice charged to an account) and
`payment_applications.billing_account_id` (money paid into one). The latter
widens that ledger's single-target CHECK from three columns to four.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260803_0042"
down_revision = "20260803_0041"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"

TABLES = ("billing_accounts", "billing_account_entries")


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')

    op.execute(
        f"""
        create table if not exists "{schema}".billing_accounts (
          id uuid primary key,
          tenant_id uuid not null,
          account_code varchar(64) not null,
          name varchar(200) not null,
          -- 'currency' = money (储值/挂账), 'points' = anything else counted.
          -- A constrained column rather than a type option because every guard
          -- in the settlement path branches on it: applying money to a points
          -- account must be unrepresentable.
          unit_type varchar(10) not null,
          -- a currency code when unit_type is 'currency'; a billing_account_unit
          -- vocabulary entry when it is 'points'
          unit varchar(30) not null,
          customer_id uuid references "{schema}".customers (id),
          vendor_id uuid references "{schema}".vendors (id),
          employee_id uuid references "{schema}".employees (id),
          owner_name_snapshot varchar(200),
          -- how far the balance may go NEGATIVE. 0 means no overdraft, which is
          -- what a points account wants.
          credit_limit numeric(14, 2) not null default 0,
          -- running sum of this account's entries; the entries are the truth
          balance numeric(14, 2) not null default 0,
          valid_from date,
          valid_until date,
          status text not null default 'active',
          external_account_id varchar(64),
          description text,
          remarks text,
          source_report_text text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz,
          constraint billing_accounts_code_uk unique (tenant_id, account_code),
          constraint billing_accounts_credit_limit_ck check (credit_limit >= 0),
          constraint billing_accounts_unit_type_ck check (unit_type in ('currency', 'points')),
          -- exactly one owner, as on payments
          constraint billing_accounts_single_owner_ck check (
            (case when customer_id is null then 0 else 1 end)
            + (case when vendor_id is null then 0 else 1 end)
            + (case when employee_id is null then 0 else 1 end) = 1
          )
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".billing_account_entries (
          id uuid primary key,
          tenant_id uuid not null,
          billing_account_id uuid not null references "{schema}".billing_accounts (id),
          -- signed: positive adds, negative spends or reverses. Rows are never
          -- updated or deleted; a mistake is a counter-entry.
          amount numeric(14, 2) not null,
          reason varchar(30) not null,
          description varchar(500),
          -- open-ended provenance, unlike payment_applications' explicit FKs:
          -- what caused this movement can be a payment application, an invoice,
          -- an order, a manual grant, or another entry (an expiry names the
          -- earn entry it expires)
          entity_type varchar(50),
          entity_id uuid,
          -- only meaningful on a points account
          expires_at timestamptz,
          effective_at timestamptz not null default now(),
          idempotency_key varchar(64),
          created_by varchar(100),
          created_at timestamptz not null default now()
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
        f'create index if not exists billing_accounts_unit_type_idx on "{schema}".billing_accounts (tenant_id, unit_type)',
        f'create index if not exists billing_accounts_customer_idx on "{schema}".billing_accounts (customer_id)',
        f'create index if not exists billing_accounts_vendor_idx on "{schema}".billing_accounts (vendor_id)',
        f'create index if not exists billing_accounts_employee_idx on "{schema}".billing_accounts (employee_id)',
        f'create index if not exists billing_accounts_external_idx on "{schema}".billing_accounts (external_account_id)',
        f'create index if not exists billing_account_entries_account_idx on "{schema}".billing_account_entries (billing_account_id)',
        f'create index if not exists billing_account_entries_reason_idx on "{schema}".billing_account_entries (reason)',
        f'create index if not exists billing_account_entries_entity_idx on "{schema}".billing_account_entries (entity_id)',
        # the expiry sweep reads by account and expiry date
        f'create index if not exists billing_account_entries_expiry_idx on "{schema}".billing_account_entries (tenant_id, billing_account_id, expires_at)',
        f'create index if not exists billing_account_entries_source_idx on "{schema}".billing_account_entries (tenant_id, entity_type, entity_id)',
        'create unique index if not exists billing_account_entries_idempotency_uk on '
        f'"{schema}".billing_account_entries (tenant_id, billing_account_id, idempotency_key) '
        "where idempotency_key is not null",
    ):
        op.execute(statement)

    # an invoice may be charged to an account instead of billed on its own
    op.execute(
        f'alter table "{schema}".invoices '
        f'add column if not exists billing_account_id uuid references "{schema}".billing_accounts (id)'
    )
    op.execute(
        f'create index if not exists invoices_billing_account_idx on "{schema}".invoices (billing_account_id)'
    )

    # and a payment may be applied INTO one (OFBiz PaymentApplication.billingAccountId),
    # which widens the ledger's single-target rule from three columns to four
    op.execute(
        f'alter table "{schema}".payment_applications '
        f'add column if not exists billing_account_id uuid references "{schema}".billing_accounts (id)'
    )
    op.execute(
        'create index if not exists payment_applications_billing_account_idx on '
        f'"{schema}".payment_applications (billing_account_id)'
    )
    op.execute(
        f'alter table "{schema}".payment_applications '
        "drop constraint if exists payment_applications_single_target_ck"
    )
    op.execute(
        f"""
        alter table "{schema}".payment_applications
          add constraint payment_applications_single_target_ck check (
            (case when invoice_id is null then 0 else 1 end)
            + (case when expense_claim_id is null then 0 else 1 end)
            + (case when billing_account_id is null then 0 else 1 end)
            + (case when to_payment_id is null then 0 else 1 end) = 1
          )
        """
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
    op.execute(
        f'alter table "{schema}".payment_applications '
        "drop constraint if exists payment_applications_single_target_ck"
    )
    op.execute(
        f'alter table "{schema}".payment_applications drop column if exists billing_account_id'
    )
    op.execute(
        f"""
        alter table "{schema}".payment_applications
          add constraint payment_applications_single_target_ck check (
            (case when invoice_id is null then 0 else 1 end)
            + (case when expense_claim_id is null then 0 else 1 end)
            + (case when to_payment_id is null then 0 else 1 end) = 1
          )
        """
    )
    op.execute(f'alter table "{schema}".invoices drop column if exists billing_account_id')
    for table in reversed(TABLES):
        op.execute(f'drop table if exists "{schema}".{table}')
