"""Exchange rates and foreign balances — plan docs/plans/foreign-currency-2026-11-27.md, phase 1.

A rate is a fact the workspace states: a pair, a day, a type and who
published it. The server stores it, finds the one asked for, and checks that
a line citing it agrees with it. It never picks a rate, never fetches one,
and never posts: which rate applies, when to revalue and where the
difference goes are the workspace's posting rules, applied by the agent.

- **Lookup**: the latest rate of a type on or before a day — of the pair as
  stated, or of the reverse pair inverted (`inverted: true`).
- **A cited rate never changes** on any write path.
- **Revaluation**: what each foreign-currency account (per party on a
  subledger) is worth at a day's rate, against the figure the book holds.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import case, event, func, select
from sqlalchemy.orm import Session

from app.models import ExchangeRate, JournalEntry, JournalLine, LedgerAccount
from app.services.ledger import SUBLEDGER_COLUMNS, ZERO, functional_currency, money

RATE_PLACES = Decimal("0.00000001")


def rate_value(value) -> Decimal:
    return Decimal(str(value)).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


def inverse(value) -> Decimal:
    return (Decimal(1) / Decimal(str(value))).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


def _404(detail: str):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def cited(db: Session, rate_id: str) -> bool:
    return db.scalar(select(JournalLine.id).where(JournalLine.exchange_rate_id == rate_id).limit(1)) is not None


@event.listens_for(Session, "before_flush")
def _kept_rates(session: Session, flush_context, instances) -> None:
    """A rate a journal line cites is part of that line's arithmetic: it is
    never edited or deleted, on any write path."""
    touched = [r for r in (*session.dirty, *session.deleted) if isinstance(r, ExchangeRate)]
    if not touched:
        return
    with session.no_autoflush:
        for rate in touched:
            if rate in session.dirty and not session.is_modified(rate, include_collections=False):
                continue
            if cited(session, rate.id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(f"rate {rate.from_currency}/{rate.to_currency} {rate.rate_type} {rate.rate_date} "
                            "is cited by a journal line and never changes — state a new rate and reverse what "
                            "used the wrong one"))


def describe(rate: ExchangeRate, *, inverted: bool = False) -> dict:
    stated = {"from_currency": rate.from_currency, "to_currency": rate.to_currency,
              "rate": float(rate_value(rate.rate))}
    return {
        "exchange_rate_id": rate.id,
        "from_currency": rate.to_currency if inverted else rate.from_currency,
        "to_currency": rate.from_currency if inverted else rate.to_currency,
        "rate": float(inverse(rate.rate) if inverted else rate_value(rate.rate)),
        "rate_date": rate.rate_date, "rate_type": rate.rate_type, "source": rate.source,
        "inverted": inverted, "stated": stated,
    }


def lookup(db: Session, tenant_id: str, from_currency: str, to_currency: str, on: date,
           rate_type: str) -> dict | None:
    """The latest rate of `rate_type` dated on or before `on`: the pair as
    asked, or the reverse pair inverted. The later of the two wins; on the
    same day, the pair as asked."""

    def latest(a: str, b: str) -> ExchangeRate | None:
        return db.scalar(select(ExchangeRate).where(
            ExchangeRate.tenant_id == tenant_id, ExchangeRate.from_currency == a, ExchangeRate.to_currency == b,
            ExchangeRate.rate_type == rate_type, ExchangeRate.rate_date <= on,
        ).order_by(ExchangeRate.rate_date.desc()).limit(1))

    direct, reverse = latest(from_currency, to_currency), latest(to_currency, from_currency)
    if direct is not None and (reverse is None or direct.rate_date >= reverse.rate_date):
        return describe(direct)
    if reverse is not None:
        return describe(reverse, inverted=True)
    return None


def check_cited(db: Session, tenant_id: str, line, where: str) -> None:
    """A line citing a rate fact agrees with it: the pair is the line's
    currency and the functional currency, either way round, and the rate is
    the line's. The date is not checked — which rate applies is the rule's."""
    rate_id = getattr(line, "exchange_rate_id", None)
    if not rate_id:
        return
    fact = db.get(ExchangeRate, rate_id)
    if fact is None or fact.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"{where}: exchange rate {rate_id} does not exist")
    if not line.currency:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"{where}: a line citing a rate states its currency, foreign_amount and rate")
    book = functional_currency(db, tenant_id)
    currency = line.currency.upper()
    stated = rate_value(line.exchange_rate)
    if (fact.from_currency, fact.to_currency) == (currency, book):
        expected = rate_value(fact.rate)
    elif (fact.from_currency, fact.to_currency) == (book, currency):
        expected = inverse(fact.rate)
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=(f"{where}: rate {rate_id} is {fact.from_currency}/{fact.to_currency}; the line "
                                    f"converts {currency} into the book's {book}"))
    if expected != stated:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=(f"{where}: the cited rate {fact.from_currency}/{fact.to_currency} "
                                    f"{fact.rate_type} {fact.rate_date} gives {expected} for {currency}, "
                                    f"not {stated}"))


# --- foreign figures ------------------------------------------------------------------


def signed_foreign():
    """A line's foreign amount with its side: debits positive."""
    return case((JournalLine.debit > 0, JournalLine.foreign_amount), else_=-JournalLine.foreign_amount)


