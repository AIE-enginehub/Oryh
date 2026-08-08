"""isolate oryh schema

Revision ID: 20260408_0005
Revises: 20260403_0004
Create Date: 2026-04-08 10:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260408_0005"
down_revision = "20260403_0004"
branch_labels = None
depends_on = None


ORYH_TABLES = [
    "tenants",
    "api_keys",
    "employees",
    "projects",
    "resources",
    "approval_targets",
    "resource_bookings",
    "timesheet_headers",
    "timesheet_entries",
    "approval_records",
    "todos",
]


def upgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    op.execute(f'create schema if not exists "{schema_name}"')
    for table_name in ORYH_TABLES:
        quoted_table = table_name.replace('"', '""')
        op.execute(f'alter table if exists public."{quoted_table}" set schema "{schema_name}"')


def downgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    for table_name in reversed(ORYH_TABLES):
        quoted_table = table_name.replace('"', '""')
        op.execute(f'alter table if exists "{schema_name}"."{quoted_table}" set schema public')
