"""Project tasks, their dependencies, milestones, and hours per task

Revision ID: 20261115_0110
Revises: 20261109_0109
Create Date: 2026-11-15 10:00:00

Plan docs/plans/project-management-2026-11-15.md, phase 1. Additive only:

* `project_tasks` — a project's work breakdown, a tree. Status is tenant
  vocabulary (`project_task_status`): the server reads nothing from it.
* `project_task_dependencies` — which task waits on which, stated as facts;
  nothing moves a date by itself.
* `project_milestones` — dated commitments, when each was reached and who
  confirmed it, the contract clause that pays on it and the invoice that
  billed it.
* `timesheet_entries.task_id` — hours against a real task. The free-text
  `task` stays for entries that name none.

Nothing is backfilled: free-text tasks are not guessed into rows.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261115_0110"
down_revision = "20261109_0109"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"
TABLES = ("project_tasks", "project_task_dependencies", "project_milestones")


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    s = f'"{schema}"'
    op.execute(
        f"""
        create table if not exists {s}.project_tasks (
          id uuid primary key,
          tenant_id uuid not null,
          project_id uuid not null references {s}.projects (id),
          parent_task_id uuid references {s}.project_tasks (id),
          task_code varchar(64),
          name varchar(200) not null,
          assignee_employee_id uuid references {s}.employees (id),
          planned_start date,
          planned_end date,
          actual_start date,
          actual_end date,
          planned_hours numeric(8, 2),
          status varchar(30) not null default 'not_started',
          sort_order integer,
          description text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint project_tasks_not_own_parent_chk check (parent_task_id is null or parent_task_id <> id),
          constraint project_tasks_planned_order_chk
            check (planned_start is null or planned_end is null or planned_end >= planned_start),
          constraint project_tasks_actual_order_chk
            check (actual_start is null or actual_end is null or actual_end >= actual_start),
          constraint project_tasks_planned_hours_chk check (planned_hours is null or planned_hours >= 0)
        )
        """
    )
    op.execute(
        f"create unique index if not exists project_tasks_code_uk on {s}.project_tasks "
        f"(tenant_id, project_id, task_code) where task_code is not null"
    )
    op.execute(
        f"""
        create table if not exists {s}.project_task_dependencies (
          id uuid primary key,
          tenant_id uuid not null,
          predecessor_task_id uuid not null references {s}.project_tasks (id),
          successor_task_id uuid not null references {s}.project_tasks (id),
          dependency_type varchar(10) not null default 'FS',
          lag_days integer not null default 0,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint project_task_dependencies_pair_uk unique (tenant_id, predecessor_task_id, successor_task_id),
          constraint project_task_dependencies_dependency_type_chk check (dependency_type in ('FF', 'FS', 'SF', 'SS')),
          constraint project_task_dependencies_not_self_chk check (predecessor_task_id <> successor_task_id)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists {s}.project_milestones (
          id uuid primary key,
          tenant_id uuid not null,
          project_id uuid not null references {s}.projects (id),
          name varchar(200) not null,
          due_date date not null,
          reached_on date,
          confirmed_by varchar(200),
          evidence_attachment_id uuid references {s}.attachments (id),
          contract_term_id uuid references {s}.contract_terms (id),
          invoice_id uuid references {s}.invoices (id),
          status varchar(20) not null default 'open',
          description text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint project_milestones_status_chk check (status in ('cancelled', 'open', 'reached')),
          constraint project_milestones_reached_chk
            check ((status = 'reached' and reached_on is not null and confirmed_by is not null) or (status <> 'reached' and reached_on is null))
        )
        """
    )
    indexes = {
        "project_tasks": ("tenant_id", "project_id", "parent_task_id", "assignee_employee_id"),
        "project_task_dependencies": ("tenant_id", "predecessor_task_id", "successor_task_id"),
        "project_milestones": ("tenant_id", "project_id", "contract_term_id", "invoice_id"),
    }
    for table, columns in indexes.items():
        for column in columns:
            op.execute(f"create index if not exists {table}_{column}_idx on {s}.{table} ({column})")
    op.execute(
        f"alter table {s}.timesheet_entries add column if not exists task_id uuid references {s}.project_tasks (id)"
    )
    op.execute(f"create index if not exists timesheet_entries_task_id_idx on {s}.timesheet_entries (task_id)")
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
    op.execute(f"alter table {s}.timesheet_entries drop column if exists task_id")
    for table in ("project_milestones", "project_task_dependencies", "project_tasks"):
        op.execute(f"drop table if exists {s}.{table}")
