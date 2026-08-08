"""finish enterprise pilot constraint naming

Revision ID: 20260730_0036
Revises: 20260730_0035
Create Date: 2026-07-30 11:45:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260730_0036"
down_revision = "20260730_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".enterprise_pilot_applications '
        "rename constraint design_partner_applications_pkey "
        "to enterprise_pilot_applications_pkey"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".enterprise_pilot_applications '
        "rename constraint enterprise_pilot_applications_pkey "
        "to design_partner_applications_pkey"
    )
