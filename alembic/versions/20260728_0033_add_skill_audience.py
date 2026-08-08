"""skill audience — who a skill is for, beside what it requires

Revision ID: 20260728_0033
Revises: 20260726_0032
Create Date: 2026-07-28 10:00:00

Distribution had one axis: `required_capability`, i.e. "are you allowed to do
this". It never expressed "who is this for", so narrowing a skill to one team
meant minting a capability purely to gate distribution — the very thing
docs/scoped-skill-capabilities.md set out to stop.

`distribution_mode` is an explicit switch rather than something inferred from
whether audience rows exist: deleting the last row of an inferred audience
would silently re-broadcast the skill to everyone who passes its capability
gate, and a per-row edit (delete-then-add) would open a window where it is
briefly visible to all. With the flag, that window narrows to "nobody" —
harmless, since sync is not instantaneous.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260728_0033"
down_revision = "20260726_0032"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        alter table "{schema}".tenant_skills
          add column if not exists distribution_mode varchar(20) not null default 'capability'
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".tenant_skill_assignments (
          id uuid primary key,
          tenant_id uuid not null,
          skill_id uuid not null references "{schema}".tenant_skills (id) on delete cascade,
          -- 'user' → subject_id is a users.id; 'role' → subject_id is a role
          -- NAME, matching how User.role and permission grants already refer
          -- to roles everywhere else.
          subject_type varchar(20) not null,
          subject_id varchar(100) not null,
          created_by varchar(100),
          created_at timestamptz not null default now(),
          constraint tenant_skill_assignments_uk
            unique (tenant_id, skill_id, subject_type, subject_id)
        )
        """
    )
    op.execute(
        'create index if not exists tenant_skill_assignments_tenant_idx '
        f'on "{schema}".tenant_skill_assignments (tenant_id)'
    )
    op.execute(
        'create index if not exists tenant_skill_assignments_skill_idx '
        f'on "{schema}".tenant_skill_assignments (skill_id)'
    )
    # the reverse question — "which skills does this person/role receive" — is
    # what the console's troubleshooting view and every bundle render ask
    op.execute(
        'create index if not exists tenant_skill_assignments_subject_idx '
        f'on "{schema}".tenant_skill_assignments (tenant_id, subject_type, subject_id)'
    )
    op.execute(f'alter table "{schema}".tenant_skill_assignments enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".tenant_skill_assignments')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".tenant_skill_assignments
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )
    op.execute(
        f"""
        do $$
        begin
          if exists (select 1 from pg_roles where rolname = 'oryh_app') then
            grant select, insert, update, delete on all tables in schema "{schema}" to oryh_app;
          end if;
        end $$
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".tenant_skill_assignments')
    op.execute(f'alter table "{schema}".tenant_skills drop column if exists distribution_mode')
