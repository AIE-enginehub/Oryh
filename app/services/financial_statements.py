"""Financial statements — plan docs/plans/financial-statements-2026-11-25.md, phase 1.

The income statement and the balance sheet, grouped by `account_type` and the
chart's own tree. Every figure is a sum of posted journal lines, derived on
each read and stored nowhere. The server adds up and checks; which account
belongs on which line of a statutory format, and why a figure moved, is the
agent's and the accountant's.

- **Income statement**: income and expenses for a span of days, natural side,
  and the result; compared with an earlier span; optionally split by one line
  dimension, with lines lacking it under `unassigned` so columns always add up.
- **Balance sheet**: assets, liabilities and equity at a day, with
  **earnings not yet closed** — the cumulative income and expense balance —
  as an equity line, so the sheet is right whether or not the agent has
  posted a year-end close. `balanced` states assets = liabilities + equity.

Each read carries what makes its figures provisional: open months, draft
entries it leaves out, and the coverage read's missing and stale counts.

Phase 3: the **cash summary** — money into and out of the accounts the
person marked `is_cash`, grouped by the account on the other side of each
entry; a direct-method view from the book, not a statutory cash flow
statement.

Phase 2: a stored layout (`app/services/statement_layouts.py`) is applied to
the same sums and returned beside the default statement as `layout`, with the
accounts no row takes under `unplaced`.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AccountingPeriod,
    AccountingSettings,
    CostCenter,
    Customer,
    Employee,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    Project,
    Vendor,
)
from app.services import ledger_coverage
from app.services import statement_layouts as layouts
from app.services.ledger import ZERO, money

COMPARES = ("previous_period", "previous_year", "none")
# the line dimension `by` splits on, and how a column is named
DIMENSIONS: dict[str, tuple] = {
    "project": (JournalLine.project_id, Project, lambda p: p.project_name, lambda p: p.project_code),
    "cost_center": (JournalLine.cost_center_id, CostCenter, lambda c: c.name, lambda c: c.cost_center_code),
    "customer": (JournalLine.customer_id, Customer, lambda c: c.name, lambda c: None),
    "vendor": (JournalLine.vendor_id, Vendor, lambda v: v.name, lambda v: None),
    "employee": (JournalLine.employee_id, Employee, lambda e: e.name, lambda e: None),
}
BY = (*DIMENSIONS, "month")
UNASSIGNED = "unassigned"
INCOME_SECTIONS = (("income", "Income"), ("expense", "Expenses"))
BALANCE_SECTIONS = (("asset", "Assets"), ("liability", "Liabilities"), ("equity", "Equity"))
# the side each type normally sits on: +1 debit, -1 credit
NATURAL = {"asset": 1, "expense": 1, "liability": -1, "equity": -1, "income": -1}


def _422(detail: str):
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


# --- spans --------------------------------------------------------------------


def month_end(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def _add_months(day: date, months: int) -> date:
    """The same day `months` later (earlier when negative), clamped to the
    month's last day."""
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _whole_months(start: date, end: date) -> int | None:
    """How many calendar months the span is, when it is whole months."""
    if start.day != 1 or end != month_end(end):
        return None
    return (end.year - start.year) * 12 + end.month - start.month + 1


def year_start(day: date, first_month: int) -> date:
    """The first day of the financial year `day` falls in."""
    start = date(day.year, first_month, 1)
    return start if start <= day else date(day.year - 1, first_month, 1)


def resolve_span(db: Session, tenant_id: str, date_from: str | None, date_to: date | None,
                 today: date) -> tuple[date, date]:
    """Defaults to the current month. `date_to` alone reads its month;
    `date_from` alone reads to its month's end. `date_from=year_start` is the
    start of the financial year `date_to` falls in."""
    if date_from == "year_start":
        end = date_to or today
        return year_start(end, fiscal_year_start_month(db, tenant_id)), end
    start = None
    if date_from:
        try:
            start = date.fromisoformat(date_from)
        except ValueError:
            _422(f"date_from: {date_from!r} is not a date (YYYY-MM-DD) or 'year_start'")
    if start is None and date_to is None:
        start = today.replace(day=1)
        return start, month_end(start)
    if start is None:
        return date_to.replace(day=1), date_to
    end = date_to or month_end(start)
    if end < start:
        _422("date_to is before date_from")
    return start, end


