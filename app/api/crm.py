"""The sales pipeline: leads and opportunities.

Both are personal documents under one approval-free grant — `crm.own` files
AND advances, the booking.own shape: qualification is the salesperson's own
judgment and a deal is won by the customer's signature, neither of which is
a review step. Reads are member-visible like every business document.

A LEAD is somebody who might become a customer, captured before anyone
decides they belong in master data. The one orchestration the server owns
is the conversion bridge (`POST /leads/{id}/convert`): it creates — or
names — the Customer this lead became, carries the lead's person into the
rolodex, optionally opens the Opportunity, and lands the lead in its
machine's `converted` state, anchored by ROLE so a tenant who renames the
state keeps the bridge. Everything else about working a lead — who to call,
when to give up, what counts as qualified — is the agent's judgment, and
the machine records the outcome.

An OPPORTUNITY is a deal being pursued. `expected_amount` is an estimate,
never a price fact — money lives in the quotations and orders the deal
produces. `closed_at` stamps when the machine enters the literal `won` or
`lost` (the shipment convention: renamed states move without stamping, and
the fact is PATCHed by whoever knows it)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import (
    allocate_number,
    apply_status_change,
    delete_document,
    envelope,
    ensure_document_editable,
    get_active_document_or_404,
    get_scoped_or_404,
    get_tenant_id,
    list_rows,
    requested_pagination,
    require_machine_state,
    restore_document,
)
from app.api.deps import Actor, enforce_member_employee, get_actor, require_permission
from app.db.session import get_db
from app.models import Customer, CustomerContact, Employee, Lead, Opportunity
from app.schemas import (
    ConvertLeadRequest,
    CreateLeadRequest,
    CreateOpportunityRequest,
    CustomerContactRead,
    CustomerRead,
    LeadEnvelope,
    LeadListEnvelope,
    LeadRead,
    OpportunityEnvelope,
    OpportunityListEnvelope,
    OpportunityRead,
    UpdateLeadRequest,
    UpdateOpportunityRequest,
)
from app.services.state_machines import (
    get_builtin_machine,
    state_for_role,
    validate_status_filter,
)

router = APIRouter()


# --- leads ------------------------------------------------------------------


@router.get("/leads", response_model=LeadListEnvelope, response_model_exclude_unset=True)
def list_leads(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    source: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    validate_status_filter(db, tenant_id, "lead", status_filter)
    stmt = select(Lead).where(Lead.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(Lead.deleted_at.is_(None))
    return list_rows(
        db, stmt,
        filters={
            Lead.employee_id: employee_id,
            Lead.source: source,
            Lead.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(Lead.id, String),
            Lead.lead_no,
            Lead.company_name,
            Lead.contact_name,
            Lead.phone,
            Lead.email,
            Lead.remarks,
        ),
        order_by=(Lead.created_at.desc(), Lead.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=LeadRead,
    )


@router.post("/leads", response_model=LeadEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: CreateLeadRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "crm.own")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    enforce_member_employee(actor, payload.employee_id)
    initial_status = require_machine_state(db, tenant_id, Lead, payload.status)
    lead_no = payload.lead_no or allocate_number(db, Lead, tenant_id)
    lead = Lead(
        tenant_id=tenant_id,
        lead_no=lead_no,
        company_name=payload.company_name,
        contact_name=payload.contact_name,
        phone=payload.phone,
        wechat=payload.wechat,
        email=payload.email,
        source=payload.source,
        employee_id=payload.employee_id,
        status=initial_status,
        remarks=payload.remarks,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(lead)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"lead_no {lead_no!r} already exists",
        )
    db.refresh(lead)
    return envelope(LeadRead.model_validate(lead).model_dump(by_alias=True))


@router.get("/leads/{lead_id}", response_model=LeadEnvelope, response_model_exclude_unset=True)
def get_lead(
    lead_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    lead = get_active_document_or_404(db, Lead, tenant_id, lead_id)
    return envelope(LeadRead.model_validate(lead).model_dump(by_alias=True))


@router.patch("/leads/{lead_id}", response_model=LeadEnvelope, response_model_exclude_unset=True)
def update_lead(
    lead_id: str,
    payload: UpdateLeadRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "crm.own")
    lead = get_active_document_or_404(db, Lead, actor.tenant_id, lead_id)
    enforce_member_employee(actor, lead.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    status_change = updates.pop("status", None)
    if updates:
        # field edits obey the machine's editable states; a status move does
        # not, so a disqualified lead can revive without its fields thawing
        ensure_document_editable(db, lead)
    if status_change is not None and status_change != lead.status:
        if status_change == state_for_role(
            get_builtin_machine(db, actor.tenant_id, "lead"), "lead", "converted"
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "a lead is converted through POST /leads/{lead_id}/convert — "
                    "the bridge records WHICH customer it became; a bare status "
                    "write would lose that"
                ),
            )
        apply_status_change(db, actor, lead, status_change)
        lead.status = status_change
    if "custom_fields" in updates:
        lead.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(lead, field, value)
    db.commit()
    db.refresh(lead)
    return envelope(LeadRead.model_validate(lead).model_dump(by_alias=True))


@router.delete("/leads/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(
    lead_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return delete_document(db, actor, Lead, lead_id)


@router.post("/leads/{lead_id}/restore")
def restore_lead(
    lead_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, Lead, lead_id)


@router.post("/leads/{lead_id}/convert", response_model_exclude_unset=True)
def convert_lead(
    lead_id: str,
    payload: ConvertLeadRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The one orchestration the server owns: lead → customer (+rolodex
    entry) [+opportunity], one transaction. It exists because the agent
    holding `crm.own` does not hold `master_data.manage` — promotion into
    master data is the conversion's whole meaning, so the bridge carries
    that single write rather than handing the salesperson the catalog."""
    tenant_id = actor.tenant_id
    require_permission(actor, "crm.own")
    lead = get_active_document_or_404(db, Lead, tenant_id, lead_id)
    enforce_member_employee(actor, lead.employee_id)
    if lead.converted_customer_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"already converted — this lead became customer "
                f"{lead.converted_customer_id}"
            ),
        )
    machine = get_builtin_machine(db, tenant_id, "lead")
    converted_state = state_for_role(machine, "lead", "converted")
    # no pre-check of the transition: apply_status_change below validates it,
    # and nothing here commits before that gate fires

    contact = None
    if payload.customer_id is not None:
        customer = get_scoped_or_404(db, Customer, tenant_id, payload.customer_id)
    else:
        customer = Customer(
            tenant_id=tenant_id,
            name=payload.customer_name or lead.company_name or lead.contact_name,
            customer_kind="company" if lead.company_name else None,
            phone=None if lead.contact_name else lead.phone,
        )
        db.add(customer)
        db.flush()
        if lead.contact_name:
            # the person the lead named goes into the rolodex, primary by
            # virtue of being the only one — a brand-new customer, so the
            # phone-dedup invariant cannot collide
            contact = CustomerContact(
                tenant_id=tenant_id,
                customer_id=customer.id,
                name=lead.contact_name,
                phone=lead.phone,
                wechat=lead.wechat,
                email=lead.email,
                is_primary=True,
            )
            db.add(contact)

    opportunity = None
    if payload.opportunity_title is not None:
        opportunity = Opportunity(
            tenant_id=tenant_id,
            opportunity_no=allocate_number(db, Opportunity, tenant_id),
            title=payload.opportunity_title,
            customer_id=customer.id,
            customer_name_snapshot=customer.name,
            lead_id=lead.id,
            employee_id=lead.employee_id,
            expected_amount=payload.expected_amount,
            expected_close_date=payload.expected_close_date,
            status=get_builtin_machine(db, tenant_id, "opportunity")["initial"],
        )
        db.add(opportunity)

    apply_status_change(db, actor, lead, converted_state)
    lead.status = converted_state
    lead.converted_customer_id = customer.id
    db.commit()
    db.refresh(lead)
    data = {
        "lead": LeadRead.model_validate(lead).model_dump(by_alias=True),
        "customer": CustomerRead.model_validate(customer).model_dump(by_alias=True),
    }
    if contact is not None:
        data["contact"] = CustomerContactRead.model_validate(contact).model_dump(by_alias=True)
    if opportunity is not None:
        data["opportunity"] = OpportunityRead.model_validate(opportunity).model_dump(by_alias=True)
    return envelope(data)


