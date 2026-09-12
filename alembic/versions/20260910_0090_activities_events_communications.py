"""the record of contact: activities, events with participants, and
communication events

Revision ID: 20260910_0090
Revises: 20260910_0089
Create Date: 2026-09-10 16:00:00

An ACTIVITY is a contact with a customer that already happened — a call, a
visit, a meeting, a message — with what was said and what comes next: the
CRM plan's "客户跟进记录", the fact the agent used to keep in the
conversation. An EVENT is something scheduled, a builtin document family
(planned → held | cancelled) with PARTICIPANTS (one of ours or one of the
customer's per row); when held, the activity is logged from it. A
COMMUNICATION EVENT is one message that passed — an email, a text — as a
fact after the fact; the channel's own message id keeps the same mail from
being recorded twice. The entity-type CHECKs re-derive from the registry so
a todo may hang off an event.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings
from app.core.entity_types import APPROVAL_ENTITY_TYPES, TODO_ENTITY_TYPES

revision = "20260910_0090"
down_revision = "20260910_0089"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _isolate(schema: str, table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.execute(f'create index if not exists {table}_{column}_idx on "{schema}".{table} ({column})')
    op.execute(f'alter table "{schema}".{table} enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".{table}
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".events (
          id uuid primary key,
          tenant_id uuid not null,
          event_no varchar(64) not null,
          subject varchar(200) not null,
          event_type varchar(50),
          employee_id uuid not null references "{schema}".employees (id),
          customer_id uuid references "{schema}".customers (id),
          lead_id uuid references "{schema}".leads (id),
          opportunity_id uuid references "{schema}".opportunities (id),
          starts_at timestamptz not null,
          ends_at timestamptz,
          location varchar(300),
          status varchar(50) not null default 'planned',
          description text,
          remarks text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint events_event_no_uk unique (tenant_id, event_no)
        )
        """
    )
    _isolate(schema, "events", ("tenant_id", "employee_id", "customer_id", "lead_id", "opportunity_id"))
    op.execute(
        f"""
        create table if not exists "{schema}".event_participants (
          id uuid primary key,
          tenant_id uuid not null,
          event_id uuid not null references "{schema}".events (id),
          employee_id uuid references "{schema}".employees (id),
          contact_id uuid references "{schema}".customer_contacts (id),
          response varchar(50),
          remarks text,
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint event_participants_one_person_check
            check ((employee_id is not null) <> (contact_id is not null))
        )
        """
    )
    op.execute(
        f'create unique index if not exists event_participants_employee_uk '
        f'on "{schema}".event_participants (tenant_id, event_id, employee_id) where employee_id is not null'
    )
    op.execute(
        f'create unique index if not exists event_participants_contact_uk '
        f'on "{schema}".event_participants (tenant_id, event_id, contact_id) where contact_id is not null'
    )
    _isolate(schema, "event_participants", ("tenant_id", "event_id", "employee_id", "contact_id"))
    op.execute(
        f"""
        create table if not exists "{schema}".communication_events (
          id uuid primary key,
          tenant_id uuid not null,
          channel varchar(50) not null,
          direction varchar(20) not null,
          subject varchar(500),
          body text,
          from_address varchar(320),
          to_addresses jsonb not null default '[]'::jsonb,
          cc_addresses jsonb not null default '[]'::jsonb,
          occurred_at timestamptz not null,
          message_id varchar(255),
          thread_id varchar(255),
          employee_id uuid references "{schema}".employees (id),
          customer_id uuid references "{schema}".customers (id),
          lead_id uuid references "{schema}".leads (id),
          opportunity_id uuid references "{schema}".opportunities (id),
          contact_id uuid references "{schema}".customer_contacts (id),
          remarks text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint communication_events_direction_check check (direction in ('inbound', 'outbound')),
          constraint communication_events_names_a_party_check
            check (customer_id is not null or lead_id is not null or opportunity_id is not null or contact_id is not null)
        )
        """
    )
    op.execute(
        f'create unique index if not exists communication_events_message_uk '
        f'on "{schema}".communication_events (tenant_id, message_id) where message_id is not null'
    )
    _isolate(schema, "communication_events",
             ("tenant_id", "thread_id", "employee_id", "customer_id", "lead_id", "opportunity_id", "contact_id"))
    op.execute(
        f"""
        create table if not exists "{schema}".activities (
          id uuid primary key,
          tenant_id uuid not null,
          customer_id uuid references "{schema}".customers (id),
          lead_id uuid references "{schema}".leads (id),
          opportunity_id uuid references "{schema}".opportunities (id),
          contact_id uuid references "{schema}".customer_contacts (id),
          employee_id uuid not null references "{schema}".employees (id),
          activity_type varchar(50) not null,
          occurred_at timestamptz not null,
          subject varchar(200) not null,
          content text,
          source_text text,
          outcome varchar(50),
          next_action varchar(500),
          next_action_at timestamptz,
          event_id uuid references "{schema}".events (id),
          communication_event_id uuid references "{schema}".communication_events (id),
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint activities_names_a_party_check
            check (customer_id is not null or lead_id is not null or opportunity_id is not null)
        )
        """
    )
    _isolate(schema, "activities",
             ("tenant_id", "customer_id", "lead_id", "opportunity_id", "contact_id", "employee_id", "event_id",
              "communication_event_id"))
    for table, name, allowed in (
        ("todos", "todos_entity_type_chk", TODO_ENTITY_TYPES),
        ("approval_records", "approval_records_entity_type_chk", APPROVAL_ENTITY_TYPES),
    ):
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {name}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {name} '
            f"check (entity_type in ({_quoted(allowed)}))"
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    keep_todo = tuple(t for t in TODO_ENTITY_TYPES if t != "event")
    keep_approval = tuple(t for t in APPROVAL_ENTITY_TYPES if t != "event")
    for table, name, keep in (
        ("todos", "todos_entity_type_chk", keep_todo),
        ("approval_records", "approval_records_entity_type_chk", keep_approval),
    ):
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {name}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {name} '
            f"check (entity_type in ({_quoted(keep)}))"
        )
    for table in ("activities", "communication_events", "event_participants", "events"):
        op.execute(f'drop table if exists "{schema}".{table}')
