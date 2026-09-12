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
from sqlalchemy import String, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import (
    ORDER_BY_DOC,
    PAGE_SIZE_DOC,
    allocate_number,
    apply_status_change,
    commit_or_conflict,
    delete_document,
    ensure_document_editable,
    envelope,
    get_active_document_or_404,
    get_scoped_or_404,
    get_tenant_id,
    list_rows,
    normalize_customer_context,
    requested_pagination,
    catalog_list_price,
    require_machine_state,
    require_type_option,
    restore_document,
)
from app.api.deps import Actor, enforce_member_employee, get_actor, has_permission, require_permission
from app.db.session import get_db
from app.models import (
    Activity,
    Campaign,
    CampaignMember,
    CommunicationEvent,
    Customer,
    CustomerContact,
    CustomerProduct,
    Employee,
    Event,
    Geo,
    Lead,
    Opportunity,
    OpportunityContact,
    OpportunityItem,
    Product,
    ProductSku,
    SalesOrder,
    SalesQuotation,
    SalesQuotationItem,
)
from app.schemas import (
    CampaignDetailEnvelope,
    CampaignDetailRead,
    CampaignEnvelope,
    CampaignListEnvelope,
    CampaignMemberEnvelope,
    CampaignMemberListEnvelope,
    CampaignMemberRead,
    CampaignRead,
    ConvertLeadRequest,
    CreateCampaignMemberRequest,
    CreateCampaignRequest,
    CreateOpportunityContactRequest,
    CreateOpportunityItemRequest,
    CreateLeadRequest,
    CreateOpportunityRequest,
    CustomerContactRead,
    CustomerRead,
    LeadEnvelope,
    LeadListEnvelope,
    LeadRead,
    ActivityRead,
    CommunicationEventRead,
    EventRead,
    OpportunityContactDetailRead,
    OpportunityContactEnvelope,
    OpportunityContactListEnvelope,
    OpportunityContactRead,
    OpportunityDetailEnvelope,
    OpportunityDetailRead,
    OpportunityEnvelope,
    OpportunityItemEnvelope,
    OpportunityItemListEnvelope,
    OpportunityItemRead,
    OpportunityListEnvelope,
    OpportunityRead,
    QuoteOpportunityRequest,
    SalesOrderRead,
    SalesQuotationItemRead,
    SalesQuotationRead,
    UpdateCampaignMemberRequest,
    UpdateCampaignRequest,
    UpdateOpportunityContactRequest,
    UpdateOpportunityItemRequest,
    UpdateLeadRequest,
    UpdateOpportunityRequest,
)
from app.services.audit import record_audit
from app.services.state_machines import (
    get_builtin_machine,
    state_for_role,
    validate_status_filter,
)
from app.api.geo import customer_territory
from app.services.audit import record_audit

router = APIRouter()


# --- leads ------------------------------------------------------------------


