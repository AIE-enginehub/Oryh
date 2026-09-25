"""Whole-document saves: revisions, restating rows, the shared save engine.

Part of app/api/common — see its __init__ for the whole shared core.
"""

from __future__ import annotations




from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy import (
    select,
)
from sqlalchemy.orm import Session

import hashlib
import json
from app.api.deps import (
    require_permission,
)
from app.services.type_options import (
    require_type_option,
)
from dataclasses import (
    field,
)
from datetime import (
    datetime,
    timezone,
)
from app.api.deps import (
    Actor,
)
from app.api.common.core import (
    ensure_uuid_or_404,
    envelope,
)
from app.api.common.charging import (
    _live_lines_of,
    recheck_charged_document,
)
from app.api.common.numbering import (
    ADJUSTMENT_FAMILIES,
)
from app.api.common.documents import (
    DOCUMENT_FAMILIES,
)
from app.api.common.lines import (
    ITEM_FAMILIES,
    _item_write_gate,
    apply_item_updates,
    build_item,
    item_reads,
    record_line_audit,
)
from app.api.common.adjustments import (
    _adjustment_read,
    build_adjustment,
)

# --- whole-document saves --------------------------------------------------------

ADJUSTMENT_MODEL_FOR_PARENT: dict[type, type] = {
    family.parent_model: model for model, family in ADJUSTMENT_FAMILIES.items()
}
ITEM_MODEL_FOR_PARENT: dict[type, type] = {
    family.parent_model: model for model, family in ITEM_FAMILIES.items()
}


def document_revision(db: Session, parent_model, document) -> str:
    """A hash of the header, the live lines and the live adjustments as their
    read models render them — what a whole-document save must present as
    `expected_revision`. Any write through any path (a single-row PATCH, a
    line delete, the header) changes it, so a stale aggregate is refused
    rather than written over."""
    family = DOCUMENT_FAMILIES[parent_model]
    header = family.read_model.model_validate(document).model_dump(mode="json", by_alias=True)
    item_model = ITEM_MODEL_FOR_PARENT[parent_model]
    item_family = ITEM_FAMILIES[item_model]
    lines = [
        item_family.read_model.model_validate(row).model_dump(mode="json", by_alias=True)
        for row in _live_lines_of(db, document.tenant_id, item_model, item_family.parent_field, document.id)
    ]
    adjustments: list = []
    adjustment_model = ADJUSTMENT_MODEL_FOR_PARENT.get(parent_model)
    if adjustment_model is not None:
        adjustment_family = ADJUSTMENT_FAMILIES[adjustment_model]
        adjustments = [
            adjustment_family.read_model.model_validate(row).model_dump(mode="json", by_alias=True)
            for row in _live_lines_of(db, document.tenant_id, adjustment_model, adjustment_family.parent_field, document.id)
        ]
    snapshot = {"header": header, "items": sorted(lines, key=lambda r: r["id"]),
                "adjustments": sorted(adjustments, key=lambda r: r["id"])}
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()


def _line_diff(item, row_values: dict) -> dict:
    """The fields of a restated line that differ from the stored line —
    what the save applies and what the audit names."""
    changed = {}
    for field, value in row_values.items():
        current = item.custom_fields_jsonb if field == "custom_fields" else getattr(item, field, None)
        if isinstance(current, float) or isinstance(value, float):
            try:
                same = current is not None and value is not None and abs(float(current) - float(value)) < 1e-9
            except (TypeError, ValueError):
                same = False
        else:
            same = current == value
        if not same and not (current is None and value in (None, {}, "")):
            changed[field] = value
    return changed


def aggregate_revision(header: dict, **collections: list[dict]) -> str:
    """The revision of a document whose lines are not an `ITEM_FAMILIES`
    member: a hash of the header and every live child collection as their
    read models render them. `document_revision` is the same idea for the
    four registry families; this is the one the rest share."""
    snapshot = {"header": header, **{name: sorted(rows, key=lambda r: r["id"]) for name, rows in collections.items()}}
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()


def require_revision(current: str, expected: str) -> None:
    if current != expected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="the document changed since it was read — GET its /detail and restate against the current revision",
        )