def compare_span(start: date, end: date, compare: str) -> tuple[date, date] | None:
    if compare == "none":
        return None
    months = _whole_months(start, end)
    if compare == "previous_year":
        if months is not None:
            return _add_months(start, -12), month_end(_add_months(end.replace(day=1), -12))
        return _add_months(start, -12), _add_months(end, -12)
    if months is not None:
        return _add_months(start, -months), start - timedelta(days=1)
    length = (end - start).days + 1
    return start - timedelta(days=length), start - timedelta(days=1)


def compare_day(as_of: date, compare: str) -> date | None:
    if compare == "none":
        return None
    if compare == "previous_year":
        moved = _add_months(as_of, -12)
        return month_end(moved) if as_of == month_end(as_of) else moved
    return as_of.replace(day=1) - timedelta(days=1)


def parse_compare(value: str | None) -> str:
    value = value or "previous_period"
    if value not in COMPARES:
        _422(f"compare: {value!r} — one of {', '.join(COMPARES)}")
    return value


def parse_by(value: str | None) -> str | None:
    if value and value not in BY:
        _422(f"by: {value!r} — one of {', '.join(BY)}; one dimension at a time")
    return value or None


def _months(start: date, end: date) -> list[date]:
    out, day = [], start.replace(day=1)
    while day <= end:
        out.append(day)
        day = _add_months(day, 1)
    return out


# --- settings and what makes a figure provisional --------------------------------


def _settings(db: Session, tenant_id: str) -> AccountingSettings | None:
    return db.scalar(select(AccountingSettings).where(AccountingSettings.tenant_id == tenant_id))


def fiscal_year_start_month(db: Session, tenant_id: str) -> int:
    row = _settings(db, tenant_id)
    return row.fiscal_year_start_month if row is not None and row.fiscal_year_start_month else 1


def _provisional(db: Session, tenant_id: str, start: date | None, end: date, months: list[date]) -> dict:
    """Open months, draft entries the figures leave out, and the coverage
    read's counts for each month."""
    closed = set(db.scalars(select(AccountingPeriod.period_start).where(
        AccountingPeriod.tenant_id == tenant_id, AccountingPeriod.status == "closed",
        AccountingPeriod.period_start.in_(months))))
    drafts = select(func.count()).select_from(JournalEntry).where(
        JournalEntry.tenant_id == tenant_id, JournalEntry.status == "draft",
        JournalEntry.deleted_at.is_(None), JournalEntry.posting_date <= end)
    if start is not None:
        drafts = drafts.where(JournalEntry.posting_date >= start)
    coverage = []
    for month in months:
        report = ledger_coverage.coverage(db, tenant_id, month, ledger_coverage.DEFAULT_FAMILIES)
        coverage.append({"period": month, "missing": len(report["missing"]), "stale": len(report["stale"])})
    return {
        "period_status": {"open_months": [m for m in months if m not in closed],
                          "closed_months": [m for m in months if m in closed]},
        "drafts": db.scalar(drafts) or 0,
        "coverage": coverage,
    }


# --- sums ---------------------------------------------------------------------------


