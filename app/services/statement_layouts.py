"""Statement layouts — plan docs/plans/financial-statements-2026-11-25.md, phase 2.

A layout is a statement format as data: ordered rows that sum accounts or
other rows. The server applies one mechanically and checks only what makes a
statement wrong rather than badly chosen:

- on write (422 naming the row): a formula names codes of the same layout,
  never a heading, with no cycle; an accounts row names accounts of a type the
  statement takes; no account feeds two rows, directly, through a parent, or
  by overlapping code ranges;
- on read (never refused): accounts with movement that no row takes are
  listed as `unplaced` with their amounts, so a layout never makes money
  disappear. Should an account added later fall into two rows, the first row
  takes it and the read lists the clash.

Whether a line is named well, or whether an account belongs on it, is the
accountant's.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LedgerAccount, StatementLayout, StatementLayoutRow

ZERO = Decimal("0")
TYPES = {
    "income_statement": ("income", "expense"),
    "balance_sheet": ("asset", "liability", "equity"),
    # the account on the other side of the money: any type
    "cash_summary": ("income", "expense", "asset", "liability", "equity"),
}
EARNINGS = "earnings_not_yet_closed"


def _422(detail: str):
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


# --- which account each row takes ------------------------------------------------------


def _children(accounts: Iterable[LedgerAccount]) -> dict[str | None, list[LedgerAccount]]:
    out: dict[str | None, list[LedgerAccount]] = defaultdict(list)
    for account in accounts:
        out[account.parent_id].append(account)
    return out


def _with_descendants(roots: Iterable[LedgerAccount], children) -> list[LedgerAccount]:
    out, stack, seen = [], list(roots), set()
    while stack:
        account = stack.pop()
        if account.id in seen:
            continue
        seen.add(account.id)
        out.append(account)
        stack.extend(children.get(account.id, ()))
    return out


def _ref(ref) -> dict:
    return ref if isinstance(ref, dict) else ref.model_dump(exclude_none=True)


def _matched(ref: dict, accounts: list[LedgerAccount], by_id: dict[str, LedgerAccount]) -> list[LedgerAccount]:
    """The accounts a reference names directly — before sub-accounts."""
    if ref.get("ledger_account_id"):
        account = by_id.get(ref["ledger_account_id"])
        return [account] if account is not None else []
    if ref.get("code_from"):
        return [a for a in accounts if ref["code_from"] <= a.account_code <= ref["code_to"]]
    return []


def assign(rows: list, accounts: list[LedgerAccount], types: tuple[str, ...]):
    """Each account the layout's rows take, first row first, and the special
    lines they take. Returns (taken {account id: row code}, special
    {key: row code}, clashes [{ledger_account_id, account_code, rows}])."""
    by_id = {a.id: a for a in accounts}
    children = _children(accounts)
    taken: dict[str, str] = {}
    claims: dict[str, list[str]] = defaultdict(list)
    special: dict[str, str] = {}
    for row in sorted(rows, key=lambda r: _get(r, "row_no")):
        if _get(row, "kind") != "accounts":
            continue
        code = _get(row, "code")
        mine: set[str] = set()
        for ref in (_get(row, "accounts") or []):
            ref = _ref(ref)
            if ref.get(EARNINGS):
                special.setdefault(EARNINGS, code)
                continue
            for account in _with_descendants(_matched(ref, accounts, by_id), children):
                if account.account_type in types:
                    mine.add(account.id)
        for account_id in mine:
            claims[account_id].append(code)
            taken.setdefault(account_id, code)
    clashes = [{"ledger_account_id": a, "account_code": by_id[a].account_code, "rows": codes}
               for a, codes in claims.items() if len(codes) > 1]
    clashes.sort(key=lambda c: c["account_code"])
    return taken, special, clashes


def _get(row, field: str):
    return row.get(field) if isinstance(row, dict) else getattr(row, field)


# --- the write checks ---------------------------------------------------------------------


def check(db: Session, tenant_id: str, statement: str, rows: list) -> None:
    """Refuse a layout that would make the statement wrong, naming the row."""
    types = TYPES[statement]
    accounts = list(db.scalars(select(LedgerAccount).where(LedgerAccount.tenant_id == tenant_id)))
    by_id = {a.id: a for a in accounts}
    codes: dict[str, object] = {}
    numbers: set[int] = set()
    for row in rows:
        where = f"row {row.row_no} ({row.code})"
        if row.code in codes:
            _422(f"{where}: code {row.code!r} is used twice")
        if row.row_no in numbers:
            _422(f"{where}: row_no {row.row_no} is used twice")
        codes[row.code] = row
        numbers.add(row.row_no)
        if row.kind == "accounts" and not row.accounts:
            _422(f"{where}: an accounts row names the accounts it sums")
        if row.kind != "accounts" and row.accounts is not None:
            _422(f"{where}: only an accounts row takes accounts")
        if row.kind == "total" and not row.formula:
            _422(f"{where}: a total row names the rows it sums in formula")
        if row.kind != "total" and row.formula is not None:
            _422(f"{where}: only a total row has a formula")
        for ref in row.accounts or []:
            given = [bool(ref.ledger_account_id), bool(ref.code_from or ref.code_to), bool(ref.earnings_not_yet_closed)]
            if sum(given) != 1:
                _422(f"{where}: each account reference is one of ledger_account_id, code_from + code_to, "
                     "or earnings_not_yet_closed")
            if ref.ledger_account_id:
                account = by_id.get(ref.ledger_account_id)
                if account is None:
                    _422(f"{where}: no ledger account {ref.ledger_account_id}")
                if account.account_type not in types:
                    _422(f"{where}: account {account.account_code} is {account.account_type}; "
                         f"the {statement.replace('_', ' ')} takes {', '.join(types)}")
            elif ref.earnings_not_yet_closed:
                if statement != "balance_sheet":
                    _422(f"{where}: earnings not yet closed is a balance sheet line")
            else:
                if not (ref.code_from and ref.code_to) or ref.code_from > ref.code_to:
                    _422(f"{where}: a code range needs code_from <= code_to")
                for account in _matched(_ref(ref), accounts, by_id):
                    if account.account_type not in types:
                        _422(f"{where}: the range {ref.code_from}–{ref.code_to} takes account "
                             f"{account.account_code}, which is {account.account_type}; the "
                             f"{statement.replace('_', ' ')} takes {', '.join(types)}")

    # one account, one row
    ranges = [(ref.code_from, ref.code_to, row.code) for row in rows for ref in (row.accounts or [])
              if ref.code_from]
    for i, (a_from, a_to, a_row) in enumerate(ranges):
        for b_from, b_to, b_row in ranges[i + 1:]:
            if a_from <= b_to and b_from <= a_to:
                _422(f"the ranges {a_from}–{a_to} ({a_row}) and {b_from}–{b_to} ({b_row}) overlap: "
                     "an account would feed two rows")
    earnings = [row.code for row in rows for ref in (row.accounts or []) if ref.earnings_not_yet_closed]
    if len(earnings) > 1:
        _422(f"earnings not yet closed feeds {', '.join(earnings)}: one row only")
    _, _, clashes = assign(rows, accounts, types)
    if clashes:
        clash = clashes[0]
        _422(f"account {clash['account_code']} feeds {' and '.join(clash['rows'])}: a figure counted twice "
             "is a wrong statement — each account, with its sub-accounts, feeds one row")

    # formulas: codes of this layout, never a heading, no cycle
    for row in rows:
        for term in row.formula or []:
            target = codes.get(term.code)
            if target is None:
                _422(f"row {row.row_no} ({row.code}): the formula names {term.code!r}, which is not a row here")
            if target.kind == "heading":
                _422(f"row {row.row_no} ({row.code}): the formula names the heading {term.code!r}, which has no figure")
    state: dict[str, int] = {}

    def visit(code: str, path: list[str]) -> None:
        if state.get(code) == 2:
            return
        if state.get(code) == 1:
            cycle = path[path.index(code):] + [code]
            _422(f"the formulas go round in a circle: {' → '.join(cycle)}")
        state[code] = 1
        for term in codes[code].formula or []:
            visit(term.code, path + [code])
        state[code] = 2

    for code in codes:
        visit(code, [])


# --- reads -----------------------------------------------------------------------------------


def for_read(db: Session, tenant_id: str, statement: str, layout_id: str | None) -> StatementLayout | None:
    """The layout a statement read applies: the one named, none for
    `layout_id=none`, else the statement's default if there is one."""
    if layout_id == "none":
        return None
    if layout_id:
        layout = db.scalar(select(StatementLayout).where(StatementLayout.tenant_id == tenant_id,
                                                         StatementLayout.id == layout_id))
        if layout is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no statement layout {layout_id}")
        if layout.statement != statement:
            _422(f"layout {layout_id} is a {layout.statement.replace('_', ' ')} layout")
        return layout
    return db.scalar(select(StatementLayout).where(
        StatementLayout.tenant_id == tenant_id, StatementLayout.statement == statement,
        StatementLayout.is_default.is_(True), StatementLayout.status == "active"))


def evaluate(rows: list[StatementLayoutRow], taken: dict[str, str], special: dict[str, str],
             values: dict[str, Decimal], special_values: dict[str, Decimal]) -> dict[str, Decimal | None]:
    """One column of figures: each row's amount from natural-side account
    values. Headings have none."""
    sums: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for account_id, value in values.items():
        if account_id in taken:
            sums[taken[account_id]] += value
    for key, code in special.items():
        sums[code] += special_values.get(key, ZERO)
    by_code = {row.code: row for row in rows}
    out: dict[str, Decimal | None] = {}

    def figure(code: str) -> Decimal:
        if code not in out:
            row = by_code[code]
            if row.kind == "accounts":
                out[code] = row.sign * sums[code]
            elif row.kind == "total":
                out[code] = row.sign * sum((term["sign"] * figure(term["code"]) for term in row.formula), ZERO)
            else:
                out[code] = None
        return out[code] or ZERO

    for row in rows:
        figure(row.code)
    return out


def describe(layout: StatementLayout) -> dict:
    return {"id": layout.id, "name": layout.name, "statement": layout.statement, "status": layout.status,
            "is_default": layout.is_default, "confirmed_by": layout.confirmed_by}
