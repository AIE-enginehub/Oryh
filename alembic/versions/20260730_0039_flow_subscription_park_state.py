"""park state survives a restart, because forgetting it costs money

Revision ID: 20260730_0039
Revises: 20260730_0038
Create Date: 2026-07-30 09:00:00

The runner stops spending on a queue that will not drain — a workflow definition
that routes nowhere looks exactly like an agent working hard on an item that
never leaves. That stop lived in the dispatcher's memory, which made it a lie:
every restart and every deploy resumed paying for the same discovery.

So it lives here. A second reason to keep it in the record layer rather than in
one process: several runner replicas then agree on what is parked without
talking to each other, which is what sharding tenants across replicas needs.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260730_0039"
down_revision = "20260730_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".flow_subscriptions '
        "add column if not exists unmoved_runs integer not null default 0"
    )
    op.execute(
        f'alter table "{schema}".flow_subscriptions '
        "add column if not exists parked_at timestamptz"
    )
    op.execute(
        f'alter table "{schema}".flow_subscriptions '
        "add column if not exists parked_reason text"
    )
    # "what is stuck right now" is the question operations asks; parked rows are
    # a handful among all subscriptions, so the partial index is the whole answer.
    op.execute(
        'create index if not exists flow_subscriptions_parked_idx '
        f'on "{schema}".flow_subscriptions (tenant_id, entity_type) '
        "where parked_at is not null"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop index if exists "{schema}".flow_subscriptions_parked_idx')
    for column in ("parked_reason", "parked_at", "unmoved_runs"):
        op.execute(f'alter table "{schema}".flow_subscriptions drop column if exists {column}')
