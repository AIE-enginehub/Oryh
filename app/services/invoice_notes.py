"""Credit and debit notes — plan docs/plans/accounting-core-2026-11-08.md, phase 2.

A note is an invoice of another kind that names the invoice it corrects, the
way a return is an order of another kind. These rules hold on every write
path (create with inline lines, a line's own POST and PATCH, the whole-lines
save, imports), so they listen at the ORM as the points thread does:

* What a note is never changes: its kind and its original are fixed, and an
  invoice's kind stays `invoice`.
* A note corrects an invoice that was stood behind (past its editable
  states), of the same direction, party and currency. Notes are for sales
  and purchase invoices only.
* Totals are signed by kind: an invoice or a debit note totals 0 or more, a
  credit note 0 or less.
* A credit note never takes back more than was billed: per original line,
  the credit notes naming it move it toward zero and never past it; in total,
  the credit notes on an invoice never exceed what it and its debit notes
  billed.
* An invoice that live notes name is not deleted.

Shape is checked before each flush; the ceilings once, as the write commits,
when every line of it — however many rode one call, each flushed on its own
— is in the database to be summed. Checked per flush, a note crediting a
discount (+20) and the goods (-60) looked positive after its first line.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceItem
from app.services.state_machines import editable_states, get_builtin_machine

NOTE_KINDS = ("credit_note", "debit_note")
NOTE_DIRECTIONS = ("sales", "purchase")
_PENDING = "oryh_invoice_notes_originals"
CENT = Decimal("0.01")


def _refuse(detail: str, code: int = status.HTTP_422_UNPROCESSABLE_CONTENT) -> None:
    raise HTTPException(status_code=code, detail=detail)


def line_amount(item: InvoiceItem) -> Decimal:
    if item.amount is not None:
        return Decimal(str(item.amount))
    if item.quantity is not None and item.unit_price is not None:
        return Decimal(str(item.quantity)) * Decimal(str(item.unit_price))
    return Decimal(0)


def _live_items(session: Session, invoice_id: str) -> list[InvoiceItem]:
    return list(session.scalars(select(InvoiceItem).where(
        InvoiceItem.invoice_id == invoice_id, InvoiceItem.deleted_at.is_(None))))


def billed(session: Session, invoice: Invoice) -> Decimal:
    if invoice.total_amount is not None:
        return Decimal(str(invoice.total_amount))
    return sum((line_amount(item) for item in _live_items(session, invoice.id)), Decimal(0))


def _check_note(session: Session, note: Invoice) -> None:
    original = session.get(Invoice, note.original_invoice_id)
    if original is None or original.tenant_id != note.tenant_id or original.deleted_at is not None:
        _refuse(f"original_invoice_id {note.original_invoice_id} names no live invoice")
    if original.invoice_kind != "invoice":
        _refuse(f"{original.invoice_no} is itself a {original.invoice_kind.replace('_', ' ')} — "
                "a note corrects the invoice")
    if note.direction not in NOTE_DIRECTIONS:
        _refuse(f"a {note.direction} invoice takes no notes — a payslip or reimbursement is corrected by "
                "voiding and reissuing it")
    for field in ("direction", "customer_id", "vendor_id", "currency"):
        if getattr(note, field) != getattr(original, field):
            _refuse(f"a note keeps its original's {field}: {original.invoice_no} has "
                    f"{getattr(original, field)!r}, this note {getattr(note, field)!r}")
    machine = get_builtin_machine(session, note.tenant_id, "invoice")
    if original.status in editable_states(machine, "invoice"):
        _refuse(f"{original.invoice_no} is {original.status!r}, still editable — correct it in place; a note "
                "corrects an invoice once it has been submitted", status.HTTP_409_CONFLICT)


@event.listens_for(Session, "before_flush")
def _note_shapes(session: Session, flush_context, instances) -> None:
    invoices = [o for o in (*session.new, *session.dirty) if isinstance(o, Invoice)]
    items = [o for o in (*session.new, *session.dirty) if isinstance(o, InvoiceItem)]
    if not invoices and not items:
        return
    originals: set[str] = session.info.setdefault(_PENDING, set())
    with session.no_autoflush:
        for invoice in invoices:
            if invoice not in session.new:
                state = inspect(invoice)
                for field in ("invoice_kind", "original_invoice_id"):
                    if state.attrs[field].history.has_changes():
                        _refuse(f"{field} is what this document is — it does not change; void it and file "
                                "the right one", status.HTTP_409_CONFLICT)
            elif invoice.invoice_kind in NOTE_KINDS:
                _check_note(session, invoice)
            if invoice.total_amount is not None:
                total = Decimal(str(invoice.total_amount))
                if invoice.invoice_kind == "credit_note" and total > 0:
                    _refuse("a credit note totals 0 or less — what it gives back is negative")
                if invoice.invoice_kind != "credit_note" and total < 0:
                    _refuse(f"an {invoice.invoice_kind.replace('_', ' ')} totals 0 or more — a credit is a "
                            "credit note naming the invoice it corrects")
            if invoice.invoice_kind in NOTE_KINDS:
                originals.add(invoice.original_invoice_id)
            elif invoice not in session.new:
                originals.add(invoice.id)
        for item in items:
            parent = session.get(Invoice, item.invoice_id)
            if parent is None:
                continue
            if item.original_invoice_item_id:
                if parent.invoice_kind not in NOTE_KINDS:
                    _refuse("original_invoice_item_id belongs on a credit or debit note's line")
                corrected = session.get(InvoiceItem, item.original_invoice_item_id)
                if corrected is None or corrected.invoice_id != parent.original_invoice_id:
                    _refuse(f"original_invoice_item_id {item.original_invoice_item_id} is not a line of the "
                            "invoice this note corrects")
            if parent.invoice_kind in NOTE_KINDS:
                originals.add(parent.original_invoice_id)
            else:
                originals.add(parent.id)


@event.listens_for(Session, "before_commit")
def _note_ceilings(session: Session) -> None:
    if not session.info.get(_PENDING):
        return
    session.flush()
    originals = session.info.pop(_PENDING, None) or set()
    with session.no_autoflush:
        for original_id in originals:
            original = session.get(Invoice, original_id)
            if original is None or original.invoice_kind != "invoice":
                continue
            notes = list(session.scalars(select(Invoice).where(
                Invoice.original_invoice_id == original.id, Invoice.deleted_at.is_(None))))
            if not notes:
                continue
            if original.deleted_at is not None:
                _refuse(f"{', '.join(n.invoice_no for n in notes)} correct {original.invoice_no} — delete or "
                        "void the notes first", status.HTTP_409_CONFLICT)
            _check_ceilings(session, original, notes)


def _check_ceilings(session: Session, original: Invoice, notes: list[Invoice]) -> None:
    credit_notes = [n for n in notes if n.invoice_kind == "credit_note"]
    debit_notes = [n for n in notes if n.invoice_kind == "debit_note"]
    for note in credit_notes:
        if billed(session, note) > CENT / 2:
            _refuse(f"credit note {note.invoice_no} would total {billed(session, note)} — a credit note "
                    "totals 0 or less")
    for note in debit_notes:
        if billed(session, note) < -CENT / 2:
            _refuse(f"debit note {note.invoice_no} would total {billed(session, note)} — a debit note "
                    "totals 0 or more")
    by_line: dict[str, dict[str, Decimal]] = {}
    note_kinds = {n.id: n.invoice_kind for n in notes}
    for item in session.scalars(select(InvoiceItem).where(
        InvoiceItem.invoice_id.in_(list(note_kinds)), InvoiceItem.deleted_at.is_(None),
        InvoiceItem.original_invoice_item_id.is_not(None),
    )):
        sums = by_line.setdefault(item.original_invoice_item_id, {"credit_note": Decimal(0), "debit_note": Decimal(0)})
        sums[note_kinds[item.invoice_id]] += line_amount(item)
    lines = {item.id: item for item in _live_items(session, original.id)}
    for line_id, sums in by_line.items():
        line = lines.get(line_id)
        if line is None:
            _refuse(f"a note corrects a line of {original.invoice_no} that no longer stands",
                    status.HTTP_409_CONFLICT)
        base = line_amount(line) + sums["debit_note"]
        after = base + sums["credit_note"]
        within = (Decimal(0) - CENT / 2 <= after <= base + CENT / 2) if base >= 0 \
            else (base - CENT / 2 <= after <= CENT / 2)
        if not within:
            _refuse(f"line {line.line_no or line.id} of {original.invoice_no} billed {base}; its credit notes "
                    f"would take it to {after} — a credit moves a line toward zero and never past it",
                    status.HTTP_409_CONFLICT)
    total = billed(session, original) + sum((billed(session, n) for n in debit_notes), Decimal(0))
    credited = sum((billed(session, n) for n in credit_notes), Decimal(0))
    if total + credited < -CENT / 2:
        _refuse(f"{original.invoice_no} and its debit notes billed {total}; its credit notes would give back "
                f"{-credited} — more than was billed", status.HTTP_409_CONFLICT)


@event.listens_for(Session, "after_rollback")
def _forget(session: Session) -> None:
    session.info.pop(_PENDING, None)
