"""Exchange rates and revaluation — plan docs/plans/foreign-currency-2026-11-27.md, phase 1.

Rates are facts the workspace states with their source; writing them needs
`ledger.manage`, reading them `ledger.read`. A rate a journal line cites
never changes. The revaluation read proposes what each foreign balance is
worth at a day; the agent posts the entry by the workspace's rule.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
from app.api.deps import Actor, get_actor, require_permission
from app.core.business_date import business_today
from app.db.session import get_db
from app.models import ExchangeRate
from app.schemas import (
    ExchangeRateEnvelope,
    ExchangeRateListEnvelope,
    ExchangeRateRead,
    ExchangeRateRequest,
    ImportExchangeRatesRequest,
    UpdateExchangeRateRequest,
)
from app.services import exchange_rates as rates
from app.services.audit import record_audit
from app.services.type_options import require_type_option

router = APIRouter()

_409 = status.HTTP_409_CONFLICT
_422 = status.HTTP_422_UNPROCESSABLE_CONTENT


def _read(actor: Actor) -> None:
    require_permission(actor, "ledger.read")


def _rate_read(rate: ExchangeRate) -> dict:
    data = ExchangeRateRead.model_validate(rate).model_dump(by_alias=True)
    data["rate"] = float(rates.rate_value(rate.rate))
    return data


def _normalized(db: Session, tenant_id: str, payload: ExchangeRateRequest, where: str = "") -> dict:
    values = {
        "from_currency": payload.from_currency.upper(), "to_currency": payload.to_currency.upper(),
        "rate": rates.rate_value(payload.rate), "rate_date": payload.rate_date,
        "rate_type": payload.rate_type.strip(), "source": payload.source.strip(),
    }
    if values["from_currency"] == values["to_currency"]:
        raise HTTPException(status_code=_422, detail=f"{where}a rate converts one currency into another")
    if not values["source"]:
        raise HTTPException(status_code=_422, detail=f"{where}source: say who published this rate")
    if values["rate"] <= 0:
        raise HTTPException(status_code=_422, detail=f"{where}rate: below 0.00000001 is not a rate")
    require_type_option(db, tenant_id, "exchange_rate_type", values["rate_type"])
    return values


def _existing(db: Session, tenant_id: str, values: dict) -> ExchangeRate | None:
    return db.scalar(select(ExchangeRate).where(
        ExchangeRate.tenant_id == tenant_id, ExchangeRate.from_currency == values["from_currency"],
        ExchangeRate.to_currency == values["to_currency"], ExchangeRate.rate_date == values["rate_date"],
        ExchangeRate.rate_type == values["rate_type"]))


def _clash(existing: ExchangeRate, values: dict) -> str:
    return (f"{values['from_currency']}/{values['to_currency']} {values['rate_type']} {values['rate_date']} is "
            f"already stated as {rates.rate_value(existing.rate)} ({existing.source}) — a day and type has one "
            "rate; correct it (if nothing cites it) or state another type")


@router.get("/exchange-rates", response_model=ExchangeRateListEnvelope, response_model_exclude_unset=True)
def list_exchange_rates(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    from_currency: str | None = None,
    to_currency: str | None = None,
    rate_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(ExchangeRate, ranges=('created_at',)))] = None,
):
    """The rates the workspace has stated, newest day first."""
    _read(actor)
    stmt = select(ExchangeRate).where(ExchangeRate.tenant_id == actor.tenant_id)
    if date_from is not None:
        stmt = stmt.where(ExchangeRate.rate_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(ExchangeRate.rate_date <= date_to)
    return list_rows(
        db, stmt,
        filters={ExchangeRate.from_currency: from_currency.upper() if from_currency else None,
                 ExchangeRate.to_currency: to_currency.upper() if to_currency else None,
                 ExchangeRate.rate_type: rate_type},
        order_by=(ExchangeRate.rate_date.desc(), ExchangeRate.from_currency, ExchangeRate.to_currency),
        pagination=requested_pagination(page, size), sort=order_by, extra=extra,
        render=lambda rows: [_rate_read(row) for row in rows],
    )


@router.get("/exchange-rates/lookup")
def lookup_exchange_rate(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    from_currency: Annotated[str, Query(min_length=3, max_length=3)],
    to_currency: Annotated[str, Query(min_length=3, max_length=3)],
    rate_type: Annotated[str, Query(description="required: the server does not choose between rate types")],
    on: Annotated[date | None, Query(description="default: today")] = None,
):
    """The latest rate of `rate_type` dated on or before `on`, with its
    `rate_date` so its age shows. When only the reverse pair is stated, it is
    answered inverted (`inverted: true`, `stated` shows the fact as written).
    404 when none is stated: the server never falls back to another type."""
    _read(actor)
    day = on or business_today()
    found = rates.lookup(db, actor.tenant_id, from_currency.upper(), to_currency.upper(), day, rate_type)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=(f"no {rate_type} rate {from_currency.upper()}/{to_currency.upper()} "
                                    f"(or its reverse) on or before {day} — import it with its source"))
    return envelope(found)


@router.post("/exchange-rates", response_model=ExchangeRateEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_exchange_rate(
    payload: ExchangeRateRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """State one rate with its type and source. One rate per pair, day and type."""
    require_permission(actor, "ledger.manage")
    values = _normalized(db, actor.tenant_id, payload)
    existing = _existing(db, actor.tenant_id, values)
    if existing is not None:
        raise HTTPException(status_code=_409, detail=_clash(existing, values))
    rate = ExchangeRate(tenant_id=actor.tenant_id, created_by=actor.label, **values)
    db.add(rate)
    db.flush()
    record_audit(db, tenant_id=actor.tenant_id, action="ledger.rate_stated", entity_type="exchange_rate",
                 entity_id=rate.id, actor=actor.label,
                 detail={k: str(v) for k, v in values.items()})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=_409, detail="this rate was stated concurrently — read /exchange-rates")
    db.refresh(rate)
    return envelope(_rate_read(rate))


@router.post("/exchange-rates/import", status_code=status.HTTP_201_CREATED)
def import_exchange_rates(
    payload: ImportExchangeRatesRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """State many rates at once, all or nothing. A row equal to one already
    stated (same pair, day, type and rate) is skipped, so an import can be
    re-run; a row that differs from one stated is refused, naming it."""
    require_permission(actor, "ledger.manage")
    created, skipped, seen = [], 0, set()
    for index, item in enumerate(payload.rates):
        values = _normalized(db, actor.tenant_id, item, f"rates[{index}]: ")
        key = (values["from_currency"], values["to_currency"], values["rate_date"], values["rate_type"])
        if key in seen:
            raise HTTPException(status_code=_422, detail=f"rates[{index}]: the same pair, day and type twice")
        seen.add(key)
        existing = _existing(db, actor.tenant_id, values)
        if existing is not None:
            if rates.rate_value(existing.rate) == values["rate"]:
                skipped += 1
                continue
            raise HTTPException(status_code=_409, detail=f"rates[{index}]: {_clash(existing, values)}")
        rate = ExchangeRate(tenant_id=actor.tenant_id, created_by=actor.label, **values)
        db.add(rate)
        created.append(rate)
    db.flush()
    record_audit(db, tenant_id=actor.tenant_id, action="ledger.rates_imported", entity_type="exchange_rate",
                 entity_id=created[0].id if created else actor.tenant_id, actor=actor.label,
                 detail={"created": len(created), "skipped": skipped})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=_409, detail="rates were stated concurrently — import again")
    return envelope({"created": len(created), "skipped": skipped,
                     "rates": [_rate_read(rate) for rate in created]})


@router.patch("/exchange-rates/{rate_id}", response_model=ExchangeRateEnvelope, response_model_exclude_unset=True)
def update_exchange_rate(
    rate_id: str,
    payload: UpdateExchangeRateRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Correct a rate or its source — only while no journal line cites it."""
    require_permission(actor, "ledger.manage")
    rate = get_scoped_or_404(db, ExchangeRate, actor.tenant_id, rate_id)
    before = {"rate": str(rates.rate_value(rate.rate)), "source": rate.source}
    if payload.rate is not None:
        rate.rate = rates.rate_value(payload.rate)
    if payload.source is not None:
        if not payload.source.strip():
            raise HTTPException(status_code=_422, detail="source: say who published this rate")
        rate.source = payload.source.strip()
    db.flush()  # a cited rate is refused here, by the listener
    record_audit(db, tenant_id=actor.tenant_id, action="ledger.rate_corrected", entity_type="exchange_rate",
                 entity_id=rate.id, actor=actor.label,
                 detail={"before": before, "after": {"rate": str(rates.rate_value(rate.rate)),
                                                     "source": rate.source}})
    db.commit()
    db.refresh(rate)
    return envelope(_rate_read(rate))


