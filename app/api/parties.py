"""The parties to a deal, a contract or a project, and the relations between
customers (plan 2026-10-14).

A referral deal has three parties and one customer: the friend who signs with
us is the carrier's `customer_id` — the contracting party, derived on every
read and never a row here — and the bus company the system is for and the
friend as the one who brought it are rows (`end_client`, `referrer`). The
rows ride with the deal into the contract and the project the bridges make,
and each carrier then keeps its own.

Customer relations say, from the subject's side, that one customer is the
`relation_type` of another; read from the object's side the type is reversed
by `CUSTOMER_RELATION_REVERSE`. They are master data: `master_data.manage`
writes them and everyone reads. Nothing here computes a commission or routes
a todo — `terms_jsonb` is for the agent that reads a linkage.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import (
    ListFilters,
    ORDER_BY_DOC,
    PAGE_SIZE_DOC,
    DOCUMENT_FAMILIES,
    list_filters,
    commit_or_conflict,
    envelope,
    get_active_document_or_404,
    get_scoped_or_404,
    get_tenant_id,
    list_rows,
    requested_pagination,
    require_family_permission,
    require_master_data_manage,
)
from app.api.deps import Actor, enforce_member_employee, get_actor, has_permission_any_scope, require_permission
from app.core.type_options import CUSTOMER_RELATION_REVERSE
from app.db.session import get_db
from app.models import (
    PARTY_CARRIERS,
    Contract,
    Customer,
    CustomerContact,
    CustomerRelation,
    DocumentParty,
    Opportunity,
    Project,
)
from app.schemas import (
    CreateCustomerRelationRequest,
    CreateDocumentPartyRequest,
    CustomerRelationEnvelope,
    CustomerRelationListEnvelope,
    CustomerRelationRead,
    CustomerRelationSideListEnvelope,
    CustomerRelationSideRead,
    DocumentPartyDetailRead,
    DocumentPartyEnvelope,
    DocumentPartyListEnvelope,
    DocumentPartyRead,
    UpdateCustomerRelationRequest,
    UpdateDocumentPartyRequest,
)
from app.services.audit import record_audit
from app.services.type_options import require_type_option

router = APIRouter()

CARRIER_MODELS = {"opportunity": Opportunity, "contract": Contract, "project": Project}
CONTRACTING = "contracting"


# --- the carriers -----------------------------------------------------------


def carrier_or_404(db: Session, tenant_id: str, entity_type: str, entity_id: str):
    if entity_type not in PARTY_CARRIERS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"entity_type must be one of {', '.join(PARTY_CARRIERS)}")
    model = CARRIER_MODELS[entity_type]
    if entity_type == "project":
        return get_scoped_or_404(db, model, tenant_id, entity_id)
    return get_active_document_or_404(db, model, tenant_id, entity_id)


def require_carrier_read(db: Session, actor: Actor, entity_type: str, entity_id: str):
    """Who may read a carrier's parties is who may read the carrier: anyone
    for a deal or a project, the contract's own side for a contract."""
    carrier = carrier_or_404(db, actor.tenant_id, entity_type, entity_id)
    if entity_type == "contract":
        require_family_permission(actor, DOCUMENT_FAMILIES[Contract], carrier)
    return carrier


def require_carrier_write(db: Session, actor: Actor, entity_type: str, entity_id: str):
    """Who may change a carrier's parties is who may change the carrier: the
    deal's owner (`crm.own`), the contract's side (`contract.manage`), the
    project desk (`project.manage`). The cast may change after the lines
    freeze, and so may the parties — who is in the deal is not its content."""
    carrier = carrier_or_404(db, actor.tenant_id, entity_type, entity_id)
    if entity_type == "opportunity":
        require_permission(actor, "crm.own")
        enforce_member_employee(actor, carrier.employee_id)
    elif entity_type == "contract":
        require_family_permission(actor, DOCUMENT_FAMILIES[Contract], carrier)
    else:
        require_permission(actor, "project.manage")
    return carrier


