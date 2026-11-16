"""The book: chart of accounts, journal entries, accounting periods

Revision ID: 20261108_0108
Revises: 20261101_0107
Create Date: 2026-11-08 10:00:00

Plan docs/plans/accounting-core-2026-11-08.md, phase 1. Additive only:

* `accounting_settings` — one row per workspace: the functional currency.
* `ledger_accounts` — the chart of accounts, a tree. An account with
  sub-accounts is a summary and takes no lines.
* `accounting_periods` — months, open or closed. A row appears the first
  time something posts into the month.
* `journal_entries` / `journal_lines` — balanced debits and credits. A posted
  entry is never edited; a correction is a reversal. One live posting per
  source fact (`journal_entries_source_uk`), one reversal per entry
  (`journal_entries_reversal_uk`).

Nothing is backfilled: no document has been posted before this.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261108_0108"
down_revision = "20261101_0107"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"
TABLES = ("accounting_settings", "ledger_accounts", "accounting_periods", "journal_entries", "journal_lines")


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(
        f"""
        create table if not exists {s}.ledger_accounts (
          id uuid primary key,
          tenant_id uuid not null,
          account_code varchar(32) not null,
          name varchar(200) not null,
          account_type varchar(20) not null,
          parent_id uuid references {s}.ledger_accounts (id),
          subledger varchar(20),
          currency varchar(3),
          status varchar(20) not null default 'active',
          description text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint ledger_accounts_code_uk unique (tenant_id, account_code),
          constraint ledger_accounts_account_type_chk
            check (account_type in ('asset', 'equity', 'expense', 'income', 'liability')),
          constraint ledger_accounts_subledger_chk
            check ((subledger in ('customer', 'employee', 'vendor')) or (subledger is null)),
          constraint ledger_accounts_status_chk check (status in ('active', 'archived')),
          constraint ledger_accounts_not_own_parent_chk check (parent_id is null or parent_id <> id)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists {s}.accounting_settings (
          id uuid primary key,
          tenant_id uuid not null,
          functional_currency varchar(3) not null,
          retained_earnings_account_id uuid references {s}.ledger_accounts (id),
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint accounting_settings_tenant_uk unique (tenant_id)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists {s}.accounting_periods (
          id uuid primary key,
          tenant_id uuid not null,
          period_start date not null,
          period_end date not null,
          status varchar(20) not null default 'open',
          closed_at timestamptz,
          closed_by varchar(200),
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint accounting_periods_start_uk unique (tenant_id, period_start),
          constraint accounting_periods_status_chk check (status in ('closed', 'open')),
          constraint accounting_periods_order_chk check (period_end >= period_start)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists {s}.journal_entries (
          id uuid primary key,
          tenant_id uuid not null,
          entry_no varchar(64) not null,
          posting_date date not null,
          status varchar(20) not null default 'draft',
          description text not null,
          source_type varchar(40),
          source_id uuid,
          source_event varchar(60),
          reverses_entry_id uuid references {s}.journal_entries (id),
          reversed_at timestamptz,
          posted_at timestamptz,
          posted_by varchar(200),
          created_by varchar(200),
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint journal_entries_entry_no_uk unique (tenant_id, entry_no),
          constraint journal_entries_status_chk check (status in ('draft', 'posted')),
          constraint journal_entries_source_pair_chk
            check ((source_type is null and source_id is null and source_event is null) or (source_type is not null and source_id is not null)),
          constraint journal_entries_posted_stamp_chk check (status = 'draft' or posted_at is not null)
        )
        """
    )
    op.execute(
        f"create unique index if not exists journal_entries_source_uk on {s}.journal_entries "
        f"(tenant_id, source_type, source_id, coalesce(source_event, '')) "
        f"where status = 'posted' and reversed_at is null and source_type is not null"
    )
    op.execute(
        f"create unique index if not exists journal_entries_reversal_uk on {s}.journal_entries "
        f"(tenant_id, reverses_entry_id) where reverses_entry_id is not null and deleted_at is null"
    )
    op.execute(
        f"""
        create table if not exists {s}.journal_lines (
          id uuid primary key,
          tenant_id uuid not null,
          entry_id uuid not null references {s}.journal_entries (id),
          line_no integer not null,
          ledger_account_id uuid not null references {s}.ledger_accounts (id),
          debit numeric(14, 2) not null default 0,
          credit numeric(14, 2) not null default 0,
          currency varchar(3),
          foreign_amount numeric(14, 2),
          exchange_rate numeric(18, 8),
          customer_id uuid references {s}.customers (id),
          vendor_id uuid references {s}.vendors (id),
          employee_id uuid references {s}.employees (id),
          cost_center_id uuid references {s}.cost_centers (id),
          project_id uuid references {s}.projects (id),
          description text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint journal_lines_side_chk
            check ((debit > 0 and credit = 0) or (credit > 0 and debit = 0)),
          constraint journal_lines_foreign_chk
            check ((currency is null and foreign_amount is null and exchange_rate is null) or (currency is not null and foreign_amount is not null and exchange_rate > 0))
        )
        """
    )
    indexes = {
        "ledger_accounts": ("tenant_id", "parent_id"),
        "accounting_settings": ("tenant_id",),
        "accounting_periods": ("tenant_id",),
        "journal_entries": ("tenant_id", "posting_date", "reverses_entry_id"),
        "journal_lines": ("tenant_id", "entry_id", "ledger_account_id", "customer_id", "vendor_id",
                          "employee_id", "cost_center_id", "project_id"),
    }
    for table, columns in indexes.items():
        for column in columns:
            op.execute(f"create index if not exists {table}_{column}_idx on {s}.{table} ({column})")
    op.execute(f"create index if not exists journal_entries_source_idx on {s}.journal_entries (source_type, source_id)")
    for table in TABLES:
        op.execute(f"alter table {s}.{table} enable row level security")
        op.execute(f"drop policy if exists tenant_isolation on {s}.{table}")
        op.execute(
            f"""
            create policy tenant_isolation on {s}.{table}
              using ({TENANT_MATCH} or {PLATFORM_ON})
              with check ({TENANT_MATCH})
            """
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table in ("journal_lines", "journal_entries", "accounting_periods", "accounting_settings", "ledger_accounts"):
        op.execute(f'drop table if exists "{schema}".{table}')
