"""The envelope, paging, filtering and the scoped fetch every read and write starts from.

Part of app/api/common — see its __init__ for the whole shared core.
"""

from __future__ import annotations

import uuid as uuid_module

from typing import Annotated


from fastapi import Depends, HTTPException, status, Query
from sqlalchemy import Uuid, func, or_, select
from sqlalchemy.orm import Session

import inspect
import uuid
from app.api.deps import (
    has_permission,
)
from app.api.visibility import is_visible, scoped
from dataclasses import (
    dataclass,
    field,
)
from datetime import (
    date,
    datetime,
)
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


MAX_PAGE_SIZE = 200
ORDER_BY_DOC = (
    "Sort order: a column name, `-` prefix for descending, comma-separated for "
    "several (e.g. -created_at,order_no). Any column of the row may be named; an "
    "unknown name answers 422 listing the sortable columns. Omit for the "
    "collection's own order (newest first for documents)."
)

PAGE_SIZE_DOC = (
    "Rows per page, 1–200; larger values are clamped to 200 (meta.page_size says "
    "what was used). Sending page or size turns paging on: the response carries "
    "meta.total, meta.page, meta.page_size. Omit both for the complete list. "
    "To count, send page=1&size=1 and read meta.total."
)


def requested_pagination(
    page: int | None, size: int | None, default: int = 50
) -> tuple[int, int] | None:
    """One paging contract for every list: either parameter opts in.

    Two contracts used to coexist — documents paged on `page` OR `size`,
    master data only on `page`, and `size` was capped by a 422 — and an agent
    that learned one of them lost a round trip on every list that followed the
    other: `size=500` refused, `size=1` without `page` answered with the whole
    table. Now `size` alone pages (page 1), `page` alone pages with the
    family's default size, and an oversize page is clamped rather than
    refused, with `meta.page_size` reporting what was served. Omitting both
    still returns the complete list, which old clients rely on.
    """
    if page is None and size is None:
        return None
    return page or 1, min(size or default, MAX_PAGE_SIZE)


def page_only_pagination(
    page: int | None, size: int | None, default: int = 50
) -> tuple[int, int] | None:
    """The master-data lists' entry point — the same contract as every other
    list now; the name survives so thirty call sites read as before."""
    return requested_pagination(page, size, default)


def sort_clauses(stmt, sort: str | None) -> list:
    """`order_by=-created_at,order_no` → ORDER BY clauses on the statement's
    main entity. Any real column may be named — the console sorts whatever
    column it shows — and an unknown name is a 422 that lists what is
    sortable, so nobody guesses twice. Descending puts NULLs last, ascending
    first, which is what a person reading the column expects."""
    if not sort or not sort.strip():
        return []
    descriptions = stmt.column_descriptions
    entity = descriptions[0].get("entity") if descriptions else None
    table = getattr(entity, "__table__", None)
    if table is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="this collection does not accept order_by",
        )
    clauses = []
    for part in sort.split(","):
        name = part.strip()
        if not name:
            continue
        descending = name.startswith("-")
        name = name.lstrip("-+")
        if name not in table.columns:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"order_by names {name!r}, which is not a column here; sortable: "
                    + ", ".join(sorted(c.key for c in table.columns))
                ),
            )
        column = getattr(entity, name)
        clauses.append(column.desc().nulls_last() if descending else column.asc().nulls_first())
    return clauses


# ---------------------------------------------------------------------------
# Declared list filters: a date range per date column, equality per reference
# and vocabulary column — declared once per list, documented in OpenAPI,
# applied by list_rows.
#
# Every list used to grow its filters by hand, one query parameter at a time,
# and the ones nobody had asked for yet were simply absent: the stock ledger
# could not be read for a week, an invoice list could not be cut by due date,
# a contract list could not be cut by who signed it. A list declares the
# columns it can be cut by; the parameters follow one naming rule —
# `<column>_from` / `<column>_thru` for a range (inclusive both ends, either
# end optional), the column's own name for an equality — so an agent that has
# learned one list has learned them all.


