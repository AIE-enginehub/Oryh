"""enable row level security

Revision ID: 20260703_0012
Revises: 20260702_0011
Create Date: 2026-07-03 10:00:00

Defense-in-depth for tenant isolation. The runtime role (oryh_app, created
by scripts/bootstrap_db_roles.py) is subject to these policies; the owning
role that runs migrations and ops scripts is exempt. Policies key on the
app.tenant_id / app.is_platform_admin GUCs bound per transaction by the app.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260703_0012"
down_revision = "20260702_0011"
branch_labels = None
depends_on = None

# Strict tenant isolation: reads need the tenant GUC (or the platform-admin
# GUC); writes always need the matching tenant GUC.
STRICT_TABLES = (
    "employees",
    "projects",
    "resources",
    "resource_bookings",
    "business_objects",
    "business_object_links",
    "object_type_definitions",
    "tenant_skills",
    "timesheet_headers",
    "timesheet_entries",
    "approval_records",
    "todos",
)

# Authentication tables: SELECT stays open because credentials are resolved
# before the tenant is known (api key by hash, user by email/session); writes
# require the tenant GUC or the platform-admin GUC.
AUTH_TABLES = ("users", "api_keys")

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table in STRICT_TABLES:
        op.execute(f'alter table "{schema}".{table} enable row level security')
        op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
        op.execute(
            f"""
            create policy tenant_isolation on "{schema}".{table}
              using ({TENANT_MATCH} or {PLATFORM_ON})
              with check ({TENANT_MATCH})
            """
        )
    for table in AUTH_TABLES:
        op.execute(f'alter table "{schema}".{table} enable row level security')
        for policy in ("auth_lookup", "tenant_insert", "tenant_update"):
            op.execute(f'drop policy if exists {policy} on "{schema}".{table}')
        op.execute(f'create policy auth_lookup on "{schema}".{table} for select using (true)')
        op.execute(
            f"""
            create policy tenant_insert on "{schema}".{table}
              for insert with check ({TENANT_MATCH} or {PLATFORM_ON})
            """
        )
        op.execute(
            f"""
            create policy tenant_update on "{schema}".{table}
              for update using ({TENANT_MATCH} or {PLATFORM_ON})
              with check ({TENANT_MATCH} or {PLATFORM_ON})
            """
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for table in STRICT_TABLES:
        op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
        op.execute(f'alter table "{schema}".{table} disable row level security')
    for table in AUTH_TABLES:
        for policy in ("auth_lookup", "tenant_insert", "tenant_update"):
            op.execute(f'drop policy if exists {policy} on "{schema}".{table}')
        op.execute(f'alter table "{schema}".{table} disable row level security')
