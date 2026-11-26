"""The book's rules and its reads — plan docs/plans/accounting-core-2026-11-08.md.

What the server holds the book to, and nothing more: an entry balances, uses
accounts that take lines, names the party its accounts require, converts at
the rate it states, posts once per source fact and never into a closed month.
Which account a document posts to, when, and why is the workspace's posting
rule, read and applied by an agent.

Balances are derived from posted lines on every read and stored nowhere.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import event, func, inspect, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AccountingPeriod,
    AccountingSettings,
    BillingAccountEntry,
    BusinessObject,
    CostCenter,
    Customer,
    Employee,
    ExpenseClaim,
    FinAccountTrans,
    InventoryItemDetail,
    Invoice,
    InvoiceOffset,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    LedgerWaiver,
    Payment,
    PaymentApplication,
    Project,
    PurchaseOrder,
    SalesOrder,
    Shipment,
    Vendor,
)

ZERO = Decimal("0")
CENT = Decimal("0.01")

# what an entry may name as its source: a document or a ledger row elsewhere
SOURCE_MODELS: dict[str, type] = {
    "invoice": Invoice,
    "invoice_offset": InvoiceOffset,
    "payment": Payment,
    "payment_application": PaymentApplication,
    "expense_claim": ExpenseClaim,
    "sales_order": SalesOrder,
    "purchase_order": PurchaseOrder,
    "shipment": Shipment,
    "inventory_item_detail": InventoryItemDetail,
    "fin_account_transaction": FinAccountTrans,
    "billing_account_entry": BillingAccountEntry,
    "business_object": BusinessObject,
}

SUBLEDGER_COLUMNS = {"customer": "customer_id", "vendor": "vendor_id", "employee": "employee_id"}
PARTY_MODELS = {"customer_id": Customer, "vendor_id": Vendor, "employee_id": Employee}
# which side of zero an account type normally sits on (debits minus credits)
DEBIT_NATURED = frozenset({"asset", "expense"})


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT)


def refuse(code: int, detail: str):
    raise HTTPException(status_code=code, detail=detail)


def month_bounds(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    following = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, date.fromordinal(following.toordinal() - 1)


def functional_currency(db: Session, tenant_id: str) -> str:
    settings = db.scalar(select(AccountingSettings).where(AccountingSettings.tenant_id == tenant_id))
    if settings is None:
        refuse(status.HTTP_409_CONFLICT,
               "the books have no functional currency yet — PUT /accounting-settings first")
    return settings.functional_currency


def has_children(db: Session, account_id: str) -> bool:
    return db.scalar(select(LedgerAccount.id).where(LedgerAccount.parent_id == account_id).limit(1)) is not None


def has_lines(db: Session, account_id: str) -> bool:
    return db.scalar(
        select(JournalLine.id).join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalLine.ledger_account_id == account_id, JournalEntry.deleted_at.is_(None)).limit(1)
    ) is not None


def has_posted(db: Session, tenant_id: str) -> bool:
    return db.scalar(select(JournalEntry.id).where(
        JournalEntry.tenant_id == tenant_id, JournalEntry.status == "posted").limit(1)) is not None


# --- an entry's lines -------------------------------------------------------------


def check_lines(db: Session, tenant_id: str, lines) -> Decimal:
    """Every rule a set of lines is held to. Returns the entry's total."""
    debit = credit = ZERO
    for index, line in enumerate(lines):
        where = f"lines[{index}]"
        account = db.get(LedgerAccount, line.ledger_account_id)
        if account is None or account.tenant_id != tenant_id:
            refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{where}: ledger account {line.ledger_account_id} does not exist")
        if account.status != "active":
            refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{where}: account {account.account_code} is archived")
        if has_children(db, account.id):
            refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
                   f"{where}: account {account.account_code} has sub-accounts — post to one of them")
        if account.subledger and not getattr(line, SUBLEDGER_COLUMNS[account.subledger]):
            refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
                   f"{where}: account {account.account_code} keeps a {account.subledger} subledger — "
                   f"name the {account.subledger} ({SUBLEDGER_COLUMNS[account.subledger]})")
        for column, model in (*PARTY_MODELS.items(), ("cost_center_id", CostCenter), ("project_id", Project)):
            value = getattr(line, column)
            if value:
                row = db.get(model, value)
                if row is None or row.tenant_id != tenant_id:
                    refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{where}: {column} {value} does not exist")
        amount = money(line.debit) + money(line.credit)
        if account.currency and line.currency != account.currency:
            refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
                   f"{where}: account {account.account_code} is kept in {account.currency} — "
                   f"state the {account.currency} amount and the rate used")
        if line.currency is not None:
            converted = (Decimal(str(line.foreign_amount)) * Decimal(str(line.exchange_rate))).quantize(
                CENT, rounding=ROUND_HALF_UP)
            if abs(converted - amount) > CENT:
                refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
                       f"{where}: {line.foreign_amount} {line.currency} at {line.exchange_rate} is {converted}, "
                       f"not {amount}")
        debit += money(line.debit)
        credit += money(line.credit)
    if debit != credit:
        refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
               f"the entry does not balance: debits {debit}, credits {credit}")
    return debit


