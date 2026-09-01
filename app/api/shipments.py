"""Freight legs: shipments and their lines, OFBiz Shipment/ShipmentItem
reduced to the agent-native shape.

One leg, one direction. `outbound` goods leave us — shipping a sales order,
sending a purchase return back to its vendor; `inbound` goods arrive —
receiving a purchase order, a customer return's parcel. The linked order row
(returns included, since returns live in the order tables) must AGREE with
the direction, and the matrix rides the refusal so the agent learns it.

The shipment is the freight document, never the stock truth. Stock moves
only through the inventory ledger, and `/shipments/{id}/post-stock` is the
one bridge: for every line that names a stock position (`inventory_item_id`
— the ShipmentItem↔InventoryItem association, OFBiz's ItemIssuance /
ShipmentReceipt collapsed to its useful core), it posts one movement with
the shipment line as provenance and the header's order FK carried through,
then stamps `stock_posted_at` so it can never run twice. Lines without a
position are 直发 legs and are reported as skipped, not failed.

Freight is warehouse work: `inventory.manage` files, edits and advances
(the purchase-order pattern — one functional grant, no owner). Reads are
member-visible like every business document.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import (
    allocate_number,
    apply_status_change,
    delete_document,
    envelope,
    ensure_document_editable,
    ensure_document_not_deleted,
    get_active_document_or_404,
    get_scoped_or_404,
    get_tenant_id,
    list_rows,
    requested_pagination,
    require_machine_state,
    restore_document,
)
from app.api.deps import Actor, attributed, get_actor, require_permission
from app.db.session import get_db
from app.models import (
    Facility,
    InventoryItem,
    InventoryItemDetail,
    Product,
    ProductSku,
    Picklist,
    PicklistItem,
    PurchaseOrder,
    SalesOrder,
    Shipment,
    ShipmentItem,
)
from app.schemas import (
    CreatePicklistItemRequest,
    ShipmentItemBase,
    CreatePicklistRequest,
    CreateShipmentItemRequest,
    CreateShipmentRequest,
    PostShipmentStockEnvelope,
    PostShipmentStockRead,
    PostedStockLineRead,
    ShipmentEnvelope,
    ShipmentItemEnvelope,
    ShipmentItemListEnvelope,
    ShipmentItemRead,
    PicklistEnvelope,
    PicklistItemEnvelope,
    PicklistItemListEnvelope,
    PicklistItemRead,
    PicklistListEnvelope,
    PicklistRead,
    ShipmentListEnvelope,
    ShipmentRead,
    UpdatePicklistItemRequest,
    UpdatePicklistRequest,
    UpdateShipmentItemRequest,
    UpdateShipmentRequest,
)
from app.services.inventory_import import post_inventory_detail
from app.services.state_machines import validate_status_filter

router = APIRouter()


# (order table, order_kind) -> the direction the goods actually move. Stated
# once, enforced with the whole matrix in the refusal so the agent reads the
# rule instead of guessing at it.
DIRECTION_BY_ORDER = {
    ("sales_order", "order"): "outbound",
    ("sales_order", "return"): "inbound",
    ("purchase_order", "order"): "inbound",
    ("purchase_order", "return"): "outbound",
}


def _require_order_coherence(
    db: Session, tenant_id: str, direction: str,
    sales_order_id: str | None, purchase_order_id: str | None,
) -> None:
    if sales_order_id and purchase_order_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a shipment serves one order side — sales_order_id or purchase_order_id, not both",
        )
    if sales_order_id:
        row = get_scoped_or_404(db, SalesOrder, tenant_id, sales_order_id)
        side = "sales_order"
    elif purchase_order_id:
        row = get_scoped_or_404(db, PurchaseOrder, tenant_id, purchase_order_id)
        side = "purchase_order"
    else:
        return
    wanted = DIRECTION_BY_ORDER[(side, row.order_kind)]
    if direction != wanted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"a {side} with order_kind={row.order_kind!r} moves goods {wanted} — "
                "the matrix: sales order → outbound, sales return → inbound, "
                "purchase order → inbound, purchase return → outbound"
            ),
        )


def _require_line_position(
    db: Session, tenant_id: str,
    product_id: str, sku_id: str | None, inventory_item_id: str | None,
) -> None:
    get_scoped_or_404(db, Product, tenant_id, product_id)
    if sku_id is not None:
        sku = get_scoped_or_404(db, ProductSku, tenant_id, sku_id)
        if sku.product_id != product_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"sku {sku_id} belongs to product {sku.product_id}, not {product_id}",
            )
    if inventory_item_id is None:
        return
    position = get_scoped_or_404(db, InventoryItem, tenant_id, inventory_item_id)
    if position.product_id != product_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"inventory item {inventory_item_id} holds product "
                f"{position.product_id}, not this line's {product_id}"
            ),
        )
    if position.sku_id is not None and sku_id is not None and position.sku_id != sku_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"inventory item {inventory_item_id} is the {position.sku_id} position, not {sku_id}",
        )


# --- picklists: which product, from which position, how many ----------------


def _require_picklist_context(
    db: Session, tenant_id: str, picklist_id: str | None, sales_order_id: str | None
) -> Picklist | None:
    """A shipment naming a picking run must agree with it about the order:
    two documents both claiming to fulfil something, pointing at different
    orders, is a wrong answer somebody will repeat."""
    if picklist_id is None:
        return None
    picklist = get_active_document_or_404(db, Picklist, tenant_id, picklist_id)
    if (
        picklist.sales_order_id is not None
        and sales_order_id is not None
        and picklist.sales_order_id != sales_order_id
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"picklist {picklist_id} picks for order {picklist.sales_order_id}, "
                f"not this shipment's {sales_order_id}"
            ),
        )
    return picklist


@router.get("/picklists", response_model=PicklistListEnvelope, response_model_exclude_unset=True)
def list_picklists(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    sales_order_id: str | None = None,
    facility_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    validate_status_filter(db, tenant_id, "picklist", status_filter)
    stmt = select(Picklist).where(Picklist.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(Picklist.deleted_at.is_(None))
    return list_rows(
        db, stmt,
        filters={
            Picklist.sales_order_id: sales_order_id,
            Picklist.facility_id: facility_id,
            Picklist.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(cast(Picklist.id, String), Picklist.picklist_no, Picklist.remarks),
        order_by=(Picklist.created_at.desc(), Picklist.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=PicklistRead,
    )


@router.post("/picklists", status_code=status.HTTP_201_CREATED)
def create_picklist(
    payload: CreatePicklistRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "inventory.manage")
    if payload.sales_order_id:
        get_scoped_or_404(db, SalesOrder, tenant_id, payload.sales_order_id)
    if payload.facility_id:
        get_scoped_or_404(db, Facility, tenant_id, payload.facility_id)
    initial_status = require_machine_state(db, tenant_id, Picklist, payload.status)
    for line in payload.items:
        _require_line_position(
            db, tenant_id, line.product_id, line.sku_id, line.inventory_item_id
        )
    picklist_no = payload.picklist_no or allocate_number(db, Picklist, tenant_id)
    picklist = Picklist(
        tenant_id=tenant_id,
        picklist_no=picklist_no,
        sales_order_id=payload.sales_order_id,
        facility_id=payload.facility_id,
        status=initial_status,
        remarks=payload.remarks,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(picklist)
    try:
        db.flush()
        items = [
            PicklistItem(
                tenant_id=tenant_id,
                picklist_id=picklist.id,
                line_no=line.line_no if line.line_no is not None else index,
                product_id=line.product_id,
                sku_id=line.sku_id,
                inventory_item_id=line.inventory_item_id,
                quantity=line.quantity,
                picked_quantity=line.picked_quantity,
                description=line.description,
            )
            for index, line in enumerate(payload.items, start=1)
        ]
        db.add_all(items)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"picklist_no {picklist_no!r} already exists",
        )
    db.refresh(picklist)
    data = PicklistRead.model_validate(picklist).model_dump(by_alias=True)
    if items:
        data["items"] = [
            PicklistItemRead.model_validate(item).model_dump(by_alias=True) for item in items
        ]
    return envelope(data)


@router.get("/picklists/{picklist_id}")
def get_picklist(
    picklist_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    picklist = get_active_document_or_404(db, Picklist, tenant_id, picklist_id)
    items = db.scalars(
        select(PicklistItem)
        .where(
            PicklistItem.tenant_id == tenant_id,
            PicklistItem.picklist_id == picklist.id,
            PicklistItem.deleted_at.is_(None),
        )
        .order_by(PicklistItem.line_no.asc(), PicklistItem.created_at.asc())
    ).all()
    data = PicklistRead.model_validate(picklist).model_dump(by_alias=True)
    data["items"] = [
        PicklistItemRead.model_validate(item).model_dump(by_alias=True) for item in items
    ]
    return envelope(data)


@router.patch("/picklists/{picklist_id}", response_model=PicklistEnvelope,
              response_model_exclude_unset=True)
def update_picklist(
    picklist_id: str,
    payload: UpdatePicklistRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "inventory.manage")
    picklist = get_active_document_or_404(db, Picklist, tenant_id, picklist_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("sales_order_id"):
        get_scoped_or_404(db, SalesOrder, tenant_id, updates["sales_order_id"])
    if updates.get("facility_id"):
        get_scoped_or_404(db, Facility, tenant_id, updates["facility_id"])
    if "status" in updates and updates["status"] != picklist.status:
        apply_status_change(db, actor, picklist, updates["status"])
    if "custom_fields" in updates:
        picklist.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(picklist, field, value)
    db.commit()
    db.refresh(picklist)
    return envelope(PicklistRead.model_validate(picklist).model_dump(by_alias=True))


@router.delete("/picklists/{picklist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_picklist(
    picklist_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "inventory.manage")
    return delete_document(db, actor, Picklist, picklist_id)


@router.post("/picklists/{picklist_id}/restore")
def restore_picklist(
    picklist_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "inventory.manage")
    return restore_document(db, actor, Picklist, picklist_id)


@router.get("/picklist-items", response_model=PicklistItemListEnvelope,
            response_model_exclude_unset=True)
def list_picklist_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    picklist_id: str | None = None,
    inventory_item_id: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    return list_rows(
        db,
        select(PicklistItem).where(
            PicklistItem.tenant_id == tenant_id, PicklistItem.deleted_at.is_(None)
        ),
        filters={
            PicklistItem.picklist_id: picklist_id,
            PicklistItem.inventory_item_id: inventory_item_id,
        },
        order_by=(PicklistItem.line_no.asc(), PicklistItem.created_at.asc()),
        pagination=requested_pagination(page, size),
        read_model=PicklistItemRead,
    )


@router.post("/picklist-items", status_code=status.HTTP_201_CREATED,
             response_model=PicklistItemEnvelope)
def create_picklist_item(
    payload: CreatePicklistItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "inventory.manage")
    picklist = get_active_document_or_404(db, Picklist, tenant_id, payload.picklist_id)
    ensure_document_editable(db, picklist)
    _require_line_position(
        db, tenant_id, payload.product_id, payload.sku_id, payload.inventory_item_id
    )
    item = PicklistItem(
        tenant_id=tenant_id,
        picklist_id=picklist.id,
        line_no=payload.line_no,
        product_id=payload.product_id,
        sku_id=payload.sku_id,
        inventory_item_id=payload.inventory_item_id,
        quantity=payload.quantity,
        picked_quantity=payload.picked_quantity,
        description=payload.description,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return envelope(PicklistItemRead.model_validate(item).model_dump(by_alias=True))


@router.patch("/picklist-items/{item_id}", response_model=PicklistItemEnvelope)
def update_picklist_item(
    item_id: str,
    payload: UpdatePicklistItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "inventory.manage")
    item = get_scoped_or_404(db, PicklistItem, tenant_id, item_id)
    ensure_document_not_deleted(item)
    picklist = get_active_document_or_404(db, Picklist, tenant_id, item.picklist_id)
    ensure_document_editable(db, picklist)
    updates = payload.model_dump(exclude_unset=True)
    if "inventory_item_id" in updates or "sku_id" in updates:
        _require_line_position(
            db, tenant_id, item.product_id,
            updates.get("sku_id", item.sku_id),
            updates.get("inventory_item_id", item.inventory_item_id),
        )
    for field, value in updates.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return envelope(PicklistItemRead.model_validate(item).model_dump(by_alias=True))


@router.delete("/picklist-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_picklist_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "inventory.manage")
    item = get_scoped_or_404(db, PicklistItem, tenant_id, item_id)
    picklist = get_active_document_or_404(db, Picklist, tenant_id, item.picklist_id)
    ensure_document_editable(db, picklist)
    item.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return None


@router.get("/shipments", response_model=ShipmentListEnvelope, response_model_exclude_unset=True)
def list_shipments(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    direction: str | None = None,
    sales_order_id: str | None = None,
    purchase_order_id: str | None = None,
    shipment_no: str | None = None,
    tracking_no: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    validate_status_filter(db, tenant_id, "shipment", status_filter)
    stmt = select(Shipment).where(Shipment.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(Shipment.deleted_at.is_(None))
    return list_rows(
        db, stmt,
        filters={
            Shipment.direction: direction,
            Shipment.sales_order_id: sales_order_id,
            Shipment.purchase_order_id: purchase_order_id,
            Shipment.shipment_no: shipment_no,
            Shipment.tracking_no: tracking_no,
            Shipment.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(Shipment.id, String),
            Shipment.shipment_no,
            Shipment.title,
            Shipment.carrier,
            Shipment.tracking_no,
            Shipment.facility,
            Shipment.address,
            Shipment.status,
            Shipment.remarks,
        ),
        order_by=(Shipment.created_at.desc(), Shipment.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=ShipmentRead,
    )


@router.post("/shipments", status_code=status.HTTP_201_CREATED)
def create_shipment(
    payload: CreateShipmentRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "inventory.manage")
    _require_order_coherence(
        db, tenant_id, payload.direction, payload.sales_order_id, payload.purchase_order_id
    )
    picklist = _require_picklist_context(
        db, tenant_id, payload.picklist_id, payload.sales_order_id
    )
    initial_status = require_machine_state(db, tenant_id, Shipment, payload.status)
    lines = list(payload.items)
    if picklist is not None and not lines:
        # the handoff: pack what was picked. Picked quantities win over asked
        # ones, and a zero pick ships nothing from that line
        picked_rows = db.scalars(
            select(PicklistItem)
            .where(
                PicklistItem.tenant_id == tenant_id,
                PicklistItem.picklist_id == picklist.id,
                PicklistItem.deleted_at.is_(None),
            )
            .order_by(PicklistItem.line_no.asc(), PicklistItem.created_at.asc())
        ).all()
        lines = [
            ShipmentItemBase(
                line_no=row.line_no,
                product_id=row.product_id,
                sku_id=row.sku_id,
                quantity=float(row.picked_quantity if row.picked_quantity is not None
                               else row.quantity),
                inventory_item_id=row.inventory_item_id,
                description=row.description,
            )
            for row in picked_rows
            if (row.picked_quantity if row.picked_quantity is not None else row.quantity) > 0
        ]
        if not lines:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"picklist {picklist.id} has no pickable lines to copy — "
                    "record picks (or pass items explicitly)"
                ),
            )
    for line in lines:
        _require_line_position(
            db, tenant_id, line.product_id, line.sku_id, line.inventory_item_id
        )
    shipment_no = payload.shipment_no or allocate_number(db, Shipment, tenant_id)
    shipment = Shipment(
        tenant_id=tenant_id,
        shipment_no=shipment_no,
        direction=payload.direction,
        title=payload.title,
        sales_order_id=payload.sales_order_id,
        purchase_order_id=payload.purchase_order_id,
        picklist_id=payload.picklist_id,
        facility=payload.facility,
        address=payload.address,
        carrier=payload.carrier,
        tracking_no=payload.tracking_no,
        expected_date=payload.expected_date,
        status=initial_status,
        remarks=payload.remarks,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(shipment)
    try:
        db.flush()
        items = [
            ShipmentItem(
                tenant_id=tenant_id,
                shipment_id=shipment.id,
                line_no=line.line_no if line.line_no is not None else index,
                product_id=line.product_id,
                sku_id=line.sku_id,
                quantity=line.quantity,
                inventory_item_id=line.inventory_item_id,
                description=line.description,
            )
            for index, line in enumerate(lines, start=1)
        ]
        db.add_all(items)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"shipment_no {shipment_no!r} already exists",
        )
    db.refresh(shipment)
    data = ShipmentRead.model_validate(shipment).model_dump(by_alias=True)
    if items:
        data["items"] = [
            ShipmentItemRead.model_validate(item).model_dump(by_alias=True) for item in items
        ]
    return envelope(data)


@router.get("/shipments/{shipment_id}")
def get_shipment(
    shipment_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    shipment = get_active_document_or_404(db, Shipment, tenant_id, shipment_id)
    items = db.scalars(
        select(ShipmentItem)
        .where(
            ShipmentItem.tenant_id == tenant_id,
            ShipmentItem.shipment_id == shipment.id,
            ShipmentItem.deleted_at.is_(None),
        )
        .order_by(ShipmentItem.line_no.asc(), ShipmentItem.created_at.asc())
    ).all()
    data = ShipmentRead.model_validate(shipment).model_dump(by_alias=True)
    data["items"] = [
        ShipmentItemRead.model_validate(item).model_dump(by_alias=True) for item in items
    ]
    return envelope(data)


@router.patch("/shipments/{shipment_id}", response_model=ShipmentEnvelope, response_model_exclude_unset=True)
def update_shipment(
    shipment_id: str,
    payload: UpdateShipmentRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "inventory.manage")
    shipment = get_active_document_or_404(db, Shipment, tenant_id, shipment_id)
    updates = payload.model_dump(exclude_unset=True)
    if "sales_order_id" in updates or "purchase_order_id" in updates:
        _require_order_coherence(
            db, tenant_id, shipment.direction,
            updates.get("sales_order_id", shipment.sales_order_id),
            updates.get("purchase_order_id", shipment.purchase_order_id),
        )
    if "status" in updates and updates["status"] != shipment.status:
        apply_status_change(db, actor, shipment, updates["status"])
        # lifecycle timestamps are facts of the transition; literal names
        # only, the sales-order convention — renamed states move without
        # stamping and the fact is PATCHed by whoever knows it
        if updates["status"] == "shipped" and shipment.shipped_at is None:
            shipment.shipped_at = datetime.now(timezone.utc)
        if updates["status"] in ("received", "delivered") and shipment.received_at is None:
            shipment.received_at = datetime.now(timezone.utc)
    if "custom_fields" in updates:
        shipment.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(shipment, field, value)
    db.commit()
    db.refresh(shipment)
    return envelope(ShipmentRead.model_validate(shipment).model_dump(by_alias=True))


@router.delete("/shipments/{shipment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shipment(
    shipment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "inventory.manage")
    return delete_document(db, actor, Shipment, shipment_id)


@router.post("/shipments/{shipment_id}/restore")
def restore_shipment(
    shipment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "inventory.manage")
    return restore_document(db, actor, Shipment, shipment_id)


@router.post("/shipments/{shipment_id}/post-stock", response_model=PostShipmentStockEnvelope)
def post_shipment_stock(
    shipment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The one bridge from freight to stock: one ledger movement per line
    that names a position, direction deciding the sign, the shipment line as
    provenance and the header's order FK carried through. Idempotent by
    refusal — the ledger is append-only, so running twice would double the
    goods, and the stamp is what makes the second call a loud 409 instead."""
    tenant_id = actor.tenant_id
    require_permission(actor, "inventory.manage")
    shipment = get_active_document_or_404(db, Shipment, tenant_id, shipment_id)
    if shipment.stock_posted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"this shipment's stock effect was posted at "
                f"{shipment.stock_posted_at.isoformat()} — the ledger is "
                "append-only; corrections are counter-entries, not re-posts"
            ),
        )
    lines = db.scalars(
        select(ShipmentItem).where(
            ShipmentItem.tenant_id == tenant_id,
            ShipmentItem.shipment_id == shipment.id,
            ShipmentItem.deleted_at.is_(None),
        )
    ).all()
    sign = 1 if shipment.direction == "inbound" else -1
    # the reason is the ledger's own vocabulary, and a customer return coming
    # back is `returned`, not `received` — otherwise the same semantic event
    # gets two words depending on which door it entered (the direct movement
    # path already says `returned`), and "how much came back from customers"
    # splits across both
    reason = "issued"
    if shipment.direction == "inbound":
        linked = None
        if shipment.sales_order_id:
            linked = db.get(SalesOrder, shipment.sales_order_id)
        elif shipment.purchase_order_id:
            linked = db.get(PurchaseOrder, shipment.purchase_order_id)
        reason = "returned" if linked is not None and linked.order_kind == "return" else "received"
    report: list[PostedStockLineRead] = []
    for line in lines:
        if line.inventory_item_id is None:
            report.append(PostedStockLineRead(
                shipment_item_id=line.id, outcome="skipped_no_position",
            ))
            continue
        position = get_scoped_or_404(db, InventoryItem, tenant_id, line.inventory_item_id)
        if position.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"inventory item {position.id} is archived — set it active "
                    "before posting this shipment's stock"
                ),
            )
        diff = sign * float(line.quantity)
        released = None
        if sign < 0 and shipment.sales_order_id:
            # goods held for this order stop being held as they leave: the
            # outstanding reservation for (position, order) is what the
            # `reserved`/`reservation_released` pair sums to, and releasing
            # up to this line's quantity in the same posting keeps ATP from
            # being deducted twice for stock already promised away
            outstanding = -float(db.scalar(
                select(func.coalesce(func.sum(InventoryItemDetail.available_to_promise_diff), 0))
                .where(
                    InventoryItemDetail.tenant_id == tenant_id,
                    InventoryItemDetail.inventory_item_id == position.id,
                    InventoryItemDetail.sales_order_id == shipment.sales_order_id,
                    InventoryItemDetail.reason.in_(("reserved", "reservation_released")),
                )
            ))
            if outstanding > 0:
                released = min(float(line.quantity), outstanding)
                post_inventory_detail(
                    db,
                    item=position,
                    quantity_on_hand_diff=0,
                    available_to_promise_diff=released,
                    reason="reservation_released",
                    description=(
                        f"shipment {shipment.shipment_no} consumes the hold"
                    ),
                    entity_type="shipment_item",
                    entity_id=line.id,
                    sales_order_id=shipment.sales_order_id,
                    created_by=attributed(actor, None),
                )
        post_inventory_detail(
            db,
            item=position,
            quantity_on_hand_diff=diff,
            reason=reason,
            description=f"shipment {shipment.shipment_no} line {line.line_no or ''}".strip(),
            entity_type="shipment_item",
            entity_id=line.id,
            sales_order_id=shipment.sales_order_id,
            purchase_order_id=shipment.purchase_order_id,
            created_by=attributed(actor, None),
        )
        report.append(PostedStockLineRead(
            shipment_item_id=line.id,
            inventory_item_id=position.id,
            quantity_on_hand_diff=diff,
            reservation_released=released,
            outcome="posted",
        ))
    shipment.stock_posted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(shipment)
    return envelope(PostShipmentStockRead(
        shipment_id=shipment.id,
        stock_posted_at=shipment.stock_posted_at,
        lines=report,
    ).model_dump(by_alias=True))


