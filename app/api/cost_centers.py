"""Cost centres — plan docs/plans/budgets-2026-10-27.md, phase 3.

Master data: where money is spent inside the company, as a tree. Written
with `master_data.manage` like every other master-data table; read by every
member, who picks one on their documents.

An employee carries a home cost centre; an expense claim, purchase request,
purchase order or invoice carries the centre it books against, filled in
when a document names none (`app/services/cost_centers.py`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import String, cast
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import commit_or_conflict, envelope, get_scoped_or_404, require_master_data_manage
from app.api.deps import Actor, get_actor
from app.api.registry import KEYWORD, ORDER_BY, PAGE, SIZE, STATUS, GetResource, ListResource, register
from app.db.session import get_db
from app.models import CostCenter
from app.schemas import (
    CostCenterEnvelope,
    CostCenterListEnvelope,
    CostCenterRead,
    CreateCostCenterRequest,
    UpdateCostCenterRequest,
)
from app.services import cost_centers as _cost_centres  # noqa: F401 — registers the flush rule
from app.services.audit import record_audit

router = APIRouter()


def _check_parent(db: Session, tenant_id: str, parent_id: str | None, current: CostCenter | None = None) -> None:
    """The parent exists, and is not the centre itself or one under it."""
    if not parent_id:
        return
    parent = get_scoped_or_404(db, CostCenter, tenant_id, parent_id)
    if current is None:
        return
    node = parent
    while node is not None:
        if node.id == current.id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="a cost centre cannot sit under itself or under one of its own")
        node = db.get(CostCenter, node.parent_id) if node.parent_id else None


@router.post("/cost-centers", response_model=CostCenterEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_cost_center(
    payload: CreateCostCenterRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_master_data_manage(actor)
    _check_parent(db, tenant_id, payload.parent_id)
    centre = CostCenter(
        tenant_id=tenant_id, cost_center_code=payload.cost_center_code.strip(), name=payload.name,
        parent_id=payload.parent_id, description=payload.description, status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(centre)
    conflict = f"cost_center_code {payload.cost_center_code!r} already exists"
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=conflict)
    record_audit(db, tenant_id=tenant_id, action="cost_center.created", entity_type="cost_center",
                 entity_id=centre.id, actor=actor.label,
                 detail={"cost_center_code": centre.cost_center_code, "name": centre.name})
    commit_or_conflict(db, conflict)
    db.refresh(centre)
    return envelope(CostCenterRead.model_validate(centre).model_dump(by_alias=True))


@router.patch("/cost-centers/{cost_center_id}", response_model=CostCenterEnvelope,
              response_model_exclude_unset=True)
def update_cost_center(
    cost_center_id: str,
    payload: UpdateCostCenterRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Rename, move in the tree, or archive. Archiving keeps every document
    and budget that names the centre; only new assignments are refused."""
    tenant_id = actor.tenant_id
    require_master_data_manage(actor)
    centre = get_scoped_or_404(db, CostCenter, tenant_id, cost_center_id)
    updates = payload.model_dump(exclude_unset=True)
    if "parent_id" in updates:
        _check_parent(db, tenant_id, updates["parent_id"], current=centre)
    if "metadata" in updates:
        centre.metadata_jsonb = updates.pop("metadata") or {}
    for field, value in updates.items():
        setattr(centre, field, value)
    record_audit(db, tenant_id=tenant_id, action="cost_center.updated", entity_type="cost_center",
                 entity_id=centre.id, actor=actor.label,
                 detail={"cost_center_code": centre.cost_center_code, "fields": sorted(updates)})
    db.commit()
    db.refresh(centre)
    return envelope(CostCenterRead.model_validate(centre).model_dump(by_alias=True))


register(
    router,
    ListResource(
        path="/cost-centers", name="list_cost_centers", model=CostCenter, read_model=CostCenterRead,
        response_model=CostCenterListEnvelope,
        params=("parent_id", "cost_center_code", STATUS, KEYWORD, PAGE, SIZE, ORDER_BY),
        order_by=(CostCenter.cost_center_code.asc(), CostCenter.id.asc()),
        keyword_columns=(cast(CostCenter.id, String), CostCenter.cost_center_code, CostCenter.name,
                         CostCenter.description),
    ),
    GetResource(path="/cost-centers/{cost_center_id}", name="get_cost_center", model=CostCenter,
                read_model=CostCenterRead, response_model=CostCenterEnvelope, id_param="cost_center_id"),
)