@router.get("/leads", response_model=LeadListEnvelope, response_model_exclude_unset=True)
def list_leads(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    source: str | None = None,
    campaign_id: str | None = None,
    geo_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
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
            Lead.campaign_id: campaign_id,
            Lead.geo_id: geo_id,
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
        sort=order_by,
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
    if payload.campaign_id:
        get_active_document_or_404(db, Campaign, tenant_id, payload.campaign_id)
    if payload.geo_id:
        get_scoped_or_404(db, Geo, tenant_id, payload.geo_id)
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
        campaign_id=payload.campaign_id,
        geo_id=payload.geo_id,
        employee_id=payload.employee_id,
        status=initial_status,
        remarks=payload.remarks,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(lead)
    commit_or_conflict(db, f"lead_no {lead_no!r} already exists")
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
    if updates.get("campaign_id"):
        get_active_document_or_404(db, Campaign, actor.tenant_id, updates["campaign_id"])
    if updates.get("geo_id"):
        get_scoped_or_404(db, Geo, actor.tenant_id, updates["geo_id"])
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


def _customer_for_conversion(db: Session, tenant_id: str, lead: Lead, payload: ConvertLeadRequest) -> tuple[Customer, CustomerContact | None]:
    """The customer the lead becomes: an existing one by id, or a new one
    named from the lead — with the person the lead named as its first
    rolodex entry, primary by virtue of being the only one (a brand-new
    customer, so the phone-dedup invariant cannot collide)."""
    if payload.customer_id is not None:
        customer = get_scoped_or_404(db, Customer, tenant_id, payload.customer_id)
        if not lead.contact_name:
            return customer, None
        # F-03: the lead's person joins the existing customer's rolodex too,
        # unless they are already in it (same phone, or same name with no phone)
        known = db.scalar(select(CustomerContact).where(
            CustomerContact.tenant_id == tenant_id, CustomerContact.customer_id == customer.id,
            (CustomerContact.phone == lead.phone) if lead.phone else (CustomerContact.name == lead.contact_name),
        ))
        if known is not None:
            return customer, known
        has_primary = db.scalar(select(CustomerContact.id).where(
            CustomerContact.tenant_id == tenant_id, CustomerContact.customer_id == customer.id,
            CustomerContact.is_primary.is_(True),
        )) is not None
        contact = CustomerContact(
            tenant_id=tenant_id, customer_id=customer.id, name=lead.contact_name,
            phone=lead.phone, wechat=lead.wechat, email=lead.email, is_primary=not has_primary,
        )
        db.add(contact)
        db.flush()
        return customer, contact
    customer = Customer(
        tenant_id=tenant_id,
        name=payload.customer_name or lead.company_name or lead.contact_name,
        customer_kind="company" if lead.company_name else None,
        phone=None if lead.contact_name else lead.phone,
        # the promotion carries where the lead is, who owns it, and the
        # territory that covers the place when exactly one does
        geo_id=lead.geo_id,
        territory_id=customer_territory(db, tenant_id, lead.geo_id, None),
        owner_employee_id=lead.employee_id,
    )
    db.add(customer)
    db.flush()
    if not lead.contact_name:
        return customer, None
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
    return customer, contact


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

    customer, contact = _customer_for_conversion(db, tenant_id, lead, payload)

    opportunity = None
    if payload.opportunity_title is not None:
        opportunity = Opportunity(
            tenant_id=tenant_id,
            opportunity_no=allocate_number(db, Opportunity, tenant_id),
            title=payload.opportunity_title,
            customer_id=customer.id,
            customer_name_snapshot=customer.name,
            lead_id=lead.id,
            campaign_id=lead.campaign_id,
            source=lead.source,
            employee_id=lead.employee_id,
            expected_amount=payload.expected_amount,
            expected_close_date=payload.expected_close_date,
            status=get_builtin_machine(db, tenant_id, "opportunity")["initial"],
        )
        db.add(opportunity)
        db.flush()

    apply_status_change(db, actor, lead, converted_state)
    lead.status = converted_state
    lead.converted_customer_id = customer.id
    # F-15: what was said, scheduled and mailed while this was a lead is the
    # customer's history from now on — and the deal's, when one was opened.
    # The lead keeps its own link; the customer and deal gain theirs.
    for model in (Activity, Event, CommunicationEvent):
        for row in db.scalars(select(model).where(model.tenant_id == tenant_id, model.lead_id == lead.id)):
            if row.customer_id is None:
                row.customer_id = customer.id
            if opportunity is not None and row.opportunity_id is None:
                row.opportunity_id = opportunity.id
            if contact is not None and getattr(row, "contact_id", None) is None and hasattr(row, "contact_id"):
                row.contact_id = contact.id
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
    campaign_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
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
            Opportunity.campaign_id: campaign_id,
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
        sort=order_by,
        read_model=OpportunityRead,
    )


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
    customer_id, snapshot = normalize_customer_context(
        db, tenant_id, payload.customer_id, payload.customer_name_snapshot
    )
    if payload.lead_id:
        get_scoped_or_404(db, Lead, tenant_id, payload.lead_id)
    if payload.campaign_id:
        get_active_document_or_404(db, Campaign, tenant_id, payload.campaign_id)
    if payload.lost_reason:
        require_type_option(db, tenant_id, "opportunity_lost_reason", payload.lost_reason)
    opportunity_no = payload.opportunity_no or allocate_number(db, Opportunity, tenant_id)
    opportunity = Opportunity(
        tenant_id=tenant_id,
        opportunity_no=opportunity_no,
        title=payload.title,
        customer_id=customer_id,
        customer_name_snapshot=snapshot,
        lead_id=payload.lead_id,
        campaign_id=payload.campaign_id,
        probability=payload.probability,
        lost_reason=payload.lost_reason,
        competitor=payload.competitor,
        source=payload.source,
        employee_id=payload.employee_id,
        expected_amount=payload.expected_amount,
        currency=payload.currency,
        expected_close_date=payload.expected_close_date,
        status=initial_status,
        remarks=payload.remarks,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(opportunity)
    commit_or_conflict(db, f"opportunity_no {opportunity_no!r} already exists")
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
        customer_id, snapshot = normalize_customer_context(
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
    if updates.get("campaign_id"):
        get_active_document_or_404(db, Campaign, actor.tenant_id, updates["campaign_id"])
    if updates.get("lost_reason"):
        require_type_option(db, tenant_id, "opportunity_lost_reason", updates["lost_reason"])
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


# --- campaigns ----------------------------------------------------------------


def _campaign_write(actor: Actor) -> None:
    require_permission(actor, "campaign.manage")


@router.get("/campaigns", response_model=CampaignListEnvelope, response_model_exclude_unset=True)
def list_campaigns(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    campaign_type: str | None = None,
    parent_campaign_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    validate_status_filter(db, tenant_id, "campaign", status_filter)
    stmt = select(Campaign).where(Campaign.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(Campaign.deleted_at.is_(None))
    return list_rows(
        db, stmt,
        filters={
            Campaign.employee_id: employee_id,
            Campaign.campaign_type: campaign_type,
            Campaign.parent_campaign_id: parent_campaign_id,
            Campaign.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(Campaign.id, String),
            Campaign.campaign_no,
            Campaign.name,
            Campaign.description,
            Campaign.remarks,
        ),
        order_by=(Campaign.start_date.desc().nulls_last(), Campaign.created_at.desc(), Campaign.id.desc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=CampaignRead,
    )


def _campaign_fields(db: Session, tenant_id: str, payload, *, current: Campaign | None = None) -> None:
    """The checks a create and an update share: the type is one of the
    tenant's, the parent exists and is not the campaign itself, the dates
    are in order."""
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("campaign_type"):
        require_type_option(db, tenant_id, "campaign_type", fields["campaign_type"])
    if fields.get("parent_campaign_id"):
        if current is not None and fields["parent_campaign_id"] == current.id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="a campaign cannot be its own parent")
        get_active_document_or_404(db, Campaign, tenant_id, fields["parent_campaign_id"])
    start = fields.get("start_date", current.start_date if current else None)
    end = fields.get("end_date", current.end_date if current else None)
    if start and end and end < start:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="end_date is before start_date")


@router.post("/campaigns", response_model=CampaignEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CreateCampaignRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    _campaign_write(actor)
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    _campaign_fields(db, tenant_id, payload)
    initial_status = require_machine_state(db, tenant_id, Campaign, payload.status)
    campaign_no = payload.campaign_no or allocate_number(db, Campaign, tenant_id)
    campaign = Campaign(
        tenant_id=tenant_id,
        campaign_no=campaign_no,
        name=payload.name,
        campaign_type=payload.campaign_type,
        parent_campaign_id=payload.parent_campaign_id,
        employee_id=payload.employee_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        budget=payload.budget,
        actual_cost=payload.actual_cost,
        expected_revenue=payload.expected_revenue,
        currency=payload.currency,
        status=initial_status,
        description=payload.description,
        remarks=payload.remarks,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(campaign)
    db.flush()
    record_audit(
        db,
        tenant_id=tenant_id,
        action="campaign.created",
        entity_type="campaign",
        entity_id=campaign.id,
        actor=actor.label,
        detail={"campaign_no": campaign.campaign_no, "name": campaign.name,
                "campaign_type": campaign.campaign_type, "employee_id": campaign.employee_id},
    )
    commit_or_conflict(db, f"campaign_no {campaign_no!r} already exists")
    db.refresh(campaign)
    return envelope(CampaignRead.model_validate(campaign).model_dump(by_alias=True))


@router.get("/campaigns/{campaign_id}", response_model=CampaignEnvelope, response_model_exclude_unset=True)
def get_campaign(
    campaign_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    campaign = get_active_document_or_404(db, Campaign, tenant_id, campaign_id)
    return envelope(CampaignRead.model_validate(campaign).model_dump(by_alias=True))


@router.get("/campaigns/{campaign_id}/detail", response_model=CampaignDetailEnvelope,
            response_model_exclude_unset=True)
def get_campaign_detail(
    campaign_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """What the campaign produced, counted live: members by status, the
    leads that name it and how many converted, the deals that name it and
    how many were won. `won_expected_amount` is the sum of the won deals'
    estimates — an indication, not revenue; revenue is in the orders."""
    campaign = get_active_document_or_404(db, Campaign, tenant_id, campaign_id)
    by_status = {
        row[0]: int(row[1])
        for row in db.execute(
            select(CampaignMember.member_status, func.count())
            .where(CampaignMember.tenant_id == tenant_id, CampaignMember.campaign_id == campaign.id)
            .group_by(CampaignMember.member_status)
        )
    }
    live_leads = select(Lead).where(
        Lead.tenant_id == tenant_id, Lead.campaign_id == campaign.id, Lead.deleted_at.is_(None)
    )
    leads_total = db.scalar(select(func.count()).select_from(live_leads.subquery())) or 0
    leads_converted = db.scalar(
        select(func.count()).select_from(
            live_leads.where(Lead.converted_customer_id.is_not(None)).subquery()
        )
    ) or 0
    live_deals = select(Opportunity).where(
        Opportunity.tenant_id == tenant_id, Opportunity.campaign_id == campaign.id,
        Opportunity.deleted_at.is_(None),
    )
    deals_total = db.scalar(select(func.count()).select_from(live_deals.subquery())) or 0
    won = live_deals.where(Opportunity.status == "won").subquery()
    deals_won = db.scalar(select(func.count()).select_from(won)) or 0
    won_amount = db.scalar(select(func.coalesce(func.sum(won.c.expected_amount), 0))) or 0
    detail = CampaignDetailRead(
        campaign=CampaignRead.model_validate(campaign),
        members_total=sum(by_status.values()),
        members_by_status=by_status,
        leads_total=int(leads_total),
        leads_converted=int(leads_converted),
        opportunities_total=int(deals_total),
        opportunities_won=int(deals_won),
        won_expected_amount=float(won_amount),
    )
    return envelope(detail.model_dump(by_alias=True))


@router.patch("/campaigns/{campaign_id}", response_model=CampaignEnvelope, response_model_exclude_unset=True)
def update_campaign(
    campaign_id: str,
    payload: UpdateCampaignRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    _campaign_write(actor)
    campaign = get_active_document_or_404(db, Campaign, tenant_id, campaign_id)
    updates = payload.model_dump(exclude_unset=True)
    status_change = updates.pop("status", None)
    if updates:
        ensure_document_editable(db, campaign)
        _campaign_fields(db, tenant_id, payload, current=campaign)
        if updates.get("employee_id"):
            get_scoped_or_404(db, Employee, tenant_id, updates["employee_id"])
    if status_change is not None and status_change != campaign.status:
        apply_status_change(db, actor, campaign, status_change)
        campaign.status = status_change
    if "custom_fields" in updates:
        campaign.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(campaign, field, value)
    db.commit()
    db.refresh(campaign)
    return envelope(CampaignRead.model_validate(campaign).model_dump(by_alias=True))


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(
    campaign_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return delete_document(db, actor, Campaign, campaign_id)


@router.post("/campaigns/{campaign_id}/restore")
def restore_campaign(
    campaign_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, Campaign, campaign_id)


# --- campaign members --------------------------------------------------------


def _member_write(db: Session, actor: Actor, *, lead_id: str | None) -> None:
    """Marketing curates the list; a salesperson may also put THEIR OWN lead
    on a campaign (they are the one who knows where it came from)."""
    if has_permission(actor, "campaign.manage"):
        return
    if lead_id and has_permission(actor, "crm.own"):
        lead = get_active_document_or_404(db, Lead, actor.tenant_id, lead_id)
        enforce_member_employee(actor, lead.employee_id)
        return
    require_permission(actor, "campaign.manage")


@router.get("/campaign-members", response_model=CampaignMemberListEnvelope,
            response_model_exclude_unset=True)
def list_campaign_members(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    campaign_id: str | None = None,
    lead_id: str | None = None,
    customer_id: str | None = None,
    contact_id: str | None = None,
    member_status: str | None = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    stmt = select(CampaignMember).where(CampaignMember.tenant_id == tenant_id)
    return list_rows(
        db, stmt,
        filters={
            CampaignMember.campaign_id: campaign_id,
            CampaignMember.lead_id: lead_id,
            CampaignMember.customer_id: customer_id,
            CampaignMember.contact_id: contact_id,
            CampaignMember.member_status: member_status,
        },
        keyword=keyword,
        keyword_columns=(cast(CampaignMember.id, String), CampaignMember.remarks),
        order_by=(CampaignMember.created_at.desc(), CampaignMember.id.desc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=CampaignMemberRead,
    )


@router.post("/campaign-members", response_model=CampaignMemberEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_campaign_member(
    payload: CreateCampaignMemberRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    _member_write(db, actor, lead_id=payload.lead_id)
    get_active_document_or_404(db, Campaign, tenant_id, payload.campaign_id)
    if payload.lead_id:
        get_active_document_or_404(db, Lead, tenant_id, payload.lead_id)
    if payload.customer_id:
        get_scoped_or_404(db, Customer, tenant_id, payload.customer_id)
    if payload.contact_id:
        contact = get_scoped_or_404(db, CustomerContact, tenant_id, payload.contact_id)
        if contact.customer_id != payload.customer_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="contact_id belongs to a different customer")
    if payload.member_status:
        require_type_option(db, tenant_id, "campaign_member_status", payload.member_status)
    member = CampaignMember(
        tenant_id=tenant_id,
        campaign_id=payload.campaign_id,
        lead_id=payload.lead_id,
        customer_id=payload.customer_id,
        contact_id=payload.contact_id,
        member_status=payload.member_status or "targeted",
        responded_at=payload.responded_at,
        remarks=payload.remarks,
        metadata_jsonb=payload.metadata_jsonb,
    )
    db.add(member)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="this party is already a member of the campaign")
    record_audit(
        db,
        tenant_id=tenant_id,
        action="campaign.member_added",
        entity_type="campaign",
        entity_id=member.campaign_id,
        actor=actor.label,
        detail={"member_id": member.id, "lead_id": member.lead_id, "customer_id": member.customer_id,
                "contact_id": member.contact_id, "member_status": member.member_status},
    )
    commit_or_conflict(db, "this party is already a member of the campaign")
    db.refresh(member)
    return envelope(CampaignMemberRead.model_validate(member).model_dump(by_alias=True))


@router.get("/campaign-members/{member_id}", response_model=CampaignMemberEnvelope,
            response_model_exclude_unset=True)
def get_campaign_member(
    member_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    member = get_scoped_or_404(db, CampaignMember, tenant_id, member_id)
    return envelope(CampaignMemberRead.model_validate(member).model_dump(by_alias=True))


@router.patch("/campaign-members/{member_id}", response_model=CampaignMemberEnvelope,
              response_model_exclude_unset=True)
def update_campaign_member(
    member_id: str,
    payload: UpdateCampaignMemberRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    member = get_scoped_or_404(db, CampaignMember, tenant_id, member_id)
    _member_write(db, actor, lead_id=member.lead_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("member_status"):
        require_type_option(db, tenant_id, "campaign_member_status", updates["member_status"])
    if updates.get("contact_id"):
        if not member.customer_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="a lead member has no customer contacts")
        contact = get_scoped_or_404(db, CustomerContact, tenant_id, updates["contact_id"])
        if contact.customer_id != member.customer_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="contact_id belongs to a different customer")
    for field, value in updates.items():
        setattr(member, field, value)
    record_audit(
        db,
        tenant_id=tenant_id,
        action="campaign.member_updated",
        entity_type="campaign",
        entity_id=member.campaign_id,
        actor=actor.label,
        detail={"member_id": member.id, **{k: v for k, v in updates.items() if k != "metadata_jsonb"}},
    )
    commit_or_conflict(db, "this party is already a member of the campaign")
    db.refresh(member)
    return envelope(CampaignMemberRead.model_validate(member).model_dump(by_alias=True))


@router.delete("/campaign-members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign_member(
    member_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    member = get_scoped_or_404(db, CampaignMember, actor.tenant_id, member_id)
    _member_write(db, actor, lead_id=member.lead_id)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="campaign.member_removed",
        entity_type="campaign",
        entity_id=member.campaign_id,
        actor=actor.label,
        detail={"member_id": member.id, "lead_id": member.lead_id, "customer_id": member.customer_id,
                "contact_id": member.contact_id},
    )
    db.delete(member)
    db.commit()


# --- opportunity lines, cast, detail, and the quote bridge -----------------


def _own_opportunity(db: Session, actor: Actor, opportunity_id: str, *, editable: bool = True) -> Opportunity:
    """A deal's lines and cast are the deal's owner's to write, while the
    deal is still editable — the same rule the deal's own fields obey."""
    require_permission(actor, "crm.own")
    opportunity = get_active_document_or_404(db, Opportunity, actor.tenant_id, opportunity_id)
    enforce_member_employee(actor, opportunity.employee_id)
    if editable:
        ensure_document_editable(db, opportunity)
    return opportunity


def _line_product(db: Session, tenant_id: str, product_id: str | None, sku_id: str | None) -> None:
    if product_id:
        get_scoped_or_404(db, Product, tenant_id, product_id)
    if sku_id:
        sku = get_scoped_or_404(db, ProductSku, tenant_id, sku_id)
        if product_id and sku.product_id != product_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="sku_id belongs to a different product")


@router.get("/opportunity-items", response_model=OpportunityItemListEnvelope, response_model_exclude_unset=True)
def list_opportunity_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    opportunity_id: str | None = None,
    product_id: str | None = None,
    sku_id: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    stmt = select(OpportunityItem).where(OpportunityItem.tenant_id == tenant_id)
    return list_rows(
        db, stmt,
        filters={
            OpportunityItem.opportunity_id: opportunity_id,
            OpportunityItem.product_id: product_id,
            OpportunityItem.sku_id: sku_id,
        },
        order_by=(OpportunityItem.line_no.asc().nulls_last(), OpportunityItem.created_at.asc(), OpportunityItem.id.asc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=OpportunityItemRead,
    )


@router.post("/opportunity-items", response_model=OpportunityItemEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_opportunity_item(
    payload: CreateOpportunityItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    opportunity = _own_opportunity(db, actor, payload.opportunity_id)
    _line_product(db, tenant_id, payload.product_id, payload.sku_id)
    name_snapshot = payload.product_name_snapshot
    if payload.product_id and not name_snapshot:
        # F-07: the catalog's name rides the line so the quotation it becomes
        # prints a product, not a blank
        name_snapshot = db.get(Product, payload.product_id).name
    item = OpportunityItem(
        tenant_id=tenant_id,
        opportunity_id=opportunity.id,
        line_no=payload.line_no,
        product_id=payload.product_id,
        sku_id=payload.sku_id,
        product_name_snapshot=name_snapshot,
        spec=payload.spec,
        quantity=payload.quantity,
        unit=payload.unit,
        unit_price=payload.unit_price,
        amount=payload.amount if payload.amount is not None
        else (round(payload.quantity * payload.unit_price, 2) if payload.unit_price is not None else None),
        notes=payload.notes,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(item)
    record_audit(db, tenant_id=tenant_id, action="opportunity.item_added", entity_type="opportunity",
                 entity_id=opportunity.id, actor=actor.label,
                 detail={"opportunity_no": opportunity.opportunity_no, "product_id": payload.product_id,
                         "quantity": payload.quantity})
    db.commit()
    db.refresh(item)
    return envelope(OpportunityItemRead.model_validate(item).model_dump(by_alias=True))


@router.get("/opportunity-items/{item_id}", response_model=OpportunityItemEnvelope, response_model_exclude_unset=True)
def get_opportunity_item(
    item_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    item = get_scoped_or_404(db, OpportunityItem, tenant_id, item_id)
    return envelope(OpportunityItemRead.model_validate(item).model_dump(by_alias=True))


@router.patch("/opportunity-items/{item_id}", response_model=OpportunityItemEnvelope, response_model_exclude_unset=True)
def update_opportunity_item(
    item_id: str,
    payload: UpdateOpportunityItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    item = get_scoped_or_404(db, OpportunityItem, tenant_id, item_id)
    opportunity = _own_opportunity(db, actor, item.opportunity_id)
    updates = payload.model_dump(exclude_unset=True)
    _line_product(db, tenant_id, updates.get("product_id", item.product_id), updates.get("sku_id", item.sku_id))
    if "custom_fields" in updates:
        item.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(item, field, value)
    if not (item.product_id or (item.product_name_snapshot or "").strip()):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="a line names a product — by id, or by name when the catalog has none")
    if "amount" not in updates and item.unit_price is not None:
        item.amount = round(float(item.quantity) * float(item.unit_price), 2)
    record_audit(db, tenant_id=tenant_id, action="opportunity.item_changed", entity_type="opportunity",
                 entity_id=opportunity.id, actor=actor.label,
                 detail={"opportunity_no": opportunity.opportunity_no, "item_id": item.id, "fields": sorted(updates)})
    db.commit()
    db.refresh(item)
    return envelope(OpportunityItemRead.model_validate(item).model_dump(by_alias=True))


@router.delete("/opportunity-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opportunity_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    item = get_scoped_or_404(db, OpportunityItem, actor.tenant_id, item_id)
    opportunity = _own_opportunity(db, actor, item.opportunity_id)
    record_audit(db, tenant_id=actor.tenant_id, action="opportunity.item_removed", entity_type="opportunity",
                 entity_id=opportunity.id, actor=actor.label,
                 detail={"opportunity_no": opportunity.opportunity_no, "item_id": item.id})
    db.delete(item)
    db.commit()


def _contact_of_deal(db: Session, tenant_id: str, opportunity: Opportunity, contact_id: str) -> CustomerContact:
    contact = get_scoped_or_404(db, CustomerContact, tenant_id, contact_id)
    if opportunity.customer_id and contact.customer_id != opportunity.customer_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="that person belongs to a different customer than this deal")
    return contact


def _demote_other_primaries(db: Session, tenant_id: str, opportunity_id: str, keep: str | None) -> None:
    for row in db.scalars(select(OpportunityContact).where(
        OpportunityContact.tenant_id == tenant_id,
        OpportunityContact.opportunity_id == opportunity_id,
        OpportunityContact.is_primary.is_(True),
    )):
        if row.id != keep:
            row.is_primary = False


@router.get("/opportunity-contacts", response_model=OpportunityContactListEnvelope, response_model_exclude_unset=True)
def list_opportunity_contacts(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    opportunity_id: str | None = None,
    contact_id: str | None = None,
    role: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    stmt = select(OpportunityContact).where(OpportunityContact.tenant_id == tenant_id)
    return list_rows(
        db, stmt,
        filters={
            OpportunityContact.opportunity_id: opportunity_id,
            OpportunityContact.contact_id: contact_id,
            OpportunityContact.role: role,
        },
        order_by=(OpportunityContact.is_primary.desc(), OpportunityContact.created_at.asc(), OpportunityContact.id.asc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=OpportunityContactRead,
    )


@router.post("/opportunity-contacts", response_model=OpportunityContactEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_opportunity_contact(
    payload: CreateOpportunityContactRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    # the cast may change after the lines freeze: who decides is a fact
    # about the customer, not about the deal's content
    opportunity = _own_opportunity(db, actor, payload.opportunity_id, editable=False)
    _contact_of_deal(db, tenant_id, opportunity, payload.contact_id)
    if payload.role:
        require_type_option(db, tenant_id, "opportunity_contact_role", payload.role)
    row = OpportunityContact(
        tenant_id=tenant_id,
        opportunity_id=opportunity.id,
        contact_id=payload.contact_id,
        role=payload.role,
        is_primary=payload.is_primary,
        remarks=payload.remarks,
        metadata_jsonb=payload.metadata_jsonb,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="that person is already on this deal")
    if payload.is_primary:
        _demote_other_primaries(db, tenant_id, opportunity.id, keep=row.id)
    record_audit(db, tenant_id=tenant_id, action="opportunity.contact_added", entity_type="opportunity",
                 entity_id=opportunity.id, actor=actor.label,
                 detail={"opportunity_no": opportunity.opportunity_no, "contact_id": payload.contact_id, "role": payload.role})
    commit_or_conflict(db, "that person is already on this deal")
    db.refresh(row)
    return envelope(OpportunityContactRead.model_validate(row).model_dump(by_alias=True))


@router.get("/opportunity-contacts/{row_id}", response_model=OpportunityContactEnvelope, response_model_exclude_unset=True)
def get_opportunity_contact(
    row_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    row = get_scoped_or_404(db, OpportunityContact, tenant_id, row_id)
    return envelope(OpportunityContactRead.model_validate(row).model_dump(by_alias=True))


@router.patch("/opportunity-contacts/{row_id}", response_model=OpportunityContactEnvelope, response_model_exclude_unset=True)
def update_opportunity_contact(
    row_id: str,
    payload: UpdateOpportunityContactRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    row = get_scoped_or_404(db, OpportunityContact, tenant_id, row_id)
    opportunity = _own_opportunity(db, actor, row.opportunity_id, editable=False)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("role"):
        require_type_option(db, tenant_id, "opportunity_contact_role", updates["role"])
    for field, value in updates.items():
        setattr(row, field, value)
    if updates.get("is_primary"):
        _demote_other_primaries(db, tenant_id, opportunity.id, keep=row.id)
    record_audit(db, tenant_id=tenant_id, action="opportunity.contact_changed", entity_type="opportunity",
                 entity_id=opportunity.id, actor=actor.label,
                 detail={"opportunity_no": opportunity.opportunity_no, "contact_id": row.contact_id, "fields": sorted(updates)})
    db.commit()
    db.refresh(row)
    return envelope(OpportunityContactRead.model_validate(row).model_dump(by_alias=True))


@router.delete("/opportunity-contacts/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opportunity_contact(
    row_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    row = get_scoped_or_404(db, OpportunityContact, actor.tenant_id, row_id)
    opportunity = _own_opportunity(db, actor, row.opportunity_id, editable=False)
    record_audit(db, tenant_id=actor.tenant_id, action="opportunity.contact_removed", entity_type="opportunity",
                 entity_id=opportunity.id, actor=actor.label,
                 detail={"opportunity_no": opportunity.opportunity_no, "contact_id": row.contact_id})
    db.delete(row)
    db.commit()


@router.get("/opportunities/{opportunity_id}/detail", response_model=OpportunityDetailEnvelope,
            response_model_exclude_unset=True)
def get_opportunity_detail(
    opportunity_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """The deal and everything hanging off it in one read: lines, cast with
    names, the quotations and orders that name it, its campaign."""
    opportunity = get_active_document_or_404(db, Opportunity, tenant_id, opportunity_id)
    items = db.scalars(
        select(OpportunityItem).where(OpportunityItem.tenant_id == tenant_id, OpportunityItem.opportunity_id == opportunity.id)
        .order_by(OpportunityItem.line_no.asc().nulls_last(), OpportunityItem.created_at.asc())
    ).all()
    cast_rows = db.execute(
        select(OpportunityContact, CustomerContact)
        .join(CustomerContact, CustomerContact.id == OpportunityContact.contact_id)
        .where(OpportunityContact.tenant_id == tenant_id, OpportunityContact.opportunity_id == opportunity.id)
        .order_by(OpportunityContact.is_primary.desc(), OpportunityContact.created_at.asc())
    ).all()
    contacts = [
        OpportunityContactDetailRead(
            **OpportunityContactRead.model_validate(row).model_dump(),
            contact_name=person.name, contact_title=person.title,
            contact_phone=person.phone, contact_email=person.email,
        )
        for row, person in cast_rows
    ]
    quotations = db.scalars(
        select(SalesQuotation).where(SalesQuotation.tenant_id == tenant_id, SalesQuotation.opportunity_id == opportunity.id,
                                     SalesQuotation.deleted_at.is_(None))
        .order_by(SalesQuotation.created_at.desc())
    ).all()
    orders = db.scalars(
        select(SalesOrder).where(SalesOrder.tenant_id == tenant_id, SalesOrder.opportunity_id == opportunity.id,
                                 SalesOrder.deleted_at.is_(None))
        .order_by(SalesOrder.created_at.desc())
    ).all()
    campaign = db.get(Campaign, opportunity.campaign_id) if opportunity.campaign_id else None
    activities = db.scalars(select(Activity).where(Activity.tenant_id == tenant_id, Activity.opportunity_id == opportunity.id,
                                                   Activity.deleted_at.is_(None)).order_by(Activity.occurred_at.desc()).limit(10)).all()
    events = db.scalars(select(Event).where(Event.tenant_id == tenant_id, Event.opportunity_id == opportunity.id,
                                            Event.deleted_at.is_(None)).order_by(Event.starts_at.desc()).limit(10)).all()
    communications = db.scalars(select(CommunicationEvent).where(
        CommunicationEvent.tenant_id == tenant_id, CommunicationEvent.opportunity_id == opportunity.id,
        CommunicationEvent.deleted_at.is_(None)).order_by(CommunicationEvent.occurred_at.desc()).limit(10)).all()
    detail = OpportunityDetailRead(
        opportunity=OpportunityRead.model_validate(opportunity),
        items=[OpportunityItemRead.model_validate(i) for i in items],
        contacts=contacts,
        quotations=[SalesQuotationRead.model_validate(q) for q in quotations],
        orders=[SalesOrderRead.model_validate(o) for o in orders],
        campaign=CampaignRead.model_validate(campaign) if campaign is not None else None,
        activities=[ActivityRead.model_validate(a) for a in activities],
        events=[EventRead.model_validate(e) for e in events],
        communications=[CommunicationEventRead.model_validate(c) for c in communications],
    )
    return envelope(detail.model_dump(by_alias=True))


def _agreed_price(db: Session, tenant_id: str, customer_id: str | None, product_id: str | None) -> float | None:
    if not (customer_id and product_id):
        return None
    row = db.scalar(select(CustomerProduct).where(
        CustomerProduct.tenant_id == tenant_id, CustomerProduct.customer_id == customer_id,
        CustomerProduct.product_id == product_id, CustomerProduct.status == "active",
    ))
    return float(row.agreed_price) if row is not None and row.agreed_price is not None else None


@router.post("/opportunities/{opportunity_id}/quote", response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def quote_opportunity(
    opportunity_id: str,
    payload: QuoteOpportunityRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The one orchestration between the pipeline and the quotation: a draft
    quotation from the deal's own lines, priced from each line's stated
    price, else the customer's agreement, else the catalog — the response
    says which per line — with the deal's primary contact on it and the
    deal moved to its `quoting` state, one transaction. Needs the quoting
    grant as well as the deal: the draft is a quotation like any other."""
    tenant_id = actor.tenant_id
    require_permission(actor, "quotation.submit_own")
    opportunity = _own_opportunity(db, actor, opportunity_id, editable=False)
    items = db.scalars(
        select(OpportunityItem).where(OpportunityItem.tenant_id == tenant_id, OpportunityItem.opportunity_id == opportunity.id)
        .order_by(OpportunityItem.line_no.asc().nulls_last(), OpportunityItem.created_at.asc())
    ).all()
    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="the opportunity has no lines to quote — add opportunity items first")
    machine = get_builtin_machine(db, tenant_id, "opportunity")
    quoting = state_for_role(machine, "opportunity", "quoting")
    primary = db.scalar(
        select(CustomerContact).join(OpportunityContact, OpportunityContact.contact_id == CustomerContact.id)
        .where(OpportunityContact.tenant_id == tenant_id, OpportunityContact.opportunity_id == opportunity.id)
        .order_by(OpportunityContact.is_primary.desc(), OpportunityContact.created_at.asc()).limit(1)
    )
    quotation_machine = get_builtin_machine(db, tenant_id, "sales_quotation")
    quotation = SalesQuotation(
        tenant_id=tenant_id,
        quote_number=allocate_number(db, SalesQuotation, tenant_id),
        revision_no=1,
        opportunity_id=opportunity.id,
        employee_id=opportunity.employee_id,
        customer_id=opportunity.customer_id,
        customer_name_snapshot=opportunity.customer_name_snapshot,
        contact_name=primary.name if primary else None,
        contact_phone=primary.phone if primary else None,
        contact_email=primary.email if primary else None,
        title=payload.title or opportunity.title,
        quote_date=payload.quote_date,
        valid_until=payload.valid_until,
        currency=opportunity.currency,
        payment_terms=payload.payment_terms,
        delivery_terms=payload.delivery_terms,
        status=quotation_machine["initial"],
        remarks=payload.remarks,
    )
    db.add(quotation)
    db.flush()
    lines, bases = [], []
    for index, item in enumerate(items, start=1):
        list_price = catalog_list_price(db, tenant_id, item.product_id, item.sku_id) if (item.product_id or item.sku_id) else None
        agreed = _agreed_price(db, tenant_id, opportunity.customer_id, item.product_id)
        if item.unit_price is not None:
            unit_price, basis = float(item.unit_price), "opportunity_line"
        elif agreed is not None:
            unit_price, basis = agreed, "customer_agreement"
        elif list_price is not None:
            unit_price, basis = list_price, "price_book"
        else:
            unit_price, basis = None, "unpriced"
        line = SalesQuotationItem(
            tenant_id=tenant_id,
            quotation_id=quotation.id,
            line_no=item.line_no or index,
            product_id=item.product_id,
            sku_id=item.sku_id,
            product_name_snapshot=item.product_name_snapshot or (
                db.get(Product, item.product_id).name if item.product_id else None
            ),
            spec=item.spec,
            quantity=item.quantity,
            unit=item.unit,
            list_price_snapshot=list_price,
            unit_price=unit_price,
            amount=round(float(item.quantity) * unit_price, 2) if unit_price is not None else None,
            # F-29: a deal line's notes are internal ("价格未谈"); the quotation
            # line is what the customer reads — it starts clean
        )
        db.add(line)
        lines.append(line)
        bases.append(basis)
    if opportunity.status != quoting and quoting in (machine.get("transitions") or {}).get(opportunity.status, []):
        # F-04: a deal already past quoting (negotiating) keeps its stage;
        # the bridge does not walk it backwards
        apply_status_change(db, actor, opportunity, quoting)
        opportunity.status = quoting
    record_audit(db, tenant_id=tenant_id, action="opportunity.quoted", entity_type="opportunity",
                 entity_id=opportunity.id, actor=actor.label,
                 detail={"opportunity_no": opportunity.opportunity_no, "quotation_id": quotation.id,
                         "quote_number": quotation.quote_number, "lines": len(lines)})
    commit_or_conflict(db, "a concurrent quotation was created for this opportunity; retry")
    db.refresh(quotation)
    data = SalesQuotationRead.model_validate(quotation).model_dump(by_alias=True)
    data["items"] = [
        {**SalesQuotationItemRead.model_validate(line).model_dump(by_alias=True), "price_basis": basis}
        for line, basis in zip(lines, bases)
    ]
    return envelope(data)
