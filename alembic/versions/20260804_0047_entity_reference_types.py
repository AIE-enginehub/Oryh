"""todos and approval facts may point at every document family, not five of them

Revision ID: 20260804_0047
Revises: 20260804_0046
Create Date: 2026-08-04 12:00:00

`todos_entity_type_chk` and `approval_records_entity_type_chk` were written when
there were five document families and never grew. Invoices, payments and
purchase orders were accepted by the API — `TODO_TARGET_MODELS` derives from
`DOCUMENT_FAMILIES`, so they resolved fine — and then refused by the database.
The IntegrityError was not caught, so an ordinary "create the approval todo for
this payment" answered **500**, on a path `$oryh-payment-approval-flow` tells
every finance agent to walk. Found by a deployed agent, not
here: nothing in the suite created a todo against a payment.

The list is now GENERATED from `DOCUMENT_FAMILIES` rather than typed out again.
That is the actual fix — the same list had been restated in three places (an
if-chain in routes.py, these constraints, and the registry) and all three had
drifted from each other. `tests/test_entity_reference_types.py` pins the
constraint against the registry, so the next family added fails the build.

This is the third instance of the same shape in recent memory:
`BUILTIN_OBJECT_TYPES` went four releases without the new families, and the
audit's `direction not in ('sales','purchase')` reported every payslip as a
violation. A hand-maintained list beside a growing registry is a defect waiting
for a release.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260804_0047"
down_revision = "20260804_0046"
branch_labels = None
depends_on = None


def _quoted(values) -> str:
    return ", ".join(f"'{value}'" for value in sorted(values))


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')

    # Imported here rather than at module scope: alembic loads every revision
    # on startup, and a migration that drags the API layer in at import time
    # makes the whole history hostage to it.
    from app.api.routes import APPROVAL_ENTITY_TYPES, TODO_ENTITY_TYPES

    for table, constraint, allowed in (
        ("todos", "todos_entity_type_chk", TODO_ENTITY_TYPES),
        ("approval_records", "approval_records_entity_type_chk", APPROVAL_ENTITY_TYPES),
    ):
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {constraint}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {constraint} '
            f"check (entity_type in ({_quoted(allowed)}))"
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')

    # The five-family list this replaced. Restated literally because that is
    # what the old constraint was — deriving it would be pretending the old
    # state was principled.
    old_todo = (
        "timesheet_header", "expense_claim", "purchase_request", "sales_quotation",
        "sales_order", "project", "approval_target", "business_object",
    )
    old_approval = (
        "timesheet_header", "expense_claim", "purchase_request", "sales_quotation",
        "sales_order", "approval_target", "business_object",
    )
    for table, constraint, allowed in (
        ("todos", "todos_entity_type_chk", old_todo),
        ("approval_records", "approval_records_entity_type_chk", old_approval),
    ):
        # rows the old constraint would refuse have to go first, or the
        # constraint cannot be added back
        op.execute(
            f'delete from "{schema}".{table} where entity_type not in ({_quoted(allowed)})'
        )
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {constraint}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {constraint} '
            f"check (entity_type in ({_quoted(allowed)}))"
        )
