"""Bookable things, and the calendar that keeps two bookings off one of them.

Split out of `routes.py`: resources and resource bookings.

A separate module from `workspace.py` despite being another tenant-level list,
because the four helpers here are a scheduling model rather than CRUD:
`get_overlapping_bookings` is the whole point of the resource, and
`build_resource_availability` answers the question the console asks before it
offers a slot. Nothing else in the API has an interval to reason about.

Imports run one way: this module reads `app.api.common` and no other endpoint
module, and nothing in `app/api` reads this one. Only `app/main.py` mounts its
router.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import String, cast, select
from sqlalchemy.orm import Session

from app.api.common import (
    archive_row,
    envelope,
    get_scoped_or_404,
    get_tenant_id,
    list_rows,
    page_only_pagination,
    requested_pagination,
    require_master_data_manage,
)
from app.api.deps import Actor, attributed, enforce_member_employee, get_actor, require_permission
from app.db.session import get_db
from app.models import (
    Employee,
    Resource,
    ResourceBooking,
)
from app.schemas import (
    CreateResourceBookingRequest,
    CreateResourceRequest,
    DeleteResourceBookingRequest,
    ResourceAvailabilityRead,
    ResourceBookingListEnvelope,
    ResourceBookingRead,
    ResourceEnvelope,
    ResourceListEnvelope,
    ResourceRead,
    UpdateResourceBookingRequest,
    UpdateResourceRequest,
)
from app.services.audit import record_audit

router = APIRouter()


# --- the scheduling model: overlap, validity, availability ------------------


def ensure_resource_active(resource: Resource) -> None:
    if resource.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="resource is not available for booking")


def get_overlapping_bookings(
    db: Session,
    tenant_id: str,
    resource_id: str,
    start_at: datetime,
    end_at: datetime,
    exclude_booking_id: str | None = None,
) -> list[ResourceBooking]:
    stmt = select(ResourceBooking).where(
        ResourceBooking.tenant_id == tenant_id,
        ResourceBooking.resource_id == resource_id,
        ResourceBooking.status == "confirmed",
        ResourceBooking.cancelled_at.is_(None),
        ResourceBooking.start_at < end_at,
        ResourceBooking.end_at > start_at,
    )
    if exclude_booking_id:
        stmt = stmt.where(ResourceBooking.id != exclude_booking_id)
    return db.scalars(stmt.order_by(ResourceBooking.start_at.asc())).all()


def validate_resource_booking(
    db: Session,
    tenant_id: str,
    resource: Resource,
    start_at: datetime,
    end_at: datetime,
    quantity: int,
    exclude_booking_id: str | None = None,
) -> list[ResourceBooking]:
    overlaps = get_overlapping_bookings(
        db,
        tenant_id=tenant_id,
        resource_id=resource.id,
        start_at=start_at,
        end_at=end_at,
        exclude_booking_id=exclude_booking_id,
    )
    if resource.booking_mode == "exclusive":
        if overlaps:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="resource is already booked for that time")
        return overlaps

    max_quantity = resource.max_quantity or 1
    booked_quantity = sum(item.quantity for item in overlaps)
    if booked_quantity + quantity > max_quantity:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="resource quantity is unavailable for that time")
    return overlaps


def build_resource_availability(
    db: Session,
    tenant_id: str,
    resource: Resource,
    start_at: datetime,
    end_at: datetime,
    exclude_booking_id: str | None = None,
) -> ResourceAvailabilityRead:
    overlaps = get_overlapping_bookings(
        db,
        tenant_id=tenant_id,
        resource_id=resource.id,
        start_at=start_at,
        end_at=end_at,
        exclude_booking_id=exclude_booking_id,
    )
    if resource.booking_mode == "exclusive":
        available = len(overlaps) == 0
        available_quantity = 1 if available else 0
    else:
        max_quantity = resource.max_quantity or 1
        booked_quantity = sum(item.quantity for item in overlaps)
        available_quantity = max(max_quantity - booked_quantity, 0)
        available = available_quantity > 0
    return ResourceAvailabilityRead(
        resource_id=resource.id,
        start_at=start_at,
        end_at=end_at,
        booking_mode=resource.booking_mode,
        available=available,
        available_quantity=available_quantity,
        conflicting_booking_ids=[item.id for item in overlaps],
    )


# --- resources: the bookable thing itself -----------------------------------


@router.get("/resources", response_model=ResourceListEnvelope, response_model_exclude_unset=True)
def list_resources(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    resource_type: str | None = None,
    booking_mode: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(Resource).where(Resource.tenant_id == tenant_id),
        filters={
            Resource.resource_type: resource_type,
            Resource.booking_mode: booking_mode,
            Resource.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(Resource.name,),
        order_by=(Resource.created_at.desc(), Resource.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=ResourceRead,
    )


@router.post(
    "/resources",
    response_model=ResourceEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_resource(
    payload: CreateResourceRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    resource = Resource(
        tenant_id=actor.tenant_id,
        resource_type=payload.resource_type,
        name=payload.name,
        code=payload.code,
        location=payload.location,
        capacity=payload.capacity,
        booking_mode=payload.booking_mode,
        max_quantity=payload.max_quantity,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return envelope(ResourceRead.model_validate(resource).model_dump(by_alias=True))


@router.get("/resources/{resource_id}", response_model=ResourceEnvelope, response_model_exclude_unset=True)
def get_resource(
    resource_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    resource = get_scoped_or_404(db, Resource, tenant_id, resource_id)
    return envelope(ResourceRead.model_validate(resource).model_dump(by_alias=True))


@router.patch("/resources/{resource_id}", response_model=ResourceEnvelope, response_model_exclude_unset=True)
def update_resource(
    resource_id: str,
    payload: UpdateResourceRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    resource = get_scoped_or_404(db, Resource, actor.tenant_id, resource_id)
    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        resource.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(resource, field, value)
    db.commit()
    db.refresh(resource)
    return envelope(ResourceRead.model_validate(resource).model_dump(by_alias=True))


@router.delete("/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource(
    resource_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, Resource, resource_id)


@router.get("/resources/{resource_id}/availability")
def get_resource_availability(
    resource_id: str,
    start_at: datetime,
    end_at: datetime,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    if end_at <= start_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_at must be greater than start_at")
    resource = get_scoped_or_404(db, Resource, tenant_id, resource_id)
    data = build_resource_availability(db, tenant_id, resource, start_at, end_at)
    return envelope(data.model_dump())


# --- bookings: one interval on one resource ---------------------------------


@router.get(
    "/resource-bookings",
    response_model=ResourceBookingListEnvelope,
    response_model_exclude_unset=True,
)
def list_resource_bookings(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    resource_id: str | None = None,
    booked_by_employee_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    return list_rows(
        db, select(ResourceBooking).where(ResourceBooking.tenant_id == tenant_id),
        filters={
            ResourceBooking.resource_id: resource_id,
            ResourceBooking.booked_by_employee_id: booked_by_employee_id,
            ResourceBooking.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(ResourceBooking.id, String),
            cast(ResourceBooking.resource_id, String),
            cast(ResourceBooking.booked_by_employee_id, String),
            ResourceBooking.title,
            ResourceBooking.booking_type,
            ResourceBooking.status,
            ResourceBooking.source_text,
            ResourceBooking.notes,
        ),
        order_by=(
            ResourceBooking.start_at.asc(),
            ResourceBooking.created_at.asc(),
            ResourceBooking.id.asc(),
        ),
        pagination=requested_pagination(page, size),
        read_model=ResourceBookingRead,
    )


@router.post("/resource-bookings", status_code=status.HTTP_201_CREATED)
def create_resource_booking(
    payload: CreateResourceBookingRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "booking.own")
    resource = get_scoped_or_404(db, Resource, tenant_id, payload.resource_id)
    ensure_resource_active(resource)
    get_scoped_or_404(db, Employee, tenant_id, payload.booked_by_employee_id)
    enforce_member_employee(actor, payload.booked_by_employee_id)
    validate_resource_booking(
        db,
        tenant_id=tenant_id,
        resource=resource,
        start_at=payload.start_at,
        end_at=payload.end_at,
        quantity=payload.quantity,
    )
    booking = ResourceBooking(
        tenant_id=tenant_id,
        resource_id=payload.resource_id,
        booked_by_employee_id=payload.booked_by_employee_id,
        booking_type=payload.booking_type,
        title=payload.title,
        start_at=payload.start_at,
        end_at=payload.end_at,
        quantity=payload.quantity,
        status=payload.status,
        source_text=payload.source_text,
        notes=payload.notes,
        metadata_jsonb=payload.metadata,
    )
    db.add(booking)
    db.flush()
    record_audit(
        db,
        tenant_id=tenant_id,
        action="booking.created",
        entity_type="resource_booking",
        entity_id=booking.id,
        actor=actor.label,
        detail={
            "employee_id": booking.booked_by_employee_id,
            "resource_id": booking.resource_id,
            "title": booking.title,
            "start_at": booking.start_at.isoformat(),
            "end_at": booking.end_at.isoformat(),
        },
    )
    db.commit()
    db.refresh(booking)
    return envelope(ResourceBookingRead.model_validate(booking).model_dump(by_alias=True))


@router.get("/resource-bookings/{booking_id}")
def get_resource_booking(
    booking_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    booking = get_scoped_or_404(db, ResourceBooking, tenant_id, booking_id)
    return envelope(ResourceBookingRead.model_validate(booking).model_dump(by_alias=True))


@router.patch("/resource-bookings/{booking_id}")
def update_resource_booking(
    booking_id: str,
    payload: UpdateResourceBookingRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    booking = get_scoped_or_404(db, ResourceBooking, tenant_id, booking_id)
    require_permission(actor, "booking.own")
    if booking.status == "cancelled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="cancelled booking cannot be changed")
    enforce_member_employee(actor, booking.booked_by_employee_id)
    resource = get_scoped_or_404(db, Resource, tenant_id, booking.resource_id)
    ensure_resource_active(resource)
    updates = payload.model_dump(exclude_unset=True)
    start_at = updates.get("start_at", booking.start_at)
    end_at = updates.get("end_at", booking.end_at)
    quantity = updates.get("quantity", booking.quantity)
    validate_resource_booking(
        db,
        tenant_id=tenant_id,
        resource=resource,
        start_at=start_at,
        end_at=end_at,
        quantity=quantity,
        exclude_booking_id=booking.id,
    )
    if "metadata" in updates:
        booking.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(booking, field, value)
    db.commit()
    db.refresh(booking)
    return envelope(ResourceBookingRead.model_validate(booking).model_dump(by_alias=True))


@router.delete("/resource-bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource_booking(
    booking_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    payload: DeleteResourceBookingRequest | None = None,
):
    booking = get_scoped_or_404(db, ResourceBooking, actor.tenant_id, booking_id)
    require_permission(actor, "booking.own")
    if booking.status == "cancelled":
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    enforce_member_employee(actor, booking.booked_by_employee_id)
    booking.status = "cancelled"
    booking.cancelled_at = datetime.now(timezone.utc)
    booking.cancelled_by = attributed(actor, payload.cancelled_by if payload else None)
    booking.cancel_reason = payload.cancel_reason if payload else None
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="booking.cancelled",
        entity_type="resource_booking",
        entity_id=booking.id,
        actor=actor.label,
        detail={
            "employee_id": booking.booked_by_employee_id,
            "resource_id": booking.resource_id,
            "title": booking.title,
            "reason": booking.cancel_reason,
        },
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
