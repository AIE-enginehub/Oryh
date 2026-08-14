"""a node an operator retired leaves the active-decision index

Revision ID: 20260812_0051
Revises: 20260810_0050
Create Date: 2026-08-12 18:00:00

`20260810_0049` gives a workflow node one deciding action and refuses to build
its index while any node holds two. One environment hit that refusal on six
legacy nodes, and the operator approved retaining both facts and retiring the
node rather than choosing which approval of somebody's invoice counts.

The natural place for that exemption looked like 0049 itself, and it was
written there first. It cannot live there. 0049 has already shipped and already
been applied, and the release guard compares the checksum of every migration in
the live release's tree against the target's: editing a published migration
refuses every future release into an environment that already ran it, forever.
That guard is right. A migration file is the record of what ran; once it has
run somewhere, it is history, and history does not get edited to suit a later
problem.

So the exemption is its own revision. It adds the typed column, promotes the
marker an authorized operator wrote out of band, and narrows the index so a
retired node leaves it while both of its facts stay in the trail verbatim.

What this does NOT do is relax 0049. An environment still sitting behind 0049
with an unmarked conflict is refused there and never reaches this revision —
the fail-closed guarantee stays where the index is first built, and getting
past it still takes an operator decision about the data.

Every statement is written to be safe on an environment that already has the
column from some earlier route: `add column if not exists`, an idempotent
promotion, and an index drop-and-create rather than a create.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings
from app.core.entity_types import (
    DECIDED_APPROVAL_ACTIONS,
    OPERATOR_CONFLICT_CLOSURE_KEY,
)


revision = "20260812_0051"
down_revision = "20260810_0050"
branch_labels = None
depends_on = None


def _decided_predicate() -> str:
    return (
        "historical_conflict_closed is false and action in ("
        + ", ".join(f"'{value}'" for value in DECIDED_APPROVAL_ACTIONS)
        + ")"
    )


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".approval_records'

    op.execute(
        f"alter table {table} add column if not exists "
        "historical_conflict_closed boolean not null default false"
    )
    op.execute(
        f"""
        update {table}
        set historical_conflict_closed = true
        where historical_conflict_closed is false
          and coalesce(metadata_jsonb ->> '{OPERATOR_CONFLICT_CLOSURE_KEY}', '')
              = 'closed_historical_conflict'
        """
    )

    # Recreated rather than created: 0049 already built this index, over every
    # decided action. The new predicate only ever NARROWS what it covers — a
    # retired node leaves — so a rebuild cannot fail on data the wider index
    # already accepted.
    op.execute(f'drop index if exists "{schema}".approval_records_one_decision_uk')
    op.execute(
        f"create unique index approval_records_one_decision_uk "
        f"on {table} (tenant_id, entity_type, entity_id, round_no, sequence_no) "
        f"where {_decided_predicate()}"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    table = f'"{schema}".approval_records'
    decided = ", ".join(f"'{value}'" for value in DECIDED_APPROVAL_ACTIONS)

    # Going back means rebuilding the WIDER index — the one with no notion of a
    # closed conflict — and a node that was closed precisely because it holds
    # two decisions cannot fit under it. Postgres would say "duplicate key" and
    # name an index, which reads as corruption rather than as the reversal
    # being impossible. Say which nodes, and why.
    closed = op.get_bind().exec_driver_sql(
        f"select entity_type, entity_id, round_no, sequence_no from {table} "
        "where historical_conflict_closed group by entity_type, entity_id, "
        "round_no, sequence_no"
    ).fetchall()
    if closed:
        lines = "\n".join(
            f"  {row.entity_type} {row.entity_id} round {row.round_no} step {row.sequence_no}"
            for row in closed[:40]
        )
        raise RuntimeError(
            f"{len(closed)} approval step(s) were retired as historical conflicts and "
            f"still hold both decisions:\n{lines}\n\n"
            "Reversing this revision restores an index that cannot represent them. "
            "Resolve each node — decide which action stands and remove the other, "
            "under an approved data-remediation scope — before downgrading."
        )

    op.execute(f'drop index if exists "{schema}".approval_records_one_decision_uk')
    op.execute(
        f"create unique index approval_records_one_decision_uk "
        f"on {table} (tenant_id, entity_type, entity_id, round_no, sequence_no) "
        f"where action in ({decided})"
    )
    op.execute(f"alter table {table} drop column if exists historical_conflict_closed")
