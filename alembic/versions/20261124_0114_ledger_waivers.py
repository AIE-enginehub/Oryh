"""Ledger waivers: a document the book needs no entry for, and who said so

Revision ID: 20261124_0114
Revises: 20261117_0113
Create Date: 2026-11-24 20:00:00

Plan docs/plans/ledger-coverage-2026-11-24.md, phase 2. The coverage read
lists every counted document no entry names; some of them the workspace's
posting rule says need none (a pro forma invoice, a zero-value claim). A
waiver records that decision — the document, optionally one event, the
reason and who decided — so the list can be emptied honestly. A waiver is
revoked, never deleted or edited; one live waiver per fact.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261124_0114"
down_revision = "20261117_0113"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(
        f"""
        create table if not exists {s}.ledger_waivers (
          id uuid primary key,
          tenant_id uuid not null,
          source_type varchar(40) not null,
          source_id uuid not null,
          source_event varchar(60),
          reason text not null,
          decided_by varchar(200) not null,
          waived_by varchar(200) not null,
          revoked_at timestamptz,
          revoked_by varchar(200),
          revoke_reason text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint ledger_waivers_reason_chk check (length(trim(reason)) > 0),
          constraint ledger_waivers_revoked_chk
            check ((revoked_at is null and revoked_by is null) or (revoked_at is not null and revoked_by is not null))
        )
        """
    )
    op.execute(f"create index if not exists ledger_waivers_tenant_id_idx on {s}.ledger_waivers (tenant_id)")
    op.execute(
        f"create index if not exists ledger_waivers_source_idx on {s}.ledger_waivers (source_type, source_id)"
    )
    op.execute(
        f"create unique index if not exists ledger_waivers_live_uk on {s}.ledger_waivers "
        f"(tenant_id, source_type, source_id, coalesce(source_event, '')) where revoked_at is null"
    )
    op.execute(f"alter table {s}.ledger_waivers enable row level security")
    op.execute(f"drop policy if exists tenant_isolation on {s}.ledger_waivers")
    op.execute(
        f"""
        create policy tenant_isolation on {s}.ledger_waivers
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".ledger_waivers')
