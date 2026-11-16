"""Project issues, status reports, and purchases that name a project

Revision ID: 20261116_0111
Revises: 20261115_0110
Create Date: 2026-11-16 10:00:00

Plan docs/plans/project-management-2026-11-15.md, phase 2. Additive only:

* `project_issues` — a project's log of issues, risks and change requests.
  Type, severity and status are tenant vocabulary; the server holds only
  that a resolved issue states its resolution.
* `project_reports` — what the project manager said about a period, with the
  figures it was written from frozen inside it. A published report never
  changes; a correction is the next revision.
* `purchase_requests.project_id`, `purchase_orders.project_id` — bought cost
  reaches the project. Nothing is backfilled and no order inherits its
  request's project: the writer names it.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261116_0111"
down_revision = "20261115_0110"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"
TABLES = ("project_issues", "project_reports")


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(
        f"""
        create table if not exists {s}.project_issues (
          id uuid primary key,
          tenant_id uuid not null,
          project_id uuid not null references {s}.projects (id),
          task_id uuid references {s}.project_tasks (id),
          issue_no varchar(64) not null,
          issue_type varchar(30) not null default 'issue',
          title varchar(200) not null,
          description text,
          severity varchar(30),
          raised_by_employee_id uuid references {s}.employees (id),
          owner_employee_id uuid references {s}.employees (id),
          raised_at timestamptz not null default now(),
          resolved_at timestamptz,
          resolution text,
          status varchar(30) not null default 'open',
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint project_issues_issue_no_uk unique (tenant_id, issue_no),
          constraint project_issues_resolution_chk check (resolved_at is null or resolution is not null)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists {s}.project_reports (
          id uuid primary key,
          tenant_id uuid not null,
          project_id uuid not null references {s}.projects (id),
          period_start date not null,
          period_end date not null,
          revision integer not null default 1,
          health varchar(10) not null,
          summary text not null,
          done text,
          next_steps text,
          blockers text,
          figures jsonb,
          status varchar(20) not null default 'draft',
          published_by varchar(200),
          published_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint project_reports_period_uk unique (tenant_id, project_id, period_start, revision),
          constraint project_reports_health_chk check (health in ('amber', 'green', 'red')),
          constraint project_reports_status_chk check (status in ('draft', 'published')),
          constraint project_reports_period_order_chk check (period_end >= period_start),
          constraint project_reports_revision_chk check (revision >= 1),
          constraint project_reports_published_chk
            check ((status = 'published' and published_at is not null and figures is not null) or (status = 'draft' and published_at is null))
        )
        """
    )
    indexes = {
        "project_issues": ("tenant_id", "project_id", "task_id", "owner_employee_id", "raised_by_employee_id"),
        "project_reports": ("tenant_id", "project_id"),
    }
    for table, columns in indexes.items():
        for column in columns:
            op.execute(f"create index if not exists {table}_{column}_idx on {s}.{table} ({column})")
    for table in ("purchase_requests", "purchase_orders"):
        op.execute(f"alter table {s}.{table} add column if not exists project_id uuid references {s}.projects (id)")
        op.execute(f"create index if not exists {table}_project_id_idx on {s}.{table} (project_id)")
    for table in TABLES:
        op.execute(f"alter table {s}.{table} enable row level security")
        op.execute(f"drop policy if exists tenant_isolation on {s}.{table}")
        op.execute(
            f"""
            create policy tenant_isolation on {s}.{table}
              using ({TENANT_MATCH} or {PLATFORM_ON})
              with check ({TENANT_MATCH})
            """
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    for table in ("purchase_orders", "purchase_requests"):
        op.execute(f"alter table {s}.{table} drop column if exists project_id")
    for table in ("project_reports", "project_issues"):
        op.execute(f"drop table if exists {s}.{table}")
