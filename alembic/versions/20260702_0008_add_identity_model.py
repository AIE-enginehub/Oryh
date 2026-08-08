"""add identity model

Revision ID: 20260702_0008
Revises: 20260422_0007
Create Date: 2026-07-02 10:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260702_0008"
down_revision = "20260422_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        alter table if exists "{schema_name}".tenants
        add column if not exists email_domain text unique
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema_name}".users (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null references "{schema_name}".tenants(id),
          email text not null unique,
          name text,
          password_hash text,
          oidc_subject text,
          role text not null default 'member',
          employee_id uuid unique references "{schema_name}".employees(id),
          status text not null default 'active',
          email_verified_at timestamptz,
          invite_token_hash text unique,
          invite_expires_at timestamptz,
          invited_by uuid,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint users_role_chk check (role in ('admin', 'member')),
          constraint users_status_chk check (status in ('invited', 'active', 'disabled'))
        )
        """
    )
    op.execute(
        f"""
        create index if not exists users_tenant_idx
          on "{schema_name}".users (tenant_id)
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema_name}".user_sessions (
          id uuid primary key default gen_random_uuid(),
          user_id uuid not null references "{schema_name}".users(id),
          token_hash text not null unique,
          expires_at timestamptz not null,
          revoked_at timestamptz,
          created_at timestamptz not null default now()
        )
        """
    )
    op.execute(
        f"""
        create index if not exists user_sessions_user_idx
          on "{schema_name}".user_sessions (user_id)
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema_name}".pending_registrations (
          id uuid primary key default gen_random_uuid(),
          company_name text not null,
          email text not null,
          email_domain text not null,
          password_hash text not null,
          token_hash text not null unique,
          expires_at timestamptz not null,
          consumed_at timestamptz,
          created_at timestamptz not null default now()
        )
        """
    )
    op.execute(
        f"""
        create index if not exists pending_registrations_email_idx
          on "{schema_name}".pending_registrations (email)
        """
    )
    op.execute(
        f"""
        create index if not exists pending_registrations_domain_idx
          on "{schema_name}".pending_registrations (email_domain)
        """
    )
    op.execute(
        f"""
        alter table if exists "{schema_name}".api_keys
        add column if not exists user_id uuid references "{schema_name}".users(id)
        """
    )
    op.execute(
        f"""
        alter table if exists "{schema_name}".api_keys
        add column if not exists role text not null default 'service'
        """
    )
    op.execute(
        f"""
        create index if not exists api_keys_user_idx
          on "{schema_name}".api_keys (user_id)
        """
    )


def downgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    op.execute(f'drop index if exists "{schema_name}".api_keys_user_idx')
    op.execute(f'alter table if exists "{schema_name}".api_keys drop column if exists role')
    op.execute(f'alter table if exists "{schema_name}".api_keys drop column if exists user_id')
    op.execute(f'drop table if exists "{schema_name}".pending_registrations')
    op.execute(f'drop table if exists "{schema_name}".user_sessions')
    op.execute(f'drop table if exists "{schema_name}".users')
    op.execute(f'alter table if exists "{schema_name}".tenants drop column if exists email_domain')
