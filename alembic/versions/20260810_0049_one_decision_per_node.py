"""a step in an approval holds one decision, and the database is what holds it

Revision ID: 20260810_0049
Revises: 20260808_0048
Create Date: 2026-08-10 12:00:00

`approval_records` was unique on
(tenant, entity_type, entity_id, round_no, sequence_no, **action**). The action
is in that key on purpose: it is what makes an agent's retry idempotent, and
that behaviour is load-bearing. What it also did was let `approved` and
`rejected` stand together at the same round and sequence — one seat, two
contradictory decisions, and nothing in the data saying which one counts.

Nobody has to misbehave to produce it. One approver opens two agent sessions,
lists their queue in both, decides in one; the other is now holding a list that
was true when it was read. The server took whatever it was told, because the
stance here is that agents drive the flow and the server records facts. That
stance is right and this is its edge: "which decision is this step's" is not a
judgment an agent should be free to answer twice.

So a partial unique index over the four positional columns, restricted to the
DECIDING actions. `commented` is outside it — an objection that settles nothing
may sit beside the decision, and several may.

The index rather than a check in the write path, because the write path already
has one and it would be a check-then-insert between exactly the two concurrent
sessions this exists to stop. The Python guard raises the readable 409; this is
what makes the guarantee true.

**This migration refuses to run on data that already violates it.** Creating
the index would fail anyway, less legibly; deleting or picking a winner would
be this migration deciding which approval of somebody's timesheet counts, which
is not a call to make from a schema change at 3am. It prints the offending
nodes and stops, so a person resolves them.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings
from app.core.entity_types import DECIDED_APPROVAL_ACTIONS


revision = "20260810_0049"
down_revision = "20260808_0048"
branch_labels = None
depends_on = None


def _decided_predicate() -> str:
    return "action in (" + ", ".join(f"'{value}'" for value in DECIDED_APPROVAL_ACTIONS) + ")"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".approval_records'
    predicate = _decided_predicate()

    offenders = op.get_bind().exec_driver_sql(
        f"""
        select tenant_id, entity_type, entity_id, round_no, sequence_no,
               string_agg(distinct action, ', ' order by action) as actions
        from {table}
        where {predicate}
        group by tenant_id, entity_type, entity_id, round_no, sequence_no
        having count(distinct action) > 1
        """
    ).fetchall()
    if offenders:
        lines = "\n".join(
            f"  {row.entity_type} {row.entity_id} round {row.round_no} "
            f"step {row.sequence_no}: {row.actions}"
            for row in offenders[:40]
        )
        raise RuntimeError(
            f"{len(offenders)} approval step(s) carry more than one decision:\n{lines}\n\n"
            "Each of these is a document whose trail says two different things about "
            "the same step. Decide which one stands and delete the other — a schema "
            "migration must not pick for you — then run this again."
        )

    op.execute(
        f"create unique index if not exists approval_records_one_decision_uk "
        f"on {table} (tenant_id, entity_type, entity_id, round_no, sequence_no) "
        f"where {predicate}"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop index if exists "{schema}".approval_records_one_decision_uk')
