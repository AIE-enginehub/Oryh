"""the external product map answers by listing title too

Revision ID: 20260902_0079
Revises: 20260902_0078
Create Date: 2026-09-02 18:00:00

Tmall's order export names products by title and spec, not by listing id,
so a map keyed only by id cannot translate the orders a merchant actually
downloads. `external_name_norm` is the title's matching form (NFKC,
casefold, whitespace collapsed), derived on every write and backfilled
here; `external_product_id` may now be '' (the export carried none), in
which case the title is the listing's identity and a second partial unique
index holds the open-slot rule for it. A row must name the listing one way
or the other (CHECK).
"""

from __future__ import annotations

import unicodedata

from alembic import op
from sqlalchemy import text

from app.core.config import settings


revision = "20260902_0079"
down_revision = "20260902_0078"
branch_labels = None
depends_on = None


def _norm(name):
    if name is None:
        return None
    folded = unicodedata.normalize("NFKC", name).casefold()
    collapsed = " ".join(folded.split())
    return collapsed or None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".external_product_maps add column if not exists '
        f"external_name_norm varchar(200)"
    )
    op.execute(
        f'create index if not exists external_product_maps_external_name_norm_idx '
        f'on "{schema}".external_product_maps (external_name_norm)'
    )
    conn = op.get_bind()
    rows = conn.execute(text(
        f'select id, external_name from "{schema}".external_product_maps '
        f"where external_name is not null"
    )).all()
    for row_id, name in rows:
        conn.execute(
            text(f'update "{schema}".external_product_maps set external_name_norm = :n where id = :i'),
            {"n": _norm(name), "i": row_id},
        )
    op.execute(f'drop index if exists "{schema}".external_product_maps_open_uq')
    op.execute(
        f"""
        create unique index if not exists external_product_maps_open_uq
          on "{schema}".external_product_maps (tenant_id, source, external_product_id, external_sku_id, product_id)
          where status = 'active' AND effective_to IS NULL AND external_product_id <> ''
        """
    )
    op.execute(
        f"""
        create unique index if not exists external_product_maps_open_name_uq
          on "{schema}".external_product_maps (tenant_id, source, external_name_norm, external_sku_id, product_id)
          where status = 'active' AND effective_to IS NULL AND external_product_id = ''
        """
    )
    op.execute(
        f'alter table "{schema}".external_product_maps drop constraint if exists '
        f'external_product_maps_names_the_listing_check'
    )
    op.execute(
        f'alter table "{schema}".external_product_maps add constraint '
        f"external_product_maps_names_the_listing_check "
        f"check (external_product_id <> '' OR external_name IS NOT NULL)"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".external_product_maps drop constraint if exists '
        f'external_product_maps_names_the_listing_check'
    )
    op.execute(f'drop index if exists "{schema}".external_product_maps_open_name_uq')
    op.execute(f'drop index if exists "{schema}".external_product_maps_open_uq')
    op.execute(
        f"""
        create unique index if not exists external_product_maps_open_uq
          on "{schema}".external_product_maps (tenant_id, source, external_product_id, external_sku_id, product_id)
          where status = 'active' AND effective_to IS NULL
        """
    )
    op.execute(f'drop index if exists "{schema}".external_product_maps_external_name_norm_idx')
    op.execute(f'alter table "{schema}".external_product_maps drop column if exists external_name_norm')