def foreign_movements(db: Session, tenant_id: str, accounts: list[LedgerAccount], date_from: date | None,
                      date_to: date) -> dict[str, dict]:
    """Per foreign-currency account: its opening, debits, credits and closing
    in its own currency, from the lines in that currency."""
    by_id = {a.id: a for a in accounts if a.currency}
    if not by_id:
        return {}
    stmt = (select(JournalLine.ledger_account_id, JournalLine.currency, JournalEntry.posting_date,
                   func.sum(case((JournalLine.debit > 0, JournalLine.foreign_amount), else_=0)),
                   func.sum(case((JournalLine.credit > 0, JournalLine.foreign_amount), else_=0)))
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .where(JournalLine.tenant_id == tenant_id, JournalLine.ledger_account_id.in_(by_id),
                   JournalLine.foreign_amount.is_not(None), JournalEntry.status == "posted",
                   JournalEntry.deleted_at.is_(None), JournalEntry.posting_date <= date_to)
            .group_by(JournalLine.ledger_account_id, JournalLine.currency, JournalEntry.posting_date))
    out: dict[str, dict] = {a: {"currency": by_id[a].currency, "opening": ZERO, "debit": ZERO, "credit": ZERO}
                            for a in by_id}
    for account_id, currency, day, debit, credit in db.execute(stmt):
        if currency != by_id[account_id].currency:
            continue
        figures = out[account_id]
        if date_from is not None and day < date_from:
            figures["opening"] += money(debit) - money(credit)
        else:
            figures["debit"] += money(debit)
            figures["credit"] += money(credit)
    return {a: {**f, "closing": f["opening"] + f["debit"] - f["credit"]} for a, f in out.items()}


def _balances(db: Session, tenant_id: str, account: LedgerAccount, as_of: date, party_column=None):
    """(party or None) -> (foreign balance, book balance) on one account."""
    keys = [party_column] if party_column is not None else []
    stmt = (select(*keys,
                   func.coalesce(func.sum(case((JournalLine.currency == account.currency, signed_foreign()),
                                               else_=0)), 0),
                   func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .where(JournalLine.tenant_id == tenant_id, JournalLine.ledger_account_id == account.id,
                   JournalEntry.status == "posted", JournalEntry.deleted_at.is_(None),
                   JournalEntry.posting_date <= as_of))
    if keys:
        stmt = stmt.group_by(*keys)
    out = {}
    for row in db.execute(stmt):
        party = row[0] if keys else None
        out[party] = (money(row[-2]), money(row[-1]))
    return out


def parse_rates(value: str | None) -> dict[str, Decimal]:
    """`USD:7.82,CNY:1.083` — rates into the functional currency the caller
    states for this read."""
    out: dict[str, Decimal] = {}
    for part in (value or "").split(","):
        part = part.strip()
        if not part:
            continue
        currency, _, rate = part.partition(":")
        try:
            parsed = Decimal(rate)
        except Exception:
            parsed = None
        if len(currency.strip()) != 3 or parsed is None or parsed <= 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail=f"rates: {part!r} — write CUR:rate, for example USD:7.82")
        out[currency.strip().upper()] = rate_value(parsed)
    return out


