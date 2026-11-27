"""The book — plan docs/plans/accounting-core-2026-11-08.md, phase 1.

The chart of accounts, journal entries and accounting periods. The rules the
server holds the book to live in `app/services/ledger.py`; this module is the
doors. Every read needs `ledger.read` (the book shows payroll totals and
margins, so belonging to the workspace is not enough); posting needs
`ledger.post`, the chart and settings `ledger.manage`, closing a month
`period.close`. Waivers — a document the book needs no entry for — are
recorded and revoked with `ledger.post`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.common import (
    ListFilters,
    ORDER_BY_DOC,
    PAGE_SIZE_DOC,
    envelope,
    get_scoped_or_404,
    list_filters,
    list_rows,
    requested_pagination,
)
from app.api.common.numbering import allocate_document_number
from app.api.deps import Actor, get_actor, require_permission
from app.core.business_date import business_today
from app.db.session import get_db
from app.models import (
    AccountingPeriod,
    AccountingSettings,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    LedgerWaiver,
    StatementLayout,
    StatementLayoutRow,
)
from app.schemas import (
    AccountingPeriodEnvelope,
    AccountingPeriodListEnvelope,
    AccountingPeriodRead,
    AccountingSettingsEnvelope,
    AccountingSettingsRead,
    AccountingSettingsRequest,
    CreateJournalEntryRequest,
    CreateLedgerAccountRequest,
    CreateLedgerWaiverRequest,
    CreateStatementLayoutRequest,
    JournalEntryEnvelope,
    JournalEntryListEnvelope,
    JournalEntryRead,
    JournalLineRead,
    LedgerAccountEnvelope,
    LedgerAccountListEnvelope,
    LedgerAccountRead,
    LedgerWaiverEnvelope,
    LedgerWaiverListEnvelope,
    LedgerWaiverRead,
    PeriodActionRequest,
    ReplaceStatementLayoutRowsRequest,
    ReverseJournalEntryRequest,
    RevokeLedgerWaiverRequest,
    UpdateJournalEntryRequest,
    StatementLayoutEnvelope,
    StatementLayoutListEnvelope,
    StatementLayoutRead,
    UpdateLedgerAccountRequest,
    UpdateStatementLayoutRequest,
)
from app.services import ledger as book
from app.services import financial_statements as statements
from app.services import ledger_coverage as coverage
from app.services import statement_layouts as layouts
from app.services.audit import record_audit

router = APIRouter()

_422 = status.HTTP_422_UNPROCESSABLE_CONTENT
_409 = status.HTTP_409_CONFLICT


def _read(actor: Actor) -> None:
    require_permission(actor, "ledger.read")


# --- settings ---------------------------------------------------------------------


@router.get("/accounting-settings", response_model=AccountingSettingsEnvelope, response_model_exclude_unset=True)
def get_accounting_settings(actor: Annotated[Actor, Depends(get_actor)], db: Annotated[Session, Depends(get_db)]):
    """The functional currency; `data` is null until it is set."""
    _read(actor)
    row = db.scalar(select(AccountingSettings).where(AccountingSettings.tenant_id == actor.tenant_id))
    return envelope(AccountingSettingsRead.model_validate(row).model_dump(by_alias=True) if row else None)


@router.put("/accounting-settings", response_model=AccountingSettingsEnvelope, response_model_exclude_unset=True)
def put_accounting_settings(
    payload: AccountingSettingsRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Set the currency the books are kept in. It cannot change once anything
    has posted: every amount in the book is in it. `fiscal_year_start_month`
    (1-12, default 1) only resolves `year_start` in the statement reads."""
    require_permission(actor, "ledger.manage")
    tenant_id = actor.tenant_id
    currency = payload.functional_currency.upper()
    row = db.scalar(select(AccountingSettings).where(AccountingSettings.tenant_id == tenant_id))
    if row is not None and row.functional_currency != currency and book.has_posted(db, tenant_id):
        book.refuse(_409, f"the book is kept in {row.functional_currency} and entries have posted in it — "
                          "the functional currency no longer changes")
    if payload.retained_earnings_account_id:
        account = get_scoped_or_404(db, LedgerAccount, tenant_id, payload.retained_earnings_account_id)
        if account.account_type != "equity":
            book.refuse(_422, f"account {account.account_code} is {account.account_type}; retained earnings is equity")
    if row is None:
        row = AccountingSettings(tenant_id=tenant_id, functional_currency=currency, fiscal_year_start_month=1)
        db.add(row)
    row.functional_currency = currency
    row.retained_earnings_account_id = payload.retained_earnings_account_id
    if payload.fiscal_year_start_month is not None:
        row.fiscal_year_start_month = payload.fiscal_year_start_month
    record_audit(db, tenant_id=tenant_id, action="ledger.settings_changed", entity_type="accounting_settings",
                 entity_id=tenant_id, actor=actor.label,
                 detail={"functional_currency": currency, "fiscal_year_start_month": row.fiscal_year_start_month})
    db.commit()
    db.refresh(row)
    return envelope(AccountingSettingsRead.model_validate(row).model_dump(by_alias=True))


# --- the chart --------------------------------------------------------------------


def _account_read(db: Session, account: LedgerAccount) -> dict:
    data = LedgerAccountRead.model_validate(account).model_dump(by_alias=True)
    data["summary"] = book.has_children(db, account.id)
    return data


def _check_parent(db: Session, tenant_id: str, parent_id: str | None, account_type: str,
                  current: LedgerAccount | None = None) -> None:
    """A parent of the same type, not the account itself or one under it,
    and not one that already carries lines — it would become a summary with
    postings of its own."""
    if not parent_id:
        return
    parent = get_scoped_or_404(db, LedgerAccount, tenant_id, parent_id)
    if parent.account_type != account_type:
        book.refuse(_422, f"account {parent.account_code} is {parent.account_type}; a sub-account shares its type")
    node = parent
    while current is not None and node is not None:
        if node.id == current.id:
            book.refuse(_422, "an account cannot sit under itself or under one of its own")
        node = db.get(LedgerAccount, node.parent_id) if node.parent_id else None
    if book.has_lines(db, parent.id):
        book.refuse(_409, f"account {parent.account_code} already carries lines — a summary account takes none. "
                          "Open the sub-account beside it instead")


