"""stores and facilities: where the company sells, and where it ships from

Revision ID: 20260901_0074
Revises: 20260831_0073
Create Date: 2026-09-01 10:00:00

OFBiz ProductStore and Facility reduced to the agent-native core. A
FACILITY is a physical place — 店铺/仓库/办公室/工厂, the tenant-extensible
`facility_type` vocabulary — whose NAME is what the stock ledger and
freight legs already say in free text, so the name is unique among active
rows: the registry those strings should come from. A STORE is a selling
front, `channel` the closed offline/online pair, `source` optionally the
lowercase channel key external orders arrive under (the external map's own
join key). Which facilities may ship for a store is `store_facilities` —
one row per pair, priority ranking, the pair reviving like a price
agreement — the store's standing answer, never a router. Sales orders gain
a nullable store_id: which front the order came through.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260901_0074"
down_revision = "20260831_0073"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".facilities (
          id uuid primary key,
          tenant_id uuid not null,
          facility_code varchar(64),
          name varchar(100) not null,
          facility_type varchar(50) not null,
          address varchar(500),
          remarks text,
          status varchar(20) not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint facilities_status_chk check (status in ('active', 'archived'))
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".stores (
          id uuid primary key,
          tenant_id uuid not null,
          store_code varchar(64),
          name varchar(100) not null,
          channel varchar(10) not null,
          source varchar(50),
          address varchar(500),
          remarks text,
          status varchar(20) not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint stores_channel_chk check (channel in ('offline', 'online')),
          constraint stores_status_chk check (status in ('active', 'archived'))
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".store_facilities (
          id uuid primary key,
          tenant_id uuid not null,
          store_id uuid not null references "{schema}".stores (id),
          facility_id uuid not null references "{schema}".facilities (id),
          priority integer,
          remarks varchar(500),
          status varchar(20) not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint store_facilities_tenant_store_facility_uk
            unique (tenant_id, store_id, facility_id),
          constraint store_facilities_status_chk check (status in ('active', 'archived'))
        )
        """
    )
    for table, extra_indexed in (
        ("facilities", ()),
        ("stores", ()),
        ("store_facilities", ("store_id", "facility_id")),
    ):
        op.execute(
            f'create index if not exists {table}_tenant_idx '
            f'on "{schema}".{table} (tenant_id)'
        )
        for column in extra_indexed:
            op.execute(
                f'create index if not exists {table}_{column}_idx '
                f'on "{schema}".{table} ({column})'
            )
        op.execute(f'alter table "{schema}".{table} enable row level security')
        op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
        op.execute(
            f"""
            create policy tenant_isolation on "{schema}".{table}
              using ({TENANT_MATCH} or {PLATFORM_ON})
              with check ({TENANT_MATCH})
            """
        )
    for table in ("facilities", "stores"):
        code = table[:-1] if table == "stores" else "facility"
        prefix = "store" if table == "stores" else "facility"
        op.execute(
            f"""
            create unique index if not exists {table}_tenant_code_uq
              on "{schema}".{table} (tenant_id, {prefix}_code)
              where {prefix}_code IS NOT NULL
            """
        )
        op.execute(
            f"""
            create unique index if not exists {table}_tenant_name_uq
              on "{schema}".{table} (tenant_id, name)
              where status = 'active'
            """
        )
    op.execute(
        f'alter table "{schema}".sales_orders add column if not exists '
        f'store_id uuid references "{schema}".stores (id)'
    )
    op.execute(
        f'create index if not exists sales_orders_store_id_idx '
        f'on "{schema}".sales_orders (store_id)'
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".sales_orders drop column if exists store_id')
    op.execute(f'drop table if exists "{schema}".store_facilities')
    op.execute(f'drop table if exists "{schema}".stores')
    op.execute(f'drop table if exists "{schema}".facilities')
