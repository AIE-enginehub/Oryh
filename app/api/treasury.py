"""The treasury desk: fin accounts and the bank register.

Where the company's money actually sits and moves — bank accounts, the cash
box, third-party payment balances (微信支付/支付宝/PayPal). The register is
the bank's truth: rows append, never edit; a wrong row is a counter-entry;
the account's balance is a running sum with exactly one write path
(`post_fin_account_trans`). Reconciliation state is derived — an unlinked
row is one whose links are null, and nothing stores "reconciled" anywhere.

Everything here, reads included, sits behind `fin_account.manage` — the
cashier's desk, split from the accountant's `payment.record` on purpose
(钱账分离): cash position and salary payout lines are payroll-grade
sensitive, so the member surface deliberately never sees them.

oryh holds no PSP credentials and pulls no statements: the tenant's own
agent fetches bills with the tenant's own tools and imports them through
/bulk, where `reference_no` makes re-imports idempotent.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import (
    archive_row,
    commit_or_conflict,
    envelope,
    get_scoped_or_404,
    list_rows,
    requested_pagination,
    require_active_row,
    require_entity_uuid,
)
from app.api.deps import Actor, attributed, get_actor, require_permission
from app.db.session import get_db
from app.models import FinAccount, FinAccountTrans, Payment
from app.schemas import (
    BulkFinAccountTransImportRequest,
    CreateFinAccountRequest,
    CreateFinAccountTransRequest,
    FinAccountEnvelope,
    FinAccountListEnvelope,
    FinAccountRead,
    FinAccountTransEnvelope,
    FinAccountTransListEnvelope,
    FinAccountTransRead,
    LinkFinAccountTransRequest,
    UpdateFinAccountRequest,
)
from app.services.treasury import post_fin_account_trans
from app.services.type_options import require_type_option

router = APIRouter()


def _require_treasury(actor: Actor) -> None:
    require_permission(actor, "fin_account.manage")


def _require_active_account(db: Session, tenant_id: str, fin_account_id: str) -> FinAccount:
    return require_active_row(
        db, FinAccount, tenant_id, fin_account_id, "fin account",
        detail="fin account is archived — set it active before posting to its register",
    )


def _require_link_coherence(
    db: Session, tenant_id: str, payment_id: str | None, amount: float
) -> None:
    """A register line linked to a payment must move money the way the
    payment says it moves: outbound documents land as negative lines,
    inbound as positive. Amounts may differ (fees, partial legs) — the sign
    may not, because a backwards link is a wrong answer the three-way reader
    would repeat."""
    if payment_id is None:
        return
    payment = get_scoped_or_404(db, Payment, tenant_id, payment_id)
    wanted = -1 if payment.direction == "outbound" else 1
    if amount * wanted <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"payment {payment_id} is {payment.direction} — its cash landing "
                f"is a {'negative' if wanted < 0 else 'positive'} register line, "
                f"not {amount}"
            ),
        )


POSITIVE_TYPES = frozenset({"deposit", "interest", "transfer_in"})
NEGATIVE_TYPES = frozenset({"withdrawal", "fee", "transfer_out"})


def _sign_error(amount: float, trans_type: str) -> str | None:
    """The teaching half of the database's own sign CHECK — the refusal
    reaches the agent as words instead of a constraint name."""
    if trans_type in POSITIVE_TYPES and amount < 0:
        return f"a {trans_type} moves money IN — its amount is positive, not {amount}"
    if trans_type in NEGATIVE_TYPES and amount > 0:
        return f"a {trans_type} moves money OUT — its amount is negative, not {amount}"
    return None


def _derived_type(amount: float, stated: str | None) -> str:
    if stated is not None:
        return stated
    return "deposit" if amount > 0 else "withdrawal"


# --- accounts ---------------------------------------------------------------


@router.get("/fin-accounts", response_model=FinAccountListEnvelope, response_model_exclude_unset=True)
def list_fin_accounts(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    account_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    _require_treasury(actor)
    return list_rows(
        db,
        select(FinAccount).where(FinAccount.tenant_id == actor.tenant_id),
        filters={
            FinAccount.account_type: account_type,
            FinAccount.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(FinAccount.name, FinAccount.institution, FinAccount.account_number),
        order_by=(FinAccount.created_at.asc(), FinAccount.id.asc()),
        pagination=requested_pagination(page, size),
        read_model=FinAccountRead,
    )


@router.post("/fin-accounts", response_model=FinAccountEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_fin_account(
    payload: CreateFinAccountRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_treasury(actor)
    tenant_id = actor.tenant_id
    require_type_option(db, tenant_id, "fin_account_type", payload.account_type)
    account = FinAccount(
        tenant_id=tenant_id,
        name=payload.name,
        institution=payload.institution,
        account_number=payload.account_number,
        account_type=payload.account_type,
        currency=payload.currency,
        status=payload.status,
        remarks=payload.remarks,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(account)
    try:
        db.flush()
        if payload.opening_balance is not None and payload.opening_balance != 0:
            # the opening balance IS the register's first row — the balance
            # column is derived and starts moving here, never by an edit
            post_fin_account_trans(
                db, account=account,
                amount=payload.opening_balance,
                trans_type="opening",
                trans_date=payload.opening_date,
                description="opening balance",
                created_by=attributed(actor, None),
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"a fin account named {payload.name!r} already exists",
        )
    db.refresh(account)
    return envelope(FinAccountRead.model_validate(account).model_dump(by_alias=True))


@router.get("/fin-accounts/{account_id}", response_model=FinAccountEnvelope,
            response_model_exclude_unset=True)
def get_fin_account(
    account_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_treasury(actor)
    account = get_scoped_or_404(db, FinAccount, actor.tenant_id, account_id)
    return envelope(FinAccountRead.model_validate(account).model_dump(by_alias=True))


@router.patch("/fin-accounts/{account_id}", response_model=FinAccountEnvelope,
              response_model_exclude_unset=True)
def update_fin_account(
    account_id: str,
    payload: UpdateFinAccountRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_treasury(actor)
    account = get_scoped_or_404(db, FinAccount, actor.tenant_id, account_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("account_type"):
        require_type_option(db, actor.tenant_id, "fin_account_type", updates["account_type"])
    if "custom_fields" in updates:
        account.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(account, field, value)
    commit_or_conflict(db, "a fin account with that name already exists")
    db.refresh(account)
    return envelope(FinAccountRead.model_validate(account).model_dump(by_alias=True))


@router.delete("/fin-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fin_account(
    account_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, FinAccount, account_id, permission="fin_account.manage")


# --- the register -----------------------------------------------------------


@router.get("/fin-account-transactions", response_model=FinAccountTransListEnvelope,
            response_model_exclude_unset=True)
def list_fin_account_transactions(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    fin_account_id: str | None = None,
    trans_type: str | None = None,
    payment_id: str | None = None,
    reference_no: str | None = None,
    unlinked: bool = False,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    _require_treasury(actor)
    stmt = select(FinAccountTrans).where(FinAccountTrans.tenant_id == actor.tenant_id)
    if unlinked:
        # the reconciliation queue, derived: no payment, no entity — nothing
        # of ours yet explains this bank fact
        stmt = stmt.where(
            FinAccountTrans.payment_id.is_(None), FinAccountTrans.entity_id.is_(None)
        )
    if date_from is not None:
        stmt = stmt.where(FinAccountTrans.trans_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(FinAccountTrans.trans_date <= date_to)
    return list_rows(
        db, stmt,
        filters={
            FinAccountTrans.fin_account_id: fin_account_id,
            FinAccountTrans.trans_type: trans_type,
            FinAccountTrans.payment_id: payment_id,
            FinAccountTrans.reference_no: reference_no,
        },
        keyword=keyword,
        keyword_columns=(
            FinAccountTrans.counterparty,
            FinAccountTrans.description,
            FinAccountTrans.reference_no,
            cast(FinAccountTrans.amount, String),
        ),
        order_by=(FinAccountTrans.trans_date.desc(), FinAccountTrans.created_at.desc(),
                  FinAccountTrans.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=FinAccountTransRead,
    )


@router.post("/fin-account-transactions", response_model=FinAccountTransEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_fin_account_trans(
    payload: CreateFinAccountTransRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    _require_treasury(actor)
    tenant_id = actor.tenant_id
    account = _require_active_account(db, tenant_id, payload.fin_account_id)
    if payload.trans_type == "opening":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "`opening` is the account-create's first row — a later opening "
                "would rewrite history; corrections are counter-entries"
            ),
        )
    require_entity_uuid(payload.entity_id)
    _require_link_coherence(db, tenant_id, payload.payment_id, payload.amount)
    trans_type = _derived_type(payload.amount, payload.trans_type)
    sign_problem = _sign_error(payload.amount, trans_type)
    if sign_problem:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=sign_problem)
    # The posting is INSIDE the try on purpose. `fin_account_trans_reference_uq`
    # is a partial unique index, so it fires on the flush that
    # post_fin_account_trans does — not on the commit. With only the commit
    # guarded, the except below never ran and a re-imported statement line came
    # back 500 instead of the 409 it plainly means to give (found live). SQLite
    # cannot build a `where reference_no is not null` index, which is why the
    # whole SQLite suite was blind to it; tests/postgres pins it now.
    try:
        trans = post_fin_account_trans(
            db, account=account,
            amount=payload.amount,
            trans_type=trans_type,
            trans_date=payload.trans_date,
            gross_amount=payload.gross_amount,
            fee_amount=payload.fee_amount,
            counterparty=payload.counterparty,
            description=payload.description,
            reference_no=payload.reference_no,
            payment_id=payload.payment_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            custom_fields=payload.custom_fields,
            created_by=attributed(actor, None),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        # Zero amount, the gross/fee/net identity, the sign rules and the
        # trans_type vocabulary are all refused as 422 before we get here, so
        # the reference index is what is left — but only when a reference was
        # actually sent. Anything else is a defect worth seeing whole, not a
        # 409 blaming a field the caller never used.
        if payload.reference_no is None:
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"reference_no {payload.reference_no!r} already sits on this "
                "account's register — the same statement line is one row, ever"
            ),
        )
    db.refresh(trans)
    return envelope(FinAccountTransRead.model_validate(trans).model_dump(by_alias=True))


@router.patch("/fin-account-transactions/{trans_id}", response_model=FinAccountTransEnvelope,
              response_model_exclude_unset=True)
def link_fin_account_trans(
    trans_id: str,
    payload: LinkFinAccountTransRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The bank facts are frozen; the LINKS are ours to set, correct and
    clear — the frozen-row-gains-a-name rule. Any bank-fact field in this
    PATCH is refused by the strict request model, which is the immutability
    teaching delivered as a 422 naming the field."""
    _require_treasury(actor)
    trans = get_scoped_or_404(db, FinAccountTrans, actor.tenant_id, trans_id)
    updates = payload.model_dump(exclude_unset=True)
    if "entity_id" in updates:
        require_entity_uuid(updates["entity_id"])
    if "payment_id" in updates and updates["payment_id"] is not None:
        _require_link_coherence(db, actor.tenant_id, updates["payment_id"], float(trans.amount))
    for field, value in updates.items():
        setattr(trans, field, value)
    db.commit()
    db.refresh(trans)
    return envelope(FinAccountTransRead.model_validate(trans).model_dump(by_alias=True))


