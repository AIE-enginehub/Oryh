"""add business objects

Revision ID: 20260422_0007
Revises: 20260411_0006
Create Date: 2026-04-22 10:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260422_0007"
down_revision = "20260411_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    op.execute(f'alter table if exists "{schema_name}".approval_targets rename to business_objects')
    op.execute(f'alter index if exists "{schema_name}".approval_targets_tenant_status_idx rename to business_objects_tenant_status_idx')
    op.execute(f'alter table if exists "{schema_name}".business_objects rename column target_type to object_type')
    op.execute(f'alter table if exists "{schema_name}".business_objects drop constraint if exists approval_targets_status_chk')
    op.execute(
        f"""
        alter table if exists "{schema_name}".business_objects
        add constraint business_objects_status_chk
        check (status in ('open', 'in_review', 'approved', 'rejected', 'archived'))
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema_name}".business_object_links (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          source_object_id uuid not null references "{schema_name}".business_objects(id),
          target_object_id uuid not null references "{schema_name}".business_objects(id),
          link_type text not null,
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          constraint business_object_links_unique_link
            unique (tenant_id, source_object_id, target_object_id, link_type),
          constraint business_object_links_distinct_objects_chk
            check (source_object_id <> target_object_id)
        )
        """
    )
    op.execute(
        f"""
        create index if not exists business_object_links_tenant_source_type_idx
          on "{schema_name}".business_object_links (tenant_id, source_object_id, link_type, created_at desc)
        """
    )
    op.execute(
        f"""
        create index if not exists business_object_links_tenant_target_type_idx
          on "{schema_name}".business_object_links (tenant_id, target_object_id, link_type, created_at desc)
        """
    )
    op.execute(f'alter table if exists "{schema_name}".approval_records drop constraint if exists approval_records_entity_type_chk')
    op.execute(
        f"""
        alter table if exists "{schema_name}".approval_records
        add constraint approval_records_entity_type_chk
        check (entity_type in ('timesheet_header', 'approval_target', 'business_object'))
        """
    )
    op.execute(f'alter table if exists "{schema_name}".todos drop constraint if exists todos_entity_type_chk')
    op.execute(
        f"""
        alter table if exists "{schema_name}".todos
        add constraint todos_entity_type_chk
        check (entity_type in ('timesheet_header', 'project', 'approval_target', 'business_object'))
        """
    )


def downgrade() -> None:
    schema_name = settings.database_schema.replace('"', '""')
    op.execute(f'alter table if exists "{schema_name}".todos drop constraint if exists todos_entity_type_chk')
    op.execute(
        f"""
        alter table if exists "{schema_name}".todos
        add constraint todos_entity_type_chk
        check (entity_type in ('timesheet_header', 'project', 'approval_target'))
        """
    )
    op.execute(f'alter table if exists "{schema_name}".approval_records drop constraint if exists approval_records_entity_type_chk')
    op.execute(
        f"""
        alter table if exists "{schema_name}".approval_records
        add constraint approval_records_entity_type_chk
        check (entity_type in ('timesheet_header', 'approval_target'))
        """
    )
    op.execute(f'drop index if exists "{schema_name}".business_object_links_tenant_target_type_idx')
    op.execute(f'drop index if exists "{schema_name}".business_object_links_tenant_source_type_idx')
    op.execute(f'drop table if exists "{schema_name}".business_object_links')
    op.execute(f'alter table if exists "{schema_name}".business_objects drop constraint if exists business_objects_status_chk')
    op.execute(f'alter table if exists "{schema_name}".business_objects rename column object_type to target_type')
    op.execute(
        f"""
        alter table if exists "{schema_name}".business_objects
        add constraint approval_targets_status_chk
        check (status in ('open', 'in_review', 'approved', 'rejected', 'archived'))
        """
    )
    op.execute(f'alter index if exists "{schema_name}".business_objects_tenant_status_idx rename to approval_targets_tenant_status_idx')
    op.execute(f'alter table if exists "{schema_name}".business_objects rename to approval_targets')
