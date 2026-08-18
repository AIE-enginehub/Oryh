"""interactive personal keys expire and refresh; service keys do not

Revision ID: 20260818_0056
Revises: 20260816_0055
Create Date: 2026-08-18 12:00:00

Until now every API key lived forever: `api_keys` had no expiry column at all,
and the device flow rendered a permanent plaintext key into the markdown of a
personal skill bundle — synced, backed up, and outliving the laptop it landed
on. These columns are the schema half of the fix (docs/mcp-adoption-plan §3
阶段 1): interactive personal keys get `expires_at` and a rotating refresh
token; NULL keeps the old meaning, so every existing key — and every tenant
service key and hosted flow-agent key minted after this — behaves exactly as
before. Grandfathering is the migration: no rows are touched.

`prior_refresh_token_hash` + `refresh_rotated_at` exist to tell a lost-response
retry from replay of a stolen copy; the grace-window logic lives in the API
layer where it can be tested.

`device_authorizations.refresh_token_plaintext` mirrors `api_key_plaintext`:
held only between browser approval and the agent's next poll, cleared on
handover.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision = "20260818_0056"
down_revision = "20260816_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema
    op.add_column(
        "api_keys",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        schema=schema,
    )
    op.add_column(
        "api_keys",
        sa.Column("refresh_token_hash", sa.String(64), nullable=True),
        schema=schema,
    )
    op.create_index(
        "api_keys_refresh_token_hash_idx",
        "api_keys",
        ["refresh_token_hash"],
        unique=True,
        schema=schema,
    )
    op.add_column(
        "api_keys",
        sa.Column("prior_refresh_token_hash", sa.String(64), nullable=True),
        schema=schema,
    )
    op.add_column(
        "api_keys",
        sa.Column("refresh_rotated_at", sa.DateTime(timezone=True), nullable=True),
        schema=schema,
    )
    op.add_column(
        "device_authorizations",
        sa.Column("refresh_token_plaintext", sa.String(200), nullable=True),
        schema=schema,
    )


def downgrade() -> None:
    schema = settings.database_schema
    op.drop_column("device_authorizations", "refresh_token_plaintext", schema=schema)
    op.drop_column("api_keys", "refresh_rotated_at", schema=schema)
    op.drop_column("api_keys", "prior_refresh_token_hash", schema=schema)
    op.drop_index("api_keys_refresh_token_hash_idx", "api_keys", schema=schema)
    op.drop_column("api_keys", "refresh_token_hash", schema=schema)
    op.drop_column("api_keys", "expires_at", schema=schema)
