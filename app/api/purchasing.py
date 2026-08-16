"""What we asked for, and what we committed to: purchase requests and orders.

Split out of `routes.py`: purchase requests and purchase orders, each with its
lines and its adjustments, plus the receive path.

The mirror of `sales.py`, and one module for the same reason: a purchase order
is written from a request, `load_lines_with_parents` walks both, and
`purchase_item_estimate` is what the request estimates and the order commits.

Imports run one way: this module reads `app.api.common` and no other endpoint
module, and nothing in `app/api` reads this one. Only `app/main.py` mounts its
router.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import (
    CENT,
    _run_document_import,
    allocate_number,
    apply_status_change,
    attachments_for_items,
    build_item,
    create_adjustment,
    create_item,
    delete_adjustment,
    delete_document,
    delete_item,
    document_approvals,
    ensure_content_edit_allowed,
    ensure_document_not_deleted,
    ensure_within_credit,
    envelope,
    exclude_rows_with_open_todo,
    get_active_document_or_404,
    get_adjustment,
    get_item,
    get_scoped_or_404,
    get_tenant_id,
    grouped_linked_lines,
    list_adjustments,
    list_items,
    list_rows,
    load_item_catalog_context,
    normalize_vendor_context,
    order_billed_on_account,
    page_only_pagination,
    recheck_charged_document,
    requested_pagination,
    require_line_on_document,
    require_machine_state,
    resolve_chargeable_account,
    resolve_item_refs,
    restore_document,
    sku_pending_flag,
    submit_document,
    update_adjustment,
    update_item,
)
from app.api.deps import Actor, attributed, enforce_member_employee, get_actor, require_permission
from app.db.session import get_db
from app.models import (
    Employee,
    InventoryItem,
    ProductSku,
    PurchaseOrder,
    PurchaseOrderAdjustment,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
    SalesOrder,
    SalesOrderItem,
    SupplierProduct,
    Vendor,
)
from app.schemas import (
    ApprovalRecordRead,
    AttachmentRead,
    BulkDocumentImportEnvelope,
    BulkPurchaseOrderImportRequest,
    CreatePurchaseOrderAdjustmentRequest,
    CreatePurchaseOrderItemRequest,
    CreatePurchaseOrderRequest,
    CreatePurchaseRequestItemRequest,
    CreatePurchaseRequestRequest,
    DeletePurchaseRequestRequest,
    LinkedPurchaseOrderItemRead,
    PurchaseOrderAdjustmentEnvelope,
    PurchaseOrderAdjustmentListEnvelope,
    PurchaseOrderAdjustmentRead,
    PurchaseOrderCreatedEnvelope,
    PurchaseOrderDetailEnvelope,
    PurchaseOrderDetailRead,
    PurchaseOrderEnvelope,
    PurchaseOrderItemDetailRead,
    PurchaseOrderItemEnvelope,
    PurchaseOrderItemListEnvelope,
    PurchaseOrderItemRead,
    PurchaseOrderListEnvelope,
    PurchaseOrderRead,
    PurchaseOrderRequestReferenceRead,
    PurchaseProductReferenceRead,
    PurchaseRequestDetailEnvelope,
    PurchaseRequestDetailRead,
    PurchaseRequestItemDetailRead,
    PurchaseRequestItemRead,
    PurchaseRequestListEnvelope,
    PurchaseRequestRead,
    PurchaseSalesOrderReferenceRead,
    PurchaseSkuReferenceRead,
    ReceivePurchaseOrderEnvelope,
    ReceivePurchaseOrderRequest,
    ReceivePurchaseOrderResult,
    ReceivedLineRead,
    RestorePurchaseRequestRequest,
    SubmitPurchaseRequestRequest,
    UpdatePurchaseOrderAdjustmentRequest,
    UpdatePurchaseOrderItemRequest,
    UpdatePurchaseOrderRequest,
    UpdatePurchaseRequestItemRequest,
    UpdatePurchaseRequestRequest,
)
from app.services.audit import record_audit
from app.services.inventory_import import _find_item as find_inventory_item, post_inventory_detail
from app.services.state_machines import validate_status_filter

router = APIRouter()


def load_lines_with_parents(
    db: Session, tenant_id: str, line_model, parent_model, parent_field: str, line_ids
) -> tuple[dict, dict]:
    """Cross-document link resolution: the linked lines by id, and their
    parent documents by id — two reads however many links there are."""
    if not line_ids:
        return {}, {}
    lines = db.scalars(
        select(line_model).where(line_model.tenant_id == tenant_id, line_model.id.in_(line_ids))
    ).all()
    lines_by_id = {line.id: line for line in lines}
    parent_ids = {getattr(line, parent_field) for line in lines}
    parents = (
        db.scalars(
            select(parent_model).where(parent_model.tenant_id == tenant_id, parent_model.id.in_(parent_ids))
        ).all()
        if parent_ids
        else []
    )
    return lines_by_id, {parent.id: parent for parent in parents}


def purchase_item_estimate(item: PurchaseRequestItem) -> float | None:
    """A line's estimated cost: explicit amount wins; otherwise derived from
    unit price; None when the line is unpriced (a normal fact, not an error)."""
    if item.amount is not None:
        return float(item.amount)
    if item.unit_price is not None:
        return float(item.unit_price) * float(item.quantity)
    return None


@router.post(
    "/purchase-orders/bulk",
    response_model=BulkDocumentImportEnvelope,
    response_model_exclude_unset=True,
)
def bulk_import_purchase_orders(
    payload: BulkPurchaseOrderImportRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Import historical purchase orders keyed on their own `po_number`.
    Every row must resolve a vendor (vendor_code or vendor_id) — a PO's
    counterparty is required, so snapshot mode never applies to it."""
    return _run_document_import(db=db, actor=actor, family="purchase_order", payload=payload)


