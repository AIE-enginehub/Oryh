"""Exchange rates: dated rate facts with their source, cited by journal lines

Revision ID: 20261127_0118
Revises: 20261127_0117
Create Date: 2026-11-27 15:00:00

Plan docs/plans/foreign-currency-2026-11-27.md, phase 1. A rate is a fact
the workspace imports with its type and source; the server never picks or
fetches one. A journal line that converts may cite the fact it used, and a
cited rate never changes.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261127_0118"
down_revision = "20261127_0117"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(
        f"""
        create table if not exists {s}.exchange_rates (
          id uuid primary key,
          tenant_id uuid not null,
          from_currency varchar(3) not null,
          to_currency varchar(3) not null,
          rate numeric(18, 8) not null,
          rate_date date not null,
          rate_type varchar(50) not null,
          source varchar(200) not null,
          created_by varchar(200),
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint exchange_rates_fact_uk unique (tenant_id, from_currency, to_currency, rate_date, rate_type),
          constraint exchange_rates_rate_chk check (rate > 0),
          constraint exchange_rates_pair_chk check (from_currency <> to_currency),
          constraint exchange_rates_source_chk check (length(trim(source)) > 0)
        )
        """
    )
    op.execute(f"create index if not exists exchange_rates_tenant_id_idx on {s}.exchange_rates (tenant_id)")
    op.execute(
        f"create index if not exists exchange_rates_lookup_idx on {s}.exchange_rates "
        f"(tenant_id, from_currency, to_currency, rate_type, rate_date)"
    )
    op.execute(f"alter table {s}.exchange_rates enable row level security")
    op.execute(f"drop policy if exists tenant_isolation on {s}.exchange_rates")
    op.execute(
        f"""
        create policy tenant_isolation on {s}.exchange_rates
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )
    op.execute(
        f"alter table {s}.journal_lines add column if not exists exchange_rate_id uuid "
        f"references {s}.exchange_rates(id)"
    )
    op.execute(
        f"create index if not exists journal_lines_exchange_rate_id_idx on {s}.journal_lines (exchange_rate_id)"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(f"drop index if exists {s}.journal_lines_exchange_rate_id_idx")
    op.execute(f"alter table {s}.journal_lines drop column if exists exchange_rate_id")
    op.execute(f"drop table if exists {s}.exchange_rates")