def restate_rows(
    db: Session, actor: Actor, parent_model, document_id: str, rows: list, existing: dict, *,
    build, update, remove, new_model, update_model, label: str = "items", audit=None,
) -> list:
    """One child collection restated as a diff — the engine behind every
    whole-document save that is not `save_document_lines`.

    `rows` is what the collection should be: a row naming a live `id` is that
    line, changed ONLY in the fields the row states (a client that does not
    know about `extracted_fields` does not erase them by not repeating them;
    a field stated as null is cleared); a row without an id is built through
    `build` — the constructor the standalone POST uses; a live line no row
    names is removed through `remove`. Each change writes the audit entry the
    single-row path writes. Never delete-and-reinsert: a line other rows point
    at (a receipt billed by an invoice line, a picked line) keeps its identity.
    """
    named = [row.id for row in rows if row.id]
    if len(named) != len(set(named)) or any(row_id not in existing for row_id in named):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{label}[].id must each be a live row of this document, named once",
        )

    def note(line_id: str, verb: str, changed: dict | None) -> None:
        if audit is not None:
            audit(line_id, verb, changed)
        else:
            record_line_audit(db, actor, parent_model, document_id, line_id, verb,
                              changed=jsonable_encoder(changed) if changed else None)

    def validated(model, values: dict, index: int):
        try:
            return model.model_validate(values)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=[{**error, "loc": ["body", label, index, *error["loc"]]}
                        for error in jsonable_encoder(exc.errors(include_url=False, include_context=False))],
            )

    updatable = set(update_model.model_fields)
    kept: list = []
    for index, row in enumerate(rows):
        if row.id:
            item = existing[row.id]
            stated = {f: getattr(row, f) for f in row.model_fields_set if f != "id"}
            changed = _line_diff(item, stated)
            fixed = sorted(set(changed) - updatable)
            if fixed:
                # the fields the single-row PATCH does not take either: what a
                # line IS (its product, its document) — replace the line instead
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"{label}[{index}]: {', '.join(fixed)} cannot change on an existing row — "
                           "leave the row out and add a new one",
                )
            if changed:
                # the update schema's own constraints (a quantity above zero, a length)
                changed = validated(update_model, changed, index).model_dump(exclude_unset=True)
                update(item, changed)
                note(item.id, "line_changed", changed)
        else:
            item = build(validated(new_model, row.model_dump(exclude_unset=True, exclude={"id"}), index))
            db.flush()
            note(item.id, "line_added", None)
        kept.append(item)
    for row_id, item in existing.items():
        if row_id not in named:
            note(row_id, "line_removed", None)
            remove(item)
    db.flush()
    return kept


def live_rows(db: Session, document, item_model, parent_field: str) -> list:
    stmt = select(item_model).where(item_model.tenant_id == document.tenant_id,
                                    getattr(item_model, parent_field) == document.id)
    if hasattr(item_model, "deleted_at"):
        stmt = stmt.where(item_model.deleted_at.is_(None))
    return list(db.scalars(stmt))


def rows_revision(db: Session, document, header_read, collections: dict) -> str:
    """`collections`: {name: (item_model, parent_field, read_model)}."""
    return aggregate_revision(
        header_read.model_validate(document).model_dump(mode="json", by_alias=True),
        **{name: [read.model_validate(row).model_dump(mode="json", by_alias=True)
                  for row in live_rows(db, document, model, parent_field)]
           for name, (model, parent_field, read) in collections.items()},
    )


def save_rows(
    db: Session, actor: Actor, *, document, parent_model, header_read, spec: tuple, payload, build, update, remove,
    new_model, update_model, validate_only: bool, after=None, audit=None,
) -> dict:
    """The body of a lines-only `/save` once the route has applied the
    document's own gates: lock, revision, diff, the family's after-check,
    read-back. `spec` = (item_model, parent_field, item_read_model)."""
    item_model, parent_field, item_read = spec
    collections = {"items": spec}
    db.refresh(document, with_for_update=True)
    require_revision(rows_revision(db, document, header_read, collections), payload.expected_revision)
    restate_rows(
        db, actor, parent_model, document.id, payload.items,
        {row.id: row for row in live_rows(db, document, item_model, parent_field)},
        build=build, update=update, remove=remove, new_model=new_model, update_model=update_model, audit=audit,
    )
    if after is not None:
        after()

    def read_back() -> dict:
        rows = live_rows(db, document, item_model, parent_field)
        rows.sort(key=lambda r: (getattr(r, "line_no", None) or 0, r.created_at))
        return {"id": document.id, "revision": rows_revision(db, document, header_read, collections),
                "items": [item_read.model_validate(r).model_dump(by_alias=True) for r in rows]}

    return finish_save(db, validate_only, read_back)


def soft_remove(item) -> None:
    item.deleted_at = datetime.now(timezone.utc)


def finish_save(db: Session, validate_only: bool, read_back) -> dict:
    """Commit and answer with the read-back — or, on a dry run, render the
    read-back first and roll everything (audit rows included) back."""
    db.flush()
    if validate_only:
        data = read_back()
        db.rollback()
        return {"data": jsonable_encoder(data), "meta": {"validate_only": True, "written": False}}
    db.commit()
    return {"data": jsonable_encoder(read_back()), "meta": {}}


