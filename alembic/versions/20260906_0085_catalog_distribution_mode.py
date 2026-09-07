"""the catalog's say on a product skill's distribution mode

Revision ID: 20260906_0085
Revises: 20260905_0084
Create Date: 2026-09-06 10:00:00

The eight `*-approval-flow` skills are the hosted runner's, yet every admin
received them: they gate on `*.advance`, and admin holds everything. The
catalog now ships them `targeted` with nobody named — the runner and the
tenant service key ignore audience, a person is out unless the tenant names
them. Tracking follows the gate's rule: a tenant who already set a mode owns
it, an untouched default follows the catalog. Backfilled to `capability` on
product rows so the first sync after this deploy flips only untouched ones.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20260906_0085"
down_revision = "20260905_0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".tenant_skills add column if not exists '
        f"catalog_distribution_mode varchar(20)"
    )
    op.execute(
        f'update "{schema}".tenant_skills set catalog_distribution_mode = \'capability\' '
        f"where kind = 'product' and catalog_distribution_mode is null"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".tenant_skills drop column if exists catalog_distribution_mode')
