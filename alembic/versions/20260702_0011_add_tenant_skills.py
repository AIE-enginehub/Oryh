"""add tenant skills

Revision ID: 20260702_0011
Revises: 20260702_0010
Create Date: 2026-07-02 22:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260702_0011"
down_revision = "20260702_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema_name}".tenant_skills (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          name text not null,
          title text,
          description text,
          files_jsonb jsonb not null default '{{}}'::jsonb,
          version integer not null default 1,
          status text not null default 'active',
          created_by text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint tenant_skills_tenant_name_uk unique (tenant_id, name),
          constraint tenant_skills_status_chk check (status in ('active', 'archived')),
          constraint tenant_skills_version_chk check (version >= 1)
        )
        """
    )
    op.execute(
        f"""
        create index if not exists tenant_skills_tenant_idx
          on "{schema_name}".tenant_skills (tenant_id, status)
        """
    )


def downgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema_name}".tenant_skills')
