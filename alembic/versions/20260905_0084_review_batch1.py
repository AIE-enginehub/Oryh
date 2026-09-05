"""review batch 1: one stock effect per source line; consent-stage OAuth rows

Revision ID: 20260905_0084
Revises: 20260904_0083
Create Date: 2026-09-05 10:00:00

R02: the ledger refuses a second effect of the same kind from the same
shipment line — the last defence behind the row lock the posting now takes.
R08: the OAuth consent is a nonce minted for the session that saw the page,
stored as a `consent`-stage row beside the codes; a consent row never
redeems as a code.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20260905_0084"
down_revision = "20260904_0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create unique index if not exists inventory_item_details_source_effect_uq
          on "{schema}".inventory_item_details (tenant_id, entity_type, entity_id, reason)
          where entity_type = 'shipment_item'
        """
    )
    op.execute(
        f'alter table "{schema}".oauth_authorization_codes add column if not exists '
        f"stage varchar(10) not null default 'code'"
    )
    op.execute(
        f'alter table "{schema}".oauth_authorization_codes add column if not exists session_id uuid'
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".oauth_authorization_codes drop column if exists session_id')
    op.execute(f'alter table "{schema}".oauth_authorization_codes drop column if exists stage')
    op.execute(f'drop index if exists "{schema}".inventory_item_details_source_effect_uq')