# --- opportunities ----------------------------------------------------------


@router.get("/opportunities", response_model=OpportunityListEnvelope,
            response_model_exclude_unset=True)
def list_opportunities(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    customer_id: str | None = None,
    lead_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    validate_status_filter(db, tenant_id, "opportunity", status_filter)
    stmt = select(Opportunity).where(Opportunity.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(Opportunity.deleted_at.is_(None))
    return list_rows(
        db, stmt,
        filters={
            Opportunity.employee_id: employee_id,
            Opportunity.customer_id: customer_id,
            Opportunity.lead_id: lead_id,
            Opportunity.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(Opportunity.id, String),
            Opportunity.opportunity_no,
            Opportunity.title,
            Opportunity.customer_name_snapshot,
            Opportunity.remarks,
        ),
        order_by=(Opportunity.created_at.desc(), Opportunity.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=OpportunityRead,
    )


def _normalize_opportunity_customer(
    db: Session, tenant_id: str, customer_id: str | None, snapshot: str | None
) -> tuple[str | None, str | None]:
    """The quotation's convention: a matched customer backfills the
    snapshot; a snapshot alone is a prospect not yet in master data."""
    if not customer_id:
        return None, snapshot
    customer = get_scoped_or_404(db, Customer, tenant_id, customer_id)
    return customer.id, snapshot or customer.name


@router.post("/opportunities", response_model=OpportunityEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    payload: CreateOpportunityRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "crm.own")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    enforce_member_employee(actor, payload.employee_id)
    initial_status = require_machine_state(db, tenant_id, Opportunity, payload.status)
    customer_id, snapshot = _normalize_opportunity_customer(
        db, tenant_id, payload.customer_id, payload.customer_name_snapshot
    )
    if payload.lead_id:
        get_scoped_or_404(db, Lead, tenant_id, payload.lead_id)
    opportunity_no = payload.opportunity_no or allocate_number(db, Opportunity, tenant_id)
    opportunity = Opportunity(
        tenant_id=tenant_id,
        opportunity_no=opportunity_no,
        title=payload.title,
        customer_id=customer_id,
        customer_name_snapshot=snapshot,
        lead_id=payload.lead_id,
        employee_id=payload.employee_id,
        expected_amount=payload.expected_amount,
        currency=payload.currency,
        expected_close_date=payload.expected_close_date,
        status=initial_status,
        remarks=payload.remarks,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(opportunity)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"opportunity_no {opportunity_no!r} already exists",
        )
    db.refresh(opportunity)
    return envelope(OpportunityRead.model_validate(opportunity).model_dump(by_alias=True))


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityEnvelope,
            response_model_exclude_unset=True)
def get_opportunity(
    opportunity_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    opportunity = get_active_document_or_404(db, Opportunity, tenant_id, opportunity_id)
    return envelope(OpportunityRead.model_validate(opportunity).model_dump(by_alias=True))


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityEnvelope,
              response_model_exclude_unset=True)
def update_opportunity(
    opportunity_id: str,
    payload: UpdateOpportunityRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "crm.own")
    opportunity = get_active_document_or_404(db, Opportunity, tenant_id, opportunity_id)
    enforce_member_employee(actor, opportunity.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    status_change = updates.pop("status", None)
    if updates:
        ensure_document_editable(db, opportunity)
    if "customer_id" in updates or "customer_name_snapshot" in updates:
        customer_id, snapshot = _normalize_opportunity_customer(
            db, tenant_id,
            updates.pop("customer_id", opportunity.customer_id),
            updates.pop("customer_name_snapshot", opportunity.customer_name_snapshot),
        )
        opportunity.customer_id = customer_id
        opportunity.customer_name_snapshot = snapshot
    if "lead_id" in updates and updates["lead_id"] is not None:
        get_scoped_or_404(db, Lead, tenant_id, updates["lead_id"])
    if status_change is not None and status_change != opportunity.status:
        apply_status_change(db, actor, opportunity, status_change)
        opportunity.status = status_change
        # lifecycle timestamps are facts of the transition; literal names
        # only, the shipment convention — renamed states move without
        # stamping and the fact is PATCHed by whoever knows it
        if status_change in ("won", "lost") and opportunity.closed_at is None:
            opportunity.closed_at = datetime.now(timezone.utc)
    if "custom_fields" in updates:
        opportunity.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(opportunity, field, value)
    db.commit()
    db.refresh(opportunity)
    return envelope(OpportunityRead.model_validate(opportunity).model_dump(by_alias=True))


@router.delete("/opportunities/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opportunity(
    opportunity_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return delete_document(db, actor, Opportunity, opportunity_id)


@router.post("/opportunities/{opportunity_id}/restore")
def restore_opportunity(
    opportunity_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, Opportunity, opportunity_id)
