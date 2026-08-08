"""add review workflow for self-service tenant registrations

Revision ID: 20260715_0020
Revises: 20260714_0019
Create Date: 2026-07-15 17:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260715_0020"
down_revision = "20260714_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".pending_registrations'
    op.execute(f"alter table {table} add column if not exists status varchar(20)")
    op.execute(f"alter table {table} add column if not exists verification_sent_at timestamptz")
    op.execute(f"alter table {table} add column if not exists verified_at timestamptz")
    op.execute(f"alter table {table} add column if not exists reviewed_at timestamptz")
    op.execute(f"alter table {table} add column if not exists reviewed_by uuid")
    op.execute(f"alter table {table} add column if not exists rejection_reason varchar(500)")
    op.execute(f"alter table {table} add column if not exists tenant_id uuid")
    op.execute(f"alter table {table} add column if not exists updated_at timestamptz")

    op.execute(
        f"""
        update {table} r
           set status = case when r.consumed_at is null then 'pending_email' else 'approved' end,
               verification_sent_at = coalesce(r.verification_sent_at, r.created_at),
               verified_at = case when r.consumed_at is not null then coalesce(r.verified_at, r.consumed_at) else r.verified_at end,
               reviewed_at = case when r.consumed_at is not null then coalesce(r.reviewed_at, r.consumed_at) else r.reviewed_at end,
               tenant_id = coalesce(r.tenant_id, t.id),
               updated_at = coalesce(r.updated_at, r.consumed_at, r.created_at)
          from "{schema}".tenants t
         where t.email_domain = r.email_domain
        """
    )
    op.execute(
        f"""
        update {table}
           set status = coalesce(status, 'pending_email'),
               verification_sent_at = coalesce(verification_sent_at, created_at),
               updated_at = coalesce(updated_at, consumed_at, created_at)
        """
    )
    # Older builds allowed several unconsumed requests for one domain. Keep
    # the newest actionable and retain the others as rejected history before
    # introducing the partial unique indexes.
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
               rejection_reason = coalesce(r.rejection_reason, 'Superseded during registration review migration'),
               updated_at = now()
          from ranked
         where ranked.id = r.id and ranked.position > 1
        """
    )
    op.execute(f"alter table {table} alter column status set default 'pending_email'")
    op.execute(f"alter table {table} alter column status set not null")
    op.execute(f"alter table {table} alter column verification_sent_at set default now()")
    op.execute(f"alter table {table} alter column verification_sent_at set not null")
    op.execute(f"alter table {table} alter column updated_at set default now()")
    op.execute(f"alter table {table} alter column updated_at set not null")
    op.execute(
        f"alter table {table} add constraint pending_registrations_status_chk "
        "check (status in ('pending_email', 'pending_review', 'approved', 'rejected'))"
    )
    op.execute(
        f"alter table {table} add constraint pending_registrations_reviewer_fk "
        f"foreign key (reviewed_by) references \"{schema}\".platform_admins(id)"
    )
    op.execute(
        f"alter table {table} add constraint pending_registrations_tenant_fk "
        f"foreign key (tenant_id) references \"{schema}\".tenants(id)"
    )
    op.execute(
        f"create unique index if not exists pending_registrations_active_email_uk on {table} (email) "
        "where status in ('pending_email', 'pending_review')"
    )
    op.execute(
        f"create unique index if not exists pending_registrations_active_domain_uk on {table} (email_domain) "
        "where status in ('pending_email', 'pending_review')"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".pending_registrations'
    op.execute(f'drop index if exists "{schema}".pending_registrations_active_domain_uk')
    op.execute(f'drop index if exists "{schema}".pending_registrations_active_email_uk')
    op.execute(f"alter table {table} drop constraint if exists pending_registrations_tenant_fk")
    op.execute(f"alter table {table} drop constraint if exists pending_registrations_reviewer_fk")
    op.execute(f"alter table {table} drop constraint if exists pending_registrations_status_chk")
    for column in (
        "updated_at",
        "tenant_id",
        "rejection_reason",
        "reviewed_by",
        "reviewed_at",
        "verified_at",
        "verification_sent_at",
        "status",
    ):
        op.execute(f"alter table {table} drop column if exists {column}")
