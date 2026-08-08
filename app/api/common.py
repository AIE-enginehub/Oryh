"""Response and pagination plumbing shared by every API module.

One envelope shape for the whole surface: `{"data": …, "meta": …}`, with
pagination meta only when the caller asked for a page. These lived as
verbatim copies in routes.py and workflows.py before being pulled here.
"""

from __future__ import annotations

import uuid as uuid_module

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import Uuid, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import Actor, get_actor


def get_tenant_id(actor: Annotated[Actor, Depends(get_actor)]) -> str:
    return actor.tenant_id


def envelope(data, total: int | None = None) -> dict:
    meta: dict[str, int] = {}
    if total is not None:
        meta["total"] = total
    return {"data": data, "meta": meta}


def paginated_envelope(data, *, total: int, page: int, page_size: int) -> dict:
    return {
        "data": data,
        "meta": {
            "total": total,
            "page": page,
            "page_size": page_size,
            # Keep page=1 a valid, stable empty-state location for the
            # console instead of reporting an unusable zero-page result.
            "pages": max(1, (total + page_size - 1) // page_size),
        },
    }


def requested_pagination(page: int | None, size: int | None) -> tuple[int, int] | None:
    """Keep legacy list semantics unless pagination was explicitly requested.

    Supplying either parameter opts into pagination; the omitted counterpart
    receives the console default. This lets old clients continue to receive the
    complete result set while new clients can use a conventional page/size
    contract.
    """
    if page is None and size is None:
        return None
    return page or 1, size or 50


def page_only_pagination(page: int | None, size: int) -> tuple[int, int] | None:
    """The master-data page contract: only `page` opts into pagination.

    These endpoints shipped `size` with a default before pagination existed,
    so `size` alone cannot opt in — it sizes the page once `page` asks for
    one, and omitting `page` keeps the full-list contract.
    """
    if page is None:
        return None
    return page, size


def list_rows(
    db: Session,
    stmt,
    *,
    filters: dict | None = None,
    keyword: str | None = None,
    keyword_columns: tuple = (),
    order_by: tuple,
    pagination: tuple[int, int] | None,
    read_model: type | None = None,
    by_alias: bool = True,
    render=None,
) -> dict:
    """The one list tail behind every collection endpoint: equality filters,
    a keyword scan across the endpoint's columns, the family's exact ordering,
    and whichever envelope the pagination contract asks for.

    Endpoints keep their explicitly typed query params — they are the OpenAPI
    surface — and pass the pieces here as data. `pagination` arrives computed
    because the opt-in rules differ by family (`requested_pagination` vs
    `page_only_pagination`); `render` is for the few lists whose rows need
    batch enrichment beyond a read model.
    """
    for column, value in (filters or {}).items():
        if value:
            # A non-UUID value against a UUID column is a caller error, not an
            # empty result — postgres refuses the cast and the refusal used to
            # surface as a 500 (a live E2E audit: ?employee_id=gujianguo). Named 422s
            # also answer the agent's actual confusion: these filters take
            # ids, not the natural names skills carry in conversation.
            if isinstance(column.type, Uuid):
                try:
                    uuid_module.UUID(str(value))
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"{column.key} must be a UUID, got {str(value)[:80]!r}",
                    )
            stmt = stmt.where(column == value)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(*(column.ilike(pattern) for column in keyword_columns)))
    if render is None:
        def render(rows):
            return [read_model.model_validate(row).model_dump(by_alias=by_alias) for row in rows]
    ordered = stmt.order_by(*order_by)
    if pagination is None:
        data = render(db.scalars(ordered).all())
        return envelope(data, len(data))
    page, size = pagination
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    data = render(db.scalars(ordered.offset((page - 1) * size).limit(size)).all())
    return paginated_envelope(data, total=total, page=page, page_size=size)
