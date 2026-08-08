"""harden registration domain and credential retention

Revision ID: 20260715_0021
Revises: 20260715_0020
Create Date: 2026-07-15 17:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.core.config import settings
from app.core.email_domains import registrable_domain


revision = "20260715_0021"
down_revision = "20260715_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".pending_registrations'
    op.execute(f'drop index if exists "{schema}".pending_registrations_active_domain_uk')
    op.execute(f"alter table {table} alter column password_hash drop not null")
    op.execute(f"alter table {table} alter column token_hash drop not null")

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            f"select id, email_domain from {table} "
            "where status in ('pending_email', 'pending_review')"
        )
    ).all()
    for registration_id, stored_domain in rows:
        try:
            canonical = registrable_domain(stored_domain)
        except ValueError:
            canonical = ""
        if canonical and canonical != stored_domain:
            bind.execute(
                sa.text(f"update {table} set email_domain = :domain where id = :id"),
                {"domain": canonical, "id": registration_id},
            )

    op.execute(
        f"""
        with ranked as (
          select id,
                 row_number() over (partition by email_domain order by created_at desc, id desc) as position
            from {table}
           where status in ('pending_email', 'pending_review')
        )
        update {table} r
           set status = 'rejected',
               consumed_at = coalesce(r.consumed_at, now()),
               reviewed_at = coalesce(r.reviewed_at, now()),
               rejection_reason = coalesce(r.rejection_reason, 'Superseded by canonical company-domain request'),
               password_hash = null,
               token_hash = null,
               updated_at = now()
          from ranked
         where ranked.id = r.id and ranked.position > 1
        """
    )
    op.execute(
        f"update {table} set password_hash = null, token_hash = null "
        "where status in ('approved', 'rejected')"
    )
    op.execute(
        f"create unique index pending_registrations_active_domain_uk on {table} (email_domain) "
        "where status in ('pending_email', 'pending_review')"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".pending_registrations'
    op.execute(
        f"update {table} set password_hash = coalesce(password_hash, '$disabled$' || id::text), "
        "token_hash = coalesce(token_hash, md5(id::text))"
    )
    op.execute(f"alter table {table} alter column token_hash set not null")
    op.execute(f"alter table {table} alter column password_hash set not null")
