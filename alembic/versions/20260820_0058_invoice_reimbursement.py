"""money owed to an employee is a fourth kind of invoice

Revision ID: 20260820_0058
Revises: 20260819_0057
Create Date: 2026-08-20 09:00:00

An approved expense claim is a payable, and until now it was settled by
pointing a payment straight at the claim. That works, but it leaves the claim
outside AP: "what does the company owe" needs two queries, and a general ledger
would need two posting rules for one kind of liability.

The obvious fix — raise a purchase invoice against the merchant who issued the
receipt — is wrong, and the counterparty guard added in the previous release
now refuses it outright. The merchant was never owed anything: the employee
already paid them, out of their own pocket, at the hotel desk. What the company
owes is the employee.

So `reimbursement` is a fourth direction whose counterparty is
`payee_employee_id`, exactly as payroll's is. It is not payroll — no
one-per-period rule, no `payroll.read` gate, ordinary visibility — but it
shares the shape that matters: the party who gets paid is the party named on
the document, which is the whole reason the settlement guard can be trusted.

`expense_claim_id` records which claim the invoice was raised from. The partial
unique index on it is what makes generation idempotent: raising the invoice is
an explicit act (the server does not invent documents on a status change), so
it can be retried, and a retry that produced a second payable would be two
settleable invoices for one trip.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision = "20260820_0058"
down_revision = "20260819_0057"
branch_labels = None
depends_on = None

SCHEMA = settings.database_schema
CK = "invoices_direction_counterparty_ck"

OLD_CK = (
    "(direction = 'sales' and customer_id is not null "
    "and vendor_id is null and payee_employee_id is null) "
    "or (direction = 'purchase' and vendor_id is not null "
    "and customer_id is null and payee_employee_id is null) "
    "or (direction = 'payroll' and payee_employee_id is not null "
    "and customer_id is null and vendor_id is null)"
)
NEW_CK = OLD_CK + (
    " or (direction = 'reimbursement' and payee_employee_id is not null "
    "and customer_id is null and vendor_id is null)"
)


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("expense_claim_id", sa.Uuid(as_uuid=False), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "invoices_expense_claim_id_fkey",
        "invoices", "expense_claims",
        ["expense_claim_id"], ["id"],
        source_schema=SCHEMA, referent_schema=SCHEMA,
    )
    op.create_index(
        "ix_invoices_expense_claim_id", "invoices", ["expense_claim_id"], schema=SCHEMA
    )
    op.create_index(
        "invoices_expense_claim_uk",
        "invoices",
        ["tenant_id", "expense_claim_id"],
        unique=True,
        postgresql_where=sa.text("expense_claim_id IS NOT NULL AND deleted_at IS NULL"),
        sqlite_where=sa.text("expense_claim_id IS NOT NULL AND deleted_at IS NULL"),
        schema=SCHEMA,
    )
    op.drop_constraint(CK, "invoices", type_="check", schema=SCHEMA)
    op.create_check_constraint(CK, "invoices", sa.text(NEW_CK), schema=SCHEMA)


def downgrade() -> None:
    op.drop_constraint(CK, "invoices", type_="check", schema=SCHEMA)
    op.create_check_constraint(CK, "invoices", sa.text(OLD_CK), schema=SCHEMA)
    op.drop_index("invoices_expense_claim_uk", "invoices", schema=SCHEMA)
    op.drop_index("ix_invoices_expense_claim_id", "invoices", schema=SCHEMA)
    op.drop_constraint("invoices_expense_claim_id_fkey", "invoices", type_="foreignkey", schema=SCHEMA)
    op.drop_column("invoices", "expense_claim_id", schema=SCHEMA)
