"""add device authorizations

Revision ID: 20260706_0015
Revises: 20260705_0014
Create Date: 2026-07-06 10:00:00

Pre-auth handshake table for the browser device flow (oryh-connect): rows
exist before any tenant/user is known, so unlike business tables it carries
no tenant RLS. All lookups go through the hashed device_code or the
short-lived user_code; the plaintext key column is nulled on consumption.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260706_0015"
down_revision = "20260705_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".device_authorizations (
          id uuid primary key default gen_random_uuid(),
          device_code_hash text not null unique,
          user_code text not null,
          client_name text,
          status text not null default 'pending',
          tenant_id uuid,
          user_id uuid,
          api_key_id uuid,
          api_key_plaintext text,
          expires_at timestamptz not null,
          approved_at timestamptz,
          consumed_at timestamptz,
          created_at timestamptz not null default now(),
          constraint device_authorizations_status_chk
            check (status in ('pending', 'approved', 'denied', 'consumed'))
        )
        """
    )
    op.execute(
        f'create index if not exists device_authorizations_user_code_idx '
        f'on "{schema}".device_authorizations (user_code)'
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
    op.execute(f'drop table if exists "{schema}".device_authorizations')
