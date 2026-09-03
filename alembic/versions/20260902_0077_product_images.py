"""product images: the catalog's pictures, bytes in the attachment store

Revision ID: 20260902_0077
Revises: 20260902_0076
Create Date: 2026-09-02 14:00:00

A link table from products to attachments — the receipts' own blob store
reused, tenant-scoped and sha256-deduplicated. Several pictures per
product, ONE primary (partial unique; setting a new one demotes the old in
the same write), a curated order behind it. Removing a picture removes the
link and leaves the bytes where the store keeps them.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260902_0077"
down_revision = "20260902_0076"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".product_images (
          id uuid primary key,
          tenant_id uuid not null,
          product_id uuid not null references "{schema}".products (id),
          attachment_id uuid not null references "{schema}".attachments (id),
          is_primary boolean not null default false,
          sort_order integer,
          caption varchar(200),
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint product_images_tenant_product_attachment_uk
            unique (tenant_id, product_id, attachment_id)
        )
        """
    )
    for column in ("tenant_id", "product_id", "attachment_id"):
        op.execute(
            f'create index if not exists product_images_{column}_idx '
            f'on "{schema}".product_images ({column})'
        )
    op.execute(f'alter table "{schema}".product_images enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".product_images')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".product_images
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )
    op.execute(
        f"""
        create unique index if not exists product_images_primary_uq
          on "{schema}".product_images (tenant_id, product_id)
          where is_primary
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".product_images')
