"""Read endpoints declared as data.

Eighty-three lists and seventy by-id reads were eighty-three and seventy
hand-written handlers — and almost all of them were the same twenty lines:
the same two dependencies, one query parameter per filterable column, the
same call into `list_rows`. The shared TAIL was already one function; the
declaration in front of it was copied. Every cross-cutting change since (date
ranges, reference filters, read visibility) had to be threaded through each
copy or pushed down into the tail to avoid them.

A `ListResource` / `GetResource` says what a handler said — which model, which
filters in which order, which columns a keyword searches, the family's
ordering — and `register` builds the endpoint from it: same URL, same
function name (so the same operationId and summary), same parameters in the
same order, same response model. The OpenAPI document does not change by a
byte, which is the migration's invariant (tests/test_read_registry.py).

What stays hand-written, on purpose: anything with business meaning of its
own — `/detail` reads, reports, matching, and every write. A list whose only
peculiarity is an extra WHERE or a batch-enriched render declares a hook
instead of leaving the registry.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import (
    ORDER_BY_DOC,
    PAGE_SIZE_DOC,
    ListFilters,
    envelope,
    get_scoped_or_404,
    get_tenant_id,
    list_filters,
    list_rows,
    requested_pagination,
    status_scope,
)
from app.db.session import get_db

# parameter names with a fixed meaning; anything else in `params` is an
# equality filter on the column of the same name
KEYWORD, STATUS, PAGE, SIZE, ORDER_BY = "keyword", "status", "page", "size", "order_by"
_STANDARD = {KEYWORD, STATUS, PAGE, SIZE, ORDER_BY}
PAGING = (PAGE, SIZE, ORDER_BY)


@dataclass(frozen=True)
class Filter:
    """An equality filter whose parameter is not simply the column's name, or
    that wants a description in the contract."""

    name: str
    column: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class Param:
    """A query parameter that is NOT an equality filter — a flag, or a value
    the `where` hook interprets (`root_only`, a filter where "" is a value)."""

    name: str
    annotation: Any = str | None
    default: Any = None


@dataclass(frozen=True)
class ListResource:
    path: str
    name: str                       # the endpoint function's name: operationId and summary derive from it
    model: type
    read_model: type | None         # None when `render` builds the rows
    response_model: type | None     # None: the contract states no response model
    params: tuple[str | Filter | Param, ...]  # query parameters, in contract order
    order_by: tuple                 # the family's own ordering (the caller's `order_by=` leads)
    keyword_columns: tuple = ()
    ranges: tuple[str, ...] = ("created_at",)
    equals: tuple[str, ...] = ()    # reference filters appended after the paging parameters
    default_size: int = 50
    options: tuple = ()             # loader options for the read model's relationships
    where: Callable[[Any, dict], Any] | None = None     # hook: (stmt, values) -> stmt
    render: Callable[[Session, str], Callable] | None = None  # hook: (db, tenant_id) -> rows renderer
    doc: str | None = None


@dataclass(frozen=True)
class GetResource:
    path: str
    name: str
    model: type
    read_model: type
    response_model: type | None
    id_param: str
    read: Callable[[Session, str, Any], dict] | None = None  # hook: (db, tenant_id, row) -> the read, when it is enriched
    doc: str | None = None


REGISTRY: list[ListResource | GetResource] = []


def _query_parameter(name: str, annotation, default=None) -> inspect.Parameter:
    return inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=annotation)


def _list_signature(resource: ListResource) -> inspect.Signature:
    parameters = [
        _query_parameter("tenant_id", Annotated[str, Depends(get_tenant_id)], inspect.Parameter.empty),
        _query_parameter("db", Annotated[Session, Depends(get_db)], inspect.Parameter.empty),
    ]
    for param in resource.params:
        if isinstance(param, Param):
            parameters.append(_query_parameter(param.name, param.annotation, param.default))
        elif isinstance(param, Filter):
            annotation = Annotated[str | None, Query(description=param.description)] if param.description else str | None
            parameters.append(_query_parameter(param.name, annotation))
        elif param == STATUS:
            parameters.append(_query_parameter("status_filter", Annotated[str | None, Query(alias="status")]))
        elif param == PAGE:
            parameters.append(_query_parameter(PAGE, Annotated[int | None, Query(ge=1)]))
        elif param == SIZE:
            parameters.append(_query_parameter(SIZE, Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)]))
        elif param == ORDER_BY:
            parameters.append(_query_parameter(ORDER_BY, Annotated[str | None, Query(description=ORDER_BY_DOC)]))
        else:
            parameters.append(_query_parameter(param, str | None))
    parameters.append(_query_parameter(
        "extra",
        Annotated[ListFilters, Depends(list_filters(resource.model, ranges=resource.ranges, equals=resource.equals))],
    ))
    return inspect.Signature(parameters)


def _list_endpoint(resource: ListResource) -> Callable:
    model = resource.model
    equality = [
        (p.name, getattr(model, p.column or p.name)) if isinstance(p, Filter) else (p, getattr(model, p))
        for p in resource.params if not isinstance(p, Param) and (isinstance(p, Filter) or p not in _STANDARD)
    ]
    has_status = STATUS in resource.params

    def endpoint(**values):
        db, tenant_id = values["db"], values["tenant_id"]
        filters = {column: values.get(name) for name, column in equality}
        if has_status:
            filters[model.status] = status_scope(values.get("status_filter"))
        stmt = select(model).options(*resource.options).where(model.tenant_id == tenant_id)
        if resource.where is not None:
            stmt = resource.where(stmt, values)
        return list_rows(
            db, stmt,
            filters=filters,
            keyword=values.get(KEYWORD),
            keyword_columns=resource.keyword_columns,
            order_by=resource.order_by,
            pagination=requested_pagination(values.get(PAGE), values.get(SIZE), default=resource.default_size),
            sort=values.get(ORDER_BY),
            read_model=resource.read_model,
            render=resource.render(db, tenant_id) if resource.render is not None else None,
            extra=values.get("extra"),
        )

    endpoint.__name__ = endpoint.__qualname__ = resource.name
    endpoint.__doc__ = resource.doc
    endpoint.__signature__ = _list_signature(resource)
    return endpoint


def _get_endpoint(resource: GetResource) -> Callable:
    def endpoint(**values):
        db, tenant_id = values["db"], values["tenant_id"]
        row = get_scoped_or_404(db, resource.model, tenant_id, values[resource.id_param])
        if resource.read is not None:
            return envelope(resource.read(db, tenant_id, row))
        return envelope(resource.read_model.model_validate(row).model_dump(by_alias=True))

    endpoint.__name__ = endpoint.__qualname__ = resource.name
    endpoint.__doc__ = resource.doc
    endpoint.__signature__ = inspect.Signature([
        _query_parameter(resource.id_param, str, inspect.Parameter.empty),
        _query_parameter("tenant_id", Annotated[str, Depends(get_tenant_id)], inspect.Parameter.empty),
        _query_parameter("db", Annotated[Session, Depends(get_db)], inspect.Parameter.empty),
    ])
    return endpoint


def register(router: APIRouter, *resources: ListResource | GetResource) -> None:
    """Build and mount one endpoint per declaration."""
    for resource in resources:
        build = _list_endpoint if isinstance(resource, ListResource) else _get_endpoint
        kwargs = {"response_model": resource.response_model, "response_model_exclude_unset": True} if resource.response_model is not None else {}
        router.get(resource.path, **kwargs)(build(resource))
        REGISTRY.append(resource)


__all__ = ["Filter", "GetResource", "ListResource", "Param", "REGISTRY", "register",
           "KEYWORD", "STATUS", "PAGE", "SIZE", "ORDER_BY", "PAGING"]