def revaluation(db: Session, tenant_id: str, as_of: date, rate_type: str | None,
                stated: dict[str, Decimal]) -> dict:
    """What each foreign balance is worth at `as_of`, against the book.
    `difference` > 0 means the account needs a debit (a gain); < 0 a credit
    (a loss). Proposes; never posts."""
    book = functional_currency(db, tenant_id)
    accounts = list(db.scalars(select(LedgerAccount).where(
        LedgerAccount.tenant_id == tenant_id, LedgerAccount.currency.is_not(None),
        LedgerAccount.currency != book).order_by(LedgerAccount.account_code)))
    period = f"revalued:{as_of:%Y-%m}"
    rows, missing = [], defaultdict(list)
    rates: dict[str, dict | None] = {}
    gains = losses = ZERO
    for account in accounts:
        column = getattr(JournalLine, SUBLEDGER_COLUMNS[account.subledger]) if account.subledger else None
        balances = {k: v for k, v in _balances(db, tenant_id, account, as_of, column).items()
                    if v != (ZERO, ZERO)}
        if not balances:
            continue
        if account.currency not in rates:
            if account.currency in stated:
                rates[account.currency] = {"rate": float(stated[account.currency]), "rate_date": as_of,
                                           "rate_type": None, "exchange_rate_id": None, "inverted": False,
                                           "source": "stated for this read"}
            elif rate_type:
                found = lookup(db, tenant_id, account.currency, book, as_of, rate_type)
                rates[account.currency] = found and {
                    "rate": found["rate"], "rate_date": found["rate_date"], "rate_type": found["rate_type"],
                    "exchange_rate_id": found["exchange_rate_id"], "inverted": found["inverted"],
                    "source": found["source"]}
            else:
                rates[account.currency] = None
        rate = rates[account.currency]
        if rate is None:
            missing[account.currency].append(account.account_code)
            continue
        entry = db.scalar(select(JournalEntry.entry_no).where(
            JournalEntry.tenant_id == tenant_id, JournalEntry.status == "posted",
            JournalEntry.reversed_at.is_(None), JournalEntry.deleted_at.is_(None),
            JournalEntry.source_type == "ledger_account", JournalEntry.source_id == account.id,
            JournalEntry.source_event == period).limit(1))
        for party, (foreign, held) in sorted(balances.items(), key=lambda kv: str(kv[0] or "")):
            revalued = (foreign * Decimal(str(rate["rate"]))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            difference = revalued - held
            if difference > ZERO:
                gains += difference
            else:
                losses -= difference
            row = {"ledger_account_id": account.id, "account_code": account.account_code, "name": account.name,
                   "currency": account.currency, "foreign_balance": float(foreign), "book_balance": float(held),
                   "rate": rate["rate"], "revalued": float(revalued), "difference": float(difference),
                   "effect": "gain" if difference > ZERO else "loss" if difference < ZERO else "none",
                   # the foreign side is settled: what is left is the exchange on settling it
                   "settled": foreign == ZERO, "revaluation_entry_no": entry}
            if column is not None:
                row[SUBLEDGER_COLUMNS[account.subledger]] = party
            rows.append(row)
    return {
        "as_of": as_of, "functional_currency": book, "rate_type": rate_type,
        "source_event": period,
        "rates": {c: r for c, r in rates.items() if r is not None},
        "rows": rows,
        "missing_rates": [{"currency": c, "account_codes": codes} for c, codes in sorted(missing.items())],
        "totals": {"gains": float(gains), "losses": float(losses), "net": float(gains - losses)},
        "basis": ("Each foreign balance at the rate shown, against the book balance, which already includes "
                  "any revaluation posted before. difference > 0: debit the account (a gain); < 0: credit it "
                  "(a loss). A settled row has no foreign balance left: its difference is the exchange on "
                  "settling. The server posts nothing."),
    }
