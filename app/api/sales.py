"""What we offered, and what they ordered: quotations and sales orders.

Split out of `routes.py`: sales quotations and sales orders, each with its
lines and its adjustments.

The two are one module because the second is written from the first. A
quotation an order quotes stops being a draft and becomes the BASELINE that
order is measured against — what was agreed, against what was ordered — which
is why `common.py`'s `ensure_not_consumed_by_an_order` exists and why
`quotation_item_effective_amount` is read from both sides here.

Imports run one way: this module reads `app.api.common` and no other endpoint
module, and nothing in `app/api` reads this one. Only `app/main.py` mounts its
router.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import (
    CENT,
    _run_document_import,
    allocate_number,
    apply_status_change,
    attachments_for_items,
    build_item,
    catalog_list_price,
    create_adjustment,
    create_item,
    delete_adjustment,
    delete_document,
    delete_item,
    document_approvals,
    ensure_content_edit_allowed,
    ensure_document_not_deleted,
    ensure_not_consumed_by_an_order,
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
    order_billed_on_account,
    recheck_charged_document,
    register_attachment_source,
    requested_pagination,
    require_machine_state,
    resolve_chargeable_account,
    resolve_item_refs,
    restore_document,
    retire_open_work_if_finished,
    serve_document_attachment,
    sku_pending_flag,
    submit_document,
    update_adjustment,
    update_item,
)
from app.api.deps import Actor, enforce_member_employee, get_actor, require_permission
from app.db.session import get_db
from app.models import (
    Customer,
    Employee,
    Project,
    PurchaseRequest,
    PurchaseRequestItem,
    SalesOrder,
    SalesOrderAdjustment,
    SalesOrderItem,
    SalesQuotation,
    SalesQuotationAdjustment,
    SalesQuotationItem,
)
from app.schemas import (
    ApprovalRecordRead,
    AttachmentRead,
    BulkDocumentImportEnvelope,
    BulkSalesOrderImportRequest,
    BulkSalesQuotationImportRequest,
    CloseSalesQuotationRequest,
    CreateSalesOrderAdjustmentRequest,
    CreateSalesOrderItemRequest,
    CreateSalesOrderRequest,
    CreateSalesQuotationAdjustmentRequest,
    CreateSalesQuotationItemRequest,
    CreateSalesQuotationRequest,
    DeleteSalesOrderRequest,
    DeleteSalesQuotationRequest,
    LinkedPurchaseItemRead,
    QuotationProductReferenceRead,
    QuotationSkuReferenceRead,
    QuoteDriftRead,
    RestoreSalesOrderRequest,
    RestoreSalesQuotationRequest,
    ReviseSalesQuotationRequest,
    SalesOrderAdjustmentEnvelope,
    SalesOrderAdjustmentListEnvelope,
    SalesOrderAdjustmentRead,
    SalesOrderDetailEnvelope,
    SalesOrderDetailRead,
    SalesOrderItemDetailRead,
    SalesOrderItemRead,
    SalesOrderListEnvelope,
    SalesOrderRead,
    SalesQuotationAdjustmentEnvelope,
    SalesQuotationAdjustmentListEnvelope,
    SalesQuotationAdjustmentRead,
    SalesQuotationDetailEnvelope,
    SalesQuotationDetailRead,
    SalesQuotationItemDetailRead,
    SalesQuotationItemRead,
    SalesQuotationListEnvelope,
    SalesQuotationRead,
    SendSalesQuotationRequest,
    SubmitSalesOrderRequest,
    SubmitSalesQuotationRequest,
    UpdateSalesOrderAdjustmentRequest,
    UpdateSalesOrderItemRequest,
    UpdateSalesOrderRequest,
    UpdateSalesQuotationAdjustmentRequest,
    UpdateSalesQuotationItemRequest,
    UpdateSalesQuotationRequest,
)
from app.services.audit import record_audit
from app.services.state_machines import (
    editable_states,
    get_builtin_machine,
    state_for_role,
    validate_status_filter,
    validate_transition,
)

router = APIRouter()


def document_total(declared, line_sum: float) -> tuple[float, str]:
    """What a document says it totals, and which fact answered.

    The contract every family here keeps: `total_amount` is the agreed total,
    and null means the line sum IS the total. Drift is only meaningful if the
    caller can see which of the two was used on each side.
    """
    if declared is None:
        return line_sum, "line_sum"
    return float(declared), "declared"


# --- quotations: what we offered, and how far the order drifted -------------


def quote_drift(
    db: Session,
    tenant_id: str,
    quotation,
    order_line_sum: float,
    order_declared,
) -> QuoteDriftRead | None:
    """Order total minus the quotation's — stated, never judged.

    Nothing is gated on it. What an acceptable gap is belongs to the tenant's
    workflow definition, which the flow agent reads; the server's part is that
    the number exists, is computed the same way every time, and is measured
    against a baseline `ensure_not_consumed_by_an_order` keeps from moving.
    """
    if quotation is None:
        return None
    items = db.scalars(
        select(SalesQuotationItem).where(
            SalesQuotationItem.tenant_id == tenant_id,
            SalesQuotationItem.quotation_id == quotation.id,
            SalesQuotationItem.deleted_at.is_(None),
        )
    ).all()
    adjustments = db.scalars(
        select(SalesQuotationAdjustment.amount).where(
            SalesQuotationAdjustment.tenant_id == tenant_id,
            SalesQuotationAdjustment.quotation_id == quotation.id,
            SalesQuotationAdjustment.deleted_at.is_(None),
        )
    ).all()
    line_sum = float(
        sum(
            amount
            for amount in (quotation_item_effective_amount(item) for item in items)
            if amount is not None
        )
    ) + float(sum(adjustments))

    quote_total, quote_basis = document_total(quotation.total_amount, line_sum)
    order_total, order_basis = document_total(order_declared, order_line_sum)
    amount = round(order_total - quote_total, 2)
    return QuoteDriftRead(
        quote_total=round(quote_total, 2),
        quote_basis=quote_basis,
        order_total=round(order_total, 2),
        order_basis=order_basis,
        amount=amount,
        percent=round(amount / quote_total * 100, 2) if quote_total else None,
    )


def normalize_customer_context(
    db: Session,
    tenant_id: str,
    customer_id: str | None,
    customer_name: str | None,
) -> tuple[str | None, str | None]:
    """Same contract as `common.py`'s normalize_vendor_context: a customer_id
    must be a real record (404 otherwise) and backfills the free-text snapshot;
    without one, the snapshot stands alone (a prospect not yet in master
    data)."""
    if not customer_id:
        return None, customer_name
    customer = get_scoped_or_404(db, Customer, tenant_id, customer_id)
    return customer.id, customer_name or customer.name


def quotation_item_effective_amount(item: SalesQuotationItem) -> float | None:
    """A line's quoted value: explicit amount wins, then unit price × quantity.
    A gift line without pricing is 0 by definition — never 'unpriced' — so
    giveaways don't read as missing facts or as 100% discounts."""
    if item.amount is not None:
        return float(item.amount)
    if item.unit_price is not None:
        return float(item.unit_price) * float(item.quantity)
    if item.is_gift:
        return 0.0
    return None


