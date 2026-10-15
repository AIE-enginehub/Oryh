"""A deal's parties, a project's provenance, relations between customers

Revision ID: 20261015_0099
Revises: 20261007_0098
Create Date: 2026-10-15 10:00:00

Plan docs/plans/deal-parties-and-project-links-2026-10-14.zh.md. A referral
deal — a friend introduces a client, signs with them and subcontracts to us —
had nowhere to live: a project knew its client only as free text, a deal had
one customer and a cast drawn from that customer alone, two customers could
not be related, and a contract could point only at another of ours.

Additive and forward-compatible:

* `projects` gains `customer_id`, `opportunity_id`, `contract_id` and
  `owner_employee_id`; `client` stays as the typed name or the customer's
  name snapshot. `customer_id` is backfilled where `client` matches exactly
  one customer's name in the tenant — a match that is ambiguous or absent
  leaves it empty, and the count per tenant is printed for the operator.
* `document_parties`: the parties to an opportunity, a contract or a project
  beyond the carrier's own customer (the contracting party is derived from
  `customer_id` on every read and never stored).
* `customer_relations`: one customer is the `relation_type` of another, dated.
* `contracts` gains `opportunity_id` (the deal it closes) and `upstream_jsonb`
  (a reference to a contract that is not ours but governs this one).
* `leads` gains `referrer_customer_id` and `referrer_contact_id`.

The vocabularies (`deal_party_role`, `customer_relation_type`, `lead_source`,
the `upstream_reference` document type) are seeded by the type-option sync
at API start, as every shipped vocabulary is.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261015_0099"
down_revision = "20261007_0098"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


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
    for statement in (
        f'alter table "{schema}".projects add column if not exists customer_id uuid references "{schema}".customers (id)',
        f'alter table "{schema}".projects add column if not exists opportunity_id uuid references "{schema}".opportunities (id)',
        f'alter table "{schema}".projects add column if not exists contract_id uuid references "{schema}".contracts (id)',
        f'alter table "{schema}".projects add column if not exists owner_employee_id uuid references "{schema}".employees (id)',
        f'create index if not exists ix_projects_customer_id on "{schema}".projects (customer_id)',
        f'create index if not exists ix_projects_opportunity_id on "{schema}".projects (opportunity_id)',
        f'create index if not exists ix_projects_contract_id on "{schema}".projects (contract_id)',
        f'create index if not exists ix_projects_owner_employee_id on "{schema}".projects (owner_employee_id)',
        f'alter table "{schema}".contracts add column if not exists opportunity_id uuid references "{schema}".opportunities (id)',
        f'alter table "{schema}".contracts add column if not exists upstream_jsonb jsonb',
        f'create index if not exists ix_contracts_opportunity_id on "{schema}".contracts (opportunity_id)',
        f'alter table "{schema}".leads add column if not exists referrer_customer_id uuid references "{schema}".customers (id)',
        f'alter table "{schema}".leads add column if not exists referrer_contact_id uuid references "{schema}".customer_contacts (id)',
        f'create index if not exists ix_leads_referrer_customer_id on "{schema}".leads (referrer_customer_id)',
        f'create index if not exists ix_leads_referrer_contact_id on "{schema}".leads (referrer_contact_id)',
    ):
        op.execute(statement)

    op.execute(
        f"""
        create table if not exists "{schema}".document_parties (
          id uuid primary key,
          tenant_id uuid not null,
          entity_type varchar(30) not null,
          entity_id uuid not null,
          customer_id uuid not null references "{schema}".customers (id),
          party_role varchar(50) not null,
          contact_id uuid references "{schema}".customer_contacts (id),
          terms_jsonb jsonb,
          remarks text,
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint document_parties_role_uk unique (entity_type, entity_id, customer_id, party_role),
          constraint document_parties_entity_type_ck check (entity_type in ('opportunity', 'contract', 'project')),
          constraint document_parties_not_contracting_ck check (party_role <> 'contracting')
        )
        """
    )
    op.execute(f'create index if not exists document_parties_carrier_idx on "{schema}".document_parties (tenant_id, entity_type, entity_id)')
    _isolate(schema, "document_parties", ("tenant_id", "customer_id", "contact_id"))

    op.execute(
        f"""
        create table if not exists "{schema}".customer_relations (
          id uuid primary key,
          tenant_id uuid not null,
          customer_id uuid not null references "{schema}".customers (id),
          related_customer_id uuid not null references "{schema}".customers (id),
          relation_type varchar(50) not null,
          effective_from date,
          effective_to date,
          remarks text,
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint customer_relations_uk unique (customer_id, related_customer_id, relation_type, effective_from),
          constraint customer_relations_two_parties_ck check (customer_id <> related_customer_id),
          constraint customer_relations_period_ck check (effective_to is null or effective_from is null or effective_to >= effective_from)
        )
        """
    )
    _isolate(schema, "customer_relations", ("tenant_id", "customer_id", "related_customer_id"))

    # backfill: a project whose typed client matches exactly one customer's
    # name in its tenant now points at that customer; the rest stay empty
    # and are counted for the operator
    bind = op.get_bind()
    bind.exec_driver_sql(
        f"""
        update "{schema}".projects p
           set customer_id = m.customer_id
          from (
            select pr.id as project_id, min(c.id::text)::uuid as customer_id
              from "{schema}".projects pr
              join "{schema}".customers c on c.tenant_id = pr.tenant_id and c.name = pr.client
             where pr.customer_id is null and pr.client is not null and pr.client <> ''
             group by pr.id
            having count(*) = 1
          ) m
         where p.id = m.project_id
        """
    )
    rows = bind.exec_driver_sql(
        f"""
        select t.slug, count(*) from "{schema}".projects p join "{schema}".tenants t on t.id = p.tenant_id
         where p.customer_id is null and p.client is not null and p.client <> ''
         group by t.slug order by t.slug
        """
    ).all()
    for slug, count in rows:
        print(f"0099: tenant {slug}: {count} project(s) whose client matched no single customer — link them in the console")


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for statement in (
        f'drop table if exists "{schema}".customer_relations',
        f'drop table if exists "{schema}".document_parties',
        f'alter table "{schema}".leads drop column if exists referrer_contact_id',
        f'alter table "{schema}".leads drop column if exists referrer_customer_id',
        f'alter table "{schema}".contracts drop column if exists upstream_jsonb',
        f'alter table "{schema}".contracts drop column if exists opportunity_id',
        f'alter table "{schema}".projects drop column if exists owner_employee_id',
        f'alter table "{schema}".projects drop column if exists contract_id',
        f'alter table "{schema}".projects drop column if exists opportunity_id',
        f'alter table "{schema}".projects drop column if exists customer_id',
    ):
        op.execute(statement)
