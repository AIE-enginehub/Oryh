"""Which side of the contract register a credential reads.

A contract's SIDE — purchase or sales — is stored on it and agrees with
its counterparty (see `Contract`), and `contract.manage:purchase` / `:sales` is checked
against it. The contracts API and anything that lists rows hanging off a
contract (a deal's parties, review 2026-10-19 F02) read one rule from here
rather than each restating it (review 2026-10-22, N4).
"""

from __future__ import annotations

from sqlalchemy import select

from app.api.deps import Actor, has_permission
from app.models import Contract

SIDES = ("purchase", "sales")


def sides_read(actor: Actor) -> list[str]:
    """The sides this credential holds `contract.manage` for."""
    return [side for side in SIDES if has_permission(actor, "contract.manage", side)]


def side_clause(side: str):
    """Which rows are a side's."""
    return Contract.side == side


def restrict_to_sides(stmt, visible: list[str], *, through=None):
    """Only the sides this credential reads. `through` is a child table's
    contract column, joined so lines, originals and clauses follow the same
    rule as the contracts themselves — without it the three child lists
    answered every side's rows whenever no contract_id was named."""
    if all(side in visible for side in SIDES):
        return stmt
    if through is not None:
        stmt = stmt.join(Contract, Contract.id == through)
    for hidden in SIDES:
        if hidden not in visible:
            stmt = stmt.where(side_clause(next(s for s in SIDES if s != hidden)))
    return stmt


def of_live_contracts(stmt, through):
    """Only rows hanging off a contract that is not deleted. A deleted
    contract reads 404; its lines, originals, clauses and parties must not
    answer a list or a keyword search either (review 2026-10-24, finding 4)."""
    return stmt.where(through.in_(select(Contract.id).where(Contract.deleted_at.is_(None))))
