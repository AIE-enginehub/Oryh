"""drop todos.assign from untuned default member roles

Revision ID: 20260725_0025
Revises: 20260724_0024
Create Date: 2026-07-25 14:00:00

todos.assign lets a credential create todos for ANY employee, and it gates the
distribution of flow-side skills (approval-notifier). Neither belongs to an
ordinary member: assigning work is routing, the flow/admin side's write. The
shipped default now omits it (app/core/permissions.py); this migration brings
EXISTING tenants' member roles in line — but only the untouched ones.

"Tenants own their tuning": a member role whose permission set differs in any
way from the old shipped default is a tenant's deliberate configuration and is
left exactly as it is. The both-way jsonb containment check below is set
equality, so only roles still carrying the verbatim old default are touched.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260725_0025"
down_revision = "20260724_0024"
branch_labels = None
depends_on = None

# The member default as shipped before this revision, order-independent.
OLD_MEMBER_DEFAULT = (
    '["timesheet.submit_own", "expense.submit_own", "purchase.submit_own", '
    '"quotation.submit_own", "order.submit_own", "business_object.write:*", '
    '"approval.record", "todos.assign", "todos.complete_own", "booking.own"]'
)


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        update "{schema}".roles
           set permissions_jsonb = permissions_jsonb - 'todos.assign',
               updated_at = now()
         where name = 'member'
           and is_system
           and permissions_jsonb @> '{OLD_MEMBER_DEFAULT}'::jsonb
           and permissions_jsonb <@ '{OLD_MEMBER_DEFAULT}'::jsonb
        """
    )


def downgrade() -> None:
    # Not restored: after the upgrade there is no way to tell a migrated
    # member role from one a tenant trimmed by hand, and re-granting a
    # permission a tenant may have removed on purpose is worse than leaving
    # the narrower set in place. Re-add todos.assign per tenant if needed.
    pass
