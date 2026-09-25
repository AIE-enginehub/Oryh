"""The adjustment families beside the lines.

Part of app/api/common — see its __init__ for the whole shared core.
"""

from __future__ import annotations




from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy import (
    select,
)
from sqlalchemy.orm import Session

from app.api.deps import (
    enforce_member_employee,
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
from fastapi import (
    Response,
)
from app.api.deps import (
    Actor,
)
from app.api.common.core import (
    ListFilters,
    envelope,
    get_scoped_or_404,
    list_rows,
)
from app.api.common.charging import (
    recheck_charged_document,
)
from app.api.common.numbering import (
    ADJUSTMENT_FAMILIES,
    AdjustmentFamily,
)
from app.api.common.documents import (
    ensure_document_editable,
    get_active_document_or_404,
    get_live_or_404,
    require_line_on_document,
)
from app.api.common.lines import (
    record_line_audit,
)

def _adjustment_read(family: AdjustmentFamily, adjustment) -> dict:
    return family.read_model.model_validate(adjustment).model_dump(by_alias=True)


def _adjustment_write_gate(db: Session, actor: Actor, family: AdjustmentFamily, parent_id: str):
    parent = get_active_document_or_404(db, family.parent_model, actor.tenant_id, parent_id)
    ensure_document_editable(db, parent)
    if family.owner_checked:
        enforce_member_employee(actor, parent.employee_id)
    return parent


def list_adjustments(
    db: Session, tenant_id: str, model, *,
    parent_id: str | None, item_id: str | None, adjustment_type: str | None,
    pagination: tuple[int, int] | None = None, sort: str | None = None, extra: ListFilters | None = None,
) -> dict:
    family = ADJUSTMENT_FAMILIES[model]
    stmt = select(model).where(model.tenant_id == tenant_id, model.deleted_at.is_(None))
    return list_rows(
        db, stmt,
        filters={
            getattr(model, family.parent_field): parent_id,
            getattr(model, family.item_field): item_id,
            model.adjustment_type: adjustment_type,
        },
        order_by=(model.created_at.asc(), model.id.asc()),
        pagination=pagination,
        sort=sort,
        render=lambda rows: [_adjustment_read(family, row) for row in rows],
        extra=extra,
    )


def create_adjustment(db: Session, actor: Actor, model, payload) -> dict:
    family = ADJUSTMENT_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    parent_id = getattr(payload, family.parent_field)
    parent = _adjustment_write_gate(db, actor, family, parent_id)
    adjustment = build_adjustment(db, actor, model, parent, payload, getattr(payload, family.item_field))
    recheck_charged_document(db, parent, label=family.parent_model.__tablename__)
    db.commit()
    db.refresh(adjustment)
    return envelope(_adjustment_read(family, adjustment))


def build_adjustment(db: Session, actor: Actor, model, parent, row, item_id: str | None):
    """One validated adjustment, standalone, inline with the document's
    create, or restated by the whole-document save — the same rules on every
    path. The caller has gated the parent."""
    family = ADJUSTMENT_FAMILIES[model]
    tenant_id = actor.tenant_id
    # ONE vocabulary for all three families: an adjustment type is not a
    # direction-specific idea
    require_type_option(db, tenant_id, "sales_adjustment_type", row.adjustment_type)
    if item_id:
        require_line_on_document(
            db, tenant_id, family.item_model, family.parent_field, family.item_field,
            parent.id, item_id,
        )
    adjustment = model(
        tenant_id=tenant_id,
        **{family.parent_field: parent.id, family.item_field: item_id},
        adjustment_type=row.adjustment_type,
        description=row.description,
        amount=row.amount,
        source_percentage=row.source_percentage,
        metadata_jsonb=row.metadata,
    )
    db.add(adjustment)
    db.flush()
    record_line_audit(
        db, actor, family.parent_model, parent.id, adjustment.id, "adjustment_added",
    )
    return adjustment


def inline_adjustments(db: Session, actor: Actor, model, parent, items: list, rows: list) -> list:
    """The adjustments a create states beside its lines: `item_index` names
    a line of the same request, so a line discount and its line are one
    act (gap 6 — bulk import could, the normal path could not)."""
    out = []
    for index, row in enumerate(rows):
        item_id = None
        if row.item_index is not None:
            if row.item_index >= len(items):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"adjustments[{index}].item_index {row.item_index} names no line of this request ({len(items)} lines)",
                )
            item_id = items[row.item_index].id
        out.append(build_adjustment(db, actor, model, parent, row, item_id))
    return out


def get_adjustment(db: Session, tenant_id: str, model, adjustment_id: str) -> dict:
    adjustment = get_live_or_404(db, model, tenant_id, adjustment_id)
    return envelope(_adjustment_read(ADJUSTMENT_FAMILIES[model], adjustment))


def update_adjustment(db: Session, actor: Actor, model, adjustment_id: str, payload) -> dict:
    family = ADJUSTMENT_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    adjustment = get_live_or_404(db, model, tenant_id, adjustment_id)
    parent_id = getattr(adjustment, family.parent_field)
    _adjustment_write_gate(db, actor, family, parent_id)
    updates = payload.model_dump(exclude_unset=True)
    if "adjustment_type" in updates:
        require_type_option(db, tenant_id, "sales_adjustment_type", updates["adjustment_type"])
    if updates.get(family.item_field):
        require_line_on_document(
            db, tenant_id, family.item_model, family.parent_field, family.item_field,
            parent_id, updates[family.item_field],
        )
    if "metadata" in updates:
        adjustment.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(adjustment, field, value)
    record_line_audit(
        db, actor, family.parent_model, parent_id, adjustment.id, "adjustment_changed",
        changed=payload.model_dump(exclude_unset=True),
    )
    parent = db.get(family.parent_model, parent_id)
    if parent is not None:
        recheck_charged_document(db, parent, label=family.parent_model.__tablename__)
    db.commit()
    db.refresh(adjustment)
    return envelope(_adjustment_read(family, adjustment))


def delete_adjustment(db: Session, actor: Actor, model, adjustment_id: str) -> Response:
    family = ADJUSTMENT_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    adjustment = get_scoped_or_404(db, model, tenant_id, adjustment_id)
    if adjustment.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    _adjustment_write_gate(db, actor, family, getattr(adjustment, family.parent_field))
    adjustment.deleted_at = datetime.now(timezone.utc)
    record_line_audit(
        db, actor, family.parent_model, getattr(adjustment, family.parent_field),
        adjustment.id, "adjustment_removed",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
