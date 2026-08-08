"""record the catalog's gate so syncs respect tenant re-gates

Revision ID: 20260725_0026
Revises: 20260725_0025
Create Date: 2026-07-25 15:00:00

The product-catalog sync used to overwrite a product skill's
required_capability (and force status back to active) whenever it differed
from the shipped catalog — silently undoing the exact re-gating and archiving
the skill-author skill teaches admins to do. The sync now compares against a
recorded catalog baseline instead: a gate equal to the baseline keeps
tracking the catalog, a gate the tenant changed is theirs.

The backfill reads the baseline from the shipped catalog itself (the same
skills/ directory this image deploys), keyed by skill name. Under the old
sync any divergence was reverted on every deploy, so rows normally equal the
catalog and resume tracking seamlessly; a row that diverges right now can
only be a tenant edit made since the last deploy — exactly the thing the new
sync must preserve, which NULL-vs-value or value-vs-value inequality does.
Product rows whose name has left the catalog stay NULL and are never visited
by the sync loop anyway.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.core.config import settings
from app.services.provisioning import PRODUCT_SKILLS_DIR, parse_frontmatter, read_skill_dir


revision = "20260725_0026"
down_revision = "20260725_0025"
branch_labels = None
depends_on = None


def _catalog_gates() -> dict[str, str | None]:
    gates: dict[str, str | None] = {}
    if not PRODUCT_SKILLS_DIR.is_dir():
        return gates
    for skill_dir in sorted(PRODUCT_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        files = read_skill_dir(skill_dir)
        if "SKILL.md" not in files:
            continue
        meta = parse_frontmatter(files["SKILL.md"])
        name = meta.get("name") or skill_dir.name
        gates[name] = meta.get("required_capability") or None
    return gates


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        alter table "{schema}".tenant_skills
        add column if not exists catalog_required_capability text
        """
    )
    bind = op.get_bind()
    for name, gate in _catalog_gates().items():
        bind.execute(
            sa.text(
                f"""
                update "{schema}".tenant_skills
                   set catalog_required_capability = :gate
                 where kind = 'product' and name = :name
                """
            ),
            {"gate": gate, "name": name},
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        alter table "{schema}".tenant_skills
        drop column if exists catalog_required_capability
        """
    )
