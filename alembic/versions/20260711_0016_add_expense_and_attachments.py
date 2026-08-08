"""add expense claims, expense items, attachments, and vendor master data

Revision ID: 20260711_0016
Revises: 20260706_0015
Create Date: 2026-07-11 10:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260711_0016"
down_revision = "20260706_0015"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".attachments (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          filename text not null,
          content_type text not null,
          size_bytes integer not null,
          sha256 text not null,
          content bytea not null,
          uploaded_by text,
          created_at timestamptz not null default now(),
          constraint attachments_tenant_sha256_uk unique (tenant_id, sha256),
          constraint attachments_size_chk check (size_bytes >= 0)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".expense_claims (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          employee_id uuid not null references "{schema}".employees(id),
          title text not null,
          claim_date date,
          currency text not null default 'CNY',
          status text not null default 'draft',
          submitted_at timestamptz,
          source_report_text text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz,
          deleted_by text,
          delete_reason text
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".vendors (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          vendor_code text,
          name text not null,
          tax_id text,
          contact text,
          email text,
          phone text,
          status text not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint vendors_status_chk check (status in ('active', 'archived'))
        )
        """
    )
    op.execute(
        f"""
        create index if not exists vendors_tenant_idx
          on "{schema}".vendors (tenant_id, status, created_at desc)
        """
    )
    op.execute(
        f"""
        create index if not exists vendors_tenant_tax_id_idx
          on "{schema}".vendors (tenant_id, tax_id)
          where tax_id is not null
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".expense_items (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          claim_id uuid not null references "{schema}".expense_claims(id),
          employee_id uuid not null references "{schema}".employees(id),
          expense_date date not null,
          category text not null default 'other',
          amount numeric(12,2) not null,
          tax_amount numeric(12,2),
          vendor_id uuid references "{schema}".vendors(id),
          merchant text,
          invoice_number text,
          invoice_type text,
          project_id uuid references "{schema}".projects(id),
          project_name_snapshot text,
          client text,
          attachment_id uuid references "{schema}".attachments(id),
          extracted_fields_jsonb jsonb not null default '{{}}'::jsonb,
          notes text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          deleted_at timestamptz,
          constraint expense_items_amount_chk check (amount > 0),
          constraint expense_items_tax_amount_chk check (tax_amount is null or tax_amount >= 0)
        )
        """
    )
    op.execute(
        f"""
        create index if not exists expense_claims_tenant_status_idx
          on "{schema}".expense_claims (tenant_id, status, created_at desc)
        """
    )
    op.execute(
        f"""
        create index if not exists expense_claims_employee_idx
          on "{schema}".expense_claims (employee_id)
        """
    )
    op.execute(
        f"""
        create index if not exists expense_items_claim_idx
          on "{schema}".expense_items (claim_id)
        """
    )
    op.execute(
        f"""
        create index if not exists expense_items_tenant_invoice_idx
          on "{schema}".expense_items (tenant_id, invoice_number)
          where invoice_number is not null
        """
    )
    op.execute(
        f"""
        create index if not exists attachments_tenant_idx
          on "{schema}".attachments (tenant_id)
        """
    )
    # legacy check constraints predate the expense builtin: admit expense_claim
    op.execute(
        f"""
        alter table "{schema}".approval_records
          drop constraint if exists approval_records_entity_type_chk
        """
    )
    op.execute(
        f"""
        alter table "{schema}".approval_records
          add constraint approval_records_entity_type_chk
          check (entity_type in ('timesheet_header', 'expense_claim', 'approval_target', 'business_object'))
        """
    )
    op.execute(
        f"""
        alter table "{schema}".todos
          drop constraint if exists todos_entity_type_chk
        """
    )
    op.execute(
        f"""
        alter table "{schema}".todos
          add constraint todos_entity_type_chk
          check (entity_type in ('timesheet_header', 'expense_claim', 'project', 'approval_target', 'business_object'))
        """
    )
    for table in ("attachments", "vendors", "expense_claims", "expense_items"):
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
    op.execute(
        f"""
        alter table "{schema}".approval_records
          drop constraint if exists approval_records_entity_type_chk
        """
    )
    op.execute(
        f"""
        alter table "{schema}".approval_records
          add constraint approval_records_entity_type_chk
          check (entity_type in ('timesheet_header', 'approval_target', 'business_object'))
        """
    )
    op.execute(
        f"""
        alter table "{schema}".todos
          drop constraint if exists todos_entity_type_chk
        """
    )
    op.execute(
        f"""
        alter table "{schema}".todos
          add constraint todos_entity_type_chk
          check (entity_type in ('timesheet_header', 'project', 'approval_target', 'business_object'))
        """
    )
    op.execute(f'drop table if exists "{schema}".expense_items')
    op.execute(f'drop table if exists "{schema}".expense_claims')
    op.execute(f'drop table if exists "{schema}".vendors')
    op.execute(f'drop table if exists "{schema}".attachments')
