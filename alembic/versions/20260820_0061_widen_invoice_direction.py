"""`reimbursement` is 13 characters and the column held 10

Revision ID: 20260820_0061
Revises: 20260820_0060
Create Date: 2026-08-20 10:30:00

`invoices.direction` was `varchar(10)`, sized for `sales`, `purchase` and
`payroll`. Adding `reimbursement` extended the CHECK constraint and never
looked at the width, so Postgres refused every insert:

    StringDataRightTruncation: value too long for type character varying(10)

Both routes failed — `POST /invoices` with the direction stated, and
`POST /expense-claims/{claim_id}/invoice`, which writes it itself. Reported
from production by a finance user who could raise every other kind of invoice.

The suite could not have caught it. Tests run on in-memory SQLite, which does
not enforce VARCHAR length: the same insert succeeds there and the column
silently holds a 13-character value. 1409 passing tests said nothing about a
constraint only the production engine applies.

Widened to 20 rather than to the exact 13, so the next direction has room
without a migration — and `test_constrained_values_fit_their_columns` now
compares every CHECK-constrained vocabulary against its column width, on the
declared types rather than on the running database, which is what makes it
work under SQLite.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision = "20260820_0061"
down_revision = "20260820_0060"
branch_labels = None
depends_on = None

SCHEMA = settings.database_schema


def upgrade() -> None:
    op.alter_column(
        "invoices", "direction",
        existing_type=sa.String(length=10),
        type_=sa.String(length=20),
        existing_nullable=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    # Refuses if any row already holds a value longer than 10 — correct: the
    # rows are the reason the column was widened.
    op.alter_column(
        "invoices", "direction",
        existing_type=sa.String(length=20),
        type_=sa.String(length=10),
        existing_nullable=False,
        schema=SCHEMA,
    )
