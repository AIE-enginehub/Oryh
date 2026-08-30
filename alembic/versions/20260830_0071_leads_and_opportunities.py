"""the sales pipeline: leads and opportunities as builtin documents

Revision ID: 20260830_0071
Revises: 20260830_0070
Create Date: 2026-08-30 12:00:00

The pipeline's two halves, both personal documents under one approval-free
grant (crm.own): a LEAD is somebody who might become a customer — captured
before anyone decides they belong in master data, qualified by the
salesperson's own judgment, ended by conversion (the bridge that creates or
names the Customer) or disqualification — and an OPPORTUNITY is a deal
being pursued, usually born from a converted lead, closed won or lost with
`closed_at` stamped by the transition.

Statuses carry no CHECK, like every builtin document: state names are the
tenant's vocabulary and the machine validates them. The entity-type CHECKs
on todos and approval_records are re-derived from the live registry so a
todo may point at a lead the day the family exists.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings
from app.core.entity_types import APPROVAL_ENTITY_TYPES, TODO_ENTITY_TYPES


revision = "20260830_0071"
down_revision = "20260830_0070"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".leads (
          id uuid primary key,
          tenant_id uuid not null,
          lead_no varchar(64) not null,
          company_name varchar(200),
          contact_name varchar(100),
          phone varchar(50),
          wechat varchar(100),
          email varchar(320),
          source varchar(100),
          employee_id uuid not null references "{schema}".employees (id),
          status varchar(50) not null default 'new',
          converted_customer_id uuid references "{schema}".customers (id),
          remarks text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint leads_lead_no_uk unique (tenant_id, lead_no),
          constraint leads_names_somebody_check
            check (company_name is not null or contact_name is not null)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".opportunities (
          id uuid primary key,
          tenant_id uuid not null,
          opportunity_no varchar(64) not null,
          title varchar(200) not null,
          customer_id uuid references "{schema}".customers (id),
          customer_name_snapshot varchar(200),
          lead_id uuid references "{schema}".leads (id),
          employee_id uuid not null references "{schema}".employees (id),
          expected_amount numeric(14, 2),
          currency varchar(3) not null default 'CNY',
          expected_close_date date,
          status varchar(50) not null default 'open',
          closed_at timestamptz,
          remarks text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint opportunities_opportunity_no_uk unique (tenant_id, opportunity_no)
        )
        """
    )
    for table, columns in (
        ("leads", ("tenant_id", "employee_id", "converted_customer_id")),
        ("opportunities", ("tenant_id", "employee_id", "customer_id", "lead_id")),
    ):
        for column in columns:
            op.execute(
                f'create index if not exists {table}_{column}_idx '
                f'on "{schema}".{table} ({column})'
            )
        op.execute(f'alter table "{schema}".{table} enable row level security')
        op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
        op.execute(
            f"""
            create policy tenant_isolation on "{schema}".{table}
              using ({TENANT_MATCH} or {PLATFORM_ON})
              with check ({TENANT_MATCH})
            """
        )
    # a todo or an approval fact may now point at a lead or an opportunity —
    # the CHECKs re-derive from the registry, the 0067 pattern
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
    keep_todo = tuple(t for t in TODO_ENTITY_TYPES if t not in ("lead", "opportunity"))
    keep_approval = tuple(t for t in APPROVAL_ENTITY_TYPES if t not in ("lead", "opportunity"))
    for table, name, keep in (
        ("todos", "todos_entity_type_chk", keep_todo),
        ("approval_records", "approval_records_entity_type_chk", keep_approval),
    ):
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {name}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {name} '
            f"check (entity_type in ({_quoted(keep)}))"
        )
    op.execute(f'drop table if exists "{schema}".opportunities')
    op.execute(f'drop table if exists "{schema}".leads')
