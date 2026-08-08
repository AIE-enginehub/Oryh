"""add rbac: capabilities and roles

Revision ID: 20260705_0014
Revises: 20260703_0013
Create Date: 2026-07-05 12:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260705_0014"
down_revision = "20260703_0013"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".capabilities (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          name text not null,
          kind text not null default 'custom',
          title text,
          description text,
          scopable boolean not null default false,
          created_by text,
          created_at timestamptz not null default now(),
          constraint capabilities_tenant_name_uk unique (tenant_id, name),
          constraint capabilities_kind_chk check (kind in ('system', 'custom'))
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".roles (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          name text not null,
          title text,
          description text,
          permissions_jsonb jsonb not null default '[]'::jsonb,
          is_system boolean not null default false,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint roles_tenant_name_uk unique (tenant_id, name)
        )
        """
    )
    for table in ("capabilities", "roles"):
        op.execute(f'create index if not exists {table}_tenant_idx on "{schema}".{table} (tenant_id)')
        op.execute(f'alter table "{schema}".{table} enable row level security')
        op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
        op.execute(
            f"""
            create policy tenant_isolation on "{schema}".{table}
              using ({TENANT_MATCH} or {PLATFORM_ON})
              with check ({TENANT_MATCH})
            """
        )
    op.execute(
        f"""
        alter table if exists "{schema}".tenant_skills
        add column if not exists required_capability text
        """
    )
    # role names are tenant-defined now
    op.execute(f'alter table if exists "{schema}".users drop constraint if exists users_role_chk')
    op.execute(
        f"""
        do $$
        begin
          if exists (select 1 from pg_roles where rolname = 'oryh_app') then
            grant select, insert, update, delete on all tables in schema "{schema}" to oryh_app;
          end if;
        end $$
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table if exists "{schema}".tenant_skills drop column if exists required_capability')
    op.execute(f'drop table if exists "{schema}".roles')
    op.execute(f'drop table if exists "{schema}".capabilities')
