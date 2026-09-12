"""the platform's switch on hosted flow driving, per company

Revision ID: 20260910_0092
Revises: 20260910_0091
Create Date: 2026-09-10 18:00:00

Stopping ORYH's runner from driving one company meant either suspending the
company — which blocks every credential they own — or switching off each of
its subscriptions one by one, which rewrites the tenant's own enrolment and
has to be undone row by row. `tenants.flow_runner_enabled` is the lever in
between: platform-set, read by the runner's tenant list, by credential
issuance, and by the hosted principal's authentication, and by nothing else.
Defaults on, because every company being driven today keeps being driven.

Written `if not exists` because this landed beside the geo migration on the
same day and was briefly numbered 0091 as well; a development database that
already carries the column must not fail the re-chained upgrade.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20260910_0092"
down_revision = "20260910_0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".tenants '
        "add column if not exists flow_runner_enabled boolean not null default true"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'alter table "{schema}".tenants drop column if exists flow_runner_enabled')