def _check_cash(is_cash: bool | None, account_type: str) -> None:
    if is_cash and account_type != "asset":
        book.refuse(_422, f"is_cash: a {account_type} account holds no cash — only an asset account (bank, cash "
                          "on hand) is a cash account")


@router.post("/ledger-accounts", response_model=LedgerAccountEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_ledger_account(
    payload: CreateLedgerAccountRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "ledger.manage")
    tenant_id = actor.tenant_id
    _check_parent(db, tenant_id, payload.parent_id, payload.account_type)
    _check_cash(payload.is_cash, payload.account_type)
    account = LedgerAccount(
        tenant_id=tenant_id, account_code=payload.account_code.strip(), name=payload.name,
        account_type=payload.account_type, parent_id=payload.parent_id, subledger=payload.subledger,
        currency=payload.currency.upper() if payload.currency else None, status=payload.status,
        description=payload.description, is_cash=payload.is_cash,
    )
    db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        book.refuse(_409, f"account_code {payload.account_code!r} already exists")
    record_audit(db, tenant_id=tenant_id, action="ledger.account_created", entity_type="ledger_account",
                 entity_id=account.id, actor=actor.label,
                 detail={"account_code": account.account_code, "account_type": account.account_type,
                         "is_cash": account.is_cash})
    db.commit()
    db.refresh(account)
    return envelope(_account_read(db, account))


IDENTITY_FIELDS = ("account_code", "account_type", "subledger", "currency")


@router.patch("/ledger-accounts/{account_id}", response_model=LedgerAccountEnvelope,
              response_model_exclude_unset=True)
def update_ledger_account(
    account_id: str,
    payload: UpdateLedgerAccountRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Rename, describe, move in the tree, archive. What an account IS — its
    code, type, subledger and currency — is fixed once it carries lines:
    every figure already posted means it."""
    require_permission(actor, "ledger.manage")
    tenant_id = actor.tenant_id
    account = get_scoped_or_404(db, LedgerAccount, tenant_id, account_id)
    updates = payload.model_dump(exclude_unset=True)
    changing = sorted(f for f in IDENTITY_FIELDS if f in updates and updates[f] != getattr(account, f))
    if changing and book.has_lines(db, account.id):
        book.refuse(_409, f"account {account.account_code} carries lines — {', '.join(changing)} no longer change. "
                          "Archive it and open a new one")
    if "account_type" in updates and book.has_children(db, account.id):
        book.refuse(_409, f"account {account.account_code} has sub-accounts of its type")
    if "parent_id" in updates:
        _check_parent(db, tenant_id, updates["parent_id"], updates.get("account_type") or account.account_type,
                      current=account)
    if updates.get("currency"):
        updates["currency"] = updates["currency"].upper()
    if updates.get("is_cash", False) is None:
        updates.pop("is_cash")
    _check_cash(updates.get("is_cash", account.is_cash), updates.get("account_type") or account.account_type)
    for field, value in updates.items():
        setattr(account, field, value)
    record_audit(db, tenant_id=tenant_id, action="ledger.account_changed", entity_type="ledger_account",
                 entity_id=account.id, actor=actor.label,
                 detail={"account_code": account.account_code, "fields": sorted(updates)})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        book.refuse(_409, f"account_code {updates.get('account_code')!r} already exists")
    db.refresh(account)
    return envelope(_account_read(db, account))


@router.get("/ledger-accounts", response_model=LedgerAccountListEnvelope, response_model_exclude_unset=True)
def list_ledger_accounts(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    account_type: str | None = None,
    parent_id: str | None = None,
    subledger: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    is_cash: Annotated[bool | None, Query(description="true: the cash accounts the cash summary follows")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(LedgerAccount, ranges=('created_at',), equals=('currency',)))] = None,
):
    """The chart, in code order."""
    _read(actor)
    parents = set(db.scalars(select(LedgerAccount.parent_id).where(
        LedgerAccount.tenant_id == actor.tenant_id, LedgerAccount.parent_id.is_not(None))))

    def render(rows):
        return [{**LedgerAccountRead.model_validate(r).model_dump(by_alias=True), "summary": r.id in parents}
                for r in rows]

    stmt = select(LedgerAccount).where(LedgerAccount.tenant_id == actor.tenant_id)
    if is_cash is not None:
        stmt = stmt.where(LedgerAccount.is_cash.is_(is_cash))
    return list_rows(
        db, stmt,
        filters={LedgerAccount.account_type: account_type, LedgerAccount.parent_id: parent_id,
                 LedgerAccount.subledger: subledger, LedgerAccount.status: status_filter},
        keyword=keyword,
        keyword_columns=(cast(LedgerAccount.id, String), LedgerAccount.account_code, LedgerAccount.name),
        order_by=(LedgerAccount.account_code.asc(), LedgerAccount.id.asc()),
        pagination=requested_pagination(page, size, default=200),
        sort=order_by, extra=extra, render=render,
    )


@router.get("/ledger-accounts/{account_id}", response_model=LedgerAccountEnvelope, response_model_exclude_unset=True)
def get_ledger_account(account_id: str, actor: Annotated[Actor, Depends(get_actor)],
                       db: Annotated[Session, Depends(get_db)]):
    _read(actor)
    return envelope(_account_read(db, get_scoped_or_404(db, LedgerAccount, actor.tenant_id, account_id)))


def _span(date_from: date | None, date_to: date | None) -> tuple[date | None, date]:
    date_to = date_to or business_today()
    if date_from is not None and date_from > date_to:
        book.refuse(_422, "date_from is after date_to")
    return date_from, date_to


@router.get("/ledger-accounts/{account_id}/ledger")
def get_account_ledger(
    account_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    date_from: date | None = None,
    date_to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    """The account's posted lines between the two dates (a summary account's
    include its sub-accounts'), with the balance before them, a running
    balance (debits minus credits) and the balance after. Lines come a page
    at a time (`page`, `size`, `total_lines`); the running balance carries
    across pages."""
    _read(actor)
    account = get_scoped_or_404(db, LedgerAccount, actor.tenant_id, account_id)
    return envelope(book.account_ledger(db, account, *_span(date_from, date_to), page=page, size=size))


@router.get("/ledger-accounts/{account_id}/parties")
def get_account_parties(
    account_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    as_of: date | None = None,
):
    """A subledger account's balance per party, as of a day: who owes what
    on receivables, whom we owe on payables. Parties at zero are left out."""
    _read(actor)
    account = get_scoped_or_404(db, LedgerAccount, actor.tenant_id, account_id)
    if not account.subledger:
        book.refuse(_422, f"account {account.account_code} keeps no subledger")
    return envelope(book.party_balances(db, account, as_of or business_today()))


@router.get("/trial-balance")
def get_trial_balance(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    date_from: date | None = None,
    date_to: date | None = None,
):
    """Every account: the balance before `date_from`, debits and credits up to
    `date_to`, and the closing balance (debits minus credits; `natural_closing`
    on the side the account normally sits). Summary accounts carry their
    sub-accounts' totals. With no `date_from`, everything up to `date_to` is
    movement and nothing is opening."""
    _read(actor)
    return envelope(book.trial_balance(db, actor.tenant_id, *_span(date_from, date_to)))


@router.get("/ledger-coverage")
def get_ledger_coverage(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    period: Annotated[date, Query(description="any day of the month to read")],
    families: Annotated[str | None, Query(description=(
        "comma-separated; default invoice,payment,expense_claim,fin_account_transaction. Also "
        "payment_application, invoice_offset, billing_account_entry"))] = None,
):
    """What happened in the month that the book does not say, and what the
    book says about documents that no longer count (plan
    docs/plans/ledger-coverage-2026-11-24.md). Per family: how many documents
    counted, how many a posted, unreversed entry names (any event), how many
    a live waiver covers, how many are missing. `missing` lists those, with
    number, day, amount and party; `waived` lists the waived ones with the
    reason and who decided; `stale` lists the live entries dated in the month whose source was
    deleted, voided or cancelled. Which documents must be posted is the
    workspace's posting rule — the server only finds and counts."""
    _read(actor)
    return envelope(coverage.coverage(db, actor.tenant_id, period, coverage.parse_families(families)))


# --- statements (plan docs/plans/financial-statements-2026-11-25.md) ---------------


@router.get("/income-statement")
def get_income_statement(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    date_from: Annotated[str | None, Query(description=(
        "YYYY-MM-DD, or year_start for the start of the financial year date_to falls in; "
        "default: the first of date_to's month, or of this month"))] = None,
    date_to: Annotated[date | None, Query(description="default: the end of date_from's month, or of this month")] = None,
    compare: Annotated[str | None, Query(description="previous_period (default), previous_year or none")] = None,
    by: Annotated[str | None, Query(description=(
        "split every figure by one of project, cost_center, customer, vendor, employee, month; lines "
        "without it fall under `unassigned`"))] = None,
    layout_id: Annotated[str | None, Query(description=(
        "a statement layout to apply; default: the workspace's default layout for this statement, if any; "
        "`none` for the default statement only"))] = None,
):
    """Income and expenses for a span of days, on their natural side, rolled
    up the chart's tree, and the result (income − expenses) — every figure a
    sum of posted lines. `compare` adds the span before (whole months shift
    by months) or the same dates a year earlier, with the change. Carries
    what makes the figures provisional: `period_status.open_months`, `drafts`
    (draft entries in the span, left out) and the coverage read's `missing`
    and `stale` counts per month. With a layout, `layout.lines` are its rows
    applied to the same sums, `layout.unplaced` the accounts with movement no
    row takes; `result` is always the book's whole result."""
    _read(actor)
    start, end = statements.resolve_span(db, actor.tenant_id, date_from, date_to, business_today())
    compare_value, by_value = statements.parse_compare(compare), statements.parse_by(by)
    layout = layouts.for_read(db, actor.tenant_id, "income_statement", layout_id)
    return envelope(statements.income_statement(db, actor.tenant_id, start, end, compare_value, by_value, layout))


@router.get("/balance-sheet")
def get_balance_sheet(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    as_of: Annotated[date | None, Query(description="default: today")] = None,
    compare: Annotated[str | None, Query(description=(
        "previous_period (default: the end of the month before), previous_year or none"))] = None,
    layout_id: Annotated[str | None, Query(description=(
        "a statement layout to apply; default: the workspace's default layout for this statement, if any; "
        "`none` for the default statement only"))] = None,
):
    """Assets, liabilities and equity at a day, on their natural side, rolled
    up the chart's tree. Equity includes **earnings not yet closed** — every
    income and expense balance to the day — so the sheet is right whether or
    not a year-end closing entry has been posted. `balanced` states assets =
    liabilities + equity; for a book of balanced entries it always holds, and
    `false` is an integrity defect. Carries the open status, drafts and
    coverage counts of `as_of`'s month. With a layout, `layout.lines` are its
    rows (earnings not yet closed is placed by an `earnings_not_yet_closed`
    reference), `layout.unplaced` what no row takes; `totals` and `balanced`
    are always the book's whole."""
    _read(actor)
    compare_value = statements.parse_compare(compare)
    layout = layouts.for_read(db, actor.tenant_id, "balance_sheet", layout_id)
    return envelope(statements.balance_sheet(db, actor.tenant_id, as_of or business_today(), compare_value, layout))


@router.get("/cash-summary")
def get_cash_summary(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    date_from: Annotated[str | None, Query(description=(
        "YYYY-MM-DD, or year_start; default: the first of date_to's month, or of this month"))] = None,
    date_to: Annotated[date | None, Query(description="default: the end of date_from's month, or of this month")] = None,
    compare: Annotated[str | None, Query(description="previous_period (default), previous_year or none")] = None,
    layout_id: Annotated[str | None, Query(description=(
        "a cash_summary layout to apply (its operating, investing and financing lines); default: the "
        "workspace's default, if any; `none` for without"))] = None,
):
    """Money into and out of the cash accounts (`is_cash` on the ledger
    account, set by the person) for a span of days: each cash account's
    opening, closing and change, and `sections[]` by the type of the account
    on the other side of each entry — received, paid and net per account.
    Each entry's cash is attributed to its other lines by their own amounts,
    stated in `basis`; an entry touching only cash accounts is a transfer and
    moves nothing in or out. `reconciled` states opening + net change =
    closing. A direct-method view from the book, not a statutory cash flow
    statement. Carries the open months, drafts and coverage counts like the
    other statements."""
    _read(actor)
    start, end = statements.resolve_span(db, actor.tenant_id, date_from, date_to, business_today())
    compare_value = statements.parse_compare(compare)
    layout = layouts.for_read(db, actor.tenant_id, "cash_summary", layout_id)
    return envelope(statements.cash_summary(db, actor.tenant_id, start, end, compare_value, layout))


# --- statement layouts -------------------------------------------------------------


def _layout_read(layout: StatementLayout) -> dict:
    return StatementLayoutRead.model_validate(layout).model_dump(by_alias=True)


def _row_dicts(rows) -> list[dict]:
    return [{"row_no": r.row_no, "code": r.code, "label": r.label, "kind": r.kind,
             "accounts": [ref.model_dump(exclude_none=True) for ref in r.accounts] if r.accounts is not None else None,
             "sign": r.sign,
             "formula": [term.model_dump() for term in r.formula] if r.formula is not None else None}
            for r in sorted(rows, key=lambda r: r.row_no)]


def _stored_rows(layout: StatementLayout) -> list[dict]:
    return [{"row_no": r.row_no, "code": r.code, "label": r.label, "kind": r.kind, "accounts": r.accounts,
             "sign": r.sign, "formula": r.formula} for r in layout.rows]


def _take_default(db: Session, layout: StatementLayout) -> None:
    """Make `layout` its statement's default: the previous one stops being it."""
    for other in db.scalars(select(StatementLayout).where(
            StatementLayout.tenant_id == layout.tenant_id, StatementLayout.statement == layout.statement,
            StatementLayout.is_default.is_(True), StatementLayout.id != layout.id).with_for_update()):
        other.is_default = False
    db.flush()
    layout.is_default = True


def _commit_layout(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        book.refuse(_409, "another layout became this statement's default at the same time — read /statement-layouts")


@router.get("/statement-layouts", response_model=StatementLayoutListEnvelope, response_model_exclude_unset=True)
def list_statement_layouts(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    statement: Annotated[str | None, Query(description="income_statement or balance_sheet")] = None,
    status_filter: Annotated[str | None, Query(alias="status", description="active or archived")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(StatementLayout, ranges=('created_at', 'updated_at')))] = None,
):
    """The workspace's statement formats, each with its rows."""
    _read(actor)
    stmt = (select(StatementLayout).where(StatementLayout.tenant_id == actor.tenant_id)
            .options(selectinload(StatementLayout.rows)))
    return list_rows(
        db, stmt, filters={StatementLayout.statement: statement, StatementLayout.status: status_filter},
        order_by=(StatementLayout.statement, StatementLayout.name),
        pagination=requested_pagination(page, size), sort=order_by, extra=extra,
        render=lambda rows: [_layout_read(row) for row in rows],
    )


@router.get("/statement-layouts/{layout_id}", response_model=StatementLayoutEnvelope,
            response_model_exclude_unset=True)
def get_statement_layout(layout_id: str, actor: Annotated[Actor, Depends(get_actor)],
                         db: Annotated[Session, Depends(get_db)]):
    _read(actor)
    return envelope(_layout_read(get_scoped_or_404(db, StatementLayout, actor.tenant_id, layout_id)))


@router.post("/statement-layouts", response_model=StatementLayoutEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_statement_layout(
    payload: CreateStatementLayoutRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Keep a statement format: ordered rows, each summing accounts (by id,
    with sub-accounts, or by code range) or other rows (`formula`), or a
    heading. Refused with 422 naming the row when a formula names a code not
    here or goes in a circle, when an account is of a type the statement does
    not take, or when an account would feed two rows. Which account belongs
    on which line is the person's decision: `confirmed_by` names them."""
    require_permission(actor, "ledger.manage")
    confirmed_by = payload.confirmed_by.strip()
    if not confirmed_by:
        book.refuse(_422, "confirmed_by: name the person who accepted this layout")
    layouts.check(db, actor.tenant_id, payload.statement, payload.rows)
    layout = StatementLayout(tenant_id=actor.tenant_id, statement=payload.statement, name=payload.name.strip(),
                             is_default=False, status="active", confirmed_by=confirmed_by, created_by=actor.label)
    db.add(layout)
    db.flush()
    for row in _row_dicts(payload.rows):
        layout.rows.append(StatementLayoutRow(tenant_id=actor.tenant_id, **row))
    if payload.is_default:
        _take_default(db, layout)
    db.flush()
    record_audit(db, tenant_id=actor.tenant_id, action="ledger.layout_created", entity_type="statement_layout",
                 entity_id=layout.id, actor=actor.label,
                 detail={"statement": layout.statement, "name": layout.name, "is_default": layout.is_default,
                         "confirmed_by": confirmed_by, "rows": _stored_rows(layout)})
    _commit_layout(db)
    db.refresh(layout)
    return envelope(_layout_read(layout))


@router.patch("/statement-layouts/{layout_id}", response_model=StatementLayoutEnvelope,
              response_model_exclude_unset=True)
def update_statement_layout(
    layout_id: str,
    payload: UpdateStatementLayoutRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Rename a layout, make it its statement's default (the previous default
    stops being it), or archive it (an archived layout is no one's default;
    it stays readable by id)."""
    require_permission(actor, "ledger.manage")
    layout = get_scoped_or_404(db, StatementLayout, actor.tenant_id, layout_id)
    before = {"name": layout.name, "is_default": layout.is_default, "status": layout.status}
    if payload.name is not None:
        layout.name = payload.name.strip()
    if payload.status is not None:
        layout.status = payload.status
    if payload.status == "archived":
        if payload.is_default:
            book.refuse(_422, "an archived layout cannot be the default")
        layout.is_default = False
    if payload.is_default is True:
        if layout.status != "active":
            book.refuse(_422, "an archived layout cannot be the default — set status active first")
        _take_default(db, layout)
    elif payload.is_default is False:
        layout.is_default = False
    after = {"name": layout.name, "is_default": layout.is_default, "status": layout.status}
    record_audit(db, tenant_id=actor.tenant_id, action="ledger.layout_changed", entity_type="statement_layout",
                 entity_id=layout.id, actor=actor.label, detail={"before": before, "after": after})
    _commit_layout(db)
    db.refresh(layout)
    return envelope(_layout_read(layout))


@router.put("/statement-layouts/{layout_id}/rows", response_model=StatementLayoutEnvelope,
            response_model_exclude_unset=True)
def replace_statement_layout_rows(
    layout_id: str,
    payload: ReplaceStatementLayoutRowsRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Replace every row of a layout at once — a layout is reviewed as one
    page — with the same checks as creating one. `confirmed_by` names who
    accepted the new rows; the audit trail keeps the rows before and after."""
    require_permission(actor, "ledger.manage")
    confirmed_by = payload.confirmed_by.strip()
    if not confirmed_by:
        book.refuse(_422, "confirmed_by: name the person who accepted these rows")
    layout = get_scoped_or_404(db, StatementLayout, actor.tenant_id, layout_id)
    layouts.check(db, actor.tenant_id, layout.statement, payload.rows)
    before = _stored_rows(layout)
    layout.rows.clear()
    db.flush()
    for row in _row_dicts(payload.rows):
        layout.rows.append(StatementLayoutRow(tenant_id=actor.tenant_id, **row))
    layout.confirmed_by = confirmed_by
    layout.updated_at = datetime.now(timezone.utc)
    db.flush()
    record_audit(db, tenant_id=actor.tenant_id, action="ledger.layout_rows_replaced", entity_type="statement_layout",
                 entity_id=layout.id, actor=actor.label,
                 detail={"confirmed_by": confirmed_by, "before": before, "after": _stored_rows(layout)})
    db.commit()
    db.refresh(layout)
    return envelope(_layout_read(layout))


# --- waivers ---------------------------------------------------------------------


def _waiver_read(waiver: LedgerWaiver) -> dict:
    return LedgerWaiverRead.model_validate(waiver).model_dump(by_alias=True)


@router.post("/ledger-waivers", response_model=LedgerWaiverEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_ledger_waiver(
    payload: CreateLedgerWaiverRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Record a person's decision that a document needs no entry — the whole
    document, or one `source_event` of it — with their reason. The coverage
    read then lists it under `waived`, not `missing`. Refused while a posted
    entry records the fact (reverse that first), and posting a waived fact is
    refused until the waiver is revoked. Whether a document needs an entry is
    the workspace's posting rule and the person's call, never the agent's
    alone: `decided_by` names who decided."""
    require_permission(actor, "ledger.post")
    tenant_id = actor.tenant_id
    reason = payload.reason.strip()
    if not reason:
        book.refuse(_422, "reason: say why this document needs no entry")
    book.check_source(db, tenant_id, payload.source_type, payload.source_id)
    book.lock_source(db, payload.source_type, payload.source_id)
    entry = book.recording_entry(db, tenant_id, payload.source_type, payload.source_id, payload.source_event)
    if entry is not None:
        event = f" ({entry.source_event})" if entry.source_event else ""
        book.refuse(_409, f"{payload.source_type} {payload.source_id}{event} is in the book as {entry.entry_no} — "
                          "a fact is never both posted and waived; reverse the entry first")
    existing = db.scalar(select(LedgerWaiver).where(
        LedgerWaiver.tenant_id == tenant_id, LedgerWaiver.revoked_at.is_(None),
        LedgerWaiver.source_type == payload.source_type, LedgerWaiver.source_id == payload.source_id,
        func.coalesce(LedgerWaiver.source_event, "") == (payload.source_event or "")))
    if existing is not None:
        book.refuse(_409, f"already waived by {existing.id} — revoke it first to record a different decision")
    waiver = LedgerWaiver(
        tenant_id=tenant_id, source_type=payload.source_type, source_id=payload.source_id,
        source_event=payload.source_event, reason=reason,
        decided_by=(payload.decided_by or "").strip() or actor.label, waived_by=actor.label,
    )
    db.add(waiver)
    db.flush()
    record_audit(db, tenant_id=tenant_id, action="ledger.waiver_recorded", entity_type="ledger_waiver",
                 entity_id=waiver.id, actor=actor.label,
                 detail={"source_type": waiver.source_type, "source_id": waiver.source_id,
                         "source_event": waiver.source_event, "decided_by": waiver.decided_by})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        book.refuse(_409, "this fact was waived concurrently — read /ledger-waivers")
    db.refresh(waiver)
    return envelope(_waiver_read(waiver))


@router.post("/ledger-waivers/{waiver_id}/revoke", response_model=LedgerWaiverEnvelope,
             response_model_exclude_unset=True)
def revoke_ledger_waiver(
    waiver_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    payload: RevokeLedgerWaiverRequest | None = None,
):
    """Withdraw a waiver: the document is missing again until it is posted or
    waived anew. The waiver stays, revoked, with who revoked it and why."""
    require_permission(actor, "ledger.post")
    get_scoped_or_404(db, LedgerWaiver, actor.tenant_id, waiver_id)
    waiver = db.scalar(select(LedgerWaiver).where(
        LedgerWaiver.tenant_id == actor.tenant_id, LedgerWaiver.id == waiver_id,
    ).with_for_update().execution_options(populate_existing=True))
    if waiver.revoked_at is not None:
        book.refuse(_409, f"already revoked by {waiver.revoked_by}")
    waiver.revoked_at = datetime.now(timezone.utc)
    waiver.revoked_by = actor.label
    waiver.revoke_reason = (payload.reason.strip() or None) if payload and payload.reason else None
    record_audit(db, tenant_id=actor.tenant_id, action="ledger.waiver_revoked", entity_type="ledger_waiver",
                 entity_id=waiver.id, actor=actor.label,
                 detail={"source_type": waiver.source_type, "source_id": waiver.source_id,
                         "source_event": waiver.source_event, "reason": waiver.revoke_reason})
    db.commit()
    db.refresh(waiver)
    return envelope(_waiver_read(waiver))


@router.get("/ledger-waivers", response_model=LedgerWaiverListEnvelope, response_model_exclude_unset=True)
def list_ledger_waivers(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    source_type: str | None = None,
    source_id: str | None = None,
    source_event: str | None = None,
    revoked: Annotated[bool | None, Query(description="true: revoked only; false: live only; unset: both")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(LedgerWaiver, ranges=('created_at', 'revoked_at')))] = None,
):
    """Waivers newest first, revoked ones included unless `revoked=false`.
    `source_type` + `source_id` answers "why is this document not in the book"."""
    _read(actor)
    stmt = select(LedgerWaiver).where(LedgerWaiver.tenant_id == actor.tenant_id)
    if revoked is not None:
        stmt = stmt.where(LedgerWaiver.revoked_at.is_not(None) if revoked else LedgerWaiver.revoked_at.is_(None))
    return list_rows(
        db, stmt,
        filters={LedgerWaiver.source_type: source_type, LedgerWaiver.source_id: source_id,
                 LedgerWaiver.source_event: source_event},
        keyword=keyword,
        keyword_columns=(LedgerWaiver.reason, LedgerWaiver.decided_by),
        order_by=(LedgerWaiver.created_at.desc(),),
        pagination=requested_pagination(page, size), sort=order_by, extra=extra,
        render=lambda rows: [_waiver_read(row) for row in rows],
    )


@router.get("/ledger-waivers/{waiver_id}", response_model=LedgerWaiverEnvelope, response_model_exclude_unset=True)
def get_ledger_waiver(waiver_id: str, actor: Annotated[Actor, Depends(get_actor)],
                      db: Annotated[Session, Depends(get_db)]):
    _read(actor)
    return envelope(_waiver_read(get_scoped_or_404(db, LedgerWaiver, actor.tenant_id, waiver_id)))


# --- periods ---------------------------------------------------------------------


@router.get("/accounting-periods", response_model=AccountingPeriodListEnvelope, response_model_exclude_unset=True)
def list_accounting_periods(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(AccountingPeriod, ranges=('created_at', 'period_start', 'closed_at')))] = None,
):
    """The months something has posted into, or that were closed; newest first."""
    _read(actor)
    return list_rows(
        db, select(AccountingPeriod).where(AccountingPeriod.tenant_id == actor.tenant_id),
        filters={AccountingPeriod.status: status_filter},
        order_by=(AccountingPeriod.period_start.desc(),),
        pagination=requested_pagination(page, size), sort=order_by, extra=extra, read_model=AccountingPeriodRead,
    )


@router.post("/accounting-periods/close", response_model=AccountingPeriodEnvelope, response_model_exclude_unset=True)
def close_accounting_period(
    payload: PeriodActionRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Close the month `period` falls in: nothing posts into it afterwards.
    A draft dated in it could then never post, so drafts are posted or
    deleted first."""
    require_permission(actor, "period.close")
    tenant_id = actor.tenant_id
    period = book.lock_period(db, tenant_id, payload.period)
    if period.status == "closed":
        return envelope(AccountingPeriodRead.model_validate(period).model_dump(by_alias=True))
    drafts = list(db.scalars(select(JournalEntry.entry_no).where(
        JournalEntry.tenant_id == tenant_id, JournalEntry.status == "draft", JournalEntry.deleted_at.is_(None),
        JournalEntry.posting_date >= period.period_start, JournalEntry.posting_date <= period.period_end,
    ).order_by(JournalEntry.entry_no).limit(20)))
    if drafts:
        book.refuse(_409, f"drafts are dated in {period.period_start:%Y-%m}: {', '.join(drafts)} — "
                          "post or delete them before closing")
    period.status = "closed"
    period.closed_at = datetime.now(timezone.utc)
    period.closed_by = actor.label
    record_audit(db, tenant_id=tenant_id, action="ledger.period_closed", entity_type="accounting_period",
                 entity_id=period.id, actor=actor.label,
                 detail={"period": f"{period.period_start:%Y-%m}", "reason": payload.reason})
    db.commit()
    db.refresh(period)
    return envelope(AccountingPeriodRead.model_validate(period).model_dump(by_alias=True))


@router.post("/accounting-periods/reopen", response_model=AccountingPeriodEnvelope, response_model_exclude_unset=True)
def reopen_accounting_period(
    payload: PeriodActionRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Reopen a closed month, with the reason — the audit trail keeps it."""
    require_permission(actor, "period.close")
    if not (payload.reason or "").strip():
        book.refuse(_422, "reopening a closed month needs a reason")
    tenant_id = actor.tenant_id
    period = book.lock_period(db, tenant_id, payload.period)
    if period.status == "closed":
        period.status = "open"
        period.closed_at = None
        period.closed_by = None
        record_audit(db, tenant_id=tenant_id, action="ledger.period_reopened", entity_type="accounting_period",
                     entity_id=period.id, actor=actor.label,
                     detail={"period": f"{period.period_start:%Y-%m}", "reason": payload.reason})
    db.commit()
    db.refresh(period)
    return envelope(AccountingPeriodRead.model_validate(period).model_dump(by_alias=True))


# --- entries ---------------------------------------------------------------------


def _entry_read(entry: JournalEntry) -> dict:
    data = JournalEntryRead.model_validate(entry).model_dump(by_alias=True)
    lines = [line for line in entry.lines]
    data["lines"] = [JournalLineRead.model_validate(line).model_dump(by_alias=True) for line in lines]
    data["total"] = float(sum((book.money(line.debit) for line in lines), book.ZERO))
    return data


def _write_lines(db: Session, entry: JournalEntry, lines) -> None:
    for index, line in enumerate(lines, start=1):
        db.add(JournalLine(
            tenant_id=entry.tenant_id, entry_id=entry.id, line_no=index,
            ledger_account_id=line.ledger_account_id, debit=book.money(line.debit), credit=book.money(line.credit),
            currency=line.currency.upper() if line.currency else None, foreign_amount=line.foreign_amount,
            exchange_rate=line.exchange_rate, exchange_rate_id=line.exchange_rate_id,
            customer_id=line.customer_id, vendor_id=line.vendor_id,
            employee_id=line.employee_id, cost_center_id=line.cost_center_id, project_id=line.project_id,
            description=line.description,
        ))


def _entry_or_404(db: Session, tenant_id: str, entry_id: str, *, lock: bool = False) -> JournalEntry:
    stmt = select(JournalEntry).where(JournalEntry.tenant_id == tenant_id, JournalEntry.id == entry_id,
                                      JournalEntry.deleted_at.is_(None))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    entry = db.scalar(stmt)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="JournalEntry not found")
    return entry


def _commit_entry(db: Session, entry: JournalEntry) -> None:
    # read before the commit: a rollback expires the entry, and a refused
    # insert leaves nothing to read back
    tenant_id, source = entry.tenant_id, (entry.source_type, entry.source_id, entry.source_event or "")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(JournalEntry).where(
            JournalEntry.tenant_id == tenant_id, JournalEntry.status == "posted",
            JournalEntry.reversed_at.is_(None), JournalEntry.source_type == source[0],
            JournalEntry.source_id == source[1], func.coalesce(JournalEntry.source_event, "") == source[2]))
        book.refuse(_409, book.duplicate_source(existing) if existing is not None
                    else "the entry number is taken, or this entry was reversed concurrently")


@router.post("/journal-entries", response_model=JournalEntryEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_journal_entry(
    payload: CreateJournalEntryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """A balanced entry: a draft for a person to check, or posted at once.
    Name the fact it records (`source_type`, `source_id`, `source_event`) and
    that fact posts once; send `Idempotency-Key` so a retry posts nothing twice."""
    require_permission(actor, "ledger.post")
    tenant_id = actor.tenant_id
    book.functional_currency(db, tenant_id)
    book.refuse_closed(db, tenant_id, payload.posting_date)
    book.check_lines(db, tenant_id, payload.lines, payload.source_type, payload.source_event, payload.source_id)
    book.check_source(db, tenant_id, payload.source_type, payload.source_id)
    entry = JournalEntry(
        tenant_id=tenant_id,
        entry_no=payload.entry_no or allocate_document_number(
            db, tenant_id, model=JournalEntry, number_column=JournalEntry.entry_no, prefix="JE-",
            lock_scope="journal_entries", field="entry_no"),
        posting_date=payload.posting_date, status="draft", description=payload.description,
        source_type=payload.source_type, source_id=payload.source_id, source_event=payload.source_event,
        created_by=actor.label,
    )
    db.add(entry)
    db.flush()
    _write_lines(db, entry, payload.lines)
    db.flush()
    if payload.status == "posted":
        book.post(db, entry, actor.label)
    record_audit(db, tenant_id=tenant_id, action=f"ledger.entry_{'posted' if entry.status == 'posted' else 'drafted'}",
                 entity_type="journal_entry", entity_id=entry.id, actor=actor.label,
                 detail={"entry_no": entry.entry_no, "source_type": entry.source_type, "source_id": entry.source_id})
    _commit_entry(db, entry)
    db.refresh(entry)
    return envelope(_entry_read(entry))


def _draft(db: Session, actor: Actor, entry_id: str) -> JournalEntry:
    entry = _entry_or_404(db, actor.tenant_id, entry_id, lock=True)
    if entry.status != "draft":
        book.refuse(_409, f"{entry.entry_no} is posted — a posted entry is corrected by reversing it "
                          "(POST /journal-entries/{id}/reverse) and posting again")
    return entry


@router.patch("/journal-entries/{entry_id}", response_model=JournalEntryEnvelope, response_model_exclude_unset=True)
def update_journal_entry(
    entry_id: str,
    payload: UpdateJournalEntryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Change a draft. `lines`, when sent, replaces every line."""
    require_permission(actor, "ledger.post")
    entry = _draft(db, actor, entry_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("posting_date") is not None:
        book.refuse_closed(db, actor.tenant_id, updates["posting_date"])
    if payload.lines is not None:
        book.check_lines(db, actor.tenant_id, payload.lines, entry.source_type, entry.source_event,
                         entry.source_id)
        for line in list(entry.lines):
            db.delete(line)
        db.flush()
        _write_lines(db, entry, payload.lines)
    for field in ("posting_date", "description"):
        if updates.get(field) is not None:
            setattr(entry, field, updates[field])
    record_audit(db, tenant_id=actor.tenant_id, action="ledger.entry_changed", entity_type="journal_entry",
                 entity_id=entry.id, actor=actor.label, detail={"entry_no": entry.entry_no, "fields": sorted(updates)})
    db.commit()
    db.refresh(entry)
    return envelope(_entry_read(entry))


@router.delete("/journal-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_journal_entry(entry_id: str, actor: Annotated[Actor, Depends(get_actor)],
                         db: Annotated[Session, Depends(get_db)]):
    """Discard a draft. A posted entry is never deleted."""
    require_permission(actor, "ledger.post")
    entry = _draft(db, actor, entry_id)
    entry.deleted_at = datetime.now(timezone.utc)
    record_audit(db, tenant_id=actor.tenant_id, action="ledger.entry_discarded", entity_type="journal_entry",
                 entity_id=entry.id, actor=actor.label, detail={"entry_no": entry.entry_no})
    db.commit()


@router.post("/journal-entries/{entry_id}/post", response_model=JournalEntryEnvelope,
             response_model_exclude_unset=True)
def post_journal_entry(entry_id: str, actor: Annotated[Actor, Depends(get_actor)],
                       db: Annotated[Session, Depends(get_db)]):
    """Post a draft. Its lines are checked again: an account may have been
    archived or given sub-accounts since the draft was written."""
    require_permission(actor, "ledger.post")
    entry = _draft(db, actor, entry_id)
    book.check_lines(db, actor.tenant_id, entry.lines, entry.source_type, entry.source_event, entry.source_id)
    book.post(db, entry, actor.label)
    record_audit(db, tenant_id=actor.tenant_id, action="ledger.entry_posted", entity_type="journal_entry",
                 entity_id=entry.id, actor=actor.label, detail={"entry_no": entry.entry_no})
    _commit_entry(db, entry)
    db.refresh(entry)
    return envelope(_entry_read(entry))


@router.post("/journal-entries/{entry_id}/reverse", response_model=JournalEntryEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def reverse_journal_entry(
    entry_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    payload: ReverseJournalEntryRequest | None = None,
):
    """Post the mirror of a posted entry — every debit a credit, every credit
    a debit — on `posting_date` (today by default), in an open month. The
    original stays as it was, marked reversed, and its source fact may then be
    posted again. Each entry is reversed at most once."""
    require_permission(actor, "ledger.post")
    payload = payload or ReverseJournalEntryRequest()
    tenant_id = actor.tenant_id
    original = _entry_or_404(db, tenant_id, entry_id, lock=True)
    if original.status != "posted":
        book.refuse(_409, f"{original.entry_no} is a draft — change or delete it instead")
    if original.reverses_entry_id is not None:
        book.refuse(_409, f"{original.entry_no} is itself a reversal — post the original afresh instead")
    if original.reversed_at is not None:
        book.refuse(_409, f"{original.entry_no} is already reversed")
    day = payload.posting_date or business_today()
    reversal = JournalEntry(
        tenant_id=tenant_id,
        entry_no=allocate_document_number(db, tenant_id, model=JournalEntry, number_column=JournalEntry.entry_no,
                                          prefix="JE-", lock_scope="journal_entries", field="entry_no"),
        posting_date=day, status="draft",
        description=payload.description or f"Reversal of {original.entry_no}: {original.description}"[:4000],
        reverses_entry_id=original.id, created_by=actor.label,
    )
    db.add(reversal)
    db.flush()
    for line in original.lines:
        db.add(JournalLine(
            tenant_id=tenant_id, entry_id=reversal.id, line_no=line.line_no,
            ledger_account_id=line.ledger_account_id, debit=line.credit, credit=line.debit,
            currency=line.currency,
            foreign_amount=line.foreign_amount,
            exchange_rate=line.exchange_rate, exchange_rate_id=line.exchange_rate_id,
            customer_id=line.customer_id, vendor_id=line.vendor_id,
            employee_id=line.employee_id, cost_center_id=line.cost_center_id, project_id=line.project_id,
            description=line.description,
        ))
    db.flush()
    book.post(db, reversal, actor.label)
    original.reversed_at = datetime.now(timezone.utc)
    record_audit(db, tenant_id=tenant_id, action="ledger.entry_reversed", entity_type="journal_entry",
                 entity_id=original.id, actor=actor.label,
                 detail={"entry_no": original.entry_no, "reversal_entry_no": reversal.entry_no})
    _commit_entry(db, reversal)
    db.refresh(reversal)
    return envelope(_entry_read(reversal))


@router.get("/journal-entries", response_model=JournalEntryListEnvelope, response_model_exclude_unset=True)
def list_journal_entries(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    source_type: str | None = None,
    source_id: str | None = None,
    source_event: str | None = None,
    ledger_account_id: str | None = None,
    reverses_entry_id: str | None = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(JournalEntry, ranges=('posting_date', 'created_at', 'posted_at')))] = None,
):
    """Entries newest first, with their lines. `source_type` + `source_id`
    answers "is this document in the book yet"."""
    _read(actor)
    stmt = select(JournalEntry).options(selectinload(JournalEntry.lines)).where(
        JournalEntry.tenant_id == actor.tenant_id, JournalEntry.deleted_at.is_(None))
    if ledger_account_id:
        stmt = stmt.where(exists().where(JournalLine.entry_id == JournalEntry.id,
                                         JournalLine.ledger_account_id == ledger_account_id))
    return list_rows(
        db, stmt,
        filters={JournalEntry.status: status_filter, JournalEntry.source_type: source_type,
                 JournalEntry.source_id: source_id, JournalEntry.source_event: source_event,
                 JournalEntry.reverses_entry_id: reverses_entry_id},
        keyword=keyword,
        keyword_columns=(cast(JournalEntry.id, String), JournalEntry.entry_no, JournalEntry.description),
        order_by=(JournalEntry.posting_date.desc(), JournalEntry.entry_no.desc()),
        pagination=requested_pagination(page, size), sort=order_by, extra=extra,
        render=lambda rows: [_entry_read(row) for row in rows],
    )


@router.get("/journal-entries/{entry_id}", response_model=JournalEntryEnvelope, response_model_exclude_unset=True)
def get_journal_entry(entry_id: str, actor: Annotated[Actor, Depends(get_actor)],
                      db: Annotated[Session, Depends(get_db)]):
    _read(actor)
    return envelope(_entry_read(_entry_or_404(db, actor.tenant_id, entry_id)))
