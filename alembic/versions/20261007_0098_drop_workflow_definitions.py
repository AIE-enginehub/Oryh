"""Drop workflow_definitions: the rollback buffer has served its release

Revision ID: 20261007_0098
Revises: 20261006_0097
Create Date: 2026-10-07 10:00:00

`20261006_0097` folded every workflow definition into `business_rules` as an
`approval_flow` and left the old table untouched as the buffer a rollback
would read. The release that carried it ran; the retired doors
(`/workflow-definitions*`, `/policies*`) go with this migration, and so does
the table — nothing has written it since, and every agent reads the rules
by kind now.

Downgrade recreates the table in its last shape and fills it back from the
approval flows, so the previous image finds what it expects: `published` →
`active`, `superseded` → `superseded`, repealed and draft rows left out
(the old table had no words for them).
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261007_0098"
down_revision = "20261006_0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".workflow_definitions')


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for statement in (
        f'''create table "{schema}".workflow_definitions (
            id uuid default gen_random_uuid() not null primary key,
            tenant_id uuid not null,
            entity_kind text default 'business_object' not null,
            object_type text not null,
            name text default 'default' not null,
            version integer default 1 not null,
            definition_text text not null,
            status text default 'active' not null,
            created_by text,
            created_at timestamp with time zone default now() not null,
            constraint workflow_definitions_entity_kind_chk check (entity_kind in ('business_object', 'builtin')),
            constraint workflow_definitions_status_chk check (status in ('active', 'superseded')),
            constraint workflow_definitions_version_chk check (version >= 1),
            constraint workflow_definitions_version_uk unique (tenant_id, entity_kind, object_type, name, version)
        )''',
        f'create index workflow_definitions_tenant_idx on "{schema}".workflow_definitions (tenant_id, entity_kind, object_type, name, status)',
        f'alter table "{schema}".workflow_definitions enable row level security',
        f'''create policy tenant_isolation on "{schema}".workflow_definitions
            using (tenant_id::text = current_setting('app.tenant_id', true)
                   or current_setting('app.is_platform_admin', true) = 'on')
            with check (tenant_id::text = current_setting('app.tenant_id', true))''',
        f'''insert into "{schema}".workflow_definitions
            (id, tenant_id, entity_kind, object_type, name, version, definition_text, status, created_by, created_at)
        select id, tenant_id, entity_kind, object_type, name, version, body,
               case status when 'published' then 'active' else 'superseded' end,
               published_by, coalesce(published_at, created_at)
          from "{schema}".business_rules
         where kind = 'approval_flow' and status in ('published', 'superseded') and deleted_at is null''',
    ):
        op.execute(statement)