def normalize_order_quotation_context(
    db: Session,
    tenant_id: str,
    quotation_id: str | None,
    quote_number_snapshot: str | None,
) -> tuple[str | None, str | None]:
    """Same contract as the other FK+snapshot pairs: a quotation_id must be a
    real quotation (404 otherwise) and backfills the free-text quote-number
    snapshot; without one, the snapshot stands alone (or the order is simply
    quote-less — a legal fact)."""
    if not quotation_id:
        return None, quote_number_snapshot
    quotation = get_scoped_or_404(db, SalesQuotation, tenant_id, quotation_id)
    ensure_document_not_deleted(quotation)
    return quotation.id, quote_number_snapshot or quotation.quote_number


@router.post(
    "/sales-quotations/bulk",
    response_model=BulkDocumentImportEnvelope,
    response_model_exclude_unset=True,
)
def bulk_import_sales_quotations(
    payload: BulkSalesQuotationImportRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Import historical quotations keyed on their own `quote_number` — the
    migration path for a retired system's export."""
    return _run_document_import(db=db, actor=actor, family="quotation", payload=payload)


@router.post(
    "/sales-orders/bulk",
    response_model=BulkDocumentImportEnvelope,
    response_model_exclude_unset=True,
)
def bulk_import_sales_orders(
    payload: BulkSalesOrderImportRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Import historical orders keyed on their own `order_no`."""
    return _run_document_import(db=db, actor=actor, family="order", payload=payload)


@router.get("/sales-quotations", response_model=SalesQuotationListEnvelope, response_model_exclude_unset=True)
def list_sales_quotations(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    customer_id: str | None = None,
    quote_number: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    without_open_todo: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    validate_status_filter(db, tenant_id, "sales_quotation", status_filter)
    stmt = select(SalesQuotation).where(SalesQuotation.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(SalesQuotation.deleted_at.is_(None))
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, SalesQuotation, tenant_id, "sales_quotation")
    return list_rows(
        db, stmt,
        filters={
            SalesQuotation.employee_id: employee_id,
            SalesQuotation.customer_id: customer_id,
            SalesQuotation.quote_number: quote_number,
            SalesQuotation.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(SalesQuotation.id, String),
            cast(SalesQuotation.employee_id, String),
            SalesQuotation.quote_number,
            SalesQuotation.title,
            SalesQuotation.customer_name_snapshot,
            SalesQuotation.contact_name,
            SalesQuotation.currency,
            SalesQuotation.status,
            SalesQuotation.remarks,
            SalesQuotation.source_report_text,
        ),
        order_by=(SalesQuotation.created_at.desc(), SalesQuotation.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=SalesQuotationRead,
    )


@router.post("/sales-quotations", status_code=status.HTTP_201_CREATED)
def create_sales_quotation(
    payload: CreateSalesQuotationRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "quotation.submit_own")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    enforce_member_employee(actor, payload.employee_id)
    initial_status = require_machine_state(db, tenant_id, SalesQuotation, payload.status)
    customer_id, customer_name_snapshot = normalize_customer_context(
        db, tenant_id, payload.customer_id, payload.customer_name_snapshot
    )
    if payload.project_id:
        get_scoped_or_404(db, Project, tenant_id, payload.project_id)
    quote_number = payload.quote_number or allocate_number(db, SalesQuotation, tenant_id)
    quotation = SalesQuotation(
        tenant_id=tenant_id,
        quote_number=quote_number,
        revision_no=1,
        employee_id=payload.employee_id,
        customer_id=customer_id,
        customer_name_snapshot=customer_name_snapshot,
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        title=payload.title,
        project_id=payload.project_id,
        quote_date=payload.quote_date,
        valid_until=payload.valid_until,
        currency=payload.currency,
        payment_terms=payload.payment_terms,
        delivery_terms=payload.delivery_terms,
        total_amount=payload.total_amount,
        status=initial_status,
        remarks=payload.remarks,
        source_report_text=payload.source_report_text,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(quotation)
    try:
        db.flush()
        # inline lines ride the same transaction: one bad row rolls back the
        # whole document, so a validation error can never leave a half-built
        # draft behind — and a three-line quote is one call, not four
        items = [
            build_item(db, actor, SalesQuotationItem, row, parent=quotation)
            for row in payload.items
        ]
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"quote_number {quote_number!r} already exists",
        )
    db.refresh(quotation)
    data = SalesQuotationRead.model_validate(quotation).model_dump(by_alias=True)
    if items:
        # the response IS the read-back: what landed, line by line
        data["items"] = [
            SalesQuotationItemRead.model_validate(item).model_dump(by_alias=True)
            for item in items
        ]
    return envelope(data)


@router.get("/sales-quotations/{quotation_id}")
def get_sales_quotation(
    quotation_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    quotation = get_scoped_or_404(db, SalesQuotation, tenant_id, quotation_id)
    if not include_deleted:
        ensure_document_not_deleted(quotation)
    return envelope(SalesQuotationRead.model_validate(quotation).model_dump(by_alias=True))


@router.patch("/sales-quotations/{quotation_id}")
def update_sales_quotation(
    quotation_id: str,
    payload: UpdateSalesQuotationRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    quotation = get_active_document_or_404(db, SalesQuotation, tenant_id, quotation_id)
    # members only touch their own quotations; approvers never patch status —
    # flow advancement is the workflow admin's write (service/admin credential)
    enforce_member_employee(actor, quotation.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    ensure_content_edit_allowed(actor, "quotation", updates)
    # Status still moves: an order existing does not stop the quotation's own
    # lifecycle from being recorded (`accepted`, `expired`). What freezes is
    # what the order was measured against — the content and the money.
    if any(field != "status" for field in updates):
        ensure_not_consumed_by_an_order(db, quotation)
    if "status" in updates and updates["status"] != quotation.status:
        # flow advancement is the workflow admin's write: members submit via
        # POST .../submit — never a raw status patch (no self-approval)
        apply_status_change(db, actor, quotation, updates["status"])
        # lifecycle timestamps are facts of the transition, whoever drives it
        # (e.g. the flow admin's expired sweep)
        if updates["status"] == "sent" and quotation.sent_at is None:
            quotation.sent_at = datetime.now(timezone.utc)
        if updates["status"] in ("accepted", "declined", "expired") and quotation.closed_at is None:
            quotation.closed_at = datetime.now(timezone.utc)
    if "customer_id" in updates or "customer_name_snapshot" in updates:
        customer_id, customer_name_snapshot = normalize_customer_context(
            db,
            tenant_id,
            updates.get("customer_id", quotation.customer_id),
            updates.get("customer_name_snapshot", quotation.customer_name_snapshot),
        )
        quotation.customer_id = customer_id
        quotation.customer_name_snapshot = customer_name_snapshot
        updates.pop("customer_id", None)
        updates.pop("customer_name_snapshot", None)
    if "project_id" in updates and updates["project_id"]:
        get_scoped_or_404(db, Project, tenant_id, updates["project_id"])
    if "custom_fields" in updates:
        quotation.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(quotation, field, value)
    db.commit()
    db.refresh(quotation)
    return envelope(SalesQuotationRead.model_validate(quotation).model_dump(by_alias=True))


@router.delete("/sales-quotations/{quotation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sales_quotation(
    quotation_id: str,
    payload: DeleteSalesQuotationRequest | None = None,
    actor: Annotated[Actor, Depends(get_actor)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    quotation = get_scoped_or_404(db, SalesQuotation, actor.tenant_id, quotation_id)
    if quotation.deleted_at is None:
        # archiving it would take the baseline out from under a live order just
        # as surely as editing it
        ensure_not_consumed_by_an_order(db, quotation)
    return delete_document(db, actor, SalesQuotation, quotation_id, payload)


@router.post("/sales-quotations/{quotation_id}/restore")
def restore_sales_quotation(
    quotation_id: str,
    payload: RestoreSalesQuotationRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, SalesQuotation, quotation_id)


@router.post("/sales-quotations/{quotation_id}/submit")
def submit_sales_quotation(
    quotation_id: str,
    payload: SubmitSalesQuotationRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return submit_document(db, actor, SalesQuotation, quotation_id)


@router.post("/sales-quotations/{quotation_id}/send")
def send_sales_quotation(
    quotation_id: str,
    payload: SendSalesQuotationRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The sales rep's own lifecycle write: the quotation went out to the
    customer. A fact registration, not an approval — the approval segment is
    already behind it (machine: approved → sent)."""
    quotation = get_active_document_or_404(db, SalesQuotation, actor.tenant_id, quotation_id)
    require_permission(actor, "quotation.submit_own")
    enforce_member_employee(actor, quotation.employee_id)
    if quotation.status == "sent":
        # idempotent resend
        return envelope(SalesQuotationRead.model_validate(quotation).model_dump(by_alias=True))
    machine = get_builtin_machine(db, actor.tenant_id, "sales_quotation")
    sent = state_for_role(machine, "sales_quotation", "sent")
    validate_transition(machine, quotation.status, sent, subject="sales_quotation")
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="quotation.sent",
        entity_type="sales_quotation",
        entity_id=quotation.id,
        actor=actor.label,
        detail={
            "employee_id": quotation.employee_id,
            "quote_number": quotation.quote_number,
            "revision_no": quotation.revision_no,
            "title": quotation.title,
            "from": quotation.status,
        },
    )
    quotation.status = sent
    quotation.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(quotation)
    return envelope(SalesQuotationRead.model_validate(quotation).model_dump(by_alias=True))


@router.post("/sales-quotations/{quotation_id}/close")
def close_sales_quotation(
    quotation_id: str,
    payload: CloseSalesQuotationRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Customer outcome registration (accepted / declined / expired) by the
    owning rep. The flow admin can reach the same states via status PATCH
    (e.g. the expired sweep)."""
    quotation = get_active_document_or_404(db, SalesQuotation, actor.tenant_id, quotation_id)
    require_permission(actor, "quotation.submit_own")
    enforce_member_employee(actor, quotation.employee_id)
    if quotation.status == payload.outcome:
        # idempotent re-close
        return envelope(SalesQuotationRead.model_validate(quotation).model_dump(by_alias=True))
    machine = get_builtin_machine(db, actor.tenant_id, "sales_quotation")
    validate_transition(machine, quotation.status, payload.outcome, subject="sales_quotation")
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="quotation.closed",
        entity_type="sales_quotation",
        entity_id=quotation.id,
        actor=actor.label,
        detail={
            "employee_id": quotation.employee_id,
            "quote_number": quotation.quote_number,
            "revision_no": quotation.revision_no,
            "title": quotation.title,
            "from": quotation.status,
            "to": payload.outcome,
            "outcome_note": payload.outcome_note,
        },
    )
    retire_open_work_if_finished(
        db, actor, machine, "sales_quotation", quotation.id,
        current=quotation.status, new_status=payload.outcome,
        editable=editable_states(machine, "sales_quotation"),
    )
    quotation.status = payload.outcome
    quotation.closed_at = datetime.now(timezone.utc)
    if payload.outcome_note is not None:
        quotation.outcome_note = payload.outcome_note
    db.commit()
    db.refresh(quotation)
    return envelope(SalesQuotationRead.model_validate(quotation).model_dump(by_alias=True))


@router.post("/sales-quotations/{quotation_id}/revise", status_code=status.HTTP_201_CREATED)
def revise_sales_quotation(
    quotation_id: str,
    payload: ReviseSalesQuotationRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Renegotiation: an approved/sent quotation is an immutable fact, so a
    price change issues a new draft revision under the same quote_number and
    steps the source aside (superseded). Line facts are copied; catalog
    snapshots refresh to quoting-time truth for lines still on the catalog."""
    tenant_id = actor.tenant_id
    source = get_active_document_or_404(db, SalesQuotation, tenant_id, quotation_id)
    require_permission(actor, "quotation.submit_own")
    enforce_member_employee(actor, source.employee_id)
    machine = get_builtin_machine(db, tenant_id, "sales_quotation")
    superseded = state_for_role(machine, "sales_quotation", "superseded")
    if source.status == superseded:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="quotation is already superseded; revise the live revision instead",
        )
    validate_transition(machine, source.status, superseded, subject="sales_quotation")
    next_revision = (
        db.scalar(
            select(func.max(SalesQuotation.revision_no)).where(
                SalesQuotation.tenant_id == tenant_id,
                SalesQuotation.quote_number == source.quote_number,
            )
        )
        or source.revision_no
    ) + 1
    revision = SalesQuotation(
        tenant_id=tenant_id,
        quote_number=source.quote_number,
        revision_no=next_revision,
        revision_of_id=source.id,
        employee_id=source.employee_id,
        customer_id=source.customer_id,
        customer_name_snapshot=source.customer_name_snapshot,
        contact_name=source.contact_name,
        contact_phone=source.contact_phone,
        contact_email=source.contact_email,
        title=source.title,
        project_id=source.project_id,
        quote_date=source.quote_date,
        valid_until=source.valid_until,
        currency=source.currency,
        payment_terms=source.payment_terms,
        delivery_terms=source.delivery_terms,
        total_amount=source.total_amount,
        # the machine's own initial — "draft" is the shipped machine's word,
        # not necessarily this workspace's
        status=machine["initial"],
        remarks=source.remarks,
        custom_fields_jsonb=dict(source.custom_fields_jsonb or {}),
    )
    db.add(revision)
    db.flush()
    items = db.scalars(
        select(SalesQuotationItem)
        .where(
            SalesQuotationItem.tenant_id == tenant_id,
            SalesQuotationItem.quotation_id == source.id,
            SalesQuotationItem.deleted_at.is_(None),
        )
        .order_by(SalesQuotationItem.line_no.asc().nulls_last(), SalesQuotationItem.created_at.asc())
    ).all()
    copied_items: dict[str, SalesQuotationItem] = {}
    for item in items:
        catalog_price = (
            catalog_list_price(db, tenant_id, item.product_id, item.sku_id)
            if (item.product_id or item.sku_id)
            else item.list_price_snapshot
        )
        copy = SalesQuotationItem(
            tenant_id=tenant_id,
            quotation_id=revision.id,
            line_no=item.line_no,
            product_id=item.product_id,
            sku_id=item.sku_id,
            product_name_snapshot=item.product_name_snapshot,
            spec=item.spec,
            quantity=item.quantity,
            unit=item.unit,
            list_price_snapshot=catalog_price,
            unit_price=item.unit_price,
            amount=item.amount,
            tax_rate=item.tax_rate,
            is_gift=item.is_gift,
            lead_time=item.lead_time,
            attachment_id=item.attachment_id,
            notes=item.notes,
            custom_fields_jsonb=dict(item.custom_fields_jsonb or {}),
        )
        db.add(copy)
        copied_items[item.id] = copy
    db.flush()
    # Adjustments ride along: the negotiation continues from the same 折扣/税/
    # 运费 facts. Line-pinned ones remap to the copied line; one pinned to a
    # line that was deleted (and so not copied) is orphaned and stays behind.
    adjustments = db.scalars(
        select(SalesQuotationAdjustment).where(
            SalesQuotationAdjustment.tenant_id == tenant_id,
            SalesQuotationAdjustment.quotation_id == source.id,
            SalesQuotationAdjustment.deleted_at.is_(None),
        )
    ).all()
    for adjustment in adjustments:
        if adjustment.quotation_item_id and adjustment.quotation_item_id not in copied_items:
            continue
        db.add(
            SalesQuotationAdjustment(
                tenant_id=tenant_id,
                quotation_id=revision.id,
                quotation_item_id=(
                    copied_items[adjustment.quotation_item_id].id
                    if adjustment.quotation_item_id
                    else None
                ),
                adjustment_type=adjustment.adjustment_type,
                description=adjustment.description,
                amount=adjustment.amount,
                source_percentage=adjustment.source_percentage,
                metadata_jsonb=dict(adjustment.metadata_jsonb or {}),
            )
        )
    record_audit(
        db,
        tenant_id=tenant_id,
        action="quotation.revised",
        entity_type="sales_quotation",
        entity_id=source.id,
        actor=actor.label,
        detail={
            "employee_id": source.employee_id,
            "quote_number": source.quote_number,
            "from_revision": source.revision_no,
            "to_revision": revision.revision_no,
            "new_quotation_id": revision.id,
            "reason": payload.reason,
        },
    )
    # The revision carries the negotiation forward; whatever was outstanding on
    # the superseded one is outstanding on nothing.
    retire_open_work_if_finished(
        db, actor, machine, "sales_quotation", source.id,
        current=source.status, new_status=superseded,
        editable=editable_states(machine, "sales_quotation"),
    )
    source.status = superseded
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a concurrent revision was created; retry against the live revision",
        )
    db.refresh(revision)
    return envelope(SalesQuotationRead.model_validate(revision).model_dump(by_alias=True))


