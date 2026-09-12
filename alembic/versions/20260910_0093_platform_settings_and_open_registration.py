"""platform settings, and a registration that claims no company domain

Revision ID: 20260910_0093
Revises: 20260910_0092
Create Date: 2026-09-10 20:00:00

Whether a company may sign up from a personal mailbox was an environment
variable, which made it a redeploy. It is a decision about who is let in
today, so it becomes a row the operator flips from the console:
`platform_settings` is one row per key with a JSON value, read at request
time (see app/saas/platform_settings.py for keys and defaults — nothing is
seeded, an absent row means the default, which is the behaviour before this
table existed).

With the requirement off, a registration from `alice@gmail.com` must not
claim `gmail.com` as its company domain — that would tell the next gmail
registrant their company already exists. So `pending_registrations.email_domain`
becomes nullable; NULL claims nothing, and the partial unique index on it
passes NULLs, so two such requests may be open at once. `tenants.email_domain`
was nullable already.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20260910_0093"
down_revision = "20260910_0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".platform_settings (
          key text primary key,
          value_jsonb jsonb not null,
          updated_at timestamptz not null default now(),
          updated_by uuid references "{schema}".platform_admins(id)
        )
        """
    )
    op.execute(
        f'alter table "{schema}".pending_registrations alter column email_domain drop not null'
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        delete from "{schema}".pending_registrations
        where email_domain is null and status in ('pending_email', 'pending_review')
        """
    )
    op.execute(
        f"""
        update "{schema}".pending_registrations
        set email_domain = split_part(email, '@', 2) where email_domain is null
        """
    )
    op.execute(
        f'alter table "{schema}".pending_registrations alter column email_domain set not null'
    )
    op.execute(f'drop table if exists "{schema}".platform_settings')
