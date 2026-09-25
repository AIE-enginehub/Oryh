"""External document links: which Tmall / JD / Amazon / anything-else number
became which document of ours.

Orders and returns usually ARRIVE from somewhere — a marketplace, a small
vendor's site, a mini-program. Recording them here means two translations:
the external ORDER number must land next to our document (this module), and
the external PRODUCT ids must translate into our catalog (the external
product map, curated in master data). The agent recording a channel order
consults the map to translate lines, creates our document, then writes one
link row per (external number, our document) pair.

The link is a transactional claim with a hard-unique tuple, which is what
makes "have we imported TM2026… already?" a reliable dedup query. Splits and
merges are rows, not special cases: one platform order fulfilled as two of
our orders is two rows; three platform orders shipped as one is three.

Authority follows the linked document, not a capability of its own: whoever
may record a sales order may say where it came from, whoever may post stock
movements may name the return parcel a movement belongs to. LINKABLE_DOCUMENTS
is that rule as data — model, capability, and where the scope lives for the
scoped ones. Reads are member-visible like the documents themselves.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import (
    commit_or_conflict,
    envelope,
    get_scoped_or_404,
)
from app.api.registry import ORDER_BY, PAGE, SIZE, GetResource, ListResource, Param, register
from app.api.deps import Actor, attributed, enforce_member_employee, get_actor, require_permission
from app.db.session import get_db
from app.models import (
    BusinessObject,
    ExternalDocumentLink,
    InventoryItemDetail,
    Invoice,
    Payment,
    PurchaseOrder,
    SalesOrder,
)
from app.schemas import (
    CreateExternalDocumentLinkRequest,
    ExternalDocumentLinkEnvelope,
    ExternalDocumentLinkListEnvelope,
    ExternalDocumentLinkRead,
)

router = APIRouter()


# entity_type -> (model, capability, attribute the scope is read from).
# A None scope attribute means the capability is unscoped. business_object is
# scoped by the object's own type, so a tenant-defined 退货单 type is guarded
# exactly as tightly as editing that object would be; invoice by its direction.
LINKABLE_DOCUMENTS: dict[str, tuple[type, str, str | None]] = {
    "sales_order": (SalesOrder, "order.submit_own", None),
    "purchase_order": (PurchaseOrder, "purchase_order.manage", None),
    "invoice": (Invoice, "invoice.manage", "direction"),
    "payment": (Payment, "payment.record", None),
    "business_object": (BusinessObject, "business_object.write", "object_type"),
    "inventory_item_detail": (InventoryItemDetail, "inventory.manage", None),
}


def _load_and_gate(db: Session, actor: Actor, entity_type: str, entity_id: str):
    """Resolve the target document tenant-scoped and require the capability
    that governs writing that document family. Used by create AND delete: a
    link is an annotation on the document, so the right to add or remove one
    is the right to work that document."""
    spec = LINKABLE_DOCUMENTS.get(entity_type)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"entity_type {entity_type!r} is not linkable — one of: "
                + ", ".join(sorted(LINKABLE_DOCUMENTS))
            ),
        )
    model, capability, scope_attr = spec
    row = get_scoped_or_404(db, model, actor.tenant_id, entity_id)
    require_permission(
        actor, capability, getattr(row, scope_attr) if scope_attr else None
    )
    return row


@router.post(
    "/external-document-links",
    response_model=ExternalDocumentLinkEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_external_document_link(
    payload: CreateExternalDocumentLinkRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    target = _load_and_gate(db, actor, payload.entity_type, payload.entity_id)
    if payload.entity_type == "sales_order":
        # a link is written by whoever may work the order — and a seller's
        # credential works its OWN orders (E-30), the same rule the order
        # itself applies
        enforce_member_employee(actor, target.employee_id)
    elsewhere = db.scalars(
        select(ExternalDocumentLink).where(
            ExternalDocumentLink.tenant_id == actor.tenant_id,
            ExternalDocumentLink.source == payload.source,
            ExternalDocumentLink.external_kind == payload.external_kind,
            ExternalDocumentLink.external_no == payload.external_no,
            ExternalDocumentLink.entity_type == payload.entity_type,
            ExternalDocumentLink.entity_id != payload.entity_id,
        )
    ).all()
    if elsewhere and not payload.split:
        # E-02: the number already became one of our documents of this
        # kind; a second one is a duplicate import unless the caller says
        # it is a split
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{payload.source} {payload.external_kind} {payload.external_no} is already "
                f"linked to {payload.entity_type} "
                + ", ".join(sorted({link.entity_id for link in elsewhere}))
                + " — a duplicate import reuses that document; a deliberate split (拆单) "
                "sends split: true"
            ),
        )
    existing = db.scalar(
        select(ExternalDocumentLink).where(
            ExternalDocumentLink.tenant_id == actor.tenant_id,
            ExternalDocumentLink.source == payload.source,
            ExternalDocumentLink.external_kind == payload.external_kind,
            ExternalDocumentLink.external_no == payload.external_no,
            ExternalDocumentLink.entity_type == payload.entity_type,
            ExternalDocumentLink.entity_id == payload.entity_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"link {existing.id} already records {payload.source} "
                f"{payload.external_kind} {payload.external_no} against this document — "
                "recording it twice is a retry, not a new fact"
            ),
        )
    link = ExternalDocumentLink(
        tenant_id=actor.tenant_id,
        source=payload.source,
        external_kind=payload.external_kind,
        external_no=payload.external_no,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        created_by=attributed(actor, None),
        metadata_jsonb=payload.metadata,
    )
    db.add(link)
    commit_or_conflict(db, "this external number is already linked to this document")
    db.refresh(link)
    return envelope(ExternalDocumentLinkRead.model_validate(link).model_dump(by_alias=True))


@router.delete("/external-document-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_external_document_link(
    link_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    link = get_scoped_or_404(db, ExternalDocumentLink, actor.tenant_id, link_id)
    _load_and_gate(db, actor, link.entity_type, link.entity_id)
    db.delete(link)
    db.commit()


# --- reads declared as data (app/api/registry.py) ---------------------------

def _normalised_link_filters(stmt, values: dict):
    """`source` and `external_no` are matched as they are stored: lower-cased
    and stripped, the way the create path writes them."""
    if values.get("source"):
        stmt = stmt.where(ExternalDocumentLink.source == values["source"].strip().lower())
    if values.get("external_no"):
        stmt = stmt.where(ExternalDocumentLink.external_no == values["external_no"].strip())
    return stmt


register(
    router,
    ListResource(
        path="/external-document-links", name="list_external_document_links", model=ExternalDocumentLink,
        read_model=ExternalDocumentLinkRead, response_model=ExternalDocumentLinkListEnvelope,
        params=(Param("source"), "external_kind", Param("external_no"), "entity_type", "entity_id", PAGE, SIZE, ORDER_BY),
        order_by=(ExternalDocumentLink.created_at.desc(), ExternalDocumentLink.id.desc()),
        where=_normalised_link_filters,
    ),
    GetResource(path="/external-document-links/{link_id}", name="get_external_document_link", model=ExternalDocumentLink,
                read_model=ExternalDocumentLinkRead, response_model=ExternalDocumentLinkEnvelope, id_param="link_id"),
)