@router.get(
    "/sales-quotations/{quotation_id}/detail",
    response_model=SalesQuotationDetailEnvelope,
    response_model_exclude_unset=True,
)
def get_sales_quotation_detail(
    quotation_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    quotation = get_scoped_or_404(db, SalesQuotation, tenant_id, quotation_id)
    if not include_deleted:
        ensure_document_not_deleted(quotation)
    items = db.scalars(
        select(SalesQuotationItem)
        .where(
            SalesQuotationItem.tenant_id == tenant_id,
            SalesQuotationItem.quotation_id == quotation_id,
            SalesQuotationItem.deleted_at.is_(None),
        )
        .order_by(SalesQuotationItem.line_no.asc().nulls_last(), SalesQuotationItem.created_at.asc())
    ).all()
    approvals = document_approvals(db, tenant_id, "sales_quotation", quotation_id)
    revisions = db.scalars(
        select(SalesQuotation)
        .where(
            SalesQuotation.tenant_id == tenant_id,
            SalesQuotation.quote_number == quotation.quote_number,
            SalesQuotation.deleted_at.is_(None),
        )
        .order_by(SalesQuotation.revision_no.asc())
    ).all()
    attachments = attachments_for_items(db, tenant_id, items)
    skus_by_id, products_by_id, products_with_skus = load_item_catalog_context(db, tenant_id, items)
    detail_items: list[SalesQuotationItemDetailRead] = []
    for item in items:
        product, sku = resolve_item_refs(item, skus_by_id, products_by_id)
        detail_items.append(
            SalesQuotationItemDetailRead(
                **SalesQuotationItemRead.model_validate(item).model_dump(),
                product=(
                    QuotationProductReferenceRead(
                        id=product.id,
                        product_code=product.product_code,
                        name=product.name,
                        spec=product.spec,
                        unit=product.unit,
                        list_price=float(product.list_price) if product.list_price is not None else None,
                    )
                    if product is not None
                    else None
                ),
                sku=(
                    QuotationSkuReferenceRead(
                        id=sku.id,
                        product_id=sku.product_id,
                        sku_code=sku.sku_code,
                        variant_attrs=sku.variant_attrs or {},
                        list_price=float(sku.list_price) if sku.list_price is not None else None,
                    )
                    if sku is not None
                    else None
                ),
                sku_pending=sku_pending_flag(item, products_with_skus),
            )
        )
    effective_amounts = [quotation_item_effective_amount(item) for item in items]
    adjustments = db.scalars(
        select(SalesQuotationAdjustment)
        .where(
            SalesQuotationAdjustment.tenant_id == tenant_id,
            SalesQuotationAdjustment.quotation_id == quotation.id,
            SalesQuotationAdjustment.deleted_at.is_(None),
        )
        .order_by(SalesQuotationAdjustment.created_at.asc(), SalesQuotationAdjustment.id.asc())
    ).all()
    computed_total = float(sum(amount for amount in effective_amounts if amount is not None))
    adjustments_total = float(sum(adjustment.amount for adjustment in adjustments))
    detail = SalesQuotationDetailRead(
        quotation=SalesQuotationRead.model_validate(quotation),
        items=detail_items,
        approval_records=[ApprovalRecordRead.model_validate(record) for record in approvals],
        attachments=[AttachmentRead.model_validate(attachment) for attachment in attachments],
        revisions=[SalesQuotationRead.model_validate(revision) for revision in revisions],
        adjustments=[SalesQuotationAdjustmentRead.model_validate(adjustment) for adjustment in adjustments],
        computed_total=computed_total,
        adjustments_total=adjustments_total,
        adjusted_total=computed_total + adjustments_total,
        unpriced_item_count=sum(1 for amount in effective_amounts if amount is None),
        pending_sku_count=sum(1 for item in detail_items if item.sku_pending),
    )
    return envelope(detail.model_dump(by_alias=True))


@router.get("/sales-quotation-items")
def list_sales_quotation_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    quotation_id: str | None = None,
    product_id: str | None = None,
    sku_id: str | None = None,
):
    return list_items(db, tenant_id, SalesQuotationItem, {"quotation_id": quotation_id, "product_id": product_id, "sku_id": sku_id})


