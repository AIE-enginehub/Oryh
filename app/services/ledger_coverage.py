"""Ledger coverage — plan docs/plans/ledger-coverage-2026-11-24.md, phase 1.

Nothing posts to the book by itself: an agent posts each document by the
workspace's posting rule. This module answers the question that leaves
open — what happened this month that the book does not say, and what the
book says about documents that no longer count.

- **missing**: a document whose money counts in the period, which no
  posted, unreversed entry names (`source_type` + `source_id`, any
  `source_event`).
- **waived**: a counted document no entry names, which a live waiver says
  needs none — a person's decision, with their reason (phase 2). Never
  counted as missing.
- **stale**: a posted, unreversed entry dated in the period whose source was
  deleted or has left the states in which its money counts (an invoice
  voided, a payment voided).

Derived on every read and stored nowhere. Which documents must be posted,
and with which events, is the workspace's posting rule; the server only
finds and counts.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Callable

from fastapi import HTTPException, status
from sqlalchemy import Date, func, select
from sqlalchemy.orm import Session

from app.models import (
    AccountingPeriod,
    BillingAccount,
    BillingAccountEntry,
    Customer,
    Employee,
    ExpenseClaim,
    ExpenseItem,
    FinAccount,
    FinAccountTrans,
    Invoice,
    InvoiceOffset,
    JournalEntry,
    LedgerWaiver,
    Payment,
    PaymentApplication,
    Vendor,
)
from app.services.state_machines import counted_states


def _day(*columns):
    """The first of these that is set, as a date: the day a fact belongs to.
    `date()` rather than a CAST: SQLite casts a timestamp to a number."""
    days = [c if isinstance(c.type, Date) else func.date(c) for c in columns]
    return days[0] if len(days) == 1 else func.coalesce(*days)


@dataclass(frozen=True)
class Family:
    """One kind of document the book records: its table, the day each fact
    belongs to, what counts, and how it is shown."""

    model: type
    day: Callable[[], Any]
    # the condition under which its money counts (None: every live row)
    counted: Callable[[Session, str], Any] | None
    number: Callable[[Any], str | None]
    amount: Callable[[Session, Any], Decimal | None]
    currency: Callable[[Session, Any], str | None]
    # the column that splits the counts, when posting rules differ by it
    group: str | None = None
    # extra condition: rows of this table that are not facts of their own
    only: Callable[[], Any] | None = None


def _counted_status(model, family: str):
    def condition(db: Session, tenant_id: str):
        return model.status.in_(counted_states(db, tenant_id, family))
    return condition


def _claim_amount(db: Session, claim: ExpenseClaim) -> Decimal:
    total = db.scalar(select(func.coalesce(func.sum(ExpenseItem.amount), 0)).where(
        ExpenseItem.claim_id == claim.id, ExpenseItem.deleted_at.is_(None)))
    return Decimal(str(total or 0))


def _money(value) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


FAMILIES: dict[str, Family] = {
    "invoice": Family(
        Invoice, lambda: _day(Invoice.invoice_date, Invoice.issued_at, Invoice.created_at),
        _counted_status(Invoice, "invoice"),
        number=lambda r: r.invoice_no, amount=lambda db, r: _money(r.total_amount),
        currency=lambda db, r: r.currency, group="direction",
    ),
    "payment": Family(
        Payment, lambda: _day(Payment.payment_date, Payment.paid_at, Payment.created_at),
        _counted_status(Payment, "payment"),
        number=lambda r: r.payment_no, amount=lambda db, r: _money(r.amount),
        currency=lambda db, r: r.currency, group="direction",
    ),
    "expense_claim": Family(
        ExpenseClaim, lambda: _day(ExpenseClaim.claim_date, ExpenseClaim.submitted_at, ExpenseClaim.created_at),
        _counted_status(ExpenseClaim, "expense_claim"),
        number=lambda r: r.title, amount=_claim_amount, currency=lambda db, r: r.currency,
    ),
    # a statement line matched to a payment is that payment's money, which
    # the payment's own entry records; the unmatched ones — fees, interest —
    # are facts of their own
    "fin_account_transaction": Family(
        FinAccountTrans, lambda: _day(FinAccountTrans.trans_date, FinAccountTrans.created_at), None,
        number=lambda r: r.reference_no, amount=lambda db, r: _money(r.amount),
        currency=lambda db, r: db.scalar(select(FinAccount.currency).where(FinAccount.id == r.fin_account_id)),
        only=lambda: FinAccountTrans.payment_id.is_(None),
    ),
    # on request only (§4.1 as built): most workspaces post settlement per
    # payment and offsets on one receivable account post nothing
    "payment_application": Family(
        PaymentApplication, lambda: _day(PaymentApplication.applied_at), None,
        number=lambda r: None, amount=lambda db, r: _money(r.amount_applied),
        currency=lambda db, r: db.scalar(select(Payment.currency).where(Payment.id == r.payment_id)),
    ),
    "invoice_offset": Family(
        InvoiceOffset, lambda: _day(InvoiceOffset.created_at), None,
        number=lambda r: None, amount=lambda db, r: _money(r.amount),
        currency=lambda db, r: db.scalar(select(Invoice.currency).where(Invoice.id == r.invoice_id)),
    ),
    "billing_account_entry": Family(
        BillingAccountEntry, lambda: _day(BillingAccountEntry.effective_at), None,
        number=lambda r: r.reason, amount=lambda db, r: _money(r.amount),
        currency=lambda db, r: db.scalar(select(BillingAccount.unit).where(BillingAccount.id == r.billing_account_id)),
        only=lambda: BillingAccountEntry.billing_account_id.in_(
            select(BillingAccount.id).where(BillingAccount.unit_type == "currency")),
    ),
}
DEFAULT_FAMILIES = ("invoice", "payment", "expense_claim", "fin_account_transaction")


def month_of(day: date) -> tuple[date, date]:
    first = day.replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def parse_families(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_FAMILIES
    names = tuple(dict.fromkeys(name.strip() for name in value.split(",") if name.strip()))
    unknown = [name for name in names if name not in FAMILIES]
    if unknown:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"families: {', '.join(unknown)} — one of {', '.join(FAMILIES)}")
    return names


def _live(model):
    return model.deleted_at.is_(None) if hasattr(model, "deleted_at") else None


def _party(db: Session, row) -> dict | None:
    for column, model, field in (("customer_id", Customer, "name"), ("vendor_id", Vendor, "name"),
                                 ("payee_employee_id", Employee, "name"), ("employee_id", Employee, "name")):
        value = getattr(row, column, None)
        if value:
            name = db.scalar(select(getattr(model, field)).where(model.id == value))
            return {column: value, "name": name}
    return None


def _recorded(db: Session, tenant_id: str, family: str, ids: list[str]) -> dict[str, list[str]]:
    """The events found in the book for each of these documents."""
    found: dict[str, list[str]] = defaultdict(list)
    for chunk in (ids[i:i + 500] for i in range(0, len(ids), 500)):
        for source_id, event in db.execute(
            select(JournalEntry.source_id, JournalEntry.source_event).where(
                JournalEntry.tenant_id == tenant_id, JournalEntry.source_type == family,
                JournalEntry.source_id.in_(chunk), JournalEntry.status == "posted",
                JournalEntry.reversed_at.is_(None), JournalEntry.deleted_at.is_(None))
        ):
            found[str(source_id)].append(event or "")
    return found


def _waived(db: Session, tenant_id: str, family: str, ids: list[str]) -> dict[str, LedgerWaiver]:
    """The live waiver naming each of these documents — for the whole
    document or one event of it."""
    found: dict[str, LedgerWaiver] = {}
    for chunk in (ids[i:i + 500] for i in range(0, len(ids), 500)):
        for waiver in db.scalars(select(LedgerWaiver).where(
            LedgerWaiver.tenant_id == tenant_id, LedgerWaiver.source_type == family,
            LedgerWaiver.source_id.in_(chunk), LedgerWaiver.revoked_at.is_(None),
        ).order_by(LedgerWaiver.source_event.is_not(None), LedgerWaiver.created_at)):
            found.setdefault(str(waiver.source_id), waiver)
    return found


def coverage(db: Session, tenant_id: str, period: date, families: tuple[str, ...]) -> dict:
    start, end = month_of(period)
    closed = db.scalar(select(AccountingPeriod.status).where(
        AccountingPeriod.tenant_id == tenant_id, AccountingPeriod.period_start == start))
    summary: dict[str, dict] = {}
    missing: list[dict] = []
    waived: list[dict] = []
    for name in families:
        spec = FAMILIES[name]
        model = spec.model
        day = spec.day()
        conditions = [model.tenant_id == tenant_id, day >= start, day <= end]
        for extra in (_live(model), spec.counted(db, tenant_id) if spec.counted else None,
                      spec.only() if spec.only else None):
            if extra is not None:
                conditions.append(extra)
        rows = db.execute(select(model, day.label("fact_day")).where(*conditions)).all()
        ids = [str(row.id) for row, _ in rows]
        recorded = _recorded(db, tenant_id, name, ids)
        waivers = _waived(db, tenant_id, name, ids)
        counts: dict[str, Any] = {"counted": 0, "recorded": 0, "waived": 0, "missing": 0}
        groups: dict[str, dict[str, int]] = defaultdict(
            lambda: {"counted": 0, "recorded": 0, "waived": 0, "missing": 0})
        for row, fact_day in rows:
            # a document posted for one event and waived for another is in
            # the book: recorded wins
            key = "recorded" if str(row.id) in recorded else "waived" if str(row.id) in waivers else "missing"
            counts["counted"] += 1
            counts[key] += 1
            if spec.group:
                bucket = groups[getattr(row, spec.group)]
                bucket["counted"] += 1
                bucket[key] += 1
            if key == "recorded":
                continue
            amount = spec.amount(db, row)
            entry = {"family": name, "id": str(row.id), "number": spec.number(row),
                     "day": fact_day if isinstance(fact_day, date) else date.fromisoformat(str(fact_day)[:10]),
                     "amount": float(amount) if amount is not None else None,
                     "currency": spec.currency(db, row), "party": _party(db, row)}
            if spec.group:
                entry[spec.group] = getattr(row, spec.group)
            if name == "invoice":
                entry["kind"] = row.invoice_kind
            if key == "waived":
                waiver = waivers[str(row.id)]
                entry.update(waiver_id=waiver.id, source_event=waiver.source_event, reason=waiver.reason,
                             decided_by=waiver.decided_by)
                waived.append(entry)
            else:
                missing.append(entry)
        if spec.group:
            counts[f"by_{spec.group}"] = dict(groups)
        summary[name] = counts
    stale = _stale(db, tenant_id, start, end, families)
    for listed in (missing, waived):
        listed.sort(key=lambda m: (m["day"], m["family"], m["number"] or ""))
    return {"period": start, "period_end": end, "period_status": closed or "open", "families": summary,
            "missing": missing, "stale": stale, "waived": waived}


def _stale(db: Session, tenant_id: str, start: date, end: date, families: tuple[str, ...]) -> list[dict]:
    """Live posted entries dated in the period whose source no longer
    counts: deleted, voided, cancelled."""
    out = []
    entries = db.scalars(select(JournalEntry).where(
        JournalEntry.tenant_id == tenant_id, JournalEntry.status == "posted",
        JournalEntry.reversed_at.is_(None), JournalEntry.deleted_at.is_(None),
        JournalEntry.posting_date >= start, JournalEntry.posting_date <= end,
        JournalEntry.source_type.in_(families),
    ).order_by(JournalEntry.posting_date, JournalEntry.entry_no)).all()
    counted_by_family: dict[str, frozenset[str]] = {}
    for entry in entries:
        spec = FAMILIES[entry.source_type]
        row = db.get(spec.model, entry.source_id)
        why = None
        if row is None:
            why = f"the {entry.source_type.replace('_', ' ')} no longer exists"
        elif getattr(row, "deleted_at", None) is not None:
            why = f"the {entry.source_type.replace('_', ' ')} was deleted"
        elif spec.counted is not None:
            if entry.source_type not in counted_by_family:
                machine_family = {"invoice": "invoice", "payment": "payment", "expense_claim": "expense_claim"}
                counted_by_family[entry.source_type] = counted_states(db, tenant_id, machine_family[entry.source_type])
            if row.status not in counted_by_family[entry.source_type]:
                why = f"the {entry.source_type.replace('_', ' ')} is {row.status}"
        if why:
            out.append({"entry_id": entry.id, "entry_no": entry.entry_no, "posting_date": entry.posting_date,
                        "source_type": entry.source_type, "source_id": entry.source_id,
                        "source_event": entry.source_event, "number": spec.number(row) if row is not None else None,
                        "why": why})
    return out
