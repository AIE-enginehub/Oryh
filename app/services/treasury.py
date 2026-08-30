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

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import FinAccount, FinAccountTrans


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
