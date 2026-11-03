"""Points redeemed on an order — docs/billing-accounts.md, "Redeeming points on
an order".

"500 points for ¥5 off" stays two facts, and the server still converts
nothing: a `redeemed` entry of -500 on the customer's points account, and a
`points` discount of -5 on the order. What this module adds is the act that
writes them together and the thread that ties them:

* `POST /sales-orders/{id}/redeem-points` — both facts in one transaction,
  under the account's lock and floor; the discount names the entry
  (`billing_account_entry_id`), one live discount per redemption.
* `POST /sales-orders/{id}/restore-points` — points given back
  (`redemption_reversed`), each entry naming the redemption it undoes, never
  more in all than it spent. With `remove_discount` the discount comes off an
  order still being edited, with as many of the points as the agent gives
  back.
* `GET /sales-orders/{id}/points-redemptions` — what was spent on the order,
  what came back, what is outstanding.

The points are spent when the order is placed, not when it is billed, so the
same points cannot pay for two open orders. Billing the discount is a
`points` invoice line naming the same redemption; it moves no points.

Whose points may pay for an order, whether a cancelled order's or a removed
discount's points come back, and how many of a partly returned order's, are
the workspace's rules — the agent's write, as releasing a cancelled order's
credit is. The integrity audit names redemptions whose discount no longer
stands and whose points did not come back.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm import Session

from app.api.billing import get_active_account_or_404, lock_for_update, post_account_entries
from app.api.common import (
    _adjustment_write_gate,
    envelope,
    get_active_document_or_404,
    record_line_audit,
    require_line_on_document,
)
from app.api.common.charging import recheck_charged_document
from app.api.common.numbering import ADJUSTMENT_FAMILIES
from app.api.deps import Actor, get_actor, require_permission
from app.api.sales import quotation_item_effective_amount
from app.db.session import get_db
from app.models import (
    BillingAccount,
    BillingAccountEntry,
    Invoice,
    InvoiceItem,
    SalesOrder,
    SalesOrderAdjustment,
    SalesOrderItem,
)
from app.schemas import (
    PointsRedemptionEnvelope,
    PointsRedemptionRead,
    RedeemPointsRequest,
    RestorePointsRequest,
    SalesOrderAdjustmentRead,
)

router = APIRouter()

REDEEMED = "redeemed"
GIVEN_BACK = "redemption_reversed"
POINTS = "points"
CENT = Decimal("0.01")

# set while this module writes or moves a linked discount; any other path
# that touches one is refused at flush
_BRIDGE = "points_redemption_bridge"


@contextmanager
def redemption_bridge(db: Session):
    db.info[_BRIDGE] = True
    try:
        yield
    finally:
        db.info.pop(_BRIDGE, None)


def _cents(value: float, field: str) -> Decimal:
    amount = Decimal(str(value))
    if amount.as_tuple().exponent < -2:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"{field} carries more than two decimals — the ledger records cents")
    return amount


def given_back(db: Session, tenant_id: str, entry_id: str) -> Decimal:
    return Decimal(str(db.scalar(select(func.coalesce(func.sum(BillingAccountEntry.amount), 0)).where(
        BillingAccountEntry.tenant_id == tenant_id, BillingAccountEntry.reason == GIVEN_BACK,
        BillingAccountEntry.entity_type == "billing_account_entry", BillingAccountEntry.entity_id == entry_id,
    )) or 0))


def _live_discount(db: Session, tenant_id: str, entry_id: str) -> SalesOrderAdjustment | None:
    return db.scalar(select(SalesOrderAdjustment).where(
        SalesOrderAdjustment.tenant_id == tenant_id, SalesOrderAdjustment.billing_account_entry_id == entry_id,
        SalesOrderAdjustment.deleted_at.is_(None),
    ))


def _order_net(db: Session, order: SalesOrder, item_id: str | None) -> Decimal:
    """What the order (or one line) comes to now: its lines' value plus its
    live adjustments — what a discount may not take below zero."""
    items = db.scalars(select(SalesOrderItem).where(
        SalesOrderItem.tenant_id == order.tenant_id, SalesOrderItem.order_id == order.id,
        SalesOrderItem.deleted_at.is_(None), *( [SalesOrderItem.id == item_id] if item_id else [] ),
    )).all()
    lines = sum((Decimal(str(quotation_item_effective_amount(item) or 0)) for item in items), Decimal(0))
    adjustments = select(func.coalesce(func.sum(SalesOrderAdjustment.amount), 0)).where(
        SalesOrderAdjustment.tenant_id == order.tenant_id, SalesOrderAdjustment.order_id == order.id,
        SalesOrderAdjustment.deleted_at.is_(None),
    )
    if item_id:
        adjustments = adjustments.where(SalesOrderAdjustment.order_item_id == item_id)
    return lines + Decimal(str(db.scalar(adjustments) or 0))


def _read(db: Session, entry: BillingAccountEntry, order_id: str, account: BillingAccount) -> dict:
    spent = -Decimal(str(entry.amount))
    back = given_back(db, entry.tenant_id, entry.id)
    adjustment = _live_discount(db, entry.tenant_id, entry.id)
    return PointsRedemptionRead(
        entry_id=entry.id, billing_account_id=entry.billing_account_id, order_id=order_id,
        points=float(spent), given_back=float(back), outstanding=float(spent - back),
        adjustment=SalesOrderAdjustmentRead.model_validate(adjustment) if adjustment is not None else None,
        balance=round(float(account.balance or 0), 2),
    ).model_dump(by_alias=True)


def _redemptions_of(db: Session, order: SalesOrder) -> list[BillingAccountEntry]:
    """The redemptions this order carries: those written on it, and those
    whose discount it carries now (a revision takes its source's)."""
    carried = select(SalesOrderAdjustment.billing_account_entry_id).where(
        SalesOrderAdjustment.tenant_id == order.tenant_id, SalesOrderAdjustment.order_id == order.id,
        SalesOrderAdjustment.deleted_at.is_(None), SalesOrderAdjustment.billing_account_entry_id.is_not(None),
    )
    return list(db.scalars(select(BillingAccountEntry).where(
        BillingAccountEntry.tenant_id == order.tenant_id, BillingAccountEntry.reason == REDEEMED,
        ((BillingAccountEntry.entity_type == "sales_order") & (BillingAccountEntry.entity_id == order.id))
        | BillingAccountEntry.id.in_(carried),
    ).order_by(BillingAccountEntry.effective_at.asc(), BillingAccountEntry.id.asc())))


@router.post("/sales-orders/{order_id}/redeem-points", response_model=PointsRedemptionEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def redeem_points(
    order_id: str,
    payload: RedeemPointsRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Spend the customer's points for a discount on this order, in one act.
    Needs the order's adjustment grant (order.submit_own, own orders for a
    member) and billing_account.post:points; the order must still be
    editable, and the discount may not take the order (or the line) below
    zero."""
    tenant_id = actor.tenant_id
    family = ADJUSTMENT_FAMILIES[SalesOrderAdjustment]
    require_permission(actor, family.permission)
    order = _adjustment_write_gate(db, actor, family, order_id)
    if order.order_kind != "order":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="points pay for an order, not for a return")
    account = get_active_account_or_404(db, tenant_id, payload.billing_account_id)
    if account.unit_type != "points":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"account {account.account_code} holds {account.unit}, not points")
    points = _cents(payload.points, "points")
    discount = _cents(payload.discount_amount, "discount_amount")
    if payload.order_item_id:
        require_line_on_document(db, tenant_id, SalesOrderItem, "order_id", "order_item_id", order.id,
                                 payload.order_item_id)
    net = _order_net(db, order, payload.order_item_id)
    if discount > net:
        where = "this line" if payload.order_item_id else "the order"
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"{where} comes to {net:.2f} — a discount of {discount:.2f} would take it below zero")
    description = payload.description or f"{points:f} points redeemed on {order.order_no}"
    entry = post_account_entries(db, actor, account, [SimpleNamespace(
        amount=float(-points), reason=REDEEMED, description=description[:500],
        entity_type="sales_order", entity_id=order.id, expires_at=None, effective_at=None,
    )])[0]
    db.flush()
    with redemption_bridge(db):
        adjustment = SalesOrderAdjustment(
            tenant_id=tenant_id, order_id=order.id, order_item_id=payload.order_item_id, adjustment_type=POINTS,
            description=description[:500], amount=float(-discount), billing_account_entry_id=entry.id,
            metadata_jsonb={"points": float(points)},
        )
        db.add(adjustment)
        db.flush()
    record_line_audit(db, actor, SalesOrder, order.id, adjustment.id, "adjustment_added")
    recheck_charged_document(db, order, label="sales_orders")
    db.commit()
    db.refresh(account)
    return envelope(_read(db, entry, order.id, account))


@router.post("/sales-orders/{order_id}/restore-points", response_model=PointsRedemptionEnvelope,
             response_model_exclude_unset=True)
def restore_points(
    order_id: str,
    payload: RestorePointsRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Give back points from a redemption on this order. `entry_id` names it
    when the order carries more than one. `points` defaults to all not yet
    given back; 0 gives none. With `remove_discount` the discount comes off
    too, on an order still editable; how many points return with it is the
    workspace's rule."""
    tenant_id = actor.tenant_id
    order = get_active_document_or_404(db, SalesOrder, tenant_id, order_id)
    redemptions = _redemptions_of(db, order)
    if payload.entry_id:
        entry = next((row for row in redemptions if row.id == payload.entry_id), None)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"order {order.order_no} carries no redemption {payload.entry_id}")
    elif len(redemptions) == 1:
        entry = redemptions[0]
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(f"order {order.order_no} carries {len(redemptions)} redemptions — name one with entry_id "
                    "(GET /sales-orders/{id}/points-redemptions)") if redemptions
            else f"order {order.order_no} carries no points redemption",
        )
    # the account is locked before the outstanding figure is read: the check
    # and the write are one critical section, as the expiry sweep's are
    account = lock_for_update(db, tenant_id, BillingAccount, entry.billing_account_id) \
        or get_active_account_or_404(db, tenant_id, entry.billing_account_id)
    outstanding = -Decimal(str(entry.amount)) - given_back(db, tenant_id, entry.id)
    if outstanding <= 0 and not payload.remove_discount:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"every point of redemption {entry.id} has already been given back")
    amount = _cents(payload.points, "points") if payload.points is not None else outstanding
    if amount == 0 and not payload.remove_discount:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="points: 0 gives nothing back — it only goes with remove_discount")
    if amount > outstanding:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"redemption {entry.id} has {outstanding:f} points not yet given back, not {amount:f}")
    adjustment = _live_discount(db, tenant_id, entry.id)
    if payload.remove_discount:
        family = ADJUSTMENT_FAMILIES[SalesOrderAdjustment]
        require_permission(actor, family.permission)
        if adjustment is None or adjustment.order_id != order.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"order {order.order_no} carries no live discount for this redemption")
        _adjustment_write_gate(db, actor, family, order.id)
    if amount > 0:
        post_account_entries(db, actor, account, [SimpleNamespace(
            amount=float(amount), reason=GIVEN_BACK,
            description=(payload.description or f"{amount:f} points given back from {order.order_no}")[:500],
            entity_type="billing_account_entry", entity_id=entry.id, expires_at=payload.expires_at,
            effective_at=None,
        )])
    if payload.remove_discount:
        with redemption_bridge(db):
            adjustment.deleted_at = datetime.now(timezone.utc)
            db.flush()
        record_line_audit(db, actor, SalesOrder, order.id, adjustment.id, "adjustment_removed")
    db.commit()
    db.refresh(account)
    return envelope(_read(db, entry, order.id, account))


