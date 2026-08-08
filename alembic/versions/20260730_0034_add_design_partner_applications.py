"""persist and review public design partner applications

Revision ID: 20260730_0034
Revises: 20260728_0033
Create Date: 2026-07-30 11:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260730_0034"
down_revision = "20260728_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".design_partner_applications'
    op.execute(
        f"""
        create table if not exists {table} (
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
          constraint design_partner_applications_status_chk
            check (status in ('submitted', 'contacted', 'accepted', 'rejected')),
          constraint design_partner_applications_weekly_users_chk
            check (
              weekly_active_agent_users is null
              or weekly_active_agent_users between 0 and 1000000
            ),
          constraint design_partner_applications_email_uk unique (email)
        )
        """
    )
    op.execute(
        f"create index if not exists design_partner_applications_status_idx "
        f"on {table} (status)"
    )
    op.execute(
        f"create index if not exists design_partner_applications_domain_idx "
        f"on {table} (email_domain)"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table if exists "{schema}".design_partner_applications')
