"""unique master-data codes for bulk upsert

Revision ID: 20260724_0024
Revises: 20260722_0023
Create Date: 2026-07-24 09:00:00

A tenant's own code (product_code / vendor_code / customer_code) becomes the
identity a bulk import upserts on, so re-running an Excel import updates rows
instead of duplicating them. The index is PARTIAL: master data may still be
created by hand without a code, and only a stated code has to be unique.

Archived rows keep their code on purpose — re-importing it revives that row
rather than creating a second one beside the archived original.

Pre-existing duplicates would make the index creation fail and take the whole
deployment's migration with it. They are extremely unlikely (nothing ever
enforced or generated these codes in bulk), but a live tenant's data is not
the place to find out: this migration de-duplicates first, keeping the oldest
row's code and suffixing the others so nothing is deleted and the operator can
find and merge them afterwards.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260724_0024"
down_revision = "20260722_0023"
branch_labels = None
depends_on = None

# (table, code column) — all three master-data families share the shape.
TABLES = (
    ("products", "product_code"),
    ("vendors", "vendor_code"),
    ("customers", "customer_code"),
)


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table, column in TABLES:
        # Keep the oldest row's code untouched; suffix any later collision with
        # its own id so the row survives, stays findable, and stops blocking
        # the unique index. -dup- is a deliberate, greppable marker.
        op.execute(
            f"""
            with ranked as (
              select id,
                     row_number() over (
                       partition by tenant_id, {column}
                       order by created_at, id
                     ) as rn
                from "{schema}".{table}
               where {column} is not null
            )
            update "{schema}".{table} as t
               set {column} = left(t.{column}, 40) || '-dup-' || left(t.id::text, 8)
              from ranked
             where ranked.id = t.id
               and ranked.rn > 1
            """
        )
        op.execute(
            f"""
            create unique index if not exists {table}_tenant_code_uq
                on "{schema}".{table} (tenant_id, {column})
             where {column} is not null
            """
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table, _column in TABLES:
        op.execute(f'drop index if exists "{schema}".{table}_tenant_code_uq')