@router.get("/sales-orders/{order_id}/points-redemptions")
def list_points_redemptions(
    order_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Each redemption the order carries: points spent, given back,
    outstanding, and the discount that stands for it (null once removed)."""
    order = get_active_document_or_404(db, SalesOrder, actor.tenant_id, order_id)
    rows = []
    for entry in _redemptions_of(db, order):
        account = db.get(BillingAccount, entry.billing_account_id)
        rows.append(_read(db, entry, order.id, account))
    return envelope(rows)


# --- what holds the two facts together, on every write path --------------------


def _refuse(code: int, detail: str) -> None:
    raise HTTPException(status_code=code, detail=detail)


def _check_adjustment(session: Session, adjustment: SalesOrderAdjustment) -> None:
    bridged = session.info.get(_BRIDGE)
    new = adjustment in session.new
    if adjustment.adjustment_type == POINTS and not adjustment.billing_account_entry_id:
        _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
                "a points discount is written by POST /sales-orders/{id}/redeem-points, which spends the points with it")
    if adjustment.billing_account_entry_id and adjustment.adjustment_type != POINTS:
        _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, "only a points discount names a redemption")
    if bridged:
        return
    if new:
        if adjustment.billing_account_entry_id:
            _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "a discount names a redemption only through POST /sales-orders/{id}/redeem-points")
        return
    state = inspect(adjustment)
    was_linked = state.attrs.billing_account_entry_id.history.deleted or [adjustment.billing_account_entry_id]
    if not any(was_linked):
        return
    watched = ("amount", "adjustment_type", "order_item_id", "order_id", "deleted_at", "billing_account_entry_id")
    if any(state.attrs[name].history.has_changes() for name in watched):
        _refuse(status.HTTP_409_CONFLICT,
                "this discount was paid for with points — change it through POST /sales-orders/{id}/restore-points "
                "(remove_discount) and redeem again")


def _check_invoice_line(session: Session, item: InvoiceItem) -> None:
    linked = item.billing_account_entry_id
    if item.invoice_item_type == POINTS and not linked:
        _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
                "a points line names the order's redemption it bills (billing_account_entry_id)")
    if linked and item.invoice_item_type != POINTS:
        _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, "only a points line names a redemption")
    if not linked:
        return
    state = inspect(item)
    if item not in session.new and not any(
        state.attrs[name].history.has_changes()
        for name in ("billing_account_entry_id", "amount", "invoice_item_type", "deleted_at")
    ):
        return
    entry = session.get(BillingAccountEntry, linked)
    invoice = session.get(Invoice, item.invoice_id)
    if entry is None or entry.tenant_id != item.tenant_id or entry.reason != REDEEMED:
        _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, f"billing_account_entry_id {linked} is not a redemption")
    if invoice is None or invoice.direction != "sales":
        _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, "points discounts are billed on sales invoices")
    discount = _live_discount(session, item.tenant_id, linked)
    order = session.get(SalesOrder, discount.order_id) if discount is not None else None
    if order is not None and order.customer_id != invoice.customer_id:
        _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"redemption {linked} discounts an order of another customer, not this invoice's customer's")
    allowed = -Decimal(str(discount.amount)) if discount is not None else Decimal(0)
    billed = Decimal(0)
    for row in session.scalars(select(InvoiceItem).where(
        InvoiceItem.tenant_id == item.tenant_id, InvoiceItem.billing_account_entry_id == linked,
        InvoiceItem.deleted_at.is_(None), InvoiceItem.id != item.id,
    )):
        if session.get(Invoice, row.invoice_id).deleted_at is None:
            billed -= Decimal(str(row.amount or 0))
    if item.deleted_at is None:
        billed -= Decimal(str(item.amount or 0))
    if billed < 0 or billed > allowed:
        _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"the order's points discount is {allowed:.2f}; its invoice lines would bill {billed:.2f} of it — "
                "a points line bills that discount, at most once (a credit note gives it back)")


@event.listens_for(Session, "before_flush")
def _points_threads(session: Session, flush_context, instances) -> None:
    """Every write of an order adjustment or an invoice line passes here,
    whichever endpoint, save or import made it: a points discount exists only
    with the redemption that paid for it, and is billed at most once."""
    touched = [obj for obj in (*session.new, *session.dirty)
               if isinstance(obj, (SalesOrderAdjustment, InvoiceItem))]
    if not touched:
        return
    with session.no_autoflush:
        for obj in touched:
            if isinstance(obj, SalesOrderAdjustment):
                _check_adjustment(session, obj)
            else:
                _check_invoice_line(session, obj)
