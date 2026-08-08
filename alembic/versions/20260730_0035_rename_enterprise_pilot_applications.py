"""rename design partner applications to enterprise pilot applications

Revision ID: 20260730_0035
Revises: 20260730_0034
Create Date: 2026-07-30 11:30:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260730_0035"
down_revision = "20260730_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".enterprise_pilot_applications'
    op.execute(
        f'alter table "{schema}".design_partner_applications '
        "rename to enterprise_pilot_applications"
    )
    op.execute(
        f"alter table {table} rename constraint "
        "design_partner_applications_status_chk "
        "to enterprise_pilot_applications_status_chk"
    )
    op.execute(
        f"alter table {table} rename constraint "
        "design_partner_applications_weekly_users_chk "
        "to enterprise_pilot_applications_weekly_users_chk"
    )
    op.execute(
        f"alter table {table} rename constraint "
        "design_partner_applications_email_uk "
        "to enterprise_pilot_applications_email_uk"
    )
    op.execute(
        f"alter table {table} rename constraint "
        "design_partner_applications_reviewed_by_fkey "
        "to enterprise_pilot_applications_reviewed_by_fkey"
    )
    op.execute(
        f'alter index "{schema}".design_partner_applications_status_idx '
        "rename to enterprise_pilot_applications_status_idx"
    )
    op.execute(
        f'alter index "{schema}".design_partner_applications_domain_idx '
        "rename to enterprise_pilot_applications_domain_idx"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".enterprise_pilot_applications'
    op.execute(
        f"alter table {table} rename constraint "
        "enterprise_pilot_applications_status_chk "
        "to design_partner_applications_status_chk"
    )
    op.execute(
        f"alter table {table} rename constraint "
        "enterprise_pilot_applications_weekly_users_chk "
        "to design_partner_applications_weekly_users_chk"
    )
    op.execute(
        f"alter table {table} rename constraint "
        "enterprise_pilot_applications_email_uk "
        "to design_partner_applications_email_uk"
    )
    op.execute(
        f"alter table {table} rename constraint "
        "enterprise_pilot_applications_reviewed_by_fkey "
        "to design_partner_applications_reviewed_by_fkey"
    )
    op.execute(
        f'alter index "{schema}".enterprise_pilot_applications_status_idx '
        "rename to design_partner_applications_status_idx"
    )
    op.execute(
        f'alter index "{schema}".enterprise_pilot_applications_domain_idx '
        "rename to design_partner_applications_domain_idx"
    )
    op.execute(
        f'alter table "{schema}".enterprise_pilot_applications '
        "rename to design_partner_applications"
    )
