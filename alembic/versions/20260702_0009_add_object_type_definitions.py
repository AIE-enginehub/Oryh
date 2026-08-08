"""add object type definitions

Revision ID: 20260702_0009
Revises: 20260702_0008
Create Date: 2026-07-02 16:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260702_0009"
down_revision = "20260702_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema_name}".object_type_definitions (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          object_type text not null,
          title text,
          description text,
          json_schema jsonb not null default '{{}}'::jsonb,
          version integer not null default 1,
          status text not null default 'active',
          created_by text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint object_type_definitions_tenant_type_uk unique (tenant_id, object_type),
          constraint object_type_definitions_status_chk check (status in ('active', 'archived')),
          constraint object_type_definitions_version_chk check (version >= 1)
        )
        """
    )
    op.execute(
        f"""
        create index if not exists object_type_definitions_tenant_idx
          on "{schema_name}".object_type_definitions (tenant_id, status)
        """
    )
    op.execute(
        f"""
        create index if not exists business_objects_payload_gin_idx
          on "{schema_name}".business_objects using gin (payload_jsonb jsonb_path_ops)
        """
    )


def downgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    op.execute(f'drop index if exists "{schema_name}".business_objects_payload_gin_idx')
    op.execute(f'drop table if exists "{schema_name}".object_type_definitions')
