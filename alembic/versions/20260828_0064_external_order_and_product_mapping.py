"""external order and product mapping: what a platform's numbers mean here

Revision ID: 20260828_0064
Revises: 20260821_0063
Create Date: 2026-08-28 10:00:00

Orders and returns usually arrive from somewhere else — Tmall, JD, Amazon, a
small vendor's site, a mini-program — and recording one means two
translations. TWO tables, not one, because the two mappings have opposite
uniqueness semantics:

- external_product_maps is reference data where MULTIPLE rows per external id
  are the point: a bundle listing is several rows with quantities, one
  product on five channels is five rows. Identity is (source, external
  listing, our product); the channel mirror of supplier_products.

- external_document_links is a transactional claim where the FULL tuple is
  hard-unique: recording the same link twice is a retry, and the constraint
  is what makes "have we imported TM2026… already?" a reliable dedup check.
  Splits and merges are extra rows (拆单/合单), not special cases. The target
  is the generic (entity_type, entity_id) pair — a return links whatever the
  tenant recorded the return AS (a business object, a refund payment, or the
  `returned` stock movement itself).

No backfill: nothing recorded external identities structurally before this —
they lived in custom_fields prose, which stays valid as the free-form side.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260828_0064"
down_revision = "20260821_0063"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".external_product_maps (
          id uuid primary key,
          tenant_id uuid not null,
          source varchar(50) not null,
          external_product_id varchar(128) not null,
          external_sku_id varchar(128) not null default '',
          external_name varchar(200),
          product_id uuid not null references "{schema}".products (id),
          sku_id uuid references "{schema}".product_skus (id),
          quantity numeric(12, 2) not null default 1,
          status varchar(20) not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint external_product_maps_identity_uk
            unique (tenant_id, source, external_product_id, external_sku_id, product_id)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".external_document_links (
          id uuid primary key,
          tenant_id uuid not null,
          source varchar(50) not null,
          external_kind varchar(50) not null,
          external_no varchar(128) not null,
          entity_type varchar(100) not null,
          entity_id uuid not null,
          created_by varchar(100),
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          constraint external_document_links_unique_link
            unique (tenant_id, source, external_kind, external_no, entity_type, entity_id)
        )
        """
    )
    for table in ("external_product_maps", "external_document_links"):
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
        f'create index if not exists external_product_maps_product_idx '
        f'on "{schema}".external_product_maps (product_id)'
    )
    op.execute(
        f'create index if not exists external_document_links_no_idx '
        f'on "{schema}".external_document_links (tenant_id, source, external_no)'
    )
    op.execute(
        f'create index if not exists external_document_links_entity_idx '
        f'on "{schema}".external_document_links (tenant_id, entity_type, entity_id)'
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".external_document_links')
    op.execute(f'drop table if exists "{schema}".external_product_maps')
