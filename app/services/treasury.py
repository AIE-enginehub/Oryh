"""The one write path for money moving on a fin account.

Mirrors `post_inventory_detail` deliberately, invariant for invariant: the
register row is appended and the account's balance moves by a RELATIVE
update in the same flush — `SET balance = balance + :amount` computed by the
database, never an absolute number Python worked out. Two concurrent
postings against one account both land; an absolute write would let the
second silently swallow the first with both register rows surviving, which
is precisely the corruption a cash balance cannot carry.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.models import FinAccount, FinAccountTrans, Payment
from app.services.state_machines import editable_states, get_builtin_machine, state_for_role


def post_fin_account_trans(
    db: Session,
    *,
    account: FinAccount,
    amount: float,
    trans_type: str,
    trans_date: date | None = None,
    gross_amount: float | None = None,
    fee_amount: float | None = None,
    counterparty: str | None = None,
    description: str | None = None,
    reference_no: str | None = None,
    payment_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    custom_fields: dict | None = None,
    created_by: str | None = None,
) -> FinAccountTrans:
    trans = FinAccountTrans(
        tenant_id=account.tenant_id,
        fin_account_id=account.id,
        trans_type=trans_type,
        amount=amount,
        gross_amount=gross_amount,
        fee_amount=fee_amount,
        trans_date=trans_date,
        counterparty=counterparty,
        description=description,
        reference_no=reference_no,
        payment_id=payment_id,
        entity_type=entity_type,
        entity_id=entity_id,
        custom_fields_jsonb=custom_fields or {},
        created_by=created_by,
    )
    db.add(trans)
    db.flush()
    db.execute(
        update(FinAccount)
        .where(FinAccount.id == account.id)
        .values(current_balance=FinAccount.current_balance + amount)
        .execution_options(synchronize_session=False)
    )
    db.expire(account, ["current_balance"])
    return trans


# --- how a register line relates to a payment (review 2026-10-26) -----------
#
# A line names one payment (`payment_id`), or one batch of payments by their
# shared `reference_no` (`payment_reference_no`). These are the rules both
# links obey and the payment's own detail reads back.


def linkable_payment_states(db: Session, tenant_id: str) -> frozenset[str]:
    """A bank line records money that moved, so it links a payment that is
    paid — or approved, because the bank debit often shows before the
    accountant marks it paid, and the cashier holding the register does not
    hold `payment.record`. Never a draft, one in approval, a cancelled or a
    voided one: that link would say money moved for a payment that did not
    move it. `paid` by its role; `approved` by its place in the machine, the
    state past editing that leads to `paid`."""
    machine = get_builtin_machine(db, tenant_id, "payment")
    paid = state_for_role(machine, "payment", "paid")
    editable = editable_states(machine, "payment")
    return frozenset({paid} | {state for state, onward in (machine.get("transitions") or {}).items()
                               if paid in onward and state not in editable})


def line_coverage(line: FinAccountTrans) -> float:
    """How much of a payment one line carries: the gross the bank recorded
    before netting its fee, else the line's own amount; unsigned."""
    value = line.gross_amount if line.gross_amount is not None else line.amount
    return abs(float(value or 0))


def payment_landings(db: Session, tenant_id: str, payment: Payment) -> list[tuple[FinAccountTrans, str]]:
    """Every register line that carries this payment: its own lines
    (`direct`), and the line that settles its batch (`batch`)."""
    lines = [
        (line, "direct")
        for line in db.scalars(
            select(FinAccountTrans).options(selectinload(FinAccountTrans.account))
            .where(FinAccountTrans.tenant_id == tenant_id, FinAccountTrans.payment_id == payment.id)
            .order_by(FinAccountTrans.trans_date.asc().nulls_last(), FinAccountTrans.created_at.asc())
        )
    ]
    if payment.reference_no:
        lines += [
            (line, "batch")
            for line in db.scalars(
                select(FinAccountTrans).options(selectinload(FinAccountTrans.account))
                .where(FinAccountTrans.tenant_id == tenant_id,
                       FinAccountTrans.payment_reference_no == payment.reference_no)
                .order_by(FinAccountTrans.created_at.asc())
            )
        ]
    return lines


def landed_amount(payment: Payment, landings: list[tuple[FinAccountTrans, str]]) -> float:
    """What the bank has carried of this payment: a batch line settles each
    member in full; its own lines carry what they cover."""
    if any(via == "batch" for _, via in landings):
        return round(float(payment.amount), 2)
    return round(sum(line_coverage(line) for line, _ in landings), 2)