def save_document_lines(db: Session, actor: Actor, parent_model, document_id: str, payload, *, validate_only: bool = False) -> dict:
    """Restate a document's lines (and adjustments) in one transaction.

    The header is locked, the editable-state and owner gates are the
    single-row paths' gates, `expected_revision` must match what the
    detail last showed, and the change is a diff: ids kept are updated
    through the same rules a PATCH uses, ids absent are removed with the
    same audit a DELETE writes, rows without an id are built through the
    same constructor a POST uses. Never a delete-and-reinsert: lines other
    documents point at (a purchase line pinned to an order line, an
    adjustment on a line) keep their identity."""
    item_model = ITEM_MODEL_FOR_PARENT[parent_model]
    family = ITEM_FAMILIES[item_model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    ensure_uuid_or_404(parent_model, document_id)
    document = db.scalar(
        select(parent_model).where(parent_model.tenant_id == tenant_id, parent_model.id == document_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if document is None or getattr(document, "deleted_at", None) is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{parent_model.__name__} not found")
    _item_write_gate(db, actor, family, document.id)
    if document_revision(db, parent_model, document) != payload.expected_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="the document changed since it was read — GET its /detail and restate against the current revision",
        )
    existing = {row.id: row for row in _live_lines_of(db, tenant_id, item_model, family.parent_field, document.id)}
    named = [row.id for row in payload.items if row.id]
    if len(named) != len(set(named)) or any(row_id not in existing for row_id in named):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="items[].id must each be a live line of this document, named once",
        )
    line_fields = set(type(payload.items[0]).model_fields) - {"id", family.parent_field}
    kept: list = []
    for row in payload.items:
        if row.id:
            item = existing[row.id]
            # only what the row states: a client that does not repeat a field does
            # not erase it (one rule for every /save — see restate_rows)
            changed = _line_diff(item, {f: getattr(row, f) for f in line_fields if f in row.model_fields_set})
            if changed:
                apply_item_updates(db, actor, item_model, item, changed)
            kept.append(item)
        else:
            kept.append(build_item(db, actor, item_model, row, parent=document))
            record_line_audit(db, actor, parent_model, document.id, kept[-1].id, "line_added")
    kept_ids = {row.id for row in kept}
    removed_ids = set(existing) - kept_ids
    adjustment_model = ADJUSTMENT_MODEL_FOR_PARENT.get(parent_model)
    adjustments_out: list = []
    if adjustment_model is not None:
        adjustment_family = ADJUSTMENT_FAMILIES[adjustment_model]
        current = {row.id: row for row in _live_lines_of(db, tenant_id, adjustment_model, adjustment_family.parent_field, document.id)}
        rows = getattr(payload, "adjustments", []) or []
        named_adjustments = [row.id for row in rows if row.id]
        if len(named_adjustments) != len(set(named_adjustments)) or any(a not in current for a in named_adjustments):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="adjustments[].id must each be a live adjustment of this document, named once",
            )
        for index, row in enumerate(rows):
            item_id = None
            if row.item_index is not None:
                if row.item_index >= len(kept):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=f"adjustments[{index}].item_index {row.item_index} names no line of this save",
                    )
                item_id = kept[row.item_index].id
            if row.id:
                adjustment = current[row.id]
                changed = {}
                for field in ("adjustment_type", "description", "amount", "source_percentage"):
                    value = getattr(row, field)
                    if getattr(adjustment, field) != value and not (
                        isinstance(value, float) and getattr(adjustment, field) is not None
                        and abs(float(getattr(adjustment, field)) - value) < 1e-9
                    ):
                        changed[field] = value
                if getattr(adjustment, adjustment_family.item_field) != item_id:
                    changed[adjustment_family.item_field] = item_id
                if (adjustment.metadata_jsonb or {}) != (row.metadata or {}):
                    adjustment.metadata_jsonb = row.metadata
                    changed["metadata"] = row.metadata
                if changed:
                    if "adjustment_type" in changed:
                        require_type_option(db, tenant_id, "sales_adjustment_type", changed["adjustment_type"])
                    for field, value in changed.items():
                        if field != "metadata":
                            setattr(adjustment, field, value)
                    record_line_audit(db, actor, parent_model, document.id, adjustment.id, "adjustment_changed", changed=changed)
                adjustments_out.append(adjustment)
            else:
                adjustments_out.append(build_adjustment(db, actor, adjustment_model, document, row, item_id))
        for adjustment_id, adjustment in current.items():
            if adjustment_id not in {a.id for a in adjustments_out}:
                adjustment.deleted_at = datetime.now(timezone.utc)
                record_line_audit(db, actor, parent_model, document.id, adjustment_id, "adjustment_removed")
    for item_id in removed_ids:
        existing[item_id].deleted_at = datetime.now(timezone.utc)
        record_line_audit(db, actor, parent_model, document.id, item_id, "line_removed")
    recheck_charged_document(db, document, label=parent_model.__tablename__)
    db.flush()
    data = {
        "id": document.id,
        "revision": document_revision(db, parent_model, document),
        "items": item_reads(db, family, kept),
        "adjustments": [
            _adjustment_read(ADJUSTMENT_FAMILIES[adjustment_model], row) for row in adjustments_out
        ] if adjustment_model is not None else [],
    }
    if validate_only:
        db.rollback()
        return {"data": data, "meta": {"validate_only": True, "written": False}}
    db.commit()
    return envelope(data)
