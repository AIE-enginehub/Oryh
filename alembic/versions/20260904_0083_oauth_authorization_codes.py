"""OAuth 2.1 authorization codes

Revision ID: 20260904_0083
Revises: 20260903_0082
Create Date: 2026-09-04 12:00:00

The second door: MCP clients (Claude, Codex, …) discover the authorization
server, run authorization code + PKCE in the person's browser, and receive
the same interactive key pair the device flow mints. The code is the
consent's receipt — hashed, ten minutes, spent once. A platform table like
device_authorizations: no tenant context exists before it is redeemed.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20260904_0083"
down_revision = "20260903_0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".oauth_authorization_codes (
          id uuid primary key,
          code_hash varchar(64) not null unique,
          client_id varchar(500) not null,
          redirect_uri varchar(1000) not null,
          code_challenge varchar(128) not null,
          resource varchar(500),
          scope varchar(500),
          tenant_id uuid not null,
          user_id uuid not null,
          expires_at timestamptz not null,
          consumed_at timestamptz,
          created_at timestamptz not null default now()
        )
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".oauth_authorization_codes')
