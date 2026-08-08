"""add the tenant slug that namespaces skill bundles on an employee's machine

Revision ID: 20260714_0019
Revises: 20260713_0018
Create Date: 2026-07-14 10:00:00

A person who works for two companies installs two bundles into the same local
agent.  Both used to be called ``oryh-skills/`` and to contain identically
named skills, so the second install destroyed the first.  The slug is the
namespace that separates them (``oryh-skills-<slug>/``), which makes it a
directory name on machines we do not control: derived once here, never updated.
"""

from __future__ import annotations

import re
import uuid

import sqlalchemy as sa
from alembic import op

from app.core.config import settings


revision = "20260714_0019"
down_revision = "20260713_0018"
branch_labels = None
depends_on = None

SLUG_MAX_LENGTH = 24


def _slug_for(email_domain: str | None) -> str:
    label = (email_domain or "").strip().lower().split(".")[0]
    label = re.sub(r"[^a-z0-9]+", "-", label).strip("-")[:SLUG_MAX_LENGTH].strip("-")
    return label or f"t-{uuid.uuid4().hex[:8]}"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".tenants add column if not exists slug varchar(24)')

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f'select id, email_domain from "{schema}".tenants where slug is null order by created_at')
    ).all()
    taken: set[str] = {
        row[0]
        for row in bind.execute(sa.text(f'select slug from "{schema}".tenants where slug is not null')).all()
    }
    for tenant_id, email_domain in rows:
        base = _slug_for(email_domain)
        candidate, suffix = base, 2
        while candidate in taken:
            tail = f"-{suffix}"
            candidate = f"{base[: SLUG_MAX_LENGTH - len(tail)].strip('-')}{tail}"
            suffix += 1
        taken.add(candidate)
        bind.execute(
            sa.text(f'update "{schema}".tenants set slug = :slug where id = :id'),
            {"slug": candidate, "id": tenant_id},
        )

    op.execute(
        f'create unique index if not exists tenants_slug_key on "{schema}".tenants (slug)'
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop index if exists "{schema}".tenants_slug_key')
    op.execute(f'alter table "{schema}".tenants drop column if exists slug')