def _party_detail(db: Session, tenant_id: str, row: DocumentParty, names: dict[str, str]) -> DocumentPartyDetailRead:
    contact_name = None
    if row.contact_id:
        person = db.get(CustomerContact, row.contact_id)
        contact_name = person.name if person is not None else None
    return DocumentPartyDetailRead(
        **DocumentPartyRead.model_validate(row).model_dump(),
        customer_name=names.get(row.customer_id), contact_name=contact_name,
    )


def parties_of(db: Session, tenant_id: str, entity_type: str, entity_id: str, carrier_customer_id: str | None) -> list[DocumentPartyDetailRead]:
    """Every party to a carrier, the contracting one first — derived from the
    carrier's own customer_id, so it can never disagree with it."""
    rows = db.scalars(
        select(DocumentParty).where(
            DocumentParty.tenant_id == tenant_id,
            DocumentParty.entity_type == entity_type,
            DocumentParty.entity_id == entity_id,
        ).order_by(DocumentParty.created_at.asc(), DocumentParty.party_role.asc(), DocumentParty.id.asc())
    ).all()
    ids = {row.customer_id for row in rows}
    if carrier_customer_id:
        ids.add(carrier_customer_id)
    names = dict(db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(ids))).all()) if ids else {}
    out: list[DocumentPartyDetailRead] = []
    if carrier_customer_id:
        out.append(DocumentPartyDetailRead(
            id=None, derived=True, entity_type=entity_type, entity_id=entity_id,
            customer_id=carrier_customer_id, party_role=CONTRACTING, contact_id=None,
            terms_jsonb=None, remarks=None, metadata_jsonb={},
            customer_name=names.get(carrier_customer_id),
            created_at=rows[0].created_at if rows else db.scalar(select(CARRIER_MODELS[entity_type].created_at).where(CARRIER_MODELS[entity_type].id == entity_id)),
            updated_at=rows[0].updated_at if rows else db.scalar(select(CARRIER_MODELS[entity_type].updated_at).where(CARRIER_MODELS[entity_type].id == entity_id)),
        ))
    out.extend(_party_detail(db, tenant_id, row, names) for row in rows)
    return out


def party_customer_ids(db: Session, tenant_id: str, entity_type: str, entity_id: str) -> set[str]:
    return set(db.scalars(select(DocumentParty.customer_id).where(
        DocumentParty.tenant_id == tenant_id,
        DocumentParty.entity_type == entity_type,
        DocumentParty.entity_id == entity_id,
    )))


def copy_parties(db: Session, tenant_id: str, source_type: str, source_id: str, target_type: str, target_id: str) -> int:
    """The parties ride with the deal into the contract and the project the
    bridges make; from then on each carrier keeps its own. Idempotent: a
    row the target already has is left alone."""
    existing = {
        (row.customer_id, row.party_role)
        for row in db.scalars(select(DocumentParty).where(
            DocumentParty.tenant_id == tenant_id,
            DocumentParty.entity_type == target_type,
            DocumentParty.entity_id == target_id,
        ))
    }
    copied = 0
    for row in db.scalars(select(DocumentParty).where(
        DocumentParty.tenant_id == tenant_id,
        DocumentParty.entity_type == source_type,
        DocumentParty.entity_id == source_id,
    )):
        if (row.customer_id, row.party_role) in existing:
            continue
        db.add(DocumentParty(
            tenant_id=tenant_id, entity_type=target_type, entity_id=target_id,
            customer_id=row.customer_id, party_role=row.party_role, contact_id=row.contact_id,
            terms_jsonb=dict(row.terms_jsonb) if row.terms_jsonb else None, remarks=row.remarks,
            metadata_jsonb=dict(row.metadata_jsonb or {}),
        ))
        copied += 1
    return copied


