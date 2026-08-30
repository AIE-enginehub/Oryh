"""audit_logs accepts platform-admin writes

Revision ID: 20260830_0072
Revises: 20260830_0071
Create Date: 2026-08-30 12:00:00

Every platform-admin write to a tenant's rows produces an audit_logs row for
that tenant — the audit trail listener derives it from the row written. The
tables the platform deliberately writes (users, api_keys in 0012;
flow_subscriptions in 0038) all carry `or platform_on` in their WITH CHECK,
but audit_logs (0013) got the strict-table shape, so under a non-owner
database role every one of those writes 500s on the audit row it generates:
issuing a tenant a service key, resetting a user's password, updating a
subscription. A deployment whose database role owns the tables never saw it —
the owner skips RLS entirely.

Widening the bookkeeping table is safer than requiring every admin endpoint
to bind the target tenant's GUC before committing: the business row's own
policy has already vetted the write (with the platform branch those policies
carry on purpose), the audit row merely records it, and a forgotten bind in
some future endpoint would otherwise fail only in environments where the
role is not the owner — exactly how this shipped broken. Tenant credentials
never carry app.is_platform_admin, so tenant isolation is unchanged.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260830_0072"
down_revision = "20260830_0071"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".audit_logs')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".audit_logs
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH} or {PLATFORM_ON})
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".audit_logs')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".audit_logs
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )
