"""Idempotency records: a retried write answers what the first attempt did

Revision ID: 20260915_0095
Revises: 20260915_0094
Create Date: 2026-09-15 12:00:00

Every write under /api/v1 may carry an `Idempotency-Key` (app/core/
idempotency.py). The row is claimed before the handler runs and filled with
the response after; a retry within 24 hours finds it and is answered from it.
Scoped by a hash of the presented credential, never by tenant: the row exists
before authentication, so the table carries no tenant RLS, like
device_authorizations and oauth_authorization_codes.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20260915_0095"
down_revision = "20260915_0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".idempotency_records (
          id uuid primary key,
          scope_hash varchar(64) not null,
          key varchar(200) not null,
          fingerprint varchar(64) not null,
          method varchar(8) not null,
          path varchar(500) not null,
          status_code integer,
          response_headers text,
          response_body text,
          completed_at timestamptz,
          created_at timestamptz not null default now(),
          constraint uq_idempotency_records_scope_key unique (scope_hash, key)
        )
        """
    )
    op.execute(
        f'create index if not exists ix_idempotency_records_created_at on "{schema}".idempotency_records (created_at)'
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".idempotency_records')