@dataclass
class ListFilters:
    """What the caller asked for, bound to the model's columns."""

    ranges: dict = field(default_factory=dict)   # column -> (from, thru)
    equals: dict = field(default_factory=dict)   # column -> value

    def apply(self, stmt):
        for column, (low, high) in self.ranges.items():
            if low is not None:
                stmt = stmt.where(column >= low)
            if high is not None:
                stmt = stmt.where(column <= high)
        for column, value in self.equals.items():
            if value is None or value == "":
                continue
            if isinstance(column.type, Uuid):
                try:
                    uuid_module.UUID(str(value))
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=f"{column.key} must be a UUID, got {str(value)[:80]!r}",
                    )
            stmt = stmt.where(column == value)
        return stmt


def list_filters(model, *, ranges: tuple[str, ...] = (), equals: tuple[str, ...] = ()):
    """A FastAPI dependency declaring a list's range and equality filters.

    `ranges` names date/datetime columns of `model`; each yields
    `<column>_from` and `<column>_thru` query parameters typed after the
    column (a `date` column takes dates, a `datetime` column takes
    timestamps). `equals` names reference and vocabulary columns; each
    yields a parameter of its own name. The dependency's signature is built
    here so OpenAPI documents every parameter by name — the contract the
    skills are generated from — and list_rows applies what arrived."""
    from sqlalchemy import Date as SaDate, DateTime as SaDateTime

    params: list[inspect.Parameter] = []
    bound: list[tuple[str, str, object]] = []  # (param, kind, column)
    for name in ranges:
        column = getattr(model, name)
        py_type = date if isinstance(column.type, SaDate) else datetime
        noun = "on or after" if py_type is date else "at or after"
        params.append(inspect.Parameter(
            f"{name}_from", inspect.Parameter.KEYWORD_ONLY, default=None,
            annotation=Annotated[py_type | None, Query(description=f"rows whose {name} is {noun} this")],
        ))
        params.append(inspect.Parameter(
            f"{name}_thru", inspect.Parameter.KEYWORD_ONLY, default=None,
            annotation=Annotated[py_type | None, Query(description=f"rows whose {name} is {noun.replace('after', 'before')} this")],
        ))
        bound.append((name, "range", column))
    for name in equals:
        column = getattr(model, name)
        params.append(inspect.Parameter(
            name, inspect.Parameter.KEYWORD_ONLY, default=None,
            annotation=Annotated[str | None, Query()],
        ))
        bound.append((name, "equal", column))

    def dependency(**kwargs) -> ListFilters:
        out = ListFilters()
        for name, kind, column in bound:
            if kind == "range":
                low, high = kwargs.get(f"{name}_from"), kwargs.get(f"{name}_thru")
                if low is not None or high is not None:
                    out.ranges[column] = (low, high)
            else:
                out.equals[column] = kwargs.get(name)
        return out

    dependency.__signature__ = inspect.Signature(params, return_annotation=ListFilters)
    dependency.__name__ = f"list_filters_{model.__name__}"
    return dependency


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
    sort: str | None = None,
    extra: ListFilters | None = None,
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
    # what this actor may read at all comes first (app/api/visibility.py)
    stmt = scoped(db, stmt)
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
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=f"{column.key} must be a UUID, got {str(value)[:80]!r}",
                    )
            stmt = stmt.where(column == value)
    if extra is not None:
        stmt = extra.apply(stmt)
    if keyword:
        # Every word the caller typed must land in some searchable column:
        # "华东 二期" finds "华东医院信息化二期", where a single substring
        # would not. An agent that misses on the first try goes looking —
        # other spellings, the whole list — and the person waits; a query
        # that forgives word order and gaps makes the first try the last.
        for word in keyword.split():
            pattern = f"%{word}%"
            stmt = stmt.where(or_(*(column.ilike(pattern) for column in keyword_columns)))
    if render is None:
        def render(rows):
            return [read_model.model_validate(row).model_dump(by_alias=by_alias) for row in rows]
    # a caller's `order_by=` leads; the family's own order stays as the tiebreak
    ordered = stmt.order_by(*sort_clauses(stmt, sort), *order_by)
    if pagination is None:
        data = render(db.scalars(ordered).all())
        return envelope(data, len(data))
    page, size = pagination
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    data = render(db.scalars(ordered.offset((page - 1) * size).limit(size)).all())
    return paginated_envelope(data, total=total, page=page, page_size=size)


