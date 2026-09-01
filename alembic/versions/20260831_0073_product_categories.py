"""product categories: the catalog's shelving, and the product's pointer to it

Revision ID: 20260831_0073
Revises: 20260830_0072
Create Date: 2026-08-31 10:00:00

OFBiz ProductCategory reduced to the agent-native core: a tree (ONE parent
per category), an import identity code that revives archived rows, and a
name unique among ACTIVE siblings — two live folders with one name at one
level is a filing error, the same name under different parents is normal
shelving. Products gain a nullable category_id; archiving a shelf touches
neither its children nor the products pointing at it, because what to do
with a retired shelf's contents is the catalog desk's judgment, not a
cascade.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260831_0073"
down_revision = "20260830_0072"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".product_categories (
          id uuid primary key,
          tenant_id uuid not null,
          category_code varchar(64),
          name varchar(100) not null,
          parent_id uuid references "{schema}".product_categories (id),
          description varchar(500),
          status varchar(20) not null default 'active',
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint product_categories_status_chk check (status in ('active', 'archived'))
        )
        """
    )
    op.execute(
        f'create index if not exists product_categories_tenant_idx '
        f'on "{schema}".product_categories (tenant_id)'
    )
    op.execute(
        f'create index if not exists product_categories_parent_id_idx '
        f'on "{schema}".product_categories (parent_id)'
    )
    op.execute(f'alter table "{schema}".product_categories enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".product_categories')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".product_categories
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )
    op.execute(
        f"""
        create unique index if not exists product_categories_tenant_code_uq
          on "{schema}".product_categories (tenant_id, category_code)
          where category_code IS NOT NULL
        """
    )
    op.execute(
        f"""
        create unique index if not exists product_categories_root_name_uq
          on "{schema}".product_categories (tenant_id, name)
          where parent_id IS NULL AND status = 'active'
        """
    )
    op.execute(
        f"""
        create unique index if not exists product_categories_child_name_uq
          on "{schema}".product_categories (tenant_id, parent_id, name)
          where parent_id IS NOT NULL AND status = 'active'
        """
    )
    op.execute(
        f'alter table "{schema}".products add column if not exists '
        f'category_id uuid references "{schema}".product_categories (id)'
    )
    op.execute(
        f'create index if not exists products_category_id_idx '
        f'on "{schema}".products (category_id)'
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".products drop column if exists category_id')
    op.execute(f'drop table if exists "{schema}".product_categories')
