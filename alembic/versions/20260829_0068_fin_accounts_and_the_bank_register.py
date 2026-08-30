"""fin accounts and the bank register: where the money actually sits

Revision ID: 20260829_0068
Revises: 20260828_0067
Create Date: 2026-08-29 10:00:00

OFBiz FinAccount/FinAccountTrans in the agent-native shape. The account's
balance is DERIVED — a running sum of an append-only register with one
write path — and the register row is the bank's fact: no lifecycle, no
edits, corrections are counter-entries (the inventory ledger's discipline
applied to cash, where an absolute balance write would let concurrent
postings silently swallow each other).

Third-party payment reality is in the columns: gross/fee/net per line
(微信/支付宝 charge per transaction; banks leave both null, and the CHECK
holds net = gross − fee whenever both speak), a partial-unique
reference_no per account making statement re-imports idempotent, and the
ledger's three-worlds provenance — payment_id for the closed chain, the
generic entity pair for orders/returns a line explains, custom_fields for
the platform's raw facts.

The sign rules ride as CHECKs because SQLite-backed tests must witness
them too (the varchar(10) lesson): deposits/interest/transfer_in positive,
withdrawals/fees/transfer_out negative, nothing zero.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260829_0068"
down_revision = "20260828_0067"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".fin_accounts (
          id uuid primary key,
          tenant_id uuid not null,
          name varchar(200) not null,
          institution varchar(200),
          account_number varchar(64),
          account_type varchar(50) not null default 'bank',
          currency varchar(3) not null default 'CNY',
          current_balance numeric(14, 2) not null default 0,
          status varchar(20) not null default 'active',
          remarks text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint fin_accounts_tenant_name_uk unique (tenant_id, name),
          constraint fin_accounts_status_chk check (status in ('active', 'archived'))
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".fin_account_transactions (
          id uuid primary key,
          tenant_id uuid not null,
          fin_account_id uuid not null references "{schema}".fin_accounts (id),
          trans_type varchar(20) not null,
          amount numeric(14, 2) not null,
          gross_amount numeric(14, 2),
          fee_amount numeric(14, 2),
          trans_date date,
          counterparty varchar(200),
          description text,
          reference_no varchar(128),
          payment_id uuid references "{schema}".payments (id),
          entity_type varchar(50),
          entity_id uuid,
          created_by varchar(100),
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          constraint fin_account_transactions_trans_type_chk check (trans_type in (
            'adjustment', 'deposit', 'fee', 'interest', 'opening', 'refund',
            'transfer_in', 'transfer_out', 'withdrawal')),
          constraint fin_account_trans_amount_nonzero_ck check (amount <> 0),
          constraint fin_account_trans_sign_ck check (
            (trans_type NOT IN ('deposit', 'interest', 'transfer_in') OR amount > 0)
            AND (trans_type NOT IN ('withdrawal', 'fee', 'transfer_out') OR amount < 0)),
          constraint fin_account_trans_net_ck check (
            gross_amount IS NULL OR fee_amount IS NULL OR amount = gross_amount - fee_amount)
        )
        """
    )
    for table in ("fin_accounts", "fin_account_transactions"):
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
    op.execute(
        f'create index if not exists fin_account_transactions_fin_account_id_idx '
        f'on "{schema}".fin_account_transactions (fin_account_id)'
    )
    op.execute(
        f'create index if not exists fin_account_transactions_payment_id_idx '
        f'on "{schema}".fin_account_transactions (payment_id)'
    )
    op.execute(
        f'create index if not exists fin_account_trans_account_date_idx '
        f'on "{schema}".fin_account_transactions (tenant_id, fin_account_id, trans_date)'
    )
    op.execute(
        f"""
        create unique index if not exists fin_account_trans_reference_uq
          on "{schema}".fin_account_transactions (tenant_id, fin_account_id, reference_no)
          where reference_no IS NOT NULL
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".fin_account_transactions')
    op.execute(f'drop table if exists "{schema}".fin_accounts')