@router.post("/sales-quotation-items", status_code=status.HTTP_201_CREATED)
def create_sales_quotation_item(
    payload: CreateSalesQuotationItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return create_item(db, actor, SalesQuotationItem, payload)


@router.get("/sales-quotation-items/{item_id}")
def get_sales_quotation_item(
    item_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    return get_item(db, tenant_id, SalesQuotationItem, item_id)


@router.patch("/sales-quotation-items/{item_id}")
def update_sales_quotation_item(
    item_id: str,
    payload: UpdateSalesQuotationItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return update_item(db, actor, SalesQuotationItem, item_id, payload)


@router.delete("/sales-quotation-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sales_quotation_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return delete_item(db, actor, SalesQuotationItem, item_id)


@router.get("/sales-quotation-adjustments", response_model=SalesQuotationAdjustmentListEnvelope, response_model_exclude_unset=True)
def list_sales_quotation_adjustments(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    quotation_id: str | None = None,
    quotation_item_id: str | None = None,
    adjustment_type: str | None = None,
):
    return list_adjustments(
        db, tenant_id, SalesQuotationAdjustment,
        parent_id=quotation_id, item_id=quotation_item_id, adjustment_type=adjustment_type,
    )


@router.post(
    "/sales-quotation-adjustments",
    status_code=status.HTTP_201_CREATED,
    response_model=SalesQuotationAdjustmentEnvelope,
    response_model_exclude_unset=True,
)
def create_sales_quotation_adjustment(
    payload: CreateSalesQuotationAdjustmentRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return create_adjustment(db, actor, SalesQuotationAdjustment, payload)


@router.get("/sales-quotation-adjustments/{adjustment_id}", response_model=SalesQuotationAdjustmentEnvelope, response_model_exclude_unset=True)
def get_sales_quotation_adjustment(
    adjustment_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    return get_adjustment(db, tenant_id, SalesQuotationAdjustment, adjustment_id)


@router.patch("/sales-quotation-adjustments/{adjustment_id}", response_model=SalesQuotationAdjustmentEnvelope, response_model_exclude_unset=True)
def update_sales_quotation_adjustment(
    adjustment_id: str,
    payload: UpdateSalesQuotationAdjustmentRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return update_adjustment(db, actor, SalesQuotationAdjustment, adjustment_id, payload)


@router.delete("/sales-quotation-adjustments/{adjustment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sales_quotation_adjustment(
    adjustment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return delete_adjustment(db, actor, SalesQuotationAdjustment, adjustment_id)


# --- sales orders: what they actually ordered --------------------------------


@router.get("/sales-orders", response_model=SalesOrderListEnvelope, response_model_exclude_unset=True)
def list_sales_orders(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    customer_id: str | None = None,
    billing_account_id: str | None = None,
    quotation_id: str | None = None,
    order_no: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    without_open_todo: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    validate_status_filter(db, tenant_id, "sales_order", status_filter)
    stmt = select(SalesOrder).where(SalesOrder.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(SalesOrder.deleted_at.is_(None))
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, SalesOrder, tenant_id, "sales_order")
    return list_rows(
        db, stmt,
        filters={
            SalesOrder.employee_id: employee_id,
            SalesOrder.customer_id: customer_id,
            SalesOrder.billing_account_id: billing_account_id,
            SalesOrder.quotation_id: quotation_id,
            SalesOrder.order_no: order_no,
            SalesOrder.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(SalesOrder.id, String),
            cast(SalesOrder.employee_id, String),
            SalesOrder.order_no,
            SalesOrder.source_quote_number,
            SalesOrder.title,
            SalesOrder.customer_name_snapshot,
            SalesOrder.contract_no,
            SalesOrder.logistics_tracking_no,
            SalesOrder.currency,
            SalesOrder.status,
            SalesOrder.remarks,
            SalesOrder.source_report_text,
        ),
        order_by=(SalesOrder.created_at.desc(), SalesOrder.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=SalesOrderRead,
    )


@router.post("/sales-orders", status_code=status.HTTP_201_CREATED)
def create_sales_order(
    payload: CreateSalesOrderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "order.submit_own")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    enforce_member_employee(actor, payload.employee_id)
    initial_status = require_machine_state(db, tenant_id, SalesOrder, payload.status)
    quotation_id, source_quote_number = normalize_order_quotation_context(
        db, tenant_id, payload.quotation_id, payload.source_quote_number
    )
    customer_id, customer_name_snapshot = normalize_customer_context(
        db, tenant_id, payload.customer_id, payload.customer_name_snapshot
    )
    if payload.project_id:
        get_scoped_or_404(db, Project, tenant_id, payload.project_id)
    charged_account = None
    if payload.billing_account_id:
        # paying by account: the order OCCUPIES the account's credit from this
        # moment — the wait between order and invoice (缺货两天,toB 数月) is
        # exactly where the same balance must not back two orders
        charged_account = resolve_chargeable_account(
            db, tenant_id, payload.billing_account_id,
            owner_field="customer_id", owner_id=customer_id,
            currency=payload.currency, label="sales order",
        )
    order_no = payload.order_no or allocate_number(db, SalesOrder, tenant_id)
    order = SalesOrder(
        tenant_id=tenant_id,
        order_no=order_no,
        quotation_id=quotation_id,
        source_quote_number=source_quote_number,
        employee_id=payload.employee_id,
        customer_id=customer_id,
        customer_name_snapshot=customer_name_snapshot,
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
        ship_to_address=payload.ship_to_address,
        title=payload.title,
        project_id=payload.project_id,
        contract_no=payload.contract_no,
        order_date=payload.order_date,
        promised_date=payload.promised_date,
        currency=payload.currency,
        billing_account_id=payload.billing_account_id,
        payment_terms=payload.payment_terms,
        delivery_terms=payload.delivery_terms,
        total_amount=payload.total_amount,
        status=initial_status,
        logistics_company=payload.logistics_company,
        logistics_tracking_no=payload.logistics_tracking_no,
        remarks=payload.remarks,
        source_report_text=payload.source_report_text,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(order)
    try:
        db.flush()
        items = [
            build_item(db, actor, SalesOrderItem, row, parent=order)
            for row in payload.items
        ]
        if charged_account is not None:
            # after the lines, so occupation counts what the order actually says
            ensure_within_credit(db, charged_account, label="sales order")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"order_no {order_no!r} already exists",
        )
    db.refresh(order)
    data = SalesOrderRead.model_validate(order).model_dump(by_alias=True)
    if items:
        data["items"] = [
            SalesOrderItemRead.model_validate(item).model_dump(by_alias=True)
            for item in items
        ]
    return envelope(data)


@router.get("/sales-orders/{order_id}")
def get_sales_order(
    order_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    order = get_scoped_or_404(db, SalesOrder, tenant_id, order_id)
    if not include_deleted:
        ensure_document_not_deleted(order)
    return envelope(SalesOrderRead.model_validate(order).model_dump(by_alias=True))


@router.patch("/sales-orders/{order_id}")
def update_sales_order(
    order_id: str,
    payload: UpdateSalesOrderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    order = get_active_document_or_404(db, SalesOrder, tenant_id, order_id)
    # members only touch their own orders; approvers never patch status —
    # flow advancement is the workflow admin's write (service/admin credential)
    enforce_member_employee(actor, order.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    ensure_content_edit_allowed(actor, "order", updates)
    if "status" in updates and updates["status"] != order.status:
        # flow advancement is the workflow admin's write: members submit via
        # POST .../submit — never a raw status patch (no self-approval)
        apply_status_change(db, actor, order, updates["status"])
        # lifecycle timestamps are facts of the transition, whoever drives it
        if updates["status"] == "shipped" and order.shipped_at is None:
            order.shipped_at = datetime.now(timezone.utc)
        if updates["status"] in ("signed", "delivered", "completed") and order.signed_at is None:
            order.signed_at = datetime.now(timezone.utc)
    if "quotation_id" in updates or "source_quote_number" in updates:
        quotation_id, source_quote_number = normalize_order_quotation_context(
            db,
            tenant_id,
            updates.get("quotation_id", order.quotation_id),
            updates.get("source_quote_number", order.source_quote_number),
        )
        order.quotation_id = quotation_id
        order.source_quote_number = source_quote_number
        updates.pop("quotation_id", None)
        updates.pop("source_quote_number", None)
    if "customer_id" in updates or "customer_name_snapshot" in updates:
        customer_id, customer_name_snapshot = normalize_customer_context(
            db,
            tenant_id,
            updates.get("customer_id", order.customer_id),
            updates.get("customer_name_snapshot", order.customer_name_snapshot),
        )
        order.customer_id = customer_id
        order.customer_name_snapshot = customer_name_snapshot
        updates.pop("customer_id", None)
        updates.pop("customer_name_snapshot", None)
    if "project_id" in updates and updates["project_id"]:
        get_scoped_or_404(db, Project, tenant_id, updates["project_id"])
    if "billing_account_id" in updates and updates["billing_account_id"] != order.billing_account_id:
        if order.billing_account_id and updates["billing_account_id"]:
            # switching accounts under invoices already billed against the old
            # one would double-count the obligation across both; clear first,
            # or move the invoices with it
            if order_billed_on_account(db, order, order.billing_account_id) > CENT:
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
                owner_field="customer_id",
                owner_id=updates.get("customer_id", order.customer_id),
                currency=updates.get("currency", order.currency), label="sales order",
            )
        # clearing (None) is the release path — cancellation's explicit write —
        # and needs no guard: freeing credit is always safe
    if "custom_fields" in updates:
        order.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(order, field, value)
    # any edit to a charged order re-runs the occupation guard: amounts grow
    recheck_charged_document(db, order, label="sales order")
    db.commit()
    db.refresh(order)
    return envelope(SalesOrderRead.model_validate(order).model_dump(by_alias=True))


@router.delete("/sales-orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sales_order(
    order_id: str,
    payload: DeleteSalesOrderRequest | None = None,
    actor: Annotated[Actor, Depends(get_actor)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    return delete_document(db, actor, SalesOrder, order_id, payload)


@router.post("/sales-orders/{order_id}/restore")
def restore_sales_order(
    order_id: str,
    payload: RestoreSalesOrderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, SalesOrder, order_id)


@router.post("/sales-orders/{order_id}/submit")
def submit_sales_order(
    order_id: str,
    payload: SubmitSalesOrderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return submit_document(db, actor, SalesOrder, order_id)


@router.get(
    "/sales-orders/{order_id}/detail",
    response_model=SalesOrderDetailEnvelope,
    response_model_exclude_unset=True,
)
def get_sales_order_detail(
    order_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    order = get_scoped_or_404(db, SalesOrder, tenant_id, order_id)
    if not include_deleted:
        ensure_document_not_deleted(order)
    items = db.scalars(
        select(SalesOrderItem)
        .where(
            SalesOrderItem.tenant_id == tenant_id,
            SalesOrderItem.order_id == order_id,
            SalesOrderItem.deleted_at.is_(None),
        )
        .order_by(SalesOrderItem.line_no.asc().nulls_last(), SalesOrderItem.created_at.asc())
    ).all()
    approvals = document_approvals(db, tenant_id, "sales_order", order_id)
    quotation = (
        db.scalar(
            select(SalesQuotation).where(
                SalesQuotation.tenant_id == tenant_id,
                SalesQuotation.id == order.quotation_id,
            )
        )
        if order.quotation_id
        else None
    )
    attachments = attachments_for_items(db, tenant_id, items)
    skus_by_id, products_by_id, products_with_skus = load_item_catalog_context(db, tenant_id, items)
    # 按单采购 supply signal: purchase lines pinned to this order's lines,
    # with their request's status — one read for the whole document
    purchase_by_line = grouped_linked_lines(
        db, tenant_id, PurchaseRequestItem, "sales_order_item_id",
        PurchaseRequest, "request_id", [item.id for item in items],
        lambda line, request: LinkedPurchaseItemRead(
            id=line.id,
            request_id=line.request_id,
            request_status=request.status,
            quantity=float(line.quantity),
            unit_price=float(line.unit_price) if line.unit_price is not None else None,
        ),
    )
    detail_items: list[SalesOrderItemDetailRead] = []
    for item in items:
        product, sku = resolve_item_refs(item, skus_by_id, products_by_id)
        detail_items.append(
            SalesOrderItemDetailRead(
                **SalesOrderItemRead.model_validate(item).model_dump(),
                product=(
                    QuotationProductReferenceRead(
                        id=product.id,
                        product_code=product.product_code,
                        name=product.name,
                        spec=product.spec,
                        unit=product.unit,
                        list_price=float(product.list_price) if product.list_price is not None else None,
                    )
                    if product is not None
                    else None
                ),
                sku=(
                    QuotationSkuReferenceRead(
                        id=sku.id,
                        product_id=sku.product_id,
                        sku_code=sku.sku_code,
                        variant_attrs=sku.variant_attrs or {},
                        list_price=float(sku.list_price) if sku.list_price is not None else None,
                    )
                    if sku is not None
                    else None
                ),
                sku_pending=sku_pending_flag(item, products_with_skus),
                purchase_items=purchase_by_line.get(item.id, []),
            )
        )
    effective_amounts = [quotation_item_effective_amount(item) for item in items]
    adjustments = db.scalars(
        select(SalesOrderAdjustment)
        .where(
            SalesOrderAdjustment.tenant_id == tenant_id,
            SalesOrderAdjustment.order_id == order.id,
            SalesOrderAdjustment.deleted_at.is_(None),
        )
        .order_by(SalesOrderAdjustment.created_at.asc(), SalesOrderAdjustment.id.asc())
    ).all()
    computed_total = float(sum(amount for amount in effective_amounts if amount is not None))
    adjustments_total = float(sum(adjustment.amount for adjustment in adjustments))
    detail = SalesOrderDetailRead(
        order=SalesOrderRead.model_validate(order),
        items=detail_items,
        approval_records=[ApprovalRecordRead.model_validate(record) for record in approvals],
        attachments=[AttachmentRead.model_validate(attachment) for attachment in attachments],
        quotation=SalesQuotationRead.model_validate(quotation) if quotation is not None else None,
        quote_drift=quote_drift(
            db, tenant_id, quotation, computed_total + adjustments_total, order.total_amount
        ),
        adjustments=[SalesOrderAdjustmentRead.model_validate(adjustment) for adjustment in adjustments],
        computed_total=computed_total,
        adjustments_total=adjustments_total,
        adjusted_total=computed_total + adjustments_total,
        unpriced_item_count=sum(1 for amount in effective_amounts if amount is None),
        pending_sku_count=sum(1 for item in detail_items if item.sku_pending),
    )
    return envelope(detail.model_dump(by_alias=True))


@router.get("/sales-order-items")
def list_sales_order_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    order_id: str | None = None,
    product_id: str | None = None,
    sku_id: str | None = None,
):
    return list_items(db, tenant_id, SalesOrderItem, {"order_id": order_id, "product_id": product_id, "sku_id": sku_id})


@router.post("/sales-order-items", status_code=status.HTTP_201_CREATED)
def create_sales_order_item(
    payload: CreateSalesOrderItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return create_item(db, actor, SalesOrderItem, payload)


@router.get("/sales-order-items/{item_id}")
def get_sales_order_item(
    item_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    return get_item(db, tenant_id, SalesOrderItem, item_id)


@router.patch("/sales-order-items/{item_id}")
def update_sales_order_item(
    item_id: str,
    payload: UpdateSalesOrderItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return update_item(db, actor, SalesOrderItem, item_id, payload)


@router.delete("/sales-order-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sales_order_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return delete_item(db, actor, SalesOrderItem, item_id)


@router.get("/sales-order-adjustments", response_model=SalesOrderAdjustmentListEnvelope, response_model_exclude_unset=True)
def list_sales_order_adjustments(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    order_id: str | None = None,
    order_item_id: str | None = None,
    adjustment_type: str | None = None,
):
    return list_adjustments(
        db, tenant_id, SalesOrderAdjustment,
        parent_id=order_id, item_id=order_item_id, adjustment_type=adjustment_type,
    )


@router.post(
    "/sales-order-adjustments",
    status_code=status.HTTP_201_CREATED,
    response_model=SalesOrderAdjustmentEnvelope,
    response_model_exclude_unset=True,
)
def create_sales_order_adjustment(
    payload: CreateSalesOrderAdjustmentRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return create_adjustment(db, actor, SalesOrderAdjustment, payload)


@router.get("/sales-order-adjustments/{adjustment_id}", response_model=SalesOrderAdjustmentEnvelope, response_model_exclude_unset=True)
def get_sales_order_adjustment(
    adjustment_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    return get_adjustment(db, tenant_id, SalesOrderAdjustment, adjustment_id)


@router.patch("/sales-order-adjustments/{adjustment_id}", response_model=SalesOrderAdjustmentEnvelope, response_model_exclude_unset=True)
def update_sales_order_adjustment(
    adjustment_id: str,
    payload: UpdateSalesOrderAdjustmentRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return update_adjustment(db, actor, SalesOrderAdjustment, adjustment_id, payload)


@router.delete("/sales-order-adjustments/{adjustment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sales_order_adjustment(
    adjustment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return delete_adjustment(db, actor, SalesOrderAdjustment, adjustment_id)


# --- the original document, reached through the record that carries it ------
#
# Authorisation is the DOCUMENT's, never the attachment id's. See
# `serve_document_attachment` in common.py for why the standalone
# `/attachments/{id}/content` could not answer this question safely.


register_attachment_source(SalesQuotation, SalesQuotationItem, "quotation_id")


@router.get("/sales-quotations/{quotation_id}/attachments/{attachment_id}/content")
def get_sales_quotation_attachment(
    quotation_id: str,
    attachment_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """A quotation's attached file, reached through the quotation."""
    document = get_scoped_or_404(db, SalesQuotation, tenant_id, quotation_id)
    return serve_document_attachment(db, tenant_id, document, attachment_id)


register_attachment_source(SalesOrder, SalesOrderItem, "order_id")


@router.get("/sales-orders/{order_id}/attachments/{attachment_id}/content")
def get_sales_order_attachment(
    order_id: str,
    attachment_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """An order line's file, reached through the order."""
    document = get_scoped_or_404(db, SalesOrder, tenant_id, order_id)
    return serve_document_attachment(db, tenant_id, document, attachment_id)
