"""refine approval targets

Revision ID: 20260402_0003
Revises: 20260402_0002
Create Date: 2026-04-02 16:20:00
"""

from __future__ import annotations

from alembic import op


revision = "20260402_0003"
down_revision = "20260402_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table approval_targets add column if not exists deleted_at timestamptz")
    op.execute("alter table approval_targets add column if not exists deleted_by text")
    op.execute("alter table approval_targets add column if not exists delete_reason text")
    op.execute(
        """
        update approval_targets
        set status = 'archived'
        where status not in ('open', 'in_review', 'approved', 'rejected', 'archived')
        """
    )
    op.execute("alter table approval_targets drop constraint if exists approval_targets_status_chk")
    op.execute(
        """
        alter table approval_targets
        add constraint approval_targets_status_chk
        check (status in ('open', 'in_review', 'approved', 'rejected', 'archived'))
        """
    )
    op.execute("drop index if exists approval_targets_tenant_status_idx")
    op.execute(
        """
        create index approval_targets_tenant_status_idx
          on approval_targets (tenant_id, status, created_at desc)
          where deleted_at is null
        """
    )


def downgrade() -> None:
    op.execute("drop index if exists approval_targets_tenant_status_idx")
    op.execute(
        """
        create index approval_targets_tenant_status_idx
          on approval_targets (tenant_id, status, created_at desc)
        """
    )
    op.execute("alter table approval_targets drop constraint if exists approval_targets_status_chk")
    op.execute("alter table approval_targets drop column if exists delete_reason")
    op.execute("alter table approval_targets drop column if exists deleted_by")
    op.execute("alter table approval_targets drop column if exists deleted_at")
