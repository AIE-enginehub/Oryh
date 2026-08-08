"""add approval targets

Revision ID: 20260402_0002
Revises: 20260402_0001
Create Date: 2026-04-02 15:10:00
"""

from __future__ import annotations

from alembic import op


revision = "20260402_0002"
down_revision = "20260402_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table approval_targets (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          target_type text not null,
          title text not null,
          summary text,
          payload_jsonb jsonb not null default '{}'::jsonb,
          source_text text,
          status text not null default 'open',
          created_by text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        )
        """
    )
    op.execute(
        """
        create index approval_targets_tenant_status_idx
          on approval_targets (tenant_id, status, created_at desc)
        """
    )
    op.execute("alter table approval_records drop constraint if exists approval_records_entity_type_chk")
    op.execute(
        """
        alter table approval_records
        add constraint approval_records_entity_type_chk
        check (entity_type in ('timesheet_header', 'approval_target'))
        """
    )
    op.execute("alter table todos drop constraint if exists todos_entity_type_chk")
    op.execute(
        """
        alter table todos
        add constraint todos_entity_type_chk
        check (entity_type in ('timesheet_header', 'project', 'approval_target'))
        """
    )


def downgrade() -> None:
    op.execute("alter table todos drop constraint if exists todos_entity_type_chk")
    op.execute(
        """
        alter table todos
        add constraint todos_entity_type_chk
        check (entity_type in ('timesheet_header', 'project'))
        """
    )
    op.execute("alter table approval_records drop constraint if exists approval_records_entity_type_chk")
    op.execute(
        """
        alter table approval_records
        add constraint approval_records_entity_type_chk
        check (entity_type in ('timesheet_header'))
        """
    )
    op.execute("drop index if exists approval_targets_tenant_status_idx")
    op.execute("drop table if exists approval_targets")
