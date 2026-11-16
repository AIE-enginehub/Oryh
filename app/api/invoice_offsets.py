"""A credit note applied against an open invoice — plan
docs/plans/accounting-core-2026-11-08.md, phase 2.

A credit note settles a debt without money moving: 300 of a credit note set
against an open invoice of the same customer is 300 that invoice no longer
waits for. Both running totals move, so outstanding stays one derived number
on each side. What remains of a credit note can instead be refunded — an
outbound payment applied to a sales credit note through `/payments/{id}/apply`.

Whether to offset or refund, and against which invoice, is the agent's
decision on the workspace's rule. The server holds the arithmetic: same
party, direction and currency; never more than the invoice still owes or the
credit note still has; a counter-row with a negative amount takes one back.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.billing import (
    ensure_invoice_visible,
    invoice_billed_total,
    live_invoice_items,
    lock_for_update,
    require_settleable,
)
from app.api.common import envelope, get_scoped_or_404
from app.api.deps import Actor, attributed, get_actor, require_permission
from app.db.session import get_db
from app.models import Invoice, InvoiceOffset
from app.schemas import CreateInvoiceOffsetRequest, InvoiceOffsetEnvelope, InvoiceOffsetListEnvelope, InvoiceOffsetRead
from app.services.audit import record_audit

router = APIRouter()

CENT = Decimal("0.005")


def _refuse(code: int, detail: str):
    raise HTTPException(status_code=code, detail=detail)


def _money(value) -> Decimal:
    return Decimal(str(value or 0))


@router.post("/invoices/{credit_note_id}/offsets", response_model=InvoiceOffsetEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_invoice_offset(
    credit_note_id: str,
    payload: CreateInvoiceOffsetRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Set part of a credit note against an open invoice or debit note of the
    same party, direction and currency. Needs `payment.apply`, the settlement
    grant. Send `Idempotency-Key`: a retried offset must not apply twice."""
    require_permission(actor, "payment.apply")
    tenant_id = actor.tenant_id
    for invoice_id in sorted((credit_note_id, payload.invoice_id)):
        # both rows locked in id order, so two offsets crossing the same pair
        # serialize instead of deadlocking
        lock_for_update(db, tenant_id, Invoice, invoice_id)
    note = get_scoped_or_404(db, Invoice, tenant_id, credit_note_id)
    target = get_scoped_or_404(db, Invoice, tenant_id, payload.invoice_id)
    for row in (note, target):
        ensure_invoice_visible(actor, row)
        if row.deleted_at is not None:
            _refuse(status.HTTP_404_NOT_FOUND, "Invoice not found")
        require_settleable(db, row)
    if note.invoice_kind != "credit_note":
        _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{note.invoice_no} is not a credit note")
    if target.invoice_kind == "credit_note":
        _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{target.invoice_no} is a credit note — a credit is set against what is owed")
    for field in ("direction", "customer_id", "vendor_id", "currency"):
        if getattr(note, field) != getattr(target, field):
            _refuse(status.HTTP_409_CONFLICT,
                    f"{note.invoice_no} and {target.invoice_no} differ in {field} — a credit settles a debt of "
                    "the same party, the same way round, in the same currency")
    amount = _money(payload.amount)
    target_billed = _money(invoice_billed_total(target, live_invoice_items(db, tenant_id, target.id)))
    note_billed = _money(invoice_billed_total(note, live_invoice_items(db, tenant_id, note.id)))
    target_after = _money(target.applied_amount) + amount
    note_after = _money(note.applied_amount) - amount
    if target_after > target_billed + CENT:
        _refuse(status.HTTP_409_CONFLICT,
                f"{target.invoice_no} still owes {target_billed - _money(target.applied_amount):.2f}, not {amount:.2f}")
    if note_after < note_billed - CENT:
        _refuse(status.HTTP_409_CONFLICT,
                f"credit note {note.invoice_no} has {_money(note.applied_amount) - note_billed:.2f} left to give, "
                f"not {amount:.2f}")
    if amount < 0:
        # what this pair has offset, not what each document holds in all: an
        # invoice also settled by cash would otherwise give a credit back that
        # was never set against it, and the note could then be used twice
        between = _money(db.scalar(select(func.coalesce(func.sum(InvoiceOffset.amount), 0)).where(
            InvoiceOffset.tenant_id == tenant_id, InvoiceOffset.credit_note_id == note.id,
            InvoiceOffset.invoice_id == target.id)))
        if between + amount < -CENT:
            _refuse(status.HTTP_409_CONFLICT,
                    f"{note.invoice_no} has {between:.2f} set against {target.invoice_no} — "
                    f"taking back {-amount:.2f} is more than was offset between these two")
    offset = InvoiceOffset(tenant_id=tenant_id, credit_note_id=note.id, invoice_id=target.id, amount=float(amount),
                           note=payload.note, created_by=attributed(actor, None))
    db.add(offset)
    target.applied_amount = float(round(target_after, 2))
    note.applied_amount = float(round(note_after, 2))
    db.flush()
    record_audit(db, tenant_id=tenant_id, action="invoice.offset", entity_type="invoice", entity_id=note.id,
                 actor=actor.label,
                 detail={"credit_note_no": note.invoice_no, "invoice_no": target.invoice_no, "amount": float(amount)})
    db.commit()
    db.refresh(offset)
    return envelope(InvoiceOffsetRead.model_validate(offset).model_dump(by_alias=True))


@router.get("/invoices/{invoice_id}/offsets", response_model=InvoiceOffsetListEnvelope,
            response_model_exclude_unset=True)
def list_invoice_offsets(
    invoice_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Every offset this invoice takes part in, as the credit note or as the
    invoice it settled, oldest first."""
    invoice = get_scoped_or_404(db, Invoice, actor.tenant_id, invoice_id)
    ensure_invoice_visible(actor, invoice)
    rows = db.scalars(select(InvoiceOffset).where(
        InvoiceOffset.tenant_id == actor.tenant_id,
        or_(InvoiceOffset.credit_note_id == invoice.id, InvoiceOffset.invoice_id == invoice.id),
    ).order_by(InvoiceOffset.created_at.asc(), InvoiceOffset.id.asc()))
    return envelope([InvoiceOffsetRead.model_validate(row).model_dump(by_alias=True) for row in rows])
