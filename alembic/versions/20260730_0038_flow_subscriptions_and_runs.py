"""hosted flow driving: what ORYH advances here, and what it did

Revision ID: 20260730_0038
Revises: 20260730_0037
Create Date: 2026-07-29 12:00:00

`flow_subscriptions` is enrolment, not policy: it records *that* one entity
type's routing was handed to the platform, never *how* it routes. The two
fields that could have hidden business knowledge deliberately point outward
instead — `driver_skill` names the tenant's own skill, `queue_filter` their own
lifecycle's in-flight states — so the dispatcher stays mechanical and a
tenant-defined object type needs no code to be driven.

`flow_runs` is the envelope around the agent's work. Business writes are
already in the audit trail; this answers "has your agent been running, what did
it find, and where did it stop" without making anyone read that trail.

Both are platform-written and tenant-read, so the RLS policies follow the
api_keys shape (writes accept the tenant GUC *or* the platform GUC) rather than
the strict tenant-only one — a subscription is created by an operator during
a commercial arrangement, before any tenant credential is in play.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260730_0038"
down_revision = "20260730_0037"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".flow_subscriptions (
          id uuid primary key,
          tenant_id uuid not null,
          -- the vocabulary todos and approval records already use: a builtin
          -- family (timesheet_header, sales_quotation, …) or a tenant-defined
          -- object type (warranty_card)
          entity_type varchar(100) not null,
          driver_skill varchar(150) not null,
          queue_filter_jsonb jsonb not null default '{{}}'::jsonb,
          cadence_seconds integer not null default 300,
          enabled boolean not null default true,
          api_key_id uuid references "{schema}".api_keys (id),
          created_by varchar(100),
          created_at timestamptz not null default now(),
          updated_at timestamptz,
          constraint flow_subscriptions_entity_uk unique (tenant_id, entity_type)
        )
        """
    )
    op.execute(
        'create index if not exists flow_subscriptions_tenant_idx '
        f'on "{schema}".flow_subscriptions (tenant_id)'
    )
    op.execute(
        f"""
        create table if not exists "{schema}".flow_runs (
          id uuid primary key,
          tenant_id uuid not null,
          subscription_id uuid references "{schema}".flow_subscriptions (id),
          entity_type varchar(100) not null,
          trigger varchar(20) not null default 'cadence',
          status varchar(20) not null default 'running',
          started_at timestamptz not null,
          finished_at timestamptz,
          queue_size integer,
          items_advanced integer,
          error text,
          detail_jsonb jsonb not null default '{{}}'::jsonb,
          recorded_by varchar(100),
          created_at timestamptz not null default now(),
          updated_at timestamptz
        )
        """
    )
    # "what happened here lately" and "is anything still open" are the only two
    # questions this table is asked, from the console and from operations.
    op.execute(
        'create index if not exists flow_runs_tenant_started_idx '
        f'on "{schema}".flow_runs (tenant_id, started_at desc)'
    )
    op.execute(
        'create index if not exists flow_runs_open_idx '
        f'on "{schema}".flow_runs (tenant_id, entity_type) '
        "where status = 'running'"
    )
    op.execute(
        'create index if not exists flow_runs_subscription_idx '
        f'on "{schema}".flow_runs (subscription_id)'
    )

    for table in ("flow_subscriptions", "flow_runs"):
        op.execute(f'alter table "{schema}".{table} enable row level security')
        for policy in ("tenant_read", "platform_write", "platform_update"):
            op.execute(f'drop policy if exists {policy} on "{schema}".{table}')
        op.execute(
            f"""
            create policy tenant_read on "{schema}".{table}
              for select using ({TENANT_MATCH} or {PLATFORM_ON})
            """
        )
        op.execute(
            f"""
            create policy platform_write on "{schema}".{table}
              for insert with check ({TENANT_MATCH} or {PLATFORM_ON})
            """
        )
        op.execute(
            f"""
            create policy platform_update on "{schema}".{table}
              for update using ({TENANT_MATCH} or {PLATFORM_ON})
              with check ({TENANT_MATCH} or {PLATFORM_ON})
            """
        )

    op.execute(
        f"""
        do $$
        begin
          if exists (select 1 from pg_roles where rolname = 'oryh_app') then
            grant select, insert, update, delete on all tables in schema "{schema}" to oryh_app;
          end if;
        end
        $$
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".flow_runs')
    op.execute(f'drop table if exists "{schema}".flow_subscriptions')
