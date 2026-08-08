"""add platform admins

Revision ID: 20260702_0010
Revises: 20260702_0009
Create Date: 2026-07-02 20:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260702_0010"
down_revision = "20260702_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema_name}".platform_admins (
          id uuid primary key default gen_random_uuid(),
          email text not null unique,
          name text,
          password_hash text not null,
          status text not null default 'active',
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint platform_admins_status_chk check (status in ('active', 'disabled'))
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema_name}".platform_sessions (
          id uuid primary key default gen_random_uuid(),
          platform_admin_id uuid not null references "{schema_name}".platform_admins(id),
          token_hash text not null unique,
          expires_at timestamptz not null,
          revoked_at timestamptz,
          created_at timestamptz not null default now()
        )
        """
    )
    op.execute(
        f"""
        create index if not exists platform_sessions_admin_idx
          on "{schema_name}".platform_sessions (platform_admin_id)
        """
    )


def downgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema_name}".platform_sessions')
    op.execute(f'drop table if exists "{schema_name}".platform_admins')
