"""The record of contact with a customer: activities, events, messages.

An ACTIVITY is a contact that already happened — a call, a visit, a
meeting, a message — with what was said (the summary the person confirmed)
and what comes next. An EVENT is something scheduled, personal like a lead
and approval-free: planned, then held or cancelled; when held, the activity
is logged from it in one transaction (`POST /events/{id}/log`). A
COMMUNICATION EVENT is one message that passed between us and a customer,
recorded as a fact after it happened — Oryh sends nothing to customers;
the person's own channel does, and the row is the record.

All three are `crm.own` work: the writer's own employee, everyone reads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, select
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
    requested_pagination,
    require_machine_state,
    require_type_option,
    restore_document,
)
from app.api.deps import Actor, enforce_member_employee, get_actor, has_permission, require_permission
from app.db.session import get_db
from app.models import (
    Activity,
    CommunicationEvent,
    Customer,
    CustomerContact,
    Employee,
    Event,
    EventParticipant,
    Lead,
    Opportunity,
)
from app.schemas import (
    ActivityEnvelope,
    ActivityListEnvelope,
    ActivityRead,
    CommunicationEventEnvelope,
    CommunicationEventListEnvelope,
    CommunicationEventRead,
    CreateActivityRequest,
    CreateCommunicationEventRequest,
    CreateEventParticipantRequest,
    CreateEventRequest,
    EventEnvelope,
    EventListEnvelope,
    EventParticipantEnvelope,
    EventParticipantListEnvelope,
    EventParticipantRead,
    EventRead,
    LogEventRequest,
    UpdateActivityRequest,
    UpdateCommunicationEventRequest,
    UpdateEventParticipantRequest,
    UpdateEventRequest,
)
from app.services.audit import record_audit
from app.services.state_machines import get_builtin_machine, state_for_role, validate_status_filter

router = APIRouter()


# --- shared -------------------------------------------------------------------


def _own_employee(db: Session, actor: Actor, employee_id: str | None) -> str:
    """The employee a record belongs to: the one named, checked against the
    credential's own; or the credential's own when none was named. A service
    key or an act-for-anyone role must name one."""
    require_permission(actor, "crm.own")
    if employee_id is None:
        if actor.employee_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="employee_id is required for a credential with no linked employee")
        employee_id = actor.employee_id
    get_scoped_or_404(db, Employee, actor.tenant_id, employee_id)
    enforce_member_employee(actor, employee_id)
    return employee_id


def _parties(db: Session, tenant_id: str, fields: dict) -> None:
    """The customer-side references a row may carry, each checked to exist,
    and a contact checked to belong to the customer named beside it."""
    if fields.get("customer_id"):
        get_scoped_or_404(db, Customer, tenant_id, fields["customer_id"])
    if fields.get("lead_id"):
        get_active_document_or_404(db, Lead, tenant_id, fields["lead_id"])
    if fields.get("opportunity_id"):
        get_active_document_or_404(db, Opportunity, tenant_id, fields["opportunity_id"])
    if fields.get("contact_id"):
        contact = get_scoped_or_404(db, CustomerContact, tenant_id, fields["contact_id"])
        if fields.get("customer_id") and contact.customer_id != fields["customer_id"]:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="contact_id belongs to a different customer")
    if fields.get("event_id"):
        get_active_document_or_404(db, Event, tenant_id, fields["event_id"])
    if fields.get("communication_event_id"):
        get_active_document_or_404(db, CommunicationEvent, tenant_id, fields["communication_event_id"])


def _window(stmt, column, since: datetime | None, until: datetime | None):
    if since is not None:
        stmt = stmt.where(column >= since)
    if until is not None:
        stmt = stmt.where(column <= until)
    return stmt


# --- activities ---------------------------------------------------------------


@router.get("/activities", response_model=ActivityListEnvelope, response_model_exclude_unset=True)
def list_activities(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    customer_id: str | None = None,
    lead_id: str | None = None,
    opportunity_id: str | None = None,
    contact_id: str | None = None,
    employee_id: str | None = None,
    event_id: str | None = None,
    activity_type: str | None = None,
    outcome: str | None = None,
    occurred_from: Annotated[datetime | None, Query(description="Activities at or after this moment")] = None,
    occurred_thru: Annotated[datetime | None, Query(description="Activities at or before this moment")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    stmt = select(Activity).where(Activity.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(Activity.deleted_at.is_(None))
    stmt = _window(stmt, Activity.occurred_at, occurred_from, occurred_thru)
    return list_rows(
        db, stmt,
        filters={
            Activity.customer_id: customer_id,
            Activity.lead_id: lead_id,
            Activity.opportunity_id: opportunity_id,
            Activity.contact_id: contact_id,
            Activity.employee_id: employee_id,
            Activity.event_id: event_id,
            Activity.activity_type: activity_type,
            Activity.outcome: outcome,
        },
        keyword=keyword,
        keyword_columns=(cast(Activity.id, String), Activity.subject, Activity.content, Activity.next_action),
        order_by=(Activity.occurred_at.desc(), Activity.id.desc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=ActivityRead,
    )


def _activity_options(db: Session, tenant_id: str, fields: dict) -> None:
    if fields.get("activity_type"):
        require_type_option(db, tenant_id, "activity_type", fields["activity_type"])
    if fields.get("outcome"):
        require_type_option(db, tenant_id, "activity_outcome", fields["outcome"])


@router.post("/activities", response_model=ActivityEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_activity(
    payload: CreateActivityRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    employee_id = _own_employee(db, actor, payload.employee_id)
    fields = payload.model_dump(exclude_unset=True)
    _parties(db, tenant_id, fields)
    _activity_options(db, tenant_id, fields)
    activity = Activity(
        tenant_id=tenant_id,
        employee_id=employee_id,
        customer_id=payload.customer_id,
        lead_id=payload.lead_id,
        opportunity_id=payload.opportunity_id,
        contact_id=payload.contact_id,
        activity_type=payload.activity_type,
        occurred_at=payload.occurred_at,
        subject=payload.subject,
        content=payload.content,
        source_text=payload.source_text,
        outcome=payload.outcome,
        next_action=payload.next_action,
        next_action_at=payload.next_action_at,
        event_id=payload.event_id,
        communication_event_id=payload.communication_event_id,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(activity)
    db.flush()
    record_audit(db, tenant_id=tenant_id, action="activity.recorded", entity_type="activity",
                 entity_id=activity.id, actor=actor.label,
                 detail={"activity_type": payload.activity_type, "subject": payload.subject,
                         "customer_id": payload.customer_id, "lead_id": payload.lead_id,
                         "opportunity_id": payload.opportunity_id})
    db.commit()
    db.refresh(activity)
    return envelope(ActivityRead.model_validate(activity).model_dump(by_alias=True))


@router.get("/activities/{activity_id}", response_model=ActivityEnvelope, response_model_exclude_unset=True)
def get_activity(
    activity_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    activity = get_active_document_or_404(db, Activity, tenant_id, activity_id)
    return envelope(ActivityRead.model_validate(activity).model_dump(by_alias=True))


@router.patch("/activities/{activity_id}", response_model=ActivityEnvelope, response_model_exclude_unset=True)
def update_activity(
    activity_id: str,
    payload: UpdateActivityRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "crm.own")
    activity = get_active_document_or_404(db, Activity, tenant_id, activity_id)
    enforce_member_employee(actor, activity.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    merged = {
        "customer_id": updates.get("customer_id", activity.customer_id),
        "lead_id": updates.get("lead_id", activity.lead_id),
        "opportunity_id": updates.get("opportunity_id", activity.opportunity_id),
        "contact_id": updates.get("contact_id", activity.contact_id),
        "event_id": updates.get("event_id", activity.event_id),
        "communication_event_id": updates.get("communication_event_id", activity.communication_event_id),
    }
    if not (merged["customer_id"] or merged["lead_id"] or merged["opportunity_id"]):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="an activity hangs off a customer, a lead or an opportunity — at least one")
    _parties(db, tenant_id, merged)
    _activity_options(db, tenant_id, updates)
    if "custom_fields" in updates:
        activity.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(activity, field, value)
    record_audit(db, tenant_id=tenant_id, action="activity.changed", entity_type="activity",
                 entity_id=activity.id, actor=actor.label, detail={"fields": sorted(updates)})
    db.commit()
    db.refresh(activity)
    return envelope(ActivityRead.model_validate(activity).model_dump(by_alias=True))


@router.delete("/activities/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(
    activity_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "crm.own")
    activity = get_active_document_or_404(db, Activity, actor.tenant_id, activity_id)
    enforce_member_employee(actor, activity.employee_id)
    activity.deleted_at = datetime.now(tz=activity.occurred_at.tzinfo) if activity.occurred_at.tzinfo else datetime.utcnow()
    record_audit(db, tenant_id=actor.tenant_id, action="activity.deleted", entity_type="activity",
                 entity_id=activity.id, actor=actor.label, detail={"subject": activity.subject})
    db.commit()


# --- events -------------------------------------------------------------------


@router.get("/events", response_model=EventListEnvelope, response_model_exclude_unset=True)
def list_events(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    customer_id: str | None = None,
    lead_id: str | None = None,
    opportunity_id: str | None = None,
    event_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    starts_from: Annotated[datetime | None, Query(description="Events starting at or after this moment")] = None,
    starts_thru: Annotated[datetime | None, Query(description="Events starting at or before this moment")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    validate_status_filter(db, tenant_id, "event", status_filter)
    stmt = select(Event).where(Event.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(Event.deleted_at.is_(None))
    stmt = _window(stmt, Event.starts_at, starts_from, starts_thru)
    return list_rows(
        db, stmt,
        filters={
            Event.employee_id: employee_id,
            Event.customer_id: customer_id,
            Event.lead_id: lead_id,
            Event.opportunity_id: opportunity_id,
            Event.event_type: event_type,
            Event.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(cast(Event.id, String), Event.event_no, Event.subject, Event.location, Event.description),
        order_by=(Event.starts_at.asc(), Event.id.asc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=EventRead,
    )


def _event_fields(db: Session, tenant_id: str, fields: dict, current: Event | None = None) -> None:
    if fields.get("event_type"):
        require_type_option(db, tenant_id, "event_type", fields["event_type"])
    _parties(db, tenant_id, fields)
    starts = fields.get("starts_at", current.starts_at if current else None)
    ends = fields.get("ends_at", current.ends_at if current else None)
    if starts and ends and ends < starts:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ends_at is before starts_at")


@router.post("/events", response_model=EventEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def create_event(
    payload: CreateEventRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    employee_id = _own_employee(db, actor, payload.employee_id)
    fields = payload.model_dump(exclude_unset=True)
    _event_fields(db, tenant_id, fields)
    initial_status = require_machine_state(db, tenant_id, Event, payload.status)
    event_no = payload.event_no or allocate_number(db, Event, tenant_id)
    event = Event(
        tenant_id=tenant_id,
        event_no=event_no,
        subject=payload.subject,
        event_type=payload.event_type,
        employee_id=employee_id,
        customer_id=payload.customer_id,
        lead_id=payload.lead_id,
        opportunity_id=payload.opportunity_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        location=payload.location,
        status=initial_status,
        description=payload.description,
        remarks=payload.remarks,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(event)
    db.flush()
    record_audit(db, tenant_id=tenant_id, action="event.planned", entity_type="event",
                 entity_id=event.id, actor=actor.label,
                 detail={"event_no": event_no, "subject": payload.subject, "starts_at": payload.starts_at.isoformat(),
                         "customer_id": payload.customer_id, "lead_id": payload.lead_id,
                         "opportunity_id": payload.opportunity_id})
    commit_or_conflict(db, f"event_no {event_no!r} already exists")
    db.refresh(event)
    return envelope(EventRead.model_validate(event).model_dump(by_alias=True))


@router.get("/events/{event_id}", response_model=EventEnvelope, response_model_exclude_unset=True)
def get_event(
    event_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    event = get_active_document_or_404(db, Event, tenant_id, event_id)
    return envelope(EventRead.model_validate(event).model_dump(by_alias=True))


@router.patch("/events/{event_id}", response_model=EventEnvelope, response_model_exclude_unset=True)
def update_event(
    event_id: str,
    payload: UpdateEventRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "crm.own")
    event = get_active_document_or_404(db, Event, tenant_id, event_id)
    enforce_member_employee(actor, event.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    status_change = updates.pop("status", None)
    if updates:
        ensure_document_editable(db, event)
        _event_fields(db, tenant_id, updates, current=event)
    if status_change is not None and status_change != event.status:
        apply_status_change(db, actor, event, status_change)
        event.status = status_change
    if "custom_fields" in updates:
        event.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    return envelope(EventRead.model_validate(event).model_dump(by_alias=True))


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return delete_document(db, actor, Event, event_id)


@router.post("/events/{event_id}/restore")
def restore_event(
    event_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, Event, event_id)


_EVENT_TO_ACTIVITY = {"meeting": "meeting", "visit": "visit", "demo": "meeting", "call": "call", "training": "meeting"}


@router.post("/events/{event_id}/log", response_model=ActivityEnvelope, response_model_exclude_unset=True,
             status_code=status.HTTP_201_CREATED)
def log_event(
    event_id: str,
    payload: LogEventRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The event was held: write the activity from it — its subject, its
    time, its customer/lead/deal, the first customer participant — with what
    the person says was said, and move the event to `held`, one
    transaction. An event with no customer-side party is a meeting among
    ourselves and has no activity to log (422)."""
    tenant_id = actor.tenant_id
    require_permission(actor, "crm.own")
    event = get_active_document_or_404(db, Event, tenant_id, event_id)
    enforce_member_employee(actor, event.employee_id)
    if not (event.customer_id or event.lead_id or event.opportunity_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="the event names no customer, lead or opportunity — nothing to log against")
    machine = get_builtin_machine(db, tenant_id, "event")
    held = state_for_role(machine, "event", "held")
    if event.status != held:
        apply_status_change(db, actor, event, held)
        event.status = held
    if payload.outcome:
        require_type_option(db, tenant_id, "activity_outcome", payload.outcome)
    contact = db.scalar(
        select(EventParticipant.contact_id).where(
            EventParticipant.tenant_id == tenant_id, EventParticipant.event_id == event.id,
            EventParticipant.contact_id.is_not(None),
        # F-30: the person who attended before the one merely invited
        ).order_by((EventParticipant.response == "attended").desc(), EventParticipant.created_at.asc()).limit(1)
    )
    activity_type = _EVENT_TO_ACTIVITY.get(event.event_type or "", "other")
    require_type_option(db, tenant_id, "activity_type", activity_type)
    activity = Activity(
        tenant_id=tenant_id,
        employee_id=event.employee_id,
        customer_id=event.customer_id,
        lead_id=event.lead_id,
        opportunity_id=event.opportunity_id,
        contact_id=contact,
        activity_type=activity_type,
        occurred_at=event.starts_at,
        subject=payload.subject or event.subject,
        content=payload.content,
        source_text=payload.source_text,
        outcome=payload.outcome,
        next_action=payload.next_action,
        next_action_at=payload.next_action_at,
        event_id=event.id,
    )
    db.add(activity)
    db.flush()
    record_audit(db, tenant_id=tenant_id, action="activity.recorded", entity_type="activity",
                 entity_id=activity.id, actor=actor.label,
                 detail={"activity_type": activity_type, "subject": activity.subject, "event_id": event.id,
                         "event_no": event.event_no})
    db.commit()
    db.refresh(activity)
    return envelope(ActivityRead.model_validate(activity).model_dump(by_alias=True))


