"""Accounting settings: the month the financial year starts

Revision ID: 20261125_0115
Revises: 20261124_0114
Create Date: 2026-11-25 10:00:00

Plan docs/plans/financial-statements-2026-11-25.md, phase 1. Used only to
resolve `year_start` and year-to-date spans in the statement reads; no
figure is stored by it, so it may change at any time.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261125_0115"
down_revision = "20261124_0114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(f"alter table {s}.accounting_settings "
               f"add column if not exists fiscal_year_start_month smallint not null default 1")
    op.execute(f"alter table {s}.accounting_settings drop constraint if exists accounting_settings_fiscal_month_chk")
    op.execute(f"alter table {s}.accounting_settings add constraint accounting_settings_fiscal_month_chk "
               f"check (fiscal_year_start_month >= 1 and fiscal_year_start_month <= 12)")


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(f"alter table {s}.accounting_settings drop constraint if exists accounting_settings_fiscal_month_chk")
    op.execute(f"alter table {s}.accounting_settings drop column if exists fiscal_year_start_month")
