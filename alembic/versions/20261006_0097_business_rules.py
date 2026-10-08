"""Business rules: policies generalised, workflow definitions folded in

Revision ID: 20261006_0097
Revises: 20260924_0096
Create Date: 2026-10-06 12:00:00

A workspace's own business logic lived in four places with four lifecycles:
`policies` (versioned, published, effective-dated, gated), `workflow_definitions`
(append-only text per object type, no dates, no gate, no draft), a skill's
calibration, and the state machine. The first two were the same kind of thing —
tenant-authored prose an agent reads — told apart by what they are keyed to and
who reads them, and those are properties of a row, not of a table.

So `policies` becomes `business_rules` and gains `kind`: `policy` (what it was),
`approval_flow` (what a workflow definition was), `data_rule` (what a document
must satisfy when filed — the "submission requirements" half of a definition,
now its own row so the submit skill reads it without seeing the routing) and
`linkage` (what happens elsewhere when a document reaches a state). The three
scoped kinds carry `entity_kind`, `object_type` and `name`; `origin` and
`catalog_hash` mark rows seeded from the shipped catalog.

Every `workflow_definitions` row is copied in as an `approval_flow` rule, whole:
version preserved, `active` → `published`, `superseded` → `superseded`, the
publish attributed to whoever published it and dated when they did. The text is
not split into routing and requirements — that is an editor's judgement, and
the setup report asks for it. `workflow_definitions` itself stays, untouched and
no longer written, as the rollback buffer until the next migration drops it.

The constraint names keep their `policies_` prefix: a rename buys nothing and
an error message prints the name.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261006_0097"
down_revision = "20260924_0096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".policies rename to business_rules')
    for statement in (
        # a scoped kind's code is generated from its scope — up to 14 + 16 + 100 + 1 + 100
        # characters — and the seeded workspaces already hold 57; policy codes stay ≤ 50
        f'alter table "{schema}".business_rules alter column code type varchar(255)',
        f'alter table "{schema}".business_rules add column if not exists kind varchar(20) not null default \'policy\'',
        f'alter table "{schema}".business_rules add column if not exists entity_kind varchar(20)',
        f'alter table "{schema}".business_rules add column if not exists object_type varchar(100)',
        f'alter table "{schema}".business_rules add column if not exists name varchar(100)',
        f'alter table "{schema}".business_rules add column if not exists origin varchar(20) not null default \'tenant\'',
        f'alter table "{schema}".business_rules add column if not exists catalog_hash varchar(64)',
        # a policy carries its category; the other kinds are classified by kind
        f'alter table "{schema}".business_rules alter column category drop not null',
        f'alter table "{schema}".business_rules add constraint business_rules_kind_ck '
        "check (kind in ('policy', 'approval_flow', 'data_rule', 'linkage'))",
        f'alter table "{schema}".business_rules add constraint business_rules_entity_kind_chk '
        "check (entity_kind in ('builtin', 'business_object'))",
        f'alter table "{schema}".business_rules add constraint business_rules_origin_chk '
        "check (origin in ('catalog', 'tenant'))",
        f'alter table "{schema}".business_rules add constraint business_rules_scope_ck '
        "check (kind = 'policy' or (entity_kind is not null and object_type is not null and name is not null))",
        f'alter table "{schema}".business_rules add constraint business_rules_category_ck '
        "check (kind <> 'policy' or category is not null)",
        'create index if not exists business_rules_scope_idx on '
        f'"{schema}".business_rules (tenant_id, kind, entity_kind, object_type, status)',
    ):
        op.execute(statement)

    # every workflow definition, whole, as an approval_flow rule
    op.execute(
        f"""
        insert into "{schema}".business_rules (
            id, tenant_id, code, version, kind, entity_kind, object_type, name, origin,
            category, title, summary, body, rules_json, visibility, required_capability,
            status, effective_from, effective_thru, published_at, published_by, supersedes_id,
            attachment_id, owner_employee_id, created_by, custom_fields_jsonb, created_at, updated_at
        )
        select
            w.id, w.tenant_id,
            'approval_flow:' || w.entity_kind || ':' || w.object_type || ':' || w.name,
            w.version, 'approval_flow', w.entity_kind, w.object_type, w.name, 'tenant',
            null, w.object_type || ' 流程定义', null, w.definition_text, null, 'internal', null,
            case w.status when 'active' then 'published' else 'superseded' end,
            w.created_at::date,
            null,
            w.created_at, coalesce(w.created_by, 'migration:20261006_0097'),
            (select p.id from "{schema}".workflow_definitions p
              where p.tenant_id = w.tenant_id and p.entity_kind = w.entity_kind
                and p.object_type = w.object_type and p.name = w.name
                and p.version = w.version - 1),
            null, null, w.created_by, '{{}}'::jsonb, w.created_at, w.created_at
        from "{schema}".workflow_definitions w
        where not exists (select 1 from "{schema}".business_rules b where b.id = w.id)
        """
    )
    # a superseded version's effective_thru is the day before its successor
    # started — or its own first day, when both were published the same day
    # (the seeded workspaces hold such pairs), since a period may not end
    # before it begins
    op.execute(
        f"""
        update "{schema}".business_rules b
           set effective_thru = greatest((n.effective_from - interval '1 day')::date, b.effective_from)
          from "{schema}".business_rules n
         where b.kind = 'approval_flow' and b.status = 'superseded'
           and n.supersedes_id = b.id and n.effective_from is not null
           and (b.effective_thru is null or b.effective_thru >= n.effective_from)
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    # rules published after the upgrade are lost on the way back; the
    # workflow_definitions table was never written since, so it is whole
    op.execute(f'delete from "{schema}".business_rules where kind <> \'policy\'')
    for statement in (
        f'drop index if exists "{schema}".business_rules_scope_idx',
        f'alter table "{schema}".business_rules drop constraint if exists business_rules_category_ck',
        f'alter table "{schema}".business_rules drop constraint if exists business_rules_scope_ck',
        f'alter table "{schema}".business_rules drop constraint if exists business_rules_origin_chk',
        f'alter table "{schema}".business_rules drop constraint if exists business_rules_entity_kind_chk',
        f'alter table "{schema}".business_rules drop constraint if exists business_rules_kind_ck',
        f'alter table "{schema}".business_rules alter column category set not null',
        # only policy rows remain, and their codes were validated at 50
        f'alter table "{schema}".business_rules alter column code type varchar(50)',
        f'alter table "{schema}".business_rules drop column if exists catalog_hash',
        f'alter table "{schema}".business_rules drop column if exists origin',
        f'alter table "{schema}".business_rules drop column if exists name',
        f'alter table "{schema}".business_rules drop column if exists object_type',
        f'alter table "{schema}".business_rules drop column if exists entity_kind',
        f'alter table "{schema}".business_rules drop column if exists kind',
        f'alter table "{schema}".business_rules rename to policies',
    ):
        op.execute(statement)
