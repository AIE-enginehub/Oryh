"""a work type the tenant defined is a work type the tenant may use

Revision ID: 20260813_0054
Revises: 20260813_0053
Create Date: 2026-08-13 20:00:00

`timesheet_entries_work_type_chk` allowed five values and predates type
options. Type options then made `work_type` one of fifteen vocabularies a
workspace defines for itself: `POST /type-options` accepts a new one, and
`require_type_option` validates writes against the tenant's active list.

Both were true at once, so the product invited a tenant to define 待命 and then
answered 500 when somebody logged eight hours against it. Defining returned
201; using it did not.

Dropped rather than widened. The column's vocabulary is the tenant's, held in
`type_options` and enforced in the write path — a fixed list in the schema is
not a weaker version of that rule, it is the opposite of it. The other fourteen
extensible families never had one, which is what made this the outlier rather
than the pattern.

Found by declaring the schema's CHECK constraints on the models, so that SQLite
test databases finally carry them: the suite had been green over this since
type options shipped.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260813_0054"
down_revision = "20260813_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".timesheet_entries '
        "drop constraint if exists timesheet_entries_work_type_chk"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".timesheet_entries'
    # Restoring the five-value list cannot succeed once a tenant has used a
    # work type it defined, and by then those rows are somebody's timesheet.
    rows = op.get_bind().exec_driver_sql(
        f"select count(*) from {table} "
        "where work_type not in ('regular','overtime','holiday','travel','other')"
    ).scalar()
    if rows:
        raise RuntimeError(
            f"{rows} timesheet entr(ies) use a tenant-defined work type. The "
            "pre-0054 constraint cannot represent them, and rewriting somebody's "
            "recorded hours to fit a dropped constraint is not a migration's call."
        )
    op.execute(
        f"alter table {table} add constraint timesheet_entries_work_type_chk "
        "check (work_type in ('regular', 'overtime', 'holiday', 'travel', 'other'))"
    )