def _sums(db: Session, tenant_id: str, start: date | None, end: date,
          by: str | None = None) -> dict[str, dict[str, Decimal]]:
    """Per account, per column: debits minus credits of posted lines in the
    span. Without `by` the single column is `total`."""
    if by == "month":
        key = JournalEntry.posting_date
    elif by:
        key = DIMENSIONS[by][0]
    else:
        key = None
    columns = [JournalLine.ledger_account_id, func.sum(JournalLine.debit), func.sum(JournalLine.credit)]
    stmt = (select(*columns, *([key] if key is not None else []))
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .where(JournalLine.tenant_id == tenant_id, JournalEntry.status == "posted",
                   JournalEntry.deleted_at.is_(None), JournalEntry.posting_date <= end)
            .group_by(JournalLine.ledger_account_id, *([key] if key is not None else [])))
    if start is not None:
        stmt = stmt.where(JournalEntry.posting_date >= start)
    out: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for row in db.execute(stmt):
        account_id, debit, credit = row[0], row[1], row[2]
        if key is None:
            column = "total"
        elif by == "month":
            day = row[3] if isinstance(row[3], date) else date.fromisoformat(str(row[3])[:10])
            column = day.replace(day=1).isoformat()
        else:
            column = str(row[3]) if row[3] is not None else UNASSIGNED
        out[account_id][column] += money(debit) - money(credit)
    return out


def _rolled(accounts: list[LedgerAccount], sums: dict[str, dict[str, Decimal]]) -> dict[str, dict[str, Decimal]]:
    """Each account's figures with its sub-accounts' carried up the tree."""
    parents = {a.id: a.parent_id for a in accounts}
    rolled: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for account_id, columns in sums.items():
        node = account_id
        while node is not None:
            for column, amount in columns.items():
                rolled[node][column] += amount
            node = parents.get(node)
    return rolled


def _tree_order(accounts: list[LedgerAccount]) -> list[tuple[LedgerAccount, int]]:
    """Accounts in the chart's order — each parent before its children, by
    code — with their depth."""
    children: dict[str | None, list[LedgerAccount]] = defaultdict(list)
    ids = {a.id for a in accounts}
    for account in accounts:
        children[account.parent_id if account.parent_id in ids else None].append(account)
    out: list[tuple[LedgerAccount, int]] = []

    def walk(parent: str | None, depth: int) -> None:
        for account in sorted(children[parent], key=lambda a: a.account_code):
            out.append((account, depth))
            walk(account.id, depth + 1)

    walk(None, 0)
    return out


