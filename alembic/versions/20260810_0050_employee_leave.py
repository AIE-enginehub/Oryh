"""请假 is a fact; the balance is not

Revision ID: 20260810_0050
Revises: 20260810_0049
Create Date: 2026-08-10 15:00:00

One table and one column, and the interesting thing about them is what is
missing.

`employee_leaves` is OFBiz's `EmplLeave` with its three compromises undone. It
keys on an id rather than `(partyId, leaveTypeId, fromDate)`, so changing the
dates writes a new record instead of deleting the history; it carries no
`approverPartyId` or `leaveStatus`, because approval goes through
`approval_records` and todos like every other family, which is what buys two
levels, a return with a reason, and a trail; and it drops the reason
classification tree for free text, because the reason for one absence is prose
and nobody queries a taxonomy of it.

**There is no entitlement, allowance, accrual or balance table here, and there
is not going to be one.** How many days somebody has left is not a fact anybody
recorded — it follows from the tenant's leave policy applied to their 工龄 and
their leave rows. Writing it down would freeze a conclusion drawn under rules
that change: revise 年假 mid-year, or backdate a 调休 ratio, and a stored
balance is a pile of numbers that were true under superseded text, correctable
only by reconciling entries. Computed, the same revision just produces
different answers — including for the past, since `policies` is versioned and
`in_force_on` answers what the rule WAS. This is the stance payroll already
takes on tax and quotations take on drift.

Which is also why OFBiz never shipped accrual, twenty years in: the rules are
too local to fix in a schema. Ours are in a document somebody can revise.

`employees.hire_date` is the one fact the computation needs and the roster did
not carry — 工龄 has to be measured from something. Nullable, because an
imported roster may not know it, and a null is an honest "nobody said" that an
agent can ask about rather than a zero it would silently compute against.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

# Verbatim from 0014, where every other tenant table's policy comes from.
# Restated rather than imported because a migration is a historical artifact
# and must not change meaning when a shared constant is edited later.
TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


revision = "20260810_0050"
down_revision = "20260810_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    leaves = f'"{schema}".employee_leaves'

    op.execute(
        f"""
        create table if not exists {leaves} (
            id uuid primary key,
            tenant_id uuid not null references "{schema}".tenants(id),
            employee_id uuid not null references "{schema}".employees(id),
            leave_type text not null,
            from_date date not null,
            thru_date date not null,
            duration_days numeric(6, 2) not null,
            reason text,
            status text not null default 'draft',
            submitted_at timestamptz,
            source_report_text text,
            custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
            deleted_at timestamptz,
            deleted_by text,
            delete_reason text,
            created_at timestamptz not null default now(),
            updated_at timestamptz,
            constraint employee_leaves_period_ck check (thru_date >= from_date),
            constraint employee_leaves_duration_ck check (duration_days > 0)
        )
        """
    )
    op.execute(
        f"create index if not exists employee_leaves_employee_idx "
        f"on {leaves} (tenant_id, employee_id, from_date)"
    )
    op.execute(
        f"create index if not exists employee_leaves_type_idx "
        f"on {leaves} (tenant_id, leave_type, from_date)"
    )
    op.execute(f"create index if not exists employee_leaves_tenant_idx on {leaves} (tenant_id)")

    # RLS on exactly the terms every other tenant table has, name included —
    # a table that opted out, or opted in differently, is the one an audit
    # misses.
    op.execute(f"alter table {leaves} enable row level security")
    op.execute(f"drop policy if exists tenant_isolation on {leaves}")
    op.execute(
        f"""
        create policy tenant_isolation on {leaves}
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )

    op.execute(
        f'alter table "{schema}".employees add column if not exists hire_date date'
    )

    # A new family has to be let INTO the two CHECK constraints that say what a
    # todo and an approval fact may point at. Adding it to the Python tuple is
    # not enough and is dangerously not enough: the model declares these from
    # the same constant, so `create_all` gives every SQLite test database the
    # new value while the migrated Postgres keeps the list frozen at whenever
    # it was last written. The suite goes green and the deployment refuses the
    # first 请假 approval anybody files.
    #
    # 0047 was written because that exact drift hid a 500 for three releases —
    # in the other direction, constraint-only and model-silent. This is the
    # mirror, and the lesson is the same: both copies move together or neither
    # is trustworthy.
    from app.core.entity_types import APPROVAL_ENTITY_TYPES, TODO_ENTITY_TYPES

    def quoted(values: tuple[str, ...]) -> str:
        return ", ".join(f"'{value}'" for value in values)

    for table, constraint, allowed in (
        ("todos", "todos_entity_type_chk", TODO_ENTITY_TYPES),
        ("approval_records", "approval_records_entity_type_chk", APPROVAL_ENTITY_TYPES),
    ):
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {constraint}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {constraint} '
            f"check (entity_type in ({quoted(allowed)}))"
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".employees drop column if exists hire_date')
    op.execute(f'drop table if exists "{schema}".employee_leaves')
