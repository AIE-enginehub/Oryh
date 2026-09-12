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

from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.common import (
    ORDER_BY_DOC,
    PAGE_SIZE_DOC,
    _run_document_import,
    allocate_number,
    apply_status_change,
    attachments_for_items,
    build_item,
    catalog_list_price,
    CENT,
    commit_or_conflict,
    create_adjustment,
    create_item,
    delete_adjustment,
    delete_document,
    delete_item,
    document_approvals,
    ensure_content_edit_allowed,
    ensure_document_editable,
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
    normalize_customer_context,
    order_billed_on_account,
    recheck_charged_document,
    register_attachment_source,
    requested_pagination,
    require_active_row,
    require_contract_for,
    require_machine_state,
    require_original_order,
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
    Employee,
    ExternalDocumentLink,
    Opportunity,
    Project,
    PurchaseRequest,
    PurchaseRequestItem,
    SalesOrder,
    SalesOrderAdjustment,
    SalesOrderItem,
    SalesQuotation,
    Shipment,
    Store,
    SalesQuotationAdjustment,
    SalesQuotationItem,
    ShipmentItem,
    Todo,
)
from app.schemas import (
    FulfilmentBacklogEnvelope,
    FulfilmentBacklogRowRead,
    FulfilmentLineRead,
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
    ReviseSalesOrderRequest,
    ReviseSalesQuotationRequest,
    SalesOrderAdjustmentEnvelope,
    SalesOrderAdjustmentListEnvelope,
    SalesOrderAdjustmentRead,
    SalesOrderDetailEnvelope,
    SalesOrderDetailRead,
    SalesOrderItemDetailRead,
    SalesOrderItemEnvelope,
    SalesOrderItemListEnvelope,
    SalesOrderItemRead,
    SalesOrderListEnvelope,
    SalesOrderRead,
    SalesQuotationAdjustmentEnvelope,
    SalesQuotationAdjustmentListEnvelope,
    SalesQuotationAdjustmentRead,
    SalesQuotationDetailEnvelope,
    SalesQuotationDetailRead,
    SalesQuotationItemDetailRead,
    SalesQuotationItemEnvelope,
    SalesQuotationItemListEnvelope,
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
    opportunity_id: str | None = None,
    quote_number: str | None = None,
    valid_before: date | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    without_open_todo: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    validate_status_filter(db, tenant_id, "sales_quotation", status_filter)
    stmt = select(SalesQuotation).where(SalesQuotation.tenant_id == tenant_id)
    if valid_before is not None:
        # the expiry sweep: sent quotations past their validity, filtered here
        # rather than by pulling every sent quotation to look at its date
        stmt = stmt.where(SalesQuotation.valid_until < valid_before)
    if not include_deleted:
        stmt = stmt.where(SalesQuotation.deleted_at.is_(None))
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, SalesQuotation, tenant_id, "sales_quotation")
    return list_rows(
        db, stmt,
        filters={
            SalesQuotation.employee_id: employee_id,
            SalesQuotation.customer_id: customer_id,
            SalesQuotation.opportunity_id: opportunity_id,
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
        sort=order_by,
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
    if payload.opportunity_id:
        get_active_document_or_404(db, Opportunity, tenant_id, payload.opportunity_id)
    quote_number = payload.quote_number or allocate_number(db, SalesQuotation, tenant_id)
    quotation = SalesQuotation(
        tenant_id=tenant_id,
        quote_number=quote_number,
        revision_no=1,
        opportunity_id=payload.opportunity_id,
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
    if updates.get("opportunity_id"):
        get_active_document_or_404(db, Opportunity, tenant_id, updates["opportunity_id"])
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
    machine = get_builtin_machine(db, actor.tenant_id, "sales_quotation")
    sent = state_for_role(machine, "sales_quotation", "sent")
    if quotation.status == sent:
        # idempotent resend (F-32: by the tenant's own name for the state)
        return envelope(SalesQuotationRead.model_validate(quotation).model_dump(by_alias=True))
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
    # F-43: the moment it actually went out, when the rep says so
    quotation.sent_at = payload.sent_at or datetime.now(timezone.utc)
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
        opportunity_id=source.opportunity_id,
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
        source_report_text=source.source_report_text,
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
    commit_or_conflict(db, "a concurrent revision was created; retry against the live revision")
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
        # F-38: a condition an approver attached to v1 ("售后 4 小时响应写进合同")
        # must survive into v2 and the order — the prior trail is read here
        prior_approval_records=[
            ApprovalRecordRead.model_validate(record)
            for revision in revisions if revision.id != quotation.id
            for record in document_approvals(db, tenant_id, "sales_quotation", revision.id)
        ],
        adjustments=[SalesQuotationAdjustmentRead.model_validate(adjustment) for adjustment in adjustments],
        computed_total=computed_total,
        adjustments_total=adjustments_total,
        adjusted_total=computed_total + adjustments_total,
        unpriced_item_count=sum(1 for amount in effective_amounts if amount is None),
        pending_sku_count=sum(1 for item in detail_items if item.sku_pending),
    )
    return envelope(detail.model_dump(by_alias=True))


@router.get("/sales-quotation-items", response_model=SalesQuotationItemListEnvelope, response_model_exclude_unset=True)
def list_sales_quotation_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    quotation_id: str | None = None,
    product_id: str | None = None,
    sku_id: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    return list_items(
        db, tenant_id, SalesQuotationItem,
        {"quotation_id": quotation_id, "product_id": product_id, "sku_id": sku_id},
        pagination=requested_pagination(page, size), sort=order_by,
    )


@router.post("/sales-quotation-items", response_model=SalesQuotationItemEnvelope, response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_sales_quotation_item(
    payload: CreateSalesQuotationItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return create_item(db, actor, SalesQuotationItem, payload)


@router.get("/sales-quotation-items/{item_id}", response_model=SalesQuotationItemEnvelope, response_model_exclude_unset=True)
def get_sales_quotation_item(
    item_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    return get_item(db, tenant_id, SalesQuotationItem, item_id)


@router.patch("/sales-quotation-items/{item_id}", response_model=SalesQuotationItemEnvelope, response_model_exclude_unset=True)
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
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    return list_adjustments(
        db, tenant_id, SalesQuotationAdjustment,
        parent_id=quotation_id, item_id=quotation_item_id, adjustment_type=adjustment_type,
        pagination=requested_pagination(page, size), sort=order_by,
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
    store_id: str | None = None,
    employee_id: str | None = None,
    customer_id: str | None = None,
    billing_account_id: str | None = None,
    quotation_id: str | None = None,
    order_no: str | None = None,
    order_kind: str | None = None,
    original_order_id: str | None = None,
    supersedes_order_id: str | None = None,
    opportunity_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    without_open_todo: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    # the status vocabulary follows the kind: a kind-scoped list is checked
    # against that kind's machine, an unscoped one against the union of both
    validate_status_filter(
        db, tenant_id,
        {"order": "sales_order", "return": "sales_return"}.get(
            order_kind, ("sales_order", "sales_return")
        ),
        status_filter,
    )
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
            SalesOrder.store_id: store_id,
            SalesOrder.billing_account_id: billing_account_id,
            SalesOrder.quotation_id: quotation_id,
            SalesOrder.order_no: order_no,
            SalesOrder.order_kind: order_kind,
            SalesOrder.original_order_id: original_order_id,
            SalesOrder.supersedes_order_id: supersedes_order_id,
            SalesOrder.opportunity_id: opportunity_id,
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
        sort=order_by,
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
    if payload.order_kind == "return":
        # a return runs its own machine and reverses money rather than owing
        # it: no quotation behind it, and never a credit-account charge — a
        # refund is a payment document, and letting a return OCCUPY credit
        # would count the customer's money against them twice
        if payload.quotation_id or payload.source_quote_number:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="a return fulfils no quotation — link the original order instead",
            )
        if payload.billing_account_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "a return is not charged to a billing account — the refund "
                    "is a payment document; leave billing_account_id off"
                ),
            )
    elif payload.original_order_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="original_order_id belongs on a return (order_kind='return')",
        )
    require_original_order(db, tenant_id, SalesOrder, payload.original_order_id)
    initial_status = require_machine_state(
        db, tenant_id, SalesOrder, payload.status,
        object_type="sales_return" if payload.order_kind == "return" else "sales_order",
    )
    quotation_id, source_quote_number = normalize_order_quotation_context(
        db, tenant_id, payload.quotation_id, payload.source_quote_number
    )
    opportunity_id = payload.opportunity_id
    payment_terms, delivery_terms = payload.payment_terms, payload.delivery_terms
    if quotation_id:
        won = db.get(SalesQuotation, quotation_id)
        if won is not None:
            # the deal travels with the quotation the order fulfils (F-48: so
            # do the terms the customer accepted, unless the order restates them)
            if opportunity_id is None:
                opportunity_id = won.opportunity_id
            if payment_terms is None:
                payment_terms = won.payment_terms
            if delivery_terms is None:
                delivery_terms = won.delivery_terms
    if payload.opportunity_id:
        get_active_document_or_404(db, Opportunity, tenant_id, payload.opportunity_id)
    customer_id, customer_name_snapshot = normalize_customer_context(
        db, tenant_id, payload.customer_id, payload.customer_name_snapshot
    )
    require_active_row(db, Store, tenant_id, payload.store_id, "store")
    require_contract_for(db, tenant_id, payload.contract_id, "sales")
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
    order_no = payload.order_no or allocate_number(
        db, SalesOrder, tenant_id,
        prefix="SR-" if payload.order_kind == "return" else None,
    )
    order = SalesOrder(
        tenant_id=tenant_id,
        order_no=order_no,
        order_kind=payload.order_kind,
        original_order_id=payload.original_order_id,
        opportunity_id=opportunity_id,
        quotation_id=quotation_id,
        source_quote_number=source_quote_number,
        employee_id=payload.employee_id,
        customer_id=customer_id,
        customer_name_snapshot=customer_name_snapshot,
        store_id=payload.store_id,
        contract_id=payload.contract_id,
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
        payment_terms=payment_terms,
        delivery_terms=delivery_terms,
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


ORDER_FULFILMENT_FIELDS = frozenset({
    "status", "logistics_company", "logistics_tracking_no", "promised_date", "remarks",
    "custom_fields", "shipped_at", "signed_at", "billing_account_id",
})
# the subset a shipment carries when the workspace files one
ORDER_FREIGHT_FACTS = frozenset({"logistics_company", "logistics_tracking_no", "shipped_at", "signed_at"})


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
    # F-05: past its editable states an order's CONTENT is closed — only the
    # fulfilment facts that arrive after confirmation (carrier, tracking,
    # promised date, remarks, the shipped/signed moments, the account
    # release) and the flow's status may still be written
    if set(updates) - ORDER_FULFILMENT_FIELDS:
        ensure_document_editable(db, order)
    if set(updates) & ORDER_FREIGHT_FACTS:
        # one door: where the warehouse files shipments, the carrier, the
        # tracking number and the shipped/signed moments are the shipment's
        # facts and the status stamps them — a header field beside a leg is
        # a second copy that drifts
        leg = db.scalar(select(Shipment.shipment_no).where(
            Shipment.tenant_id == tenant_id, Shipment.sales_order_id == order.id,
            Shipment.deleted_at.is_(None),
        ).limit(1))
        if leg is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"order {order.order_no} ships by shipments ({leg}): record the carrier and "
                    "tracking number on the shipment, and shipped_at / signed_at stamp when the "
                    "status moves — the header's logistics fields are for workspaces that file no shipments"
                ),
            )
    if "store_id" in updates:
        require_active_row(db, Store, tenant_id, updates["store_id"], "store")
    if "contract_id" in updates:
        require_contract_for(db, tenant_id, updates["contract_id"], "sales")
    if "original_order_id" in updates:
        if order.order_kind != "return":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="original_order_id belongs on a return (order_kind='return')",
            )
        require_original_order(db, tenant_id, SalesOrder, updates["original_order_id"])
    if order.order_kind == "return":
        # the create-time guards, held on the PATCH path too: a return fulfils
        # no quotation, and letting one acquire a billing account after the
        # fact would occupy credit for money that flows the other way
        if updates.get("quotation_id") or updates.get("source_quote_number"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="a return fulfils no quotation — link the original order instead",
            )
        if updates.get("billing_account_id"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "a return is not charged to a billing account — the refund "
                    "is a payment document"
                ),
            )
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


