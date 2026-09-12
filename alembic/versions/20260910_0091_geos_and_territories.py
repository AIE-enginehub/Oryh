"""geography and territories: geos, territories, coverage, members; where
a customer or a lead is, and who covers it

Revision ID: 20260910_0091
Revises: 20260910_0090
Create Date: 2026-09-10 18:00:00

A GEO is a place in a hierarchy (OFBiz's Geo) — country, province, city,
district, postal code, a region the workspace draws — each naming its
parent. A TERRITORY is a named set of geos (coverage by containment) with
the people who work it, nesting through a parent. Customers carry where
they are (`geo_id`), who covers them (`territory_id`, resolved from the geo
when exactly one territory does), whose account it is
(`owner_employee_id`) and their payment terms; leads carry where the
inquiry is from. All master data: no lifecycle, no CHECKs beyond identity.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20260910_0091"
down_revision = "20260910_0090"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def _isolate(schema: str, table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.execute(f'create index if not exists {table}_{column}_idx on "{schema}".{table} ({column})')
    op.execute(f'alter table "{schema}".{table} enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".{table}
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".geos (
          id uuid primary key,
          tenant_id uuid not null,
          geo_code varchar(64) not null,
          name varchar(200) not null,
          geo_type varchar(50) not null,
          parent_geo_id uuid references "{schema}".geos (id),
          abbreviation varchar(50),
          status varchar(20) not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint geos_geo_code_uk unique (tenant_id, geo_code)
        )
        """
    )
    _isolate(schema, "geos", ("tenant_id", "parent_geo_id"))
    op.execute(
        f"""
        create table if not exists "{schema}".territories (
          id uuid primary key,
          tenant_id uuid not null,
          territory_code varchar(64) not null,
          name varchar(200) not null,
          parent_territory_id uuid references "{schema}".territories (id),
          manager_employee_id uuid references "{schema}".employees (id),
          description text,
          status varchar(20) not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint territories_territory_code_uk unique (tenant_id, territory_code)
        )
        """
    )
    _isolate(schema, "territories", ("tenant_id", "parent_territory_id", "manager_employee_id"))
    op.execute(
        f"""
        create table if not exists "{schema}".territory_geos (
          id uuid primary key,
          tenant_id uuid not null,
          territory_id uuid not null references "{schema}".territories (id),
          geo_id uuid not null references "{schema}".geos (id),
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint territory_geos_uk unique (tenant_id, territory_id, geo_id)
        )
        """
    )
    _isolate(schema, "territory_geos", ("tenant_id", "territory_id", "geo_id"))
    op.execute(
        f"""
        create table if not exists "{schema}".territory_members (
          id uuid primary key,
          tenant_id uuid not null,
          territory_id uuid not null references "{schema}".territories (id),
          employee_id uuid not null references "{schema}".employees (id),
          role varchar(50),
          valid_from date,
          valid_until date,
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint territory_members_uk unique (tenant_id, territory_id, employee_id)
        )
        """
    )
    _isolate(schema, "territory_members", ("tenant_id", "territory_id", "employee_id"))
    for column, ddl in (
        ("geo_id", f'uuid references "{schema}".geos (id)'),
        ("territory_id", f'uuid references "{schema}".territories (id)'),
        ("owner_employee_id", f'uuid references "{schema}".employees (id)'),
        ("payment_terms", "varchar(500)"),
    ):
        op.execute(f'alter table "{schema}".customers add column if not exists {column} {ddl}')
    for column in ("geo_id", "territory_id", "owner_employee_id"):
        op.execute(f'create index if not exists customers_{column}_idx on "{schema}".customers ({column})')
    op.execute(f'alter table "{schema}".leads add column if not exists geo_id uuid references "{schema}".geos (id)')
    op.execute(f'create index if not exists leads_geo_id_idx on "{schema}".leads (geo_id)')


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop index if exists "{schema}".leads_geo_id_idx')
    op.execute(f'alter table "{schema}".leads drop column if exists geo_id')
    for column in ("geo_id", "territory_id", "owner_employee_id"):
        op.execute(f'drop index if exists "{schema}".customers_{column}_idx')
    for column in ("geo_id", "territory_id", "owner_employee_id", "payment_terms"):
        op.execute(f'alter table "{schema}".customers drop column if exists {column}')
    for table in ("territory_members", "territory_geos", "territories", "geos"):
        op.execute(f'drop table if exists "{schema}".{table}')
