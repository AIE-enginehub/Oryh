"""a workspace may refine a shipped skill without forking it

Revision ID: 20260819_0057
Revises: 20260818_0056
Create Date: 2026-08-19 09:00:00

A tenant who wants one sentence changed in a product skill has had exactly one
route: edit its files, which forks it to `custom` and stops catalog syncs
forever. That is the right trade for a genuine rewrite and much too expensive
for a preference — "只列标题就好" cost a workspace every correction shipped
afterwards.

`calibration` is a tenant-owned text field the sync never touches, appended as
a section when the bundle renders. It sits beside `required_capability` (who
may receive) and `distribution_mode` (who is targeted) as the third knob a
tenant owns outright, and the skill's content keeps tracking the catalog.

Column only. What calibration may not do — widen a skill's permissions,
override its prohibitions — is stated in the rendered text and enforced by the
same boundary that already governs the skill, not by a constraint: a CHECK
cannot read English.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision = "20260819_0057"
down_revision = "20260818_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_skills",
        sa.Column("calibration", sa.Text(), nullable=True),
        schema=settings.database_schema,
    )


def downgrade() -> None:
    op.drop_column("tenant_skills", "calibration", schema=settings.database_schema)