# --- purchase requests: what somebody asked us to buy ------------------------


@router.get(
    "/purchase-requests",
    response_model=PurchaseRequestListEnvelope,
    response_model_exclude_unset=True,
)
def list_purchase_requests(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    vendor_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    without_open_todo: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    validate_status_filter(db, tenant_id, "purchase_request", status_filter)
    stmt = select(PurchaseRequest).where(PurchaseRequest.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(PurchaseRequest.deleted_at.is_(None))
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, PurchaseRequest, tenant_id, "purchase_request")
    return list_rows(
        db, stmt,
        filters={
            PurchaseRequest.employee_id: employee_id,
            PurchaseRequest.vendor_id: vendor_id,
            PurchaseRequest.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(PurchaseRequest.id, String),
            cast(PurchaseRequest.employee_id, String),
            PurchaseRequest.title,
            cast(PurchaseRequest.request_date, String),
            cast(PurchaseRequest.needed_by, String),
            PurchaseRequest.vendor_name_snapshot,
            PurchaseRequest.currency,
            PurchaseRequest.status,
            PurchaseRequest.source_report_text,
        ),
        order_by=(PurchaseRequest.created_at.desc(), PurchaseRequest.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=PurchaseRequestRead,
    )


@router.post("/purchase-requests", status_code=status.HTTP_201_CREATED)
def create_purchase_request(
    payload: CreatePurchaseRequestRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "purchase.submit_own")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    enforce_member_employee(actor, payload.employee_id)
    require_machine_state(db, tenant_id, PurchaseRequest, payload.status)
    vendor_id, vendor_name_snapshot = normalize_vendor_context(
        db, tenant_id, payload.vendor_id, payload.vendor_name_snapshot
    )
    request = PurchaseRequest(
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        title=payload.title,
        request_date=payload.request_date,
        needed_by=payload.needed_by,
        vendor_id=vendor_id,
        vendor_name_snapshot=vendor_name_snapshot,
        currency=payload.currency,
        status=payload.status,
        source_report_text=payload.source_report_text,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(request)
    db.flush()
    items = [
        build_item(db, actor, PurchaseRequestItem, row, parent=request)
        for row in payload.items
    ]
    db.commit()
    db.refresh(request)
    data = PurchaseRequestRead.model_validate(request).model_dump(by_alias=True)
    if items:
        data["items"] = [
            PurchaseRequestItemRead.model_validate(item).model_dump(by_alias=True)
            for item in items
        ]
    return envelope(data)


@router.get("/purchase-requests/{request_id}")
def get_purchase_request(
    request_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    request = get_scoped_or_404(db, PurchaseRequest, tenant_id, request_id)
    if not include_deleted:
        ensure_document_not_deleted(request)
    return envelope(PurchaseRequestRead.model_validate(request).model_dump(by_alias=True))


@router.patch("/purchase-requests/{request_id}")
def update_purchase_request(
    request_id: str,
    payload: UpdatePurchaseRequestRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    request = get_active_document_or_404(db, PurchaseRequest, tenant_id, request_id)
    # members only touch their own requests; approvers never patch status —
    # flow advancement is the workflow admin's write (service/admin credential)
    enforce_member_employee(actor, request.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    ensure_content_edit_allowed(actor, "purchase", updates)
    if "status" in updates and updates["status"] != request.status:
        # flow advancement is the workflow admin's write: members submit via
        # POST .../submit — never a raw status patch (no self-approval)
        apply_status_change(db, actor, request, updates["status"])
    if "vendor_id" in updates or "vendor_name_snapshot" in updates:
        vendor_id, vendor_name_snapshot = normalize_vendor_context(
            db,
            tenant_id,
            updates.get("vendor_id", request.vendor_id),
            updates.get("vendor_name_snapshot", request.vendor_name_snapshot),
        )
        request.vendor_id = vendor_id
        request.vendor_name_snapshot = vendor_name_snapshot
        updates.pop("vendor_id", None)
        updates.pop("vendor_name_snapshot", None)
    if "custom_fields" in updates:
        request.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(request, field, value)
    db.commit()
    db.refresh(request)
    return envelope(PurchaseRequestRead.model_validate(request).model_dump(by_alias=True))


@router.delete("/purchase-requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_request(
    request_id: str,
    payload: DeletePurchaseRequestRequest | None = None,
    actor: Annotated[Actor, Depends(get_actor)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    return delete_document(db, actor, PurchaseRequest, request_id, payload)


@router.post("/purchase-requests/{request_id}/restore")
def restore_purchase_request(
    request_id: str,
    payload: RestorePurchaseRequestRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, PurchaseRequest, request_id)


@router.post("/purchase-requests/{request_id}/submit")
def submit_purchase_request(
    request_id: str,
    payload: SubmitPurchaseRequestRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return submit_document(db, actor, PurchaseRequest, request_id)


@router.get(
    "/purchase-requests/{request_id}/detail",
    response_model=PurchaseRequestDetailEnvelope,
    response_model_exclude_unset=True,
)
def get_purchase_request_detail(
    request_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    request = get_scoped_or_404(db, PurchaseRequest, tenant_id, request_id)
    if not include_deleted:
        ensure_document_not_deleted(request)
    items = db.scalars(
        select(PurchaseRequestItem)
        .where(
            PurchaseRequestItem.tenant_id == tenant_id,
            PurchaseRequestItem.request_id == request_id,
            PurchaseRequestItem.deleted_at.is_(None),
        )
        .order_by(PurchaseRequestItem.created_at.asc())
    ).all()
    approvals = document_approvals(db, tenant_id, "purchase_request", request_id)
    attachments = attachments_for_items(db, tenant_id, items)
    skus_by_id, products_by_id, products_with_skus = load_item_catalog_context(db, tenant_id, items)
    # 按单采购 context: the sales order line (and its order) behind each
    # pinned purchase line, resolved in two reads for the whole document
    order_lines_by_id, orders_by_id = load_lines_with_parents(
        db, tenant_id, SalesOrderItem, SalesOrder, "order_id",
        {item.sales_order_item_id for item in items if item.sales_order_item_id},
    )
    # PO lines ordering each request line — the downstream half of the chain
    po_lines_by_request_line = grouped_linked_lines(
        db, tenant_id, PurchaseOrderItem, "purchase_request_item_id",
        PurchaseOrder, "po_id", [item.id for item in items],
        lambda line, po: LinkedPurchaseOrderItemRead(
            id=line.id,
            po_id=line.po_id,
            po_number=po.po_number,
            po_status=po.status,
            quantity=float(line.quantity),
            received_quantity=float(line.received_quantity),
            unit_price=float(line.unit_price) if line.unit_price is not None else None,
        ),
    )
    detail_items: list[PurchaseRequestItemDetailRead] = []
    for item in items:
        product, sku = resolve_item_refs(item, skus_by_id, products_by_id)
        detail_items.append(
            PurchaseRequestItemDetailRead(
                **PurchaseRequestItemRead.model_validate(item).model_dump(),
                product=(
                    PurchaseProductReferenceRead(
                        id=product.id,
                        product_code=product.product_code,
                        name=product.name,
                        spec=product.spec,
                        unit=product.unit,
                    )
                    if product is not None
                    else None
                ),
                sku=(
                    PurchaseSkuReferenceRead(
                        id=sku.id,
                        product_id=sku.product_id,
                        sku_code=sku.sku_code,
                        variant_attrs=sku.variant_attrs or {},
                    )
                    if sku is not None
                    else None
                ),
                sku_pending=sku_pending_flag(item, products_with_skus),
                sales_order=(
                    PurchaseSalesOrderReferenceRead(
                        sales_order_item_id=line.id,
                        order_id=order.id,
                        order_no=order.order_no,
                        order_status=order.status,
                        customer_name_snapshot=order.customer_name_snapshot,
                        quantity=float(line.quantity),
                    )
                    if (line := order_lines_by_id.get(item.sales_order_item_id or "")) is not None
                    and (order := orders_by_id.get(line.order_id)) is not None
                    else None
                ),
                purchase_order_items=po_lines_by_request_line.get(item.id, []),
            )
        )
    estimates = [purchase_item_estimate(item) for item in items]
    detail = PurchaseRequestDetailRead(
        request=PurchaseRequestRead.model_validate(request),
        items=detail_items,
        approval_records=[ApprovalRecordRead.model_validate(record) for record in approvals],
        attachments=[AttachmentRead.model_validate(attachment) for attachment in attachments],
        estimated_total=float(sum(e for e in estimates if e is not None)),
        unpriced_item_count=sum(1 for e in estimates if e is None),
        pending_sku_count=sum(1 for item in detail_items if item.sku_pending),
    )
    return envelope(detail.model_dump(by_alias=True))


@router.get("/purchase-request-items")
def list_purchase_request_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    request_id: str | None = None,
    product_id: str | None = None,
    sku_id: str | None = None,
):
    return list_items(db, tenant_id, PurchaseRequestItem, {"request_id": request_id, "product_id": product_id, "sku_id": sku_id})


@router.post("/purchase-request-items", status_code=status.HTTP_201_CREATED)
def create_purchase_request_item(
    payload: CreatePurchaseRequestItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return create_item(db, actor, PurchaseRequestItem, payload)


@router.get("/purchase-request-items/{item_id}")
def get_purchase_request_item(
    item_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    return get_item(db, tenant_id, PurchaseRequestItem, item_id)


@router.patch("/purchase-request-items/{item_id}")
def update_purchase_request_item(
    item_id: str,
    payload: UpdatePurchaseRequestItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return update_item(db, actor, PurchaseRequestItem, item_id, payload)


@router.delete("/purchase-request-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_request_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return delete_item(db, actor, PurchaseRequestItem, item_id)


# --- purchase orders: the commitment to a vendor -----------------------------


@router.get("/purchase-orders", response_model=PurchaseOrderListEnvelope, response_model_exclude_unset=True)
def list_purchase_orders(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    vendor_id: str | None = None,
    billing_account_id: str | None = None,
    employee_id: str | None = None,
    po_number: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    validate_status_filter(db, tenant_id, "purchase_order", status_filter)
    stmt = select(PurchaseOrder).where(
        PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.deleted_at.is_(None)
    )
    return list_rows(
        db, stmt,
        filters={
            PurchaseOrder.vendor_id: vendor_id,
            PurchaseOrder.billing_account_id: billing_account_id,
            PurchaseOrder.employee_id: employee_id,
            PurchaseOrder.po_number: po_number,
            PurchaseOrder.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            PurchaseOrder.title,
            PurchaseOrder.po_number,
            PurchaseOrder.vendor_name_snapshot,
            PurchaseOrder.contract_no,
        ),
        order_by=(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=PurchaseOrderRead,
    )


@router.post(
    "/purchase-orders",
    status_code=status.HTTP_201_CREATED,
    response_model=PurchaseOrderCreatedEnvelope,
    response_model_exclude_unset=True,
)
def create_purchase_order(
    payload: CreatePurchaseOrderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "purchase_order.manage")
    vendor = get_scoped_or_404(db, Vendor, tenant_id, payload.vendor_id)
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    require_machine_state(db, tenant_id, PurchaseOrder, payload.status)
    charged_account = None
    if payload.billing_account_id:
        # OUR standing account at this vendor: prepay, then order against it,
        # the vendor's credit covering what the deposit does not
        charged_account = resolve_chargeable_account(
            db, tenant_id, payload.billing_account_id,
            owner_field="vendor_id", owner_id=payload.vendor_id,
            currency=payload.currency, label="purchase order",
        )
    po_number = payload.po_number or allocate_number(db, PurchaseOrder, tenant_id)
    po = PurchaseOrder(
        tenant_id=tenant_id,
        po_number=po_number,
        vendor_id=payload.vendor_id,
        vendor_name_snapshot=payload.vendor_name_snapshot or vendor.name,
        employee_id=payload.employee_id,
        title=payload.title,
        contract_no=payload.contract_no,
        order_date=payload.order_date,
        promised_date=payload.promised_date,
        currency=payload.currency,
        billing_account_id=payload.billing_account_id,
        payment_terms=payload.payment_terms,
        delivery_terms=payload.delivery_terms,
        total_amount=payload.total_amount,
        status=payload.status,
        remarks=payload.remarks,
        source_report_text=payload.source_report_text,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(po)
    try:
        db.flush()
        # lines ride the same transaction, as on every other family
        items = [
            build_item(db, actor, PurchaseOrderItem, row, parent=po) for row in payload.items
        ]
        if charged_account is not None:
            ensure_within_credit(db, charged_account, label="purchase order")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"po_number {po_number!r} already exists in this workspace",
        )
    db.refresh(po)
    data = PurchaseOrderRead.model_validate(po).model_dump(by_alias=True)
    if items:
        data["items"] = [
            PurchaseOrderItemRead.model_validate(item).model_dump(by_alias=True) for item in items
        ]
    return envelope(data)


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrderEnvelope, response_model_exclude_unset=True)
def get_purchase_order(
    po_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    po = get_active_document_or_404(db, PurchaseOrder, tenant_id, po_id)
    return envelope(PurchaseOrderRead.model_validate(po).model_dump(by_alias=True))


@router.patch("/purchase-orders/{po_id}", response_model=PurchaseOrderEnvelope, response_model_exclude_unset=True)
def update_purchase_order(
    po_id: str,
    payload: UpdatePurchaseOrderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """One capability drives filing AND advancement: the PO is a procurement
    function, not a personal document, so there is no submit_own/advance
    split. Status moves are machine-guarded like every lifecycle."""
    tenant_id = actor.tenant_id
    require_permission(actor, "purchase_order.manage")
    po = get_active_document_or_404(db, PurchaseOrder, tenant_id, po_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("vendor_id"):
        vendor = get_scoped_or_404(db, Vendor, tenant_id, updates["vendor_id"])
        updates.setdefault("vendor_name_snapshot", vendor.name)
    if "status" in updates and updates["status"] != po.status:
        apply_status_change(db, actor, po, updates["status"])
    if "billing_account_id" in updates and updates["billing_account_id"] != po.billing_account_id:
        if po.billing_account_id and updates["billing_account_id"]:
            if order_billed_on_account(db, po, po.billing_account_id) > CENT:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "invoices have already billed this order against its "
                        "current account — clear the charge instead of switching it"
                    ),
                )
        if updates["billing_account_id"]:
            resolve_chargeable_account(
                db, tenant_id, updates["billing_account_id"],
                owner_field="vendor_id",
                owner_id=updates.get("vendor_id", po.vendor_id),
                currency=updates.get("currency", po.currency), label="purchase order",
            )
        # clearing is the cancellation-release path and is never guarded
    if "custom_fields" in updates:
        po.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(po, field, value)
    recheck_charged_document(db, po, label="purchase order")
    db.commit()
    db.refresh(po)
    return envelope(PurchaseOrderRead.model_validate(po).model_dump(by_alias=True))


@router.delete("/purchase-orders/{po_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order(
    po_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return delete_document(db, actor, PurchaseOrder, po_id)


@router.post("/purchase-orders/{po_id}/restore", response_model=PurchaseOrderEnvelope, response_model_exclude_unset=True)
def restore_purchase_order(
    po_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, PurchaseOrder, po_id)


@router.get("/purchase-order-items", response_model=PurchaseOrderItemListEnvelope, response_model_exclude_unset=True)
def list_purchase_order_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    po_id: str | None = None,
    purchase_request_item_id: str | None = None,
):
    return list_items(db, tenant_id, PurchaseOrderItem, {"po_id": po_id, "purchase_request_item_id": purchase_request_item_id})


@router.post(
    "/purchase-order-items",
    status_code=status.HTTP_201_CREATED,
    response_model=PurchaseOrderItemEnvelope,
    response_model_exclude_unset=True,
)
def create_purchase_order_item(
    payload: CreatePurchaseOrderItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return create_item(db, actor, PurchaseOrderItem, payload)


@router.get("/purchase-order-items/{item_id}", response_model=PurchaseOrderItemEnvelope, response_model_exclude_unset=True)
def get_purchase_order_item(
    item_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    return get_item(db, tenant_id, PurchaseOrderItem, item_id)


@router.patch("/purchase-order-items/{item_id}", response_model=PurchaseOrderItemEnvelope, response_model_exclude_unset=True)
def update_purchase_order_item(
    item_id: str,
    payload: UpdatePurchaseOrderItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return update_item(db, actor, PurchaseOrderItem, item_id, payload)


@router.delete("/purchase-order-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return delete_item(db, actor, PurchaseOrderItem, item_id)


@router.get("/purchase-order-adjustments", response_model=PurchaseOrderAdjustmentListEnvelope, response_model_exclude_unset=True)
def list_purchase_order_adjustments(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    po_id: str | None = None,
    po_item_id: str | None = None,
    adjustment_type: str | None = None,
):
    return list_adjustments(
        db, tenant_id, PurchaseOrderAdjustment,
        parent_id=po_id, item_id=po_item_id, adjustment_type=adjustment_type,
    )


@router.post(
    "/purchase-order-adjustments",
    status_code=status.HTTP_201_CREATED,
    response_model=PurchaseOrderAdjustmentEnvelope,
    response_model_exclude_unset=True,
)
def create_purchase_order_adjustment(
    payload: CreatePurchaseOrderAdjustmentRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return create_adjustment(db, actor, PurchaseOrderAdjustment, payload)


@router.get("/purchase-order-adjustments/{adjustment_id}", response_model=PurchaseOrderAdjustmentEnvelope, response_model_exclude_unset=True)
def get_purchase_order_adjustment(
    adjustment_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    return get_adjustment(db, tenant_id, PurchaseOrderAdjustment, adjustment_id)


@router.patch("/purchase-order-adjustments/{adjustment_id}", response_model=PurchaseOrderAdjustmentEnvelope, response_model_exclude_unset=True)
def update_purchase_order_adjustment(
    adjustment_id: str,
    payload: UpdatePurchaseOrderAdjustmentRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return update_adjustment(db, actor, PurchaseOrderAdjustment, adjustment_id, payload)


@router.delete("/purchase-order-adjustments/{adjustment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order_adjustment(
    adjustment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return delete_adjustment(db, actor, PurchaseOrderAdjustment, adjustment_id)


@router.get(
    "/purchase-orders/{po_id}/detail",
    response_model=PurchaseOrderDetailEnvelope,
    response_model_exclude_unset=True,
)
def get_purchase_order_detail(
    po_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    po = get_active_document_or_404(db, PurchaseOrder, tenant_id, po_id)
    items = db.scalars(
        select(PurchaseOrderItem)
        .where(
            PurchaseOrderItem.tenant_id == tenant_id,
            PurchaseOrderItem.po_id == po.id,
            PurchaseOrderItem.deleted_at.is_(None),
        )
        .order_by(
            PurchaseOrderItem.line_no.asc().nulls_last(),
            PurchaseOrderItem.created_at.asc(),
            PurchaseOrderItem.id.asc(),
        )
    ).all()
    skus_by_id, products_by_id, products_with_skus = load_item_catalog_context(db, tenant_id, items)
    # the request lines this PO orders, and their requests' statuses
    request_lines_by_id, requests_by_id = load_lines_with_parents(
        db, tenant_id, PurchaseRequestItem, PurchaseRequest, "request_id",
        {item.purchase_request_item_id for item in items if item.purchase_request_item_id},
    )
    detail_items: list[PurchaseOrderItemDetailRead] = []
    for item in items:
        product, sku = resolve_item_refs(item, skus_by_id, products_by_id)
        request_line = request_lines_by_id.get(item.purchase_request_item_id or "")
        request = requests_by_id.get(request_line.request_id) if request_line is not None else None
        detail_items.append(
            PurchaseOrderItemDetailRead(
                **PurchaseOrderItemRead.model_validate(item).model_dump(),
                product=(
                    PurchaseProductReferenceRead(
                        id=product.id,
                        product_code=product.product_code,
                        name=product.name,
                        spec=product.spec,
                        unit=product.unit,
                    )
                    if product is not None
                    else None
                ),
                sku=(
                    PurchaseSkuReferenceRead(
                        id=sku.id,
                        product_id=sku.product_id,
                        sku_code=sku.sku_code,
                        variant_attrs=sku.variant_attrs or {},
                    )
                    if sku is not None
                    else None
                ),
                sku_pending=sku_pending_flag(item, products_with_skus),
                purchase_request=(
                    PurchaseOrderRequestReferenceRead(
                        purchase_request_item_id=request_line.id,
                        request_id=request.id,
                        request_status=request.status,
                        quantity=float(request_line.quantity),
                    )
                    if request_line is not None and request is not None
                    else None
                ),
            )
        )
    adjustments = db.scalars(
        select(PurchaseOrderAdjustment)
        .where(
            PurchaseOrderAdjustment.tenant_id == tenant_id,
            PurchaseOrderAdjustment.po_id == po.id,
            PurchaseOrderAdjustment.deleted_at.is_(None),
        )
        .order_by(PurchaseOrderAdjustment.created_at.asc(), PurchaseOrderAdjustment.id.asc())
    ).all()
    approvals = document_approvals(db, tenant_id, "purchase_order", po.id)
    estimates = [purchase_item_estimate(item) for item in items]
    computed_total = float(sum(e for e in estimates if e is not None))
    adjustments_total = float(sum(adjustment.amount for adjustment in adjustments))
    detail = PurchaseOrderDetailRead(
        po=PurchaseOrderRead.model_validate(po),
        items=detail_items,
        adjustments=[PurchaseOrderAdjustmentRead.model_validate(adjustment) for adjustment in adjustments],
        approval_records=[ApprovalRecordRead.model_validate(record) for record in approvals],
        computed_total=computed_total,
        adjustments_total=adjustments_total,
        adjusted_total=computed_total + adjustments_total,
        ordered_quantity=float(sum(float(item.quantity) for item in items)),
        received_quantity=float(sum(float(item.received_quantity) for item in items)),
    )
    return envelope(detail.model_dump(by_alias=True))


@router.post(
    "/purchase-orders/{po_id}/receive",
    response_model=ReceivePurchaseOrderEnvelope,
    response_model_exclude_unset=True,
)
def receive_purchase_order(
    po_id: str,
    payload: ReceivePurchaseOrderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Record goods arriving against PO lines. Facts only, no status magic:
    received_quantity accumulates on each line, and a line given a `facility`
    also lands in the inventory ledger (reason `received`, entity pinned to
    the PO line). No facility = a 直发/零库存 receipt that never touches
    stock. The flow agent moves the PO's status when the facts support it.

    Deliberately NOT gated on status: the state names are tenant-editable, so
    the server cannot know which of them mean "receivable" — that judgment is
    the agent's. Over-receiving is likewise recorded as stated (超收 is a real
    thing); flagging it is conversation, not rejection.

    A vendor's price becomes their SupplierProduct.last_price when the link
    already exists — recording the freshest procurement fact — but a link is
    never invented here."""
    tenant_id = actor.tenant_id
    require_permission(actor, "purchase_order.manage")
    po = get_active_document_or_404(db, PurchaseOrder, tenant_id, po_id)
    results: list[ReceivedLineRead] = []
    for line in payload.lines:
        item = require_line_on_document(
            db, tenant_id, PurchaseOrderItem, "po_id", "po_item_id", po.id, line.po_item_id
        )
        inventory_item_id: str | None = None
        if line.facility is not None:
            product_id = item.product_id
            if product_id is None and item.sku_id is not None:
                sku = db.get(ProductSku, item.sku_id)
                product_id = sku.product_id if sku is not None else None
            if product_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "landing a receipt in inventory needs a cataloged product on the line — "
                        "free-text lines can be received without a facility"
                    ),
                )
            position = find_inventory_item(
                db, tenant_id, product_id, item.sku_id, line.facility, line.lot_id or ""
            )
            if position is None:
                position = InventoryItem(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    sku_id=item.sku_id,
                    facility=line.facility,
                    lot_id=line.lot_id or "",
                    bin_number=line.bin_number,
                    expire_date=line.expire_date,
                    unit_cost=line.unit_cost if line.unit_cost is not None else item.unit_price,
                )
                db.add(position)
                db.flush()
            post_inventory_detail(
                db,
                item=position,
                quantity_on_hand_diff=line.quantity,
                reason="received",
                description=f"PO {po.po_number} 收货：{line.quantity}{item.unit or ''}",
                entity_type="purchase_order_item",
                entity_id=item.id,
                unit_cost=line.unit_cost if line.unit_cost is not None else (
                    float(item.unit_price) if item.unit_price is not None else None
                ),
                created_by=attributed(actor, None),
            )
            inventory_item_id = position.id
        item.received_quantity = float(item.received_quantity) + float(line.quantity)
        # freshest procurement fact: update the existing supplier link's
        # last_price in place; never invent a link here
        if item.product_id and item.unit_price is not None:
            link = db.scalar(
                select(SupplierProduct).where(
                    SupplierProduct.tenant_id == tenant_id,
                    SupplierProduct.product_id == item.product_id,
                    SupplierProduct.vendor_id == po.vendor_id,
                )
            )
            if link is not None:
                link.last_price = item.unit_price
        results.append(
            ReceivedLineRead(
                po_item_id=item.id,
                received_quantity=float(item.received_quantity),
                inventory_item_id=inventory_item_id,
            )
        )
    record_audit(
        db,
        tenant_id=tenant_id,
        action="purchase_order.received",
        entity_type="purchase_order",
        entity_id=po.id,
        actor=actor.label,
        detail={
            "po_number": po.po_number,
            "lines": [
                {"po_item_id": r.po_item_id, "quantity": float(l.quantity), "facility": l.facility}
                for r, l in zip(results, payload.lines)
            ],
        },
    )
    db.commit()
    return envelope(ReceivePurchaseOrderResult(lines=results).model_dump())
