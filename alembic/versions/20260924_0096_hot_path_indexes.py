"""Indexes for the lists every workspace opens most

Revision ID: 20260924_0096
Revises: 20260915_0095
Create Date: 2026-09-24 12:00:00

The 2026-09-24 review compared the filters the API applies with the indexes
`sql/schema.sql` carries. Purchase orders, shipments, leads and opportunities
are listed by tenant + status, newest first, and had only a tenant index;
invoices and payments are listed by tenant + direction + status and their
index stopped short of the ordering column; the importers look SKUs up by
code within a tenant and there was no index for it. Each is the shape the
document families that already had one use (`sales_orders_tenant_status_idx`).
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20260924_0096"
down_revision = "20260915_0095"
branch_labels = None
depends_on = None

INDEXES = (
    ("purchase_orders_tenant_status_idx", "purchase_orders", "tenant_id, status, created_at desc"),
    ("shipments_tenant_status_idx", "shipments", "tenant_id, status, created_at desc"),
    ("leads_tenant_status_idx", "leads", "tenant_id, status, created_at desc"),
    ("opportunities_tenant_status_idx", "opportunities", "tenant_id, status, created_at desc"),
    ("invoices_tenant_direction_status_created_idx", "invoices", "tenant_id, direction, status, created_at desc"),
    ("payments_tenant_direction_status_created_idx", "payments", "tenant_id, direction, status, created_at desc"),
    ("product_skus_tenant_sku_code_idx", "product_skus", "tenant_id, sku_code"),
)


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for name, table, columns in INDEXES:
        op.execute(f'create index if not exists {name} on "{schema}".{table} ({columns})')


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    for name, _table, _columns in INDEXES:
        op.execute(f'drop index if exists "{schema}".{name}')