def check_source(db: Session, tenant_id: str, source_type: str | None, source_id: str | None) -> None:
    if source_type is None:
        return
    model = SOURCE_MODELS.get(source_type)
    if model is None:
        refuse(status.HTTP_422_UNPROCESSABLE_CONTENT,
               f"source_type {source_type!r} is not a source — one of {', '.join(sorted(SOURCE_MODELS))}")
    row = db.get(model, source_id)
    if row is None or row.tenant_id != tenant_id:
        refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{source_type} {source_id} does not exist")
    if getattr(row, "deleted_at", None) is not None:
        refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{source_type} {source_id} is deleted")


# --- the months ------------------------------------------------------------------


def lock_period(db: Session, tenant_id: str, day: date) -> AccountingPeriod:
    """The month `day` falls in, row-locked; created open if it has no row yet.
    Posting and closing both take this lock, so an entry cannot slip into a
    month in the instant it closes."""
    start, end = month_bounds(day)

    def locked():
        return db.scalar(select(AccountingPeriod).where(
            AccountingPeriod.tenant_id == tenant_id, AccountingPeriod.period_start == start,
        ).with_for_update().execution_options(populate_existing=True))

    period = locked()
    if period is None:
        try:
            with db.begin_nested():
                db.add(AccountingPeriod(tenant_id=tenant_id, period_start=start, period_end=end, status="open"))
        except IntegrityError:
            pass  # created by a concurrent writer; take its row
        period = locked()
    return period


def require_open(db: Session, tenant_id: str, day: date) -> None:
    period = lock_period(db, tenant_id, day)
    if period.status != "open":
        refuse(status.HTTP_409_CONFLICT,
               f"{period.period_start:%Y-%m} is closed — nothing posts into it. Post in an open month, "
               "or reopen it (POST /accounting-periods/reopen) with a reason")


def refuse_closed(db: Session, tenant_id: str, day: date) -> None:
    """A draft dated in a closed month could never post: closing refuses
    while one is there, so writing one there afterwards is refused too
    (review 2026-11-12, finding 6)."""
    start, _ = month_bounds(day)
    closed = db.scalar(select(AccountingPeriod.id).where(
        AccountingPeriod.tenant_id == tenant_id, AccountingPeriod.period_start == start,
        AccountingPeriod.status == "closed"))
    if closed is not None:
        refuse(status.HTTP_409_CONFLICT,
               f"{start:%Y-%m} is closed — an entry dated there could never post. Date it in an open month, "
               "or reopen it (POST /accounting-periods/reopen) with a reason")