@router.delete("/exchange-rates/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exchange_rate(
    rate_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Withdraw a rate stated by mistake — only while no journal line cites it."""
    require_permission(actor, "ledger.manage")
    rate = get_scoped_or_404(db, ExchangeRate, actor.tenant_id, rate_id)
    record_audit(db, tenant_id=actor.tenant_id, action="ledger.rate_withdrawn", entity_type="exchange_rate",
                 entity_id=rate.id, actor=actor.label,
                 detail={"pair": f"{rate.from_currency}/{rate.to_currency}", "rate_date": str(rate.rate_date),
                         "rate_type": rate.rate_type, "rate": str(rates.rate_value(rate.rate))})
    db.delete(rate)
    db.flush()  # a cited rate is refused here, by the listener
    db.commit()


@router.get("/fx-revaluation")
def get_fx_revaluation(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    as_of: Annotated[date | None, Query(description="default: today")] = None,
    rate_type: Annotated[str | None, Query(description=(
        "the type of rate to value at (the workspace's rule, usually month_end); looked up on or before as_of"))] = None,
    rates_param: Annotated[str | None, Query(alias="rates", description=(
        "CUR:rate pairs into the functional currency, for rates no table holds: USD:7.82,CNY:1.083"))] = None,
):
    """What each foreign-currency account — per party on a subledger account
    — is worth at `as_of`, against the figure the book holds (which already
    includes earlier revaluations). `difference` > 0: debit the account, a
    gain; < 0: credit it, a loss. A currency with no rate is listed under
    `missing_rates`, never valued at a guess. `revaluation_entry_no` names
    an entry already posted for the account and month (`source_type:
    ledger_account`, `source_event: revalued:YYYY-MM`). Proposes only: the
    agent posts by the workspace's rule."""
    _read(actor)
    stated = rates.parse_rates(rates_param)
    if not rate_type and not stated:
        raise HTTPException(status_code=_422, detail="name a rate_type to look rates up, or state rates=CUR:rate")
    return envelope(rates.revaluation(db, actor.tenant_id, as_of or business_today(), rate_type, stated))
