"""record what our defaults gave a system role, so the next capability lands

Revision ID: 20260813_0052
Revises: 20260812_0051
Create Date: 2026-08-13 12:00:00

A capability shipped after a workspace was created reached nobody there.
`provision_system_roles` could not fix it, and the reason was epistemic rather
than technical: a capability absent from `member` is either one we shipped
later or one the workspace removed, and `permissions_jsonb` alone cannot tell
those apart. So the sync topped up `admin` — safe, because admin is defined as
everything — and left every other role alone.

That cost 结算, 工资 and 请假 each a release where the feature was live and the
people who needed it got a 403. Each was found days later, in the middle of
somebody's flow, and closed by hand with `scripts/reconcile_demo_roles.py`.

This column ends the ambiguity the same way `tenant_skills
.catalog_required_capability` ended it for skill gating: record what we gave,
and the gap becomes readable. In neither the live set nor the baseline → never
offered here, so offer it. In the baseline but not the live set → taken away
deliberately, so leave it away.

**This fixes the future and deliberately not the past.** The backfill records
today's defaults, so a capability already missing today stays missing and keeps
being reported by the startup alarm until somebody decides about it. The
alternative — assuming every current gap is an omission and closing it — would
silently re-grant a capability a customer removed on purpose, and a permission
that comes back unnoticed is a worse failure than one that never arrived. The
existing backlog is a handful of roles closed by a named, reviewed script; that
is the cheaper error.

The `member` list is written out literally rather than imported. A migration
that reads the live constant gives a different baseline depending on WHEN it
runs, so an environment several releases behind — Hong Kong is — would record a
newer baseline than one that migrated on time and would silently skip
everything shipped in between. Frozen text makes every environment converge on
the same starting point.
"""

from __future__ import annotations

import json

from alembic import op

from app.core.config import settings


revision = "20260813_0052"
down_revision = "20260812_0051"
branch_labels = None
depends_on = None


# `DEFAULT_ROLE_PERMISSIONS["member"]` as of this revision. Frozen on purpose:
# see the module docstring. `admin` is absent because its branch of the sync
# ignores the baseline entirely — it is topped up to ALL_PERMISSIONS — so its
# record is filled by the first sync with no behavioural difference.
MEMBER_AS_OF_0052 = [
    "timesheet.submit_own",
    "leave.submit_own",
    "expense.submit_own",
    "purchase.submit_own",
    "quotation.submit_own",
    "order.submit_own",
    "business_object.write:*",
    "approval.record",
    "todos.complete_own",
    "booking.own",
]


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".roles'

    op.execute(f"alter table {table} add column if not exists catalog_permissions_jsonb jsonb")
    op.execute(
        f"update {table} set catalog_permissions_jsonb = '{json.dumps(MEMBER_AS_OF_0052)}'::jsonb "
        "where is_system and name = 'member' and catalog_permissions_jsonb is null"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".roles drop column if exists catalog_permissions_jsonb')
