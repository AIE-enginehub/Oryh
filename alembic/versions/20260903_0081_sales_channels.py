"""sales channels: the keys orders arrive under, as master data

Revision ID: 20260903_0081
Revises: 20260902_0080
Create Date: 2026-09-03 10:00:00

`source` was a string three tables agreed on by convention (stores, the
external product map, document links) with nowhere to say which channels
the company sells through, nor to hold a channel's own facts. A sales
channel is now a row: `channel_code` IS that key (lowercase, immutable,
unique per tenant regardless of status — an archived channel revives),
`channel_kind` the tenant's `sales_channel_kind` vocabulary. Stores point
at a channel instead of carrying the string; the map's `source` must name
a registered channel from now on; document links keep free text, because
banks and a counterparty's ERP are sources too. Existing keys become
channel rows here, so nothing a tenant already wrote stops resolving.
"""

from __future__ import annotations

import uuid

from alembic import op
from sqlalchemy import text

from app.core.config import settings

revision = "20260903_0081"
down_revision = "20260902_0080"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".sales_channels (
          id uuid primary key,
          tenant_id uuid not null,
          channel_code varchar(50) not null,
          name varchar(100) not null,
          channel_kind varchar(50) not null,
          remarks text,
          status varchar(20) not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint sales_channels_tenant_code_uk unique (tenant_id, channel_code),
          constraint sales_channels_status_chk check (status in ('active', 'archived'))
        )
        """
    )
    op.execute(
        f'create index if not exists sales_channels_tenant_idx '
        f'on "{schema}".sales_channels (tenant_id)'
    )
    op.execute(
        f"""
        create unique index if not exists sales_channels_tenant_name_uq
          on "{schema}".sales_channels (tenant_id, name)
          where status = 'active'
        """
    )
    op.execute(f'alter table "{schema}".sales_channels enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".sales_channels')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".sales_channels
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )
    op.execute(
        f'alter table "{schema}".stores add column if not exists sales_channel_id uuid '
        f'references "{schema}".sales_channels (id)'
    )
    op.execute(
        f'create index if not exists stores_sales_channel_id_idx '
        f'on "{schema}".stores (sales_channel_id)'
    )
    # every key a tenant already wrote becomes its channel row — the store's
    # string and the map's alike, so nothing stops resolving
    conn = op.get_bind()
    keys = conn.execute(text(
        f'select tenant_id, source from "{schema}".stores where source is not null '
        f'union select tenant_id, source from "{schema}".external_product_maps'
    )).all()
    for tenant_id, source in keys:
        conn.execute(
            text(
                f'insert into "{schema}".sales_channels '
                f"(id, tenant_id, channel_code, name, channel_kind) "
                f"values (:id, :t, :c, :c, 'marketplace') "
                f"on conflict (tenant_id, channel_code) do nothing"
            ),
            {"id": str(uuid.uuid4()), "t": tenant_id, "c": source},
        )
    op.execute(
        f"""
        update "{schema}".stores s
           set sales_channel_id = c.id
          from "{schema}".sales_channels c
         where c.tenant_id = s.tenant_id and c.channel_code = s.source
           and s.sales_channel_id is null
        """
    )
    op.execute(f'alter table "{schema}".stores drop column if exists source')


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".stores add column if not exists source varchar(50)')
    op.execute(
        f"""
        update "{schema}".stores s
           set source = c.channel_code
          from "{schema}".sales_channels c
         where c.id = s.sales_channel_id
        """
    )
    op.execute(f'alter table "{schema}".stores drop column if exists sales_channel_id')
    op.execute(f'drop table if exists "{schema}".sales_channels')
