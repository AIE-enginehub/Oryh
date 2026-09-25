"""Routes a document family gets for free, declared as data.

Two shapes recur across the trading modules:

* the LINES of a document — quotation, order, purchase-request and
  purchase-order items, and the adjustments beside them: a list, a create, a
  by-id read, a PATCH and a delete, every one a single call into the family
  machinery in app/api/common.py (`list_items`, `create_item`, …).
  Thirty-five handlers said that in thirty-five copies.
* the VERBS of a document — delete, restore, submit — one call into
  `delete_document` / `restore_document` / `submit_document`, sometimes
  after a family-specific check.

A `LineRoutes` or a `Verb` declaration says what those handlers said: path,
models, the list's query parameters in contract order, the response model,
the docstring, the check that runs first. `register_lines` and
`register_document_verbs` build the endpoints from it — same URL, same
function name (so the same operationId and summary), same parameters in the
same order, same body and response models — so the OpenAPI document does not
change by a byte, the same invariant the read registry keeps
(app/api/registry.py, tests/test_read_registry.py).

What stays hand-written, on purpose: a verb with logic of its own — a
billing account's delete that refuses while a balance stands, the business
object's delete that refuses a posted row.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.common import (
    ORDER_BY_DOC,
    PAGE_SIZE_DOC,
    ListFilters,
    create_adjustment,
    create_item,
    delete_adjustment,
    delete_document,
    delete_item,
    get_adjustment,
    get_item,
    get_tenant_id,
    list_adjustments,
    list_filters,
    list_items,
    requested_pagination,
    restore_document,
    submit_document,
    update_adjustment,
    update_item,
)
from app.api.deps import Actor, get_actor
from app.db.session import get_db

_EMPTY = inspect.Parameter.empty

# every route mounted through this module, as (function name, method, path)
DECLARED: list[tuple[str, str, str]] = []


def _param(name: str, annotation: Any, default: Any = _EMPTY) -> inspect.Parameter:
    return inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=annotation)


def _tenant() -> inspect.Parameter:
    return _param("tenant_id", Annotated[str, Depends(get_tenant_id)])


def _actor() -> inspect.Parameter:
    return _param("actor", Annotated[Actor, Depends(get_actor)])


def _db() -> inspect.Parameter:
    return _param("db", Annotated[Session, Depends(get_db)])


def _named(endpoint: Callable, name: str, doc: str | None, *parameters: inspect.Parameter) -> Callable:
    endpoint.__name__ = endpoint.__qualname__ = name
    endpoint.__doc__ = doc
    endpoint.__signature__ = inspect.Signature(list(parameters))
    return endpoint


def _model_kwargs(envelope: type | None) -> dict:
    return {"response_model": envelope, "response_model_exclude_unset": True} if envelope is not None else {}


# --- lines and adjustments ---------------------------------------------------


@dataclass(frozen=True)
class LineRoutes:
    """One line family's five routes.

    `filters` are the list's equality filters in contract order (the parent
    first); `params` are further query parameters the `where` hook
    interprets. An adjustment family names exactly three filters: the
    parent, the line, the adjustment type."""

    path: str
    model: type
    create_model: type
    update_model: type
    envelope: type | None = None        # None: no response model on the contract (purchase-request items)
    list_envelope: type | None = None
    filters: tuple[str, ...] = ()
    params: tuple[str, ...] = ()
    ranges: tuple[str, ...] = ("created_at",)
    equals: tuple[str, ...] = ()
    paged: bool = True
    kind: str = "item"                  # or "adjustment"
    where: Callable[[dict], list] | None = None   # hook: (values) -> extra WHERE clauses
    doc: str | None = None

    @property
    def plural(self) -> str:
        return self.path.strip("/").replace("-", "_")

    @property
    def singular(self) -> str:
        return self.plural[:-1]

    @property
    def id_param(self) -> str:
        return "item_id" if self.kind == "item" else "adjustment_id"


def _list_lines(spec: LineRoutes) -> Callable:
    def endpoint(**values):
        db, tenant_id = values["db"], values["tenant_id"]
        pagination = requested_pagination(values.get("page"), values.get("size")) if spec.paged else None
        if spec.kind == "adjustment":
            parent, line, kind = spec.filters
            return list_adjustments(
                db, tenant_id, spec.model,
                parent_id=values.get(parent), item_id=values.get(line), adjustment_type=values.get(kind),
                pagination=pagination, sort=values.get("order_by"), extra=values.get("extra"),
            )
        return list_items(
            db, tenant_id, spec.model,
            {name: values.get(name) for name in spec.filters},
            where=spec.where(values) if spec.where is not None else (),
            pagination=pagination, sort=values.get("order_by"), extra=values.get("extra"),
        )

    parameters = [_tenant(), _db()]
    parameters += [_param(name, str | None, None) for name in (*spec.filters, *spec.params)]
    if spec.paged:
        parameters += [
            _param("page", Annotated[int | None, Query(ge=1)], None),
            _param("size", Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)], None),
            _param("order_by", Annotated[str | None, Query(description=ORDER_BY_DOC)], None),
            _param("extra", Annotated[ListFilters, Depends(list_filters(spec.model, ranges=spec.ranges, equals=spec.equals))], None),
        ]
    return _named(endpoint, f"list_{spec.plural}", spec.doc, *parameters)


def _line_verbs(spec: LineRoutes) -> dict[str, Callable]:
    adjustment = spec.kind == "adjustment"
    create, read, update, delete = (
        (create_adjustment, get_adjustment, update_adjustment, delete_adjustment) if adjustment
        else (create_item, get_item, update_item, delete_item)
    )

    def create_endpoint(**v):
        return create(v["db"], v["actor"], spec.model, v["payload"])

    def get_endpoint(**v):
        return read(v["db"], v["tenant_id"], spec.model, v[spec.id_param])

    def update_endpoint(**v):
        return update(v["db"], v["actor"], spec.model, v[spec.id_param], v["payload"])

    def delete_endpoint(**v):
        return delete(v["db"], v["actor"], spec.model, v[spec.id_param])

    return {
        "create": _named(create_endpoint, f"create_{spec.singular}", None,
                         _param("payload", spec.create_model), _actor(), _db()),
        "get": _named(get_endpoint, f"get_{spec.singular}", None,
                      _param(spec.id_param, str), _tenant(), _db()),
        "update": _named(update_endpoint, f"update_{spec.singular}", None,
                         _param(spec.id_param, str), _param("payload", spec.update_model), _actor(), _db()),
        "delete": _named(delete_endpoint, f"delete_{spec.singular}", None,
                         _param(spec.id_param, str), _actor(), _db()),
    }


def register_lines(router: APIRouter, *specs: LineRoutes) -> None:
    """Mount list, create, read, update and delete for each line family."""
    for spec in specs:
        verbs = _line_verbs(spec)
        by_id = f"{spec.path}/{{{spec.id_param}}}"
        router.get(spec.path, **_model_kwargs(spec.list_envelope))(_list_lines(spec))
        router.post(spec.path, status_code=status.HTTP_201_CREATED, **_model_kwargs(spec.envelope))(verbs["create"])
        router.get(by_id, **_model_kwargs(spec.envelope))(verbs["get"])
        router.patch(by_id, **_model_kwargs(spec.envelope))(verbs["update"])
        router.delete(by_id, status_code=status.HTTP_204_NO_CONTENT)(verbs["delete"])
        DECLARED.extend([
            (f"list_{spec.plural}", "get", spec.path), (f"create_{spec.singular}", "post", spec.path),
            (f"get_{spec.singular}", "get", by_id), (f"update_{spec.singular}", "patch", by_id),
            (f"delete_{spec.singular}", "delete", by_id),
        ])


# --- delete, restore, submit -------------------------------------------------


@dataclass(frozen=True)
class Verb:
    """One document verb: its optional body model, its response model, its
    docstring, and the family's own check that runs before the shared act
    (`before(db, actor, document_id)`)."""

    body: type | None = None
    response_model: type | None = None
    doc: str | None = None
    before: Callable[[Session, Actor, str], None] | None = None


def register_document_verbs(
    router: APIRouter,
    model: type,
    *,
    path: str,
    id_param: str,
    singular: str | None = None,
    delete: Verb | None = None,
    restore: Verb | None = None,
    submit: Verb | None = None,
) -> None:
    """Mount the family's delete, restore and submit routes — each the shared
    act from app/api/common.py, after the verb's own check if it has one."""
    noun = singular or path.strip("/").replace("-", "_")[:-1]
    by_id = f"{path}/{{{id_param}}}"

    def mount(verb: Verb, act: Callable, name: str, route: str, **route_kwargs) -> None:
        def endpoint(**v):
            db, actor, document_id = v["db"], v["actor"], v[id_param]
            if verb.before is not None:
                verb.before(db, actor, document_id)
            return act(db, actor, model, document_id, v.get("payload")) if act is delete_document \
                else act(db, actor, model, document_id)

        parameters = [_param(id_param, str), _actor(), _db()]
        if verb.body is not None:
            parameters.append(_param("payload", verb.body, Body(default=None)))
        route(f"{name}_{noun}", **route_kwargs)(_named(endpoint, f"{name}_{noun}", verb.doc, *parameters))
        DECLARED.append((f"{name}_{noun}", "delete" if act is delete_document else "post",
                         by_id if act is delete_document else f"{by_id}/{name}"))

    if delete is not None:
        mount(delete, delete_document, "delete",
              lambda _name, **kw: router.delete(by_id, status_code=status.HTTP_204_NO_CONTENT, **kw))
    if restore is not None:
        mount(restore, restore_document, "restore",
              lambda _name, **kw: router.post(f"{by_id}/restore", **kw), **_model_kwargs(restore.response_model))
    if submit is not None:
        mount(submit, submit_document, "submit",
              lambda _name, **kw: router.post(f"{by_id}/submit", **kw), **_model_kwargs(submit.response_model))


__all__ = ["DECLARED", "LineRoutes", "Verb", "register_document_verbs", "register_lines"]
