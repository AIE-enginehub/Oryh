"""tenant-customizable type vocabularies (OFBiz-style *_TYPE tables)

Revision ID: 20260726_0030
Revises: 20260726_0029
Create Date: 2026-07-26 12:00:00

One table for every type vocabulary a tenant may extend: product price
types, sales adjustment types, expense categories, work types. kind=system
rows mirror the shipped catalog (seeded per tenant by provisioning on the
next deploy sync — this migration only creates the table); kind=custom rows
are tenant-defined. Validation falls back to the shipped catalog for a
tenant with no rows, so nothing breaks in the window between this migration
and the seed.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260726_0030"
down_revision = "20260726_0029"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".type_options (
          id uuid primary key,
          tenant_id uuid not null,
          family varchar(50) not null,
          name varchar(50) not null,
          kind varchar(20) not null default 'custom',
          title varchar(200),
          description text,
          status varchar(20) not null default 'active',
          created_by varchar(100),
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint type_options_tenant_family_name_uk unique (tenant_id, family, name)
        )
        """
    )
    op.execute(f'create index if not exists type_options_tenant_idx on "{schema}".type_options (tenant_id)')
    op.execute(f'create index if not exists type_options_family_idx on "{schema}".type_options (family)')
    op.execute(f'alter table "{schema}".type_options enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".type_options')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".type_options
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
    op.execute(f'drop table if exists "{schema}".type_options')
