"""payroll: an effective-dated salary, and the payslip as an invoice

Revision ID: 20260803_0044
Revises: 20260803_0043
Create Date: 2026-08-03 18:00:00

OFBiz keeps an employee's pay in `PayHistory` — effective-dated, so what
someone was paid last March is still answerable next year — and issues the
monthly payslip as an `Invoice` with `invoiceTypeId = PAYROL_INVOICE`, whose
lines carry the salary, the allowances and every deduction. This follows that,
which means the whole payables chain (settlement, ageing, approval, the audit
invariants) is reused rather than rebuilt.

Three things had to give:

`direction` takes a third value. It is OFBiz's `invoiceTypeId` under a name
chosen when only the two money-flow values existed; a payslip's counterparty is
an employee, so `payee_employee_id` joins the counterparty rule and the CHECK
becomes three-way. The column is not renamed: that would touch every guard,
every skill document and the agent-facing contract, which is a lot to pay for a
word.

A payslip covers a period, and 双发工资 is the expensive mistake here — so
`period_start`/`period_end` are real columns and one payslip per person per
period is a partial unique index rather than an agent's care.

`type_options` gains a nullable `sign`. On a payslip the sign IS the meaning: 个税
recorded as +2000 instead of -2000 pays the person 4000 too much. The shipped
payroll vocabulary declares the direction and the write path checks it; a tenant
adding its own deduction type declares its own.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260803_0044"
down_revision = "20260803_0043"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')

    op.execute(
        f"""
        create table if not exists "{schema}".pay_histories (
          id uuid primary key,
          tenant_id uuid not null,
          employee_id uuid not null references "{schema}".employees (id),
          effective_from date not null,
          -- null = still in force; a raise closes this and opens a new row
          effective_thru date,
          amount numeric(14, 2) not null,
          -- month / hour / day / year — what the amount is per
          period_type varchar(20) not null default 'month',
          currency varchar(3) not null default 'CNY',
          notes text,
          created_by varchar(100),
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint pay_histories_amount_ck check (amount >= 0),
          constraint pay_histories_period_ck check (
            effective_thru is null or effective_thru >= effective_from
          )
        )
        """
    )
    for statement in (
        f'create index if not exists pay_histories_tenant_idx on "{schema}".pay_histories (tenant_id)',
        f'create index if not exists pay_histories_employee_idx on "{schema}".pay_histories (employee_id)',
        'create index if not exists pay_histories_employee_from_idx on '
        f'"{schema}".pay_histories (tenant_id, employee_id, effective_from)',
        # one row per employee per start date. Overlapping RANGES are checked in
        # the API and by the integrity audit — a unique index cannot say that.
        'create unique index if not exists pay_histories_employee_from_uk on '
        f'"{schema}".pay_histories (tenant_id, employee_id, effective_from)',
    ):
        op.execute(statement)

    op.execute(f'alter table "{schema}".pay_histories enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".pay_histories')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".pay_histories
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )

    # the payslip's counterparty, and the period it covers
    op.execute(
        f'alter table "{schema}".invoices '
        f'add column if not exists payee_employee_id uuid references "{schema}".employees (id)'
    )
    op.execute(f'alter table "{schema}".invoices add column if not exists period_start date')
    op.execute(f'alter table "{schema}".invoices add column if not exists period_end date')
    op.execute(
        'create index if not exists invoices_payee_employee_idx on '
        f'"{schema}".invoices (payee_employee_id)'
    )
    op.execute(
        'create unique index if not exists invoices_payroll_period_uk on '
        f'"{schema}".invoices (tenant_id, payee_employee_id, period_start) '
        "where direction = 'payroll' and deleted_at is null"
    )
    op.execute(
        f'alter table "{schema}".invoices drop constraint if exists invoices_direction_counterparty_ck'
    )
    op.execute(
        f"""
        alter table "{schema}".invoices
          add constraint invoices_direction_counterparty_ck check (
            (direction = 'sales' and customer_id is not null
              and vendor_id is null and payee_employee_id is null)
            or (direction = 'purchase' and vendor_id is not null
              and customer_id is null and payee_employee_id is null)
            or (direction = 'payroll' and payee_employee_id is not null
              and customer_id is null and vendor_id is null)
          )
        """
    )

    # a payslip's salary line names the salary record it came from
    op.execute(
        f'alter table "{schema}".invoice_items '
        f'add column if not exists pay_history_id uuid references "{schema}".pay_histories (id)'
    )
    op.execute(
        'create index if not exists invoice_items_pay_history_idx on '
        f'"{schema}".invoice_items (pay_history_id)'
    )

    # which way a kind of value moves money; null where the question does not
    # arise, which is every family but payroll today
    op.execute(f'alter table "{schema}".type_options add column if not exists sign integer')

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
    op.execute(f'alter table "{schema}".type_options drop column if exists sign')
    op.execute(f'alter table "{schema}".invoice_items drop column if exists pay_history_id')
    op.execute(f'drop index if exists "{schema}".invoices_payroll_period_uk')
    op.execute(
        f'alter table "{schema}".invoices drop constraint if exists invoices_direction_counterparty_ck'
    )
    op.execute(f'alter table "{schema}".invoices drop column if exists payee_employee_id')
    op.execute(f'alter table "{schema}".invoices drop column if exists period_start')
    op.execute(f'alter table "{schema}".invoices drop column if exists period_end')
    op.execute(
        f"""
        alter table "{schema}".invoices
          add constraint invoices_direction_counterparty_ck check (
            (direction = 'sales' and customer_id is not null and vendor_id is null)
            or (direction = 'purchase' and vendor_id is not null and customer_id is null)
          )
        """
    )
    op.execute(f'drop table if exists "{schema}".pay_histories')