# --- lines ------------------------------------------------------------------


@router.get("/shipment-items", response_model=ShipmentItemListEnvelope, response_model_exclude_unset=True)
def list_shipment_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    shipment_id: str | None = None,
    product_id: str | None = None,
    inventory_item_id: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    return list_rows(
        db,
        select(ShipmentItem).where(
            ShipmentItem.tenant_id == tenant_id, ShipmentItem.deleted_at.is_(None)
        ),
        filters={
            ShipmentItem.shipment_id: shipment_id,
            ShipmentItem.product_id: product_id,
            ShipmentItem.inventory_item_id: inventory_item_id,
        },
        order_by=(ShipmentItem.created_at.asc(), ShipmentItem.id.asc()),
        pagination=requested_pagination(page, size),
        read_model=ShipmentItemRead,
    )


@router.post("/shipment-items", status_code=status.HTTP_201_CREATED, response_model=ShipmentItemEnvelope)
def create_shipment_item(
    payload: CreateShipmentItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "inventory.manage")
    shipment = get_active_document_or_404(db, Shipment, tenant_id, payload.shipment_id)
    ensure_document_editable(db, shipment)
    _require_line_position(
        db, tenant_id, payload.product_id, payload.sku_id, payload.inventory_item_id
    )
    item = ShipmentItem(
        tenant_id=tenant_id,
        shipment_id=shipment.id,
        line_no=payload.line_no,
        product_id=payload.product_id,
        sku_id=payload.sku_id,
        quantity=payload.quantity,
        inventory_item_id=payload.inventory_item_id,
        description=payload.description,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return envelope(ShipmentItemRead.model_validate(item).model_dump(by_alias=True))


@router.patch("/shipment-items/{item_id}", response_model=ShipmentItemEnvelope)
def update_shipment_item(
    item_id: str,
    payload: UpdateShipmentItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "inventory.manage")
    item = get_active_document_or_404(db, ShipmentItem, tenant_id, item_id)
    shipment = get_active_document_or_404(db, Shipment, tenant_id, item.shipment_id)
    ensure_document_editable(db, shipment)
    updates = payload.model_dump(exclude_unset=True)
    _require_line_position(
        db, tenant_id, item.product_id,
        updates.get("sku_id", item.sku_id),
        updates.get("inventory_item_id", item.inventory_item_id),
    )
    for field, value in updates.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return envelope(ShipmentItemRead.model_validate(item).model_dump(by_alias=True))


@router.delete("/shipment-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shipment_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "inventory.manage")
    item = get_active_document_or_404(db, ShipmentItem, tenant_id, item_id)
    shipment = get_active_document_or_404(db, Shipment, tenant_id, item.shipment_id)
    ensure_document_editable(db, shipment)
    item.deleted_at = datetime.now(timezone.utc)
    db.commit()

