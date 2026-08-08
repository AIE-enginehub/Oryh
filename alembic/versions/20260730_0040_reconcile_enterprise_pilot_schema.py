"""reconcile enterprise pilot schema after the legacy flow revision collision

Revision ID: 20260730_0040
Revises: 20260730_0039
Create Date: 2026-07-30 18:00:00

The first hosted-flow release used revision IDs 20260729_0034 through
20260730_0036.  Before that branch was merged, the enterprise-pilot work used
the same terminal IDs and the flow migrations were renumbered to 0037-0039.
Databases that ran the hosted-flow release therefore arrive here with all flow
objects present but without the enterprise-pilot table: Alembic sees 0036 and
cannot tell which historical 0036 produced it.

This reconciliation is deliberately idempotent.  A database that followed the
linear main migration chain already has the final table and is unchanged.  A
database stopped after the old design-partner migration is renamed forward.
A database that deployed the colliding hosted-flow 0036 gets the final table
created directly.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260730_0040"
down_revision = "20260730_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_name = settings.database_schema
    schema = schema_name.replace('"', '""')
    schema_literal = schema_name.replace("'", "''")
    enterprise_table = f'"{schema}".enterprise_pilot_applications'
    design_table = f'"{schema}".design_partner_applications'
    enterprise_regclass = enterprise_table.replace("'", "''")
    design_regclass = design_table.replace("'", "''")

    # Preserve rows if an environment stopped between the original create and
    # rename migrations.  The normal main path and the legacy hosted-flow path
    # both skip this branch.
    op.execute(
        f"""
        do $$
        begin
          if to_regclass('{enterprise_regclass}') is not null
             and to_regclass('{design_regclass}') is not null then
            raise exception
              'both enterprise_pilot_applications and design_partner_applications exist';
          elsif to_regclass('{enterprise_regclass}') is null
                and to_regclass('{design_regclass}') is not null then
            alter table {design_table} rename to enterprise_pilot_applications;
          end if;
        end
        $$;
        """
    )

    # This is the final schema produced by 0034-0036, expressed directly for
    # databases whose colliding legacy 0036 caused Alembic to skip that chain.
    op.execute(
        f"""
        create table if not exists {enterprise_table} (
          id uuid primary key,
          company_name varchar(200) not null,
          email varchar(320) not null,
          email_domain varchar(255) not null,
          company_size varchar(20) not null,
          agents_jsonb jsonb not null default '[]'::jsonb,
          other_agents varchar(500),
          agent_management varchar(30) not null,
          weekly_active_agent_users integer,
          workflows_jsonb jsonb not null default '[]'::jsonb,
          other_workflow varchar(500),
          agent_write_readiness varchar(50) not null,
          executive_sponsor_role varchar(200),
          pilot_timing varchar(30) not null,
          notes varchar(2000),
          privacy_policy_version varchar(20) not null,
          privacy_accepted_at timestamptz not null,
          acknowledgement_sent_at timestamptz,
          status varchar(20) not null default 'submitted',
          reviewed_at timestamptz,
          reviewed_by uuid references "{schema}".platform_admins(id),
          review_note varchar(1000),
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint enterprise_pilot_applications_status_chk
            check (status in ('submitted', 'contacted', 'accepted', 'rejected')),
          constraint enterprise_pilot_applications_weekly_users_chk
            check (
              weekly_active_agent_users is null
              or weekly_active_agent_users between 0 and 1000000
            ),
          constraint enterprise_pilot_applications_email_uk unique (email)
        )
        """
    )

    # A renamed legacy table keeps its old constraint and index names.  Match
    # the names produced by the linear 0034-0036 chain without disturbing a
    # database that already has the final names.
    constraint_renames = (
        (
            "design_partner_applications_status_chk",
            "enterprise_pilot_applications_status_chk",
        ),
        (
            "design_partner_applications_weekly_users_chk",
            "enterprise_pilot_applications_weekly_users_chk",
        ),
        (
            "design_partner_applications_email_uk",
            "enterprise_pilot_applications_email_uk",
        ),
        (
            "design_partner_applications_reviewed_by_fkey",
            "enterprise_pilot_applications_reviewed_by_fkey",
        ),
        (
            "design_partner_applications_pkey",
            "enterprise_pilot_applications_pkey",
        ),
    )
    for old_name, new_name in constraint_renames:
        op.execute(
            f"""
            do $$
            begin
              if exists (
                select 1
                from pg_constraint
                where conrelid = to_regclass('{enterprise_regclass}')
                  and conname = '{old_name}'
              ) and not exists (
                select 1
                from pg_constraint
                where conrelid = to_regclass('{enterprise_regclass}')
                  and conname = '{new_name}'
              ) then
                alter table {enterprise_table}
                  rename constraint {old_name} to {new_name};
              elsif exists (
                select 1
                from pg_constraint
                where conrelid = to_regclass('{enterprise_regclass}')
                  and conname = '{old_name}'
              ) and exists (
                select 1
                from pg_constraint
                where conrelid = to_regclass('{enterprise_regclass}')
                  and conname = '{new_name}'
              ) then
                raise exception
                  'enterprise_pilot_applications has both % and % constraints',
                  '{old_name}', '{new_name}';
              end if;
            end
            $$;
            """
        )

    for old_name, new_name in (
        (
            "design_partner_applications_status_idx",
            "enterprise_pilot_applications_status_idx",
        ),
        (
            "design_partner_applications_domain_idx",
            "enterprise_pilot_applications_domain_idx",
        ),
    ):
        old_index = f'"{schema}".{old_name}'
        new_index = f'"{schema}".{new_name}'
        old_regclass = old_index.replace("'", "''")
        new_regclass = new_index.replace("'", "''")
        op.execute(
            f"""
            do $$
            begin
              if to_regclass('{old_regclass}') is not null
                 and to_regclass('{new_regclass}') is null then
                alter index {old_index} rename to {new_name};
              elsif to_regclass('{old_regclass}') is not null
                    and to_regclass('{new_regclass}') is not null then
                raise exception
                  'enterprise_pilot_applications has both % and % indexes',
                  '{old_name}', '{new_name}';
              end if;
            end
            $$;
            """
        )

    op.execute(
        f"create index if not exists enterprise_pilot_applications_status_idx "
        f"on {enterprise_table} (status)"
    )
    op.execute(
        f"create index if not exists enterprise_pilot_applications_domain_idx "
        f"on {enterprise_table} (email_domain)"
    )

    # Do not let the revision advance if a previously hand-created or partial
    # table lacks any column the application relies on.
    expected_columns = (
        "id",
        "company_name",
        "email",
        "email_domain",
        "company_size",
        "agents_jsonb",
        "other_agents",
        "agent_management",
        "weekly_active_agent_users",
        "workflows_jsonb",
        "other_workflow",
        "agent_write_readiness",
        "executive_sponsor_role",
        "pilot_timing",
        "notes",
        "privacy_policy_version",
        "privacy_accepted_at",
        "acknowledgement_sent_at",
        "status",
        "reviewed_at",
        "reviewed_by",
        "review_note",
        "created_at",
        "updated_at",
    )
    expected_columns_sql = ", ".join(f"'{name}'" for name in expected_columns)
    op.execute(
        f"""
        do $$
        begin
          if exists (
            select expected.column_name
            from unnest(array[{expected_columns_sql}]) as expected(column_name)
            where not exists (
              select 1
              from information_schema.columns actual
              where actual.table_schema = '{schema_literal}'
                and actual.table_name = 'enterprise_pilot_applications'
                and actual.column_name = expected.column_name
            )
          ) then
            raise exception
              'enterprise_pilot_applications is missing required columns';
          end if;
        end
        $$;
        """
    )

    expected_constraints = (
        "enterprise_pilot_applications_pkey",
        "enterprise_pilot_applications_status_chk",
        "enterprise_pilot_applications_weekly_users_chk",
        "enterprise_pilot_applications_email_uk",
        "enterprise_pilot_applications_reviewed_by_fkey",
    )
    expected_constraints_sql = ", ".join(
        f"'{name}'" for name in expected_constraints
    )
    op.execute(
        f"""
        do $$
        begin
          if exists (
            select expected.constraint_name
            from unnest(array[{expected_constraints_sql}])
              as expected(constraint_name)
            where not exists (
              select 1
              from pg_constraint actual
              where actual.conrelid = to_regclass('{enterprise_regclass}')
                and actual.conname = expected.constraint_name
            )
          ) then
            raise exception
              'enterprise_pilot_applications is missing required constraints';
          end if;
        end
        $$;
        """
    )

    # The legacy flow path runs 0038's grant before this migration creates the
    # enterprise table, so repeat the normal application-role grant here.
    op.execute(
        f"""
        do $$
        begin
          if exists (select 1 from pg_roles where rolname = 'oryh_app') then
            grant select, insert, update, delete
              on table {enterprise_table} to oryh_app;
          end if;
        end
        $$;
        """
    )


def downgrade() -> None:
    # This revision reconciles two histories.  The table belongs to 0034 on
    # the linear path, so dropping or renaming it here would corrupt that path.
    pass