# ---------------------------------------------------------------------------
# The shared document core, moved out of routes.py.
#
# These are the helpers three or more domains call: fetch-and-404, the
# archive/delete/restore/submit verbs, the family registries they read. They
# lived in a 13,008-line module beside the 264 endpoints that use them, so
# every domain extraction would have had to import back into routes.py and
# the dependency graph would have knotted on the second one.
#
# Nothing here calls an endpoint, which is what makes the direction one-way:
# domain modules and routes.py import from common, common imports from
# neither.
# ---------------------------------------------------------------------------

def require_master_data_manage(actor: Actor) -> None:
    """Guard tenant master-data writes.

    ``users.manage`` remains an accepted legacy grant so existing tenant
    administrator roles keep working when this more focused capability ships.
    Service credentials continue to pass through ``has_permission``'s normal
    service-actor bypass.
    """
    if not (
        has_permission(actor, "master_data.manage")
        or has_permission(actor, "users.manage")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requires capability master_data.manage",
        )


def ensure_uuid_or_404(model, entity_id) -> None:
    """A path segment that is not a UUID cannot be a row — postgres would
    refuse the cast and that refusal used to surface as a 500 (a live E2E
    audit: /employees/principals falling into /employees/{id}). Not-a-valid-id
    and no-such-id are the same answer to the caller: 404. Every lookup that
    does not go through `get_scoped_or_404` (the row-locked ones) calls this
    first."""
    try:
        uuid.UUID(str(entity_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")


def get_scoped_or_404(
    db: Session,
    model,
    tenant_id: str,
    entity_id: str,
):
    ensure_uuid_or_404(model, entity_id)
    instance = db.get(model, entity_id)
    if instance is None or instance.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    # A row this actor may not read does not exist for them — the same 404,
    # so the API does not confirm what it will not show.
    if not is_visible(db, instance):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    return instance


@dataclass(frozen=True)
class DocumentFamily:
    """Everything the shared plumbing needs to know about one document
    family. The families behave identically by design — same soft delete,
    same machine-gated line editing, same number allocation — so the
    differences live here as data, not as six copies of the same function."""

    object_type: str            # builtin machine key
    items_phrase: str           # subject of the editable 409
    parent_noun: str            # how the 409 names the parent
    permission: str             # the capability that files this family
    read_model: type
    audit_prefix: str           # "quotation" in quotation.submitted / .status_changed
    audit_identity: object      # doc -> the identifying keys every audit carries
    state_noun: str             # how the create-time 422 names the machine
    advance_permission: str | None = None   # None = filing capability covers advancement
    # doc -> the scope its filing capability is checked with, for families whose
    # verb is scopable (invoice.manage:sales). Without it the shared helpers
    # would check the bare verb and refuse an 应收会计 holding only :sales.
    permission_scope: object | None = None
    owner_checked: bool = True  # personal documents enforce the member-own limit
    attributed_delete: bool = True          # deleted_by / delete_reason columns exist
    editable_hint: str = ""     # family-specific tail of the 409
    number_prefix: str | None = None
    number_field: str | None = None
    lock_scope: str | None = None
    # doc -> the machine key for THIS row, for families whose one table holds
    # more than one lifecycle: `order_kind` splits orders from returns, and a
    # return runs a return's machine (申请→发出→收到→验货入库→退款), not an
    # order's. None = the family's single object_type, which is every other
    # family. Only MACHINE lookups branch on this; entity references, hosted
    # write scopes and audits stay keyed on the table's own object_type,
    # because the row IS a row of that table.
    machine_type_for: object | None = None

    def machine_type(self, document) -> str:
        return self.machine_type_for(document) if self.machine_type_for else self.object_type