def _figure(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def _change(amount: Decimal, base: Decimal | None) -> dict:
    if base is None:
        return {}
    change = amount - base
    return {"compare": _figure(base), "change": _figure(change),
            "change_ratio": round(float(change / abs(base)), 4) if base != ZERO else None}


def _accounts(db: Session, tenant_id: str, types: Iterable[str]) -> list[LedgerAccount]:
    return list(db.scalars(select(LedgerAccount).where(LedgerAccount.tenant_id == tenant_id,
                                                       LedgerAccount.account_type.in_(tuple(types)))))


def _section(key: str, label: str, accounts: list[LedgerAccount], rolled, rolled_compare,
             raw, raw_compare, columns: list[str] | None) -> tuple[dict, Decimal]:
    """One `account_type` of the statement: the accounts that moved in either
    span, natural side, in the chart's order."""
    sign = NATURAL[key]
    mine = [a for a in accounts if a.account_type == key]
    with_children = {a.parent_id for a in mine if a.parent_id}
    rows = []
    for account, depth in _tree_order(mine):
        if account.id not in rolled and (rolled_compare is None or account.id not in rolled_compare):
            continue
        figures = rolled.get(account.id, {})
        amount = sign * sum(figures.values(), ZERO)
        row = {"ledger_account_id": account.id, "account_code": account.account_code, "name": account.name,
               "depth": depth, "summary": account.id in with_children, "amount": _figure(amount)}
        if columns is not None:
            row["amounts"] = {c: _figure(sign * figures.get(c, ZERO)) for c in columns}
        if rolled_compare is not None:
            row.update(_change(amount, sign * sum(rolled_compare.get(account.id, {}).values(), ZERO)))
        rows.append(row)
    ids = {a.id for a in mine}
    total = sign * sum((sum(raw[i].values(), ZERO) for i in raw if i in ids), ZERO)
    section = {"key": key, "label": label, "total": _figure(total), "rows": rows}
    if columns is not None:
        section["totals"] = {c: _figure(sign * sum((raw[i].get(c, ZERO) for i in raw if i in ids), ZERO))
                             for c in columns}
    if raw_compare is not None:
        section.update(_change(total, sign * sum((sum(raw_compare[i].values(), ZERO)
                                                  for i in raw_compare if i in ids), ZERO)))
    return section, total


def _columns(db: Session, tenant_id: str, by: str, start: date, end: date,
             sums: dict[str, dict[str, Decimal]]) -> list[dict]:
    if by == "month":
        return [{"key": m.isoformat(), "label": m.strftime("%Y-%m")} for m in _months(start, end)]
    keys = sorted({c for columns in sums.values() for c in columns if c != UNASSIGNED})
    _, model, name, code = DIMENSIONS[by]
    found = {str(r.id): r for r in db.scalars(select(model).where(model.tenant_id == tenant_id, model.id.in_(keys)))}
    out = [{"key": k, "label": name(found[k]) if k in found else k,
            "code": code(found[k]) if k in found else None} for k in keys]
    out.sort(key=lambda c: (c["code"] or "", c["label"] or ""))
    if any(UNASSIGNED in columns for columns in sums.values()):
        out.append({"key": UNASSIGNED, "label": "Unassigned", "code": None})
    return out


# --- a stored layout ------------------------------------------------------------------


def _layout_block(layout, accounts: list[LedgerAccount], raw, raw_compare, keys: list[str] | None,
                  special: dict[str, Decimal] | None = None,
                  special_compare: dict[str, Decimal] | None = None, signed: bool = True) -> dict:
    """The layout's lines, applied mechanically to the same sums as the
    default statement; what no row takes is listed as `unplaced`."""
    types = layouts.TYPES[layout.statement]
    rows = list(layout.rows)
    taken, placed_special, clashes = layouts.assign(rows, accounts, types)
    kinds = {a.id: a for a in accounts if a.account_type in types}

    def natural(sums, column: str | None = None) -> dict[str, Decimal]:
        # `signed=False`: the figures are already on the statement's side
        return {a: (NATURAL[kinds[a].account_type] if signed else 1) * (
                    sum(cols.values(), ZERO) if column is None else cols.get(column, ZERO))
                for a, cols in sums.items() if a in kinds}

    values = natural(raw)
    main = layouts.evaluate(rows, taken, placed_special, values, special or {})
    per_column = ({c: layouts.evaluate(rows, taken, placed_special, natural(raw, c), {}) for c in keys}
                  if keys is not None else None)
    compared = natural(raw_compare) if raw_compare is not None else None
    base = (layouts.evaluate(rows, taken, placed_special, compared, special_compare or {})
            if compared is not None else None)
    moved = set(values) | set(compared or {})
    lines = []
    for row in rows:
        amount = main[row.code]
        line = {"row_no": row.row_no, "code": row.code, "label": row.label, "kind": row.kind,
                "amount": _figure(amount) if amount is not None else None}
        if amount is not None:
            if per_column is not None:
                line["amounts"] = {c: _figure(per_column[c][row.code]) for c in keys}
            if base is not None:
                line.update(_change(amount, base[row.code]))
        if row.kind == "accounts":
            feeding = sorted((kinds[a] for a in moved if taken.get(a) == row.code), key=lambda a: a.account_code)
            line["accounts"] = [{"ledger_account_id": a.id, "account_code": a.account_code, "name": a.name,
                                 "amount": _figure(row.sign * values.get(a.id, ZERO))} for a in feeding]
        lines.append(line)
    unplaced = []
    for account in sorted((kinds[a] for a in moved if a not in taken), key=lambda a: a.account_code):
        item = {"ledger_account_id": account.id, "account_code": account.account_code, "name": account.name,
                "account_type": account.account_type, "amount": _figure(values.get(account.id, ZERO))}
        if compared is not None:
            item["compare"] = _figure(compared.get(account.id, ZERO))
        unplaced.append(item)
    for key, value in (special or {}).items():
        if key not in placed_special and (value != ZERO or (special_compare or {}).get(key, ZERO) != ZERO):
            unplaced.append({"key": key, "name": "Earnings not yet closed", "amount": _figure(value)})
    return {**layouts.describe(layout), "lines": lines, "unplaced": unplaced, "clashes": clashes}


# --- the statements -------------------------------------------------------------------


def income_statement(db: Session, tenant_id: str, start: date, end: date, compare: str,
                     by: str | None, layout=None) -> dict:
    accounts = _accounts(db, tenant_id, ("income", "expense"))
    ids = {a.id for a in accounts}
    raw = {k: v for k, v in _sums(db, tenant_id, start, end, by).items() if k in ids}
    span = compare_span(start, end, compare)
    raw_compare = ({k: v for k, v in _sums(db, tenant_id, *span).items() if k in ids}
                   if span is not None else None)
    columns = _columns(db, tenant_id, by, start, end, raw) if by else None
    keys = [c["key"] for c in columns] if columns is not None else None
    rolled = _rolled(accounts, raw)
    rolled_compare = _rolled(accounts, raw_compare) if raw_compare is not None else None
    sections, totals = [], {}
    for key, label in INCOME_SECTIONS:
        section, total = _section(key, label, accounts, rolled, rolled_compare, raw, raw_compare, keys)
        sections.append(section)
        totals[key] = total
    result_amount = totals["income"] - totals["expense"]
    result = {"amount": _figure(result_amount)}
    if keys is not None:
        result["amounts"] = {k: round(sections[0]["totals"][k] - sections[1]["totals"][k], 2) for k in keys}
    if raw_compare is not None:
        base = -sum((sum(v.values(), ZERO) for v in raw_compare.values()), ZERO)
        result.update(_change(result_amount, base))
    settings = _settings(db, tenant_id)
    out = {
        "date_from": start, "date_to": end, "currency": settings.functional_currency if settings else None,
        "compare": {"date_from": span[0], "date_to": span[1]} if span else None,
        "by": by, "columns": columns, "sections": sections, "result": result,
        "layout": _layout_block(layout, accounts, raw, raw_compare, keys) if layout is not None else None,
    }
    out.update(_provisional(db, tenant_id, start, end, _months(start, end)))
    return out


def balance_sheet(db: Session, tenant_id: str, as_of: date, compare: str, layout=None) -> dict:
    accounts = _accounts(db, tenant_id, ("asset", "liability", "equity", "income", "expense"))
    day = compare_day(as_of, compare)
    raw = _sums(db, tenant_id, None, as_of)
    raw_compare = _sums(db, tenant_id, None, day) if day is not None else None
    by_type = {a.id: a.account_type for a in accounts}

    def earnings(sums) -> Decimal:
        # income and expense not yet closed into equity, on equity's side
        return -sum((sum(v.values(), ZERO) for k, v in sums.items() if by_type.get(k) in ("income", "expense")),
                    ZERO)

    sheet = [a for a in accounts if a.account_type in ("asset", "liability", "equity")]
    keep = {a.id for a in sheet}
    rolled = _rolled(sheet, {k: v for k, v in raw.items() if k in keep})
    rolled_compare = (_rolled(sheet, {k: v for k, v in raw_compare.items() if k in keep})
                      if raw_compare is not None else None)
    sections, totals = [], {}
    for key, label in BALANCE_SECTIONS:
        section, total = _section(key, label, sheet, rolled, rolled_compare, raw,
                                  raw_compare, None)
        sections.append(section)
        totals[key] = total
    unclosed = earnings(raw)
    line = {"key": "earnings_not_yet_closed", "name": "Earnings not yet closed", "amount": _figure(unclosed)}
    equity = sections[2]
    if raw_compare is not None:
        unclosed_compare = earnings(raw_compare)
        line.update(_change(unclosed, unclosed_compare))
        base = equity["compare"] + float(unclosed_compare)
        equity.update(_change(totals["equity"] + unclosed, Decimal(str(base))))
    equity["earnings_not_yet_closed"] = line
    equity["total"] = _figure(totals["equity"] + unclosed)
    assets = totals["asset"]
    claims = totals["liability"] + totals["equity"] + unclosed
    settings = _settings(db, tenant_id)
    out = {
        "as_of": as_of, "currency": settings.functional_currency if settings else None,
        "compare": {"as_of": day} if day else None, "sections": sections,
        "totals": {"assets": _figure(assets), "liabilities_and_equity": _figure(claims)},
        "balanced": assets == claims,
        "retained_earnings_account_id": settings.retained_earnings_account_id if settings else None,
        "layout": (_layout_block(layout, accounts, raw, raw_compare, None, {layouts.EARNINGS: unclosed},
                                 {layouts.EARNINGS: unclosed_compare} if raw_compare is not None else None)
                   if layout is not None else None),
    }
    out.update(_provisional(db, tenant_id, None, as_of, [as_of.replace(day=1)]))
    return out


# --- the cash summary (phase 3) -------------------------------------------------------------

CASH_BASIS = (
    "Money into and out of the cash accounts (is_cash), from posted entries. Each entry's cash movement is "
    "attributed to its other lines by their own amounts (credit minus debit), so the groups add up to the "
    "change in cash. An entry touching only cash accounts is a transfer: it moves no money in or out. A "
    "direct-method view from the book, not a statutory cash flow statement."
)
CASH_SECTIONS = (("income", "Income"), ("expense", "Expenses"), ("asset", "Other assets"),
                 ("liability", "Liabilities"), ("equity", "Equity"))


def cash_ids(accounts: list[LedgerAccount]) -> set[str]:
    """Every account the person marked as cash, and its sub-accounts."""
    by_id = {a.id: a for a in accounts}
    out = set()
    for account in accounts:
        node = account
        while node is not None:
            if node.is_cash:
                out.add(account.id)
                break
            node = by_id.get(node.parent_id) if node.parent_id else None
    return out


def _cash_flows(db: Session, tenant_id: str, cash: set[str], start: date, end: date):
    """Per counterpart account, the cash received from it and paid to it in
    the span; and the transfers between cash accounts."""
    flows: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"received": ZERO, "paid": ZERO})
    transfers = {"count": 0, "amount": ZERO}
    if not cash:
        return flows, transfers
    touching = (select(JournalLine.entry_id)
                .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                .where(JournalLine.tenant_id == tenant_id, JournalEntry.status == "posted",
                       JournalEntry.deleted_at.is_(None), JournalEntry.posting_date >= start,
                       JournalEntry.posting_date <= end, JournalLine.ledger_account_id.in_(cash)))
    lines = db.execute(select(JournalLine.entry_id, JournalLine.ledger_account_id, JournalLine.debit,
                              JournalLine.credit)
                       .where(JournalLine.tenant_id == tenant_id, JournalLine.entry_id.in_(touching))
                       .order_by(JournalLine.entry_id, JournalLine.line_no))
    entries: dict[str, list] = defaultdict(list)
    for entry_id, account_id, debit, credit in lines:
        entries[entry_id].append((account_id, money(debit), money(credit)))
    for entry_lines in entries.values():
        others = [line for line in entry_lines if line[0] not in cash]
        if not others:
            transfers["count"] += 1
            transfers["amount"] += sum((debit for _, debit, _ in entry_lines), ZERO)
            continue
        for account_id, debit, credit in others:
            net = credit - debit
            if net > ZERO:
                flows[account_id]["received"] += net
            elif net < ZERO:
                flows[account_id]["paid"] -= net
    return flows, transfers


