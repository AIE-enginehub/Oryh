"""Give the completed todos back the name they lost

A resubmission completes the rework todo it answers. That path wrote
`completed_at` and not `completed_by`, so every resubmission left a row
claiming to be done by nobody — the integrity audit's
`completed todos carry completed_at and completed_by` grew by one per
blackbox run for two weeks.

The code is fixed. The rows already written are repaired from the audit
trail rather than from a guess: the same call that forgot the column wrote
`record_audit(action="todo.completed", actor=attributed(actor, None))`
immediately afterwards, and that actor IS the value the column should have
held. Rows with no audit row keep NULL — inventing an actor to make a check
go green is the one thing this migration must not do.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20260906_0086"
down_revision = "20260906_0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        update "{schema}".todos as t
           set completed_by = a.actor
          from (
                select distinct on (entity_id) entity_id, actor
                  from "{schema}".audit_logs
                 where action = 'todo.completed'
                   and entity_type = 'todo'
                   and actor is not null
                 order by entity_id, id desc
               ) as a
         where a.entity_id = t.id
           and t.completed_at is not null
           and t.completed_by is null
        """
    )


def downgrade() -> None:
    # Deliberately empty. The column was always meant to hold this; putting
    # the rows back to NULL would restore a defect, not a state.
    pass
