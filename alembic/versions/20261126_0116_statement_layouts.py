"""Statement layouts: the lines a workspace reports on, and which accounts feed them

Revision ID: 20261126_0116
Revises: 20261125_0115
Create Date: 2026-11-26 09:00:00

Plan docs/plans/financial-statements-2026-11-25.md, phase 2. The default
statements group by `account_type`, which cannot tell cost of sales from
overhead, so they cannot say gross profit. A layout is a statutory or
management format as data: ordered rows, each summing accounts (by id or by
code range) or other rows, with the person who confirmed it. The server
applies it mechanically on each read and lists what no row took.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261126_0116"
down_revision = "20261125_0115"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def _isolate(s: str, table: str) -> None:
    op.execute(f"alter table {s}.{table} enable row level security")
    op.execute(f"drop policy if exists tenant_isolation on {s}.{table}")
    op.execute(
        f"""
        create policy tenant_isolation on {s}.{table}
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(
        f"""
        create table if not exists {s}.statement_layouts (
          id uuid primary key,
          tenant_id uuid not null,
          statement varchar(20) not null,
          name varchar(200) not null,
          is_default boolean not null default false,
          status varchar(20) not null default 'active',
          confirmed_by varchar(200) not null,
          created_by varchar(200),
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint statement_layouts_statement_chk
            check (statement in ('balance_sheet', 'cash_summary', 'income_statement')),
          constraint statement_layouts_status_chk check (status in ('active', 'archived')),
          constraint statement_layouts_confirmed_chk check (length(trim(confirmed_by)) > 0),
          constraint statement_layouts_default_active_chk check ((is_default = false) OR (status = 'active'))
        )
        """
    )
    op.execute(f"create index if not exists statement_layouts_tenant_id_idx on {s}.statement_layouts (tenant_id)")
    op.execute(
        f"create unique index if not exists statement_layouts_default_uk on {s}.statement_layouts "
        f"(tenant_id, statement) where is_default"
    )
    _isolate(s, "statement_layouts")

    op.execute(
        f"""
        create table if not exists {s}.statement_layout_rows (
          id uuid primary key,
          tenant_id uuid not null,
          layout_id uuid not null references {s}.statement_layouts(id) on delete cascade,
          row_no integer not null,
          code varchar(40) not null,
          label varchar(200) not null,
          kind varchar(20) not null,
          accounts jsonb,
          sign smallint not null default 1,
          formula jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint statement_layout_rows_row_no_uk unique (layout_id, row_no),
          constraint statement_layout_rows_code_uk unique (layout_id, code),
          constraint statement_layout_rows_kind_chk check (kind in ('accounts', 'heading', 'total')),
          constraint statement_layout_rows_sign_chk check ((sign = 1) OR (sign = -1)),
          constraint statement_layout_rows_shape_chk check (
            (kind = 'accounts' AND accounts IS NOT NULL AND formula IS NULL)
            OR (kind = 'total' AND formula IS NOT NULL AND accounts IS NULL)
            OR (kind = 'heading' AND accounts IS NULL AND formula IS NULL))
        )
        """
    )
    op.execute(
        f"create index if not exists statement_layout_rows_tenant_id_idx on {s}.statement_layout_rows (tenant_id)"
    )
    op.execute(
        f"create index if not exists statement_layout_rows_layout_id_idx on {s}.statement_layout_rows (layout_id)"
    )
    _isolate(s, "statement_layout_rows")


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".statement_layout_rows')
    op.execute(f'drop table if exists "{schema}".statement_layouts')
