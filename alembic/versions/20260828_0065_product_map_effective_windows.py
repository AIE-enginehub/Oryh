"""a listing's meaning gets a time axis: effective windows on the product map

Revision ID: 20260828_0065
Revises: 20260828_0064
Create Date: 2026-08-28 16:00:00

Platforms reward a listing's ranking, not its contents: a merchant who
fought for a good promotion slot keeps the SAME Tmall/JD product id and
swaps what it sells. So one external id means different products at
different times — and order sync lags, so yesterday's orders arrive today
and must translate against what the listing meant on the ORDER's date.

0064's permanent unique constraint on (source, listing, product) cannot
hold that world: it blocks a listing from ever swapping BACK to a product
it meant before, and "current pairing only" silently mistranslates every
back-dated import after a swap.

So map rows gain [effective_from, effective_to) — half-open, null bounds
open-ended, both null meaning "always" so tenants that never swap never
touch them. A swap closes the old row's window and creates the new row;
the old row stays ACTIVE because it is still the truth about its window
(archived means withdrawn — a mistake — never superseded). The constraint
becomes the price book's shape, a partial unique index: at most one OPEN
live assertion per pairing; a closed window frees the slot.

Existing rows backfill to (null, null) by simply gaining nullable columns:
"always", which is exactly what they asserted before time existed here.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.core.config import settings


revision = "20260828_0065"
down_revision = "20260828_0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.add_column(
        "external_product_maps",
        sa.Column("effective_from", sa.Date(), nullable=True),
        schema=settings.database_schema,
    )
    op.add_column(
        "external_product_maps",
        sa.Column("effective_to", sa.Date(), nullable=True),
        schema=settings.database_schema,
    )
    op.execute(
        f'alter table "{schema}".external_product_maps '
        "drop constraint if exists external_product_maps_identity_uk"
    )
    op.execute(
        f"""
        create unique index if not exists external_product_maps_open_uq
          on "{schema}".external_product_maps
             (tenant_id, source, external_product_id, external_sku_id, product_id)
          where status = 'active' and effective_to is null
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop index if exists "{schema}".external_product_maps_open_uq')
    op.execute(
        f"""
        alter table "{schema}".external_product_maps
          add constraint external_product_maps_identity_uk
          unique (tenant_id, source, external_product_id, external_sku_id, product_id)
        """
    )
    op.drop_column("external_product_maps", "effective_to", schema=settings.database_schema)
    op.drop_column("external_product_maps", "effective_from", schema=settings.database_schema)