def cash_summary(db: Session, tenant_id: str, start: date, end: date, compare: str, layout=None) -> dict:
    accounts = _accounts(db, tenant_id, ("asset", "liability", "equity", "income", "expense"))
    by_id = {a.id: a for a in accounts}
    cash = cash_ids(accounts)
    flows, transfers = _cash_flows(db, tenant_id, cash, start, end)
    span = compare_span(start, end, compare)
    compared = _cash_flows(db, tenant_id, cash, *span)[0] if span is not None else None

    def net(f) -> Decimal:
        return f["received"] - f["paid"]

    sections = []
    for key, label in CASH_SECTIONS:
        ids = sorted({a for a in (set(flows) | set(compared or {})) if by_id[a].account_type == key},
                     key=lambda a: by_id[a].account_code)
        if not ids:
            continue
        rows, total, base = [], ZERO, ZERO
        for account_id in ids:
            f = flows.get(account_id, {"received": ZERO, "paid": ZERO})
            account = by_id[account_id]
            row = {"ledger_account_id": account_id, "account_code": account.account_code, "name": account.name,
                   "received": _figure(f["received"]), "paid": _figure(f["paid"]), "net": _figure(net(f))}
            total += net(f)
            if compared is not None:
                before = net(compared[account_id]) if account_id in compared else ZERO
                base += before
                row.update(_change(net(f), before))
            rows.append(row)
        section = {"key": key, "label": label, "net": _figure(total), "rows": rows}
        if compared is not None:
            section.update(_change(total, base))
        sections.append(section)

    cash_accounts = [a for a in accounts if a.id in cash]
    opening = {k: v for k, v in _sums(db, tenant_id, None, start - timedelta(days=1)).items() if k in cash}
    closing = {k: v for k, v in _sums(db, tenant_id, None, end).items() if k in cash}
    open_total = sum((sum(v.values(), ZERO) for v in opening.values()), ZERO)
    close_total = sum((sum(v.values(), ZERO) for v in closing.values()), ZERO)
    rolled_open, rolled_close = _rolled(cash_accounts, opening), _rolled(cash_accounts, closing)
    parents = {a.parent_id for a in cash_accounts if a.parent_id}
    cash_rows = []
    for account, depth in _tree_order(cash_accounts):
        before = sum(rolled_open.get(account.id, {}).values(), ZERO)
        after = sum(rolled_close.get(account.id, {}).values(), ZERO)
        cash_rows.append({"ledger_account_id": account.id, "account_code": account.account_code,
                          "name": account.name, "depth": depth, "summary": account.id in parents,
                          "opening": _figure(before), "closing": _figure(after), "change": _figure(after - before)})
    net_change = sum((net(f) for f in flows.values()), ZERO)
    settings = _settings(db, tenant_id)
    out = {
        "date_from": start, "date_to": end, "currency": settings.functional_currency if settings else None,
        "compare": {"date_from": span[0], "date_to": span[1]} if span else None,
        "basis": CASH_BASIS,
        "cash_accounts": cash_rows,
        "opening": _figure(open_total), "closing": _figure(close_total), "net_change": _figure(net_change),
        "sections": sections,
        "transfers": {"count": transfers["count"], "amount": _figure(transfers["amount"])},
        # opening + what came in and went out = closing; always, for a book of balanced entries
        "reconciled": open_total + net_change == close_total,
        "layout": None,
    }
    if compared is not None:
        out["net_change_compare"] = _figure(sum((net(f) for f in compared.values()), ZERO))
    if layout is not None:
        values = {a: {"total": net(f)} for a, f in flows.items()}
        base_values = ({a: {"total": net(f)} for a, f in compared.items()} if compared is not None else None)
        out["layout"] = _layout_block(layout, accounts, values, base_values, None, signed=False)
    out.update(_provisional(db, tenant_id, start, end, _months(start, end)))
    return out