def post(db: Session, entry: JournalEntry, actor_label: str) -> None:
    """Make a draft final: the month is open, the source still stands, and the
    source fact is not already in the book."""
    check_source(db, entry.tenant_id, entry.source_type, entry.source_id)
    require_open(db, entry.tenant_id, entry.posting_date)
    if entry.source_type is not None:
        lock_source(db, entry.source_type, entry.source_id)
        waiver = live_waiver(db, entry.tenant_id, entry.source_type, entry.source_id, entry.source_event)
        if waiver is not None:
            refuse(status.HTTP_409_CONFLICT, waived_fact(waiver))
        # A read, then a write: two posts of one fact at once both pass here.
        # `journal_entries_source_uk` is what refuses the second — this check
        # only gives the common case its sentence. Keep the index.
        clash = db.scalar(select(JournalEntry).where(
            JournalEntry.tenant_id == entry.tenant_id, JournalEntry.id != entry.id,
            JournalEntry.status == "posted", JournalEntry.reversed_at.is_(None),
            JournalEntry.source_type == entry.source_type, JournalEntry.source_id == entry.source_id,
            func.coalesce(JournalEntry.source_event, "") == (entry.source_event or ""),
        ))
        if clash is not None:
            refuse(status.HTTP_409_CONFLICT, duplicate_source(clash))
    entry.status = "posted"
    entry.posted_at = datetime.now(timezone.utc)
    entry.posted_by = actor_label


def lock_source(db: Session, source_type: str, source_id: str) -> None:
    """Row-lock the source document. Posting a fact and waiving it both take
    this lock, so the two cannot pass their checks at the same instant and
    leave a fact both in the book and waived."""
    model = SOURCE_MODELS[source_type]
    db.execute(select(model.id).where(model.id == source_id).with_for_update())


def live_waiver(db: Session, tenant_id: str, source_type: str, source_id: str,
                source_event: str | None) -> LedgerWaiver | None:
    """The live waiver that covers this fact: one for the whole document, or
    one for this event."""
    return db.scalar(select(LedgerWaiver).where(
        LedgerWaiver.tenant_id == tenant_id, LedgerWaiver.revoked_at.is_(None),
        LedgerWaiver.source_type == source_type, LedgerWaiver.source_id == source_id,
        or_(LedgerWaiver.source_event.is_(None),
            func.coalesce(LedgerWaiver.source_event, "") == (source_event or "")),
    ).limit(1))


def waived_fact(waiver: LedgerWaiver) -> str:
    what = f"{waiver.source_type} {waiver.source_id}" + (f" ({waiver.source_event})" if waiver.source_event else "")
    return (f"{what} is waived — {waiver.decided_by} decided it needs no entry: {waiver.reason!r}. "
            f"Revoke the waiver first (POST /ledger-waivers/{waiver.id}/revoke) to post it")


def recording_entry(db: Session, tenant_id: str, source_type: str, source_id: str,
                    source_event: str | None) -> JournalEntry | None:
    """A live posted entry for this fact; with no event, for any event of the
    document."""
    conditions = [JournalEntry.tenant_id == tenant_id, JournalEntry.status == "posted",
                  JournalEntry.reversed_at.is_(None), JournalEntry.deleted_at.is_(None),
                  JournalEntry.source_type == source_type, JournalEntry.source_id == source_id]
    if source_event is not None:
        conditions.append(func.coalesce(JournalEntry.source_event, "") == source_event)
    return db.scalar(select(JournalEntry).where(*conditions).order_by(JournalEntry.posting_date).limit(1))


_REVOCATION = frozenset({"revoked_at", "revoked_by", "revoke_reason", "updated_at"})


