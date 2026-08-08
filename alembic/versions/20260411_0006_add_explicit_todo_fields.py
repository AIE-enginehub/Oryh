"""add explicit todo fields

Revision ID: 20260411_0006
Revises: 20260408_0005
Create Date: 2026-04-11 11:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260411_0006"
down_revision = "20260408_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    op.execute(f'alter table if exists "{schema_name}".todos add column if not exists todo_type text')
    op.execute(f'alter table if exists "{schema_name}".todos add column if not exists created_by text')


def downgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    op.execute(f'alter table if exists "{schema_name}".todos drop column if exists created_by')
    op.execute(f'alter table if exists "{schema_name}".todos drop column if exists todo_type')
