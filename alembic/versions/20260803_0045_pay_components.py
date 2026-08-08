"""a pay history holds every term of someone's pay, not only the salary

Revision ID: 20260803_0045
Revises: 20260803_0044
Create Date: 2026-08-03 20:00:00

A commission rate and a bonus arrangement are facts about a particular person,
exactly as their salary is, and they change over time the same way. They were
going to land in a tenant-defined business object — until the reason not to
became clear: business-object reads are not gated, and somebody's commission
rate is as confidential as their salary. Everything in `pay_histories` sits
behind `payroll.read` already.

So a row now states one COMPONENT of someone's pay, in whichever of three
shapes fits: a scalar `amount` (12000 a month), a proportional `rate` with the
`basis` it applies to (3% of collections), or a `formula` in words for the
arrangements that fit neither (阶梯提成, 绩效系数). The formula is text for the
agent to read; the server never parses it, exactly as it never parses a workflow
definition.

Two consequences for the constraints: the unique key gains the component, since
a salary and a commission legitimately start on the same day, and `amount`
stops being required — a commission row has a rate instead.

National policy (五险一金 rates) is deliberately absent: it is public knowledge
the agent already has, and what it produced is recorded on the payslip line
itself. What IS a fact about the person — their contribution base — goes in this
table's `custom_fields`, where it inherits the effective dating for free.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260803_0045"
down_revision = "20260803_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".pay_histories'

    op.execute(f"alter table {table} add column if not exists component varchar(30)")
    op.execute("update " + table + " set component = 'base_salary' where component is null")
    op.execute(f"alter table {table} alter column component set default 'base_salary'")
    op.execute(f"alter table {table} alter column component set not null")

    op.execute(f"alter table {table} add column if not exists rate numeric(9, 6)")
    op.execute(f"alter table {table} add column if not exists basis varchar(200)")
    op.execute(f"alter table {table} add column if not exists formula text")

    # a commission row states a rate, not an amount
    op.execute(f"alter table {table} alter column amount drop not null")

    for name, expression in (
        ("pay_histories_amount_ck", "amount is null or amount >= 0"),
        ("pay_histories_rate_ck", "rate is null or rate >= 0"),
        # a term that states nothing is not a term
        (
            "pay_histories_states_something_ck",
            "amount is not null or rate is not null or formula is not null",
        ),
        # a proportion with nothing to apply it to is unusable
        ("pay_histories_rate_basis_ck", "rate is null or basis is not null"),
    ):
        op.execute(f"alter table {table} drop constraint if exists {name}")
        op.execute(f"alter table {table} add constraint {name} check ({expression})")

    # salary and commission legitimately start on the same day
    op.execute(f'drop index if exists "{schema}".pay_histories_employee_from_uk')
    op.execute(f'drop index if exists "{schema}".pay_histories_employee_from_idx')
    op.execute(
        'create unique index if not exists pay_histories_employee_from_uk on '
        f"{table} (tenant_id, employee_id, component, effective_from)"
    )
    op.execute(
        'create index if not exists pay_histories_employee_from_idx on '
        f"{table} (tenant_id, employee_id, component, effective_from)"
    )
    op.execute(f'create index if not exists pay_histories_component_idx on {table} (component)')


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".pay_histories'

    op.execute(f'drop index if exists "{schema}".pay_histories_component_idx')
    op.execute(f'drop index if exists "{schema}".pay_histories_employee_from_uk')
    op.execute(f'drop index if exists "{schema}".pay_histories_employee_from_idx')
    op.execute(
        'create unique index if not exists pay_histories_employee_from_uk on '
        f"{table} (tenant_id, employee_id, effective_from)"
    )
    op.execute(
        'create index if not exists pay_histories_employee_from_idx on '
        f"{table} (tenant_id, employee_id, effective_from)"
    )
    for name in (
        "pay_histories_rate_basis_ck",
        "pay_histories_states_something_ck",
        "pay_histories_rate_ck",
        "pay_histories_amount_ck",
    ):
        op.execute(f"alter table {table} drop constraint if exists {name}")
    op.execute(f"delete from {table} where amount is null")
    op.execute(f"alter table {table} alter column amount set not null")
    op.execute(f"alter table {table} add constraint pay_histories_amount_ck check (amount >= 0)")
    for column in ("formula", "basis", "rate", "component"):
        op.execute(f"alter table {table} drop column if exists {column}")