@event.listens_for(Session, "before_flush")
def _kept_waivers(session: Session, flush_context, instances) -> None:
    """A waiver is a decision on the record: never deleted, never edited.
    The only change it takes is its revocation, once."""
    for waiver in session.deleted:
        if isinstance(waiver, LedgerWaiver):
            refuse(status.HTTP_409_CONFLICT, "a waiver is kept — revoke it instead")
    for waiver in session.dirty:
        if not isinstance(waiver, LedgerWaiver):
            continue
        state = inspect(waiver)
        if any(attr.key not in _REVOCATION and attr.history.has_changes() for attr in state.attrs):
            refuse(status.HTTP_409_CONFLICT, "a waiver never changes — revoke it and record a new one")
        if state.attrs.revoked_at.history.deleted and state.attrs.revoked_at.history.deleted[0] is not None:
            refuse(status.HTTP_409_CONFLICT, "a revoked waiver stays revoked — record a new one")


def duplicate_source(existing: JournalEntry) -> str:
    event = f" ({existing.source_event})" if existing.source_event else ""
    return (f"{existing.source_type} {existing.source_id}{event} is already in the book as {existing.entry_no} — "
            "reverse that entry first to post it differently")


# --- reads ----------------------------------------------------------------------


@dataclass
class Movement:
    opening: Decimal = ZERO
    debit: Decimal = ZERO
    credit: Decimal = ZERO

    @property
    def closing(self) -> Decimal:
        return self.opening + self.debit - self.credit


def _posted_lines(tenant_id: str):
    return (
        select(JournalLine, JournalEntry.posting_date)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalLine.tenant_id == tenant_id, JournalEntry.status == "posted",
               JournalEntry.deleted_at.is_(None))
    )


def movements(db: Session, tenant_id: str, date_from: date | None, date_to: date) -> dict[str, Movement]:
    """Per account: what stood before `date_from`, and what moved up to `date_to`."""
    out: dict[str, Movement] = defaultdict(Movement)
    stmt = (
        select(JournalLine.ledger_account_id, JournalEntry.posting_date,
               func.sum(JournalLine.debit), func.sum(JournalLine.credit))
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalLine.tenant_id == tenant_id, JournalEntry.status == "posted",
               JournalEntry.deleted_at.is_(None), JournalEntry.posting_date <= date_to)
        .group_by(JournalLine.ledger_account_id, JournalEntry.posting_date)
    )
    for account_id, day, debit, credit in db.execute(stmt):
        row = out[account_id]
        if date_from is not None and day < date_from:
            row.opening += money(debit) - money(credit)
        else:
            row.debit += money(debit)
            row.credit += money(credit)
    return out


def descendants(accounts: list[LedgerAccount], root: str) -> set[str]:
    children: dict[str | None, list[str]] = defaultdict(list)
    for account in accounts:
        children[account.parent_id].append(account.id)
    found, stack = {root}, [root]
    while stack:
        for child in children[stack.pop()]:
            if child not in found:
                found.add(child)
                stack.append(child)
    return found


def trial_balance(db: Session, tenant_id: str, date_from: date | None, date_to: date) -> dict:
    accounts = list(db.scalars(select(LedgerAccount).where(LedgerAccount.tenant_id == tenant_id)
                               .order_by(LedgerAccount.account_code)))
    moved = movements(db, tenant_id, date_from, date_to)
    parents = {a.id: a.parent_id for a in accounts}
    rolled: dict[str, Movement] = defaultdict(Movement)
    for account_id, movement in moved.items():
        node = account_id
        while node is not None:
            total = rolled[node]
            total.opening += movement.opening
            total.debit += movement.debit
            total.credit += movement.credit
            node = parents.get(node)
    with_children = {a.parent_id for a in accounts if a.parent_id}
    rows = []
    for account in accounts:
        figures = rolled.get(account.id)
        if figures is None and account.status != "active":
            continue
        figures = figures or Movement()
        rows.append({
            "ledger_account_id": account.id, "account_code": account.account_code, "name": account.name,
            "account_type": account.account_type, "parent_id": account.parent_id,
            "summary": account.id in with_children,
            "opening": float(figures.opening), "debit": float(figures.debit), "credit": float(figures.credit),
            "closing": float(figures.closing),
            # the closing figure on the side the account normally sits on
            "natural_closing": float(figures.closing if account.account_type in DEBIT_NATURED else -figures.closing),
        })
    leaves = [m for account_id, m in moved.items() if account_id not in with_children]
    return {
        "date_from": date_from, "date_to": date_to, "rows": rows,
        "totals": {"debit": float(sum((m.debit for m in leaves), ZERO)),
                   "credit": float(sum((m.credit for m in leaves), ZERO))},
    }


