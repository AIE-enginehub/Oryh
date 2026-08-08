"""audit logs, state machines, product skills

Revision ID: 20260703_0013
Revises: 20260703_0012
Create Date: 2026-07-03 18:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260703_0013"
down_revision = "20260703_0012"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')

    # --- audit trail -----------------------------------------------------
    op.execute(
        f"""
        create table if not exists "{schema}".audit_logs (
          id bigserial primary key,
          tenant_id uuid not null,
          action text not null,
          entity_type text not null,
          entity_id uuid not null,
          actor text,
          detail_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now()
        )
        """
    )
    op.execute(
        f"""
        create index if not exists audit_logs_tenant_idx
          on "{schema}".audit_logs (tenant_id, id desc)
        """
    )
    op.execute(
        f"""
        create index if not exists audit_logs_tenant_entity_idx
          on "{schema}".audit_logs (tenant_id, entity_type, entity_id, id desc)
        """
    )
    op.execute(f'alter table "{schema}".audit_logs enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".audit_logs')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".audit_logs
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )
    op.execute(
        f"""
        alter table if exists "{schema}".todos
        add column if not exists due_at timestamptz
        """
    )

    # --- natural-language workflow definitions (append-only versions) --------
    op.execute(
        f"""
        create table if not exists "{schema}".workflow_definitions (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          entity_kind text not null default 'business_object',
          object_type text not null,
          name text not null default 'default',
          version integer not null default 1,
          definition_text text not null,
          status text not null default 'active',
          created_by text,
          created_at timestamptz not null default now(),
          constraint workflow_definitions_version_uk
            unique (tenant_id, entity_kind, object_type, name, version),
          constraint workflow_definitions_status_chk check (status in ('active', 'superseded')),
          constraint workflow_definitions_entity_kind_chk check (entity_kind in ('business_object', 'builtin')),
          constraint workflow_definitions_version_chk check (version >= 1)
        )
        """
    )
    op.execute(
        f"""
        create index if not exists workflow_definitions_tenant_idx
          on "{schema}".workflow_definitions (tenant_id, entity_kind, object_type, name, status)
        """
    )
    op.execute(f'alter table "{schema}".workflow_definitions enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".workflow_definitions')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".workflow_definitions
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )
    op.execute(
        f"""
        do $$
        begin
          if exists (select 1 from pg_roles where rolname = 'oryh_app') then
            grant select, insert, update, delete on all tables in schema "{schema}" to oryh_app;
            grant usage on all sequences in schema "{schema}" to oryh_app;
            alter default privileges in schema "{schema}" grant usage on sequences to oryh_app;
          end if;
        end $$
        """
    )

    # --- unified type registry: entity kind + state machine ------------------
    op.execute(
        f"""
        alter table if exists "{schema}".object_type_definitions
        add column if not exists entity_kind text not null default 'business_object'
        """
    )
    op.execute(
        f"""
        alter table if exists "{schema}".object_type_definitions
        add column if not exists state_machine jsonb
        """
    )
    op.execute(
        f"""
        alter table if exists "{schema}".object_type_definitions
        drop constraint if exists object_type_definitions_tenant_type_uk
        """
    )
    op.execute(
        f"""
        alter table if exists "{schema}".object_type_definitions
        add constraint object_type_definitions_tenant_kind_type_uk
        unique (tenant_id, entity_kind, object_type)
        """
    )
    op.execute(
        f"""
        alter table if exists "{schema}".object_type_definitions
        add constraint object_type_definitions_entity_kind_chk
        check (entity_kind in ('business_object', 'builtin'))
        """
    )

    # status legality moves to the app layer, driven by per-tenant machines
    op.execute(
        f'alter table if exists "{schema}".business_objects drop constraint if exists business_objects_status_chk'
    )
    op.execute(
        f'alter table if exists "{schema}".timesheet_headers drop constraint if exists timesheet_headers_status_chk'
    )

    # --- approval idempotency -------------------------------------------------
    op.execute(
        f"""
        alter table if exists "{schema}".approval_records
        add constraint approval_records_action_uk
        unique (tenant_id, entity_type, entity_id, round_no, sequence_no, action)
        """
    )

    # --- product vs custom skills ----------------------------------------------
    op.execute(
        f"""
        alter table if exists "{schema}".tenant_skills
        add column if not exists kind text not null default 'custom'
        """
    )
    op.execute(
        f"""
        alter table if exists "{schema}".tenant_skills
        add constraint tenant_skills_kind_chk check (kind in ('product', 'custom'))
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table if exists "{schema}".tenant_skills drop constraint if exists tenant_skills_kind_chk')
    op.execute(f'alter table if exists "{schema}".tenant_skills drop column if exists kind')
    op.execute(
        f'alter table if exists "{schema}".approval_records drop constraint if exists approval_records_action_uk'
    )
    op.execute(
        f"""
        alter table if exists "{schema}".business_objects
        add constraint business_objects_status_chk
        check (status in ('open', 'in_review', 'approved', 'rejected', 'archived'))
        """
    )
    op.execute(
        f"""
        alter table if exists "{schema}".timesheet_headers
        add constraint timesheet_headers_status_chk
        check (status in ('draft', 'submitted', 'approved', 'rejected', 'returned'))
        """
    )
    op.execute(
        f'alter table if exists "{schema}".object_type_definitions drop constraint if exists object_type_definitions_entity_kind_chk'
    )
    op.execute(
        f"""
        alter table if exists "{schema}".object_type_definitions
        drop constraint if exists object_type_definitions_tenant_kind_type_uk
        """
    )
    op.execute(
        f"""
        alter table if exists "{schema}".object_type_definitions
        add constraint object_type_definitions_tenant_type_uk unique (tenant_id, object_type)
        """
    )
    op.execute(f'alter table if exists "{schema}".object_type_definitions drop column if exists state_machine')
    op.execute(f'alter table if exists "{schema}".object_type_definitions drop column if exists entity_kind')
    op.execute(f'drop table if exists "{schema}".workflow_definitions')
    op.execute(f'alter table if exists "{schema}".todos drop column if exists due_at')
    op.execute(f'drop table if exists "{schema}".audit_logs')
