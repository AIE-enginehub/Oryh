"""add resources

Revision ID: 20260403_0004
Revises: 20260402_0003
Create Date: 2026-04-03 09:40:00
"""

from __future__ import annotations

from alembic import op


revision = "20260403_0004"
down_revision = "20260402_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists resources (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          resource_type text not null,
          name text not null,
          code text,
          location text,
          capacity integer,
          booking_mode text not null default 'exclusive',
          max_quantity integer,
          status text not null default 'active',
          metadata_jsonb jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint resources_booking_mode_chk check (booking_mode in ('exclusive', 'shared')),
          constraint resources_status_chk check (status in ('active', 'inactive', 'archived')),
          constraint resources_capacity_chk check (capacity is null or capacity >= 1),
          constraint resources_max_quantity_chk check (max_quantity is null or max_quantity >= 1)
        )
        """
    )
    op.execute(
        """
        create unique index if not exists resources_tenant_code_uk
          on resources (tenant_id, code)
          where code is not null
        """
    )
    op.execute(
        """
        create index if not exists resources_tenant_type_status_idx
          on resources (tenant_id, resource_type, status, created_at desc)
        """
    )
    op.execute(
        """
        create table if not exists resource_bookings (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null,
          resource_id uuid not null references resources(id),
          booked_by_employee_id uuid not null references employees(id),
          booking_type text,
          title text not null,
          start_at timestamptz not null,
          end_at timestamptz not null,
          quantity integer not null default 1,
          status text not null default 'confirmed',
          source_text text,
          notes text,
          metadata_jsonb jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          cancelled_at timestamptz,
          cancelled_by text,
          cancel_reason text,
          constraint resource_bookings_period_chk check (end_at > start_at),
          constraint resource_bookings_quantity_chk check (quantity >= 1),
          constraint resource_bookings_status_chk check (status in ('confirmed', 'cancelled'))
        )
        """
    )
    op.execute(
        """
        create index if not exists resource_bookings_tenant_resource_time_idx
          on resource_bookings (tenant_id, resource_id, start_at, end_at)
          where cancelled_at is null
        """
    )
    op.execute(
        """
        create index if not exists resource_bookings_tenant_booked_by_idx
          on resource_bookings (tenant_id, booked_by_employee_id, start_at desc)
        """
    )


def downgrade() -> None:
    op.execute("drop index if exists resource_bookings_tenant_booked_by_idx")
    op.execute("drop index if exists resource_bookings_tenant_resource_time_idx")
    op.execute("drop table if exists resource_bookings")
    op.execute("drop index if exists resources_tenant_type_status_idx")
    op.execute("drop index if exists resources_tenant_code_uk")
    op.execute("drop table if exists resources")