@router.post("/fin-account-transactions/bulk")
def bulk_import_fin_account_trans(
    payload: BulkFinAccountTransImportRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Statement import, the master-data contract: dry_run runs the identical
    write path and rolls back; `reference_no` is the idempotence key — the
    same line re-imported reports `unchanged`, and the same reference with a
    DIFFERENT amount is an error row, because a bank that reuses line ids
    with new numbers is a question for a person, not a silent overwrite."""
    _require_treasury(actor)
    tenant_id = actor.tenant_id
    account = _require_active_account(db, tenant_id, payload.fin_account_id)

    # only the batch's own reference numbers can collide — one IN read, not
    # the account's whole register in memory for a fifty-line statement
    batch_refs = {row.reference_no for row in payload.rows if row.reference_no}
    existing_by_ref: dict[str, FinAccountTrans] = {
        t.reference_no: t
        for t in db.scalars(
            select(FinAccountTrans).where(
                FinAccountTrans.tenant_id == tenant_id,
                FinAccountTrans.fin_account_id == account.id,
                FinAccountTrans.reference_no.in_(batch_refs),
            )
        )
    } if batch_refs else {}
    seen_in_batch: set[str] = set()
    results: list[dict] = []
    created = unchanged = failed = 0
    aborted = False
    for index, row in enumerate(payload.rows):
        error: str | None = None
        trans_type = _derived_type(row.amount, row.trans_type)
        if row.trans_type == "opening":
            error = "`opening` belongs to account creation, not a statement"
        elif _sign_error(row.amount, trans_type):
            error = _sign_error(row.amount, trans_type)
        elif row.reference_no and row.reference_no in seen_in_batch:
            error = f"duplicate reference_no {row.reference_no!r} in this batch"
        elif row.reference_no and row.reference_no in existing_by_ref:
            prior = existing_by_ref[row.reference_no]
            if float(prior.amount) == row.amount:
                unchanged += 1
                results.append({"index": index, "reference_no": row.reference_no,
                                "outcome": "unchanged", "id": prior.id})
                continue
            error = (
                f"reference_no {row.reference_no!r} already on the register "
                f"with amount {float(prior.amount)} — a changed statement line "
                "is a person's question, never an overwrite"
            )
        if error is None:
            post_fin_account_trans(
                db, account=account,
                amount=row.amount,
                trans_type=trans_type,
                trans_date=row.trans_date,
                gross_amount=row.gross_amount,
                fee_amount=row.fee_amount,
                counterparty=row.counterparty,
                description=row.description,
                reference_no=row.reference_no,
                custom_fields=row.custom_fields,
                created_by=attributed(actor, None),
            )
            created += 1
            if row.reference_no:
                seen_in_batch.add(row.reference_no)
            results.append({"index": index, "reference_no": row.reference_no,
                            "outcome": "created"})
            continue
        failed += 1
        results.append({"index": index, "reference_no": row.reference_no,
                        "outcome": "error", "error": error})
        if payload.on_error == "abort":
            aborted = True
            break

    applied = not payload.dry_run and not aborted
    if applied:
        db.commit()
    else:
        db.rollback()
    return envelope({
        "dry_run": payload.dry_run,
        "applied": applied,
        "summary": {"total": len(payload.rows), "created": created,
                    "unchanged": unchanged, "failed": failed},
        "results": results,
    })
