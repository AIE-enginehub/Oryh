"""a todo may be cancelled — which the database has refused since the baseline

Revision ID: 20260813_0053
Revises: 20260813_0052
Create Date: 2026-08-13 17:00:00

`20260402_0001` wrote `check (status in ('open','completed'))` and nothing ever
widened it. `schemas.TodoStatus` has listed `cancelled` for as long as anyone
can remember, and `cancel_todos_for` — the server's answer to a work item whose
subject was deleted — writes exactly that value.

So on every Postgres environment, for the whole life of the product:

- `PATCH /todos/{id}` with `{"status": "cancelled"}` was a 500, not a 422;
- and worse, **deleting a document that had an open todo was a 500**, because
  the delete path cancels its todos in the same transaction. The document was
  not deleted either. That one arrived with `cancel_todos_for` itself: the fix
  for orphaned todos could not run, and took document deletion with it.

The suite never saw it. The model declared no CHECK on `status`, SQLite builds
its schema from the model, so the tests ran against a database with no
constraint at all — green over a value Postgres refuses. The model now declares
it, from the same `TODO_STATUSES` this migration reads, so the two cannot drift
again and SQLite gets the constraint too.

Widening only. Every existing row is `open` or `completed`, both still legal,
so there is nothing to validate and nothing to migrate.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings
from app.core.entity_types import TODO_STATUSES


revision = "20260813_0053"
down_revision = "20260813_0052"
branch_labels = None
depends_on = None


def _values() -> str:
    return ", ".join(f"'{value}'" for value in TODO_STATUSES)


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".todos'
    op.execute(f"alter table {table} drop constraint if exists todos_status_chk")
    op.execute(
        f"alter table {table} add constraint todos_status_chk "
        f"check (status in ({_values()}))"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".todos'
    # Narrowing back cannot succeed while a cancelled todo exists, and by then
    # cancelling is how the product retires unactionable work. Say so rather
    # than emit a constraint-violation error about a value we introduced.
    cancelled = op.get_bind().exec_driver_sql(
        f"select count(*) from {table} where status = 'cancelled'"
    ).scalar()
    if cancelled:
        raise RuntimeError(
            f"{cancelled} todo(s) are cancelled, which the pre-0053 constraint "
            "does not allow. Decide what those work items should say — there is "
            "no honest mapping onto 'completed', because nobody did them — "
            "before reversing this."
        )
    op.execute(f"alter table {table} drop constraint if exists todos_status_chk")
    op.execute(
        f"alter table {table} add constraint todos_status_chk "
        "check (status in ('open', 'completed'))"
    )