def add_party(db: Session, tenant_id: str, entity_type: str, entity_id: str, *, customer_id: str, party_role: str,
              contact_id: str | None = None, terms: dict | None = None, remarks: str | None = None) -> DocumentParty:
    """One party row, checked: the role is the workspace's, the contact
    belongs to the party, and nobody files the contracting party here."""
    if party_role == CONTRACTING:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="the contracting party is the carrier's customer_id — change it on the deal, contract or project itself",
        )
    require_type_option(db, tenant_id, "deal_party_role", party_role)
    get_scoped_or_404(db, Customer, tenant_id, customer_id)
    if contact_id:
        person = get_scoped_or_404(db, CustomerContact, tenant_id, contact_id)
        if person.customer_id != customer_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="contact_id must be a person of this party's customer")
    row = DocumentParty(
        tenant_id=tenant_id, entity_type=entity_type, entity_id=entity_id, customer_id=customer_id,
        party_role=party_role, contact_id=contact_id, terms_jsonb=terms, remarks=remarks,
    )
    db.add(row)
    return row


# --- document parties -------------------------------------------------------


@router.get("/document-parties", response_model=DocumentPartyListEnvelope, response_model_exclude_unset=True)
def list_document_parties(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    entity_type: str | None = None,
    entity_id: str | None = None,
    customer_id: str | None = None,
    party_role: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(DocumentParty, ranges=("created_at",)))] = None,
):
    """The rows, never the derived contracting party — a carrier's detail
    read shows that one. Naming a carrier reads it first; without one, a
    reader who holds no contract grant sees no contract's parties."""
    tenant_id = actor.tenant_id
    stmt = select(DocumentParty).where(DocumentParty.tenant_id == tenant_id)
    if entity_type is not None and entity_id is not None:
        require_carrier_read(db, actor, entity_type, entity_id)
    elif not has_permission_any_scope(actor, "contract.manage"):
        stmt = stmt.where(DocumentParty.entity_type != "contract")
    return list_rows(
        db, stmt,
        filters={
            DocumentParty.entity_type: entity_type,
            DocumentParty.entity_id: entity_id,
            DocumentParty.customer_id: customer_id,
            DocumentParty.party_role: party_role,
        },
        order_by=(DocumentParty.created_at.asc(), DocumentParty.id.asc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=DocumentPartyRead,
        extra=extra,
    )


@router.post("/document-parties", response_model=DocumentPartyEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_document_party(
    payload: CreateDocumentPartyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    carrier = require_carrier_write(db, actor, payload.entity_type, payload.entity_id)
    row = add_party(
        db, tenant_id, payload.entity_type, carrier.id, customer_id=payload.customer_id,
        party_role=payload.party_role, contact_id=payload.contact_id, terms=payload.terms, remarks=payload.remarks,
    )
    row.metadata_jsonb = payload.metadata
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="that customer already holds that role on this record")
    record_audit(db, tenant_id=tenant_id, action="party.added", entity_type=payload.entity_type, entity_id=carrier.id,
                 actor=actor.label, detail={"customer_id": payload.customer_id, "party_role": payload.party_role})
    commit_or_conflict(db, "that customer already holds that role on this record")
    db.refresh(row)
    return envelope(DocumentPartyRead.model_validate(row).model_dump(by_alias=True))


def _party_or_404(db: Session, tenant_id: str, party_id: str) -> DocumentParty:
    return get_scoped_or_404(db, DocumentParty, tenant_id, party_id)


@router.get("/document-parties/{party_id}", response_model=DocumentPartyEnvelope, response_model_exclude_unset=True)
def get_document_party(
    party_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    row = _party_or_404(db, actor.tenant_id, party_id)
    require_carrier_read(db, actor, row.entity_type, row.entity_id)
    return envelope(DocumentPartyRead.model_validate(row).model_dump(by_alias=True))


@router.patch("/document-parties/{party_id}", response_model=DocumentPartyEnvelope, response_model_exclude_unset=True)
def update_document_party(
    party_id: str,
    payload: UpdateDocumentPartyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    row = _party_or_404(db, tenant_id, party_id)
    require_carrier_write(db, actor, row.entity_type, row.entity_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("party_role") == CONTRACTING:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="the contracting party is the carrier's customer_id — change it on the record itself")
    if "party_role" in updates:
        require_type_option(db, tenant_id, "deal_party_role", updates["party_role"])
    if "customer_id" in updates:
        get_scoped_or_404(db, Customer, tenant_id, updates["customer_id"])
    customer_id = updates.get("customer_id", row.customer_id)
    if updates.get("contact_id"):
        person = get_scoped_or_404(db, CustomerContact, tenant_id, updates["contact_id"])
        if person.customer_id != customer_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="contact_id must be a person of this party's customer")
    if "terms" in updates:
        row.terms_jsonb = updates.pop("terms")
    if "metadata" in updates:
        row.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(row, field, value)
    record_audit(db, tenant_id=tenant_id, action="party.updated", entity_type=row.entity_type, entity_id=row.entity_id,
                 actor=actor.label, detail={"party_id": row.id, "fields": sorted(payload.model_dump(exclude_unset=True))})
    commit_or_conflict(db, "that customer already holds that role on this record")
    db.refresh(row)
    return envelope(DocumentPartyRead.model_validate(row).model_dump(by_alias=True))


@router.delete("/document-parties/{party_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document_party(
    party_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    row = _party_or_404(db, tenant_id, party_id)
    require_carrier_write(db, actor, row.entity_type, row.entity_id)
    record_audit(db, tenant_id=tenant_id, action="party.removed", entity_type=row.entity_type, entity_id=row.entity_id,
                 actor=actor.label, detail={"customer_id": row.customer_id, "party_role": row.party_role})
    db.delete(row)
    db.commit()


# --- customer relations -----------------------------------------------------


def relations_of(db: Session, tenant_id: str, customer_id: str) -> list[CustomerRelationSideRead]:
    """Both directions, each read from this customer's side."""
    rows = db.scalars(
        select(CustomerRelation).where(
            CustomerRelation.tenant_id == tenant_id,
            (CustomerRelation.customer_id == customer_id) | (CustomerRelation.related_customer_id == customer_id),
        ).order_by(CustomerRelation.effective_from.asc().nulls_first(), CustomerRelation.created_at.asc())
    ).all()
    others = {row.related_customer_id if row.customer_id == customer_id else row.customer_id for row in rows}
    names = dict(db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(others))).all()) if others else {}
    out = []
    for row in rows:
        base = CustomerRelationRead.model_validate(row).model_dump()
        if row.customer_id == customer_id:
            other, here, direction = row.related_customer_id, row.relation_type, "subject"
        else:
            other, here, direction = row.customer_id, CUSTOMER_RELATION_REVERSE.get(row.relation_type, row.relation_type), "object"
        out.append(CustomerRelationSideRead(**base, other_customer_id=other, other_customer_name=names.get(other),
                                            relation_type_here=here, direction=direction))
    return out


@router.get("/customers/{customer_id}/relations", response_model=CustomerRelationSideListEnvelope, response_model_exclude_unset=True)
def list_customer_relations_of(
    customer_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    get_scoped_or_404(db, Customer, tenant_id, customer_id)
    rows = relations_of(db, tenant_id, customer_id)
    return {"data": [row.model_dump(by_alias=True) for row in rows],
            "meta": {"total": len(rows), "page": 1, "page_size": max(len(rows), 1), "pages": 1}}


@router.get("/customer-relations", response_model=CustomerRelationListEnvelope, response_model_exclude_unset=True)
def list_customer_relations(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    customer_id: str | None = None,
    related_customer_id: str | None = None,
    relation_type: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
    extra: Annotated[ListFilters, Depends(list_filters(CustomerRelation, ranges=("created_at", "effective_from", "effective_to")))] = None,
):
    """The rows as written, subject's side; `GET /customers/{id}/relations`
    reads both directions from one customer's side."""
    return list_rows(
        db, select(CustomerRelation).where(CustomerRelation.tenant_id == tenant_id),
        filters={
            CustomerRelation.customer_id: customer_id,
            CustomerRelation.related_customer_id: related_customer_id,
            CustomerRelation.relation_type: relation_type,
        },
        order_by=(CustomerRelation.created_at.desc(), CustomerRelation.id.desc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=CustomerRelationRead,
        extra=extra,
    )


def _relation_fields(db: Session, tenant_id: str, updates: dict, current: CustomerRelation | None = None) -> None:
    customer_id = updates.get("customer_id", current.customer_id if current else None)
    related = updates.get("related_customer_id", current.related_customer_id if current else None)
    if customer_id == related:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="a relation needs two different customers")
    for key in ("customer_id", "related_customer_id"):
        if updates.get(key):
            get_scoped_or_404(db, Customer, tenant_id, updates[key])
    if updates.get("relation_type"):
        require_type_option(db, tenant_id, "customer_relation_type", updates["relation_type"])
    f = updates.get("effective_from", current.effective_from if current else None)
    t = updates.get("effective_to", current.effective_to if current else None)
    if f is not None and t is not None and t < f:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="effective_to must not precede effective_from")


@router.post("/customer-relations", response_model=CustomerRelationEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_customer_relation(
    payload: CreateCustomerRelationRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_master_data_manage(actor)
    fields = payload.model_dump(exclude_unset=True)
    _relation_fields(db, tenant_id, fields)
    row = CustomerRelation(
        tenant_id=tenant_id, customer_id=payload.customer_id, related_customer_id=payload.related_customer_id,
        relation_type=payload.relation_type, effective_from=payload.effective_from, effective_to=payload.effective_to,
        remarks=payload.remarks, metadata_jsonb=payload.metadata,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="that relation is already recorded for that date")
    record_audit(db, tenant_id=tenant_id, action="customer.relation_added", entity_type="customer", entity_id=payload.customer_id,
                 actor=actor.label, detail={"related_customer_id": payload.related_customer_id, "relation_type": payload.relation_type})
    commit_or_conflict(db, "that relation is already recorded for that date")
    db.refresh(row)
    return envelope(CustomerRelationRead.model_validate(row).model_dump(by_alias=True))


@router.patch("/customer-relations/{relation_id}", response_model=CustomerRelationEnvelope, response_model_exclude_unset=True)
def update_customer_relation(
    relation_id: str,
    payload: UpdateCustomerRelationRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_master_data_manage(actor)
    row = get_scoped_or_404(db, CustomerRelation, tenant_id, relation_id)
    updates = payload.model_dump(exclude_unset=True)
    _relation_fields(db, tenant_id, updates, current=row)
    if "metadata" in updates:
        row.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(row, field, value)
    record_audit(db, tenant_id=tenant_id, action="customer.relation_updated", entity_type="customer", entity_id=row.customer_id,
                 actor=actor.label, detail={"relation_id": row.id, "fields": sorted(payload.model_dump(exclude_unset=True))})
    commit_or_conflict(db, "that relation is already recorded for that date")
    db.refresh(row)
    return envelope(CustomerRelationRead.model_validate(row).model_dump(by_alias=True))


@router.delete("/customer-relations/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer_relation(
    relation_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_master_data_manage(actor)
    row = get_scoped_or_404(db, CustomerRelation, tenant_id, relation_id)
    record_audit(db, tenant_id=tenant_id, action="customer.relation_removed", entity_type="customer", entity_id=row.customer_id,
                 actor=actor.label, detail={"related_customer_id": row.related_customer_id, "relation_type": row.relation_type})
    db.delete(row)
    db.commit()
