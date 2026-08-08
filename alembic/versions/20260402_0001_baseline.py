"""baseline schema

Revision ID: 20260402_0001
Revises: None
Create Date: 2026-04-02 10:45:00
"""

from __future__ import annotations

from alembic import op


revision = "20260402_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("create extension if not exists pgcrypto")

    op.execute(
        """
        create table tenants (
          id uuid primary key default gen_random_uuid(),
          name text not null,
          status text not null default 'active',
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint tenants_status_chk check (status in ('active', 'inactive'))
        )
        """
    )
    op.execute(
        """
        create table api_keys (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null references tenants(id),
          key_hash text not null,
          label text,
          is_active boolean not null default true,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        )
        """
    )
    op.execute("create unique index api_keys_key_hash_uk on api_keys (key_hash)")
    op.execute("create index api_keys_tenant_idx on api_keys (tenant_id)")

    op.execute(
        """
        create table employees (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          employee_code text,
          name text not null,
          email text,
          timezone text,
          status text not null default 'active',
          metadata_jsonb jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint employees_status_chk check (status in ('active', 'inactive'))
        )
        """
    )
    op.execute(
        """
        create unique index employees_tenant_employee_code_uk
          on employees (tenant_id, employee_code)
          where employee_code is not null
        """
    )

    op.execute(
        """
        create table projects (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          project_code text,
          project_name text not null,
          client text,
          status text not null default 'active',
          start_date date,
          end_date date,
          metadata_jsonb jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint projects_status_chk check (status in ('active', 'archived')),
          constraint projects_date_chk check (end_date is null or start_date is null or end_date >= start_date)
        )
        """
    )
    op.execute(
        """
        create unique index projects_tenant_project_code_uk
          on projects (tenant_id, project_code)
          where project_code is not null
        """
    )

    op.execute(
        """
        create table timesheet_headers (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          employee_id uuid not null references employees(id),
          period_start date not null,
          period_end date not null,
          status text not null default 'draft',
          submitted_at timestamptz,
          source_report_text text,
          custom_fields_jsonb jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz,
          deleted_by text,
          delete_reason text,
          constraint timesheet_headers_status_chk check (status in ('draft', 'submitted', 'approved', 'rejected', 'returned')),
          constraint timesheet_headers_period_chk check (period_end >= period_start)
        )
        """
    )
    op.execute(
        """
        create unique index timesheet_headers_tenant_employee_period_uk
          on timesheet_headers (tenant_id, employee_id, period_start, period_end)
        """
    )
    op.execute(
        """
        create index timesheet_headers_tenant_active_period_idx
          on timesheet_headers (tenant_id, employee_id, period_start desc)
          where deleted_at is null
        """
    )

    op.execute(
        """
        create table timesheet_entries (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          header_id uuid not null references timesheet_headers(id),
          employee_id uuid not null references employees(id),
          work_date date not null,
          project_id uuid references projects(id),
          project_name_snapshot text,
          client text,
          task text,
          hours numeric(5,2) not null,
          work_type text not null default 'regular',
          notes text,
          custom_fields_jsonb jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz,
          constraint timesheet_entries_hours_chk check (hours > 0 and hours <= 24),
          constraint timesheet_entries_work_type_chk check (work_type in ('regular', 'overtime', 'holiday', 'travel', 'other'))
        )
        """
    )
    op.execute(
        """
        create index timesheet_entries_tenant_header_idx
          on timesheet_entries (tenant_id, header_id)
          where deleted_at is null
        """
    )
    op.execute(
        """
        create index timesheet_entries_tenant_employee_date_idx
          on timesheet_entries (tenant_id, employee_id, work_date)
          where deleted_at is null
        """
    )

    op.execute(
        """
        create table approval_records (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          entity_type text not null,
          entity_id uuid not null,
          round_no integer not null default 1,
          sequence_no integer not null default 1,
          action text not null,
          approver_id text,
          approver_role text,
          comment text,
          source text,
          metadata_jsonb jsonb not null default '{}'::jsonb,
          acted_at timestamptz not null,
          created_at timestamptz not null default now(),
          constraint approval_records_entity_type_chk check (entity_type in ('timesheet_header')),
          constraint approval_records_action_chk check (action in ('submitted', 'approved', 'rejected', 'returned', 'commented')),
          constraint approval_records_source_chk check (source in ('web', 'api', 'ai', 'system') or source is null),
          constraint approval_records_round_no_chk check (round_no >= 1),
          constraint approval_records_sequence_no_chk check (sequence_no >= 1)
        )
        """
    )

    op.execute(
        """
        create table todos (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          employee_id uuid not null references employees(id),
          entity_type text not null,
          entity_id uuid not null,
          title text not null,
          description text,
          status text not null default 'open',
          metadata_jsonb jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          completed_at timestamptz,
          completed_by text,
          constraint todos_status_chk check (status in ('open', 'completed')),
          constraint todos_entity_type_chk check (entity_type in ('timesheet_header', 'project'))
        )
        """
    )
    op.execute(
        """
        create index todos_tenant_assignee_status_idx
          on todos (tenant_id, employee_id, status, created_at desc)
        """
    )
    op.execute(
        """
        create unique index todos_open_entity_assignee_uk
          on todos (tenant_id, employee_id, entity_type, entity_id)
          where status = 'open'
        """
    )


def downgrade() -> None:
    op.execute("drop index if exists todos_open_entity_assignee_uk")
    op.execute("drop index if exists todos_tenant_assignee_status_idx")
    op.execute("drop table if exists todos")
    op.execute("drop table if exists approval_records")
    op.execute("drop index if exists timesheet_entries_tenant_employee_date_idx")
    op.execute("drop index if exists timesheet_entries_tenant_header_idx")
    op.execute("drop table if exists timesheet_entries")
    op.execute("drop index if exists timesheet_headers_tenant_active_period_idx")
    op.execute("drop index if exists timesheet_headers_tenant_employee_period_uk")
    op.execute("drop table if exists timesheet_headers")
    op.execute("drop index if exists projects_tenant_project_code_uk")
    op.execute("drop table if exists projects")
    op.execute("drop index if exists employees_tenant_employee_code_uk")
    op.execute("drop table if exists employees")
    op.execute("drop index if exists api_keys_tenant_idx")
    op.execute("drop index if exists api_keys_key_hash_uk")
    op.execute("drop table if exists api_keys")
    op.execute("drop table if exists tenants")
