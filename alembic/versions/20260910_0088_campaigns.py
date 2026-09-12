"""campaigns: where leads come from, as a builtin document with members

Revision ID: 20260910_0088
Revises: 20260909_0087
Create Date: 2026-09-10 10:00:00

A CAMPAIGN is a marketing effort — a trade fair, a webinar, a mailing — that
leads and deals are attributed to. Salesforce's Campaign reduced to facts:
when it ran, what it cost, who owns it, who was reached (the MEMBERS: a
lead, or a customer and optionally one of its contacts, exactly one party
per row). What it earned is never stored: `leads.campaign_id` and
`opportunities.campaign_id` are the attribution, read live by the detail.

Not personal (marketing runs it for everyone) and approval-free, so one
functional grant (`campaign.manage`) files and advances. Statuses carry no
CHECK, like every builtin document. The entity-type CHECKs on todos and
approval_records re-derive from the registry, the 0071 pattern, so a todo
may point at a campaign the day the family exists.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings
from app.core.entity_types import APPROVAL_ENTITY_TYPES, TODO_ENTITY_TYPES

revision = "20260910_0088"
down_revision = "20260909_0087"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".campaigns (
          id uuid primary key,
          tenant_id uuid not null,
          campaign_no varchar(64) not null,
          name varchar(200) not null,
          campaign_type varchar(50),
          parent_campaign_id uuid references "{schema}".campaigns (id),
          employee_id uuid not null references "{schema}".employees (id),
          start_date date,
          end_date date,
          budget numeric(14, 2),
          actual_cost numeric(14, 2),
          expected_revenue numeric(14, 2),
          currency varchar(3) not null default 'CNY',
          status varchar(50) not null default 'planned',
          description text,
          remarks text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint campaigns_campaign_no_uk unique (tenant_id, campaign_no)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".campaign_members (
          id uuid primary key,
          tenant_id uuid not null,
          campaign_id uuid not null references "{schema}".campaigns (id),
          lead_id uuid references "{schema}".leads (id),
          customer_id uuid references "{schema}".customers (id),
          contact_id uuid references "{schema}".customer_contacts (id),
          member_status varchar(50) not null default 'targeted',
          responded_at timestamptz,
          remarks text,
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint campaign_members_one_party_check
            check ((lead_id is not null) <> (customer_id is not null))
        )
        """
    )
    op.execute(
        f'create unique index if not exists campaign_members_lead_uk '
        f'on "{schema}".campaign_members (tenant_id, campaign_id, lead_id) '
        f"where lead_id is not null"
    )
    op.execute(
        f'create unique index if not exists campaign_members_customer_uk '
        f'on "{schema}".campaign_members (tenant_id, campaign_id, customer_id) '
        f"where customer_id is not null and contact_id is null"
    )
    op.execute(
        f'create unique index if not exists campaign_members_contact_uk '
        f'on "{schema}".campaign_members (tenant_id, campaign_id, customer_id, contact_id) '
        f"where contact_id is not null"
    )
    for table, columns in (
        ("campaigns", ("tenant_id", "employee_id", "parent_campaign_id")),
        ("campaign_members", ("tenant_id", "campaign_id", "lead_id", "customer_id", "contact_id")),
    ):
        for column in columns:
            op.execute(
                f'create index if not exists {table}_{column}_idx '
                f'on "{schema}".{table} ({column})'
            )
        op.execute(f'alter table "{schema}".{table} enable row level security')
        op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
        op.execute(
            f"""
            create policy tenant_isolation on "{schema}".{table}
              using ({TENANT_MATCH} or {PLATFORM_ON})
              with check ({TENANT_MATCH})
            """
        )
    # attribution: the lead and the deal name the campaign they came from
    for table in ("leads", "opportunities"):
        op.execute(
            f'alter table "{schema}".{table} '
            f'add column if not exists campaign_id uuid references "{schema}".campaigns (id)'
        )
        op.execute(
            f'create index if not exists {table}_campaign_id_idx '
            f'on "{schema}".{table} (campaign_id)'
        )
    # a todo or an approval fact may now point at a campaign
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
    keep_todo = tuple(t for t in TODO_ENTITY_TYPES if t != "campaign")
    keep_approval = tuple(t for t in APPROVAL_ENTITY_TYPES if t != "campaign")
    for table, name, keep in (
        ("todos", "todos_entity_type_chk", keep_todo),
        ("approval_records", "approval_records_entity_type_chk", keep_approval),
    ):
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {name}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {name} '
            f"check (entity_type in ({_quoted(keep)}))"
        )
    for table in ("leads", "opportunities"):
        op.execute(f'drop index if exists "{schema}".{table}_campaign_id_idx')
        op.execute(f'alter table "{schema}".{table} drop column if exists campaign_id')
    op.execute(f'drop table if exists "{schema}".campaign_members')
    op.execute(f'drop table if exists "{schema}".campaigns')
