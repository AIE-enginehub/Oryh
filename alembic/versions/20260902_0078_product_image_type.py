"""product images say what kind of picture they are

Revision ID: 20260902_0078
Revises: 20260902_0077
Create Date: 2026-09-02 16:00:00

`image_type` on product_images — the tenant-extensible product_image_type
vocabulary (展示图/详情图/设计图稿/包装图/尺寸图/其他), so a caption
stops being the only place "this is the detail shot" could live. Orthogonal
to is_primary. Existing rows backfill: primaries as `main`, the rest as
`other` — what a gallery held before it knew the word.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260902_0078"
down_revision = "20260902_0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".product_images add column if not exists '
        f"image_type varchar(50) not null default 'other'"
    )
    op.execute(
        f"""update "{schema}".product_images set image_type = 'main' where is_primary"""
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".product_images drop column if exists image_type')