# --- participants -------------------------------------------------------------


def _event_of_participant(db: Session, actor: Actor, event_id: str) -> Event:
    require_permission(actor, "crm.own")
    event = get_active_document_or_404(db, Event, actor.tenant_id, event_id)
    enforce_member_employee(actor, event.employee_id)
    return event


@router.get("/event-participants", response_model=EventParticipantListEnvelope, response_model_exclude_unset=True)
def list_event_participants(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    event_id: str | None = None,
    employee_id: str | None = None,
    contact_id: str | None = None,
    response: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    stmt = select(EventParticipant).where(EventParticipant.tenant_id == tenant_id)
    return list_rows(
        db, stmt,
        filters={
            EventParticipant.event_id: event_id,
            EventParticipant.employee_id: employee_id,
            EventParticipant.contact_id: contact_id,
            EventParticipant.response: response,
        },
        order_by=(EventParticipant.created_at.asc(), EventParticipant.id.asc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=EventParticipantRead,
    )


@router.post("/event-participants", response_model=EventParticipantEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_event_participant(
    payload: CreateEventParticipantRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    event = _event_of_participant(db, actor, payload.event_id)
    if payload.employee_id:
        get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    if payload.contact_id:
        contact = get_scoped_or_404(db, CustomerContact, tenant_id, payload.contact_id)
        if event.customer_id and contact.customer_id != event.customer_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="that person belongs to a different customer than the event")
    if payload.response:
        require_type_option(db, tenant_id, "event_response", payload.response)
    row = EventParticipant(
        tenant_id=tenant_id, event_id=event.id, employee_id=payload.employee_id,
        contact_id=payload.contact_id, response=payload.response, remarks=payload.remarks,
        metadata_jsonb=payload.metadata_jsonb,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="that person is already on the event")
    record_audit(db, tenant_id=tenant_id, action="event.participant_added", entity_type="event",
                 entity_id=event.id, actor=actor.label,
                 detail={"event_no": event.event_no, "employee_id": payload.employee_id, "contact_id": payload.contact_id})
    db.commit()
    db.refresh(row)
    return envelope(EventParticipantRead.model_validate(row).model_dump(by_alias=True))


@router.get("/event-participants/{row_id}", response_model=EventParticipantEnvelope, response_model_exclude_unset=True)
def get_event_participant(
    row_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    row = get_scoped_or_404(db, EventParticipant, tenant_id, row_id)
    return envelope(EventParticipantRead.model_validate(row).model_dump(by_alias=True))


@router.patch("/event-participants/{row_id}", response_model=EventParticipantEnvelope, response_model_exclude_unset=True)
def update_event_participant(
    row_id: str,
    payload: UpdateEventParticipantRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    row = get_scoped_or_404(db, EventParticipant, tenant_id, row_id)
    event = _event_of_participant(db, actor, row.event_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("response"):
        require_type_option(db, tenant_id, "event_response", updates["response"])
    for field, value in updates.items():
        setattr(row, field, value)
    record_audit(db, tenant_id=tenant_id, action="event.participant_changed", entity_type="event",
                 entity_id=event.id, actor=actor.label, detail={"event_no": event.event_no, "fields": sorted(updates)})
    db.commit()
    db.refresh(row)
    return envelope(EventParticipantRead.model_validate(row).model_dump(by_alias=True))


@router.delete("/event-participants/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event_participant(
    row_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    row = get_scoped_or_404(db, EventParticipant, actor.tenant_id, row_id)
    event = _event_of_participant(db, actor, row.event_id)
    record_audit(db, tenant_id=actor.tenant_id, action="event.participant_removed", entity_type="event",
                 entity_id=event.id, actor=actor.label,
                 detail={"event_no": event.event_no, "employee_id": row.employee_id, "contact_id": row.contact_id})
    db.delete(row)
    db.commit()


# --- communication events ---------------------------------------------------


@router.get("/communication-events", response_model=CommunicationEventListEnvelope, response_model_exclude_unset=True)
def list_communication_events(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    channel: str | None = None,
    direction: str | None = None,
    customer_id: str | None = None,
    lead_id: str | None = None,
    opportunity_id: str | None = None,
    contact_id: str | None = None,
    employee_id: str | None = None,
    thread_id: str | None = None,
    message_id: str | None = None,
    occurred_from: Annotated[datetime | None, Query(description="Messages at or after this moment")] = None,
    occurred_thru: Annotated[datetime | None, Query(description="Messages at or before this moment")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    stmt = select(CommunicationEvent).where(CommunicationEvent.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(CommunicationEvent.deleted_at.is_(None))
    stmt = _window(stmt, CommunicationEvent.occurred_at, occurred_from, occurred_thru)
    return list_rows(
        db, stmt,
        filters={
            CommunicationEvent.channel: channel,
            CommunicationEvent.direction: direction,
            CommunicationEvent.customer_id: customer_id,
            CommunicationEvent.lead_id: lead_id,
            CommunicationEvent.opportunity_id: opportunity_id,
            CommunicationEvent.contact_id: contact_id,
            CommunicationEvent.employee_id: employee_id,
            CommunicationEvent.thread_id: thread_id,
            CommunicationEvent.message_id: message_id,
        },
        keyword=keyword,
        keyword_columns=(cast(CommunicationEvent.id, String), CommunicationEvent.subject, CommunicationEvent.body,
                         CommunicationEvent.from_address),
        order_by=(CommunicationEvent.occurred_at.desc(), CommunicationEvent.id.desc()),
        pagination=requested_pagination(page, size),
        sort=order_by,
        read_model=CommunicationEventRead,
    )


@router.post("/communication-events", response_model=CommunicationEventEnvelope,
             response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_communication_event(
    payload: CreateCommunicationEventRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    # a recorded message may have no employee of ours (an inbound mail to a
    # shared box); when one is named it is the writer's own
    require_permission(actor, "crm.own")
    employee_id = payload.employee_id
    if employee_id is not None or not has_permission(actor, "tenant.act_for_any_employee"):
        employee_id = _own_employee(db, actor, employee_id) if (employee_id or actor.employee_id) else None
    fields = payload.model_dump(exclude_unset=True)
    _parties(db, tenant_id, fields)
    require_type_option(db, tenant_id, "communication_channel", payload.channel)
    if payload.message_id:
        existing = db.scalar(select(CommunicationEvent).where(
            CommunicationEvent.tenant_id == tenant_id, CommunicationEvent.message_id == payload.message_id,
        ))
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"message_id {payload.message_id!r} is already recorded as {existing.id}")
    row = CommunicationEvent(
        tenant_id=tenant_id,
        channel=payload.channel,
        direction=payload.direction,
        subject=payload.subject,
        body=payload.body,
        from_address=payload.from_address,
        to_addresses=list(payload.to_addresses),
        cc_addresses=list(payload.cc_addresses),
        occurred_at=payload.occurred_at,
        message_id=payload.message_id,
        thread_id=payload.thread_id,
        employee_id=employee_id,
        customer_id=payload.customer_id,
        lead_id=payload.lead_id,
        opportunity_id=payload.opportunity_id,
        contact_id=payload.contact_id,
        remarks=payload.remarks,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(row)
    db.flush()
    record_audit(db, tenant_id=tenant_id, action="communication.recorded", entity_type="communication_event",
                 entity_id=row.id, actor=actor.label,
                 detail={"channel": payload.channel, "direction": payload.direction, "subject": payload.subject,
                         "message_id": payload.message_id})
    commit_or_conflict(db, f"message_id {payload.message_id!r} is already recorded")
    db.refresh(row)
    return envelope(CommunicationEventRead.model_validate(row).model_dump(by_alias=True))


@router.get("/communication-events/{row_id}", response_model=CommunicationEventEnvelope, response_model_exclude_unset=True)
def get_communication_event(
    row_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    row = get_active_document_or_404(db, CommunicationEvent, tenant_id, row_id)
    return envelope(CommunicationEventRead.model_validate(row).model_dump(by_alias=True))


def _communication_write(db: Session, actor: Actor, row: CommunicationEvent) -> None:
    require_permission(actor, "crm.own")
    if row.employee_id is not None:
        enforce_member_employee(actor, row.employee_id)


@router.patch("/communication-events/{row_id}", response_model=CommunicationEventEnvelope, response_model_exclude_unset=True)
def update_communication_event(
    row_id: str,
    payload: UpdateCommunicationEventRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    row = get_active_document_or_404(db, CommunicationEvent, tenant_id, row_id)
    _communication_write(db, actor, row)
    updates = payload.model_dump(exclude_unset=True)
    merged = {k: updates.get(k, getattr(row, k)) for k in ("customer_id", "lead_id", "opportunity_id", "contact_id")}
    if all(v is None for v in merged.values()):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="a message names who it was with — a customer, a lead, an opportunity or a contact")
    _parties(db, tenant_id, merged)
    if "custom_fields" in updates:
        row.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(row, field, value)
    record_audit(db, tenant_id=tenant_id, action="communication.changed", entity_type="communication_event",
                 entity_id=row.id, actor=actor.label, detail={"fields": sorted(updates)})
    db.commit()
    db.refresh(row)
    return envelope(CommunicationEventRead.model_validate(row).model_dump(by_alias=True))


@router.delete("/communication-events/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_communication_event(
    row_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    row = get_active_document_or_404(db, CommunicationEvent, actor.tenant_id, row_id)
    _communication_write(db, actor, row)
    row.deleted_at = datetime.now(tz=row.occurred_at.tzinfo) if row.occurred_at.tzinfo else datetime.utcnow()
    record_audit(db, tenant_id=actor.tenant_id, action="communication.deleted", entity_type="communication_event",
                 entity_id=row.id, actor=actor.label, detail={"subject": row.subject, "message_id": row.message_id})
    db.commit()