@router.post("/sales-orders/{order_id}/revise", status_code=status.HTTP_201_CREATED)
def revise_sales_order(
    order_id: str,
    payload: ReviseSalesOrderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The warehouse cannot ship a confirmed order as written, and the order
    is past its machine's editable states. The tenant's own answer — cancel
    it, raise a new one from it — as one transaction: a fresh draft copied
    from the source (header, lines, adjustments, custom fields, the platform
    numbers it was imported under) that names its source in
    `supersedes_order_id`, while the source moves to the machine's cancelled
    state and releases whatever credit it occupied.

    An order still in an editable state is edited, not revised (409): the
    revision exists for the case where editing is closed. A return is
    reversed, never revised. An order a shipment already names is partly on
    its way — that is a return or a second parcel, not a replacement.
    """
    tenant_id = actor.tenant_id
    source = get_active_document_or_404(db, SalesOrder, tenant_id, order_id)
    require_permission(actor, "order.submit_own")
    enforce_member_employee(actor, source.employee_id)
    if source.order_kind != "order":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a return is reversed, not revised — record a second return against the same original",
        )
    machine = get_builtin_machine(db, tenant_id, "sales_order")
    editable = editable_states(machine, "sales_order")
    if source.status in editable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"the order is still editable in {source.status!r} — change it in "
                "place; revise is for an order past its editable states"
            ),
        )
    cancelled = state_for_role(machine, "sales_order", "cancelled")
    if source.status == cancelled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="the order is already cancelled — revise the live order that replaced it",
        )
    validate_transition(machine, source.status, cancelled, subject="sales_order")
    shipment = db.scalar(
        select(Shipment.id).where(
            Shipment.tenant_id == tenant_id,
            Shipment.sales_order_id == source.id,
            Shipment.deleted_at.is_(None),
        ).limit(1)
    )
    if shipment is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "a shipment already names this order — goods are on their way; "
                "record a return or a further shipment instead of replacing the order"
            ),
        )

    charged_account = None
    if source.billing_account_id:
        # the replacement occupies the same account; the source's occupation
        # is released below in the same transaction, so the net stays honest
        charged_account = resolve_chargeable_account(
            db, tenant_id, source.billing_account_id,
            owner_field="customer_id", owner_id=source.customer_id,
            currency=source.currency, label="sales order",
        )
    revision = SalesOrder(
        tenant_id=tenant_id,
        order_no=allocate_number(db, SalesOrder, tenant_id),
        order_kind="order",
        supersedes_order_id=source.id,
        opportunity_id=source.opportunity_id,
        quotation_id=source.quotation_id,
        source_quote_number=source.source_quote_number,
        employee_id=source.employee_id,
        customer_id=source.customer_id,
        customer_name_snapshot=source.customer_name_snapshot,
        store_id=source.store_id,
        contract_id=source.contract_id,
        contact_name=source.contact_name,
        contact_phone=source.contact_phone,
        ship_to_address=source.ship_to_address,
        title=source.title,
        project_id=source.project_id,
        contract_no=source.contract_no,
        order_date=source.order_date,
        promised_date=source.promised_date,
        currency=source.currency,
        billing_account_id=source.billing_account_id,
        payment_terms=source.payment_terms,
        delivery_terms=source.delivery_terms,
        total_amount=source.total_amount,
        # the machine's own initial — "draft" is the shipped machine's word
        status=machine["initial"],
        # the failed attempt's logistics facts stay with it; the draft starts clean
        remarks=payload.reason or source.remarks,
        source_report_text=source.source_report_text,
        custom_fields_jsonb=dict(source.custom_fields_jsonb or {}),
    )
    db.add(revision)
    db.flush()
    items = db.scalars(
        select(SalesOrderItem)
        .where(
            SalesOrderItem.tenant_id == tenant_id,
            SalesOrderItem.order_id == source.id,
            SalesOrderItem.deleted_at.is_(None),
        )
        .order_by(SalesOrderItem.line_no.asc().nulls_last(), SalesOrderItem.created_at.asc())
    ).all()
    copied_items: dict[str, SalesOrderItem] = {}
    for item in items:
        copy = SalesOrderItem(
            tenant_id=tenant_id,
            order_id=revision.id,
            line_no=item.line_no,
            product_id=item.product_id,
            sku_id=item.sku_id,
            product_name_snapshot=item.product_name_snapshot,
            spec=item.spec,
            quantity=item.quantity,
            unit=item.unit,
            list_price_snapshot=item.list_price_snapshot,
            unit_price=item.unit_price,
            amount=item.amount,
            tax_rate=item.tax_rate,
            is_gift=item.is_gift,
            promised_date=item.promised_date,
            attachment_id=item.attachment_id,
            notes=item.notes,
            custom_fields_jsonb=dict(item.custom_fields_jsonb or {}),
        )
        db.add(copy)
        copied_items[item.id] = copy
    db.flush()
    adjustments = db.scalars(
        select(SalesOrderAdjustment).where(
            SalesOrderAdjustment.tenant_id == tenant_id,
            SalesOrderAdjustment.order_id == source.id,
            SalesOrderAdjustment.deleted_at.is_(None),
        )
    ).all()
    for adjustment in adjustments:
        if adjustment.order_item_id and adjustment.order_item_id not in copied_items:
            continue
        db.add(
            SalesOrderAdjustment(
                tenant_id=tenant_id,
                order_id=revision.id,
                order_item_id=(
                    copied_items[adjustment.order_item_id].id
                    if adjustment.order_item_id
                    else None
                ),
                adjustment_type=adjustment.adjustment_type,
                description=adjustment.description,
                amount=adjustment.amount,
                source_percentage=adjustment.source_percentage,
                metadata_jsonb=dict(adjustment.metadata_jsonb or {}),
            )
        )
    # the platform numbers the source was imported under now also name the
    # replacement — a merge or split is many links, and this is one more
    links = db.scalars(
        select(ExternalDocumentLink).where(
            ExternalDocumentLink.tenant_id == tenant_id,
            ExternalDocumentLink.entity_type == "sales_order",
            ExternalDocumentLink.entity_id == source.id,
        )
    ).all()
    for link in links:
        db.add(
            ExternalDocumentLink(
                tenant_id=tenant_id,
                source=link.source,
                external_kind=link.external_kind,
                external_no=link.external_no,
                entity_type="sales_order",
                entity_id=revision.id,
                created_by=actor.label,
                metadata_jsonb=dict(link.metadata_jsonb or {}),
            )
        )
    record_audit(
        db,
        tenant_id=tenant_id,
        action="order.revised",
        entity_type="sales_order",
        entity_id=source.id,
        actor=actor.label,
        detail={
            "employee_id": source.employee_id,
            "order_no": source.order_no,
            "from": source.status,
            "to": cancelled,
            "new_order_id": revision.id,
            "new_order_no": revision.order_no,
            "reason": payload.reason,
        },
    )
    # the replacement carries the work forward; whatever was open on the
    # source is open on nothing
    retire_open_work_if_finished(
        db, actor, machine, "sales_order", source.id,
        current=source.status, new_status=cancelled, editable=editable,
    )
    source.status = cancelled
    # cancellation's explicit release: the credit the source occupied is free
    # for the replacement to occupy — checked once the lines are in
    source.billing_account_id = None
    if charged_account is not None:
        db.flush()
        ensure_within_credit(db, charged_account, label="sales order")
    commit_or_conflict(db, "a concurrent revision was created; retry against the live order")
    db.refresh(revision)
    data = SalesOrderRead.model_validate(revision).model_dump(by_alias=True)
    data["items"] = [
        SalesOrderItemRead.model_validate(copy).model_dump(by_alias=True)
        for copy in copied_items.values()
    ]
    return envelope(data)


def fulfilment_lines(db: Session, tenant_id: str, order: SalesOrder, items: list[SalesOrderItem]) -> list[dict]:
    """What has left the warehouse against each line: posted outbound legs
    summed per (product, sku), allocated to the order's lines in line order
    when two lines name the same goods (a shipment line does not yet point
    at an order line — E-28)."""
    shipped: dict[tuple[str | None, str | None], float] = {}
    for product_id, sku_id, quantity in db.execute(
        select(ShipmentItem.product_id, ShipmentItem.sku_id, func.coalesce(func.sum(ShipmentItem.quantity), 0))
        .join(Shipment, Shipment.id == ShipmentItem.shipment_id)
        .where(
            ShipmentItem.tenant_id == tenant_id,
            ShipmentItem.deleted_at.is_(None),
            Shipment.sales_order_id == order.id,
            Shipment.direction == "outbound",
            Shipment.deleted_at.is_(None),
            Shipment.stock_posted_at.is_not(None),
        )
        .group_by(ShipmentItem.product_id, ShipmentItem.sku_id)
    ):
        shipped[(product_id, sku_id)] = float(quantity)
    # a leg written against the product alone also serves a SKU line
    by_product: dict[str | None, float] = {}
    for (product_id, sku_id), quantity in shipped.items():
        if sku_id is None:
            by_product[product_id] = by_product.get(product_id, 0.0) + quantity
    rows = []
    for item in items:
        ordered = float(item.quantity)
        taken = 0.0
        if item.product_id is not None:
            key = (item.product_id, item.sku_id)
            pool = shipped.get(key, 0.0)
            taken = min(ordered, pool)
            shipped[key] = pool - taken
            if item.sku_id is not None and taken < ordered:
                spare = by_product.get(item.product_id, 0.0)
                more = min(ordered - taken, spare)
                by_product[item.product_id] = spare - more
                shipped[(item.product_id, None)] = shipped.get((item.product_id, None), 0.0) - more
                taken += more
        rows.append({
            "order_item_id": item.id,
            "line_no": item.line_no,
            "product_id": item.product_id,
            "sku_id": item.sku_id,
            "product_name_snapshot": item.product_name_snapshot,
            "ordered": ordered,
            "shipped": round(taken, 2),
            "outstanding": round(ordered - taken, 2),
        })
    return rows


@router.get(
    "/fulfilment-backlog",
    response_model=FulfilmentBacklogEnvelope,
    response_model_exclude_unset=True,
)
def list_fulfilment_backlog(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    store_id: str | None = None,
    employee_id: str | None = None,
    min_days_waiting: Annotated[int, Query(ge=0)] = 0,
):
    """Confirmed orders (the tenant's name for that state) with lines the
    warehouse has not fully shipped — the shortage as a fact the flow can
    chase without a promised date or a remark to find it in (E-22, E-27).
    Oldest first. An order whose every line has shipped is not here even
    while its status still says confirmed: advancing it is the flow's step."""
    machine = get_builtin_machine(db, tenant_id, "sales_order")
    confirmed = state_for_role(machine, "sales_order", "confirmed")
    stmt = select(SalesOrder).where(
        SalesOrder.tenant_id == tenant_id,
        SalesOrder.deleted_at.is_(None),
        SalesOrder.order_kind == "order",
        SalesOrder.status == confirmed,
    ).order_by(SalesOrder.submitted_at.asc().nulls_last(), SalesOrder.created_at.asc())
    if store_id:
        stmt = stmt.where(SalesOrder.store_id == store_id)
    if employee_id:
        stmt = stmt.where(SalesOrder.employee_id == employee_id)
    orders = db.scalars(stmt).all()
    if not orders:
        return envelope([], total=0)
    order_ids = [order.id for order in orders]
    items_by_order: dict[str, list[SalesOrderItem]] = {}
    for item in db.scalars(
        select(SalesOrderItem).where(
            SalesOrderItem.tenant_id == tenant_id,
            SalesOrderItem.order_id.in_(order_ids),
            SalesOrderItem.deleted_at.is_(None),
        ).order_by(SalesOrderItem.line_no.asc().nulls_last(), SalesOrderItem.created_at.asc())
    ):
        items_by_order.setdefault(item.order_id, []).append(item)
    posted = dict(db.execute(
        select(Shipment.sales_order_id, func.count(Shipment.id)).where(
            Shipment.tenant_id == tenant_id, Shipment.sales_order_id.in_(order_ids),
            Shipment.direction == "outbound", Shipment.deleted_at.is_(None),
            Shipment.stock_posted_at.is_not(None),
        ).group_by(Shipment.sales_order_id)
    ).all())
    open_todos = dict(db.execute(
        select(Todo.entity_id, func.count(Todo.id)).where(
            Todo.tenant_id == tenant_id, Todo.entity_type == "sales_order",
            Todo.entity_id.in_(order_ids), Todo.status == "open",
        ).group_by(Todo.entity_id)
    ).all())
    now = datetime.now(timezone.utc)
    rows = []
    for order in orders:
        lines = fulfilment_lines(db, tenant_id, order, items_by_order.get(order.id, []))
        if not any(line["outstanding"] > 0 for line in lines):
            continue
        since = order.submitted_at or order.created_at
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        days = max(0, (now - since).days)
        if days < min_days_waiting:
            continue
        rows.append(FulfilmentBacklogRowRead(
            order_id=order.id, order_no=order.order_no, status=order.status,
            employee_id=order.employee_id, store_id=order.store_id,
            customer_name_snapshot=order.customer_name_snapshot,
            promised_date=order.promised_date, submitted_at=order.submitted_at,
            days_waiting=days, shipments_posted=int(posted.get(order.id, 0)),
            open_todo_count=int(open_todos.get(order.id, 0)),
            lines=[FulfilmentLineRead(**line) for line in lines],
        ).model_dump(by_alias=True))
    return envelope(rows, total=len(rows))


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
    superseded_by = db.scalar(
        select(SalesOrder).where(
            SalesOrder.tenant_id == tenant_id,
            SalesOrder.supersedes_order_id == order.id,
            SalesOrder.deleted_at.is_(None),
        ).order_by(SalesOrder.created_at.desc()).limit(1)
    )
    detail = SalesOrderDetailRead(
        order=SalesOrderRead.model_validate(order),
        superseded_by=SalesOrderRead.model_validate(superseded_by) if superseded_by is not None else None,
        items=detail_items,
        fulfilment=[FulfilmentLineRead(**line) for line in fulfilment_lines(db, tenant_id, order, items)],
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


@router.get("/sales-order-items", response_model=SalesOrderItemListEnvelope, response_model_exclude_unset=True)
def list_sales_order_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    order_id: str | None = None,
    product_id: str | None = None,
    sku_id: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    return list_items(
        db, tenant_id, SalesOrderItem,
        {"order_id": order_id, "product_id": product_id, "sku_id": sku_id},
        pagination=requested_pagination(page, size), sort=order_by,
    )


@router.post("/sales-order-items", response_model=SalesOrderItemEnvelope, response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED)
def create_sales_order_item(
    payload: CreateSalesOrderItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return create_item(db, actor, SalesOrderItem, payload)


@router.get("/sales-order-items/{item_id}", response_model=SalesOrderItemEnvelope, response_model_exclude_unset=True)
def get_sales_order_item(
    item_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    return get_item(db, tenant_id, SalesOrderItem, item_id)


@router.patch("/sales-order-items/{item_id}", response_model=SalesOrderItemEnvelope, response_model_exclude_unset=True)
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
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, description=PAGE_SIZE_DOC)] = None,
    order_by: Annotated[str | None, Query(description=ORDER_BY_DOC)] = None,
):
    return list_adjustments(
        db, tenant_id, SalesOrderAdjustment,
        parent_id=order_id, item_id=order_item_id, adjustment_type=adjustment_type,
        pagination=requested_pagination(page, size), sort=order_by,
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
