"""customer contacts: the rolodex behind a B2B account

Revision ID: 20260829_0069
Revises: 20260829_0068
Create Date: 2026-08-29 14:00:00

ProductSku's shape applied to Customer: a child identity table under a
master-data parent. A hospital has a procurement clerk, an equipment
engineer and a finance desk; the parent row's single contact column cannot
hold three people, and "寄票找谁" is a question about a person.

Documents keep their free-text contact snapshots — what a printed quotation
said survives the person changing jobs — so no document gains a contact FK;
this table is what agents consult when writing those snapshots.

Two partial-unique invariants, both freed by archiving: at most one active
PRIMARY per customer (the write path demotes the old one; the index is the
race's backstop), and one active row per (customer, phone) — the same
number twice under one customer is a duplicate person.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260829_0069"
down_revision = "20260829_0068"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".customer_contacts (
          id uuid primary key,
          tenant_id uuid not null,
          customer_id uuid not null references "{schema}".customers (id),
          name varchar(100) not null,
          title varchar(100),
          phone varchar(50),
          wechat varchar(100),
          email varchar(320),
          is_primary boolean not null default false,
          status varchar(20) not null default 'active',
          remarks text,
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint customer_contacts_status_chk check (status in ('active', 'archived'))
        )
        """
    )
    op.execute(
        f'create index if not exists customer_contacts_tenant_idx '
        f'on "{schema}".customer_contacts (tenant_id)'
    )
    op.execute(
        f'create index if not exists customer_contacts_customer_id_idx '
        f'on "{schema}".customer_contacts (customer_id)'
    )
    op.execute(f'alter table "{schema}".customer_contacts enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".customer_contacts')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".customer_contacts
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )
    op.execute(
        f"""
        create unique index if not exists customer_contacts_primary_uq
          on "{schema}".customer_contacts (tenant_id, customer_id)
          where is_primary AND status = 'active'
        """
    )
    op.execute(
        f"""
        create unique index if not exists customer_contacts_phone_uq
          on "{schema}".customer_contacts (tenant_id, customer_id, phone)
          where phone IS NOT NULL AND status = 'active'
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".customer_contacts')