def account_ledger(db: Session, account: LedgerAccount, date_from: date | None, date_to: date, *,
                   page: int = 1, size: int = 200) -> dict:
    """One account's lines, with its sub-accounts' when it is a summary, and a
    running balance."""
    accounts = list(db.scalars(select(LedgerAccount).where(LedgerAccount.tenant_id == account.tenant_id)))
    ids = descendants(accounts, account.id)
    # sums in SQL, one page of lines in Python: a busy bank account's whole
    # history no longer comes through the process (review 2026-11-12, finding 7)
    posted = (
        select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalLine.tenant_id == account.tenant_id, JournalLine.ledger_account_id.in_(ids),
               JournalEntry.status == "posted", JournalEntry.deleted_at.is_(None))
    )
    opening = money(db.scalar(posted.where(JournalEntry.posting_date < date_from))) if date_from else ZERO
    closing = money(db.scalar(posted.where(JournalEntry.posting_date <= date_to)))
    in_range = _posted_lines(account.tenant_id).where(JournalLine.ledger_account_id.in_(ids),
                                                      JournalEntry.posting_date <= date_to)
    if date_from is not None:
        in_range = in_range.where(JournalEntry.posting_date >= date_from)
    ordered = in_range.order_by(JournalEntry.posting_date, JournalEntry.entry_no, JournalLine.line_no, JournalLine.id)
    total = db.scalar(select(func.count()).select_from(in_range.subquery()))
    skipped = (page - 1) * size
    earlier = ordered.with_only_columns((JournalLine.debit - JournalLine.credit).label("delta")).limit(skipped)
    running = opening + money(db.scalar(select(func.coalesce(func.sum(earlier.subquery().c.delta), 0)))) \
        if skipped else opening
    out = []
    for line, day in db.execute(ordered.limit(size).offset(skipped)):
        running += money(line.debit) - money(line.credit)
        out.append({
            "posting_date": day, "entry_id": line.entry_id, "entry_no": line.entry.entry_no,
            "description": line.description or line.entry.description, "ledger_account_id": line.ledger_account_id,
            "debit": float(money(line.debit)), "credit": float(money(line.credit)), "balance": float(running),
            "customer_id": line.customer_id, "vendor_id": line.vendor_id, "employee_id": line.employee_id,
        })
    return {"ledger_account_id": account.id, "account_code": account.account_code, "date_from": date_from,
            "date_to": date_to, "opening": float(opening), "lines": out, "closing": float(closing),
            "total_lines": total, "page": page, "size": size}


def party_balances(db: Session, account: LedgerAccount, as_of: date) -> list[dict]:
    """A subledger account's balance per party."""
    column = getattr(JournalLine, SUBLEDGER_COLUMNS[account.subledger])
    stmt = (
        select(column, func.sum(JournalLine.debit), func.sum(JournalLine.credit))
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalLine.ledger_account_id == account.id, JournalEntry.status == "posted",
               JournalEntry.deleted_at.is_(None), JournalEntry.posting_date <= as_of)
        .group_by(column)
    )
    return [{SUBLEDGER_COLUMNS[account.subledger]: party, "debit": float(money(debit)),
             "credit": float(money(credit)), "balance": float(money(debit) - money(credit))}
            for party, debit, credit in db.execute(stmt) if money(debit) != money(credit)]
