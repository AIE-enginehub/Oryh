"""Budgets: the plan ledger, its change documents, and links from spending

Revision ID: 20261027_0102
Revises: 20261024_0101
Create Date: 2026-10-27 12:00:00

Plan docs/plans/budgets-2026-10-27.md, phase 1. Additive only:

* `budgets` — the header: direction (spend / income), period, currency.
* `budget_lines` — what a budget is divided into; a line of a collecting
  category (`labour`, `marketing`, `sales`) gathers its documents by rule,
  one active collector per category per budget (`budget_lines_collector_uk`).
* `budget_changes` and `budget_change_lines` — every change to the plan is a
  document with its reason.
* `budget_entries` — the plan ledger, appended when a change posts, never
  updated; a change line posts once (`budget_entries_change_line_uk`).
* `budget_line_id` on purchase request, purchase order, invoice and expense
  items — the explicit tag for spend no collection rule reaches.
* The entity-type CHECKs on todos and approval_records re-derive from the
  registry, so a todo or an approval may point at a budget or a change.

Consumption is derived from the existing documents and stored nowhere, so
there is nothing to backfill.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings
from app.core.entity_types import APPROVAL_ENTITY_TYPES, TODO_ENTITY_TYPES

revision = "20261027_0102"
down_revision = "20261024_0101"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"
NEW_TABLES = ("budgets", "budget_lines", "budget_changes", "budget_change_lines", "budget_entries")
TAGGED_ITEMS = ("purchase_request_items", "purchase_order_items", "invoice_items", "expense_items")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _isolate(schema: str, table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.execute(f'create index if not exists {table}_{column}_idx on "{schema}".{table} ({column})')
    op.execute(f'alter table "{schema}".{table} enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".{table}
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".budgets (
          id uuid primary key,
          tenant_id uuid not null,
          budget_no varchar(64) not null,
          name varchar(200) not null,
          direction varchar(10) not null default 'spend',
          budget_type varchar(50) not null default 'operating',
          currency varchar(3) not null default 'CNY',
          period_start date not null,
          period_end date not null,
          owner_employee_id uuid references "{schema}".employees (id),
          status varchar(50) not null default 'draft',
          activated_at timestamptz,
          closed_at timestamptz,
          description text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint budgets_budget_no_uk unique (tenant_id, budget_no),
          constraint budgets_direction_chk check (direction in ('income', 'spend')),
          constraint budgets_period_chk check (period_end >= period_start)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".budget_lines (
          id uuid primary key,
          tenant_id uuid not null,
          budget_id uuid not null references "{schema}".budgets (id),
          line_code varchar(64) not null,
          name varchar(200) not null,
          category varchar(50) not null default 'other',
          owner_employee_id uuid references "{schema}".employees (id),
          status varchar(20) not null default 'active',
          sort_order integer,
          description text,
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint budget_lines_code_uk unique (tenant_id, budget_id, line_code),
          constraint budget_lines_status_chk check (status in ('active', 'closed'))
        )
        """
    )
    op.execute(
        f'create unique index if not exists budget_lines_collector_uk on "{schema}".budget_lines '
        f"(tenant_id, budget_id, category) "
        f"where status = 'active' and category in ('labour', 'marketing', 'sales')"
    )
    op.execute(
        f"""
        create table if not exists "{schema}".budget_changes (
          id uuid primary key,
          tenant_id uuid not null,
          change_no varchar(64) not null,
          budget_id uuid not null references "{schema}".budgets (id),
          change_type varchar(50) not null default 'original',
          employee_id uuid not null references "{schema}".employees (id),
          reason text not null,
          status varchar(50) not null default 'draft',
          submitted_at timestamptz,
          posted_at timestamptz,
          posted_by varchar(100),
          source_budget_id uuid references "{schema}".budgets (id),
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint budget_changes_change_no_uk unique (tenant_id, change_no)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".budget_change_lines (
          id uuid primary key,
          tenant_id uuid not null,
          change_id uuid not null references "{schema}".budget_changes (id),
          line_no integer,
          budget_line_id uuid not null references "{schema}".budget_lines (id),
          period_month date not null,
          amount numeric(14, 2) not null,
          note text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint budget_change_lines_amount_chk check (amount <> 0)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".budget_entries (
          id uuid primary key,
          tenant_id uuid not null,
          budget_id uuid not null references "{schema}".budgets (id),
          budget_line_id uuid not null references "{schema}".budget_lines (id),
          change_id uuid not null references "{schema}".budget_changes (id),
          change_line_id uuid not null references "{schema}".budget_change_lines (id),
          entry_type varchar(20) not null,
          period_month date not null,
          amount numeric(14, 2) not null,
          created_by varchar(100),
          created_at timestamptz not null default now(),
          constraint budget_entries_change_line_uk unique (tenant_id, change_line_id),
          constraint budget_entries_entry_type_chk check (entry_type in (
            'carry_forward_in', 'carry_forward_out', 'decrease', 'increase', 'original',
            'transfer_in', 'transfer_out')),
          constraint budget_entries_sign_chk check (
            (entry_type in ('original', 'increase', 'transfer_in', 'carry_forward_in') and amount > 0)
            or (entry_type in ('decrease', 'transfer_out', 'carry_forward_out') and amount < 0))
        )
        """
    )
    op.execute(
        f'create index if not exists budget_entries_line_month_idx on "{schema}".budget_entries '
        f"(tenant_id, budget_line_id, period_month)"
    )
    for table, columns in (
        ("budgets", ("tenant_id", "owner_employee_id")),
        ("budget_lines", ("tenant_id", "budget_id", "owner_employee_id")),
        ("budget_changes", ("tenant_id", "budget_id", "employee_id", "source_budget_id")),
        ("budget_change_lines", ("tenant_id", "change_id", "budget_line_id")),
        ("budget_entries", ("tenant_id", "budget_id", "budget_line_id", "change_id")),
    ):
        _isolate(schema, table, columns)

    for table in TAGGED_ITEMS:
        op.execute(
            f'alter table "{schema}".{table} '
            f'add column if not exists budget_line_id uuid references "{schema}".budget_lines (id)'
        )
        op.execute(
            f'create index if not exists {table}_budget_line_id_idx on "{schema}".{table} (budget_line_id)'
        )

    # a todo or an approval fact may now point at a budget or a change
    for table, name, allowed in (
        ("todos", "todos_entity_type_chk", TODO_ENTITY_TYPES),
        ("approval_records", "approval_records_entity_type_chk", APPROVAL_ENTITY_TYPES),
    ):
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {name}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {name} '
            f"check (entity_type in ({_quoted(allowed)}))"
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table in TAGGED_ITEMS:
        op.execute(f'alter table "{schema}".{table} drop column if exists budget_line_id')
    for table in reversed(NEW_TABLES):
        op.execute(f'drop table if exists "{schema}".{table}')
    without = ("budget", "budget_change")
    for table, name, allowed in (
        ("todos", "todos_entity_type_chk", TODO_ENTITY_TYPES),
        ("approval_records", "approval_records_entity_type_chk", APPROVAL_ENTITY_TYPES),
    ):
        kept = tuple(value for value in allowed if value not in without)
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {name}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {name} '
            f"check (entity_type in ({_quoted(kept)}))"
        )
