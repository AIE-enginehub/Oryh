from __future__ import annotations

import base64
import binascii
import uuid
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import String, and_, case, cast, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.api.common import envelope, get_tenant_id, list_rows, page_only_pagination, requested_pagination
from app.api.deps import Actor, attributed, enforce_member_employee, get_actor, has_permission, require_permission
from app.core.config import settings
from app.core.entity_types import (
    APPROVAL_ENTITY_TYPES,
    DECIDED_APPROVAL_ACTIONS,
    OPERATOR_CONFLICT_CLOSURE_KEY,
    TODO_ENTITY_TYPES,
)
from app.core.permissions import (
    HOSTED_FLOW_AGENT_DISPLAY_NAME,
    PRINCIPAL_HOSTED_FLOW_AGENT,
    PRINCIPAL_TENANT_SERVICE,
)
from app.db.session import get_db
from app.models import (
    ApiKey,
    ApprovalRecord,
    Attachment,
    BusinessObject,
    BusinessObjectLink,
    Customer,
    Employee,
    EmployeeLeave,
    AuditLog,
    ExpenseClaim,
    ExpenseItem,
    BillingAccount,
    BillingAccountEntry,
    InventoryItem,
    InventoryItemDetail,
    Invoice,
    InvoiceItem,
    ObjectTypeDefinition,
    PayHistory,
    Policy,
    Payment,
    PaymentApplication,
    Product,
    ProductPrice,
    ProductSku,
    Project,
    PurchaseOrder,
    PurchaseOrderAdjustment,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
    Resource,
    ResourceBooking,
    SalesOrder,
    SalesOrderAdjustment,
    SalesOrderItem,
    SalesQuotation,
    SalesQuotationAdjustment,
    SalesQuotationItem,
    SupplierProduct,
    Tenant,
    Todo,
    TypeOption,
    TimesheetEntry,
    TimesheetHeader,
    User,
    Vendor,
    WorkflowDefinition,
    generate_api_key,
    hash_api_key,
)
from app.schemas import (
    CreateEmployeeLeaveRequest,
    DeleteEmployeeLeaveRequest,
    EmployeeLeaveEnvelope,
    EmployeeLeaveListEnvelope,
    EmployeeLeaveRead,
    UpdateEmployeeLeaveRequest,
    BuiltinObjectTypeEnvelope,
    BulkTodoEnvelope,
    BulkTodoCreateRequest,
    ApprovalTargetRead,
    ApprovalTargetEnvelope,
    ApprovalTargetListEnvelope,
    ApprovalRecordRead,
    ApprovalRecordEnvelope,
    ApprovalRecordListEnvelope,
    ApiKeyEnvelope,
    ApiKeyListEnvelope,
    ApiKeyOwnerListEnvelope,
    ApiKeyOwnerRead,
    ApiKeyRead,
    BatchCreateProductSkusEnvelope,
    BatchCreateProductSkusRequest,
    BusinessObjectDetailEnvelope,
    BusinessObjectDetailRead,
    BusinessObjectEnvelope,
    BusinessObjectLinkEnvelope,
    BusinessObjectLinkListEnvelope,
    BusinessObjectLinkRead,
    BusinessObjectListEnvelope,
    BusinessObjectRead,
    CreateApiKeyRequest,
    CreateApiKeyEnvelope,
    CreateApiKeyResponse,
    CreateApprovalRecordRequest,
    CreateApprovalTargetRequest,
    CreateBusinessObjectLinkRequest,
    CreateBusinessObjectRequest,
    AttachmentRead,
    CreateAttachmentRequest,
    BulkCustomerUpsertRequest,
    BulkDocumentImportEnvelope,
    BulkSalesQuotationImportRequest,
    BulkPurchaseOrderImportRequest,
    BulkInvoiceImportRequest,
    BulkPaymentImportRequest,
    BulkSalesOrderImportRequest,
    BulkProductUpsertRequest,
    BulkUpsertEnvelope,
    BulkVendorUpsertRequest,
    CreateEmployeeRequest,
    CreateExpenseClaimRequest,
    CreateExpenseItemRequest,
    CloseSalesQuotationRequest,
    CreateCustomerRequest,
    CreateProductRequest,
    CreateProductSkuRequest,
    CreateProjectRequest,
    CreatePurchaseRequestItemRequest,
    CreatePurchaseRequestRequest,
    CreateResourceBookingRequest,
    CreateResourceRequest,
    CreateSalesOrderItemRequest,
    CreateSalesOrderRequest,
    CreateSalesQuotationItemRequest,
    CreateSalesQuotationRequest,
    CreateTenantRequest,
    CreateTenantResponse,
    CreateTodoRequest,
    CreateVendorRequest,
    CustomerEnvelope,
    CustomerListEnvelope,
    CustomerRead,
    DisplayNameResolveRequest,
    DisplayNameResolutionEnvelope,
    DisplayNameResolutionRead,
    DeleteApprovalTargetRequest,
    DeleteBusinessObjectRequest,
    DeleteExpenseClaimRequest,
    DeletePurchaseRequestRequest,
    DeleteResourceBookingRequest,
    DeleteSalesOrderRequest,
    DeleteSalesQuotationRequest,
    DeleteTimesheetHeaderRequest,
    ExpenseClaimDetailRead,
    ExpenseClaimDetailEnvelope,
    ExpenseClaimListEnvelope,
    ExpenseClaimRead,
    ExpenseItemDetailRead,
    ExpenseItemRead,
    EmployeeEnvelope,
    EmployeeListEnvelope,
    ProductRead,
    ProductEnvelope,
    ProductListEnvelope,
    ProductSkuRead,
    ProductSkuEnvelope,
    ProductSkuListEnvelope,
    CreateProductPriceRequest,
    UpdateProductPriceRequest,
    ProductPriceRead,
    ProductPriceEnvelope,
    ProductPriceListEnvelope,
    CreateSupplierProductRequest,
    CreateTypeOptionRequest,
    UpdateTypeOptionRequest,
    TypeOptionRead,
    TypeOptionEnvelope,
    TypeOptionListEnvelope,
    UpdateSupplierProductRequest,
    SupplierProductRead,
    SupplierProductEnvelope,
    SupplierProductListEnvelope,
    CreateInventoryItemRequest,
    UpdateInventoryItemRequest,
    InventoryItemRead,
    InventoryItemEnvelope,
    InventoryItemListEnvelope,
    CreateInventoryItemDetailRequest,
    InventoryItemDetailRead,
    InventoryItemDetailEnvelope,
    InventoryItemDetailListEnvelope,
    BulkInventoryUpsertRequest,
    PurchaseRequestDetailRead,
    PurchaseRequestDetailEnvelope,
    PurchaseRequestListEnvelope,
    PurchaseProductReferenceRead,
    PurchaseRequestItemRead,
    PurchaseSalesOrderReferenceRead,
    LinkedPurchaseOrderItemRead,
    CreatePurchaseOrderRequest,
    UpdatePurchaseOrderRequest,
    PurchaseOrderRead,
    PurchaseOrderEnvelope,
    PurchaseOrderCreatedEnvelope,
    PurchaseOrderListEnvelope,
    CreatePurchaseOrderItemRequest,
    UpdatePurchaseOrderItemRequest,
    PurchaseOrderItemRead,
    PurchaseOrderItemEnvelope,
    PurchaseOrderItemListEnvelope,
    CreatePurchaseOrderAdjustmentRequest,
    UpdatePurchaseOrderAdjustmentRequest,
    PurchaseOrderAdjustmentRead,
    PurchaseOrderAdjustmentEnvelope,
    PurchaseOrderAdjustmentListEnvelope,
    PurchaseOrderRequestReferenceRead,
    PurchaseOrderItemDetailRead,
    PurchaseOrderDetailRead,
    PurchaseOrderDetailEnvelope,
    ReceivePurchaseOrderRequest,
    ReceivedLineRead,
    ReceivePurchaseOrderResult,
    ReceivePurchaseOrderEnvelope,
    CreateInvoiceRequest,
    UpdateInvoiceRequest,
    DeleteInvoiceRequest,
    InvoiceRead,
    InvoiceEnvelope,
    InvoiceCreatedEnvelope,
    InvoiceListEnvelope,
    CreateInvoiceItemRequest,
    UpdateInvoiceItemRequest,
    InvoiceItemRead,
    InvoiceItemEnvelope,
    InvoiceItemListEnvelope,
    InvoiceItemDetailRead,
    InvoiceOrderMatchLineRead,
    InvoiceOrderMatchRead,
    InvoiceDetailRead,
    InvoiceDetailEnvelope,
    PaymentApplicationRead,
    PaymentApplicationListEnvelope,
    CreatePaymentRequest,
    UpdatePaymentRequest,
    DeletePaymentRequest,
    PaymentRead,
    PaymentEnvelope,
    PaymentListEnvelope,
    PaymentDetailRead,
    PaymentDetailEnvelope,
    PaymentApplicationDetailRead,
    SettlementTargetRead,
    ApplyPaymentRequest,
    ApplyPaymentResult,
    ApplyPaymentEnvelope,
    CreatePayHistoryRequest,
    UpdatePayHistoryRequest,
    PayHistoryRead,
    PayHistoryEnvelope,
    PayHistoryListEnvelope,
    PayHistoryChangeRead,
    PayHistoryChangeEnvelope,
    PolicyEnvelope,
    PolicyListEnvelope,
    PolicyPublishEnvelope,
    PolicyPublishRead,
    PolicyRead,
    CreatePolicyRequest,
    PublishPolicyRequest,
    RepealPolicyRequest,
    RescopePolicyRequest,
    UpdatePolicyRequest,
    CreateBillingAccountRequest,
    UpdateBillingAccountRequest,
    DeleteBillingAccountRequest,
    BillingAccountRead,
    BillingAccountEnvelope,
    BillingAccountListEnvelope,
    BillingAccountEntryRead,
    BillingAccountEntryListEnvelope,
    PostBillingAccountEntriesRequest,
    PostBillingAccountEntriesResult,
    PostBillingAccountEntriesEnvelope,
    BillingAccountDetailRead,
    BillingAccountDetailEnvelope,
    ExpiringBillingAccountEntriesRead,
    ExpiringBillingAccountEntriesEnvelope,
    LinkedPurchaseItemRead,
    PurchaseRequestItemDetailRead,
    PurchaseRequestRead,
    PurchaseSkuReferenceRead,
    CreateTimesheetEntryRequest,
    CreateTimesheetHeaderRequest,
    CreateObjectTypeDefinitionRequest,
    EmployeeRead,
    AuditLogRead,
    ObjectTypeDefinitionRead,
    ObjectDirectoryEntryRead,
    ObjectDirectoryEnvelope,
    ObjectTypeDefinitionEnvelope,
    ObjectTypeDefinitionListEnvelope,
    ProjectRead,
    ProjectEnvelope,
    ProjectListEnvelope,
    ResourceAvailabilityRead,
    ResourceBookingListEnvelope,
    ResourceBookingRead,
    ResourceRead,
    ResourceEnvelope,
    ResourceListEnvelope,
    RestoreApprovalTargetRequest,
    RestoreBusinessObjectRequest,
    RestoreExpenseClaimRequest,
    RestorePurchaseRequestRequest,
    RestoreSalesOrderRequest,
    RestoreSalesQuotationRequest,
    ReviseSalesQuotationRequest,
    QuoteDriftRead,
    SalesOrderDetailRead,
    SalesOrderDetailEnvelope,
    SalesOrderItemDetailRead,
    SalesOrderItemRead,
    SalesOrderListEnvelope,
    SalesOrderRead,
    SalesQuotationDetailRead,
    SalesQuotationDetailEnvelope,
    SalesQuotationEnvelope,
    SalesQuotationItemDetailRead,
    SalesQuotationItemRead,
    CreateSalesQuotationAdjustmentRequest,
    UpdateSalesQuotationAdjustmentRequest,
    SalesQuotationAdjustmentRead,
    SalesQuotationAdjustmentEnvelope,
    SalesQuotationAdjustmentListEnvelope,
    CreateSalesOrderAdjustmentRequest,
    UpdateSalesOrderAdjustmentRequest,
    SalesOrderAdjustmentRead,
    SalesOrderAdjustmentEnvelope,
    SalesOrderAdjustmentListEnvelope,
    SalesQuotationListEnvelope,
    SalesQuotationRead,
    QuotationProductReferenceRead,
    QuotationSkuReferenceRead,
    SendSalesQuotationRequest,
    SubmitExpenseClaimRequest,
    SubmitPurchaseRequestRequest,
    SubmitSalesOrderRequest,
    SubmitSalesQuotationRequest,
    SubmitTimesheetRequest,
    RestoreTimesheetHeaderRequest,
    TenantRead,
    TodoEnvelope,
    TodoListEnvelope,
    TodoLastApproval,
    TodoRead,
    TodoTargetSummary,
    TimesheetDetailRead,
    TimesheetHeaderListEnvelope,
    TimesheetEntryRead,
    TimesheetHeaderRead,
    UpdateApiKeyRequest,
    UpdateApprovalTargetRequest,
    UpdateExpenseClaimRequest,
    UpdateExpenseItemRequest,
    UpdateObjectTypeDefinitionRequest,
    UpdateCustomerRequest,
    UpdateProductRequest,
    UpdateProductSkuRequest,
    UpdatePurchaseRequestItemRequest,
    UpdatePurchaseRequestRequest,
    UpdateSalesOrderItemRequest,
    UpdateSalesOrderRequest,
    UpdateSalesQuotationItemRequest,
    UpdateSalesQuotationRequest,
    UpdateBusinessObjectRequest,
    UpdateEmployeeRequest,
    UpdateProjectRequest,
    UpdateResourceBookingRequest,
    UpdateResourceRequest,
    UpdateTodoRequest,
    UpdateTimesheetEntryRequest,
    UpdateTimesheetHeaderRequest,
    UpdateVendorRequest,
    VendorRead,
    VendorEnvelope,
    VendorListEnvelope,
    WorkflowDefinitionRead,
)
from app.services.audit import record_audit
from app.services.inventory_import import _find_item, bulk_inventory_upsert, post_inventory_detail
from app.services import document_import
from app.services.master_data_import import bulk_upsert
from app.services.object_types import (
    BUILTIN_OBJECT_TYPES,
    builtin_object_vocabulary,
    ensure_valid_json_schema,
    validate_business_object_payload,
)
from app.core.type_options import TYPE_FAMILIES, system_type_names
from app.services.provisioning import provision_system_type_options, provision_tenant_defaults
from app.core.type_options import SIGNED_TYPE_FAMILIES
from app.services.type_options import require_type_option, type_option_sign
from app.services.inventory_import import _find_item as find_inventory_item, post_inventory_detail
from app.services.state_machines import (
    editable_states,
    ensure_valid_state_machine,
    get_builtin_machine,
    validate_business_object_status,
    validate_business_object_status_filter,
    validate_status_filter,
    validate_transition,
)
from app.services.tenants import create_tenant_with_api_key

router = APIRouter()


def require_master_data_manage(actor: Actor) -> None:
    """Guard tenant master-data writes.

    ``users.manage`` remains an accepted legacy grant so existing tenant
    administrator roles keep working when this more focused capability ships.
    Service credentials continue to pass through ``has_permission``'s normal
    service-actor bypass.
    """
    if not (
        has_permission(actor, "master_data.manage")
        or has_permission(actor, "users.manage")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requires capability master_data.manage",
        )


def ensure_code_available(
    db: Session,
    model,
    tenant_id: str,
    code_attr: str,
    code: str | None,
    *,
    exclude_id: str | None = None,
) -> None:
    """Reject a master-data code the tenant already uses, as a 409 naming the
    conflict, before the database raises an opaque integrity error.

    The unique index is the real guarantee; this exists so the ordinary case —
    someone re-adds a product that is already in the catalog — comes back as a
    conflict the caller can act on instead of a 500. `exclude_id` lets an
    update keep its own code.
    """
    if not code:
        return
    stmt = select(model.id).where(
        model.tenant_id == tenant_id, getattr(model, code_attr) == code
    )
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{code_attr} '{code}' already exists in this tenant",
        )


def get_current_tenant(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="tenant not found for API key")
    return tenant


def get_scoped_or_404(
    db: Session,
    model,
    tenant_id: str,
    entity_id: str,
):
    # A path segment that is not a UUID cannot be a row — postgres would
    # refuse the cast and that refusal used to surface as a 500 (a live E2E
    # audit: /employees/principals falling into /employees/{id}). Not-a-valid-id and
    # no-such-id are the same answer to the caller: 404.
    try:
        uuid.UUID(str(entity_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    instance = db.get(model, entity_id)
    if instance is None or instance.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    return instance


@dataclass(frozen=True)
class DocumentFamily:
    """Everything the shared plumbing needs to know about one document
    family. The families behave identically by design — same soft delete,
    same machine-gated line editing, same number allocation — so the
    differences live here as data, not as six copies of the same function."""

    object_type: str            # builtin machine key
    items_phrase: str           # subject of the editable 409
    parent_noun: str            # how the 409 names the parent
    permission: str             # the capability that files this family
    read_model: type
    audit_prefix: str           # "quotation" in quotation.submitted / .status_changed
    audit_identity: object      # doc -> the identifying keys every audit carries
    state_noun: str             # how the create-time 422 names the machine
    advance_permission: str | None = None   # None = filing capability covers advancement
    # doc -> the scope its filing capability is checked with, for families whose
    # verb is scopable (invoice.manage:sales). Without it the shared helpers
    # would check the bare verb and refuse an 应收会计 holding only :sales.
    permission_scope: object | None = None
    owner_checked: bool = True  # personal documents enforce the member-own limit
    attributed_delete: bool = True          # deleted_by / delete_reason columns exist
    editable_hint: str = ""     # family-specific tail of the 409
    number_prefix: str | None = None
    number_field: str | None = None
    lock_scope: str | None = None


DOCUMENT_FAMILIES: dict[type, DocumentFamily] = {
    TimesheetHeader: DocumentFamily(
        "timesheet_header", "timesheet entries", "header",
        "timesheet.submit_own", TimesheetHeaderRead, "timesheet",
        lambda d: {
            "employee_id": d.employee_id,
            "period_start": d.period_start.isoformat(),
            "period_end": d.period_end.isoformat(),
        },
        "timesheet", advance_permission="timesheet.advance",
    ),
    EmployeeLeave: DocumentFamily(
        # No line items: a leave request is one absence, so the items_phrase /
        # parent_noun pair only ever surfaces in the editable-state 409, where
        # it reads correctly because that gate also guards header edits.
        "employee_leave", "leave details", "request",
        "leave.submit_own", EmployeeLeaveRead, "leave",
        lambda d: {
            "employee_id": d.employee_id,
            "leave_type": d.leave_type,
            "from_date": d.from_date.isoformat(),
            "thru_date": d.thru_date.isoformat(),
            "duration_days": float(d.duration_days),
        },
        "leave", advance_permission="leave.advance",
    ),
    ExpenseClaim: DocumentFamily(
        "expense_claim", "expense items", "claim",
        "expense.submit_own", ExpenseClaimRead, "expense",
        lambda d: {"employee_id": d.employee_id, "title": d.title},
        "expense", advance_permission="expense.advance",
    ),
    PurchaseRequest: DocumentFamily(
        "purchase_request", "purchase request items", "request",
        "purchase.submit_own", PurchaseRequestRead, "purchase",
        lambda d: {"employee_id": d.employee_id, "title": d.title},
        "purchase", advance_permission="purchase.advance",
    ),
    SalesQuotation: DocumentFamily(
        "sales_quotation", "quotation items", "quotation",
        "quotation.submit_own", SalesQuotationRead, "quotation",
        lambda d: {
            "employee_id": d.employee_id,
            "quote_number": d.quote_number,
            "revision_no": d.revision_no,
            "title": d.title,
        },
        "quotation", advance_permission="quotation.advance",
        editable_hint="; a sent quotation is revised, not edited",
        number_prefix="QT-", number_field="quote_number", lock_scope="sales_quotation_number",
    ),
    SalesOrder: DocumentFamily(
        "sales_order", "sales order items", "order",
        "order.submit_own", SalesOrderRead, "order",
        lambda d: {"employee_id": d.employee_id, "order_no": d.order_no, "title": d.title},
        "order", advance_permission="order.advance",
        number_prefix="SO-", number_field="order_no", lock_scope="sales_order_number",
    ),
    PurchaseOrder: DocumentFamily(
        # procurement is a function, not "my documents": one capability files
        # AND advances, no owner to enforce, and (for now) no delete attribution
        "purchase_order", "purchase order items", "order",
        "purchase_order.manage", PurchaseOrderRead, "purchase_order",
        lambda d: {"po_number": d.po_number},
        "purchase order", advance_permission=None,
        owner_checked=False, attributed_delete=False,
        number_prefix="PO-", number_field="po_number", lock_scope="purchase_order_number",
    ),
    Invoice: DocumentFamily(
        # invoicing is a finance function like procurement — no owner-own limit
        # — but unlike the PO it keeps an approval half (开票申请), so filing and
        # advancing are separate grants. The filing capability is checked with
        # the direction as its scope, which is why the routes pass one.
        "invoice", "invoice lines", "invoice",
        "invoice.manage", InvoiceRead, "invoice",
        lambda d: {
            "invoice_no": d.invoice_no,
            "direction": d.direction,
            "title": d.title,
        },
        "invoice", advance_permission="invoice.advance",
        permission_scope=lambda d: d.direction,
        owner_checked=False,
        number_prefix="INV-", number_field="invoice_no", lock_scope="invoice_number",
    ),
    Payment: DocumentFamily(
        # a payment has no lines, so the items_phrase/parent_noun pair only ever
        # shows up in the editable-state 409 the shared plumbing raises; it reads
        # correctly there because that gate also guards edits to the header.
        "payment", "payment details", "payment",
        "payment.record", PaymentRead, "payment",
        lambda d: {
            "payment_no": d.payment_no,
            "direction": d.direction,
            "amount": float(d.amount),
        },
        "payment", advance_permission="payment.advance",
        owner_checked=False, attributed_delete=False,
        number_prefix="PAY-", number_field="payment_no", lock_scope="payment_number",
    ),
}


def may_read_payroll(actor: Actor) -> bool:
    """Salaries and payslips are the one thing here that belonging to the
    workspace does not entitle you to read.

    Every other read in this API is tenant-scoped only, which is fine for
    business documents and unacceptable for pay. Writing payroll implies reading
    it; `payroll.read` exists separately so a workspace can let someone see the
    numbers without being able to change them."""
    return has_permission(actor, "payroll.read") or has_permission(
        actor, "invoice.manage", "payroll"
    )


def own_employee_id(actor: Actor) -> str | None:
    """The employee this credential IS, when it is a person's. Service keys are
    nobody, so they see their own payslip never — and their whole workspace's
    only with the capability."""
    return actor.employee_id if actor.kind == "user" else None


def visible_payroll_filter(actor: Actor):
    """The payroll visibility rule, as a SQL condition on `invoices`.

    Returned as a clause rather than applied here because it has to be threaded
    into several queries — and the whole value of this gate is that no path
    around it exists. Every read that could surface a payslip, or a payment that
    settles one, goes through this or `hide_payroll_payments`.

    Everyone sees their own payslip. That is not a concession: an employee who
    cannot see what they were paid has no way to check it."""
    if may_read_payroll(actor):
        return None
    own = own_employee_id(actor)
    if own is None:
        return Invoice.direction != "payroll"
    return or_(Invoice.direction != "payroll", Invoice.payee_employee_id == own)


def may_see_invoice(actor: Actor, invoice: Invoice) -> bool:
    if invoice.direction != "payroll" or may_read_payroll(actor):
        return True
    return own_employee_id(actor) is not None and invoice.payee_employee_id == own_employee_id(actor)


def ensure_invoice_visible(actor: Actor, invoice: Invoice) -> None:
    """404 rather than 403: refusing by name would confirm that this person has
    a payslip for this period, which is most of what the gate is protecting."""
    if not may_see_invoice(actor, invoice):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")


def ensure_payment_visible(db: Session, actor: Actor, payment: Payment) -> None:
    """404 for a payment that settles someone else's payslip — its amount is
    their net pay."""
    if may_read_payroll(actor):
        return
    own = own_employee_id(actor)
    hidden = db.scalar(
        select(func.count())
        .select_from(PaymentApplication)
        .join(Invoice, PaymentApplication.invoice_id == Invoice.id)
        .where(
            PaymentApplication.tenant_id == actor.tenant_id,
            PaymentApplication.payment_id == payment.id,
            Invoice.direction == "payroll",
            *([] if own is None else [Invoice.payee_employee_id != own]),
        )
    )
    if hidden:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    # …and the same before it is settled, which is the window the list gate
    # missed: a payout naming another employee is their money whether or not
    # anything has been applied to it yet.
    if (
        payment.payee_employee_id is not None
        and payment.payee_employee_id != own
        and not handles_money(actor)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")


def hide_payroll_payments(stmt, actor: Actor):
    """A payment that settles a payslip carries the net pay as its amount, so
    the invoice gate would be pointless without this one.

    Two clauses, because the first one alone had a window in it that the
    live test environment walked straight through. Settlement is what
    makes a payout *provably* payroll, but the payout exists before it is
    settled — created, submitted, approved, paid, and only then applied. For
    that whole stretch it sat in plain view of every colleague, carrying the
    payee's name and their net pay, and only became confidential after the
    money had already moved.

    So the second clause gates on the payment itself: money that names another
    employee as payee is that person's business, whether or not anything has
    been applied to it yet. It exempts the money handlers, because a 出纳
    processing 报销付款 and 工资代发 has to see what they are paying — the
    exemption is the job, not a hole. Everyone else sees their own payouts and
    the company's ordinary customer and supplier payments.

    The first clause keeps its full strength, money handlers included: once a
    payout is applied to somebody's payslip, its amount IS their net pay and
    nothing below `payroll.read` reads it.
    """
    if may_read_payroll(actor):
        return stmt
    own = own_employee_id(actor)
    settles_payroll = (
        select(PaymentApplication.id)
        .join(Invoice, PaymentApplication.invoice_id == Invoice.id)
        .where(
            PaymentApplication.tenant_id == actor.tenant_id,
            PaymentApplication.payment_id == Payment.id,
            Invoice.direction == "payroll",
            *([] if own is None else [Invoice.payee_employee_id != own]),
        )
        .exists()
    )
    stmt = stmt.where(~settles_payroll)
    if handles_money(actor):
        return stmt
    return stmt.where(
        or_(
            Payment.payee_employee_id.is_(None),
            *([] if own is None else [Payment.payee_employee_id == own]),
        )
    )


def handles_money(actor: Actor) -> bool:
    """Whether this credential's job is moving money. A 出纳 recording a payout,
    a 会计 matching it, and the approver deciding whether it goes at all have to
    see payments made to people; an ordinary employee has no such reason.

    `payment.advance` is here because approving a payout you cannot see is not
    a weaker version of the job, it is none of it: the queue came back empty,
    so a workspace whose workflow definition routed 工资发放 through payment
    approval had a step nobody — human or flow agent — could ever reach. The
    exemption is the duty, same as for the other two.

    It is a real widening, and worth naming: whoever may approve payouts can
    read an unsettled payroll payout's amount, which is somebody's net pay.
    Two things bound it. The first clause of `hide_payroll_payments` keeps its
    full strength regardless — once applied to a payslip, the amount IS net pay
    and only `payroll.read` sees it. And this reaches the payout alone; the
    payslip behind it, with its line-by-line 社保/个税 breakdown, stays shut."""
    return (
        has_permission(actor, "payment.record")
        or has_permission(actor, "payment.apply")
        or has_permission(actor, "payment.advance")
    )


def require_family_permission(actor: Actor, family: DocumentFamily, document) -> None:
    """The filing check for a document that already exists. Scopable families
    are checked against the document's own scope (an invoice's direction), so
    a role granted only `invoice.manage:sales` reaches its own documents and
    no others."""
    scope = family.permission_scope(document) if family.permission_scope else None
    require_permission(actor, family.permission, scope)


def _document_read(family: DocumentFamily, document) -> dict:
    return family.read_model.model_validate(document).model_dump(by_alias=True)


def require_machine_state(db: Session, tenant_id: str, model, status_value: str) -> dict:
    """Create-time gate: a new document may start in ANY state of the
    tenant's machine (history imports mid-flow), but never outside it."""
    family = DOCUMENT_FAMILIES[model]
    machine = get_builtin_machine(db, tenant_id, family.object_type)
    if status_value not in set(machine.get("states", ())):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status {status_value!r} is not a state of the tenant's {family.state_noun} state machine",
        )
    return machine


def require_hosted_write_scope(
    actor: Actor, entity_type: str, row, *, ignore: tuple[str, ...] = ()
) -> None:
    """Hold a hosted flow agent's business writes to its subscriptions.

    A live E2E run: a subscription filtered to one employee's timesheets, and the
    agent returned two other people's. The prompt now states the boundary
    (flow_runner); this makes it mechanical — a model that talks itself into a
    record outside the filter is refused, not trusted.

    Matching is equality on the filter's keys against the row's CURRENT
    (pre-write) attributes. `ignore=("status",)` at the todo/approval sites,
    because status is the queue's ENTRY condition, not the record's identity:
    the agent legitimately returns an in-scope record and must then be able to
    create its rework todo, by which time the status no longer matches. The
    identity keys — employee_id and friends — are what the incident violated,
    and they always apply. A filter key the row lacks counts as a mismatch:
    refusing too much is recoverable, a leaked write is not.
    """
    scope = actor.write_scope
    if scope is None:
        return
    queue_filter = scope.get(entity_type)
    if queue_filter is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"the hosted principal has no enabled subscription for {entity_type}",
        )
    for field_name, expected in queue_filter.items():
        if field_name in ignore:
            continue
        if getattr(row, field_name, None) != expected:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"outside this subscription's boundary: {entity_type} record's "
                    f"{field_name} does not match the subscription filter"
                ),
            )


def scoped_write_target(db: Session, tenant_id: str, entity_type: str, entity_id: str):
    """The row a todo or approval fact points at, for the scope check above.
    Builtins resolve through the family registry; anything else is a custom
    business object whose entity_type is its object_type."""
    model = TODO_TARGET_MODELS.get(entity_type)
    if model is not None:
        return db.scalar(
            select(model).where(model.tenant_id == tenant_id, model.id == entity_id)
        )
    return db.scalar(
        select(BusinessObject).where(
            BusinessObject.tenant_id == tenant_id,
            BusinessObject.id == entity_id,
            BusinessObject.object_type == entity_type,
        )
    )


def apply_status_change(db: Session, actor: Actor, document, new_status: str) -> None:
    """Machine-guarded, audited status move — the PATCH half of every
    lifecycle. Validates the transition and records the audit fact; the
    caller's setattr loop performs the actual write."""
    family = DOCUMENT_FAMILIES[type(document)]
    if family.advance_permission:
        require_permission(actor, family.advance_permission)
    require_hosted_write_scope(actor, family.object_type, document)
    machine = get_builtin_machine(db, document.tenant_id, family.object_type)
    validate_transition(machine, document.status, new_status, subject=family.object_type)
    record_audit(
        db,
        tenant_id=document.tenant_id,
        action=f"{family.audit_prefix}.status_changed",
        entity_type=family.object_type,
        entity_id=document.id,
        actor=actor.label,
        detail={**family.audit_identity(document), "from": document.status, "to": new_status},
    )


def ensure_no_operator_closure_marker(metadata: dict | None) -> None:
    """A tenant may not mint its own historical-conflict closure.

    The typed column is unwritable through the API, which is the guarantee the
    exemption rests on — but the migration that fills that column promotes this
    metadata key, and metadata IS caller-supplied. Before an environment has
    run that migration, anybody holding `approval.record` could plant the word
    and be exempted from the one-decision rule the moment it does. The key
    ships in the open-core export, so it is public knowledge, not a secret.

    Same shape as `ensure_label_is_not_impersonation`: the real guarantee is
    structural, and this keeps the tenant-supplied side from imitating it.
    A genuine closure is written by the operator script straight to the
    database, which never passes through here.
    """
    if metadata and OPERATOR_CONFLICT_CLOSURE_KEY in metadata:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"metadata key {OPERATOR_CONFLICT_CLOSURE_KEY!r} is reserved for "
                "an authorized operator remediation and cannot be set through "
                "the API"
            ),
        )


def ensure_node_undecided(db: Session, tenant_id: str, payload) -> None:
    """One decision per node — the readable half of a guard the index enforces.

    The natural key includes `action`, which makes a retry idempotent and used
    to let `approved` and `rejected` both stand at the same round and sequence:
    one seat, two contradictory decisions, nothing saying which one counts.

    Nobody has to misbehave to get there. The same approver opens two agent
    sessions, lists the queue in both, decides in one — and the other is now
    holding a list that was true when it was read. That is the ordinary shape
    of the mistake, which is why the server takes it rather than leaving it to
    an agent's memory of what it has already done.

    The 409 names the decision that already stands, because "conflict" alone
    sends an agent looking for its own error when the answer is that a
    colleague — or its other self — got there first.
    """
    if payload.action not in DECIDED_APPROVAL_ACTIONS:
        return
    closed_history = db.scalar(
        select(ApprovalRecord).where(
            ApprovalRecord.tenant_id == tenant_id,
            ApprovalRecord.entity_type == payload.entity_type,
            ApprovalRecord.entity_id == payload.entity_id,
            ApprovalRecord.round_no == payload.round_no,
            ApprovalRecord.sequence_no == payload.sequence_no,
            ApprovalRecord.historical_conflict_closed.is_(True),
        )
    )
    if closed_history is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"round {payload.round_no} step {payload.sequence_no} is a closed "
                "historical approval conflict. Do not decide it again; retire its "
                "remaining work through the document or Todo workflow."
            ),
        )
    decided = db.scalar(
        select(ApprovalRecord).where(
            ApprovalRecord.tenant_id == tenant_id,
            ApprovalRecord.entity_type == payload.entity_type,
            ApprovalRecord.entity_id == payload.entity_id,
            ApprovalRecord.round_no == payload.round_no,
            ApprovalRecord.sequence_no == payload.sequence_no,
            ApprovalRecord.action.in_(DECIDED_APPROVAL_ACTIONS),
            ApprovalRecord.historical_conflict_closed.is_(False),
        )
    )
    if decided is None:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"round {payload.round_no} step {payload.sequence_no} was already "
            f"{decided.action} by {decided.approver_id} at {decided.acted_at} — "
            "a step holds one decision. Re-read the approval trail before acting: "
            "this one is settled, and if it needs revisiting that is a new round, "
            "not a second decision in this one"
        ),
    )




def require_submission_before_decision(payload) -> None:
    """Sequence 1 of a round is the submission; a decision cannot sit there.

    The audit asks that every decided approval have a `submitted` record at a
    LOWER sequence. Nothing enforced it, and `sequence_no` defaults to 1 — so
    an agent recording an approval without passing a sequence put the decision
    at the submission's own place, where no submission can ever precede it. An
    integrity audit found 133 such rows. Cleaning them would not have stopped
    the next one; the default did that.

    The refusal is deliberately about the ARITHMETIC and not about the rest of
    the trail. Whether a decision may be recorded for a document that was
    never submitted is the tenant's flow to define — the server records the
    facts an agent reports and does not adjudicate their order beyond this:
    position 1 is taken, by definition, by the submission. Refusing more than
    that would block a historical import, an auto-approval, or a
    tenant-defined object whose flow has no submission step at all.
    """
    if payload.action in DECIDED_APPROVAL_ACTIONS and payload.sequence_no <= 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"sequence_no 1 is the submission; a {payload.action} record "
                "belongs after it. Use the sequence the workflow admin put on "
                "the todo (metadata.sequence_no), or the next free sequence in "
                "this round."
            ),
        )


def record_submission_fact(
    db: Session,
    actor: Actor,
    entity_type: str,
    entity_id: str,
    acted_at: datetime,
) -> None:
    """Write the `submitted` approval fact for a submission the server just made.

    The approval trail is supposed to open with it — `round_no=1,
    sequence_no=1` — and every later decision is ordered against it. It used to
    be the SUBMITTER's job: post the fact if your role carries
    `approval.record`, and if it does not, skip it and let the workflow admin
    backfill from `submitted_at`. Two agents had to remember, one of them
    conditionally, for a fact the server itself performs and already stores.
    They did not always remember, and the integrity audit found 133 decided
    approvals with nothing in front of them.

    So the server writes it. The round is derived rather than passed: a
    submission opens round 1, and each `returned` sends the document back for
    another one, which is exactly the rule the submit skills stated in prose.
    The natural key makes this idempotent against an agent that posts the same
    fact anyway — the create endpoint hands back the existing row — so nothing
    breaks for a skill that has not been updated.
    """
    returns = db.scalar(
        select(func.count())
        .select_from(ApprovalRecord)
        .where(
            ApprovalRecord.tenant_id == actor.tenant_id,
            ApprovalRecord.entity_type == entity_type,
            ApprovalRecord.entity_id == entity_id,
            ApprovalRecord.action == "returned",
        )
    )
    round_no = (returns or 0) + 1
    already = db.scalar(
        select(ApprovalRecord).where(
            ApprovalRecord.tenant_id == actor.tenant_id,
            ApprovalRecord.entity_type == entity_type,
            ApprovalRecord.entity_id == entity_id,
            ApprovalRecord.round_no == round_no,
            ApprovalRecord.sequence_no == 1,
            ApprovalRecord.action == "submitted",
        )
    )
    if already is not None:
        return
    db.add(
        ApprovalRecord(
            tenant_id=actor.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            round_no=round_no,
            sequence_no=1,
            action="submitted",
            approver_id=actor.label,
            approver_role="submitter",
            source="system",
            acted_at=acted_at,
        )
    )


def submit_document(db: Session, actor: Actor, model, document_id: str) -> dict:
    """POST .../submit — the one transition a member may drive themselves."""
    family = DOCUMENT_FAMILIES[model]
    document = get_active_document_or_404(db, model, actor.tenant_id, document_id)
    require_family_permission(actor, family, document)
    require_hosted_write_scope(actor, family.object_type, document)
    if family.owner_checked:
        enforce_member_employee(actor, document.employee_id)
    if document.status == "submitted":
        # idempotent resubmit
        return envelope(_document_read(family, document))
    machine = get_builtin_machine(db, actor.tenant_id, family.object_type)
    validate_transition(machine, document.status, "submitted", subject=family.object_type)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action=f"{family.audit_prefix}.submitted",
        entity_type=family.object_type,
        entity_id=document.id,
        actor=actor.label,
        detail={**family.audit_identity(document), "from": document.status},
    )
    document.status = "submitted"
    document.submitted_at = datetime.now(timezone.utc)
    record_submission_fact(
        db, actor, family.object_type, document.id, document.submitted_at
    )
    db.commit()
    db.refresh(document)
    return envelope(_document_read(family, document))


def cancel_todos_for(
    db: Session, actor: Actor, entity_type: str, entity_id: str, *, reason: str
) -> int:
    """Close the open todos pointing at a record that has just been deleted.

    HR issued five payslips, the CEO returned them, and five rework todos
    appeared. HR then voided all five and issued five fresh ones, which were
    approved — and the five todos stayed open forever, attached to documents
    that no longer exist. Nothing was wrong with the flow: "fix the returned
    document" and "void it and redo it" are both reasonable, and only the first
    one had anything that closed the todo.

    So the server closes them, and only on the fact it is certain of: the thing
    this work item points at is gone, therefore the work item cannot be done.
    That is not a judgment about the flow — a todo whose subject was deleted is
    unactionable whatever the workspace's rules say.

    `cancelled`, never `completed`. The work was not done, and recording that it
    was would make the trail lie about a person's queue. The partial unique
    index only reserves `open`, so a replacement todo on the same record is free
    to exist the moment this one leaves that state.

    Restoring the document does NOT resurrect these rows. The restored record
    re-enters the flow agent's queue (`without_open_todo=true` is what finds
    it), and letting the agent raise fresh work is both simpler and truer than
    reviving a cancellation — the old todo's text may no longer be what needs
    doing.
    """
    open_todos = list(
        db.scalars(
            select(Todo).where(
                Todo.tenant_id == actor.tenant_id,
                Todo.entity_type == entity_type,
                Todo.entity_id == entity_id,
                Todo.status == "open",
            )
        )
    )
    for todo in open_todos:
        todo.status = "cancelled"
        record_audit(
            db,
            tenant_id=actor.tenant_id,
            action="todo.cancelled",
            entity_type="todo",
            entity_id=todo.id,
            actor=attributed(actor, None),
            detail={
                "employee_id": todo.employee_id,
                "title": todo.title,
                "target_type": entity_type,
                "target_id": entity_id,
                "reason": reason,
            },
        )
    return len(open_todos)


def delete_document(db: Session, actor: Actor, model, document_id: str, payload=None) -> Response:
    family = DOCUMENT_FAMILIES[model]
    document = get_scoped_or_404(db, model, actor.tenant_id, document_id)
    require_family_permission(actor, family, document)
    if document.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if family.owner_checked:
        enforce_member_employee(actor, document.employee_id)
    document.deleted_at = datetime.now(timezone.utc)
    if family.attributed_delete:
        document.deleted_by = attributed(actor, payload.deleted_by if payload else None)
        document.delete_reason = payload.delete_reason if payload else None
    cancel_todos_for(
        db, actor, family.object_type, document.id,
        reason=f"{family.object_type} deleted",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def restore_document(db: Session, actor: Actor, model, document_id: str) -> dict:
    family = DOCUMENT_FAMILIES[model]
    document = get_scoped_or_404(db, model, actor.tenant_id, document_id)
    require_family_permission(actor, family, document)
    if family.owner_checked:
        enforce_member_employee(actor, document.employee_id)
    if document.deleted_at is None:
        return envelope(_document_read(family, document))
    document.deleted_at = None
    if family.attributed_delete:
        document.deleted_by = None
        document.delete_reason = None
    db.commit()
    db.refresh(document)
    return envelope(_document_read(family, document))


def ensure_document_not_deleted(document) -> None:
    if document.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{type(document).__name__} not found"
        )


def get_active_document_or_404(db: Session, model, tenant_id: str, document_id: str):
    document = get_scoped_or_404(db, model, tenant_id, document_id)
    ensure_document_not_deleted(document)
    return document


def document_total(declared, line_sum: float) -> tuple[float, str]:
    """What a document says it totals, and which fact answered.

    The contract every family here keeps: `total_amount` is the agreed total,
    and null means the line sum IS the total. Drift is only meaningful if the
    caller can see which of the two was used on each side.
    """
    if declared is None:
        return line_sum, "line_sum"
    return float(declared), "declared"


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


def ensure_not_consumed_by_an_order(db: Session, document) -> None:
    """A quotation an order was written from is history, not a draft.

    The states a document may be edited in are the tenant's to choose, and a
    workspace that keeps `accepted` editable is making a legitimate choice —
    right up to the moment an order quotes it. From then on the quotation is
    the BASELINE that order is measured against: what was agreed, against what
    was ordered. Move it afterwards and every later answer about the gap is
    computed from a number nobody agreed to.

    This is the same argument `ensure_money_fields_editable` already makes one
    level down — a settlement guard is worth nothing if the amount it measured
    can be moved afterwards — applied to the quote→order pair.

    Note what it does NOT depend on: any status, any threshold, any reading of
    the tenant's vocabulary. "An order references this quotation" is a fact
    about rows, which is why the server may hold it.
    """
    if not isinstance(document, SalesQuotation):
        return
    order = db.scalar(
        select(SalesOrder.order_no).where(
            SalesOrder.tenant_id == document.tenant_id,
            SalesOrder.quotation_id == document.id,
            SalesOrder.deleted_at.is_(None),
        )
    )
    if order is None:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"sales order {order} was written from this quotation, so it is "
            "now the agreed baseline and cannot be changed. Revise it into a "
            "new version (POST /sales-quotations/{id}/revise) if the customer "
            "renegotiated, or record the difference on the order itself"
        ),
    )


def ensure_document_editable(db: Session, document) -> None:
    """409 unless the document sits in one of its machine's editable states —
    the single write-gate for lines and adjustments across every family."""
    ensure_not_consumed_by_an_order(db, document)
    family = DOCUMENT_FAMILIES[type(document)]
    machine = get_builtin_machine(db, document.tenant_id, family.object_type)
    editable = editable_states(machine, family.object_type)
    if document.status not in editable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{family.items_phrase} can only be changed while the "
                f"{family.parent_noun} is in {sorted(editable)}{family.editable_hint}"
            ),
        )


def ensure_money_fields_editable(db: Session, document, updates: dict, fields: tuple[str, ...]) -> None:
    """A document's own money may only be restated while it is still editable.

    The settlement endpoint refuses to over-apply, but that guard is worth
    nothing if the amount it measured against can be moved afterwards: shrinking
    an issued invoice's total leaves it settled beyond what it bills — a state
    the integrity audit calls corruption and the API used to allow with a plain
    PATCH.

    So the same states that freeze a document's LINES freeze the amounts on its
    header. Restating an issued document is a void-and-reissue or a credit note,
    not an edit. Which states those are stays the tenant's choice, as ever."""
    family = DOCUMENT_FAMILIES[type(document)]
    changing = [
        field
        for field in fields
        if field in updates and updates[field] != getattr(document, field)
    ]
    if not changing:
        return
    machine = get_builtin_machine(db, document.tenant_id, family.object_type)
    editable = editable_states(machine, family.object_type)
    if document.status not in editable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{', '.join(sorted(changing))} cannot be restated while this "
                f"{family.parent_noun} is {document.status!r} — only in {sorted(editable)}. "
                "Void and reissue it, or record the difference as its own document"
            ),
        )


def ensure_nothing_applied(db: Session, document, *, label: str) -> None:
    """A settled document may not be hidden. The applications against it would
    keep a running total sourced from a row nobody can see, and the ledger would
    point at a document that no longer exists."""
    applied = float(getattr(document, "applied_amount", 0) or 0)
    if abs(applied) > CENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{applied:.2f} is applied to this {label} — reverse those "
                "applications before deleting it"
            ),
        )


def allocate_number(db: Session, model, tenant_id: str) -> str:
    family = DOCUMENT_FAMILIES[model]
    return allocate_document_number(
        db, tenant_id,
        model=model, number_column=getattr(model, family.number_field),
        prefix=family.number_prefix, lock_scope=family.lock_scope, field=family.number_field,
    )


def get_live_or_404(db: Session, model, tenant_id: str, row_id: str):
    """Scoped fetch that treats a soft-deleted row as absent."""
    row = get_scoped_or_404(db, model, tenant_id, row_id)
    if row.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    return row


def require_line_on_document(
    db: Session, tenant_id: str, item_model, parent_field: str, item_field: str,
    parent_id: str, item_id: str,
):
    """The line a write pins to must be a live line of the SAME document."""
    item = get_live_or_404(db, item_model, tenant_id, item_id)
    if getattr(item, parent_field) != parent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{item_field} does not belong to {parent_field}",
        )
    return item


def require_live_line(db: Session, tenant_id: str, item_model, parent_model, parent_field: str, line_id: str):
    """A live line whose document is also live — the shape of every
    cross-document link check and of reading a single line."""
    line = get_live_or_404(db, item_model, tenant_id, line_id)
    ensure_document_not_deleted(get_scoped_or_404(db, parent_model, tenant_id, getattr(line, parent_field)))
    return line


def _sales_order_item_for_link(db: Session, tenant_id: str, sales_order_item_id: str) -> SalesOrderItem:
    """The confirmed sales order line a procure-to-order purchase line pins
    to. Existence and tenant scope only: the ORDER may be in any live state —
    that is the point, procurement happens after confirmation locks it."""
    return require_live_line(db, tenant_id, SalesOrderItem, SalesOrder, "order_id", sales_order_item_id)


def _purchase_request_item_for_po_link(db: Session, tenant_id: str, purchase_request_item_id: str) -> PurchaseRequestItem:
    """The approved request line a PO line orders. Existence and tenant scope
    only — the REQUEST may be in any live state; ordering happens after its
    approval locks it, which is the same reason the sales link works this way."""
    return require_live_line(
        db, tenant_id, PurchaseRequestItem, PurchaseRequest, "request_id", purchase_request_item_id
    )


@dataclass(frozen=True)
class ItemFamily:
    """The four line-item families differ only in data: which document they
    hang off, which capability writes them, whether the parent has an owner,
    which extra columns exist, whether the catalog list price is snapshotted,
    and which cross-document link (if any) a line may pin to."""

    parent_model: type
    parent_field: str
    permission: str
    owner_checked: bool
    read_model: type
    extra_fields: tuple[str, ...]        # payload attrs copied verbatim
    capture_list_price: bool = False     # sales lines snapshot the catalog price
    link_field: str | None = None
    link_validator: object | None = None
    list_order: object | None = None     # model -> order_by columns


ITEM_FAMILIES: dict[type, ItemFamily] = {
    SalesQuotationItem: ItemFamily(
        SalesQuotation, "quotation_id", "quotation.submit_own", True, SalesQuotationItemRead,
        ("line_no", "tax_rate", "is_gift", "lead_time"), capture_list_price=True,
        list_order=lambda m: (m.line_no.asc().nulls_last(), m.created_at.desc()),
    ),
    SalesOrderItem: ItemFamily(
        SalesOrder, "order_id", "order.submit_own", True, SalesOrderItemRead,
        ("line_no", "tax_rate", "is_gift", "promised_date"), capture_list_price=True,
        list_order=lambda m: (m.line_no.asc().nulls_last(), m.created_at.desc()),
    ),
    PurchaseOrderItem: ItemFamily(
        PurchaseOrder, "po_id", "purchase_order.manage", False, PurchaseOrderItemRead,
        ("line_no", "tax_rate", "promised_date"),
        link_field="purchase_request_item_id", link_validator=_purchase_request_item_for_po_link,
        list_order=lambda m: (m.line_no.asc().nulls_last(), m.created_at.asc(), m.id.asc()),
    ),
    PurchaseRequestItem: ItemFamily(
        PurchaseRequest, "request_id", "purchase.submit_own", True, PurchaseRequestItemRead,
        (),
        link_field="sales_order_item_id", link_validator=_sales_order_item_for_link,
        list_order=lambda m: (m.created_at.desc(),),
    ),
}


def _item_read(family: ItemFamily, item) -> dict:
    return family.read_model.model_validate(item).model_dump(by_alias=True)


def _item_write_gate(db: Session, actor: Actor, family: ItemFamily, parent_id: str):
    parent = get_active_document_or_404(db, family.parent_model, actor.tenant_id, parent_id)
    ensure_document_editable(db, parent)
    if family.owner_checked:
        enforce_member_employee(actor, parent.employee_id)
    return parent


def list_items(db: Session, tenant_id: str, model, filters: dict[str, str | None]) -> dict:
    """One list shape for every line family: live lines of live documents,
    equality filters, the family's own ordering."""
    family = ITEM_FAMILIES[model]
    stmt = (
        select(model)
        .join(family.parent_model, getattr(model, family.parent_field) == family.parent_model.id)
        .where(
            model.tenant_id == tenant_id,
            model.deleted_at.is_(None),
            family.parent_model.deleted_at.is_(None),
        )
    )
    return list_rows(
        db, stmt,
        filters={getattr(model, column): value for column, value in filters.items()},
        order_by=family.list_order(model),
        pagination=None,
        render=lambda rows: [_item_read(family, row) for row in rows],
    )


def build_item(db: Session, actor: Actor, model, payload, *, parent=None):
    """One validated line, standalone or inline — the single set of rules for
    both paths; the inline path exists to save turns, not to skip checks.

    `parent` passed = the line rides the document's own create: identity comes
    from the parent, and the editable-state gate does not apply — the person is
    stating the document as a whole, including record-won documents created
    directly in a later state."""
    family = ITEM_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    if parent is None:
        parent_id = getattr(payload, family.parent_field)
        _item_write_gate(db, actor, family, parent_id)
    else:
        named = getattr(payload, family.parent_field)
        if named and named != parent.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "inline items belong to the document being created; "
                    f"do not name another {family.parent_field}"
                ),
            )
        parent_id = parent.id
    if payload.attachment_id:
        get_scoped_or_404(db, Attachment, tenant_id, payload.attachment_id)
    link_id = getattr(payload, family.link_field) if family.link_field else None
    if link_id:
        family.link_validator(db, tenant_id, link_id)
    product_id, sku_id, product_name_snapshot, unit = normalize_product_context(
        db, tenant_id, payload.product_id, payload.sku_id, payload.product_name_snapshot, payload.unit
    )
    if product_id is None and not product_name_snapshot:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="an item needs a product_id (or sku_id) or a free-text product_name_snapshot",
        )
    values = {field: getattr(payload, field) for field in family.extra_fields}
    if family.link_field:
        values[family.link_field] = link_id
    if family.capture_list_price:
        list_price_snapshot = payload.list_price_snapshot
        if list_price_snapshot is None and (product_id or sku_id):
            # capture the catalog truth at writing time; an explicit payload
            # value (e.g. a customer-tier price list) wins
            list_price_snapshot = catalog_list_price(db, tenant_id, product_id, sku_id)
        values["list_price_snapshot"] = list_price_snapshot
    item = model(
        tenant_id=tenant_id,
        **{family.parent_field: parent_id},
        product_id=product_id,
        sku_id=sku_id,
        product_name_snapshot=product_name_snapshot,
        spec=payload.spec,
        quantity=payload.quantity,
        unit=unit,
        unit_price=payload.unit_price,
        amount=payload.amount,
        attachment_id=payload.attachment_id,
        notes=payload.notes,
        custom_fields_jsonb=payload.custom_fields,
        **values,
    )
    db.add(item)
    db.flush()
    return item


def create_item(db: Session, actor: Actor, model, payload) -> dict:
    item = build_item(db, actor, model, payload)
    db.commit()
    db.refresh(item)
    return envelope(_item_read(ITEM_FAMILIES[model], item))


def get_item(db: Session, tenant_id: str, model, item_id: str) -> dict:
    family = ITEM_FAMILIES[model]
    item = require_live_line(db, tenant_id, model, family.parent_model, family.parent_field, item_id)
    return envelope(_item_read(family, item))


def update_item(db: Session, actor: Actor, model, item_id: str, payload) -> dict:
    family = ITEM_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    item = get_live_or_404(db, model, tenant_id, item_id)
    _item_write_gate(db, actor, family, getattr(item, family.parent_field))
    updates = payload.model_dump(exclude_unset=True)
    if "attachment_id" in updates and updates["attachment_id"]:
        get_scoped_or_404(db, Attachment, tenant_id, updates["attachment_id"])
    if family.link_field and updates.get(family.link_field):
        family.link_validator(db, tenant_id, updates[family.link_field])
    if "product_id" in updates or "sku_id" in updates or "product_name_snapshot" in updates or "unit" in updates:
        # changing the product without naming a sku drops the old sku — a
        # stale variant must never survive a product swap
        product_unchanged = updates.get("product_id", item.product_id) == item.product_id
        sku_default = item.sku_id if product_unchanged else None
        product_id, sku_id, product_name_snapshot, unit = normalize_product_context(
            db,
            tenant_id,
            updates.get("product_id", item.product_id),
            updates.get("sku_id", sku_default),
            updates.get("product_name_snapshot", item.product_name_snapshot),
            updates.get("unit", item.unit),
        )
        refs_changed = (product_id, sku_id) != (item.product_id, item.sku_id)
        item.product_id = product_id
        item.sku_id = sku_id
        item.product_name_snapshot = product_name_snapshot
        item.unit = unit
        if family.capture_list_price and refs_changed and "list_price_snapshot" not in updates:
            # the snapshot follows the new reference (None when uncataloged);
            # an old product's price must never survive a product swap
            item.list_price_snapshot = catalog_list_price(db, tenant_id, product_id, sku_id)
        updates.pop("product_id", None)
        updates.pop("sku_id", None)
        updates.pop("product_name_snapshot", None)
        updates.pop("unit", None)
    if "custom_fields" in updates:
        item.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return envelope(_item_read(family, item))


def delete_item(db: Session, actor: Actor, model, item_id: str) -> Response:
    family = ITEM_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    item = get_scoped_or_404(db, model, tenant_id, item_id)
    if item.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    _item_write_gate(db, actor, family, getattr(item, family.parent_field))
    item.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def archive_row(
    db: Session,
    actor: Actor,
    model,
    row_id: str,
    *,
    permission: str | None = None,
    audit_action: str | None = None,
    audit_entity_type: str | None = None,
    audit_detail=None,
) -> Response:
    """Master data archives, never deletes: existing records keep whatever
    they already reference — archiving only removes the row from what NEW
    records may use, and the history beneath it stays readable.

    `audit_action` is opt-in per family rather than always-on: most families
    here have never written an audit entry for an archive, and turning that on
    for all of them at once is a separate decision from fixing the one family
    whose vocabulary changes silently reinterpret existing records."""
    if permission:
        require_permission(actor, permission)
    else:
        require_master_data_manage(actor)
    row = get_scoped_or_404(db, model, actor.tenant_id, row_id)
    row.status = "archived"
    if audit_action:
        # Stated, not singularized off the table name: `rstrip("s")` is right
        # for `type_options` and wrong the first time a table is not spelled
        # that way, and a wrong entity_type in an audit trail is worse than a
        # missing one — it is a record filed under something that never
        # happened.
        assert audit_entity_type, "audit_action needs audit_entity_type"
        record_audit(
            db,
            tenant_id=actor.tenant_id,
            action=audit_action,
            entity_type=audit_entity_type,
            entity_id=row.id,
            actor=actor.label,
            detail=audit_detail(row) if callable(audit_detail) else audit_detail,
        )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def exclude_rows_with_open_todo(stmt, model, tenant_id: str, entity_type: str):
    """NOT-EXISTS filter for work queues: rows someone already has an open
    todo to act on are hidden, leaving what still needs an assignment
    (e.g. status=submitted&without_open_todo=true)."""
    return stmt.where(
        ~select(Todo.id)
        .where(
            Todo.tenant_id == tenant_id,
            Todo.entity_type == entity_type,
            Todo.entity_id == model.id,
            Todo.status == "open",
        )
        .exists()
    )


def document_approvals(db: Session, tenant_id: str, entity_type: str, entity_id: str) -> list:
    """The approval trail every /detail carries, in workflow order."""
    return db.scalars(
        select(ApprovalRecord)
        .where(
            ApprovalRecord.tenant_id == tenant_id,
            ApprovalRecord.entity_type == entity_type,
            ApprovalRecord.entity_id == entity_id,
        )
        .order_by(ApprovalRecord.round_no.asc(), ApprovalRecord.sequence_no.asc(), ApprovalRecord.acted_at.asc())
    ).all()


def attachments_for_items(db: Session, tenant_id: str, items) -> list:
    attachment_ids = {item.attachment_id for item in items if item.attachment_id}
    if not attachment_ids:
        return []
    return db.scalars(
        select(Attachment).where(Attachment.tenant_id == tenant_id, Attachment.id.in_(attachment_ids))
    ).all()


def load_item_catalog_context(db: Session, tenant_id: str, items) -> tuple[dict, dict, set]:
    """(skus_by_id, products_by_id, products_with_skus) for a set of lines —
    the three maps every /detail needs to label its lines, in three reads
    regardless of how many lines the document has."""
    sku_ids = {item.sku_id for item in items if item.sku_id}
    skus = (
        db.scalars(
            select(ProductSku).where(ProductSku.tenant_id == tenant_id, ProductSku.id.in_(sku_ids))
        ).all()
        if sku_ids
        else []
    )
    skus_by_id = {sku.id: sku for sku in skus}
    item_product_ids = {item.product_id for item in items if item.product_id}
    products_with_skus = (
        set(
            db.scalars(
                select(ProductSku.product_id)
                .where(
                    ProductSku.tenant_id == tenant_id,
                    ProductSku.product_id.in_(item_product_ids),
                    ProductSku.status == "active",
                )
                .group_by(ProductSku.product_id)
            ).all()
        )
        if item_product_ids
        else set()
    )
    product_ids = set(item_product_ids)
    product_ids.update(sku.product_id for sku in skus)
    products = (
        db.scalars(
            select(Product).where(Product.tenant_id == tenant_id, Product.id.in_(product_ids))
        ).all()
        if product_ids
        else []
    )
    return skus_by_id, {product.id: product for product in products}, products_with_skus


def resolve_item_refs(item, skus_by_id: dict, products_by_id: dict) -> tuple:
    """(product, sku) for one line, from the catalog context maps."""
    sku = skus_by_id.get(item.sku_id) if item.sku_id else None
    if sku is not None and item.product_id is not None and sku.product_id != item.product_id:
        # Defensive against historic/corrupt cross-product references: do
        # not attach a misleading label even though writes now prevent it.
        sku = None
    product_id = item.product_id or (sku.product_id if sku is not None else None)
    return (products_by_id.get(product_id) if product_id else None), sku


def sku_pending_flag(item, products_with_skus: set) -> bool:
    """A variant product quoted/ordered at product level: the SKU decision
    is still open — surfaced so reviewers see 尺码待定 at a glance."""
    return bool(item.product_id and not item.sku_id and item.product_id in products_with_skus)


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


def grouped_linked_lines(
    db: Session, tenant_id: str, line_model, link_field: str,
    parent_model, parent_field: str, target_ids, build,
) -> dict[str, list]:
    """The reverse side of a cross-document link: for each target line id,
    the live lines pinned to it (with live parents), rendered by `build` —
    two reads for the whole document."""
    grouped: dict[str, list] = {}
    if not target_ids:
        return grouped
    lines = db.scalars(
        select(line_model)
        .where(
            line_model.tenant_id == tenant_id,
            getattr(line_model, link_field).in_(target_ids),
            line_model.deleted_at.is_(None),
        )
        .order_by(line_model.created_at.asc(), line_model.id.asc())
    ).all()
    parent_ids = {getattr(line, parent_field) for line in lines}
    parents_by_id = (
        {
            parent.id: parent
            for parent in db.scalars(
                select(parent_model).where(
                    parent_model.tenant_id == tenant_id, parent_model.id.in_(parent_ids)
                )
            ).all()
        }
        if parent_ids
        else {}
    )
    for line in lines:
        parent = parents_by_id.get(getattr(line, parent_field))
        if parent is None or parent.deleted_at is not None:
            continue
        grouped.setdefault(getattr(line, link_field), []).append(build(line, parent))
    return grouped


def get_locked_product_or_404(db: Session, tenant_id: str, product_id: str) -> Product:
    """Lock the SKU parent row before checking or changing variant identity.

    Product SKU variants are stored as free-form JSON, so a portable database
    uniqueness constraint cannot express their full equality. Serializing all
    identity-changing paths on the parent product closes that race instead.
    """
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.tenant_id == tenant_id)
        .with_for_update()
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


def validate_header_entry_link(header: TimesheetHeader, employee_id: str, work_date) -> None:
    if header.employee_id != employee_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="employee_id must match the header")
    if not (header.period_start <= work_date <= header.period_end):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="work_date must be inside the header period")


def normalize_project_context(
    db: Session,
    tenant_id: str,
    project_id: str | None,
    project_name_snapshot: str | None,
) -> tuple[str | None, str | None]:
    if not project_id:
        return None, project_name_snapshot
    project = get_scoped_or_404(db, Project, tenant_id, project_id)
    return project.id, project_name_snapshot or project.project_name


def normalize_vendor_context(
    db: Session,
    tenant_id: str,
    vendor_id: str | None,
    merchant: str | None,
) -> tuple[str | None, str | None]:
    """Same contract as normalize_project_context: a vendor_id must be a real
    record (404 otherwise) and backfills the free-text merchant snapshot;
    without one, merchant stays whatever the receipt said."""
    if not vendor_id:
        return None, merchant
    vendor = get_scoped_or_404(db, Vendor, tenant_id, vendor_id)
    return vendor.id, merchant or vendor.name


def ensure_invoice_not_duplicated(
    db: Session,
    tenant_id: str,
    invoice_number: str | None,
    exclude_item_id: str | None = None,
    *,
    direction: str = "purchase",
    exclude_invoice_id: str | None = None,
) -> None:
    """The duplicate-booking control: one tax invoice number may only be booked
    once per tenant.

    For 进项 the check spans BOTH places such an invoice can land — an expense
    item and a vendor bill — because the expensive mistake is precisely the one
    a single-table check misses: the same receipt reimbursed to an employee and
    then paid again against the supplier's own invoice. Sales-side numbers are
    ours to issue, so they only have to be unique among our own invoices.

    The agent should catch this in conversation; the server is the hard
    backstop."""
    if not invoice_number:
        return
    if direction == "purchase":
        claimed = (
            select(ExpenseItem)
            .join(ExpenseClaim, ExpenseItem.claim_id == ExpenseClaim.id)
            .where(
                ExpenseItem.tenant_id == tenant_id,
                ExpenseItem.invoice_number == invoice_number,
                ExpenseItem.deleted_at.is_(None),
                ExpenseClaim.deleted_at.is_(None),
            )
        )
        if exclude_item_id:
            claimed = claimed.where(ExpenseItem.id != exclude_item_id)
        existing_item = db.scalars(claimed).first()
        if existing_item is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"invoice {invoice_number!r} is already claimed on expense item "
                    f"{existing_item.id} (claim {existing_item.claim_id})"
                ),
            )
    booked = select(Invoice).where(
        Invoice.tenant_id == tenant_id,
        Invoice.direction == direction,
        Invoice.tax_invoice_number == invoice_number,
        Invoice.deleted_at.is_(None),
    )
    if exclude_invoice_id:
        booked = booked.where(Invoice.id != exclude_invoice_id)
    existing_invoice = db.scalars(booked).first()
    if existing_invoice is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"invoice {invoice_number!r} is already booked on "
                f"{existing_invoice.invoice_no} ({existing_invoice.id})"
            ),
        )


def normalize_product_context(
    db: Session,
    tenant_id: str,
    product_id: str | None,
    sku_id: str | None,
    product_name_snapshot: str | None,
    unit: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Same contract as normalize_project_context: ids must be real records
    (404 otherwise) and backfill the free-text name/unit snapshots; without
    them, the free text stands alone. A sku alone derives its product; a sku
    given with a mismatching product is a 400 — the pair must agree."""
    if sku_id:
        sku = get_scoped_or_404(db, ProductSku, tenant_id, sku_id)
        if product_id and product_id != sku.product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="sku_id does not belong to the given product_id",
            )
        product_id = sku.product_id
    if not product_id:
        return None, None, product_name_snapshot, unit
    product = get_scoped_or_404(db, Product, tenant_id, product_id)
    return product.id, sku_id, product_name_snapshot or product.name, unit or product.unit


def product_has_skus(db: Session, tenant_id: str, product_id: str) -> bool:
    return db.scalar(
        select(ProductSku.id)
        .where(
            ProductSku.tenant_id == tenant_id,
            ProductSku.product_id == product_id,
            ProductSku.status == "active",
        )
        .limit(1)
    ) is not None


def existing_product_sku_variant_attrs(
    db: Session,
    tenant_id: str,
    product_id: str,
    *,
    exclude_sku_id: str | None = None,
) -> list[dict]:
    stmt = select(ProductSku.variant_attrs).where(
        ProductSku.tenant_id == tenant_id,
        ProductSku.product_id == product_id,
    )
    if exclude_sku_id is not None:
        stmt = stmt.where(ProductSku.id != exclude_sku_id)
    return [attrs or {} for attrs in db.scalars(stmt).all()]


def json_value_identity(value):
    """Return a hashable, JSON-type-aware identity for a decoded value.

    Python considers ``True == 1`` and ``False == 0``. JSON does not: booleans
    and numbers are different value types. Tag every JSON type before comparing
    recursively so variant identity follows JSON semantics while retaining
    numeric equivalence such as ``1 == 1.0``.
    """
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, (int, float)):
        return ("number", value)
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, list):
        return ("array", tuple(json_value_identity(item) for item in value))
    if isinstance(value, dict):
        return (
            "object",
            tuple(
                sorted(
                    (key, json_value_identity(item))
                    for key, item in value.items()
                )
            ),
        )
    # ``variant_attrs`` comes from JSON request bodies / JSON(B) columns, so
    # reaching this branch indicates corrupt or non-JSON application data.
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


def ensure_product_sku_variant_attrs_available(
    db: Session,
    tenant_id: str,
    product_id: str,
    variant_attrs: dict,
    *,
    exclude_sku_id: str | None = None,
) -> None:
    # Empty attributes describe no variant identity and remain valid for legacy
    # and SKU-code-only catalogs. Only a non-empty exact JSON combination is
    # reserved.
    existing_identities = {
        json_value_identity(attrs)
        for attrs in existing_product_sku_variant_attrs(
            db,
            tenant_id,
            product_id,
            exclude_sku_id=exclude_sku_id,
        )
    }
    if variant_attrs and json_value_identity(variant_attrs) in existing_identities:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SKU with identical variant attributes already exists for this product",
        )


def product_sku_stats(
    db: Session,
    tenant_id: str,
    product_ids: list[str],
) -> dict[str, tuple[int, int]]:
    if not product_ids:
        return {}

    rows = db.execute(
        select(
            ProductSku.product_id,
            func.count(),
            func.sum(case((ProductSku.status == "active", 1), else_=0)),
        )
        .where(ProductSku.tenant_id == tenant_id, ProductSku.product_id.in_(product_ids))
        .group_by(ProductSku.product_id)
    ).all()
    return {product_id: (int(total), int(active or 0)) for product_id, total, active in rows}


def product_sku_counts(db: Session, tenant_id: str, product_ids: list[str]) -> dict[str, int]:
    """Historical count for catalog display, including archived variants."""
    return {
        product_id: total
        for product_id, (total, _active) in product_sku_stats(db, tenant_id, product_ids).items()
    }


def product_reads_with_sku_stats(db: Session, tenant_id: str, products) -> list[dict]:
    """Product reads carrying their variant counts — one stats query however
    many rows the page has."""
    stats = product_sku_stats(db, tenant_id, [product.id for product in products])
    data = []
    for product in products:
        read = ProductRead.model_validate(product)
        total, active = stats.get(product.id, (0, 0))
        read.sku_count = total
        read.has_skus = active > 0
        data.append(read.model_dump(by_alias=True))
    return data


def product_read_with_skus_flag(db: Session, product: Product) -> dict:
    return product_reads_with_sku_stats(db, product.tenant_id, [product])[0]


def purchase_item_estimate(item: PurchaseRequestItem) -> float | None:
    """A line's estimated cost: explicit amount wins; otherwise derived from
    unit price; None when the line is unpriced (a normal fact, not an error)."""
    if item.amount is not None:
        return float(item.amount)
    if item.unit_price is not None:
        return float(item.unit_price) * float(item.quantity)
    return None


def normalize_customer_context(
    db: Session,
    tenant_id: str,
    customer_id: str | None,
    customer_name: str | None,
) -> tuple[str | None, str | None]:
    """Same contract as normalize_vendor_context: a customer_id must be a real
    record (404 otherwise) and backfills the free-text snapshot; without one,
    the snapshot stands alone (a prospect not yet in master data)."""
    if not customer_id:
        return None, customer_name
    customer = get_scoped_or_404(db, Customer, tenant_id, customer_id)
    return customer.id, customer_name or customer.name


def catalog_list_price(db: Session, tenant_id: str, product_id: str | None, sku_id: str | None) -> float | None:
    """The catalog reference price for a line: sku price overrides product
    price; None when the catalog is silent. Captured onto the line as
    list_price_snapshot so the discount stays derivable after catalog edits."""
    if sku_id:
        sku = get_scoped_or_404(db, ProductSku, tenant_id, sku_id)
        if sku.list_price is not None:
            return float(sku.list_price)
        product = get_scoped_or_404(db, Product, tenant_id, sku.product_id)
        return float(product.list_price) if product.list_price is not None else None
    if product_id:
        product = get_scoped_or_404(db, Product, tenant_id, product_id)
        return float(product.list_price) if product.list_price is not None else None
    return None


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


def doc_number_lock_key(scope: str, tenant_id: str) -> int:
    digest = hashlib.sha256()
    for value in (scope, tenant_id):
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return int.from_bytes(digest.digest()[:8], "big", signed=True)


def allocate_document_number(
    db: Session, tenant_id: str, *, model, number_column, prefix: str, lock_scope: str, field: str
) -> str:
    """Next {prefix}NNNNNN for the tenant. Serialized with a transaction-scoped
    advisory lock on PostgreSQL (same idiom as workflow version allocation);
    SQLite (unit tests) has no equivalent and is single-writer anyway.
    Numbers are never reused — soft-deleted documents keep theirs, and the
    unique constraint stays the backstop for agent-supplied numbers."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("select pg_advisory_xact_lock(cast(:lock_key as bigint))"),
            {"lock_key": doc_number_lock_key(lock_scope, tenant_id)},
        )
    latest = db.scalar(
        select(func.max(number_column)).where(
            model.tenant_id == tenant_id,
            # fixed-width suffix: lexicographic max == numeric max
            number_column.like(prefix + "______"),
        )
    )
    try:
        seq = int(latest[len(prefix):]) + 1 if latest else 1
    except ValueError:
        # a tenant-supplied number happens to match the width pattern —
        # restart low and let the existence probe walk past collisions
        seq = 1
    for _ in range(100):
        candidate = f"{prefix}{seq:06d}"
        exists = db.scalar(
            select(model.id)
            .where(model.tenant_id == tenant_id, number_column == candidate)
            .limit(1)
        )
        if exists is None:
            return candidate
        seq += 1
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"unable to allocate a number; supply {field} explicitly",
    )


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


def ensure_business_object_not_deleted(business_object: BusinessObject, detail: str = "BusinessObject not found") -> None:
    if business_object.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def get_active_business_object_or_404(db: Session, tenant_id: str, business_object_id: str) -> BusinessObject:
    business_object = get_scoped_or_404(db, BusinessObject, tenant_id, business_object_id)
    ensure_business_object_not_deleted(business_object)
    return business_object


def get_active_approval_target_or_404(db: Session, tenant_id: str, approval_target_id: str) -> BusinessObject:
    business_object = get_scoped_or_404(db, BusinessObject, tenant_id, approval_target_id)
    ensure_business_object_not_deleted(business_object, detail="ApprovalTarget not found")
    return business_object


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


def build_timesheet_todo_content(db: Session, header: TimesheetHeader) -> tuple[str, str]:
    employee = get_scoped_or_404(db, Employee, header.tenant_id, header.employee_id)
    title = f"Review timesheet for {employee.name}"
    description = (
        f"Review timesheet {header.period_start.isoformat()} to {header.period_end.isoformat()} "
        f"for employee {employee.name}."
    )
    return title, description


def build_business_object_todo_content(target: BusinessObject) -> tuple[str, str]:
    title = f"Review {target.title}"
    description = target.summary or f"Review {target.object_type.replace('_', ' ')}: {target.title}."
    return title, description


def ensure_content_edit_allowed(actor: Actor, family: str, updates: dict) -> None:
    """A document's own fields are the submitter's write; only `status` is the
    flow's.

    Status is guarded where it is applied, by the family's `advance` verb. The
    rest of the header is what a person reported — their hours, their narrative,
    their claim — so changing it takes the same capability that filed it. This
    changes nothing for the tenant's own credentials: a member editing their own
    header holds `submit_own` and has already passed the own-employee check, and
    admins and tenant service keys hold or bypass everything. It draws the line
    for a principal that may advance a flow while being nobody in the company —
    ORYH's hosted agent can move a timesheet to `approved`, and cannot touch a
    word of what the employee wrote."""
    if any(field != "status" for field in updates):
        require_permission(actor, f"{family}.submit_own")


def same_todo_assignment(existing: Todo, payload: CreateTodoRequest) -> bool:
    """Whether a create request is a retry of the open todo it collided with.

    Employee + entity already matched to get here. What separates "the same
    assignment again" from "a new assignment on a stale view" is the flow
    position the assigner wrote down: a second finance review in round 2 is a
    genuinely different todo from the round-1 one, even for the same person on
    the same document. Round/sequence live in metadata because oryh never
    interprets them — it only has to notice when they differ."""
    if (existing.todo_type or None) != (payload.todo_type or None):
        return False
    existing_metadata = existing.metadata_jsonb or {}
    requested_metadata = payload.metadata or {}
    return all(
        existing_metadata.get(field) == requested_metadata.get(field)
        for field in ("round_no", "sequence_no")
    )


# What a todo or an approval fact may point at.
#
# Derived from DOCUMENT_FAMILIES rather than restated, because restating it is
# how this broke: the same list lived in an if-chain here, in a CHECK
# constraint in the migrations, and in DOCUMENT_FAMILIES, and the three drifted.
# Invoices, payments and purchase orders reached the API fine and were refused
# by the database — a 500 on an ordinary approval request, on a path
# `$oryh-payment-approval-flow` tells agents to walk.
#
# `tests/test_entity_reference_types.py` pins these against the live CHECK
# constraint, so the next family added fails the build instead of production.
ALLOWED_APPROVAL_ENTITY_TYPES: frozenset[str] = frozenset(APPROVAL_ENTITY_TYPES)
ALLOWED_TODO_ENTITY_TYPES: frozenset[str] = frozenset(TODO_ENTITY_TYPES)


def ensure_referenced_entity_exists(
    db: Session, tenant_id: str, entity_type: str, entity_id: str, *,
    allowed: frozenset[str], label: str,
):
    """One resolver for both todos and approval facts. Returns the row.

    An unknown type is refused here rather than left to the database. The
    approval path used to fall through an if-chain with no else, so a type it
    did not recognise skipped the existence check entirely and reached the
    CHECK constraint — which answered with a 500 rather than a sentence.

    It returns the row it resolved because it had already fetched it and threw
    it away, and the approval path needs the target's `created_at` to refuse a
    decision recorded before the thing it decides existed.
    """
    if entity_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"unsupported {label} entity type {entity_type!r} — "
                f"expected one of: {', '.join(sorted(allowed))}"
            ),
        )
    model = TODO_TARGET_MODELS.get(entity_type)
    if model is not None:
        return get_active_document_or_404(db, model, tenant_id, entity_id)
    if entity_type == "approval_target":
        return get_active_approval_target_or_404(db, tenant_id, entity_id)
    if entity_type == "business_object":
        return get_active_business_object_or_404(db, tenant_id, entity_id)
    return get_scoped_or_404(db, Project, tenant_id, entity_id)


# An agent's host clock is not the server's. Wide enough that an honestly
# stamped "now" never trips the future check, narrow enough that a date pulled
# out of a document never passes it.
ACTED_AT_CLOCK_SKEW = timedelta(minutes=5)


def resolve_acted_at(supplied: datetime | None, target) -> datetime:
    """When the decision happened — the server's answer unless told otherwise.

    This used to be a required field, which meant every caller had to produce a
    timestamp and an agent has no clock. Every skill example showed a literal
    (`"2026-07-11T09:00:00Z"`), so an agent filling the template in took the
    most plausible date in front of it — usually one off the document it was
    approving. Production ended up with approvals recorded before the thing
    they approved existed, which is not a wrong number so much as a trail that
    cannot be true.

    So the server stamps it. Supplying one is now a deliberate act rather than
    a tax on every write, and the two impossible shapes are refused:

    - **the future**, beyond clock skew: nobody decides in advance, and this is
      the shape a guessed date takes when the guess runs forward;
    - **before the target existed**: the shape it takes running backward, and
      the one found in production.

    Backfilling stays possible and one case is already legitimate — the missing
    `submitted` fact takes the document's own `submitted_at`, a stored fact
    rather than an invention, and it satisfies both rules by construction.
    Recording an approval that genuinely predates its record — a historical
    import — is refused: that path does not exist through this API today, and
    when it does it should arrive as a designed feature rather than as the
    absence of a check.
    """
    now = datetime.now(timezone.utc)
    if supplied is None:
        return now

    acted = supplied if supplied.tzinfo else supplied.replace(tzinfo=timezone.utc)
    if acted > now + ACTED_AT_CLOCK_SKEW:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"acted_at {acted.isoformat()} is in the future — a decision cannot be "
                "recorded before it is made. Omit acted_at and the server stamps the "
                "moment of the call."
            ),
        )

    created = getattr(target, "created_at", None)
    if created is not None:
        created = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        if acted < created:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"acted_at {acted.isoformat()} is before this record existed "
                    f"({created.isoformat()}) — the trail would say it was decided "
                    "before it was created. Omit acted_at and the server stamps the "
                    "moment of the call; supply one only when the person you are "
                    "acting for told you the decision happened at another time, and "
                    "never infer it from a date on the document."
                ),
            )
    return acted


def ensure_todo_entity_exists(db: Session, tenant_id: str, entity_type: str, entity_id: str) -> None:
    ensure_referenced_entity_exists(
        db, tenant_id, entity_type, entity_id, allowed=ALLOWED_TODO_ENTITY_TYPES, label="todo"
    )


@router.post("/tenants", status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: CreateTenantRequest,
    db: Annotated[Session, Depends(get_db)],
):
    # Legacy internal bootstrap path; self-service signup goes through
    # /auth/register with email verification.
    if not settings.allow_open_tenant_create:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="open tenant creation is disabled; register via /auth/register",
        )
    tenant, api_key, plain_text_api_key = create_tenant_with_api_key(
        db,
        tenant_name=payload.name,
        tenant_status=payload.status,
        api_key_label=payload.initial_api_key_label,
    )
    provision_tenant_defaults(db, tenant.id)
    db.commit()
    data = CreateTenantResponse(
        tenant=TenantRead.model_validate(tenant),
        api_key=ApiKeyRead.model_validate(api_key),
        plain_text_api_key=plain_text_api_key,
    )
    return envelope(data.model_dump())


@router.get("/tenant")
def get_tenant(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    return envelope(TenantRead.model_validate(tenant).model_dump())


@router.get(
    "/tenant/api-keys",
    response_model=ApiKeyListEnvelope,
    response_model_exclude_unset=True,
)
def list_api_keys(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    user_id: str | None = None,
    status_filter: Annotated[Literal["active", "inactive", "all"] | None, Query(alias="status")] = None,
    is_active: bool | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    require_permission(actor, "keys.manage")
    stmt = select(ApiKey).where(ApiKey.tenant_id == actor.tenant_id)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        matching_user_ids = select(User.id).where(
            User.tenant_id == actor.tenant_id,
            or_(User.name.ilike(pattern), User.email.ilike(pattern)),
        )
        stmt = stmt.where(
            or_(
                ApiKey.label.ilike(pattern),
                cast(ApiKey.id, String).ilike(pattern),
                ApiKey.user_id.in_(matching_user_ids),
            )
        )
    if is_active is not None:
        stmt = stmt.where(ApiKey.is_active.is_(is_active))
    elif status_filter and status_filter != "all":
        stmt = stmt.where(ApiKey.is_active.is_(status_filter == "active"))

    def render(api_keys):
        users = api_key_users(db, actor.tenant_id, api_keys)
        return [
            enriched_api_key(api_key, users.get(api_key.user_id)).model_dump()
            for api_key in api_keys
        ]

    return list_rows(
        db, stmt,
        filters={ApiKey.user_id: user_id},
        order_by=(ApiKey.created_at.desc(), ApiKey.id.desc()),
        pagination=requested_pagination(page, size),
        render=render,
    )


def api_key_users(db: Session, tenant_id: str, api_keys: list[ApiKey]) -> dict[str, User]:
    user_ids = {api_key.user_id for api_key in api_keys if api_key.user_id is not None}
    if not user_ids:
        return {}
    users = db.scalars(
        select(User).where(User.tenant_id == tenant_id, User.id.in_(user_ids))
    ).all()
    return {user.id: user for user in users}


def ensure_label_is_not_impersonation(label: str | None) -> None:
    """Keep the hosted agent's name out of tenant-chosen labels.

    The badge itself is structural (`principal_kind`), so a look-alike label
    cannot actually forge anything. This is the cheap second line: an audit
    reader scanning a column should never have to notice a `key:` prefix to
    tell ORYH's principal from a key the tenant named after it."""
    if label and HOSTED_FLOW_AGENT_DISPLAY_NAME in label:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"名称 {HOSTED_FLOW_AGENT_DISPLAY_NAME!r} 由平台保留，不能用于工作空间凭证",
        )


def enriched_api_key(api_key: ApiKey, user: User | None = None) -> ApiKeyRead:
    owner_is_active = user is not None and user.status == "active"
    effective_active = api_key.is_active and (
        api_key.user_id is None or owner_is_active
    )
    effective_role = None
    if effective_active:
        effective_role = api_key.role if api_key.user_id is None else user.role
    return ApiKeyRead.model_validate(api_key).model_copy(
        update={
            "user_name": user.name if user is not None else None,
            "user_email": user.email if user is not None else None,
            "user_status": user.status if user is not None else None,
            "effective_active": effective_active,
            "effective_role": effective_role,
        }
    )


@router.get(
    "/tenant/api-key-owners",
    response_model=ApiKeyOwnerListEnvelope,
    response_model_exclude_unset=True,
)
def list_api_key_owners(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Search active users eligible to own a user-bound API key.

    This intentionally requires ``keys.manage`` rather than ``users.manage``
    and exposes only the identity fields needed by the key-management UI.
    """
    require_permission(actor, "keys.manage")
    stmt = select(User).where(
        User.tenant_id == actor.tenant_id,
        User.status == "active",
    )
    return list_rows(
        db, stmt,
        keyword=keyword,
        keyword_columns=(User.name, User.email),
        order_by=(User.name.asc(), User.email.asc(), User.id.asc()),
        pagination=(page, size),
        read_model=ApiKeyOwnerRead, by_alias=False,
    )


def valid_uuid_ids(values: list[str]) -> set[str]:
    valid: set[str] = set()
    for value in values:
        try:
            valid.add(str(UUID(value)))
        except (ValueError, TypeError, AttributeError):
            continue
    return valid


@router.post(
    "/directory/display-names/resolve",
    response_model=DisplayNameResolutionEnvelope,
    response_model_exclude_unset=True,
)
def resolve_display_names(
    payload: DisplayNameResolveRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Resolve only the requested tenant-scoped display labels.

    The endpoint deliberately returns maps rather than user/key records so an
    object page can label one bounded page of activity without downloading a
    tenant-wide identity directory or exposing unrelated profile fields.
    """
    employee_ids = valid_uuid_ids(payload.employee_ids)
    requested_user_ids = valid_uuid_ids(
        [label.removeprefix("user:") for label in payload.actor_labels if label.startswith("user:")]
    )
    requested_key_ids = valid_uuid_ids(
        [label.removeprefix("key:") for label in payload.actor_labels if label.startswith("key:")]
    )

    employees = (
        db.scalars(
            select(Employee).where(
                Employee.tenant_id == actor.tenant_id,
                Employee.id.in_(employee_ids),
            )
        ).all()
        if employee_ids
        else []
    )
    users = (
        db.scalars(
            select(User).where(
                User.tenant_id == actor.tenant_id,
                User.id.in_(requested_user_ids),
            )
        ).all()
        if requested_user_ids
        else []
    )
    api_keys = (
        db.scalars(
            select(ApiKey).where(
                ApiKey.tenant_id == actor.tenant_id,
                ApiKey.id.in_(requested_key_ids),
            )
        ).all()
        if requested_key_ids
        else []
    )
    hosted = {
        api_key.id
        for api_key in api_keys
        if api_key.principal_kind == PRINCIPAL_HOSTED_FLOW_AGENT
    }
    result = DisplayNameResolutionRead(
        employees={employee.id: employee.name for employee in employees},
        actors={
            **{
                f"user:{user.id}": user.name or user.email
                for user in users
            },
            **{
                # A hosted principal reads as its canonical name, taken from the
                # constant rather than from `label` — the tenant can neither
                # rename it nor mint a key that renders the same way.
                f"key:{api_key.id}": (
                    HOSTED_FLOW_AGENT_DISPLAY_NAME
                    if api_key.id in hosted
                    else f"key:{api_key.label or api_key.id[:8]}"
                )
                for api_key in api_keys
            },
        },
        actor_kinds={f"key:{key_id}": PRINCIPAL_HOSTED_FLOW_AGENT for key_id in hosted},
    )
    return envelope(result.model_dump())


@router.post(
    "/tenant/api-keys",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateApiKeyEnvelope,
    response_model_exclude_unset=True,
)
def create_api_key(
    payload: CreateApiKeyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "keys.manage")
    ensure_label_is_not_impersonation(payload.label)
    key_role = "service"
    user: User | None = None
    if payload.user_id is not None:
        user = db.get(User, payload.user_id)
        if user is None or user.tenant_id != actor.tenant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if user.status != "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user is not active")
        key_role = user.role
    plain_text_api_key = generate_api_key()
    api_key = ApiKey(
        tenant_id=actor.tenant_id,
        key_hash=hash_api_key(plain_text_api_key),
        label=payload.label,
        user_id=payload.user_id,
        role=key_role,
        # Tenants issue tenant-service keys and nothing else. The hosted
        # principal is minted by the platform (POST /admin/tenants/{id}/
        # hosted-flow-agent-key) so that "ORYH holds a key here" is always the
        # record of a platform action, never something a tenant can assert.
        principal_kind=PRINCIPAL_TENANT_SERVICE,
        is_active=True,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    data = CreateApiKeyResponse(
        api_key=enriched_api_key(api_key, user),
        plain_text_api_key=plain_text_api_key,
    )
    return envelope(data.model_dump())


@router.patch(
    "/tenant/api-keys/{api_key_id}",
    response_model=ApiKeyEnvelope,
    response_model_exclude_unset=True,
)
def update_api_key(
    api_key_id: str,
    payload: UpdateApiKeyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "keys.manage")
    api_key = get_scoped_or_404(db, ApiKey, actor.tenant_id, api_key_id)
    updates = payload.model_dump(exclude_unset=True)
    ensure_label_is_not_impersonation(updates.get("label"))
    if api_key.principal_kind == PRINCIPAL_HOSTED_FLOW_AGENT:
        # The tenant's control over ORYH's principal is exactly one lever:
        # switch it off. Renaming it would break the identity its audit entries
        # are read under, and switching it back on would restore a supplier's
        # access without the supplier — or the subscription — knowing.
        if "label" in updates:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{HOSTED_FLOW_AGENT_DISPLAY_NAME} 的名称由平台固定，不可修改",
            )
        if updates.get("is_active") is True and not api_key.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"{HOSTED_FLOW_AGENT_DISPLAY_NAME} 一经停用即为退订，"
                    "重新启用需要平台重新签发"
                ),
            )
    for field, value in updates.items():
        setattr(api_key, field, value)
    db.commit()
    db.refresh(api_key)
    user = db.get(User, api_key.user_id) if api_key.user_id is not None else None
    return envelope(enriched_api_key(api_key, user).model_dump())


@router.get("/projects", response_model=ProjectListEnvelope, response_model_exclude_unset=True)
def list_projects(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(Project).where(Project.tenant_id == tenant_id),
        filters={Project.status: status_filter},
        keyword=keyword,
        keyword_columns=(Project.project_name,),
        order_by=(Project.created_at.desc(), Project.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=ProjectRead,
    )


MASTER_CODE_FIELDS = {
    Project: ("project_code", "project"),
    Vendor: ("vendor_code", "vendor"),
    Customer: ("customer_code", "customer"),
    Product: ("product_code", "product"),
}


def commit_or_code_conflict(db: Session, row) -> None:
    """Commit a master-data write; a duplicate code becomes a 409 that names
    the holder instead of a 500.

    A live E2E run hit this with a project: the unique index has enforced
    per-tenant codes on postgres since the baseline migration, but no create
    or update here caught IntegrityError, so re-using an ARCHIVED project's
    code surfaced as Internal Server Error. The holder's status matters in
    the message for exactly that reason — the person cannot see an archived
    twin in their default list view, so "already exists" alone reads as a
    lie.
    """
    model = type(row)
    code_field, noun = MASTER_CODE_FIELDS[model]
    code_value = getattr(row, code_field)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if not code_value:
            raise
        holder = db.scalar(
            select(model).where(
                model.tenant_id == row.tenant_id,
                getattr(model, code_field) == code_value,
            )
        )
        if holder is None:
            raise
        detail = f"{code_field} {code_value!r} already belongs to {noun} {holder.id}"
        status_value = getattr(holder, "status", None)
        if status_value and status_value != "active":
            detail += (
                f" (status: {status_value} — it keeps its code; "
                "restore it or pick another code)"
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


@router.post(
    "/projects",
    response_model=ProjectEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    payload: CreateProjectRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    project = Project(
        tenant_id=actor.tenant_id,
        project_code=payload.project_code,
        project_name=payload.project_name,
        client=payload.client,
        status=payload.status,
        start_date=payload.start_date,
        end_date=payload.end_date,
        metadata_jsonb=payload.metadata,
    )
    db.add(project)
    commit_or_code_conflict(db, project)
    db.refresh(project)
    return envelope(ProjectRead.model_validate(project).model_dump(by_alias=True))


@router.get("/projects/{project_id}", response_model=ProjectEnvelope, response_model_exclude_unset=True)
def get_project(
    project_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    project = get_scoped_or_404(db, Project, tenant_id, project_id)
    return envelope(ProjectRead.model_validate(project).model_dump(by_alias=True))


@router.patch("/projects/{project_id}", response_model=ProjectEnvelope, response_model_exclude_unset=True)
def update_project(
    project_id: str,
    payload: UpdateProjectRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    project = get_scoped_or_404(db, Project, actor.tenant_id, project_id)
    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        project.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(project, field, value)
    commit_or_code_conflict(db, project)
    db.refresh(project)
    return envelope(ProjectRead.model_validate(project).model_dump(by_alias=True))


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, Project, project_id)


@router.get("/vendors", response_model=VendorListEnvelope, response_model_exclude_unset=True)
def list_vendors(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    tax_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(Vendor).where(Vendor.tenant_id == tenant_id),
        filters={Vendor.tax_id: tax_id, Vendor.status: status_filter},
        keyword=keyword,
        keyword_columns=(Vendor.name,),
        order_by=(Vendor.created_at.desc(), Vendor.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=VendorRead,
    )


@router.post(
    "/vendors",
    response_model=VendorEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_vendor(
    payload: CreateVendorRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    ensure_code_available(db, Vendor, actor.tenant_id, "vendor_code", payload.vendor_code)
    vendor = Vendor(
        tenant_id=actor.tenant_id,
        vendor_code=payload.vendor_code,
        name=payload.name,
        tax_id=payload.tax_id,
        contact=payload.contact,
        email=payload.email,
        phone=payload.phone,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(vendor)
    commit_or_code_conflict(db, vendor)
    db.refresh(vendor)
    return envelope(VendorRead.model_validate(vendor).model_dump(by_alias=True))


@router.get("/vendors/{vendor_id}", response_model=VendorEnvelope, response_model_exclude_unset=True)
def get_vendor(
    vendor_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    vendor = get_scoped_or_404(db, Vendor, tenant_id, vendor_id)
    return envelope(VendorRead.model_validate(vendor).model_dump(by_alias=True))


@router.patch("/vendors/{vendor_id}", response_model=VendorEnvelope, response_model_exclude_unset=True)
def update_vendor(
    vendor_id: str,
    payload: UpdateVendorRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    vendor = get_scoped_or_404(db, Vendor, actor.tenant_id, vendor_id)
    updates = payload.model_dump(exclude_unset=True)
    if "vendor_code" in updates:
        ensure_code_available(
            db, Vendor, actor.tenant_id, "vendor_code", updates["vendor_code"], exclude_id=vendor.id
        )
    if "metadata" in updates:
        vendor.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(vendor, field, value)
    commit_or_code_conflict(db, vendor)
    db.refresh(vendor)
    return envelope(VendorRead.model_validate(vendor).model_dump(by_alias=True))


@router.delete("/vendors/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vendor(
    vendor_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, Vendor, vendor_id)


@router.get("/customers", response_model=CustomerListEnvelope, response_model_exclude_unset=True)
def list_customers(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    tax_id: str | None = None,
    phone: str | None = None,
    customer_kind: str | None = None,
    customer_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(Customer).where(Customer.tenant_id == tenant_id),
        filters={
            Customer.tax_id: tax_id,
            # the retail identity key, as tax_id is the B2B one — "这个手机号
            # 是不是老客户" is the question a counter agent actually asks
            Customer.phone: phone,
            Customer.customer_kind: customer_kind,
            Customer.customer_type: customer_type,
            Customer.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(Customer.name,),
        order_by=(Customer.created_at.desc(), Customer.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=CustomerRead,
    )


@router.post(
    "/customers",
    response_model=CustomerEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    payload: CreateCustomerRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    ensure_code_available(db, Customer, actor.tenant_id, "customer_code", payload.customer_code)
    if payload.customer_type is not None:
        require_type_option(db, actor.tenant_id, "customer_type", payload.customer_type)
    customer = Customer(
        tenant_id=actor.tenant_id,
        customer_code=payload.customer_code,
        name=payload.name,
        customer_kind=payload.customer_kind,
        customer_type=payload.customer_type,
        tax_id=payload.tax_id,
        contact=payload.contact,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(customer)
    commit_or_code_conflict(db, customer)
    db.refresh(customer)
    return envelope(CustomerRead.model_validate(customer).model_dump(by_alias=True))


@router.get("/customers/{customer_id}", response_model=CustomerEnvelope, response_model_exclude_unset=True)
def get_customer(
    customer_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    customer = get_scoped_or_404(db, Customer, tenant_id, customer_id)
    return envelope(CustomerRead.model_validate(customer).model_dump(by_alias=True))


@router.patch("/customers/{customer_id}", response_model=CustomerEnvelope, response_model_exclude_unset=True)
def update_customer(
    customer_id: str,
    payload: UpdateCustomerRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    customer = get_scoped_or_404(db, Customer, actor.tenant_id, customer_id)
    updates = payload.model_dump(exclude_unset=True)
    if "customer_code" in updates:
        ensure_code_available(
            db, Customer, actor.tenant_id, "customer_code", updates["customer_code"],
            exclude_id=customer.id,
        )
    if updates.get("customer_type") is not None:
        require_type_option(db, actor.tenant_id, "customer_type", updates["customer_type"])
    if "metadata" in updates:
        customer.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(customer, field, value)
    commit_or_code_conflict(db, customer)
    db.refresh(customer)
    return envelope(CustomerRead.model_validate(customer).model_dump(by_alias=True))


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, Customer, customer_id)


@router.get("/products", response_model=ProductListEnvelope, response_model_exclude_unset=True)
def list_products(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(Product).where(Product.tenant_id == tenant_id),
        filters={Product.status: status_filter},
        keyword=keyword,
        # agents paste full codes ("E2E-20260801-001") into keyword — a
        # search that finds the product by name but not by its own code reads
        # as "the import failed" (observed in a live E2E run)
        keyword_columns=(Product.name, Product.product_code),
        order_by=(Product.created_at.desc(), Product.id.desc()),
        pagination=page_only_pagination(page, size),
        render=lambda products: product_reads_with_sku_stats(db, tenant_id, products),
    )


@router.post(
    "/products",
    response_model=ProductEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    payload: CreateProductRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    ensure_code_available(db, Product, actor.tenant_id, "product_code", payload.product_code)
    product = Product(
        tenant_id=actor.tenant_id,
        product_code=payload.product_code,
        name=payload.name,
        spec=payload.spec,
        unit=payload.unit,
        list_price=payload.list_price,
        currency=payload.currency,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(product)
    commit_or_code_conflict(db, product)
    db.refresh(product)
    return envelope(ProductRead.model_validate(product).model_dump(by_alias=True))


def _run_bulk_upsert(
    *,
    db: Session,
    actor: Actor,
    family: str,
    payload,
) -> dict:
    """Shared tail for the three bulk endpoints: capability gate, upsert, one
    audit entry for the whole import, and a single commit-or-rollback.

    The audit records the import as ONE event with its counts, not one entry
    per row: 500 near-identical rows would bury the trail that makes it useful,
    and the interesting fact is "someone replaced the price list on Tuesday"."""
    require_master_data_manage(actor)
    result = bulk_upsert(
        db,
        tenant_id=actor.tenant_id,
        family=family,
        rows=payload.rows,
        dry_run=payload.dry_run,
        on_error=payload.on_error,
    )
    return _finish_bulk_import(
        db, actor, result,
        action="master_data.imported",
        detail={"family": family, "on_error": payload.on_error},
    )


def _finish_bulk_import(db: Session, actor: Actor, result: dict, *, action: str, detail: dict) -> dict:
    """Rollback-or-audit-and-commit tail shared by every bulk import. The
    audit records the import as ONE event with its counts, not one entry per
    row — 500 near-identical rows would bury the trail. An import spans many
    rows, so there is no single entity to anchor to (and `entity_id` is a
    uuid column): it anchors to the tenant whose data changed.
    """
    if not result["applied"]:
        db.rollback()
        return envelope(result)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action=action,
        entity_type="tenant",
        entity_id=actor.tenant_id,
        actor=actor.label,
        detail={**detail, **result["summary"]},
    )
    db.commit()
    return envelope(result)


def _run_document_import(*, db: Session, actor: Actor, family: str, payload) -> dict:
    """Shared tail for the historical-document imports. Gated on the family's
    own submit capability — importing history is still writing that family's
    documents — and audited as ONE event with its counts, like master data."""
    spec = document_import.FAMILIES[family]
    if family == "purchase_order":
        # Purchase orders are a FUNCTION, not "my documents" — the same single
        # capability that files one PO files a thousand historical ones, and
        # the own-employee limit never applied to this family to begin with.
        require_permission(actor, "purchase_order.manage")
        machine = get_builtin_machine(db, actor.tenant_id, "purchase_order")
    elif family == "invoice":
        # Invoicing is a function too, but scopable: a 期初 file usually carries
        # both directions, so the import needs the capability for both rather
        # than one side of it.
        for direction in ("sales", "purchase"):
            if any(row.direction == direction for row in payload.rows):
                require_permission(actor, "invoice.manage", direction)
        machine = get_builtin_machine(db, actor.tenant_id, "invoice")
    elif family == "payment":
        require_permission(actor, "payment.record")
        machine = get_builtin_machine(db, actor.tenant_id, "payment")
    else:
        require_permission(actor, "quotation.submit_own" if family == "quotation" else "order.submit_own")
        # A migration writes documents belonging to MANY salespeople, which the
        # single-document endpoints forbid via enforce_member_employee. Rather
        # than checking row by row — every historical document names someone
        # else — the endpoint requires the capability that lifts the own-employee
        # limit outright, so a plain member key cannot backfill history under a
        # colleague's name.
        if actor.kind == "user" and not has_permission(actor, "tenant.act_for_any_employee"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "importing historical documents writes records for other employees — "
                    "requires capability tenant.act_for_any_employee"
                ),
            )
        machine = (
            get_builtin_machine(db, actor.tenant_id, "sales_quotation")
            if family == "quotation"
            else get_builtin_machine(db, actor.tenant_id, "sales_order")
        )
    result = document_import.bulk_import_documents(
        db,
        tenant_id=actor.tenant_id,
        family=family,
        rows=payload.rows,
        machine_states=set(machine.get("states", ())),
        dry_run=payload.dry_run,
        on_error=payload.on_error,
        on_missing_reference=payload.on_missing_reference,
    )
    return _finish_bulk_import(
        db, actor, result,
        action=f"{spec['label']}.imported",
        detail={"on_error": payload.on_error, "on_missing_reference": payload.on_missing_reference},
    )


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


@router.post(
    "/invoices/bulk",
    response_model=BulkDocumentImportEnvelope,
    response_model_exclude_unset=True,
)
def bulk_import_invoices(
    payload: BulkInvoiceImportRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Import 期初应收应付 keyed on each invoice's own `invoice_no`.

    Settlement is deliberately not part of a row: how much of an invoice was
    already collected is a payment fact, and importing it as a column would
    make the running total disagree with the ledger it is supposed to be a sum
    of. Open balances arrive as invoices; the money that already moved arrives
    as payments and their applications."""
    return _run_document_import(db=db, actor=actor, family="invoice", payload=payload)


@router.post(
    "/payments/bulk",
    response_model=BulkDocumentImportEnvelope,
    response_model_exclude_unset=True,
)
def bulk_import_payments(
    payload: BulkPaymentImportRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Import historical收付款 keyed on each payment's own `payment_no`.

    Imported payments arrive fully unapplied — which invoice each one settled
    is recorded through `POST /payments/{id}/apply`, so the over-application,
    direction and currency guards run on every match. A bulk path into the
    ledger would be a bulk path around the only checks that make it trustworthy.
    """
    return _run_document_import(db=db, actor=actor, family="payment", payload=payload)


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


@router.post(
    "/products/bulk",
    response_model=BulkUpsertEnvelope,
    response_model_exclude_unset=True,
)
def bulk_upsert_products(
    payload: BulkProductUpsertRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Upsert products keyed on `product_code` — the spreadsheet-import path."""
    return _run_bulk_upsert(db=db, actor=actor, family="product", payload=payload)


@router.post(
    "/vendors/bulk",
    response_model=BulkUpsertEnvelope,
    response_model_exclude_unset=True,
)
def bulk_upsert_vendors(
    payload: BulkVendorUpsertRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Upsert vendors keyed on `vendor_code`."""
    return _run_bulk_upsert(db=db, actor=actor, family="vendor", payload=payload)


@router.post(
    "/customers/bulk",
    response_model=BulkUpsertEnvelope,
    response_model_exclude_unset=True,
)
def bulk_upsert_customers(
    payload: BulkCustomerUpsertRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Upsert customers keyed on `customer_code`."""
    return _run_bulk_upsert(db=db, actor=actor, family="customer", payload=payload)


@router.get("/products/{product_id}", response_model=ProductEnvelope, response_model_exclude_unset=True)
def get_product(
    product_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    product = get_scoped_or_404(db, Product, tenant_id, product_id)
    return envelope(product_read_with_skus_flag(db, product))


@router.post(
    "/products/{product_id}/skus/batch",
    response_model=BatchCreateProductSkusEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def batch_create_product_skus(
    product_id: str,
    payload: BatchCreateProductSkusRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Create a stable, de-duplicated run of one-dimensional SKUs.

    Existing rows in any lifecycle state reserve their complete, non-empty
    variant-attribute combination, so retrying a batch is idempotent without
    conflating a one-dimensional SKU with a richer multi-dimensional variant.
    """
    require_master_data_manage(actor)
    product = get_locked_product_or_404(db, actor.tenant_id, product_id)
    if product.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot create SKU for an archived product",
        )

    existing_identities = {
        json_value_identity(attrs)
        for attrs in existing_product_sku_variant_attrs(db, actor.tenant_id, product_id)
    }

    created: list[ProductSku] = []
    skipped: list[str] = []
    for value in payload.values:
        variant_attrs = {payload.dimension: value}
        variant_identity = json_value_identity(variant_attrs)
        if variant_identity in existing_identities:
            skipped.append(value)
            continue

        generated_code = f"{product.product_code}-{value}" if product.product_code else None
        # sku_code is optional. For unusually long source values, retaining the
        # complete variant attribute is preferable to truncating into a code
        # that could collide with another generated SKU.
        if generated_code is not None and len(generated_code) > 64:
            generated_code = None
        sku = ProductSku(
            tenant_id=actor.tenant_id,
            product_id=product_id,
            sku_code=generated_code,
            variant_attrs=variant_attrs,
            list_price=payload.list_price,
            status="active",
            metadata_jsonb={},
        )
        db.add(sku)
        created.append(sku)
        existing_identities.add(variant_identity)

    created_data: list[dict] = []
    if created:
        # One flush populates generated ids/timestamps for the response; avoid
        # issuing a refresh query per SKU after the batch commit.
        db.flush()
        created_data = [
            ProductSkuRead.model_validate(sku).model_dump(by_alias=True)
            for sku in created
        ]
        db.commit()

    return envelope(
        {
            "created": created_data,
            "skipped": skipped,
        }
    )


@router.patch("/products/{product_id}", response_model=ProductEnvelope, response_model_exclude_unset=True)
def update_product(
    product_id: str,
    payload: UpdateProductRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    product = get_scoped_or_404(db, Product, actor.tenant_id, product_id)
    updates = payload.model_dump(exclude_unset=True)
    if "product_code" in updates:
        ensure_code_available(
            db, Product, actor.tenant_id, "product_code", updates["product_code"],
            exclude_id=product.id,
        )
    if "metadata" in updates:
        product.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(product, field, value)
    commit_or_code_conflict(db, product)
    db.refresh(product)
    return envelope(product_read_with_skus_flag(db, product))


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, Product, product_id)


@router.get("/product-skus", response_model=ProductSkuListEnvelope, response_model_exclude_unset=True)
def list_product_skus(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    product_id: str | None = None,
    sku_code: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(ProductSku).where(ProductSku.tenant_id == tenant_id),
        filters={
            ProductSku.product_id: product_id,
            ProductSku.sku_code: sku_code,
            ProductSku.status: status_filter,
        },
        order_by=(ProductSku.created_at.asc(), ProductSku.sku_code.asc(), ProductSku.id.asc()),
        pagination=page_only_pagination(page, size),
        read_model=ProductSkuRead,
    )


@router.post(
    "/product-skus",
    response_model=ProductSkuEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_product_sku(
    payload: CreateProductSkuRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    product = get_locked_product_or_404(db, actor.tenant_id, payload.product_id)
    if product.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot create SKU for an archived product",
        )
    ensure_product_sku_variant_attrs_available(
        db,
        actor.tenant_id,
        payload.product_id,
        payload.variant_attrs,
    )
    sku = ProductSku(
        tenant_id=actor.tenant_id,
        product_id=payload.product_id,
        sku_code=payload.sku_code,
        variant_attrs=payload.variant_attrs,
        list_price=payload.list_price,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(sku)
    db.commit()
    db.refresh(sku)
    return envelope(ProductSkuRead.model_validate(sku).model_dump(by_alias=True))


@router.get(
    "/product-skus/{sku_id}",
    response_model=ProductSkuEnvelope,
    response_model_exclude_unset=True,
)
def get_product_sku(
    sku_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    sku = get_scoped_or_404(db, ProductSku, tenant_id, sku_id)
    return envelope(ProductSkuRead.model_validate(sku).model_dump(by_alias=True))


@router.patch(
    "/product-skus/{sku_id}",
    response_model=ProductSkuEnvelope,
    response_model_exclude_unset=True,
)
def update_product_sku(
    sku_id: str,
    payload: UpdateProductSkuRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    sku = get_scoped_or_404(db, ProductSku, actor.tenant_id, sku_id)
    updates = payload.model_dump(exclude_unset=True)
    if "variant_attrs" in updates:
        get_locked_product_or_404(db, actor.tenant_id, sku.product_id)
        candidate_attrs = updates["variant_attrs"] or {}
        ensure_product_sku_variant_attrs_available(
            db,
            actor.tenant_id,
            sku.product_id,
            candidate_attrs,
            exclude_sku_id=sku.id,
        )
        updates["variant_attrs"] = candidate_attrs
    if "metadata" in updates:
        sku.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(sku, field, value)
    db.commit()
    db.refresh(sku)
    return envelope(ProductSkuRead.model_validate(sku).model_dump(by_alias=True))


@router.delete("/product-skus/{sku_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_sku(
    sku_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, ProductSku, sku_id)


# --- type options: the tenant's vocabularies for *_type fields -------------


@router.get("/type-options", response_model=TypeOptionListEnvelope, response_model_exclude_unset=True)
def list_type_options(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    family: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
):
    if family is not None and family not in TYPE_FAMILIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown family — one of: {', '.join(sorted(TYPE_FAMILIES))}",
        )
    return list_rows(
        db, select(TypeOption).where(TypeOption.tenant_id == tenant_id),
        filters={TypeOption.family: family, TypeOption.status: status_filter},
        order_by=(TypeOption.family.asc(), TypeOption.created_at.asc(), TypeOption.id.asc()),
        pagination=None,
        read_model=TypeOptionRead,
    )


@router.post(
    "/type-options",
    status_code=status.HTTP_201_CREATED,
    response_model=TypeOptionEnvelope,
    response_model_exclude_unset=True,
)
def create_type_option(
    payload: CreateTypeOptionRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Tenant-defined vocabulary entry (经销价、开票服务费…). The first
    customization materializes the shipped catalog as system rows, so the
    vocabulary the tenant now owns is complete and editable."""
    require_permission(actor, "object_types.manage")
    tenant_id = actor.tenant_id
    if payload.family not in TYPE_FAMILIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown family — one of: {', '.join(sorted(TYPE_FAMILIES))}",
        )
    if payload.name in system_type_names(payload.family):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name collides with a system value")
    provision_system_type_options(db, tenant_id)
    existing = db.scalar(
        select(TypeOption).where(
            TypeOption.tenant_id == tenant_id,
            TypeOption.family == payload.family,
            TypeOption.name == payload.name,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="type option already exists")
    row = TypeOption(
        tenant_id=tenant_id,
        family=payload.family,
        name=payload.name,
        kind="custom",
        title=payload.title,
        description=payload.description,
        created_by=attributed(actor, None),
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        tenant_id=tenant_id,
        action="type_option.created",
        entity_type="type_option",
        entity_id=row.id,
        actor=actor.label,
        detail={"family": row.family, "name": row.name, "title": row.title},
    )
    db.commit()
    db.refresh(row)
    return envelope(TypeOptionRead.model_validate(row).model_dump(by_alias=True))


@router.patch(
    "/type-options/{type_option_id}",
    response_model=TypeOptionEnvelope,
    response_model_exclude_unset=True,
)
def update_type_option(
    type_option_id: str,
    payload: UpdateTypeOptionRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "object_types.manage")
    row = get_scoped_or_404(db, TypeOption, actor.tenant_id, type_option_id)
    updates = payload.model_dump(exclude_unset=True)
    if row.kind == "system" and ("title" in updates or "description" in updates):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a system value's wording follows the catalog; only its status is the tenant's",
        )
    # Recorded BEFORE the writes, and only what actually moves: a business
    # vocabulary silently changing its meaning is exactly the thing nobody can
    # reconstruct later. "渠道价" being redefined is a different price in every
    # report that reads it, and until now the row's `updated_at` was the only
    # trace — no actor, no old value, no reason.
    changed = {
        field: {"from": getattr(row, field), "to": value}
        for field, value in updates.items()
        if getattr(row, field) != value
    }
    for field, value in updates.items():
        setattr(row, field, value)
    if changed:
        record_audit(
            db,
            tenant_id=actor.tenant_id,
            action="type_option.updated",
            entity_type="type_option",
            entity_id=row.id,
            actor=actor.label,
            detail={"family": row.family, "name": row.name, "changed": changed},
        )
    db.commit()
    db.refresh(row)
    return envelope(TypeOptionRead.model_validate(row).model_dump(by_alias=True))


@router.delete("/type-options/{type_option_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_type_option(
    type_option_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Archive, never delete: existing records keep whatever value they
    already carry; archiving only removes it from what NEW records may use."""
    return archive_row(
        db,
        actor,
        TypeOption,
        type_option_id,
        permission="object_types.manage",
        audit_action="type_option.archived",
        audit_entity_type="type_option",
        audit_detail=lambda row: {"family": row.family, "name": row.name},
    )


# --- product prices: the price book beside the product's own list_price ----


def _find_active_price(
    db: Session, tenant_id: str, product_id: str, sku_id: str | None, price_type: str, currency: str
) -> ProductPrice | None:
    stmt = select(ProductPrice).where(
        ProductPrice.tenant_id == tenant_id,
        ProductPrice.product_id == product_id,
        ProductPrice.price_type == price_type,
        ProductPrice.currency == currency,
        ProductPrice.status == "active",
    )
    stmt = stmt.where(ProductPrice.sku_id == sku_id) if sku_id else stmt.where(ProductPrice.sku_id.is_(None))
    return db.scalar(stmt)


@router.get("/product-prices", response_model=ProductPriceListEnvelope, response_model_exclude_unset=True)
def list_product_prices(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    product_id: str | None = None,
    sku_id: str | None = None,
    price_type: str | None = None,
    currency: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(ProductPrice).where(ProductPrice.tenant_id == tenant_id),
        filters={
            ProductPrice.product_id: product_id,
            ProductPrice.sku_id: sku_id,
            ProductPrice.price_type: price_type,
            ProductPrice.currency: currency,
            ProductPrice.status: status_filter,
        },
        # newest first: the live price and its history read top-down
        order_by=(ProductPrice.created_at.desc(), ProductPrice.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=ProductPriceRead,
    )


@router.post(
    "/product-prices",
    response_model=ProductPriceEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_product_price(
    payload: CreateProductPriceRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    require_type_option(db, tenant_id, "product_price_type", payload.price_type)
    get_scoped_or_404(db, Product, tenant_id, payload.product_id)
    if payload.sku_id:
        sku = get_scoped_or_404(db, ProductSku, tenant_id, payload.sku_id)
        if sku.product_id != payload.product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="sku_id does not belong to product_id",
            )
    if payload.status == "active":
        existing = _find_active_price(
            db, tenant_id, payload.product_id, payload.sku_id, payload.price_type, payload.currency
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"active {payload.price_type} price {existing.id} already exists for this "
                    "(product, sku, currency) — archive it first, or PATCH it"
                ),
            )
    row = ProductPrice(
        tenant_id=tenant_id,
        product_id=payload.product_id,
        sku_id=payload.sku_id,
        price_type=payload.price_type,
        price=payload.price,
        currency=payload.currency,
        tax_in_price=payload.tax_in_price,
        tax_percentage=payload.tax_percentage,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an active price for this (product, sku, type, currency) already exists",
        )
    db.refresh(row)
    return envelope(ProductPriceRead.model_validate(row).model_dump(by_alias=True))


@router.get("/product-prices/{price_id}", response_model=ProductPriceEnvelope, response_model_exclude_unset=True)
def get_product_price(
    price_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    row = get_scoped_or_404(db, ProductPrice, tenant_id, price_id)
    return envelope(ProductPriceRead.model_validate(row).model_dump(by_alias=True))


@router.patch("/product-prices/{price_id}", response_model=ProductPriceEnvelope, response_model_exclude_unset=True)
def update_product_price(
    price_id: str,
    payload: UpdateProductPriceRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    row = get_scoped_or_404(db, ProductPrice, actor.tenant_id, price_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("status") == "active" and row.status != "active":
        clash = _find_active_price(
            db, actor.tenant_id, row.product_id, row.sku_id, row.price_type, row.currency
        )
        if clash is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"active price {clash.id} already holds this (product, sku, type, currency) slot",
            )
    if "metadata" in updates:
        row.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(row, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an active price for this (product, sku, type, currency) already exists",
        )
    db.refresh(row)
    return envelope(ProductPriceRead.model_validate(row).model_dump(by_alias=True))


@router.delete("/product-prices/{price_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_price(
    price_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, ProductPrice, price_id)


# --- supplier products: who supplies what, on which terms ------------------


@router.get("/supplier-products", response_model=SupplierProductListEnvelope, response_model_exclude_unset=True)
def list_supplier_products(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    product_id: str | None = None,
    vendor_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(SupplierProduct).where(SupplierProduct.tenant_id == tenant_id),
        filters={
            SupplierProduct.product_id: product_id,
            SupplierProduct.vendor_id: vendor_id,
            SupplierProduct.status: status_filter,
        },
        # preferred sources first; unranked trail in arrival order
        order_by=(
            SupplierProduct.preference.asc().nulls_last(),
            SupplierProduct.created_at.asc(),
            SupplierProduct.id.asc(),
        ),
        pagination=page_only_pagination(page, size),
        read_model=SupplierProductRead,
    )


@router.post(
    "/supplier-products",
    response_model=SupplierProductEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier_product(
    payload: CreateSupplierProductRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    get_scoped_or_404(db, Product, tenant_id, payload.product_id)
    get_scoped_or_404(db, Vendor, tenant_id, payload.vendor_id)
    existing = db.scalar(
        select(SupplierProduct).where(
            SupplierProduct.tenant_id == tenant_id,
            SupplierProduct.product_id == payload.product_id,
            SupplierProduct.vendor_id == payload.vendor_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"supplier link {existing.id} already exists for this (product, vendor) — "
                "PATCH it; an archived link revives by setting status active"
            ),
        )
    link = SupplierProduct(
        tenant_id=tenant_id,
        product_id=payload.product_id,
        vendor_id=payload.vendor_id,
        supplier_product_code=payload.supplier_product_code,
        supplier_product_name=payload.supplier_product_name,
        last_price=payload.last_price,
        currency=payload.currency,
        lead_time_days=payload.lead_time_days,
        min_order_quantity=payload.min_order_quantity,
        order_increment=payload.order_increment,
        preference=payload.preference,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(link)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a supplier link for this (product, vendor) already exists",
        )
    db.refresh(link)
    return envelope(SupplierProductRead.model_validate(link).model_dump(by_alias=True))


@router.get(
    "/supplier-products/{supplier_product_id}",
    response_model=SupplierProductEnvelope,
    response_model_exclude_unset=True,
)
def get_supplier_product(
    supplier_product_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    link = get_scoped_or_404(db, SupplierProduct, tenant_id, supplier_product_id)
    return envelope(SupplierProductRead.model_validate(link).model_dump(by_alias=True))


@router.patch(
    "/supplier-products/{supplier_product_id}",
    response_model=SupplierProductEnvelope,
    response_model_exclude_unset=True,
)
def update_supplier_product(
    supplier_product_id: str,
    payload: UpdateSupplierProductRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    link = get_scoped_or_404(db, SupplierProduct, actor.tenant_id, supplier_product_id)
    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        link.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(link, field, value)
    db.commit()
    db.refresh(link)
    return envelope(SupplierProductRead.model_validate(link).model_dump(by_alias=True))


@router.delete("/supplier-products/{supplier_product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier_product(
    supplier_product_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, SupplierProduct, supplier_product_id)


# --- inventory: items are running sums of an append-only detail ledger -----


@router.get("/inventory-items", response_model=InventoryItemListEnvelope, response_model_exclude_unset=True)
def list_inventory_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    product_id: str | None = None,
    sku_id: str | None = None,
    facility: str | None = None,
    lot_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    stmt = select(InventoryItem).where(InventoryItem.tenant_id == tenant_id)
    # "" is a real position ("" is the default lot, and a facility may be
    # unnamed), so these two filter on presence, not truthiness
    if facility is not None:
        stmt = stmt.where(InventoryItem.facility == facility)
    if lot_id is not None:
        stmt = stmt.where(InventoryItem.lot_id == lot_id)
    return list_rows(
        db, stmt,
        filters={
            InventoryItem.product_id: product_id,
            InventoryItem.sku_id: sku_id,
            InventoryItem.status: status_filter,
        },
        order_by=(InventoryItem.created_at.desc(), InventoryItem.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=InventoryItemRead,
    )


@router.post(
    "/inventory-items",
    response_model=InventoryItemEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_item(
    payload: CreateInventoryItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_master_data_manage(actor)
    tenant_id = actor.tenant_id
    get_scoped_or_404(db, Product, tenant_id, payload.product_id)
    if payload.sku_id:
        sku = get_scoped_or_404(db, ProductSku, tenant_id, payload.sku_id)
        if sku.product_id != payload.product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="sku_id does not belong to product_id",
            )
    facility, lot_id = payload.facility.strip(), payload.lot_id.strip()
    existing = _find_item(db, tenant_id, payload.product_id, payload.sku_id, facility, lot_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"inventory item {existing.id} already holds this "
                "(product, sku, facility, lot) position — post a detail to move its stock"
            ),
        )
    item = InventoryItem(
        tenant_id=tenant_id,
        product_id=payload.product_id,
        sku_id=payload.sku_id,
        facility=facility,
        lot_id=lot_id,
        bin_number=payload.bin_number,
        expire_date=payload.expire_date,
        received_at=payload.received_at,
        unit_cost=payload.unit_cost,
        currency=payload.currency,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an inventory item for this (product, sku, facility, lot) already exists",
        )
    # the opening balance is a ledger entry like any other movement
    if payload.initial_quantity is not None and payload.initial_quantity != 0:
        post_inventory_detail(
            db,
            item=item,
            quantity_on_hand_diff=payload.initial_quantity,
            reason=payload.initial_reason,
            description=payload.initial_description,
            unit_cost=payload.unit_cost,
            created_by=attributed(actor, None),
        )
    db.commit()
    db.refresh(item)
    return envelope(InventoryItemRead.model_validate(item).model_dump(by_alias=True))


@router.get("/inventory-items/{item_id}", response_model=InventoryItemEnvelope, response_model_exclude_unset=True)
def get_inventory_item(
    item_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    item = get_scoped_or_404(db, InventoryItem, tenant_id, item_id)
    return envelope(InventoryItemRead.model_validate(item).model_dump(by_alias=True))


@router.patch("/inventory-items/{item_id}", response_model=InventoryItemEnvelope, response_model_exclude_unset=True)
def update_inventory_item(
    item_id: str,
    payload: UpdateInventoryItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Identity, dates and cost — never quantities: the request model carries
    no quantity fields, so a client sending one gets a 422 naming it. Stock
    moves only through POST /inventory-item-details."""
    require_master_data_manage(actor)
    item = get_scoped_or_404(db, InventoryItem, actor.tenant_id, item_id)
    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        item.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(item, field, value.strip() if field in ("facility", "lot_id") else value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an inventory item for this (product, sku, facility, lot) already exists",
        )
    db.refresh(item)
    return envelope(InventoryItemRead.model_validate(item).model_dump(by_alias=True))


@router.delete("/inventory-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inventory_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, InventoryItem, item_id)


@router.get(
    "/inventory-item-details",
    response_model=InventoryItemDetailListEnvelope,
    response_model_exclude_unset=True,
)
def list_inventory_item_details(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    inventory_item_id: str | None = None,
    reason: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(InventoryItemDetail).where(InventoryItemDetail.tenant_id == tenant_id),
        filters={
            InventoryItemDetail.inventory_item_id: inventory_item_id,
            InventoryItemDetail.reason: reason,
            InventoryItemDetail.entity_type: entity_type,
            InventoryItemDetail.entity_id: entity_id,
        },
        order_by=(
            InventoryItemDetail.effective_at.desc(),
            InventoryItemDetail.created_at.desc(),
            InventoryItemDetail.id.desc(),
        ),
        pagination=page_only_pagination(page, size),
        read_model=InventoryItemDetailRead,
    )


@router.post(
    "/inventory-item-details",
    response_model=InventoryItemDetailEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_item_detail(
    payload: CreateInventoryItemDetailRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Append one movement. Details are immutable — there is no PATCH or
    DELETE; a mistake is corrected by a counter-entry. The item's totals move
    here and only here."""
    require_master_data_manage(actor)
    item = get_scoped_or_404(db, InventoryItem, actor.tenant_id, payload.inventory_item_id)
    if item.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="inventory item is archived — set it active before posting movement",
        )
    detail = post_inventory_detail(
        db,
        item=item,
        quantity_on_hand_diff=payload.quantity_on_hand_diff,
        available_to_promise_diff=payload.available_to_promise_diff,
        reason=payload.reason,
        description=payload.description,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        unit_cost=payload.unit_cost,
        effective_at=payload.effective_at,
        created_by=attributed(actor, payload.created_by),
    )
    db.commit()
    db.refresh(detail)
    return envelope(InventoryItemDetailRead.model_validate(detail).model_dump(by_alias=True))


@router.post(
    "/inventory-items/bulk",
    response_model=BulkUpsertEnvelope,
    response_model_exclude_unset=True,
)
def bulk_upsert_inventory(
    payload: BulkInventoryUpsertRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The stock-take import. Quantities land as ledger details — a counted
    number that differs from the system count becomes an `import_override`
    movement naming both numbers, never an edit of the item."""
    require_master_data_manage(actor)
    result = bulk_inventory_upsert(
        db,
        tenant_id=actor.tenant_id,
        rows=payload.rows,
        dry_run=payload.dry_run,
        on_error=payload.on_error,
        created_by=attributed(actor, None),
    )
    return _finish_bulk_import(
        db, actor, result,
        action="inventory.imported",
        detail={"on_error": payload.on_error},
    )


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


@router.get("/employees", response_model=EmployeeListEnvelope, response_model_exclude_unset=True)
def list_employees(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    keyword: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_rows(
        db, select(Employee).where(Employee.tenant_id == tenant_id),
        filters={Employee.status: status_filter},
        keyword=keyword,
        keyword_columns=(Employee.name,),
        order_by=(Employee.created_at.desc(), Employee.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=EmployeeRead,
    )


@router.post(
    "/employees",
    response_model=EmployeeEnvelope,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
def create_employee(
    payload: CreateEmployeeRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "employees.manage")
    employee = Employee(
        tenant_id=actor.tenant_id,
        employee_code=payload.employee_code,
        name=payload.name,
        email=payload.email,
        timezone=payload.timezone,
        hire_date=payload.hire_date,
        status=payload.status,
        metadata_jsonb=payload.metadata,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return envelope(EmployeeRead.model_validate(employee).model_dump(by_alias=True))


@router.get("/employees/{employee_id}", response_model=EmployeeEnvelope, response_model_exclude_unset=True)
def get_employee(
    employee_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    employee = get_scoped_or_404(db, Employee, tenant_id, employee_id)
    return envelope(EmployeeRead.model_validate(employee).model_dump(by_alias=True))


@router.patch("/employees/{employee_id}", response_model=EmployeeEnvelope, response_model_exclude_unset=True)
def update_employee(
    employee_id: str,
    payload: UpdateEmployeeRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "employees.manage")
    employee = get_scoped_or_404(db, Employee, actor.tenant_id, employee_id)
    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        employee.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(employee, field, value)
    db.commit()
    db.refresh(employee)
    return envelope(EmployeeRead.model_validate(employee).model_dump(by_alias=True))


@router.get(
    "/employees/{employee_id}/todos",
    response_model=TodoListEnvelope,
    response_model_exclude_unset=True,
)
def list_employee_todos(
    employee_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    get_scoped_or_404(db, Employee, tenant_id, employee_id)
    stmt = select(Todo).where(
        Todo.tenant_id == tenant_id,
        Todo.employee_id == employee_id,
    )
    result = list_rows(
        db, stmt,
        filters={
            Todo.status: status_filter,
            Todo.entity_type: entity_type,
            Todo.entity_id: entity_id,
        },
        keyword=keyword,
        keyword_columns=(
            Todo.title,
            Todo.description,
            Todo.todo_type,
            cast(Todo.entity_id, String),
        ),
        order_by=(Todo.created_at.desc(), Todo.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=TodoRead,
    )
    for row in result["data"]:
        row.pop("target", None)
    return result


@router.get(
    "/approval-targets",
    response_model=ApprovalTargetListEnvelope,
    response_model_exclude_unset=True,
)
def list_approval_targets(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    target_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    stmt = select(BusinessObject).where(BusinessObject.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(BusinessObject.deleted_at.is_(None))
    return list_rows(
        db, stmt,
        filters={
            BusinessObject.object_type: target_type,
            BusinessObject.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            BusinessObject.title,
            BusinessObject.summary,
            BusinessObject.source_text,
            cast(BusinessObject.id, String),
        ),
        order_by=(BusinessObject.created_at.desc(), BusinessObject.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=ApprovalTargetRead,
    )


@router.post(
    "/approval-targets",
    status_code=status.HTTP_201_CREATED,
    response_model=ApprovalTargetEnvelope,
    response_model_exclude_unset=True,
)
def create_approval_target(
    payload: CreateApprovalTargetRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "business_object.write", payload.target_type)
    validate_business_object_payload(db, actor.tenant_id, payload.target_type, payload.payload)
    validate_business_object_status(
        db, actor.tenant_id, payload.target_type, current=None, new=payload.status
    )
    approval_target = BusinessObject(
        tenant_id=actor.tenant_id,
        object_type=payload.target_type,
        title=payload.title,
        summary=payload.summary,
        payload_jsonb=payload.payload,
        source_text=payload.source_text,
        status=payload.status,
        created_by=attributed(actor, payload.created_by),
    )
    db.add(approval_target)
    db.flush()
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="business_object.created",
        entity_type="business_object",
        entity_id=approval_target.id,
        actor=actor.label,
        detail={"object_type": approval_target.object_type, "title": approval_target.title, "status": approval_target.status},
    )
    db.commit()
    db.refresh(approval_target)
    return envelope(ApprovalTargetRead.model_validate(approval_target).model_dump(by_alias=True))


@router.get(
    "/approval-targets/{approval_target_id}",
    response_model=ApprovalTargetEnvelope,
    response_model_exclude_unset=True,
)
def get_approval_target(
    approval_target_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    approval_target = get_scoped_or_404(db, BusinessObject, tenant_id, approval_target_id)
    if not include_deleted:
        ensure_business_object_not_deleted(approval_target, detail="ApprovalTarget not found")
    return envelope(ApprovalTargetRead.model_validate(approval_target).model_dump(by_alias=True))


@router.patch(
    "/approval-targets/{approval_target_id}",
    response_model=ApprovalTargetEnvelope,
    response_model_exclude_unset=True,
)
def update_approval_target(
    approval_target_id: str,
    payload: UpdateApprovalTargetRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    approval_target = get_active_approval_target_or_404(db, tenant_id, approval_target_id)
    updates = payload.model_dump(exclude_unset=True)
    final_type = updates.get("target_type", approval_target.object_type)
    require_permission(actor, "business_object.write", final_type)
    final_payload = updates.get("payload", approval_target.payload_jsonb)
    validate_business_object_payload(db, tenant_id, final_type, final_payload)
    if "status" in updates and updates["status"] != approval_target.status:
        require_permission(actor, "business_object.advance", final_type)
        validate_business_object_status(
            db, tenant_id, final_type, current=approval_target.status, new=updates["status"]
        )
        record_audit(
            db,
            tenant_id=tenant_id,
            action="business_object.status_changed",
            entity_type="business_object",
            entity_id=approval_target.id,
            actor=actor.label,
            detail={"object_type": final_type, "from": approval_target.status, "to": updates["status"]},
        )
    if "payload" in updates:
        approval_target.payload_jsonb = updates.pop("payload")
    if "target_type" in updates:
        approval_target.object_type = updates.pop("target_type")
    for field, value in updates.items():
        setattr(approval_target, field, value)
    db.commit()
    db.refresh(approval_target)
    return envelope(ApprovalTargetRead.model_validate(approval_target).model_dump(by_alias=True))


@router.delete("/approval-targets/{approval_target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_approval_target(
    approval_target_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    payload: DeleteApprovalTargetRequest | None = None,
):
    approval_target = get_scoped_or_404(db, BusinessObject, actor.tenant_id, approval_target_id)
    require_permission(actor, "business_object.write", approval_target.object_type)
    if approval_target.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    approval_target.deleted_at = datetime.now(timezone.utc)
    approval_target.deleted_by = attributed(actor, payload.deleted_by if payload else None)
    approval_target.delete_reason = payload.delete_reason if payload else None
    cancel_todos_for(
        db, actor, "approval_target", approval_target.id,
        reason="approval target deleted",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/approval-targets/{approval_target_id}/restore",
    response_model=ApprovalTargetEnvelope,
    response_model_exclude_unset=True,
)
def restore_approval_target(
    approval_target_id: str,
    payload: RestoreApprovalTargetRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    approval_target = get_scoped_or_404(
        db, BusinessObject, actor.tenant_id, approval_target_id
    )
    require_permission(actor, "business_object.write", approval_target.object_type)
    if approval_target.deleted_at is None:
        return envelope(ApprovalTargetRead.model_validate(approval_target).model_dump(by_alias=True))
    approval_target.deleted_at = None
    approval_target.deleted_by = None
    approval_target.delete_reason = None
    db.commit()
    db.refresh(approval_target)
    return envelope(ApprovalTargetRead.model_validate(approval_target).model_dump(by_alias=True))


@router.get(
    "/object-type-definitions",
    response_model=ObjectTypeDefinitionListEnvelope,
    response_model_exclude_unset=True,
)
def list_object_type_definitions(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    object_type: str | None = None,
    entity_kind: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    return list_rows(
        db, select(ObjectTypeDefinition).where(ObjectTypeDefinition.tenant_id == tenant_id),
        filters={
            ObjectTypeDefinition.object_type: object_type,
            ObjectTypeDefinition.entity_kind: entity_kind,
            ObjectTypeDefinition.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            ObjectTypeDefinition.object_type,
            ObjectTypeDefinition.title,
            ObjectTypeDefinition.description,
        ),
        order_by=(ObjectTypeDefinition.object_type.asc(), ObjectTypeDefinition.id.asc()),
        pagination=requested_pagination(page, size),
        read_model=ObjectTypeDefinitionRead, by_alias=False,
    )


@router.get("/builtin-object-types", response_model=BuiltinObjectTypeEnvelope)
def get_builtin_object_types(
    actor: Annotated[Actor, Depends(get_actor)],
):
    """What ORYH already ships, so an agent can tell whether a custom object is
    one of these under another name.

    Asked to "建一个 Product 自定义对象", an agent would define one, and the
    workspace would end up with two answers to "有多少产品" — the real catalogue
    and a shadow of it that no order line, price or inventory row can ever point
    at. Once the shadow has data the two cannot be merged back.

    This endpoint states the fact and stops there. Whether a company's "product"
    is our product is a reading of THEIR business, and the agent is the one with
    the person in front of it — it can ask, and the server cannot. So there is no
    409 here and none on the create paths: read this first, and if it matches,
    say so rather than defining a second one.

    Ungated, like the skill catalogue and for the same reason: it is a trigger
    index, and it reveals nothing about this workspace's data.
    """
    return envelope(list(builtin_object_vocabulary()))


@router.get(
    "/object-directory",
    response_model=ObjectDirectoryEnvelope,
    response_model_exclude_unset=True,
)
def get_object_directory(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Discover every object collection available in the tenant console.

    Custom types are the union of definitions and actual data, so schema-less
    types created before the definition catalog was introduced remain visible.
    Counts include soft-deleted records because the object console can browse
    them with ``include_deleted=true``.
    """
    tenant_id = actor.tenant_id
    # "how many payslips did this company issue" is itself worth hiding
    payroll_gate = visible_payroll_filter(actor)
    invoice_count_stmt = select(func.count()).select_from(Invoice).where(
        Invoice.tenant_id == tenant_id
    )
    if payroll_gate is not None:
        invoice_count_stmt = invoice_count_stmt.where(payroll_gate)
    builtin_counts = {
        "timesheet_header": db.scalar(
            select(func.count()).select_from(TimesheetHeader).where(
                TimesheetHeader.tenant_id == tenant_id
            )
        )
        or 0,
        "employee_leave": db.scalar(
            select(func.count()).select_from(EmployeeLeave).where(
                EmployeeLeave.tenant_id == tenant_id
            )
        )
        or 0,
        "expense_claim": db.scalar(
            select(func.count()).select_from(ExpenseClaim).where(
                ExpenseClaim.tenant_id == tenant_id
            )
        )
        or 0,
        "purchase_request": db.scalar(
            select(func.count()).select_from(PurchaseRequest).where(
                PurchaseRequest.tenant_id == tenant_id
            )
        )
        or 0,
        "sales_quotation": db.scalar(
            select(func.count()).select_from(SalesQuotation).where(
                SalesQuotation.tenant_id == tenant_id
            )
        )
        or 0,
        "sales_order": db.scalar(
            select(func.count()).select_from(SalesOrder).where(
                SalesOrder.tenant_id == tenant_id
            )
        )
        or 0,
        "purchase_order": db.scalar(
            select(func.count()).select_from(PurchaseOrder).where(
                PurchaseOrder.tenant_id == tenant_id
            )
        )
        or 0,
        "invoice": db.scalar(invoice_count_stmt) or 0,
        "payment": db.scalar(
            select(func.count()).select_from(Payment).where(Payment.tenant_id == tenant_id)
        )
        or 0,
        "billing_account": db.scalar(
            select(func.count()).select_from(BillingAccount).where(
                BillingAccount.tenant_id == tenant_id
            )
        )
        or 0,
        "resource_booking": db.scalar(
            select(func.count()).select_from(ResourceBooking).where(
                ResourceBooking.tenant_id == tenant_id
            )
        )
        or 0,
    }
    custom_counts = dict(
        db.execute(
            select(BusinessObject.object_type, func.count())
            .where(BusinessObject.tenant_id == tenant_id)
            .group_by(BusinessObject.object_type)
        ).all()
    )
    definitions = db.scalars(
        select(ObjectTypeDefinition).where(ObjectTypeDefinition.tenant_id == tenant_id)
    ).all()
    definition_by_key = {
        (definition.entity_kind, definition.object_type): definition
        for definition in definitions
    }
    defined_custom_types = {
        definition.object_type
        for definition in definitions
        if definition.entity_kind == "business_object"
    }
    entries = [
        ObjectDirectoryEntryRead(
            entity_kind="builtin",
            object_type=object_type,
            count=builtin_counts[object_type],
            title=(
                definition_by_key[("builtin", object_type)].title
                if ("builtin", object_type) in definition_by_key
                else None
            ),
            definition_status=(
                definition_by_key[("builtin", object_type)].status
                if ("builtin", object_type) in definition_by_key
                else None
            ),
        )
        for object_type in BUILTIN_OBJECT_TYPES
    ]
    entries.extend(
        ObjectDirectoryEntryRead(
            entity_kind="business_object",
            object_type=object_type,
            count=custom_counts.get(object_type, 0),
            title=(
                definition_by_key[("business_object", object_type)].title
                if ("business_object", object_type) in definition_by_key
                else None
            ),
            definition_status=(
                definition_by_key[("business_object", object_type)].status
                if ("business_object", object_type) in definition_by_key
                else None
            ),
        )
        for object_type in sorted(defined_custom_types | set(custom_counts))
    )
    return envelope([entry.model_dump() for entry in entries], len(entries))


@router.post(
    "/object-type-definitions",
    status_code=status.HTTP_201_CREATED,
    response_model=ObjectTypeDefinitionEnvelope,
    response_model_exclude_unset=True,
)
def create_object_type_definition(
    payload: CreateObjectTypeDefinitionRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "object_types.manage")
    ensure_valid_json_schema(payload.json_schema)
    if payload.state_machine is not None:
        ensure_valid_state_machine(
            payload.state_machine, entity_kind=payload.entity_kind, object_type=payload.object_type
        )
    elif payload.entity_kind == "builtin":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="builtin entity definitions must include a state_machine",
        )
    existing = db.scalar(
        select(ObjectTypeDefinition).where(
            ObjectTypeDefinition.tenant_id == actor.tenant_id,
            ObjectTypeDefinition.entity_kind == payload.entity_kind,
            ObjectTypeDefinition.object_type == payload.object_type,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a definition for this object_type already exists; update it instead",
        )
    definition = ObjectTypeDefinition(
        tenant_id=actor.tenant_id,
        entity_kind=payload.entity_kind,
        object_type=payload.object_type,
        title=payload.title,
        description=payload.description,
        json_schema=payload.json_schema,
        state_machine=payload.state_machine,
        created_by=attributed(actor, payload.created_by),
    )
    db.add(definition)
    db.commit()
    db.refresh(definition)
    return envelope(ObjectTypeDefinitionRead.model_validate(definition).model_dump())


@router.get(
    "/object-type-definitions/{definition_id}",
    response_model=ObjectTypeDefinitionEnvelope,
    response_model_exclude_unset=True,
)
def get_object_type_definition(
    definition_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    # Agents hold natural names ("warranty_card"), not definition ids — four
    # of a live E2E audit's six 500s were exactly this call with an object_type in the
    # id slot. The ref resolves either way, like roles do.
    try:
        uuid.UUID(str(definition_id))
    except ValueError:
        definition = db.scalar(
            select(ObjectTypeDefinition).where(
                ObjectTypeDefinition.tenant_id == tenant_id,
                ObjectTypeDefinition.object_type == definition_id,
            )
        )
        if definition is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="ObjectTypeDefinition not found"
            )
    else:
        definition = get_scoped_or_404(db, ObjectTypeDefinition, tenant_id, definition_id)
    return envelope(ObjectTypeDefinitionRead.model_validate(definition).model_dump())


@router.patch(
    "/object-type-definitions/{definition_id}",
    response_model=ObjectTypeDefinitionEnvelope,
    response_model_exclude_unset=True,
)
def update_object_type_definition(
    definition_id: str,
    payload: UpdateObjectTypeDefinitionRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "object_types.manage")
    definition = get_scoped_or_404(db, ObjectTypeDefinition, actor.tenant_id, definition_id)
    updates = payload.model_dump(exclude_unset=True)
    version_bumped = False
    if "json_schema" in updates:
        ensure_valid_json_schema(updates["json_schema"])
        if updates["json_schema"] != definition.json_schema:
            definition.version += 1
            version_bumped = True
        definition.json_schema = updates.pop("json_schema")
    if "state_machine" in updates:
        machine = updates.pop("state_machine")
        if machine is None and definition.entity_kind == "builtin":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="builtin entity definitions must keep a state_machine",
            )
        if machine is not None:
            ensure_valid_state_machine(
                machine, entity_kind=definition.entity_kind, object_type=definition.object_type
            )
        if machine != definition.state_machine and not version_bumped:
            definition.version += 1
        definition.state_machine = machine
    for field, value in updates.items():
        setattr(definition, field, value)
    db.commit()
    db.refresh(definition)
    return envelope(ObjectTypeDefinitionRead.model_validate(definition).model_dump())


@router.delete("/object-type-definitions/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_object_type_definition(
    definition_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return archive_row(db, actor, ObjectTypeDefinition, definition_id, permission="object_types.manage")


def require_audit_scope(
    caller: Actor, *, entity_type: str | None, entity_id: str | None, actor: str | None
) -> None:
    """Who may sweep the whole trail, and who must name what they are asking about.

    The log carries every actor's activity, including `skill_bundle.*` rows and
    the `key_id` in their detail. Ungated, a plain member could read the lot —
    while `GET /auth/users` correctly refused them the directory of the very
    people whose actions they were reading.

    Holders of `users.manage` (and service actors, which act for the company)
    keep the full sweep; it is their troubleshooting tool. Everyone else must
    scope the query, to one of:

    - their own activity (`actor=user:<self>`)
    - their own account (`entity_type=user&entity_id=<self>`)
    - one named record of any other type

    That last clause is deliberate. "What happened to this record" is the
    console's object-detail trail and the documented use in
    `$oryh-business-object`; it is the record's history, not another person's,
    and it is no wider than the read access they already have to the record.

    Refused rather than silently narrowed: a quietly filtered log reads as
    "nothing happened", which is the failure this codebase just spent a fix
    removing from status filters.
    """
    if has_permission(caller, "users.manage"):
        return
    if actor is not None and actor != caller.label:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="you may only filter this log by your own actor",
        )
    own_account = entity_type == "user" and entity_id == caller.user_id
    if entity_type == "user" and not own_account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="you may only read your own user's audit trail",
        )
    scoped = (
        actor == caller.label
        or own_account
        or (entity_id is not None and entity_type != "user")
    )
    if not scoped:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "reading the whole audit trail requires users.manage; "
                "otherwise name what you are asking about — entity_id=<record>, "
                f"entity_type=user&entity_id=<you>, or actor={caller.label}"
            ),
        )


@router.get("/audit-logs")
def list_audit_logs(
    caller: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor: str | None = None,
    before: int | None = None,
    limit: int = 100,
):
    """Read-only audit trail, newest first. For troubleshooting and
    accountability — agent coordination uses todos and state queries, not
    this endpoint. Page backwards with `before=<smallest id seen>`.

    `users.manage` reads the whole trail; everyone else names what they are
    asking about — see `require_audit_scope`."""
    require_audit_scope(caller, entity_type=entity_type, entity_id=entity_id, actor=actor)
    tenant_id = caller.tenant_id
    limit = max(1, min(limit, 500))
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    if before is not None:
        stmt = stmt.where(AuditLog.id < before)
    entries = db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit)).all()
    data = [AuditLogRead.model_validate(item).model_dump(by_alias=True) for item in entries]
    return envelope(data, len(data))


def parse_payload_match(payload_match: str | None) -> dict:
    if not payload_match:
        return {}
    try:
        parsed = json.loads(payload_match)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="payload_match must be a JSON object"
        ) from exc
    if not isinstance(parsed, dict) or not all(
        isinstance(value, (str, int, float, bool)) for value in parsed.values()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload_match must be a flat JSON object of scalar values",
        )
    return parsed


@router.get(
    "/business-objects",
    response_model=BusinessObjectListEnvelope,
    response_model_exclude_unset=True,
)
def list_business_objects(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    object_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    payload_match: str | None = None,
    without_open_todo: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    validate_business_object_status_filter(db, tenant_id, object_type, status_filter)
    stmt = select(BusinessObject).where(BusinessObject.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(BusinessObject.deleted_at.is_(None))
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, BusinessObject, tenant_id, "business_object")
    for key, value in parse_payload_match(payload_match).items():
        element = BusinessObject.payload_jsonb[key]
        if isinstance(value, bool):
            stmt = stmt.where(element.as_boolean() == value)
        elif isinstance(value, int):
            stmt = stmt.where(element.as_integer() == value)
        elif isinstance(value, float):
            stmt = stmt.where(element.as_float() == value)
        else:
            stmt = stmt.where(element.as_string() == value)
    return list_rows(
        db, stmt,
        filters={
            BusinessObject.object_type: object_type,
            BusinessObject.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            BusinessObject.title,
            BusinessObject.summary,
            BusinessObject.source_text,
            BusinessObject.object_type,
            cast(BusinessObject.id, String),
        ),
        order_by=(BusinessObject.created_at.desc(), BusinessObject.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=BusinessObjectRead,
    )


@router.post(
    "/business-objects",
    status_code=status.HTTP_201_CREATED,
    response_model=BusinessObjectEnvelope,
    response_model_exclude_unset=True,
)
def create_business_object(
    payload: CreateBusinessObjectRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "business_object.write", payload.object_type)
    validate_business_object_payload(db, actor.tenant_id, payload.object_type, payload.payload)
    validate_business_object_status(
        db, actor.tenant_id, payload.object_type, current=None, new=payload.status
    )
    business_object = BusinessObject(
        tenant_id=actor.tenant_id,
        object_type=payload.object_type,
        title=payload.title,
        summary=payload.summary,
        payload_jsonb=payload.payload,
        source_text=payload.source_text,
        status=payload.status,
        created_by=attributed(actor, payload.created_by),
    )
    db.add(business_object)
    db.flush()
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="business_object.created",
        entity_type="business_object",
        entity_id=business_object.id,
        actor=actor.label,
        detail={"object_type": business_object.object_type, "title": business_object.title, "status": business_object.status},
    )
    db.commit()
    db.refresh(business_object)
    return envelope(BusinessObjectRead.model_validate(business_object).model_dump(by_alias=True))


@router.get(
    "/business-objects/{business_object_id}",
    response_model=BusinessObjectEnvelope,
    response_model_exclude_unset=True,
)
def get_business_object(
    business_object_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    business_object = get_scoped_or_404(db, BusinessObject, tenant_id, business_object_id)
    if not include_deleted:
        ensure_business_object_not_deleted(business_object)
    return envelope(BusinessObjectRead.model_validate(business_object).model_dump(by_alias=True))


@router.get(
    "/business-objects/{business_object_id}/detail",
    response_model=BusinessObjectDetailEnvelope,
    response_model_exclude_unset=True,
)
def get_business_object_detail(
    business_object_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    """Return the related records needed to render an object detail view.

    Approval/todo rows created through the legacy ``approval_target`` alias are
    included alongside canonical ``business_object`` rows so the activity
    timeline remains complete during migration.
    """
    business_object = get_scoped_or_404(db, BusinessObject, tenant_id, business_object_id)
    if not include_deleted:
        ensure_business_object_not_deleted(business_object)

    links = db.scalars(
        select(BusinessObjectLink)
        .where(
            BusinessObjectLink.tenant_id == tenant_id,
            or_(
                BusinessObjectLink.source_object_id == business_object_id,
                BusinessObjectLink.target_object_id == business_object_id,
            ),
        )
        .order_by(BusinessObjectLink.created_at.desc(), BusinessObjectLink.id.desc())
    ).all()
    approval_records = db.scalars(
        select(ApprovalRecord)
        .where(
            ApprovalRecord.tenant_id == tenant_id,
            ApprovalRecord.entity_type.in_(("business_object", "approval_target")),
            ApprovalRecord.entity_id == business_object_id,
        )
        .order_by(
            ApprovalRecord.round_no.asc(),
            ApprovalRecord.sequence_no.asc(),
            ApprovalRecord.acted_at.asc(),
            ApprovalRecord.id.asc(),
        )
    ).all()
    todos = db.scalars(
        select(Todo)
        .where(
            Todo.tenant_id == tenant_id,
            Todo.entity_type.in_(("business_object", "approval_target")),
            Todo.entity_id == business_object_id,
        )
        .order_by(Todo.created_at.desc(), Todo.id.desc())
    ).all()
    audit_logs = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.entity_type.in_(("business_object", "approval_target")),
            AuditLog.entity_id == business_object_id,
        )
        .order_by(AuditLog.id.desc())
        .limit(200)
    ).all()
    object_type_definition = db.scalar(
        select(ObjectTypeDefinition)
        .where(
            ObjectTypeDefinition.tenant_id == tenant_id,
            ObjectTypeDefinition.entity_kind == "business_object",
            ObjectTypeDefinition.object_type == business_object.object_type,
        )
        .order_by(ObjectTypeDefinition.version.desc(), ObjectTypeDefinition.created_at.desc())
        .limit(1)
    )
    workflow_definitions = db.scalars(
        select(WorkflowDefinition)
        .where(
            WorkflowDefinition.tenant_id == tenant_id,
            WorkflowDefinition.entity_kind == "business_object",
            WorkflowDefinition.object_type == business_object.object_type,
        )
        .order_by(
            WorkflowDefinition.name.asc(),
            WorkflowDefinition.version.desc(),
            WorkflowDefinition.id.desc(),
        )
    ).all()
    detail = BusinessObjectDetailRead(
        business_object=BusinessObjectRead.model_validate(business_object),
        links=[BusinessObjectLinkRead.model_validate(item) for item in links],
        approval_records=[ApprovalRecordRead.model_validate(item) for item in approval_records],
        todos=[TodoRead.model_validate(item) for item in todos],
        audit_logs=[AuditLogRead.model_validate(item) for item in audit_logs],
        object_type_definition=(
            ObjectTypeDefinitionRead.model_validate(object_type_definition)
            if object_type_definition is not None
            else None
        ),
        workflow_definitions=[
            WorkflowDefinitionRead.model_validate(item) for item in workflow_definitions
        ],
    )
    return envelope(detail.model_dump(by_alias=True))


@router.patch(
    "/business-objects/{business_object_id}",
    response_model=BusinessObjectEnvelope,
    response_model_exclude_unset=True,
)
def update_business_object(
    business_object_id: str,
    payload: UpdateBusinessObjectRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    business_object = get_active_business_object_or_404(db, tenant_id, business_object_id)
    updates = payload.model_dump(exclude_unset=True)
    final_type = updates.get("object_type", business_object.object_type)
    require_permission(actor, "business_object.write", final_type)
    # custom-type subscriptions advance through this PATCH, not
    # apply_status_change — same wall, same pre-write match
    require_hosted_write_scope(actor, business_object.object_type, business_object)
    final_payload = updates.get("payload", business_object.payload_jsonb)
    validate_business_object_payload(db, tenant_id, final_type, final_payload)
    old_status = business_object.status
    if "status" in updates and updates["status"] != old_status:
        require_permission(actor, "business_object.advance", final_type)
        validate_business_object_status(
            db, tenant_id, final_type, current=old_status, new=updates["status"]
        )
        record_audit(
            db,
            tenant_id=tenant_id,
            action="business_object.status_changed",
            entity_type="business_object",
            entity_id=business_object.id,
            actor=actor.label,
            detail={
                "object_type": final_type,
                "title": updates.get("title", business_object.title),
                "from": old_status,
                "to": updates["status"],
            },
        )
    if "payload" in updates:
        business_object.payload_jsonb = updates.pop("payload")
    for field, value in updates.items():
        setattr(business_object, field, value)
    db.commit()
    db.refresh(business_object)
    return envelope(BusinessObjectRead.model_validate(business_object).model_dump(by_alias=True))


@router.delete("/business-objects/{business_object_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business_object(
    business_object_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    payload: DeleteBusinessObjectRequest | None = None,
):
    business_object = get_scoped_or_404(db, BusinessObject, actor.tenant_id, business_object_id)
    require_permission(actor, "business_object.write", business_object.object_type)
    if business_object.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    business_object.deleted_at = datetime.now(timezone.utc)
    business_object.deleted_by = attributed(actor, payload.deleted_by if payload else None)
    business_object.delete_reason = payload.delete_reason if payload else None
    # todos on a custom object name it by the generic type, not by its
    # object_type — see TODO_ENTITY_TYPES
    cancel_todos_for(
        db, actor, "business_object", business_object.id,
        reason="business object deleted",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/business-objects/{business_object_id}/restore",
    response_model=BusinessObjectEnvelope,
    response_model_exclude_unset=True,
)
def restore_business_object(
    business_object_id: str,
    payload: RestoreBusinessObjectRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    business_object = get_scoped_or_404(
        db, BusinessObject, actor.tenant_id, business_object_id
    )
    require_permission(actor, "business_object.write", business_object.object_type)
    if business_object.deleted_at is None:
        return envelope(BusinessObjectRead.model_validate(business_object).model_dump(by_alias=True))
    business_object.deleted_at = None
    business_object.deleted_by = None
    business_object.delete_reason = None
    db.commit()
    db.refresh(business_object)
    return envelope(BusinessObjectRead.model_validate(business_object).model_dump(by_alias=True))


@router.get(
    "/business-object-links",
    response_model=BusinessObjectLinkListEnvelope,
    response_model_exclude_unset=True,
)
def list_business_object_links(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    source_object_id: str | None = None,
    target_object_id: str | None = None,
    link_type: str | None = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    return list_rows(
        db, select(BusinessObjectLink).where(BusinessObjectLink.tenant_id == tenant_id),
        filters={
            BusinessObjectLink.source_object_id: source_object_id,
            BusinessObjectLink.target_object_id: target_object_id,
            BusinessObjectLink.link_type: link_type,
        },
        keyword=keyword,
        keyword_columns=(
            BusinessObjectLink.link_type,
            cast(BusinessObjectLink.source_object_id, String),
            cast(BusinessObjectLink.target_object_id, String),
        ),
        order_by=(BusinessObjectLink.created_at.desc(), BusinessObjectLink.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=BusinessObjectLinkRead,
    )


@router.post(
    "/business-object-links",
    status_code=status.HTTP_201_CREATED,
    response_model=BusinessObjectLinkEnvelope,
    response_model_exclude_unset=True,
)
def create_business_object_link(
    payload: CreateBusinessObjectLinkRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    source_object = get_active_business_object_or_404(
        db, actor.tenant_id, payload.source_object_id
    )
    target_object = get_active_business_object_or_404(
        db, actor.tenant_id, payload.target_object_id
    )
    require_permission(actor, "business_object.write", source_object.object_type)
    require_permission(actor, "business_object.write", target_object.object_type)
    if source_object.id == target_object.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source and target objects must differ")
    existing = db.scalar(
        select(BusinessObjectLink).where(
            BusinessObjectLink.tenant_id == actor.tenant_id,
            BusinessObjectLink.source_object_id == source_object.id,
            BusinessObjectLink.target_object_id == target_object.id,
            BusinessObjectLink.link_type == payload.link_type,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="business object link already exists")
    link = BusinessObjectLink(
        tenant_id=actor.tenant_id,
        source_object_id=source_object.id,
        target_object_id=target_object.id,
        link_type=payload.link_type,
        metadata_jsonb=payload.metadata,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return envelope(BusinessObjectLinkRead.model_validate(link).model_dump(by_alias=True))


@router.get(
    "/business-object-links/{link_id}",
    response_model=BusinessObjectLinkEnvelope,
    response_model_exclude_unset=True,
)
def get_business_object_link(
    link_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    link = get_scoped_or_404(db, BusinessObjectLink, tenant_id, link_id)
    return envelope(BusinessObjectLinkRead.model_validate(link).model_dump(by_alias=True))


@router.delete("/business-object-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business_object_link(
    link_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    link = get_scoped_or_404(db, BusinessObjectLink, actor.tenant_id, link_id)
    source_object = get_scoped_or_404(
        db, BusinessObject, actor.tenant_id, link.source_object_id
    )
    target_object = get_scoped_or_404(
        db, BusinessObject, actor.tenant_id, link.target_object_id
    )
    require_permission(actor, "business_object.write", source_object.object_type)
    require_permission(actor, "business_object.write", target_object.object_type)
    db.delete(link)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/employee-leaves",
    response_model=EmployeeLeaveListEnvelope,
    response_model_exclude_unset=True,
)
def list_employee_leaves(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    leave_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    overlapping_from: date | None = None,
    overlapping_thru: date | None = None,
    include_deleted: bool = False,
    without_open_todo: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    """The rows an agent computes a balance FROM.

    `overlapping_from`/`overlapping_thru` is the filter that makes the
    computation one call: leave that overlaps the period at all, which is what
    "how much annual leave has this person used this year" needs — a request
    straddling New Year belongs to both years in part, and the caller decides
    how to split it by the tenant's rule. Filtering on `from_date` alone would
    silently drop it from one side.
    """
    validate_status_filter(db, tenant_id, "employee_leave", status_filter)
    stmt = select(EmployeeLeave).where(EmployeeLeave.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(EmployeeLeave.deleted_at.is_(None))
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, EmployeeLeave, tenant_id, "employee_leave")
    if overlapping_from is not None:
        stmt = stmt.where(EmployeeLeave.thru_date >= overlapping_from)
    if overlapping_thru is not None:
        stmt = stmt.where(EmployeeLeave.from_date <= overlapping_thru)
    return list_rows(
        db, stmt,
        filters={
            EmployeeLeave.employee_id: employee_id,
            EmployeeLeave.leave_type: leave_type,
            EmployeeLeave.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(EmployeeLeave.id, String),
            cast(EmployeeLeave.employee_id, String),
            EmployeeLeave.leave_type,
            EmployeeLeave.reason,
            EmployeeLeave.status,
            EmployeeLeave.source_report_text,
        ),
        order_by=(
            EmployeeLeave.from_date.desc(),
            EmployeeLeave.created_at.desc(),
            EmployeeLeave.id.desc(),
        ),
        pagination=requested_pagination(page, size),
        read_model=EmployeeLeaveRead,
    )


@router.post("/employee-leaves", status_code=status.HTTP_201_CREATED)
def create_employee_leave(
    payload: CreateEmployeeLeaveRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """File one absence.

    Deliberately absent: any check that the person has the days. Entitlement is
    computed from the tenant's policy, not stored, so the server has nothing to
    check against and inventing one would be the server deciding a rule that
    belongs in a document somebody can revise. Over-requesting is a legal
    record; the approver — informed by the agent's computation — decides.
    """
    tenant_id = actor.tenant_id
    require_permission(actor, "leave.submit_own")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    enforce_member_employee(actor, payload.employee_id)
    require_type_option(db, tenant_id, "leave_type", payload.leave_type)
    require_machine_state(db, tenant_id, EmployeeLeave, payload.status)
    if payload.thru_date < payload.from_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="thru_date cannot precede from_date",
        )
    leave = EmployeeLeave(
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        leave_type=payload.leave_type,
        from_date=payload.from_date,
        thru_date=payload.thru_date,
        duration_days=payload.duration_days,
        reason=payload.reason,
        status=payload.status,
        source_report_text=payload.source_report_text,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)
    return envelope(EmployeeLeaveRead.model_validate(leave).model_dump(by_alias=True))


@router.get(
    "/employee-leaves/{leave_id}",
    response_model=EmployeeLeaveEnvelope,
    response_model_exclude_unset=True,
)
def get_employee_leave(
    leave_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    leave = get_scoped_or_404(db, EmployeeLeave, tenant_id, leave_id)
    return envelope(EmployeeLeaveRead.model_validate(leave).model_dump(by_alias=True))


@router.patch(
    "/employee-leaves/{leave_id}",
    response_model=EmployeeLeaveEnvelope,
    response_model_exclude_unset=True,
)
def update_employee_leave(
    leave_id: str,
    payload: UpdateEmployeeLeaveRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    leave = get_active_document_or_404(db, EmployeeLeave, tenant_id, leave_id)
    enforce_member_employee(actor, leave.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    ensure_content_edit_allowed(actor, "leave", updates)
    if updates.get("leave_type"):
        require_type_option(db, tenant_id, "leave_type", updates["leave_type"])
    from_date = updates.get("from_date", leave.from_date)
    thru_date = updates.get("thru_date", leave.thru_date)
    if thru_date < from_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="thru_date cannot precede from_date",
        )
    if "status" in updates and updates["status"] != leave.status:
        apply_status_change(db, actor, leave, updates["status"])
    if "custom_fields" in updates:
        leave.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(leave, field, value)
    db.commit()
    db.refresh(leave)
    return envelope(EmployeeLeaveRead.model_validate(leave).model_dump(by_alias=True))


@router.delete("/employee-leaves/{leave_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee_leave(
    leave_id: str,
    payload: DeleteEmployeeLeaveRequest | None = None,
    actor: Annotated[Actor, Depends(get_actor)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    return delete_document(db, actor, EmployeeLeave, leave_id, payload)


@router.post("/employee-leaves/{leave_id}/restore")
def restore_employee_leave(
    leave_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, EmployeeLeave, leave_id)


@router.post("/employee-leaves/{leave_id}/submit")
def submit_employee_leave(
    leave_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return submit_document(db, actor, EmployeeLeave, leave_id)


@router.get(
    "/timesheet-headers",
    response_model=TimesheetHeaderListEnvelope,
    response_model_exclude_unset=True,
)
def list_timesheet_headers(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    without_open_todo: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    validate_status_filter(db, tenant_id, "timesheet_header", status_filter)
    stmt = select(TimesheetHeader).where(TimesheetHeader.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(TimesheetHeader.deleted_at.is_(None))
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, TimesheetHeader, tenant_id, "timesheet_header")
    return list_rows(
        db, stmt,
        filters={
            TimesheetHeader.employee_id: employee_id,
            TimesheetHeader.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(TimesheetHeader.id, String),
            cast(TimesheetHeader.employee_id, String),
            cast(TimesheetHeader.period_start, String),
            cast(TimesheetHeader.period_end, String),
            TimesheetHeader.status,
            TimesheetHeader.source_report_text,
        ),
        order_by=(
            TimesheetHeader.period_start.desc(),
            TimesheetHeader.created_at.desc(),
            TimesheetHeader.id.desc(),
        ),
        pagination=requested_pagination(page, size),
        read_model=TimesheetHeaderRead,
    )


@router.post("/timesheet-headers", status_code=status.HTTP_201_CREATED)
def create_timesheet_header(
    payload: CreateTimesheetHeaderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "timesheet.submit_own")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    enforce_member_employee(actor, payload.employee_id)
    require_machine_state(db, tenant_id, TimesheetHeader, payload.status)
    header = TimesheetHeader(
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        status=payload.status,
        source_report_text=payload.source_report_text,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(header)
    try:
        db.flush()
        # inline rows ride the same transaction: one bad row rolls back the
        # whole document, so a crash or a validation error can no longer
        # leave a half-filled draft behind
        entries = [
            build_timesheet_entry(db, actor, row, header=header) for row in payload.entries
        ]
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(TimesheetHeader).where(
                TimesheetHeader.tenant_id == tenant_id,
                TimesheetHeader.employee_id == payload.employee_id,
                TimesheetHeader.period_start == payload.period_start,
                TimesheetHeader.period_end == payload.period_end,
            )
        )
        if existing is None:
            raise
        period = f"{existing.period_start.isoformat()}..{existing.period_end.isoformat()}"
        if existing.deleted_at is not None:
            # the unique index intentionally covers soft-deleted rows: a deleted
            # header keeps its period slot so /restore can never collide
            detail = (
                f"deleted timesheet header {existing.id} still holds period {period} "
                f"for employee {payload.employee_id}; restore it instead of recreating"
            )
        else:
            detail = (
                f"timesheet header {existing.id} already covers period {period} "
                f"for employee {payload.employee_id}"
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    db.refresh(header)
    data = TimesheetHeaderRead.model_validate(header).model_dump(by_alias=True)
    if entries:
        # the response IS the read-back: what landed, row by row
        data["entries"] = [
            TimesheetEntryRead.model_validate(entry).model_dump(by_alias=True)
            for entry in entries
        ]
    return envelope(data)


@router.get("/timesheet-headers/{header_id}")
def get_timesheet_header(
    header_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    header = get_scoped_or_404(db, TimesheetHeader, tenant_id, header_id)
    if not include_deleted:
        ensure_document_not_deleted(header)
    return envelope(TimesheetHeaderRead.model_validate(header).model_dump(by_alias=True))


@router.patch("/timesheet-headers/{header_id}")
def update_timesheet_header(
    header_id: str,
    payload: UpdateTimesheetHeaderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    header = get_active_document_or_404(db, TimesheetHeader, tenant_id, header_id)
    # members only touch their own headers; approvers never patch status —
    # flow advancement is the workflow admin's write (service/admin credential)
    enforce_member_employee(actor, header.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    ensure_content_edit_allowed(actor, "timesheet", updates)
    if "status" in updates and updates["status"] != header.status:
        # flow advancement is the workflow admin's write: members submit via
        # POST .../submit — never a raw status patch (no self-approval)
        apply_status_change(db, actor, header, updates["status"])
    if "custom_fields" in updates:
        header.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(header, field, value)
    db.commit()
    db.refresh(header)
    return envelope(TimesheetHeaderRead.model_validate(header).model_dump(by_alias=True))


@router.delete("/timesheet-headers/{header_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_timesheet_header(
    header_id: str,
    payload: DeleteTimesheetHeaderRequest | None = None,
    actor: Annotated[Actor, Depends(get_actor)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    return delete_document(db, actor, TimesheetHeader, header_id, payload)


@router.post("/timesheet-headers/{header_id}/restore")
def restore_timesheet_header(
    header_id: str,
    payload: RestoreTimesheetHeaderRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, TimesheetHeader, header_id)


@router.post("/timesheet-headers/{header_id}/submit")
def submit_timesheet_header(
    header_id: str,
    payload: SubmitTimesheetRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return submit_document(db, actor, TimesheetHeader, header_id)


@router.get("/timesheet-headers/{header_id}/detail")
def get_timesheet_detail(
    header_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    header = get_scoped_or_404(db, TimesheetHeader, tenant_id, header_id)
    if not include_deleted:
        ensure_document_not_deleted(header)
    entries = db.scalars(
        select(TimesheetEntry)
        .where(
            TimesheetEntry.tenant_id == tenant_id,
            TimesheetEntry.header_id == header_id,
            TimesheetEntry.deleted_at.is_(None),
        )
        .order_by(TimesheetEntry.work_date.asc(), TimesheetEntry.created_at.asc())
    ).all()
    approvals = document_approvals(db, tenant_id, "timesheet_header", header_id)
    detail = TimesheetDetailRead(
        header=TimesheetHeaderRead.model_validate(header),
        entries=[TimesheetEntryRead.model_validate(entry) for entry in entries],
        approval_records=[ApprovalRecordRead.model_validate(record) for record in approvals],
    )
    return envelope(detail.model_dump(by_alias=True))


@router.get("/timesheet-entries")
def list_timesheet_entries(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    header_id: str | None = None,
    employee_id: str | None = None,
    project_id: str | None = None,
    work_date_from: date | None = None,
    work_date_to: date | None = None,
):
    stmt = (
        select(TimesheetEntry)
        .join(TimesheetHeader, TimesheetEntry.header_id == TimesheetHeader.id)
        .where(
            TimesheetEntry.tenant_id == tenant_id,
            TimesheetEntry.deleted_at.is_(None),
            TimesheetHeader.deleted_at.is_(None),
        )
    )
    if work_date_from:
        stmt = stmt.where(TimesheetEntry.work_date >= work_date_from)
    if work_date_to:
        stmt = stmt.where(TimesheetEntry.work_date <= work_date_to)
    return list_rows(
        db, stmt,
        filters={
            TimesheetEntry.header_id: header_id,
            TimesheetEntry.employee_id: employee_id,
            TimesheetEntry.project_id: project_id,
        },
        order_by=(TimesheetEntry.work_date.desc(),),
        pagination=None,
        read_model=TimesheetEntryRead,
    )


def build_timesheet_entry(
    db: Session, actor: Actor, payload, *, header: TimesheetHeader | None = None
) -> TimesheetEntry:
    """One validated entry, standalone or inline. The single set of rules for
    both paths — the inline path exists to save turns, not to skip checks.

    `header` passed = the row rides the header's own create: parent identity
    comes from the header, and the editable-state gate does not apply — the
    person is stating the document as a whole, including record-won documents
    created directly in a later state."""
    tenant_id = actor.tenant_id
    require_type_option(db, tenant_id, "work_type", payload.work_type)
    if header is None:
        if not payload.header_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="header_id is required")
        header = get_active_document_or_404(db, TimesheetHeader, tenant_id, payload.header_id)
        ensure_document_editable(db, header)
    elif payload.header_id and payload.header_id != header.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="inline entries belong to the header being created; do not name another header_id",
        )
    enforce_member_employee(actor, header.employee_id)
    employee_id = payload.employee_id or header.employee_id
    get_scoped_or_404(db, Employee, tenant_id, employee_id)
    if payload.work_date is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="work_date is required")
    validate_header_entry_link(header, employee_id, payload.work_date)
    project_id, project_name_snapshot = normalize_project_context(
        db,
        tenant_id,
        payload.project_id,
        payload.project_name_snapshot,
    )
    entry = TimesheetEntry(
        tenant_id=tenant_id,
        header_id=header.id,
        employee_id=employee_id,
        work_date=payload.work_date,
        project_id=project_id,
        project_name_snapshot=project_name_snapshot,
        client=payload.client,
        task=payload.task,
        hours=payload.hours,
        work_type=payload.work_type,
        notes=payload.notes,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(entry)
    return entry


@router.post("/timesheet-entries", status_code=status.HTTP_201_CREATED)
def create_timesheet_entry(
    payload: CreateTimesheetEntryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "timesheet.submit_own")
    entry = build_timesheet_entry(db, actor, payload)
    db.commit()
    db.refresh(entry)
    return envelope(TimesheetEntryRead.model_validate(entry).model_dump(by_alias=True))


@router.get("/timesheet-entries/{entry_id}")
def get_timesheet_entry(
    entry_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    entry = get_scoped_or_404(db, TimesheetEntry, tenant_id, entry_id)
    if entry.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TimesheetEntry not found")
    ensure_document_not_deleted(get_scoped_or_404(db, TimesheetHeader, tenant_id, entry.header_id))
    return envelope(TimesheetEntryRead.model_validate(entry).model_dump(by_alias=True))


@router.patch("/timesheet-entries/{entry_id}")
def update_timesheet_entry(
    entry_id: str,
    payload: UpdateTimesheetEntryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "timesheet.submit_own")
    entry = get_scoped_or_404(db, TimesheetEntry, tenant_id, entry_id)
    if entry.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TimesheetEntry not found")
    header = get_active_document_or_404(db, TimesheetHeader, tenant_id, entry.header_id)
    ensure_document_editable(db, header)
    enforce_member_employee(actor, header.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    if "work_type" in updates:
        require_type_option(db, tenant_id, "work_type", updates["work_type"])
    if "project_id" in updates or "project_name_snapshot" in updates:
        project_id, project_name_snapshot = normalize_project_context(
            db,
            tenant_id,
            updates.get("project_id", entry.project_id),
            updates.get("project_name_snapshot", entry.project_name_snapshot),
        )
        entry.project_id = project_id
        entry.project_name_snapshot = project_name_snapshot
        updates.pop("project_id", None)
        updates.pop("project_name_snapshot", None)
    if "hours" in updates:
        entry.hours = updates.pop("hours")
    if "custom_fields" in updates:
        entry.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return envelope(TimesheetEntryRead.model_validate(entry).model_dump(by_alias=True))


@router.delete("/timesheet-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_timesheet_entry(
    entry_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "timesheet.submit_own")
    entry = get_scoped_or_404(db, TimesheetEntry, tenant_id, entry_id)
    if entry.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    header = get_active_document_or_404(db, TimesheetHeader, tenant_id, entry.header_id)
    ensure_document_editable(db, header)
    enforce_member_employee(actor, header.employee_id)
    entry.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/expense-claims",
    response_model=ExpenseClaimListEnvelope,
    response_model_exclude_unset=True,
)
def list_expense_claims(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_deleted: bool = False,
    without_open_todo: bool = False,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    validate_status_filter(db, tenant_id, "expense_claim", status_filter)
    stmt = select(ExpenseClaim).where(ExpenseClaim.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(ExpenseClaim.deleted_at.is_(None))
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, ExpenseClaim, tenant_id, "expense_claim")
    return list_rows(
        db, stmt,
        filters={
            ExpenseClaim.employee_id: employee_id,
            ExpenseClaim.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            cast(ExpenseClaim.id, String),
            cast(ExpenseClaim.employee_id, String),
            ExpenseClaim.title,
            cast(ExpenseClaim.claim_date, String),
            ExpenseClaim.currency,
            ExpenseClaim.status,
            ExpenseClaim.source_report_text,
        ),
        order_by=(ExpenseClaim.created_at.desc(), ExpenseClaim.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=ExpenseClaimRead,
    )


@router.post("/expense-claims", status_code=status.HTTP_201_CREATED)
def create_expense_claim(
    payload: CreateExpenseClaimRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "expense.submit_own")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    enforce_member_employee(actor, payload.employee_id)
    require_machine_state(db, tenant_id, ExpenseClaim, payload.status)
    claim = ExpenseClaim(
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        title=payload.title,
        claim_date=payload.claim_date,
        currency=payload.currency,
        status=payload.status,
        source_report_text=payload.source_report_text,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(claim)
    db.flush()
    items = [build_expense_item(db, actor, row, claim=claim) for row in payload.items]
    db.commit()
    db.refresh(claim)
    data = ExpenseClaimRead.model_validate(claim).model_dump(by_alias=True)
    if items:
        data["items"] = [
            ExpenseItemRead.model_validate(item).model_dump(by_alias=True) for item in items
        ]
    return envelope(data)


@router.get("/expense-claims/{claim_id}")
def get_expense_claim(
    claim_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    claim = get_scoped_or_404(db, ExpenseClaim, tenant_id, claim_id)
    if not include_deleted:
        ensure_document_not_deleted(claim)
    return envelope(ExpenseClaimRead.model_validate(claim).model_dump(by_alias=True))


@router.patch("/expense-claims/{claim_id}")
def update_expense_claim(
    claim_id: str,
    payload: UpdateExpenseClaimRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    claim = get_active_document_or_404(db, ExpenseClaim, tenant_id, claim_id)
    # members only touch their own claims; approvers never patch status —
    # flow advancement is the workflow admin's write (service/admin credential)
    enforce_member_employee(actor, claim.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    ensure_content_edit_allowed(actor, "expense", updates)
    if "status" in updates and updates["status"] != claim.status:
        # flow advancement is the workflow admin's write: members submit via
        # POST .../submit — never a raw status patch (no self-approval)
        apply_status_change(db, actor, claim, updates["status"])
    if "custom_fields" in updates:
        claim.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(claim, field, value)
    db.commit()
    db.refresh(claim)
    return envelope(ExpenseClaimRead.model_validate(claim).model_dump(by_alias=True))


@router.delete("/expense-claims/{claim_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense_claim(
    claim_id: str,
    payload: DeleteExpenseClaimRequest | None = None,
    actor: Annotated[Actor, Depends(get_actor)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """A claim that has been paid out cannot be hidden: the payment applied to
    it would keep pointing at a document nobody can see."""
    claim = get_scoped_or_404(db, ExpenseClaim, actor.tenant_id, claim_id)
    if claim.deleted_at is None:
        ensure_nothing_applied(db, claim, label="expense claim")
    return delete_document(db, actor, ExpenseClaim, claim_id, payload)


@router.post("/expense-claims/{claim_id}/restore")
def restore_expense_claim(
    claim_id: str,
    payload: RestoreExpenseClaimRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, ExpenseClaim, claim_id)


@router.post("/expense-claims/{claim_id}/submit")
def submit_expense_claim(
    claim_id: str,
    payload: SubmitExpenseClaimRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return submit_document(db, actor, ExpenseClaim, claim_id)


@router.get(
    "/expense-claims/{claim_id}/detail",
    response_model=ExpenseClaimDetailEnvelope,
    response_model_exclude_unset=True,
)
def get_expense_claim_detail(
    claim_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    claim = get_scoped_or_404(db, ExpenseClaim, tenant_id, claim_id)
    if not include_deleted:
        ensure_document_not_deleted(claim)
    items = db.scalars(
        select(ExpenseItem)
        .where(
            ExpenseItem.tenant_id == tenant_id,
            ExpenseItem.claim_id == claim_id,
            ExpenseItem.deleted_at.is_(None),
        )
        .order_by(ExpenseItem.expense_date.asc(), ExpenseItem.created_at.asc())
    ).all()
    approvals = document_approvals(db, tenant_id, "expense_claim", claim_id)
    attachments = attachments_for_items(db, tenant_id, items)
    vendor_ids = {item.vendor_id for item in items if item.vendor_id}
    vendors = (
        db.scalars(
            select(Vendor).where(
                Vendor.tenant_id == tenant_id,
                Vendor.id.in_(vendor_ids),
            )
        ).all()
        if vendor_ids
        else []
    )
    vendor_names = {vendor.id: vendor.name for vendor in vendors}
    detail_items = [
        ExpenseItemDetailRead(
            **ExpenseItemRead.model_validate(item).model_dump(),
            vendor_name=vendor_names.get(item.vendor_id) if item.vendor_id else None,
        )
        for item in items
    ]
    detail = ExpenseClaimDetailRead(
        claim=ExpenseClaimRead.model_validate(claim),
        items=detail_items,
        approval_records=[ApprovalRecordRead.model_validate(record) for record in approvals],
        attachments=[AttachmentRead.model_validate(attachment) for attachment in attachments],
        total_amount=float(sum(item.amount for item in items)),
        total_tax_amount=float(sum(item.tax_amount or 0 for item in items)),
    )
    return envelope(detail.model_dump(by_alias=True))


@router.get("/expense-items")
def list_expense_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    claim_id: str | None = None,
    employee_id: str | None = None,
    project_id: str | None = None,
    vendor_id: str | None = None,
    invoice_number: str | None = None,
    expense_date_from: date | None = None,
    expense_date_to: date | None = None,
):
    stmt = (
        select(ExpenseItem)
        .join(ExpenseClaim, ExpenseItem.claim_id == ExpenseClaim.id)
        .where(
            ExpenseItem.tenant_id == tenant_id,
            ExpenseItem.deleted_at.is_(None),
            ExpenseClaim.deleted_at.is_(None),
        )
    )
    if expense_date_from:
        stmt = stmt.where(ExpenseItem.expense_date >= expense_date_from)
    if expense_date_to:
        stmt = stmt.where(ExpenseItem.expense_date <= expense_date_to)
    return list_rows(
        db, stmt,
        filters={
            ExpenseItem.claim_id: claim_id,
            ExpenseItem.employee_id: employee_id,
            ExpenseItem.project_id: project_id,
            ExpenseItem.vendor_id: vendor_id,
            ExpenseItem.invoice_number: invoice_number,
        },
        order_by=(ExpenseItem.expense_date.desc(),),
        pagination=None,
        read_model=ExpenseItemRead,
    )


def build_expense_item(
    db: Session, actor: Actor, payload, *, claim: ExpenseClaim | None = None
) -> ExpenseItem:
    """One validated item, standalone or inline — see build_timesheet_entry."""
    tenant_id = actor.tenant_id
    require_type_option(db, tenant_id, "expense_category", payload.category)
    if claim is None:
        if not payload.claim_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="claim_id is required")
        claim = get_active_document_or_404(db, ExpenseClaim, tenant_id, payload.claim_id)
        ensure_document_editable(db, claim)
    elif payload.claim_id and payload.claim_id != claim.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="inline items belong to the claim being created; do not name another claim_id",
        )
    enforce_member_employee(actor, claim.employee_id)
    employee_id = payload.employee_id or claim.employee_id
    get_scoped_or_404(db, Employee, tenant_id, employee_id)
    if claim.employee_id != employee_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="employee_id must match the claim")
    if payload.expense_date is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="expense_date is required")
    if payload.amount is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="amount is required")
    ensure_invoice_not_duplicated(db, tenant_id, payload.invoice_number)
    if payload.attachment_id:
        get_scoped_or_404(db, Attachment, tenant_id, payload.attachment_id)
    project_id, project_name_snapshot = normalize_project_context(
        db,
        tenant_id,
        payload.project_id,
        payload.project_name_snapshot,
    )
    vendor_id, merchant = normalize_vendor_context(db, tenant_id, payload.vendor_id, payload.merchant)
    item = ExpenseItem(
        tenant_id=tenant_id,
        claim_id=claim.id,
        employee_id=employee_id,
        expense_date=payload.expense_date,
        category=payload.category,
        amount=payload.amount,
        tax_amount=payload.tax_amount,
        vendor_id=vendor_id,
        merchant=merchant,
        invoice_number=payload.invoice_number,
        invoice_type=payload.invoice_type,
        project_id=project_id,
        project_name_snapshot=project_name_snapshot,
        client=payload.client,
        attachment_id=payload.attachment_id,
        extracted_fields_jsonb=payload.extracted_fields,
        notes=payload.notes,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(item)
    return item


@router.post("/expense-items", status_code=status.HTTP_201_CREATED)
def create_expense_item(
    payload: CreateExpenseItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "expense.submit_own")
    item = build_expense_item(db, actor, payload)
    db.commit()
    db.refresh(item)
    return envelope(ExpenseItemRead.model_validate(item).model_dump(by_alias=True))


@router.get("/expense-items/{item_id}")
def get_expense_item(
    item_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    item = get_scoped_or_404(db, ExpenseItem, tenant_id, item_id)
    if item.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExpenseItem not found")
    ensure_document_not_deleted(get_scoped_or_404(db, ExpenseClaim, tenant_id, item.claim_id))
    return envelope(ExpenseItemRead.model_validate(item).model_dump(by_alias=True))


@router.patch("/expense-items/{item_id}")
def update_expense_item(
    item_id: str,
    payload: UpdateExpenseItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "expense.submit_own")
    item = get_scoped_or_404(db, ExpenseItem, tenant_id, item_id)
    if item.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ExpenseItem not found")
    claim = get_active_document_or_404(db, ExpenseClaim, tenant_id, item.claim_id)
    ensure_document_editable(db, claim)
    enforce_member_employee(actor, claim.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    if "category" in updates:
        require_type_option(db, tenant_id, "expense_category", updates["category"])
    if "invoice_number" in updates and updates["invoice_number"] != item.invoice_number:
        ensure_invoice_not_duplicated(db, tenant_id, updates["invoice_number"], exclude_item_id=item.id)
    if "attachment_id" in updates and updates["attachment_id"]:
        get_scoped_or_404(db, Attachment, tenant_id, updates["attachment_id"])
    if "vendor_id" in updates or "merchant" in updates:
        vendor_id, merchant = normalize_vendor_context(
            db,
            tenant_id,
            updates.get("vendor_id", item.vendor_id),
            updates.get("merchant", item.merchant),
        )
        item.vendor_id = vendor_id
        item.merchant = merchant
        updates.pop("vendor_id", None)
        updates.pop("merchant", None)
    if "project_id" in updates or "project_name_snapshot" in updates:
        project_id, project_name_snapshot = normalize_project_context(
            db,
            tenant_id,
            updates.get("project_id", item.project_id),
            updates.get("project_name_snapshot", item.project_name_snapshot),
        )
        item.project_id = project_id
        item.project_name_snapshot = project_name_snapshot
        updates.pop("project_id", None)
        updates.pop("project_name_snapshot", None)
    if "extracted_fields" in updates:
        item.extracted_fields_jsonb = updates.pop("extracted_fields")
    if "custom_fields" in updates:
        item.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return envelope(ExpenseItemRead.model_validate(item).model_dump(by_alias=True))


@router.delete("/expense-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "expense.submit_own")
    item = get_scoped_or_404(db, ExpenseItem, tenant_id, item_id)
    if item.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    claim = get_active_document_or_404(db, ExpenseClaim, tenant_id, item.claim_id)
    ensure_document_editable(db, claim)
    enforce_member_employee(actor, claim.employee_id)
    item.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


@router.post("/attachments", status_code=status.HTTP_201_CREATED)
def create_attachment(
    payload: CreateAttachmentRequest,
    response: Response,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    # any capability that files attachment-backed records grants upload
    if not (has_permission(actor, "expense.submit_own") or has_permission(actor, "purchase.submit_own")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="requires capability expense.submit_own or purchase.submit_own",
        )
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="content_base64 is not valid base64",
        )
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="attachment content is empty")
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"attachment exceeds {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB",
        )
    digest = hashlib.sha256(content).hexdigest()
    existing = db.scalar(
        select(Attachment).where(Attachment.tenant_id == tenant_id, Attachment.sha256 == digest)
    )
    if existing is not None:
        # Idempotent per (tenant, sha256): the same bytes resolve to the same
        # row. **200 says reused, 201 says newly stored** — that distinction is
        # the duplicate-evidence signal, and the server is the only thing that
        # can state it honestly. Callers previously had to guess from
        # created_at, which is wrong for anything uploaded in the last few
        # minutes — exactly when a claim's receipts arrive together.
        response.status_code = status.HTTP_200_OK
        return envelope(AttachmentRead.model_validate(existing).model_dump(by_alias=True))
    attachment = Attachment(
        tenant_id=tenant_id,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=len(content),
        sha256=digest,
        content=content,
        uploaded_by=attributed(actor, None),
    )
    db.add(attachment)
    db.flush()
    record_audit(
        db,
        tenant_id=tenant_id,
        action="attachment.uploaded",
        entity_type="attachment",
        entity_id=attachment.id,
        actor=actor.label,
        detail={"filename": attachment.filename, "size_bytes": attachment.size_bytes, "sha256": digest},
    )
    db.commit()
    db.refresh(attachment)
    return envelope(AttachmentRead.model_validate(attachment).model_dump(by_alias=True))


@router.get("/attachments/{attachment_id}")
def get_attachment(
    attachment_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    attachment = get_scoped_or_404(db, Attachment, tenant_id, attachment_id)
    return envelope(AttachmentRead.model_validate(attachment).model_dump(by_alias=True))


@router.get("/attachments/{attachment_id}/content")
def get_attachment_content(
    attachment_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    attachment = get_scoped_or_404(db, Attachment, tenant_id, attachment_id)
    return Response(
        content=attachment.content,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(attachment.filename)}",
        },
    )


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


# --- purchase orders: the commitment to a vendor ---------------------------


@router.get("/purchase-orders", response_model=PurchaseOrderListEnvelope, response_model_exclude_unset=True)
def list_purchase_orders(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    vendor_id: str | None = None,
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
    if "custom_fields" in updates:
        po.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(po, field, value)
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


@dataclass(frozen=True)
class AdjustmentFamily:
    """The three adjustment families (quotation / sales order / purchase
    order) behave identically by construction — same fields, same vocabulary,
    same editable-state gate. What differs is data: the models, the two FK
    names, the capability, and whether the parent has an owner to enforce."""

    parent_model: type
    item_model: type
    parent_field: str
    item_field: str
    permission: str
    owner_checked: bool
    read_model: type


ADJUSTMENT_FAMILIES: dict[type, AdjustmentFamily] = {
    SalesQuotationAdjustment: AdjustmentFamily(
        SalesQuotation, SalesQuotationItem, "quotation_id", "quotation_item_id",
        "quotation.submit_own", True, SalesQuotationAdjustmentRead,
    ),
    SalesOrderAdjustment: AdjustmentFamily(
        SalesOrder, SalesOrderItem, "order_id", "order_item_id",
        "order.submit_own", True, SalesOrderAdjustmentRead,
    ),
    PurchaseOrderAdjustment: AdjustmentFamily(
        PurchaseOrder, PurchaseOrderItem, "po_id", "po_item_id",
        # procurement is a function, not "my documents": one capability, no owner
        "purchase_order.manage", False, PurchaseOrderAdjustmentRead,
    ),
}


def _adjustment_read(family: AdjustmentFamily, adjustment) -> dict:
    return family.read_model.model_validate(adjustment).model_dump(by_alias=True)


def _adjustment_write_gate(db: Session, actor: Actor, family: AdjustmentFamily, parent_id: str):
    parent = get_active_document_or_404(db, family.parent_model, actor.tenant_id, parent_id)
    ensure_document_editable(db, parent)
    if family.owner_checked:
        enforce_member_employee(actor, parent.employee_id)
    return parent


def list_adjustments(
    db: Session, tenant_id: str, model, *,
    parent_id: str | None, item_id: str | None, adjustment_type: str | None,
) -> dict:
    family = ADJUSTMENT_FAMILIES[model]
    stmt = select(model).where(model.tenant_id == tenant_id, model.deleted_at.is_(None))
    return list_rows(
        db, stmt,
        filters={
            getattr(model, family.parent_field): parent_id,
            getattr(model, family.item_field): item_id,
            model.adjustment_type: adjustment_type,
        },
        order_by=(model.created_at.asc(), model.id.asc()),
        pagination=None,
        render=lambda rows: [_adjustment_read(family, row) for row in rows],
    )


def create_adjustment(db: Session, actor: Actor, model, payload) -> dict:
    family = ADJUSTMENT_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    # ONE vocabulary for all three families: an adjustment type is not a
    # direction-specific idea
    require_type_option(db, tenant_id, "sales_adjustment_type", payload.adjustment_type)
    parent_id = getattr(payload, family.parent_field)
    _adjustment_write_gate(db, actor, family, parent_id)
    item_id = getattr(payload, family.item_field)
    if item_id:
        require_line_on_document(
            db, tenant_id, family.item_model, family.parent_field, family.item_field,
            parent_id, item_id,
        )
    adjustment = model(
        tenant_id=tenant_id,
        **{family.parent_field: parent_id, family.item_field: item_id},
        adjustment_type=payload.adjustment_type,
        description=payload.description,
        amount=payload.amount,
        source_percentage=payload.source_percentage,
        metadata_jsonb=payload.metadata,
    )
    db.add(adjustment)
    db.commit()
    db.refresh(adjustment)
    return envelope(_adjustment_read(family, adjustment))


def get_adjustment(db: Session, tenant_id: str, model, adjustment_id: str) -> dict:
    adjustment = get_live_or_404(db, model, tenant_id, adjustment_id)
    return envelope(_adjustment_read(ADJUSTMENT_FAMILIES[model], adjustment))


def update_adjustment(db: Session, actor: Actor, model, adjustment_id: str, payload) -> dict:
    family = ADJUSTMENT_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    adjustment = get_live_or_404(db, model, tenant_id, adjustment_id)
    parent_id = getattr(adjustment, family.parent_field)
    _adjustment_write_gate(db, actor, family, parent_id)
    updates = payload.model_dump(exclude_unset=True)
    if "adjustment_type" in updates:
        require_type_option(db, tenant_id, "sales_adjustment_type", updates["adjustment_type"])
    if updates.get(family.item_field):
        require_line_on_document(
            db, tenant_id, family.item_model, family.parent_field, family.item_field,
            parent_id, updates[family.item_field],
        )
    if "metadata" in updates:
        adjustment.metadata_jsonb = updates.pop("metadata")
    for field, value in updates.items():
        setattr(adjustment, field, value)
    db.commit()
    db.refresh(adjustment)
    return envelope(_adjustment_read(family, adjustment))


def delete_adjustment(db: Session, actor: Actor, model, adjustment_id: str) -> Response:
    family = ADJUSTMENT_FAMILIES[model]
    tenant_id = actor.tenant_id
    require_permission(actor, family.permission)
    adjustment = get_scoped_or_404(db, model, tenant_id, adjustment_id)
    if adjustment.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    _adjustment_write_gate(db, actor, family, getattr(adjustment, family.parent_field))
    adjustment.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    require_machine_state(db, tenant_id, SalesQuotation, payload.status)
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
        status=payload.status,
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
    validate_transition(machine, quotation.status, "sent", subject="sales_quotation")
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
    quotation.status = "sent"
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
    if source.status == "superseded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="quotation is already superseded; revise the live revision instead",
        )
    machine = get_builtin_machine(db, tenant_id, "sales_quotation")
    validate_transition(machine, source.status, "superseded", subject="sales_quotation")
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
        status="draft",
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
    source.status = "superseded"
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


@router.get("/sales-orders", response_model=SalesOrderListEnvelope, response_model_exclude_unset=True)
def list_sales_orders(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    customer_id: str | None = None,
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
    require_machine_state(db, tenant_id, SalesOrder, payload.status)
    quotation_id, source_quote_number = normalize_order_quotation_context(
        db, tenant_id, payload.quotation_id, payload.source_quote_number
    )
    customer_id, customer_name_snapshot = normalize_customer_context(
        db, tenant_id, payload.customer_id, payload.customer_name_snapshot
    )
    if payload.project_id:
        get_scoped_or_404(db, Project, tenant_id, payload.project_id)
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
        payment_terms=payload.payment_terms,
        delivery_terms=payload.delivery_terms,
        total_amount=payload.total_amount,
        status=payload.status,
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
    if "custom_fields" in updates:
        order.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(order, field, value)
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


# --- invoices -------------------------------------------------------------
#
# One family, both directions (OFBiz's `Invoice` shape). The direction decides
# which counterparty is required, which capability scope is checked, which
# order the lines may bill, and — in the settlement path — what a payment may
# apply to. Everything else about a bill is the same in either direction.


COUNTERPARTY_FIELD_BY_DIRECTION = {
    "sales": "customer_id",
    "purchase": "vendor_id",
    "payroll": "payee_employee_id",
}
COUNTERPARTY_MODEL_BY_DIRECTION = {
    "sales": Customer,
    "purchase": Vendor,
    "payroll": Employee,
}
# a payslip bills no order at all — hence the None
ORDER_LINK_BY_DIRECTION = {
    "sales": "sales_order_id",
    "purchase": "purchase_order_id",
    "payroll": None,
}
ORDER_MODEL_BY_DIRECTION = {"sales": SalesOrder, "purchase": PurchaseOrder}
ORDER_ITEM_LINK_BY_DIRECTION = {
    "sales": ("sales_order_item_id", SalesOrderItem, "order_id"),
    "purchase": ("purchase_order_item_id", PurchaseOrderItem, "po_id"),
}
# which vocabulary a line's type is checked against — a payslip counts salary
# and deductions, not goods and shipping. Same two-vocabulary shape a billing
# account's `unit` uses.
ITEM_TYPE_FAMILY_BY_DIRECTION = {
    "sales": "invoice_item_type",
    "purchase": "invoice_item_type",
    "payroll": "payroll_item_type",
}


def resolve_invoice_counterparty(
    db: Session, tenant_id: str, direction: str, given: dict
) -> tuple[dict, str | None]:
    """The counterparty must be the side the direction implies, and it must
    exist here. Returns ({counterparty columns}, name) — a wrong-side value is
    refused rather than silently dropped, because an invoice filed against the
    wrong party is worse than one that failed to file."""
    wanted = COUNTERPARTY_FIELD_BY_DIRECTION[direction]
    fields = set(COUNTERPARTY_FIELD_BY_DIRECTION.values())
    for other in sorted(fields - {wanted}):
        if given.get(other) is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"a {direction!r} invoice carries {wanted}, not {other}",
            )
    if given.get(wanted) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"a {direction!r} invoice needs {wanted}",
        )
    party = get_scoped_or_404(db, COUNTERPARTY_MODEL_BY_DIRECTION[direction], tenant_id, given[wanted])
    resolved = {field: None for field in fields}
    resolved[wanted] = party.id
    return resolved, party.name


def ensure_invoice_order_link(db: Session, tenant_id: str, direction: str, updates: dict) -> None:
    """An invoice bills an order on its own side of the house. Naming the other
    side's order is refused rather than ignored — that link is what the
    three-way match reads, so a wrong one is a wrong answer later. A payslip
    bills nothing, so both links are refused on it."""
    wanted = ORDER_LINK_BY_DIRECTION[direction]
    for field in ("sales_order_id", "purchase_order_id"):
        if field == wanted or updates.get(field) is None:
            continue
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"a payslip bills no order, so it carries neither sales_order_id "
                f"nor purchase_order_id"
                if wanted is None
                else f"a {direction!r} invoice bills a {wanted[:-3]}, not a {field[:-3]}"
            ),
        )
    if wanted is not None and updates.get(wanted) is not None:
        get_active_document_or_404(
            db, ORDER_MODEL_BY_DIRECTION[direction], tenant_id, updates[wanted]
        )


def ensure_payroll_shape(db: Session, tenant_id: str, payload) -> None:
    """What a payslip is, beyond being an invoice.

    The period is required because 双发工资 is the expensive mistake in this
    family and the one-per-person-per-period index needs something to key on.
    A declared total is refused because net pay IS the sum of the lines —
    stating a different number could only ever be wrong, unlike a 抹零 on a
    sales invoice."""
    if payload.period_start is None or payload.period_end is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a payslip covers a pay period: send period_start and period_end",
        )
    if payload.period_end < payload.period_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period_end cannot precede period_start",
        )
    if payload.total_amount is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "a payslip's net pay is the sum of its lines — do not declare a "
                "total_amount, state the earnings and deductions instead"
            ),
        )
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a payslip is its lines: send the earnings and deductions as items",
        )


def ensure_line_sign(db: Session, tenant_id: str, family: str, item_type: str, amount) -> None:
    """On a payslip the sign IS the meaning. 个税 recorded as +2000 rather than
    -2000 pays the person 4000 too much, and nothing downstream would notice —
    so the vocabulary declares the direction and this refuses the other one."""
    if family not in SIGNED_TYPE_FAMILIES or amount is None:
        return
    sign = type_option_sign(db, tenant_id, family, item_type)
    if sign is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{item_type!r} does not say whether it adds to pay or deducts from it — "
                "set `sign` (+1 or -1) on the type option before using it on a payslip"
            ),
        )
    if amount == 0 or (amount > 0) != (sign > 0):
        expected = "positive" if sign > 0 else "negative"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{item_type!r} is {'an earning' if sign > 0 else 'a deduction'}, so its "
                f"amount must be {expected} — got {amount}"
            ),
        )


def conflicting_invoice(
    db: Session, tenant_id: str, invoice_no: str, payload
) -> HTTPException:
    """A payslip collides two ways, and they mean opposite things.

    A duplicate `invoice_no` is a numbering clash — pick another number. A
    duplicate (person, period) is the guard against paying somebody twice, and
    it is the most expensive mistake on this path. Telling the second one that
    its NUMBER is taken is worse than saying nothing: it names a remedy that
    cannot work and hides the one that matters.

    Which fired is settled by asking the database the actual question rather
    than reading the driver's message. Postgres names the index and SQLite
    names the columns, so message-sniffing would have been right on one dialect
    and quietly wrong on the other — and it would have gone on being wrong
    until somebody read a production 409 closely.
    """
    if payload.direction == "payroll" and payload.payee_employee_id:
        existing = db.scalars(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.direction == "payroll",
                Invoice.payee_employee_id == payload.payee_employee_id,
                Invoice.period_start == payload.period_start,
                Invoice.deleted_at.is_(None),
            )
        ).first()
        if existing is not None:
            return HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"this employee already has payslip {existing.invoice_no} covering "
                    f"{payload.period_start} — a second one for the same period would "
                    "pay them twice. Correct that one, or file the next period"
                ),
            )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"invoice_no {invoice_no!r} already exists in this workspace",
    )


def ensure_payslip_line_explains_itself(direction: str, notes, pay_history_id) -> None:
    """A payslip line has to say where its number came from.

    This is the other half of a deliberate omission. 五险一金 rates, the 个税
    累计预扣 table, the contribution ceilings — none of it is stored here,
    because it is national policy the agent already knows and a records layer
    that quietly applied it would be inventing policy. The consequence is that
    the payslip is the ONLY place the arithmetic survives: nothing in this
    database could reconstruct why the deduction was 960.00 rather than 860.00.

    So a line either cites the pay record it came from — a salary line saying
    "this is that 15000" — or spells the calculation out in `notes`
    ("缴费基数 12000.00 × 8% = 960.00"). A line that does neither is a number
    nobody can check, which is the one thing a payslip may not contain.
    """
    if direction != "payroll" or pay_history_id is not None:
        return
    if notes is None or not str(notes).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "a payslip line must show its working: either cite the pay record it "
                "comes from (`pay_history_id`) or state the calculation in `notes` "
                "— e.g. 缴费基数 12000.00 × 8% = 960.00. The server computes no "
                "social-insurance or tax figure of its own, so this line is the only "
                "record of how the number was reached"
            ),
        )


@router.get("/invoices", response_model=InvoiceListEnvelope, response_model_exclude_unset=True)
def list_invoices(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    direction: str | None = None,
    customer_id: str | None = None,
    vendor_id: str | None = None,
    employee_id: str | None = None,
    # the person a payslip pays, as opposed to the 经办人 in `employee_id`
    payee_employee_id: str | None = None,
    invoice_no: str | None = None,
    tax_invoice_number: str | None = None,
    sales_order_id: str | None = None,
    purchase_order_id: str | None = None,
    period_start: date | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    outstanding: bool = False,
    due_before: date | None = None,
    without_open_todo: bool = False,
    keyword: str | None = None,
    include_deleted: bool = False,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """The receivables/payables work queues live here.

    `outstanding=true` is "still owed" measured against the settlement ledger,
    not against a status: an invoice is outstanding while what it bills exceeds
    what has been applied to it. Combined with `direction` and `due_before` it
    is the overdue queue — `?direction=sales&outstanding=true&due_before=today`
    is 逾期应收, and the purchase side is what is due to be paid.
    """
    tenant_id = actor.tenant_id
    validate_status_filter(db, tenant_id, "invoice", status_filter)
    stmt = select(Invoice).where(Invoice.tenant_id == tenant_id)
    # payslips are hidden from credentials that may not read pay; everyone
    # still sees their own
    payroll_gate = visible_payroll_filter(actor)
    if payroll_gate is not None:
        stmt = stmt.where(payroll_gate)
    if not include_deleted:
        stmt = stmt.where(Invoice.deleted_at.is_(None))
    if outstanding:
        # the billed amount is the declared total when there is one, else the
        # live line sum — the same rule /detail reports, expressed in SQL
        line_sum = (
            select(func.coalesce(func.sum(InvoiceItem.amount), 0))
            .where(
                InvoiceItem.tenant_id == tenant_id,
                InvoiceItem.invoice_id == Invoice.id,
                InvoiceItem.deleted_at.is_(None),
            )
            .scalar_subquery()
        )
        billed = func.coalesce(Invoice.total_amount, line_sum)
        stmt = stmt.where(billed - func.coalesce(Invoice.applied_amount, 0) > 0.005)
    if due_before is not None:
        stmt = stmt.where(Invoice.due_date.is_not(None), Invoice.due_date < due_before)
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, Invoice, tenant_id, "invoice")
    return list_rows(
        db, stmt,
        filters={
            Invoice.direction: direction,
            Invoice.customer_id: customer_id,
            Invoice.vendor_id: vendor_id,
            Invoice.employee_id: employee_id,
            Invoice.payee_employee_id: payee_employee_id,
            Invoice.invoice_no: invoice_no,
            Invoice.tax_invoice_number: tax_invoice_number,
            Invoice.sales_order_id: sales_order_id,
            Invoice.purchase_order_id: purchase_order_id,
            Invoice.period_start: period_start,
            Invoice.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            Invoice.title,
            Invoice.invoice_no,
            Invoice.tax_invoice_number,
            Invoice.counterparty_name_snapshot,
        ),
        order_by=(Invoice.created_at.desc(), Invoice.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=InvoiceRead,
    )


@router.post(
    "/invoices",
    status_code=status.HTTP_201_CREATED,
    response_model=InvoiceCreatedEnvelope,
    response_model_exclude_unset=True,
)
def create_invoice(
    payload: CreateInvoiceRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "invoice.manage", payload.direction)
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    counterparty, party_name = resolve_invoice_counterparty(
        db, tenant_id, payload.direction,
        {
            "customer_id": payload.customer_id,
            "vendor_id": payload.vendor_id,
            "payee_employee_id": payload.payee_employee_id,
        },
    )
    if payload.direction == "payroll":
        ensure_payroll_shape(db, tenant_id, payload)
    if payload.invoice_type is not None:
        require_type_option(db, tenant_id, "invoice_type", payload.invoice_type)
    ensure_invoice_order_link(
        db, tenant_id, payload.direction,
        {
            "sales_order_id": payload.sales_order_id,
            "purchase_order_id": payload.purchase_order_id,
        },
    )
    if payload.attachment_id:
        get_scoped_or_404(db, Attachment, tenant_id, payload.attachment_id)
    if payload.project_id:
        get_scoped_or_404(db, Project, tenant_id, payload.project_id)
    ensure_invoice_not_duplicated(
        db, tenant_id, payload.tax_invoice_number, direction=payload.direction
    )
    # An invoice bills something. With neither lines nor a declared total it
    # bills nothing — `billed_total` is 0, so it is not a draft awaiting detail,
    # it is a document that says nothing and can never be settled. Lines ride
    # this call precisely so that stating both at once is the easy path.
    if payload.total_amount is None and not payload.items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "an invoice needs something to bill: send `items`, or a "
                "`total_amount` when the amount is agreed as one figure (汇总开票)"
            ),
        )
    require_machine_state(db, tenant_id, Invoice, payload.status)
    invoice_no = payload.invoice_no or allocate_number(db, Invoice, tenant_id)
    invoice = Invoice(
        tenant_id=tenant_id,
        invoice_no=invoice_no,
        direction=payload.direction,
        invoice_type=payload.invoice_type,
        employee_id=payload.employee_id,
        counterparty_name_snapshot=payload.counterparty_name_snapshot or party_name,
        title=payload.title,
        period_start=payload.period_start,
        period_end=payload.period_end,
        invoice_date=payload.invoice_date,
        **counterparty,
        due_date=payload.due_date,
        currency=payload.currency,
        total_amount=payload.total_amount,
        tax_amount=payload.tax_amount,
        tax_invoice_code=payload.tax_invoice_code,
        tax_invoice_number=payload.tax_invoice_number,
        extracted_fields_jsonb=payload.extracted_fields,
        attachment_id=payload.attachment_id,
        sales_order_id=payload.sales_order_id,
        purchase_order_id=payload.purchase_order_id,
        project_id=payload.project_id,
        status=payload.status,
        remarks=payload.remarks,
        source_report_text=payload.source_report_text,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(invoice)
    try:
        db.flush()
        # inline lines ride the same transaction: one bad row rolls the whole
        # invoice back, so a validation error never leaves a half-raised
        # document behind
        items = [build_invoice_item(db, actor, row, invoice=invoice) for row in payload.items]
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflicting_invoice(db, tenant_id, invoice_no, payload)
    db.refresh(invoice)
    data = InvoiceRead.model_validate(invoice).model_dump(by_alias=True)
    if items:
        # the response IS the read-back: what landed, line by line
        data["items"] = [
            InvoiceItemRead.model_validate(item).model_dump(by_alias=True) for item in items
        ]
    return envelope(data)


@router.get("/invoices/{invoice_id}", response_model=InvoiceEnvelope, response_model_exclude_unset=True)
def get_invoice(
    invoice_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    invoice = get_active_document_or_404(db, Invoice, actor.tenant_id, invoice_id)
    ensure_invoice_visible(actor, invoice)
    return envelope(InvoiceRead.model_validate(invoice).model_dump(by_alias=True))


@router.patch("/invoices/{invoice_id}", response_model=InvoiceEnvelope, response_model_exclude_unset=True)
def update_invoice(
    invoice_id: str,
    payload: UpdateInvoiceRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The direction is immutable: it decides the counterparty, the capability
    scope, the billable order and what a payment may settle. Changing it would
    silently reinterpret every one of those, so an invoice filed the wrong way
    round is voided and refiled rather than flipped."""
    tenant_id = actor.tenant_id
    invoice = get_active_document_or_404(db, Invoice, tenant_id, invoice_id)
    # A payslip is invisible to a principal without `payroll.read`, and
    # invisible has to mean untouchable: the same 404 GET gives, so a PATCH
    # cannot be used to probe for one. This used to be covered incidentally by
    # the blanket `invoice.manage` check below — it is explicit now that the
    # check is conditional.
    ensure_invoice_visible(actor, invoice)
    updates = payload.model_dump(exclude_unset=True)
    # Only `status` is the flow's to write; the rest of the header is what
    # somebody filed, so changing it takes the capability that filed it. The
    # same line `ensure_content_edit_allowed` draws for timesheets and expense
    # claims, which is why the hosted agent can advance those and — until now —
    # could not advance the two money documents it is subscribed to by default.
    #
    # Status itself stays guarded, harder: `apply_status_change` requires
    # `invoice.advance` AND the hosted write boundary AND a legal transition.
    if any(field != "status" for field in updates):
        require_permission(actor, "invoice.manage", invoice.direction)
    # what this invoice bills is what settlement measures against — freeze it
    # once the invoice is no longer editable, or /apply's over-application guard
    # can be walked around with a plain PATCH
    ensure_money_fields_editable(
        db, invoice, updates, ("total_amount", "tax_amount", "currency")
    )
    if "invoice_type" in updates and updates["invoice_type"] is not None:
        require_type_option(db, tenant_id, "invoice_type", updates["invoice_type"])
    if any(field in updates for field in COUNTERPARTY_FIELD_BY_DIRECTION.values()):
        counterparty, party_name = resolve_invoice_counterparty(
            db, tenant_id, invoice.direction,
            {
                field: updates.get(field, getattr(invoice, field))
                for field in COUNTERPARTY_FIELD_BY_DIRECTION.values()
            },
        )
        updates.update(counterparty)
        updates.setdefault("counterparty_name_snapshot", party_name)
    if "sales_order_id" in updates or "purchase_order_id" in updates:
        ensure_invoice_order_link(db, tenant_id, invoice.direction, updates)
    if updates.get("attachment_id"):
        get_scoped_or_404(db, Attachment, tenant_id, updates["attachment_id"])
    if updates.get("project_id"):
        get_scoped_or_404(db, Project, tenant_id, updates["project_id"])
    if "tax_invoice_number" in updates and updates["tax_invoice_number"] != invoice.tax_invoice_number:
        ensure_invoice_not_duplicated(
            db, tenant_id, updates["tax_invoice_number"],
            direction=invoice.direction, exclude_invoice_id=invoice.id,
        )
    if "status" in updates and updates["status"] != invoice.status:
        apply_status_change(db, actor, invoice, updates["status"])
        if updates["status"] == "issued" and invoice.issued_at is None:
            invoice.issued_at = datetime.now(timezone.utc)
    if "extracted_fields" in updates:
        invoice.extracted_fields_jsonb = updates.pop("extracted_fields")
    if "custom_fields" in updates:
        invoice.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(invoice, field, value)
    db.commit()
    db.refresh(invoice)
    return envelope(InvoiceRead.model_validate(invoice).model_dump(by_alias=True))


@router.delete("/invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(
    invoice_id: str,
    payload: DeleteInvoiceRequest | None = None,
    actor: Annotated[Actor, Depends(get_actor)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """An invoice payments have settled cannot be hidden — same rule the
    payment side keeps, for the same reason."""
    invoice = get_scoped_or_404(db, Invoice, actor.tenant_id, invoice_id)
    if invoice.deleted_at is None:
        ensure_nothing_applied(db, invoice, label="invoice")
    return delete_document(db, actor, Invoice, invoice_id, payload)


@router.post("/invoices/{invoice_id}/restore", response_model=InvoiceEnvelope, response_model_exclude_unset=True)
def restore_invoice(
    invoice_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, Invoice, invoice_id)


@router.post("/invoices/{invoice_id}/submit", response_model=InvoiceEnvelope, response_model_exclude_unset=True)
def submit_invoice(
    invoice_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return submit_document(db, actor, Invoice, invoice_id)


def invoice_line_amount(item: InvoiceItem) -> float | None:
    """The line's money: the stated amount, else quantity × unit price. A line
    with neither (a description-only line on a 汇总开票) contributes nothing and
    is not an error."""
    if item.amount is not None:
        return float(item.amount)
    if item.quantity is not None and item.unit_price is not None:
        return float(item.quantity) * float(item.unit_price)
    return None


def invoice_billed_total(invoice: Invoice, items: list[InvoiceItem]) -> float:
    """What settlement is measured against: the declared header total when the
    tenant stated one, else the line sum. Same contract quotations and orders
    keep — and it is what makes a header-only invoice (no lines at all, which
    is how most 汇总开票 arrive) settleable."""
    if invoice.total_amount is not None:
        return float(invoice.total_amount)
    return float(sum(amount for amount in map(invoice_line_amount, items) if amount is not None))


def live_invoice_items(db: Session, tenant_id: str, invoice_id: str) -> list[InvoiceItem]:
    return list(
        db.scalars(
            select(InvoiceItem)
            .where(
                InvoiceItem.tenant_id == tenant_id,
                InvoiceItem.invoice_id == invoice_id,
                InvoiceItem.deleted_at.is_(None),
            )
            .order_by(
                InvoiceItem.line_no.asc().nulls_last(),
                InvoiceItem.created_at.asc(),
                InvoiceItem.id.asc(),
            )
        ).all()
    )


def invoice_applications(db: Session, tenant_id: str, invoice_id: str) -> list[PaymentApplication]:
    return applications_for_target(db, tenant_id, "invoice", invoice_id)


def invoice_order_match(db: Session, tenant_id: str, invoice: Invoice, items: list[InvoiceItem]):
    """三单匹配 — 采购: ordered vs received vs billed, per order line.

    Facts only. The tolerance question ("是不是差得太多了") is the agent's,
    against the tenant's workflow definition; a threshold here would be
    business policy living in the record layer.

    Billed quantities are summed across EVERY invoice pinned to the order, not
    just this one — otherwise a second invoice for the same delivery would look
    like the first one never happened."""
    order_field = ORDER_LINK_BY_DIRECTION[invoice.direction]
    # a payslip bills no order, so there is nothing to match against
    if order_field is None:
        return None
    order_id = getattr(invoice, order_field)
    if order_id is None:
        return None
    order_model = ORDER_MODEL_BY_DIRECTION[invoice.direction]
    order = db.scalar(
        select(order_model).where(order_model.tenant_id == tenant_id, order_model.id == order_id)
    )
    if order is None:
        return None
    line_field, item_model, parent_field = ORDER_ITEM_LINK_BY_DIRECTION[invoice.direction]
    order_lines = list(
        db.scalars(
            select(item_model)
            .where(
                item_model.tenant_id == tenant_id,
                getattr(item_model, parent_field) == order.id,
                item_model.deleted_at.is_(None),
            )
            .order_by(item_model.line_no.asc().nulls_last(), item_model.created_at.asc())
        ).all()
    )
    invoice_line_col = getattr(InvoiceItem, line_field)
    billed_rows = db.execute(
        select(
            invoice_line_col,
            func.coalesce(func.sum(InvoiceItem.quantity), 0),
            func.coalesce(func.sum(InvoiceItem.amount), 0),
        )
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .where(
            InvoiceItem.tenant_id == tenant_id,
            invoice_line_col.in_([line.id for line in order_lines] or [""]),
            InvoiceItem.deleted_at.is_(None),
            Invoice.deleted_at.is_(None),
        )
        .group_by(invoice_line_col)
    ).all()
    billed = {row[0]: (float(row[1]), float(row[2])) for row in billed_rows}

    match_lines: list[InvoiceOrderMatchLineRead] = []
    ordered_total = 0.0
    for line in order_lines:
        billed_quantity, billed_amount = billed.get(line.id, (0.0, 0.0))
        ordered_amount = (
            float(line.amount)
            if line.amount is not None
            else (
                float(line.quantity) * float(line.unit_price)
                if line.unit_price is not None
                else None
            )
        )
        ordered_total += ordered_amount or 0.0
        received = getattr(line, "received_quantity", None)
        received_quantity = float(received) if received is not None else None
        match_lines.append(
            InvoiceOrderMatchLineRead(
                order_item_id=line.id,
                line_no=line.line_no,
                product_name=line.product_name_snapshot,
                ordered_quantity=float(line.quantity),
                ordered_amount=ordered_amount,
                received_quantity=received_quantity,
                billed_quantity=round(billed_quantity, 2),
                billed_amount=round(billed_amount, 2),
                quantity_variance=round(billed_quantity - float(line.quantity), 2),
                receipt_variance=(
                    round(billed_quantity - received_quantity, 2)
                    if received_quantity is not None
                    else None
                ),
            )
        )
    billed_total = float(sum(line.billed_amount for line in match_lines))
    return InvoiceOrderMatchRead(
        order_type="sales_order" if invoice.direction == "sales" else "purchase_order",
        order_id=order.id,
        order_no=order.order_no if invoice.direction == "sales" else order.po_number,
        order_status=order.status,
        lines=match_lines,
        ordered_total=round(ordered_total, 2),
        billed_total=round(billed_total, 2),
        unbilled_total=round(ordered_total - billed_total, 2),
        unmatched_line_count=sum(1 for item in items if getattr(item, line_field) is None),
    )


@router.get(
    "/invoices/{invoice_id}/detail",
    response_model=InvoiceDetailEnvelope,
    response_model_exclude_unset=True,
)
def get_invoice_detail(
    invoice_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    tenant_id = actor.tenant_id
    invoice = get_scoped_or_404(db, Invoice, tenant_id, invoice_id)
    ensure_invoice_visible(actor, invoice)
    if not include_deleted:
        ensure_document_not_deleted(invoice)
    items = live_invoice_items(db, tenant_id, invoice.id)
    skus_by_id, products_by_id, _ = load_item_catalog_context(db, tenant_id, items)
    detail_items: list[InvoiceItemDetailRead] = []
    for item in items:
        product, sku = resolve_item_refs(item, skus_by_id, products_by_id)
        detail_items.append(
            InvoiceItemDetailRead(
                **InvoiceItemRead.model_validate(item).model_dump(),
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
            )
        )
    amounts = [invoice_line_amount(item) for item in items]
    billed_total = invoice_billed_total(invoice, items)
    applied_amount = float(invoice.applied_amount or 0)
    detail = InvoiceDetailRead(
        invoice=InvoiceRead.model_validate(invoice),
        items=detail_items,
        approval_records=[
            ApprovalRecordRead.model_validate(record)
            for record in document_approvals(db, tenant_id, "invoice", invoice.id)
        ],
        order_match=invoice_order_match(db, tenant_id, invoice, items),
        applications=[
            PaymentApplicationRead.model_validate(row)
            for row in invoice_applications(db, tenant_id, invoice.id)
        ],
        computed_total=float(sum(amount for amount in amounts if amount is not None)),
        computed_tax_total=float(
            sum(float(item.tax_amount) for item in items if item.tax_amount is not None)
        ),
        billed_total=billed_total,
        applied_amount=applied_amount,
        outstanding_amount=round(billed_total - applied_amount, 2),
    )
    return envelope(detail.model_dump(by_alias=True))


def _invoice_for_line(db: Session, actor: Actor, invoice_id: str) -> Invoice:
    """The write gate every invoice line shares: the invoice must be live,
    editable, and within the actor's direction scope."""
    invoice = get_active_document_or_404(db, Invoice, actor.tenant_id, invoice_id)
    require_permission(actor, "invoice.manage", invoice.direction)
    ensure_document_editable(db, invoice)
    return invoice


def ensure_invoice_item_order_link(
    db: Session, tenant_id: str, invoice: Invoice, updates: dict
) -> None:
    """A line may only bill a line of the order its own invoice bills — the
    direction's order type, and that specific order. Both halves matter: the
    first keeps 销项/进项 apart, the second stops a line quietly billing a
    different customer's order and corrupting the match.

    A payslip has no order at all, so both links are refused on its lines."""
    linkable = ORDER_ITEM_LINK_BY_DIRECTION.get(invoice.direction)
    if linkable is None:
        for field in ("sales_order_item_id", "purchase_order_item_id"):
            if updates.get(field) is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"a payslip line bills no order, so it may not pin {field}",
                )
        return
    wanted, item_model, parent_field = linkable
    other, *_ = ORDER_ITEM_LINK_BY_DIRECTION["purchase" if invoice.direction == "sales" else "sales"]
    if updates.get(other) is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"a line of a {invoice.direction!r} invoice may pin {wanted}, not {other}",
        )
    link_id = updates.get(wanted)
    if link_id is None:
        return
    line = get_live_or_404(db, item_model, tenant_id, link_id)
    billed_order_id = getattr(invoice, ORDER_LINK_BY_DIRECTION[invoice.direction])
    if billed_order_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"pin the invoice to its order first: set "
                f"{ORDER_LINK_BY_DIRECTION[invoice.direction]} on the invoice"
            ),
        )
    if getattr(line, parent_field) != billed_order_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="that order line belongs to a different order than this invoice bills",
        )


@router.get("/invoice-items", response_model=InvoiceItemListEnvelope, response_model_exclude_unset=True)
def list_invoice_items(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    invoice_id: str | None = None,
    product_id: str | None = None,
    sales_order_item_id: str | None = None,
    purchase_order_item_id: str | None = None,
):
    stmt = (
        select(InvoiceItem)
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .where(
            InvoiceItem.tenant_id == tenant_id,
            InvoiceItem.deleted_at.is_(None),
            Invoice.deleted_at.is_(None),
        )
    )
    return list_rows(
        db, stmt,
        filters={
            InvoiceItem.invoice_id: invoice_id,
            InvoiceItem.product_id: product_id,
            InvoiceItem.sales_order_item_id: sales_order_item_id,
            InvoiceItem.purchase_order_item_id: purchase_order_item_id,
        },
        order_by=(
            InvoiceItem.line_no.asc().nulls_last(),
            InvoiceItem.created_at.asc(),
            InvoiceItem.id.asc(),
        ),
        pagination=None,
        read_model=InvoiceItemRead,
    )


def build_invoice_item(db: Session, actor: Actor, payload, *, invoice: Invoice | None = None):
    """One validated line, inline or standalone — the same rules on both paths.

    `invoice` passed = the line rides the invoice's own create, so identity
    comes from the parent and the editable-state gate does not apply: the person
    is stating the whole document at once, including an invoice recorded
    directly in a later state."""
    tenant_id = actor.tenant_id
    if invoice is None:
        invoice = _invoice_for_line(db, actor, payload.invoice_id)
    else:
        named = getattr(payload, "invoice_id", None)
        if named and named != invoice.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "inline lines belong to the invoice being created; "
                    "do not name another invoice_id"
                ),
            )
    family = ITEM_TYPE_FAMILY_BY_DIRECTION[invoice.direction]
    require_type_option(db, tenant_id, family, payload.invoice_item_type)
    ensure_line_sign(db, tenant_id, family, payload.invoice_item_type, payload.amount)
    ensure_payslip_line_explains_itself(
        invoice.direction, payload.notes, payload.pay_history_id
    )
    updates = payload.model_dump(exclude_unset=True)
    ensure_invoice_item_order_link(db, tenant_id, invoice, updates)
    if payload.pay_history_id is not None:
        record = get_scoped_or_404(db, PayHistory, tenant_id, payload.pay_history_id)
        if record.employee_id != invoice.payee_employee_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="that salary record belongs to a different employee than this payslip pays",
            )
    product_id, sku_id, product_name_snapshot, unit = normalize_product_context(
        db, tenant_id, payload.product_id, payload.sku_id, payload.product_name_snapshot, payload.unit
    )
    if product_id is None and not product_name_snapshot:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="an invoice line needs a product_id (or sku_id) or a free-text product_name_snapshot",
        )
    item = InvoiceItem(
        tenant_id=tenant_id,
        invoice_id=invoice.id,
        line_no=payload.line_no,
        invoice_item_type=payload.invoice_item_type,
        product_id=product_id,
        sku_id=sku_id,
        product_name_snapshot=product_name_snapshot,
        spec=payload.spec,
        quantity=payload.quantity,
        unit=unit,
        unit_price=payload.unit_price,
        amount=payload.amount,
        tax_rate=payload.tax_rate,
        tax_amount=payload.tax_amount,
        sales_order_item_id=payload.sales_order_item_id,
        purchase_order_item_id=payload.purchase_order_item_id,
        pay_history_id=payload.pay_history_id,
        notes=payload.notes,
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(item)
    db.flush()
    return item


@router.post(
    "/invoice-items",
    status_code=status.HTTP_201_CREATED,
    response_model=InvoiceItemEnvelope,
    response_model_exclude_unset=True,
)
def create_invoice_item(
    payload: CreateInvoiceItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Add a line to an invoice that already exists. Raising an invoice with its
    lines is one call — see POST /invoices."""
    item = build_invoice_item(db, actor, payload)
    db.commit()
    db.refresh(item)
    return envelope(InvoiceItemRead.model_validate(item).model_dump(by_alias=True))


@router.get("/invoice-items/{item_id}", response_model=InvoiceItemEnvelope, response_model_exclude_unset=True)
def get_invoice_item(
    item_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    item = require_live_line(db, tenant_id, InvoiceItem, Invoice, "invoice_id", item_id)
    return envelope(InvoiceItemRead.model_validate(item).model_dump(by_alias=True))


@router.patch("/invoice-items/{item_id}", response_model=InvoiceItemEnvelope, response_model_exclude_unset=True)
def update_invoice_item(
    item_id: str,
    payload: UpdateInvoiceItemRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    item = get_live_or_404(db, InvoiceItem, tenant_id, item_id)
    invoice = _invoice_for_line(db, actor, item.invoice_id)
    updates = payload.model_dump(exclude_unset=True)
    family = ITEM_TYPE_FAMILY_BY_DIRECTION[invoice.direction]
    if updates.get("invoice_item_type") is not None:
        require_type_option(db, tenant_id, family, updates["invoice_item_type"])
    ensure_line_sign(
        db, tenant_id, family,
        updates.get("invoice_item_type", item.invoice_item_type),
        updates.get("amount", item.amount),
    )
    ensure_payslip_line_explains_itself(
        invoice.direction,
        updates.get("notes", item.notes),
        updates.get("pay_history_id", item.pay_history_id),
    )
    ensure_invoice_item_order_link(db, tenant_id, invoice, updates)
    if "product_id" in updates or "sku_id" in updates or "product_name_snapshot" in updates or "unit" in updates:
        # a stale variant must never survive a product swap — same rule the
        # shared line helper keeps
        product_unchanged = updates.get("product_id", item.product_id) == item.product_id
        product_id, sku_id, product_name_snapshot, unit = normalize_product_context(
            db, tenant_id,
            updates.get("product_id", item.product_id),
            updates.get("sku_id", item.sku_id if product_unchanged else None),
            updates.get("product_name_snapshot", item.product_name_snapshot),
            updates.get("unit", item.unit),
        )
        item.product_id, item.sku_id = product_id, sku_id
        item.product_name_snapshot, item.unit = product_name_snapshot, unit
        for consumed in ("product_id", "sku_id", "product_name_snapshot", "unit"):
            updates.pop(consumed, None)
    if "custom_fields" in updates:
        item.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return envelope(InvoiceItemRead.model_validate(item).model_dump(by_alias=True))


@router.delete("/invoice-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice_item(
    item_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    item = get_live_or_404(db, InvoiceItem, actor.tenant_id, item_id)
    _invoice_for_line(db, actor, item.invoice_id)
    item.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- payroll: the salary record ---------------------------------------------
#
# OFBiz's `PayHistory`. The point of the entity is the history: what someone was
# paid last March has to stay answerable, because a payslip issued last March
# has to stay explainable.


def pay_history_or_404(db: Session, tenant_id: str, record_id: str) -> PayHistory:
    return get_scoped_or_404(db, PayHistory, tenant_id, record_id)


def ensure_pay_history_unused(db: Session, record: PayHistory) -> None:
    """A record a payslip has already cited is frozen. Moving it would change
    what an issued document says without touching that document."""
    cited = db.scalar(
        select(func.count())
        .select_from(InvoiceItem)
        .where(
            InvoiceItem.tenant_id == record.tenant_id,
            InvoiceItem.pay_history_id == record.id,
            InvoiceItem.deleted_at.is_(None),
        )
    )
    if cited:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{cited} payslip line(s) were computed from this salary record — "
                "record a new one from a later date instead of editing this"
            ),
        )


def ensure_no_overlapping_pay_period(
    db: Session, tenant_id: str, employee_id: str, component: str, effective_from: date,
    effective_thru: date | None, *, exclude_id: str | None = None,
) -> None:
    """Two salaries in force on the same day is not a fact about anybody — but
    a salary and a commission rate in force on the same day is the ordinary
    case, so the check is per COMPONENT.

    A unique index cannot say this — it is about ranges — so the API says it and
    the integrity audit says it again over the whole table."""
    stmt = select(PayHistory).where(
        PayHistory.tenant_id == tenant_id,
        PayHistory.employee_id == employee_id,
        PayHistory.component == component,
        PayHistory.effective_from <= (effective_thru or date(9999, 12, 31)),
        or_(
            PayHistory.effective_thru.is_(None),
            PayHistory.effective_thru >= effective_from,
        ),
    )
    if exclude_id:
        stmt = stmt.where(PayHistory.id != exclude_id)
    clash = db.scalars(stmt).first()
    if clash is not None:
        stated = (
            f"{float(clash.amount):.2f}"
            if clash.amount is not None
            else (f"{float(clash.rate)} of {clash.basis}" if clash.rate is not None else "a term")
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{clash.component} of {stated} is already in force from "
                f"{clash.effective_from} to {clash.effective_thru or '—'} for this employee"
            ),
        )


def pay_term_in_force_on(on: date):
    """A term is in force on a day if it had started and had not yet ended.
    An open `effective_thru` means "still current", not "ended at null"."""
    return and_(
        PayHistory.effective_from <= on,
        or_(PayHistory.effective_thru.is_(None), PayHistory.effective_thru >= on),
    )


def ensure_pay_term_states_something(payload) -> None:
    """A term has to say what it is. The three shapes cover a scalar (12000 a
    month), a proportion (3% of collections) and everything else in words — but
    a rate with nothing to apply it to is not a rule, it is half of one."""
    if payload.amount is None and payload.rate is None and not payload.formula:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "a pay term states an amount, a rate (with the basis it applies to), "
                "or a formula in words — this one states none of them"
            ),
        )
    if payload.rate is not None and not payload.basis:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "a rate needs the basis it applies to — 回款额, 毛利, 签约额, "
                "whatever this workspace calls it"
            ),
        )


@router.get("/pay-histories", response_model=PayHistoryListEnvelope, response_model_exclude_unset=True)
def list_pay_histories(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    component: str | None = None,
    in_force_on: date | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Salaries are the one thing in this system a credential does not get to
    read merely by belonging to the workspace. Without `payroll.read` an actor
    sees its own record and nothing else."""
    tenant_id = actor.tenant_id
    stmt = select(PayHistory).where(PayHistory.tenant_id == tenant_id)
    if not may_read_payroll(actor):
        own = own_employee_id(actor)
        if own is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="requires capability payroll.read",
            )
        stmt = stmt.where(PayHistory.employee_id == own)
    if in_force_on is not None:
        stmt = stmt.where(pay_term_in_force_on(in_force_on))
    return list_rows(
        db, stmt,
        filters={PayHistory.employee_id: employee_id, PayHistory.component: component},
        order_by=(PayHistory.effective_from.desc(), PayHistory.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=PayHistoryRead,
    )


@router.post(
    "/pay-histories",
    status_code=status.HTTP_201_CREATED,
    response_model=PayHistoryChangeEnvelope,
    response_model_exclude_unset=True,
)
def create_pay_history(
    payload: CreatePayHistoryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Set or change a salary. A change closes the record in force the day
    before and opens this one — one call, one transaction, because as two calls
    the pair eventually drifts and leaves a hole in someone's history."""
    tenant_id = actor.tenant_id
    require_permission(actor, "payroll.manage")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    require_type_option(db, tenant_id, "pay_component_type", payload.component)
    require_type_option(db, tenant_id, "pay_period_type", payload.period_type)
    ensure_pay_term_states_something(payload)
    if payload.effective_thru is not None and payload.effective_thru < payload.effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="effective_thru cannot precede effective_from",
        )

    superseded = db.scalars(
        select(PayHistory)
        .where(
            PayHistory.tenant_id == tenant_id,
            PayHistory.employee_id == payload.employee_id,
            # only the same component is superseded — a pay rise must not
            # silently close somebody's commission arrangement
            PayHistory.component == payload.component,
            PayHistory.effective_from < payload.effective_from,
            PayHistory.effective_thru.is_(None),
        )
        .order_by(PayHistory.effective_from.desc())
    ).first()
    if superseded is not None:
        superseded.effective_thru = payload.effective_from - timedelta(days=1)
        db.flush()

    ensure_no_overlapping_pay_period(
        db, tenant_id, payload.employee_id, payload.component,
        payload.effective_from, payload.effective_thru,
    )
    record = PayHistory(
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        component=payload.component,
        effective_from=payload.effective_from,
        effective_thru=payload.effective_thru,
        amount=payload.amount,
        rate=payload.rate,
        basis=payload.basis,
        formula=payload.formula,
        period_type=payload.period_type,
        currency=payload.currency,
        notes=payload.notes,
        created_by=attributed(actor, None),
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                    f"this employee already has a {payload.component} term starting "
                f"{payload.effective_from}"
            ),
        )
    db.refresh(record)
    if superseded is not None:
        db.refresh(superseded)
    record_audit(
        db,
        tenant_id=tenant_id,
        action="pay_history.recorded",
        entity_type="pay_history",
        entity_id=record.id,
        actor=actor.label,
        detail={
            "employee_id": record.employee_id,
            "component": record.component,
            "effective_from": record.effective_from.isoformat(),
            "superseded_id": superseded.id if superseded else None,
        },
    )
    db.commit()
    return envelope(
        PayHistoryChangeRead(
            current=PayHistoryRead.model_validate(record),
            superseded=(
                PayHistoryRead.model_validate(superseded) if superseded is not None else None
            ),
        ).model_dump(by_alias=True)
    )


@router.get("/pay-histories/{record_id}", response_model=PayHistoryEnvelope, response_model_exclude_unset=True)
def get_pay_history(
    record_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    record = pay_history_or_404(db, actor.tenant_id, record_id)
    if not may_read_payroll(actor) and own_employee_id(actor) != record.employee_id:
        # 404, not 403: refusing by name would confirm whose record exists
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PayHistory not found")
    return envelope(PayHistoryRead.model_validate(record).model_dump(by_alias=True))


@router.patch("/pay-histories/{record_id}", response_model=PayHistoryEnvelope, response_model_exclude_unset=True)
def update_pay_history(
    record_id: str,
    payload: UpdatePayHistoryRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Correcting a typo. A real change in pay is a new record — see POST."""
    tenant_id = actor.tenant_id
    require_permission(actor, "payroll.manage")
    record = pay_history_or_404(db, tenant_id, record_id)
    ensure_pay_history_unused(db, record)
    updates = payload.model_dump(exclude_unset=True)
    if "period_type" in updates and updates["period_type"] is not None:
        require_type_option(db, tenant_id, "pay_period_type", updates["period_type"])
    effective_from = updates.get("effective_from", record.effective_from)
    effective_thru = updates.get("effective_thru", record.effective_thru)
    if effective_thru is not None and effective_thru < effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="effective_thru cannot precede effective_from",
        )
    if "effective_from" in updates or "effective_thru" in updates:
        ensure_no_overlapping_pay_period(
            db, tenant_id, record.employee_id, record.component,
            effective_from, effective_thru, exclude_id=record.id,
        )
    ensure_pay_term_states_something(
        SimpleNamespace(
            amount=updates.get("amount", record.amount),
            rate=updates.get("rate", record.rate),
            basis=updates.get("basis", record.basis),
            formula=updates.get("formula", record.formula),
        )
    )
    if "custom_fields" in updates:
        record.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return envelope(PayHistoryRead.model_validate(record).model_dump(by_alias=True))


@router.get(
    "/employees/{employee_id}/pay-history",
    response_model=PayHistoryListEnvelope,
    response_model_exclude_unset=True,
)
def get_employee_pay_history(
    employee_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    component: str | None = None,
    in_force_on: date | None = None,
):
    """One person's whole compensation trail, newest first.

    `in_force_on` narrows it to what applied on a day, which is the question
    a payslip actually asks — every component in force that month, in one
    call."""
    tenant_id = actor.tenant_id
    if not may_read_payroll(actor) and own_employee_id(actor) != employee_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    get_scoped_or_404(db, Employee, tenant_id, employee_id)
    stmt = select(PayHistory).where(
        PayHistory.tenant_id == tenant_id, PayHistory.employee_id == employee_id
    )
    if in_force_on is not None:
        stmt = stmt.where(pay_term_in_force_on(in_force_on))
    return list_rows(
        db,
        stmt,
        filters={PayHistory.component: component},
        order_by=(PayHistory.effective_from.desc(), PayHistory.id.desc()),
        pagination=None,
        read_model=PayHistoryRead,
    )


# --- 规章制度 ---------------------------------------------------------------
#
# The company's own rules, published with a version and a name attached.
#
# There is deliberately no second table holding the figures in a structured
# form. That shape exists in traditional systems because their consumer cannot
# read prose; ours can. A `policy_rules` table would only have been a second
# source of truth for the same rules, free to drift from the body with nothing
# to notice — so the structured restatement, when a workspace wants one, is
# `rules_json` on this row, versioned and published and frozen with the document
# it restates.
#
# The server never applies a rule and never parses one. It stores what HR
# published and who published it; the agent reads it, computes with it, and
# records its working — the same relationship the payroll path has with 五险一金
# rates, except the figure now has a publisher and a date instead of living in
# the agent's memory. See docs/policies.md.


def may_manage_policies(actor: Actor) -> bool:
    return has_permission(actor, "policy.manage") or has_permission(actor, "policy.publish")


def may_read_policy(actor: Actor, policy: Policy) -> bool:
    """Three gates, in the order they matter.

    A DRAFT is invisible to everyone but its authors — the draft 裁员方案 is
    more dangerous than the published one, and a workspace that could read
    drafts would learn what is coming before it is decided.

    A REPEALED policy is likewise author-only: it is history, and leaving it in
    the handbook is how somebody follows a rule that no longer applies.

    A RESTRICTED policy names the capability it wants and the row is checked
    against it. Everything else published is readable by anyone here, which is
    the point — an employee handbook nobody may read is not a handbook.
    """
    if policy.status in ("draft", "repealed"):
        return may_manage_policies(actor)
    if policy.visibility == "restricted":
        if not policy.required_capability:
            # the CHECK constraint makes this unreachable; if it ever is
            # reached, refusing is the safe direction
            return may_manage_policies(actor)
        verb, _, scope = policy.required_capability.partition(":")
        return has_permission(actor, verb, scope or None)
    return True


def covered_policy_capabilities(db: Session, actor: Actor, tenant_id: str) -> list[str]:
    """Which of the capability strings this tenant's policies ask for are ones
    this actor holds.

    The set is decided in Python — `has_permission` knows about scopes and
    bypasses — but it has to become a SQL predicate, so it is resolved against
    the DISTINCT values actually in use rather than against every string that
    could exist. That is a handful of rows, and it keeps the filter exact.
    """
    declared = db.scalars(
        select(Policy.required_capability)
        .where(Policy.tenant_id == tenant_id, Policy.required_capability.is_not(None))
        .distinct()
    ).all()
    covered = []
    for value in declared:
        verb, _, scope = value.partition(":")
        if has_permission(actor, verb, scope or None):
            covered.append(value)
    return covered


def visible_policy_filter(db: Session, actor: Actor, tenant_id: str):
    """The list-side twin of `may_read_policy`, as SQL rather than a post-filter.

    Filtering rows after the query would make `total` and the page size lie —
    the caller would page through a list whose count includes documents it
    cannot see, which is itself a leak (how many restricted policies exist is
    worth hiding). So the whole gate is expressed as a WHERE clause.
    """
    if may_manage_policies(actor):
        return None
    readable = or_(
        Policy.visibility != "restricted",
        Policy.required_capability.in_(covered_policy_capabilities(db, actor, tenant_id)),
    )
    return and_(Policy.status.in_(("published", "superseded")), readable)


def ensure_policy_visible(actor: Actor, policy: Policy) -> None:
    """404, not 403. That a 薪酬管理办法 exists at all is part of what a
    restricted policy is hiding."""
    if not may_read_policy(actor, policy):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")


def ensure_policy_visibility_shape(visibility: str | None, required_capability) -> None:
    if visibility == "restricted" and not required_capability:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "a restricted policy must name the capability that may read it "
                "(`required_capability`) — one that names none is readable by "
                "everyone, which is the opposite of what it says"
            ),
        )


def ensure_policy_editable(policy: Policy) -> None:
    if policy.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"policy {policy.code} v{policy.version} is {policy.status} — a published "
                "policy is corrected by publishing a new version, never edited in place, "
                "so that what people were told stays recoverable. To change only who "
                "may READ it, which is not a change to what it says, use "
                "POST /policies/{id}/visibility"
            ),
        )


def next_policy_version(db: Session, tenant_id: str, code: str) -> int:
    highest = db.scalar(
        select(func.max(Policy.version)).where(
            Policy.tenant_id == tenant_id, Policy.code == code
        )
    )
    return (highest or 0) + 1


@router.get("/policies", response_model=PolicyListEnvelope, response_model_exclude_unset=True)
def list_policies(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    code: str | None = None,
    category: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    visibility: str | None = None,
    in_force_on: date | None = None,
    keyword: str | None = None,
    include_deleted: bool = False,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """`in_force_on` is the question worth asking — what applied in March, not
    what is on the intranet today."""
    tenant_id = actor.tenant_id
    stmt = select(Policy).where(Policy.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(Policy.deleted_at.is_(None))
    narrowing = visible_policy_filter(db, actor, tenant_id)
    if narrowing is not None:
        stmt = stmt.where(narrowing)
    if in_force_on is not None:
        stmt = stmt.where(
            Policy.status.in_(("published", "superseded", "repealed")),
            or_(Policy.effective_from.is_(None), Policy.effective_from <= in_force_on),
            or_(Policy.effective_thru.is_(None), Policy.effective_thru >= in_force_on),
        )
    result = list_rows(
        db, stmt,
        filters={
            Policy.code: code,
            Policy.category: category,
            Policy.status: status_filter,
            Policy.visibility: visibility,
        },
        keyword=keyword,
        keyword_columns=(Policy.code, Policy.title, Policy.summary),
        order_by=(Policy.code.asc(), Policy.version.desc()),
        pagination=page_only_pagination(page, size),
        read_model=PolicyRead,
    )
    return result


@router.post(
    "/policies",
    status_code=status.HTTP_201_CREATED,
    response_model=PolicyEnvelope,
    response_model_exclude_unset=True,
)
def create_policy(
    payload: CreatePolicyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Always a draft. Reusing a `code` opens the next version of that policy —
    the version number is the server's to allocate, so two people cannot both
    be drafting v2."""
    require_permission(actor, "policy.manage")
    tenant_id = actor.tenant_id
    require_type_option(db, tenant_id, "policy_category", payload.category)
    ensure_policy_visibility_shape(payload.visibility, payload.required_capability)
    if payload.effective_thru and payload.effective_from and (
        payload.effective_thru < payload.effective_from
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="effective_thru cannot precede effective_from",
        )
    if payload.attachment_id:
        get_scoped_or_404(db, Attachment, tenant_id, payload.attachment_id)
    if payload.owner_employee_id:
        get_scoped_or_404(db, Employee, tenant_id, payload.owner_employee_id)

    version = next_policy_version(db, tenant_id, payload.code)
    previous = db.scalars(
        select(Policy).where(
            Policy.tenant_id == tenant_id,
            Policy.code == payload.code,
            Policy.version == version - 1,
        )
    ).first()
    policy = Policy(
        tenant_id=tenant_id,
        code=payload.code,
        version=version,
        category=payload.category,
        title=payload.title,
        summary=payload.summary,
        body=payload.body,
        rules_json=payload.rules_json,
        visibility=payload.visibility,
        required_capability=payload.required_capability,
        status="draft",
        effective_from=payload.effective_from,
        effective_thru=payload.effective_thru,
        supersedes_id=previous.id if previous else None,
        attachment_id=payload.attachment_id,
        owner_employee_id=payload.owner_employee_id,
        created_by=attributed(actor, None),
        custom_fields_jsonb=payload.custom_fields,
    )
    db.add(policy)
    db.flush()
    record_audit(
        db, tenant_id=tenant_id, action="policy.drafted", entity_type="policy",
        entity_id=policy.id, actor=attributed(actor, None),
        detail={"code": policy.code, "version": policy.version},
    )
    db.commit()
    db.refresh(policy)
    return envelope(PolicyRead.model_validate(policy).model_dump(by_alias=True))


@router.get(
    "/policies/{policy_id}", response_model=PolicyEnvelope, response_model_exclude_unset=True
)
def get_policy(
    policy_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    policy = get_live_or_404(db, Policy, actor.tenant_id, policy_id)
    ensure_policy_visible(actor, policy)
    return envelope(PolicyRead.model_validate(policy).model_dump(by_alias=True))


@router.patch(
    "/policies/{policy_id}", response_model=PolicyEnvelope, response_model_exclude_unset=True
)
def update_policy(
    policy_id: str,
    payload: UpdatePolicyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "policy.manage")
    tenant_id = actor.tenant_id
    policy = get_live_or_404(db, Policy, tenant_id, policy_id)
    ensure_policy_editable(policy)
    updates = payload.model_dump(exclude_unset=True)
    if "category" in updates and updates["category"]:
        require_type_option(db, tenant_id, "policy_category", updates["category"])
    ensure_policy_visibility_shape(
        updates.get("visibility", policy.visibility),
        updates.get("required_capability", policy.required_capability),
    )
    if updates.get("attachment_id"):
        get_scoped_or_404(db, Attachment, tenant_id, updates["attachment_id"])
    if updates.get("owner_employee_id"):
        get_scoped_or_404(db, Employee, tenant_id, updates["owner_employee_id"])
    effective_from = updates.get("effective_from", policy.effective_from)
    effective_thru = updates.get("effective_thru", policy.effective_thru)
    if effective_from and effective_thru and effective_thru < effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="effective_thru cannot precede effective_from",
        )
    if "custom_fields" in updates:
        policy.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(policy, field, value)
    db.commit()
    db.refresh(policy)
    return envelope(PolicyRead.model_validate(policy).model_dump(by_alias=True))


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(
    policy_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    reason: Annotated[str | None, Query(max_length=500)] = None,
):
    """Drafts only. A published policy is repealed, not deleted — people acted
    on it, and the record of what they were told has to survive."""
    require_permission(actor, "policy.manage")
    policy = get_live_or_404(db, Policy, actor.tenant_id, policy_id)
    if policy.status != "draft":
        remedy = (
            "repeal it (POST /policies/{id}/repeal) rather than deleting it"
            if policy.status == "published"
            else "it is already closed and stays as the record of what applied then"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"policy {policy.code} v{policy.version} is {policy.status} — "
                f"{remedy}; people acted on it"
            ),
        )
    policy.deleted_at = datetime.now(timezone.utc)
    policy.deleted_by = attributed(actor, None)
    policy.delete_reason = reason
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/policies/{policy_id}/publish",
    response_model=PolicyPublishEnvelope,
    response_model_exclude_unset=True,
)
def publish_policy(
    policy_id: str,
    payload: PublishPolicyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Publishing closes the previous version and opens this one, in one
    transaction — the same handover `POST /pay-histories` performs, and for the
    same reason: as two calls they eventually drift, and a policy history with
    a gap in it cannot answer what applied in March.

    The previous version's `effective_thru` lands the day before this one
    starts, so the pair reads as a continuous record rather than two documents
    that happen to be numbered.
    """
    require_permission(actor, "policy.publish")
    tenant_id = actor.tenant_id
    policy = get_live_or_404(db, Policy, tenant_id, policy_id)
    if policy.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"policy {policy.code} v{policy.version} is already {policy.status}",
        )
    effective_from = payload.effective_from or policy.effective_from or date.today()
    if policy.effective_thru and policy.effective_thru < effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="this policy stops applying before the date it would start",
        )

    superseded = db.scalars(
        select(Policy).where(
            Policy.tenant_id == tenant_id,
            Policy.code == policy.code,
            Policy.status == "published",
            Policy.id != policy.id,
            Policy.deleted_at.is_(None),
        )
    ).first()
    if superseded is not None:
        superseded.status = "superseded"
        if superseded.effective_thru is None or superseded.effective_thru >= effective_from:
            superseded.effective_thru = effective_from - timedelta(days=1)
        # flush before promoting this one: the unit of work orders UPDATEs by
        # its own bookkeeping, not by assignment order, so without this the new
        # version can reach 'published' while the old one still is — and the
        # partial unique index refuses, correctly, in the middle of a legal
        # handover
        db.flush()

    policy.status = "published"
    policy.effective_from = effective_from
    policy.published_at = datetime.now(timezone.utc)
    policy.published_by = attributed(actor, None)
    record_audit(
        db, tenant_id=tenant_id, action="policy.published", entity_type="policy",
        entity_id=policy.id, actor=attributed(actor, None),
        detail={
            "code": policy.code,
            "version": policy.version,
            "effective_from": effective_from.isoformat(),
            "superseded_id": superseded.id if superseded else None,
            "note": payload.note,
        },
    )
    db.commit()
    db.refresh(policy)
    if superseded is not None:
        db.refresh(superseded)
    return envelope(
        PolicyPublishRead(
            current=PolicyRead.model_validate(policy),
            superseded=PolicyRead.model_validate(superseded) if superseded else None,
        ).model_dump(by_alias=True)
    )


@router.post(
    "/policies/{policy_id}/visibility",
    response_model=PolicyEnvelope,
    response_model_exclude_unset=True,
)
def rescope_policy(
    policy_id: str,
    payload: RescopePolicyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Change who may read a policy, at any status, without touching a word of
    it.

    Publication freezes what the rule SAYS — that is what lets the handbook
    answer "what were people told in March". It never should have frozen who
    may read it. Those are different kinds of fact: one is a statement made on
    a date, the other is a standing decision that outlives the statement and
    changes when the company does.

    Conflating them left the worst case with no remedy. A policy published to
    a wider audience than intended could not be edited (409), could not be
    deleted (published policies never are), and repealing it would retire a
    rule that is still in force — so the only way to close the reading was to
    stop applying the rule. That is not a choice a workspace should have to
    make about its own handbook.

    Superseded and repealed versions are re-scopable for the same reason, and
    it matters more there: they stay readable to whoever could read them, so a
    version that should never have been broadly visible has to be closable
    after the fact.

    `policy.publish` rather than `policy.manage`, because this is the authority
    act on a published document that drafting is deliberately kept apart from —
    the same line publish and repeal already draw.
    """
    require_permission(actor, "policy.publish")
    tenant_id = actor.tenant_id
    policy = get_live_or_404(db, Policy, tenant_id, policy_id)
    ensure_policy_visibility_shape(payload.visibility, payload.required_capability)
    before = (policy.visibility, policy.required_capability)
    after = (payload.visibility, payload.required_capability)
    if before == after:
        # nothing to record; a no-op audit row is noise in the one trail that
        # should read as a list of real decisions
        return envelope(PolicyRead.model_validate(policy).model_dump(by_alias=True))
    policy.visibility = payload.visibility
    policy.required_capability = payload.required_capability
    record_audit(
        db, tenant_id=tenant_id, action="policy.visibility_changed", entity_type="policy",
        entity_id=policy.id, actor=attributed(actor, None),
        detail={
            "code": policy.code,
            "version": policy.version,
            "status": policy.status,
            "from": {"visibility": before[0], "required_capability": before[1]},
            "to": {"visibility": after[0], "required_capability": after[1]},
            "note": payload.note,
        },
    )
    db.commit()
    db.refresh(policy)
    return envelope(PolicyRead.model_validate(policy).model_dump(by_alias=True))


@router.post(
    "/policies/{policy_id}/repeal",
    response_model=PolicyEnvelope,
    response_model_exclude_unset=True,
)
def repeal_policy(
    policy_id: str,
    payload: RepealPolicyRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """废止 — it stops applying, and it stops being visible to people who are
    not its authors, because a repealed rule left in the handbook is how
    somebody follows a rule that no longer exists. It is not deleted: what
    people were told, and until when, stays answerable."""
    require_permission(actor, "policy.publish")
    tenant_id = actor.tenant_id
    policy = get_live_or_404(db, Policy, tenant_id, policy_id)
    if policy.status != "published":
        # A superseded version is refused for a reason that is easy to miss: it
        # already stopped applying, on the date the handover set, and repealing
        # it would MOVE that date. The result is a hole — publish v2 from
        # 2027-07-01 (closing v1 at 2027-06-30), then repeal v1 as of
        # 2026-12-31, and the first half of 2027 is governed by neither
        # version. Nothing downstream would notice; `in_force_on` would simply
        # return nothing for six months.
        detail = (
            f"only the published version can be repealed — this one is {policy.status}"
        )
        if policy.status == "superseded":
            detail = (
                f"{policy.code} v{policy.version} was already closed on "
                f"{policy.effective_thru} when v{policy.version + 1} took over; "
                "repealing it would move that date and leave a gap in the history. "
                "Repeal the version that is currently published instead"
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    effective_thru = payload.effective_thru or date.today()
    if policy.effective_from and effective_thru < policy.effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a policy cannot stop applying before it started",
        )
    policy.status = "repealed"
    policy.effective_thru = effective_thru
    record_audit(
        db, tenant_id=tenant_id, action="policy.repealed", entity_type="policy",
        entity_id=policy.id, actor=attributed(actor, None),
        detail={
            "code": policy.code,
            "version": policy.version,
            "effective_thru": effective_thru.isoformat(),
            "note": payload.note,
        },
    )
    db.commit()
    db.refresh(policy)
    return envelope(PolicyRead.model_validate(policy).model_dump(by_alias=True))


# --- billing accounts -------------------------------------------------------
#
# A party's standing balance, in money or in points. OFBiz's BillingAccount is
# the money half; `unit_type` widens it, because a loyalty balance is the same
# object with a different unit.
#
# The balance is a running sum of an append-only entry ledger — the third time
# this codebase uses that shape (stock, settlement, and now this). Every write
# path funnels through `post_account_entries`, so the floor guard cannot be
# reached around.

ACCOUNT_OWNER_FIELDS = ("customer_id", "vendor_id", "employee_id")
ACCOUNT_OWNER_MODELS = {"customer_id": Customer, "vendor_id": Vendor, "employee_id": Employee}


def resolve_account_owner(db: Session, tenant_id: str, values: dict) -> tuple[dict, str]:
    """Exactly one owner, and it must exist here — the same rule payments keep.
    An account belonging to nobody cannot be reconciled against anything."""
    named = [field for field in ACCOUNT_OWNER_FIELDS if values.get(field)]
    if len(named) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "an account names exactly one owner: customer_id, vendor_id or employee_id"
            ),
        )
    field = named[0]
    party = get_scoped_or_404(db, ACCOUNT_OWNER_MODELS[field], tenant_id, values[field])
    resolved = {other: None for other in ACCOUNT_OWNER_FIELDS if other != field}
    resolved[field] = party.id
    return resolved, party.name


def validate_account_unit(db: Session, tenant_id: str, unit_type: str, unit: str) -> None:
    """A money account counts a currency; a points account counts whatever the
    tenant named. One column, two vocabularies — which is why `unit_type` has to
    be structural rather than a type option."""
    if unit_type == "currency":
        if len(unit) != 3 or not unit.isalpha():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"a currency account's unit is a 3-letter currency code, not {unit!r}",
            )
        return
    require_type_option(db, tenant_id, "billing_account_unit", unit)


def get_active_account_or_404(db: Session, tenant_id: str, account_id: str) -> BillingAccount:
    account = get_scoped_or_404(db, BillingAccount, tenant_id, account_id)
    if account.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BillingAccount not found")
    return account


def post_account_entries(
    db: Session,
    actor: Actor,
    account: BillingAccount,
    lines: list,
    *,
    idempotency_key: str | None = None,
    check_permission: bool = True,
) -> list[BillingAccountEntry]:
    """Append movements and move the running balance. The single write path —
    the settlement endpoint calls it too, so an account can never be moved
    without the floor being checked.

    Not gated on any document's status, for the reasons the rest of this family
    is not. It IS gated on the account's own status: refusing movement is the
    entire meaning of freezing an account, and unlike a document's lifecycle
    those three names are the product's, not the tenant's."""
    tenant_id = actor.tenant_id
    if check_permission:
        require_permission(actor, "billing_account.post", account.unit_type)
    if account.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"account {account.account_code} is {account.status} — "
                "reactivate it before recording movement"
            ),
        )
    delta = 0.0
    for line in lines:
        if abs(line.amount) < CENT:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="amount must not be zero — an entry records the balance moving",
            )
        require_type_option(db, tenant_id, "billing_account_entry_reason", line.reason)
        if getattr(line, "expires_at", None) is not None and account.unit_type != "points":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="expires_at only means something on a points account",
            )
        delta += line.amount

    balance = float(account.balance or 0)
    floor = -float(account.credit_limit or 0)
    after = balance + delta
    if after < floor - CENT:
        available = balance - floor
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{account.account_code} only has {available:.2f} {account.unit} available "
                f"(balance {balance:.2f}, credit limit {float(account.credit_limit or 0):.2f})"
            ),
        )

    written: list[BillingAccountEntry] = []
    for seq, line in enumerate(lines):
        entry = BillingAccountEntry(
            tenant_id=tenant_id,
            billing_account_id=account.id,
            amount=line.amount,
            reason=line.reason,
            description=getattr(line, "description", None),
            entity_type=getattr(line, "entity_type", None),
            entity_id=getattr(line, "entity_id", None),
            expires_at=getattr(line, "expires_at", None),
            idempotency_key=idempotency_key,
            # the key names the call; this is the row's place in it
            idempotency_seq=seq if idempotency_key else None,
            created_by=attributed(actor, None),
        )
        effective_at = getattr(line, "effective_at", None)
        if effective_at is not None:
            entry.effective_at = effective_at
        db.add(entry)
        written.append(entry)
    account.balance = round(after, 2)
    record_audit(
        db,
        tenant_id=tenant_id,
        action="billing_account.posted",
        entity_type="billing_account",
        entity_id=account.id,
        actor=actor.label,
        detail={
            "account_code": account.account_code,
            "unit": account.unit,
            "lines": [{"amount": line.amount, "reason": line.reason} for line in lines],
            "balance": account.balance,
        },
    )
    return written


def account_entries_replay(
    db: Session, tenant_id: str, account_id: str, idempotency_key: str
) -> list[BillingAccountEntry]:
    return list(
        db.scalars(
            select(BillingAccountEntry)
            .where(
                BillingAccountEntry.tenant_id == tenant_id,
                BillingAccountEntry.billing_account_id == account_id,
                BillingAccountEntry.idempotency_key == idempotency_key,
            )
            .order_by(
                BillingAccountEntry.idempotency_seq.asc().nulls_first(),
                BillingAccountEntry.id.asc(),
            )
        ).all()
    )


def expiring_account_entries(
    db: Session, tenant_id: str, account: BillingAccount, before: datetime
) -> list[BillingAccountEntry]:
    """Positive entries whose expiry has passed `before` and which no `expired`
    entry points at yet.

    The NOT EXISTS is what makes the sweep idempotent: an expiry names the earn
    entry it expired, so re-running the sweep sees the batch as already
    handled instead of expiring it twice."""
    earned = aliased(BillingAccountEntry)
    expiry = aliased(BillingAccountEntry)
    return list(
        db.scalars(
            select(earned)
            .where(
                earned.tenant_id == tenant_id,
                earned.billing_account_id == account.id,
                earned.amount > 0,
                earned.expires_at.is_not(None),
                earned.expires_at < before,
                ~select(expiry.id)
                .where(
                    expiry.tenant_id == tenant_id,
                    expiry.reason == "expired",
                    expiry.entity_type == "billing_account_entry",
                    expiry.entity_id == earned.id,
                )
                .exists(),
            )
            .order_by(earned.expires_at.asc(), earned.id.asc())
        ).all()
    )


@router.get("/billing-accounts", response_model=BillingAccountListEnvelope, response_model_exclude_unset=True)
def list_billing_accounts(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    unit_type: str | None = None,
    unit: str | None = None,
    customer_id: str | None = None,
    vendor_id: str | None = None,
    employee_id: str | None = None,
    account_code: str | None = None,
    external_account_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    over_limit: bool = False,
    keyword: str | None = None,
    include_deleted: bool = False,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """`over_limit=true` is the credit-risk queue: accounts whose balance has
    gone past the credit line they were given."""
    stmt = select(BillingAccount).where(BillingAccount.tenant_id == tenant_id)
    if not include_deleted:
        stmt = stmt.where(BillingAccount.deleted_at.is_(None))
    if over_limit:
        stmt = stmt.where(
            BillingAccount.balance < -func.coalesce(BillingAccount.credit_limit, 0) + 0.005
        )
    return list_rows(
        db, stmt,
        filters={
            BillingAccount.unit_type: unit_type,
            BillingAccount.unit: unit,
            BillingAccount.customer_id: customer_id,
            BillingAccount.vendor_id: vendor_id,
            BillingAccount.employee_id: employee_id,
            BillingAccount.account_code: account_code,
            BillingAccount.external_account_id: external_account_id,
            BillingAccount.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            BillingAccount.name,
            BillingAccount.account_code,
            BillingAccount.owner_name_snapshot,
            BillingAccount.external_account_id,
        ),
        order_by=(BillingAccount.created_at.desc(), BillingAccount.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=BillingAccountRead,
    )


@router.post(
    "/billing-accounts",
    status_code=status.HTTP_201_CREATED,
    response_model=BillingAccountEnvelope,
    response_model_exclude_unset=True,
)
def create_billing_account(
    payload: CreateBillingAccountRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """An opening balance is recorded as the account's first ENTRY, never as a
    column: the balance has to stay the ledger's sum from the very first row, or
    the integrity check that says so is a lie."""
    tenant_id = actor.tenant_id
    require_permission(actor, "billing_account.manage")
    owner, owner_name = resolve_account_owner(db, tenant_id, payload.model_dump())
    validate_account_unit(db, tenant_id, payload.unit_type, payload.unit)
    account_code = payload.account_code or allocate_document_number(
        db, tenant_id,
        model=BillingAccount, number_column=BillingAccount.account_code,
        prefix="BA-", lock_scope="billing_account_number", field="account_code",
    )
    account = BillingAccount(
        tenant_id=tenant_id,
        account_code=account_code,
        name=payload.name,
        unit_type=payload.unit_type,
        unit=payload.unit,
        owner_name_snapshot=payload.owner_name_snapshot or owner_name,
        credit_limit=payload.credit_limit,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        status=payload.status,
        external_account_id=payload.external_account_id,
        description=payload.description,
        remarks=payload.remarks,
        source_report_text=payload.source_report_text,
        custom_fields_jsonb=payload.custom_fields,
        **owner,
    )
    db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"account_code {account_code!r} already exists in this workspace",
        )
    if payload.opening_balance is not None and abs(payload.opening_balance) >= CENT:
        post_account_entries(
            db, actor, account,
            [
                SimpleNamespace(
                    amount=payload.opening_balance,
                    reason="initial",
                    description="开户期初余额",
                    entity_type=None, entity_id=None, expires_at=None, effective_at=None,
                )
            ],
            check_permission=False,
        )
    db.commit()
    db.refresh(account)
    return envelope(BillingAccountRead.model_validate(account).model_dump(by_alias=True))


@router.get("/billing-accounts/{account_id}", response_model=BillingAccountEnvelope, response_model_exclude_unset=True)
def get_billing_account(
    account_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    account = get_active_account_or_404(db, tenant_id, account_id)
    return envelope(BillingAccountRead.model_validate(account).model_dump(by_alias=True))


@router.patch("/billing-accounts/{account_id}", response_model=BillingAccountEnvelope, response_model_exclude_unset=True)
def update_billing_account(
    account_id: str,
    payload: UpdateBillingAccountRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """The unit, the unit type and the owner are all immutable: each of them
    decides what may be posted here and who it belongs to, so changing one would
    silently reinterpret every entry already recorded. A wrong account is closed
    and a right one opened."""
    tenant_id = actor.tenant_id
    require_permission(actor, "billing_account.manage")
    account = get_active_account_or_404(db, tenant_id, account_id)
    updates = payload.model_dump(exclude_unset=True)
    if "credit_limit" in updates and updates["credit_limit"] is not None:
        # narrowing the line below what is already drawn would strand the
        # account outside its own guard
        if float(account.balance or 0) < -float(updates["credit_limit"]) - CENT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{account.account_code} is already drawn to {float(account.balance):.2f}; "
                    "settle it before lowering the credit limit"
                ),
            )
    if "custom_fields" in updates:
        account.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    return envelope(BillingAccountRead.model_validate(account).model_dump(by_alias=True))


@router.delete("/billing-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_billing_account(
    account_id: str,
    payload: DeleteBillingAccountRequest | None = None,
    actor: Annotated[Actor, Depends(get_actor)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """An account still holding a balance cannot be hidden — the money or the
    points would still be owed to someone nobody can see."""
    require_permission(actor, "billing_account.manage")
    account = get_scoped_or_404(db, BillingAccount, actor.tenant_id, account_id)
    if account.deleted_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if abs(float(account.balance or 0)) > CENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{account.account_code} still holds {float(account.balance):.2f} {account.unit} — "
                "clear the balance before deleting it"
            ),
        )
    account.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/billing-accounts/{account_id}/restore",
    response_model=BillingAccountEnvelope,
    response_model_exclude_unset=True,
)
def restore_billing_account(
    account_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "billing_account.manage")
    account = get_scoped_or_404(db, BillingAccount, actor.tenant_id, account_id)
    if account.deleted_at is not None:
        account.deleted_at = None
        db.commit()
        db.refresh(account)
    return envelope(BillingAccountRead.model_validate(account).model_dump(by_alias=True))


@router.get(
    "/billing-accounts/{account_id}/detail",
    response_model=BillingAccountDetailEnvelope,
    response_model_exclude_unset=True,
)
def get_billing_account_detail(
    account_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    entry_limit: Annotated[int, Query(ge=1, le=200)] = 50,
    include_deleted: bool = False,
):
    account = get_scoped_or_404(db, BillingAccount, tenant_id, account_id)
    if not include_deleted:
        ensure_document_not_deleted(account)
    entries = list(
        db.scalars(
            select(BillingAccountEntry)
            .where(
                BillingAccountEntry.tenant_id == tenant_id,
                BillingAccountEntry.billing_account_id == account.id,
            )
            .order_by(BillingAccountEntry.effective_at.desc(), BillingAccountEntry.id.desc())
            .limit(entry_limit)
        ).all()
    )
    expiring = (
        expiring_account_entries(db, tenant_id, account, datetime.now(timezone.utc))
        if account.unit_type == "points"
        else []
    )
    balance = float(account.balance or 0)
    credit_limit = float(account.credit_limit or 0)
    detail = BillingAccountDetailRead(
        account=BillingAccountRead.model_validate(account),
        entries=[BillingAccountEntryRead.model_validate(row) for row in entries],
        balance=round(balance, 2),
        credit_limit=round(credit_limit, 2),
        available_amount=round(balance + credit_limit, 2),
        expiring_amount=round(float(sum(float(row.amount) for row in expiring)), 2),
        expiring_entry_count=len(expiring),
    )
    return envelope(detail.model_dump(by_alias=True))


@router.post(
    "/billing-accounts/{account_id}/entries",
    response_model=PostBillingAccountEntriesEnvelope,
    response_model_exclude_unset=True,
)
def post_billing_account_entries(
    account_id: str,
    payload: PostBillingAccountEntriesRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """Record movement on an account — the twin of the purchase order's receive
    endpoint and the payment's apply endpoint.

    What the server guarantees: the balance never falls below the credit line,
    a frozen account takes nothing, the reason is a word this workspace uses,
    and a retry with the same key posts once. What it does NOT do is decide how
    many points a purchase earns or what they are worth — those rules live in
    the tenant's workflow definition, and nothing here converts between units.
    """
    tenant_id = actor.tenant_id
    account = get_active_account_or_404(db, tenant_id, account_id)
    if payload.idempotency_key:
        replay = account_entries_replay(db, tenant_id, account.id, payload.idempotency_key)
        if replay:
            balance = float(account.balance or 0)
            return envelope(
                PostBillingAccountEntriesResult(
                    entries=[BillingAccountEntryRead.model_validate(row) for row in replay],
                    balance=round(balance, 2),
                    available_amount=round(balance + float(account.credit_limit or 0), 2),
                    replayed=True,
                ).model_dump(by_alias=True)
            )
    written = post_account_entries(
        db, actor, account, payload.lines, idempotency_key=payload.idempotency_key
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = account_entries_replay(db, tenant_id, account.id, payload.idempotency_key or "")
        if not replay:
            raise
        db.refresh(account)
        balance = float(account.balance or 0)
        return envelope(
            PostBillingAccountEntriesResult(
                entries=[BillingAccountEntryRead.model_validate(row) for row in replay],
                balance=round(balance, 2),
                available_amount=round(balance + float(account.credit_limit or 0), 2),
                replayed=True,
            ).model_dump(by_alias=True)
        )
    db.refresh(account)
    for entry in written:
        db.refresh(entry)
    balance = float(account.balance or 0)
    return envelope(
        PostBillingAccountEntriesResult(
            entries=[BillingAccountEntryRead.model_validate(row) for row in written],
            balance=round(balance, 2),
            available_amount=round(balance + float(account.credit_limit or 0), 2),
        ).model_dump(by_alias=True)
    )


@router.get(
    "/billing-accounts/{account_id}/expiring",
    response_model=ExpiringBillingAccountEntriesEnvelope,
    response_model_exclude_unset=True,
)
def get_expiring_billing_account_entries(
    account_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    before: datetime | None = None,
):
    """The expiry sweep's queue: earn entries past `before` that nothing has
    expired yet.

    `expiring_amount` is the sum of those batches, NOT the amount that should be
    expired. How much of each batch survived redemption depends on whether the
    workspace draws points FIFO, LIFO or by pool — that is policy, it lives in
    the workflow definition, and the agent applies it."""
    account = get_active_account_or_404(db, tenant_id, account_id)
    cutoff = before or datetime.now(timezone.utc)
    entries = expiring_account_entries(db, tenant_id, account, cutoff)
    result = ExpiringBillingAccountEntriesRead(
        billing_account_id=account.id,
        unit=account.unit,
        balance=round(float(account.balance or 0), 2),
        before=cutoff,
        entries=[BillingAccountEntryRead.model_validate(row) for row in entries],
        expiring_amount=round(float(sum(float(row.amount) for row in entries)), 2),
    )
    return envelope(result.model_dump(by_alias=True))


@router.get(
    "/billing-account-entries",
    response_model=BillingAccountEntryListEnvelope,
    response_model_exclude_unset=True,
)
def list_billing_account_entries(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    billing_account_id: str | None = None,
    reason: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Read-only: the ledger has no update or delete. Corrections are
    counter-entries posted through POST /billing-accounts/{id}/entries."""
    return list_rows(
        db, select(BillingAccountEntry).where(BillingAccountEntry.tenant_id == tenant_id),
        filters={
            BillingAccountEntry.billing_account_id: billing_account_id,
            BillingAccountEntry.reason: reason,
            BillingAccountEntry.entity_type: entity_type,
            BillingAccountEntry.entity_id: entity_id,
        },
        order_by=(BillingAccountEntry.effective_at.desc(), BillingAccountEntry.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=BillingAccountEntryRead,
    )


# --- payments and 核销 ------------------------------------------------------
#
# The settlement half. A payment is money that moved; an application is one act
# of saying which document that money settles. The ledger is append-only, so a
# mistake is corrected by a counter-entry — never by editing history.
#
# The line this draws is deliberate and matches the receive endpoint's: AMOUNTS
# are guarded by the server (nothing may be over-applied, in either direction,
# in either currency), STATUS is not (state names are tenant-editable, so the
# server cannot know which of them mean "settled" — that judgment is the
# agent's, reading the workflow definition).

# money comparisons are on values the database stores as numeric(12,2); half a
# cent of slack absorbs float round-tripping without ever admitting a real
# over-application
CENT = 0.005


@dataclass(frozen=True)
class SettlementTarget:
    """One kind of document a payment may settle. The parallel of
    TODO_TARGET_MODELS for the money side.

    `column` is the ledger's own foreign key for this kind — the API names a
    target uniformly (`applied_to_type` + `applied_to_id`) while storage keeps
    a column per kind, so this is where the two meet.

    `running_column` and `bounds` exist because a billing account does not fit
    the shape the other three share. A claim has a ceiling — you cannot settle
    more of an invoice than it bills — and a floor of zero. A DEPOSIT has
    neither: paying money into an account is not settling a claim, so there is
    nothing to exceed, and the balance may legitimately be negative down to the
    credit line. Rather than special-case the account inside the guard, each
    kind states its own running column and its own two bounds."""

    model: type
    label: str
    column: str
    # row -> which payment direction may settle it. A function, not a constant,
    # because an invoice's own direction decides it — and for an account, both
    # directions are legal (a deposit in, a refund out).
    settling_direction: object
    describe: object
    # the row attribute the running total lives in
    running_column: str = "applied_amount"
    # (db, row) -> (floor, ceiling|None); None means unbounded above
    bounds: object = None
    # how a positive application moves the running column: +1 everywhere except
    # an account, where an outbound payment REDUCES the balance
    effect_sign: object = None


def _expense_claim_total(db: Session, claim: ExpenseClaim) -> float:
    """A claim has no total column — the sum of its live items IS the claim,
    which is also what /detail reports."""
    return float(
        db.scalar(
            select(func.coalesce(func.sum(ExpenseItem.amount), 0)).where(
                ExpenseItem.tenant_id == claim.tenant_id,
                ExpenseItem.claim_id == claim.id,
                ExpenseItem.deleted_at.is_(None),
            )
        )
        or 0
    )


SETTLEMENT_TARGETS: dict[str, SettlementTarget] = {
    "invoice": SettlementTarget(
        Invoice,
        "invoice",
        "invoice_id",
        # a customer invoice is settled by money coming IN; a vendor bill by
        # money going OUT
        lambda row: "inbound" if row.direction == "sales" else "outbound",
        lambda row: f"{row.invoice_no} {row.title}",
        bounds=lambda db, row: (
            0.0,
            invoice_billed_total(row, live_invoice_items(db, row.tenant_id, row.id)),
        ),
    ),
    "expense_claim": SettlementTarget(
        ExpenseClaim,
        "expense claim",
        "expense_claim_id",
        # we always pay the employee, never collect from them: a refund of an
        # overpaid claim is a counter-entry on the original payment
        lambda row: "outbound",
        lambda row: row.title,
        bounds=lambda db, row: (0.0, _expense_claim_total(db, row)),
    ),
    "billing_account": SettlementTarget(
        BillingAccount,
        "billing account",
        "billing_account_id",
        # both directions are legal here, unlike every other target: money goes
        # IN as a deposit and OUT as a refund of what was deposited
        lambda row: None,
        lambda row: f"{row.account_code} {row.name}",
        running_column="balance",
        # no ceiling — a deposit is not a claim, so there is nothing to exceed
        bounds=lambda db, row: (-float(row.credit_limit or 0), None),
        # an outbound payment applied here REDUCES the balance
        effect_sign=lambda payment: 1.0 if payment.direction == "inbound" else -1.0,
    ),
    "payment": SettlementTarget(
        Payment,
        "payment",
        "to_payment_id",
        # netting (OFBiz toPaymentId): a refund going out settles part of a
        # receipt that came in, and vice versa
        lambda row: "outbound" if row.direction == "inbound" else "inbound",
        lambda row: f"{row.payment_no} {row.counterparty_name_snapshot or ''}".strip(),
        bounds=lambda db, row: (0.0, float(row.amount)),
    ),
}


def target_effect_sign(spec: SettlementTarget, payment: Payment) -> float:
    return spec.effect_sign(payment) if spec.effect_sign else 1.0


def applications_for_target(db: Session, tenant_id: str, target_type: str, target_id: str):
    """Every ledger row against one document, oldest first — through that
    kind's own foreign key."""
    column = getattr(PaymentApplication, SETTLEMENT_TARGETS[target_type].column)
    return list(
        db.scalars(
            select(PaymentApplication)
            .where(PaymentApplication.tenant_id == tenant_id, column == target_id)
            .order_by(PaymentApplication.applied_at.asc(), PaymentApplication.id.asc())
        ).all()
    )


def resolve_settlement_target(db: Session, tenant_id: str, target_type: str, target_id: str):
    """The live document an application points at. A soft-deleted one is absent:
    settling against a deleted document would put money somewhere nobody can
    see."""
    spec = SETTLEMENT_TARGETS[target_type]
    row = get_scoped_or_404(db, spec.model, tenant_id, target_id)
    if getattr(row, "deleted_at", None) is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{spec.label} {target_id} not found",
        )
    return row


def settlement_target_read(db: Session, target_type: str, row) -> SettlementTargetRead:
    spec = SETTLEMENT_TARGETS[target_type]
    floor, ceiling = spec.bounds(db, row)
    running = float(getattr(row, spec.running_column) or 0)
    common = {
        "applied_to_type": target_type,
        "applied_to_id": row.id,
        "label": spec.describe(row),
        "currency": row.unit if target_type == "billing_account" else row.currency,
    }
    if ceiling is None:
        # an account: a balance and what may still be spent, not a claim
        return SettlementTargetRead(
            **common,
            balance=round(running, 2),
            available_amount=round(running - floor, 2),
        )
    return SettlementTargetRead(
        **common,
        settleable_total=round(ceiling, 2),
        applied_amount=round(running, 2),
        outstanding_amount=round(ceiling - running, 2),
    )


def _applications_result(
    db: Session, payment: Payment, applications: list[PaymentApplication], *, replayed: bool
) -> dict:
    targets: dict[tuple[str, str], object] = {}
    for row in applications:
        key = (row.applied_to_type, row.applied_to_id)
        if key not in targets:
            targets[key] = resolve_settlement_target(
                db, payment.tenant_id, row.applied_to_type, row.applied_to_id
            )
    applied = float(payment.applied_amount or 0)
    result = ApplyPaymentResult(
        applications=[PaymentApplicationRead.model_validate(row) for row in applications],
        applied_amount=round(applied, 2),
        unapplied_amount=round(float(payment.amount) - applied, 2),
        targets=[
            settlement_target_read(db, target_type, row)
            for (target_type, _id), row in targets.items()
        ],
        replayed=replayed,
    )
    return envelope(result.model_dump(by_alias=True))


PAYMENT_COUNTERPARTY_FIELDS = ("customer_id", "vendor_id", "payee_employee_id")
PAYMENT_COUNTERPARTY_MODELS = {
    "customer_id": Customer,
    "vendor_id": Vendor,
    "payee_employee_id": Employee,
}


def resolve_payment_counterparty(db: Session, tenant_id: str, values: dict) -> tuple[dict, str | None]:
    """Exactly one counterparty, and it must exist here. A payment to nobody
    cannot be applied to anything, and one naming two parties cannot be
    reconciled against either."""
    named = [field for field in PAYMENT_COUNTERPARTY_FIELDS if values.get(field)]
    if len(named) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "a payment names exactly one counterparty: customer_id (收款), "
                "vendor_id (付供应商) or payee_employee_id (付员工/报销)"
            ),
        )
    field = named[0]
    party = get_scoped_or_404(db, PAYMENT_COUNTERPARTY_MODELS[field], tenant_id, values[field])
    resolved = {other: None for other in PAYMENT_COUNTERPARTY_FIELDS if other != field}
    resolved[field] = party.id
    return resolved, party.name


@router.get("/payments", response_model=PaymentListEnvelope, response_model_exclude_unset=True)
def list_payments(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    direction: str | None = None,
    customer_id: str | None = None,
    vendor_id: str | None = None,
    payee_employee_id: str | None = None,
    employee_id: str | None = None,
    payment_no: str | None = None,
    reference_no: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    unapplied: bool = False,
    without_open_todo: bool = False,
    keyword: str | None = None,
    include_deleted: bool = False,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """`unapplied=true` is the 认领队列: money that arrived or went out and has
    not been matched to a document yet. On the inbound side that is 预收款 plus
    every bank line nobody has identified; on the outbound side, 预付款."""
    tenant_id = actor.tenant_id
    validate_status_filter(db, tenant_id, "payment", status_filter)
    stmt = select(Payment).where(Payment.tenant_id == tenant_id)
    # a payment settling someone else's payslip carries their net pay
    stmt = hide_payroll_payments(stmt, actor)
    if not include_deleted:
        stmt = stmt.where(Payment.deleted_at.is_(None))
    if unapplied:
        stmt = stmt.where(Payment.amount - func.coalesce(Payment.applied_amount, 0) > 0.005)
    if without_open_todo:
        stmt = exclude_rows_with_open_todo(stmt, Payment, tenant_id, "payment")
    return list_rows(
        db, stmt,
        filters={
            Payment.direction: direction,
            Payment.customer_id: customer_id,
            Payment.vendor_id: vendor_id,
            Payment.payee_employee_id: payee_employee_id,
            Payment.employee_id: employee_id,
            Payment.payment_no: payment_no,
            Payment.reference_no: reference_no,
            Payment.status: status_filter,
        },
        keyword=keyword,
        keyword_columns=(
            Payment.payment_no,
            Payment.reference_no,
            Payment.counterparty_name_snapshot,
            Payment.remarks,
        ),
        order_by=(Payment.created_at.desc(), Payment.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=PaymentRead,
    )


@router.post(
    "/payments",
    status_code=status.HTTP_201_CREATED,
    response_model=PaymentEnvelope,
    response_model_exclude_unset=True,
)
def create_payment(
    payload: CreatePaymentRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """An outbound payment normally starts at `draft` and is walked through
    付款审批; an inbound receipt is money that already arrived, so it is created
    directly in whatever state says so — create accepts any state of the
    tenant's machine, as every builtin does."""
    tenant_id = actor.tenant_id
    require_permission(actor, "payment.record")
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    counterparty, party_name = resolve_payment_counterparty(db, tenant_id, payload.model_dump())
    if payload.payment_method is not None:
        require_type_option(db, tenant_id, "payment_method", payload.payment_method)
    if payload.attachment_id:
        get_scoped_or_404(db, Attachment, tenant_id, payload.attachment_id)
    require_machine_state(db, tenant_id, Payment, payload.status)
    payment_no = payload.payment_no or allocate_number(db, Payment, tenant_id)
    payment = Payment(
        tenant_id=tenant_id,
        payment_no=payment_no,
        direction=payload.direction,
        payment_method=payload.payment_method,
        employee_id=payload.employee_id,
        counterparty_name_snapshot=payload.counterparty_name_snapshot or party_name,
        payment_date=payload.payment_date,
        amount=payload.amount,
        currency=payload.currency,
        bank_account=payload.bank_account,
        counterparty_account=payload.counterparty_account,
        reference_no=payload.reference_no,
        attachment_id=payload.attachment_id,
        status=payload.status,
        remarks=payload.remarks,
        source_report_text=payload.source_report_text,
        custom_fields_jsonb=payload.custom_fields,
        **counterparty,
    )
    db.add(payment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"payment_no {payment_no!r} already exists in this workspace",
        )
    db.refresh(payment)
    return envelope(PaymentRead.model_validate(payment).model_dump(by_alias=True))


@router.get("/payments/{payment_id}", response_model=PaymentEnvelope, response_model_exclude_unset=True)
def get_payment(
    payment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    payment = get_active_document_or_404(db, Payment, actor.tenant_id, payment_id)
    ensure_payment_visible(db, actor, payment)
    return envelope(PaymentRead.model_validate(payment).model_dump(by_alias=True))


@router.patch("/payments/{payment_id}", response_model=PaymentEnvelope, response_model_exclude_unset=True)
def update_payment(
    payment_id: str,
    payload: UpdatePaymentRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    payment = get_active_document_or_404(db, Payment, tenant_id, payment_id)
    # A payout settling someone's payslip is their net pay: same 404 the read
    # gate gives. Checked before the capability so a PATCH cannot confirm one
    # exists, and so the two doors give the same answer.
    ensure_payment_visible(db, actor, payment)
    updates = payload.model_dump(exclude_unset=True)
    # Same split as the invoice above: the flow owns `status`, the filer owns
    # everything else. `apply_status_change` still requires `payment.advance`,
    # the hosted write boundary and a legal transition.
    if any(field != "status" for field in updates):
        require_permission(actor, "payment.record")
    # the amount is what an approver approved and what the ledger measures
    # against; restating it after the fact is a different payment
    ensure_money_fields_editable(db, payment, updates, ("amount", "currency"))
    if "payment_method" in updates and updates["payment_method"] is not None:
        require_type_option(db, tenant_id, "payment_method", updates["payment_method"])
    if any(field in updates for field in PAYMENT_COUNTERPARTY_FIELDS):
        current = {field: getattr(payment, field) for field in PAYMENT_COUNTERPARTY_FIELDS}
        # a stated counterparty REPLACES the old one rather than adding a
        # second: naming a vendor on a payment that named a customer is a
        # correction, not a contradiction
        stated = {field: updates[field] for field in PAYMENT_COUNTERPARTY_FIELDS if field in updates}
        if any(stated.values()):
            current = {field: None for field in PAYMENT_COUNTERPARTY_FIELDS}
        counterparty, party_name = resolve_payment_counterparty(db, tenant_id, {**current, **stated})
        updates.update(counterparty)
        updates.setdefault("counterparty_name_snapshot", party_name)
    if updates.get("attachment_id"):
        get_scoped_or_404(db, Attachment, tenant_id, updates["attachment_id"])
    if "amount" in updates and updates["amount"] != float(payment.amount):
        # the ledger is a running sum of this number; letting it drop below what
        # is already applied would make the payment owe money it never held
        applied = float(payment.applied_amount or 0)
        if updates["amount"] < applied - CENT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{applied:.2f} is already applied from this payment — reverse the "
                    "applications before reducing its amount"
                ),
            )
    if "status" in updates and updates["status"] != payment.status:
        apply_status_change(db, actor, payment, updates["status"])
        if updates["status"] == "paid" and payment.paid_at is None:
            payment.paid_at = datetime.now(timezone.utc)
    if "custom_fields" in updates:
        payment.custom_fields_jsonb = updates.pop("custom_fields")
    for field, value in updates.items():
        setattr(payment, field, value)
    db.commit()
    db.refresh(payment)
    return envelope(PaymentRead.model_validate(payment).model_dump(by_alias=True))


@router.delete("/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment(
    payment_id: str,
    payload: DeletePaymentRequest | None = None,
    actor: Annotated[Actor, Depends(get_actor)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """A payment carrying applications cannot be hidden: the documents it
    settled would keep a running total sourced from a row nobody can see.
    Reverse the applications first."""
    payment = get_scoped_or_404(db, Payment, actor.tenant_id, payment_id)
    if payment.deleted_at is None and abs(float(payment.applied_amount or 0)) > CENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{float(payment.applied_amount):.2f} of this payment is applied to documents — "
                "reverse those applications before deleting it"
            ),
        )
    return delete_document(db, actor, Payment, payment_id, payload)


@router.post("/payments/{payment_id}/restore", response_model=PaymentEnvelope, response_model_exclude_unset=True)
def restore_payment(
    payment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return restore_document(db, actor, Payment, payment_id)


@router.post("/payments/{payment_id}/submit", response_model=PaymentEnvelope, response_model_exclude_unset=True)
def submit_payment(
    payment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    return submit_document(db, actor, Payment, payment_id)


@router.get(
    "/payments/{payment_id}/detail",
    response_model=PaymentDetailEnvelope,
    response_model_exclude_unset=True,
)
def get_payment_detail(
    payment_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    include_deleted: bool = False,
):
    tenant_id = actor.tenant_id
    payment = get_scoped_or_404(db, Payment, tenant_id, payment_id)
    ensure_payment_visible(db, actor, payment)
    if not include_deleted:
        ensure_document_not_deleted(payment)
    applications = list(
        db.scalars(
            select(PaymentApplication)
            .where(
                PaymentApplication.tenant_id == tenant_id,
                PaymentApplication.payment_id == payment.id,
            )
            .order_by(PaymentApplication.applied_at.asc(), PaymentApplication.id.asc())
        ).all()
    )
    summaries: dict[tuple[str, str | None], SettlementTargetRead] = {}
    for row in applications:
        key = (row.applied_to_type, row.applied_to_id)
        if key in summaries:
            continue
        try:
            target = resolve_settlement_target(db, tenant_id, row.applied_to_type, row.applied_to_id)
        except HTTPException:
            # a target that has since been soft-deleted: the ledger row stands
            # as history, it just has nothing left to summarize
            continue
        summaries[key] = settlement_target_read(db, row.applied_to_type, target)
    applied = float(payment.applied_amount or 0)
    detail = PaymentDetailRead(
        payment=PaymentRead.model_validate(payment),
        approval_records=[
            ApprovalRecordRead.model_validate(record)
            for record in document_approvals(db, tenant_id, "payment", payment.id)
        ],
        applications=[
            PaymentApplicationDetailRead(
                **PaymentApplicationRead.model_validate(row).model_dump(),
                target=summaries.get((row.applied_to_type, row.applied_to_id)),
            )
            for row in applications
        ],
        applied_amount=round(applied, 2),
        unapplied_amount=round(float(payment.amount) - applied, 2),
    )
    return envelope(detail.model_dump(by_alias=True))


@router.post(
    "/payments/{payment_id}/apply",
    response_model=ApplyPaymentEnvelope,
    response_model_exclude_unset=True,
)
def apply_payment(
    payment_id: str,
    payload: ApplyPaymentRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """核销: record which documents this payment settles.

    Facts only, no status magic — the twin of the purchase order's receive
    endpoint. Each line appends an immutable ledger row and moves the running
    `applied_amount` on both sides; the flow agent moves statuses when the facts
    support it. Reversing an application is a line with a negative amount, never
    a delete.

    Deliberately NOT gated on either document's status, for the same reason
    receiving is not: the state names are the tenant's own, so the server cannot
    know which of them mean "payable". What the server does guarantee is that no
    more money is applied than exists on either side, that the direction and the
    currency agree, and that a retry with the same idempotency key applies once.
    """
    tenant_id = actor.tenant_id
    require_permission(actor, "payment.apply")
    payment = get_active_document_or_404(db, Payment, tenant_id, payment_id)

    if payload.idempotency_key:
        replay = list(
            db.scalars(
                select(PaymentApplication)
                .where(
                    PaymentApplication.tenant_id == tenant_id,
                    PaymentApplication.payment_id == payment.id,
                    PaymentApplication.idempotency_key == payload.idempotency_key,
                )
                .order_by(
                    PaymentApplication.idempotency_seq.asc().nulls_first(),
                    PaymentApplication.id.asc(),
                )
            ).all()
        )
        if replay:
            return _applications_result(db, payment, replay, replayed=True)

    # Pass 1 — resolve and validate every line before writing any of them, so a
    # request whose lines individually fit but together overflow is refused
    # whole rather than half-applied.
    resolved: list[tuple[object, str, object]] = []
    target_rows: dict[tuple[str, str], object] = {}
    target_deltas: dict[tuple[str, str], float] = {}
    for line in payload.lines:
        if abs(line.amount_applied) < CENT:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="amount_applied must not be zero — an application records money moving",
            )
        if line.applied_to_type == "payment" and line.applied_to_id == payment.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="a payment cannot settle itself",
            )
        key = (line.applied_to_type, line.applied_to_id)
        row = target_rows.get(key)
        if row is None:
            row = resolve_settlement_target(db, tenant_id, line.applied_to_type, line.applied_to_id)
            target_rows[key] = row
        spec = SETTLEMENT_TARGETS[line.applied_to_type]
        wanted = spec.settling_direction(row)
        # None = both directions are legal (an account takes deposits and gives
        # refunds); every other target is settled from exactly one side
        if wanted is not None and payment.direction != wanted:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"a {payment.direction!r} payment cannot settle this {spec.label} — "
                    f"it is settled by an {wanted!r} payment"
                ),
            )
        if line.applied_to_type == "billing_account":
            # money must never land in a points balance. This is the whole
            # reason unit_type is a constrained column rather than a vocabulary
            # the tenant could extend.
            if row.unit_type != "currency":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"{row.account_code} counts {row.unit}, not money — a payment cannot be "
                        "applied to a points account. Record the redemption as an account entry "
                        "and price it on the document itself"
                    ),
                )
            if row.status != "active":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"account {row.account_code} is {row.status} and takes no movement",
                )
        target_currency = row.unit if line.applied_to_type == "billing_account" else row.currency
        if target_currency != payment.currency:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"currency mismatch: the payment is in {payment.currency} and this "
                    f"{spec.label} is in {target_currency}. Cross-currency settlement needs an "
                    "explicit rate and is not supported yet — record the exchange separately"
                ),
            )
        if line.invoice_item_id is not None:
            if line.applied_to_type != "invoice":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="invoice_item_id only applies when settling an invoice",
                )
            item = get_live_or_404(db, InvoiceItem, tenant_id, line.invoice_item_id)
            if item.invoice_id != row.id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="that invoice line belongs to a different invoice",
                )
        target_deltas[key] = target_deltas.get(key, 0.0) + line.amount_applied
        resolved.append((row, line.applied_to_type, line))

    payment_total = float(payment.amount)
    payment_applied = float(payment.applied_amount or 0)
    payment_after = payment_applied + sum(target_deltas.values())
    if payment_after < -CENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"reversing more than was applied: {payment.payment_no} has "
                f"{payment_applied:.2f} applied"
            ),
        )
    if payment_after > payment_total + CENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"over-applying {payment.payment_no}: {payment_total - payment_applied:.2f} "
                f"of {payment_total:.2f} is still unapplied"
            ),
        )

    for key, delta in target_deltas.items():
        target_type, _target_id = key
        row = target_rows[key]
        spec = SETTLEMENT_TARGETS[target_type]
        floor, ceiling = spec.bounds(db, row)
        running = float(getattr(row, spec.running_column) or 0)
        after = running + delta * target_effect_sign(spec, payment)
        if after < floor - CENT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"this {spec.label} only has {running - floor:.2f} available"
                    if ceiling is None
                    else (
                        f"reversing more than was applied to this {spec.label}: "
                        f"{running:.2f} is applied"
                    )
                ),
            )
        if ceiling is not None and after > ceiling + CENT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"over-applying this {spec.label}: {ceiling - running:.2f} of "
                    f"{ceiling:.2f} is still outstanding"
                ),
            )

    # Pass 2 — write. Every row is append-only; the running sums are what the
    # work queues and /detail read.
    written: list[PaymentApplication] = []
    for seq, (row, target_type, line) in enumerate(resolved):
        application = PaymentApplication(
            tenant_id=tenant_id,
            payment_id=payment.id,
            # the API names the target uniformly; storage keeps a real foreign
            # key per kind, and this is the one line where the two meet
            **{SETTLEMENT_TARGETS[target_type].column: row.id},
            invoice_item_id=line.invoice_item_id,
            amount_applied=line.amount_applied,
            note=line.note,
            idempotency_key=payload.idempotency_key,
            # the key names the call; this is the row's place in it
            idempotency_seq=seq if payload.idempotency_key else None,
            created_by=attributed(actor, None),
        )
        db.add(application)
        written.append(application)
    for key, delta in target_deltas.items():
        target_type, _target_id = key
        row = target_rows[key]
        spec = SETTLEMENT_TARGETS[target_type]
        if target_type == "billing_account":
            # An account's balance only ever moves through its own ledger, so
            # that the balance stays the sum of the entries no matter which
            # endpoint the money came in through — the same discipline the
            # receive endpoint keeps with the inventory ledger. `check_permission`
            # is off because `payment.apply` is the grant that authorized this
            # call; requiring billing_account.post as well would mean nobody
            # could deposit a customer's cheque without also being able to mint
            # points.
            signed = delta * target_effect_sign(spec, payment)
            post_account_entries(
                db, actor, row,
                [
                    SimpleNamespace(
                        amount=signed,
                        reason="deposit" if signed > 0 else "refund",
                        description=f"{payment.payment_no} 核销",
                        entity_type="payment",
                        entity_id=payment.id,
                        expires_at=None,
                        effective_at=None,
                    )
                ],
                check_permission=False,
            )
            continue
        setattr(
            row,
            spec.running_column,
            round(float(getattr(row, spec.running_column) or 0) + delta, 2),
        )
    payment.applied_amount = round(payment_after, 2)
    record_audit(
        db,
        tenant_id=tenant_id,
        action="payment.applied",
        entity_type="payment",
        entity_id=payment.id,
        actor=actor.label,
        detail={
            "payment_no": payment.payment_no,
            "lines": [
                {
                    "applied_to_type": target_type,
                    "applied_to_id": row.id,
                    "amount_applied": line.amount_applied,
                }
                for row, target_type, line in resolved
            ],
            "applied_amount": payment.applied_amount,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # the partial unique index caught a concurrent call with the same key;
        # the winner's rows are the answer
        replay = list(
            db.scalars(
                select(PaymentApplication)
                .where(
                    PaymentApplication.tenant_id == tenant_id,
                    PaymentApplication.payment_id == payment.id,
                    PaymentApplication.idempotency_key == payload.idempotency_key,
                )
                .order_by(
                    PaymentApplication.idempotency_seq.asc().nulls_first(),
                    PaymentApplication.id.asc(),
                )
            ).all()
        )
        if not replay:
            raise
        db.refresh(payment)
        return _applications_result(db, payment, replay, replayed=True)
    for application in written:
        db.refresh(application)
    db.refresh(payment)
    return _applications_result(db, payment, written, replayed=False)


@router.get(
    "/payment-applications",
    response_model=PaymentApplicationListEnvelope,
    response_model_exclude_unset=True,
)
def list_payment_applications(
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
    payment_id: str | None = None,
    applied_to_type: str | None = None,
    applied_to_id: str | None = None,
    invoice_item_id: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Read-only: the ledger has no update or delete. Corrections are
    counter-entries recorded through POST /payments/{id}/apply.

    `applied_to_type`/`applied_to_id` are the uniform way to name a target, the
    same pair the apply endpoint takes; they resolve to that kind's own foreign
    key. Naming an id without its type would have to search three columns, so
    it is refused rather than guessed at."""
    tenant_id = actor.tenant_id
    stmt = select(PaymentApplication).where(PaymentApplication.tenant_id == tenant_id)
    # an application naming a payslip reveals both the person and the amount
    payroll_gate = visible_payroll_filter(actor)
    if payroll_gate is not None:
        stmt = stmt.where(
            ~select(Invoice.id)
            .where(
                Invoice.id == PaymentApplication.invoice_id,
                Invoice.direction == "payroll",
                ~payroll_gate,
            )
            .exists()
        )
    if applied_to_type is not None:
        if applied_to_type not in SETTLEMENT_TARGETS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"unknown applied_to_type {applied_to_type!r} — "
                    f"one of {', '.join(sorted(SETTLEMENT_TARGETS))}"
                ),
            )
        column = getattr(PaymentApplication, SETTLEMENT_TARGETS[applied_to_type].column)
        stmt = stmt.where(column.is_not(None))
        if applied_to_id is not None:
            stmt = stmt.where(column == applied_to_id)
    elif applied_to_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="applied_to_id needs applied_to_type to say which kind of document it names",
        )
    return list_rows(
        db, stmt,
        filters={
            PaymentApplication.payment_id: payment_id,
            PaymentApplication.invoice_item_id: invoice_item_id,
        },
        order_by=(PaymentApplication.applied_at.desc(), PaymentApplication.id.desc()),
        pagination=page_only_pagination(page, size),
        read_model=PaymentApplicationRead,
    )


@router.get(
    "/approval-records",
    response_model=ApprovalRecordListEnvelope,
    response_model_exclude_unset=True,
)
def list_approval_records(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    entity_type: str | None = None,
    entity_id: str | None = None,
    action_filter: Annotated[str | None, Query(alias="action")] = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    pagination = requested_pagination(page, size)
    return list_rows(
        db, select(ApprovalRecord).where(ApprovalRecord.tenant_id == tenant_id),
        filters={
            ApprovalRecord.entity_type: entity_type,
            ApprovalRecord.entity_id: entity_id,
            ApprovalRecord.action: action_filter,
        },
        keyword=keyword,
        keyword_columns=(
            ApprovalRecord.comment,
            ApprovalRecord.approver_id,
            ApprovalRecord.approver_role,
            cast(ApprovalRecord.entity_id, String),
        ),
        # Unpaged keeps the historical workflow-order contract for agent
        # clients. Console pagination is an activity feed, newest first.
        order_by=(
            (
                ApprovalRecord.round_no.asc(),
                ApprovalRecord.sequence_no.asc(),
                ApprovalRecord.acted_at.asc(),
                ApprovalRecord.id.asc(),
            )
            if pagination is None
            else (ApprovalRecord.acted_at.desc(), ApprovalRecord.id.desc())
        ),
        pagination=pagination,
        read_model=ApprovalRecordRead,
    )


TODO_TARGET_MODELS = {family.object_type: model for model, family in DOCUMENT_FAMILIES.items()}


def attach_todo_targets(db: Session, tenant_id: str, rows: list[dict]) -> None:
    """Summarize each todo's target onto the row, in a fixed number of batched
    reads regardless of how many todos there are.

    The check-in used to spend one detail call per todo to learn this much —
    the only part of it that grew with how busy the person was. Eight todos
    was eight extra agent turns at ~12s each. Here it is one grouped query per
    family present, plus one for line sums, approvals, and names.

    The summary shows the same facts the target's own detail endpoint would
    show the same caller — reads are tenant-wide by design — so it widens
    nothing.
    """
    pairs = {(row["entity_type"], row["entity_id"]) for row in rows}
    by_type: dict[str, set[str]] = {}
    for entity_type, entity_id in pairs:
        by_type.setdefault(entity_type, set()).add(entity_id)

    summaries: dict[tuple[str, str], TodoTargetSummary] = {}
    employee_ids: set[str] = set()
    approver_user_ids: set[str] = set()

    for entity_type, ids in by_type.items():
        model = TODO_TARGET_MODELS.get(entity_type)
        if model is not None:
            docs = db.scalars(
                select(model).where(model.tenant_id == tenant_id, model.id.in_(ids))
            ).all()
            for doc in docs:
                summary = TodoTargetSummary(
                    object_type=entity_type,
                    status=doc.status,
                    employee_id=doc.employee_id,
                )
                if entity_type == "timesheet_header":
                    summary.title = f"{doc.period_start} – {doc.period_end}"
                    summary.unit = "hours"
                elif entity_type in ("expense_claim", "purchase_request"):
                    summary.title = doc.title
                    summary.unit = "amount"
                    summary.currency = doc.currency
                elif entity_type == "sales_quotation":
                    summary.title = f"{doc.quote_number} {doc.title or ''}".strip()
                    summary.customer_name = doc.customer_name_snapshot
                    summary.amount = float(doc.total_amount) if doc.total_amount is not None else None
                    summary.unit = "amount"
                    summary.currency = doc.currency
                elif entity_type == "sales_order":
                    summary.title = f"{doc.order_no} {doc.title or ''}".strip()
                    summary.customer_name = doc.customer_name_snapshot
                    summary.amount = float(doc.total_amount) if doc.total_amount is not None else None
                    summary.unit = "amount"
                    summary.currency = doc.currency
                if doc.employee_id:
                    employee_ids.add(doc.employee_id)
                # Deliberately not filtered out of the query above: a todo whose
                # target was deleted still needs describing, and dropping the
                # row here would report it as `missing` — the same word used for
                # an id that names nothing, which is a different problem with a
                # different fix.
                summary.deleted = doc.deleted_at is not None
                summaries[(entity_type, doc.id)] = summary
        elif entity_type in ("business_object", "approval_target"):
            # `approval_target` is a BusinessObject too — the same row reached
            # by a different verb. It was absent from this branch, so every
            # todo pointing at one came back `missing: true` while the row sat
            # there readable. Two of the three non-document types reporting a
            # phantom integrity problem is what made `missing` unusable as the
            # signal a sweep looks for.
            for doc in db.scalars(
                select(BusinessObject).where(
                    BusinessObject.tenant_id == tenant_id, BusinessObject.id.in_(ids)
                )
            ).all():
                summaries[(entity_type, doc.id)] = TodoTargetSummary(
                    object_type=doc.object_type, title=doc.title, status=doc.status,
                    deleted=doc.deleted_at is not None,
                )
        elif entity_type == "project":
            # A project is archived rather than deleted, so `deleted` is never
            # set here; an archived one shows its status and the sweep judges
            # it the same way it judges any dead state.
            for row in db.scalars(
                select(Project).where(Project.tenant_id == tenant_id, Project.id.in_(ids))
            ).all():
                summaries[(entity_type, row.id)] = TodoTargetSummary(
                    object_type="project", title=row.project_name, status=row.status,
                )

    # line-derived amounts, one grouped query per family that stores none
    sum_specs = (
        ("timesheet_header", TimesheetEntry, TimesheetEntry.header_id, func.sum(TimesheetEntry.hours)),
        ("expense_claim", ExpenseItem, ExpenseItem.claim_id, func.sum(ExpenseItem.amount)),
        ("purchase_request", PurchaseRequestItem, PurchaseRequestItem.request_id, func.sum(PurchaseRequestItem.amount)),
        # the sales families store a header total, but nothing forces it to be
        # set — a real quotation shipped with priced lines and a null header
        # total, and the briefing could not put a number on the deal. The
        # header total wins when present; the line sum fills the gap.
        ("sales_quotation", SalesQuotationItem, SalesQuotationItem.quotation_id, func.sum(SalesQuotationItem.amount)),
        ("sales_order", SalesOrderItem, SalesOrderItem.order_id, func.sum(SalesOrderItem.amount)),
    )
    for entity_type, line_model, parent_col, total_col in sum_specs:
        ids = by_type.get(entity_type)
        if not ids:
            continue
        totals = db.execute(
            select(parent_col, total_col)
            .where(
                line_model.tenant_id == tenant_id,
                parent_col.in_(ids),
                line_model.deleted_at.is_(None),
            )
            .group_by(parent_col)
        ).all()
        for parent_id, total in totals:
            summary = summaries.get((entity_type, parent_id))
            if summary is not None and total is not None and summary.amount is None:
                summary.amount = float(total)

    # approval position: newest fact per target, plus how deep the trail is
    for entity_type, ids in by_type.items():
        records = db.scalars(
            select(ApprovalRecord)
            .where(
                ApprovalRecord.tenant_id == tenant_id,
                ApprovalRecord.entity_type == entity_type,
                ApprovalRecord.entity_id.in_(ids),
            )
            .order_by(ApprovalRecord.round_no.asc(), ApprovalRecord.sequence_no.asc())
        ).all()
        for record in records:
            summary = summaries.get((entity_type, record.entity_id))
            if summary is None:
                continue
            summary.approval_count += 1
            summary.last_approval = TodoLastApproval(
                action=record.action,
                round_no=record.round_no,
                sequence_no=record.sequence_no,
                approver_role=record.approver_role,
                comment=record.comment,
                acted_at=record.acted_at,
            )
            if record.approver_id:
                # approver_id is an employee id only when a person acted
                # directly. Real trails also carry actor labels — "user:<id>"
                # from the API layer and service labels like "workflow-admin"
                # from the flow agent — and postgres refuses to cast either to
                # uuid, so each form resolves its own way.
                label = record.approver_id
                summary.last_approval.approver_name = label  # resolved below
                if label.startswith("user:"):
                    approver_user_ids.add(label[5:])
                else:
                    try:
                        uuid.UUID(label)
                    except ValueError:
                        pass  # service label; shown as-is
                    else:
                        employee_ids.add(label)

    names = {
        employee.id: employee.name
        for employee in db.scalars(
            select(Employee).where(Employee.tenant_id == tenant_id, Employee.id.in_(employee_ids))
        ).all()
    } if employee_ids else {}
    if approver_user_ids:
        names.update({
            f"user:{user.id}": user.name or user.email
            for user in db.scalars(
                select(User).where(User.tenant_id == tenant_id, User.id.in_(approver_user_ids))
            ).all()
        })
    for summary in summaries.values():
        if summary.employee_id:
            summary.employee_name = names.get(summary.employee_id)
        if summary.last_approval is not None and summary.last_approval.approver_name:
            # employee ids resolve to names; service labels stay as they are
            summary.last_approval.approver_name = names.get(
                summary.last_approval.approver_name, summary.last_approval.approver_name
            )

    for row in rows:
        key = (row["entity_type"], row["entity_id"])
        summary = summaries.get(key)
        if summary is None:
            summary = TodoTargetSummary(object_type=row["entity_type"], missing=True)
        row["target"] = summary.model_dump()


@router.get(
    "/todos",
    response_model=TodoListEnvelope,
    response_model_exclude_unset=True,
)
def list_todos(
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
    employee_id: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    due_before: datetime | None = None,
    include: Literal["target"] | None = None,
    keyword: str | None = None,
    page: Annotated[int | None, Query(ge=1)] = None,
    size: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    stmt = select(Todo).where(Todo.tenant_id == tenant_id)
    if due_before is not None:
        stmt = stmt.where(Todo.due_at.is_not(None), Todo.due_at <= due_before)
    result = list_rows(
        db, stmt,
        filters={
            Todo.employee_id: employee_id,
            Todo.status: status_filter,
            Todo.entity_type: entity_type,
            Todo.entity_id: entity_id,
        },
        keyword=keyword,
        keyword_columns=(
            Todo.title,
            Todo.description,
            Todo.todo_type,
            cast(Todo.entity_id, String),
        ),
        order_by=(Todo.created_at.desc(), Todo.id.desc()),
        pagination=requested_pagination(page, size),
        read_model=TodoRead,
    )
    if include == "target" and result["data"]:
        attach_todo_targets(db, tenant_id, result["data"])
    else:
        # the read model dumps the field as null even when nobody asked;
        # absent beats null for a shape that predates the feature
        for row in result["data"]:
            row.pop("target", None)
    return result


@router.post(
    "/todos",
    status_code=status.HTTP_201_CREATED,
    response_model=TodoEnvelope,
    response_model_exclude_unset=True,
)
def create_todo(
    payload: CreateTodoRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    require_permission(actor, "todos.assign")
    todo, created = assign_todo(db, actor, payload)
    db.commit()
    db.refresh(todo)
    return envelope(TodoRead.model_validate(todo).model_dump(by_alias=True))


def assign_todo(db: Session, actor: Actor, payload: CreateTodoRequest) -> tuple[Todo, bool]:
    """One assignment, every guard it has to pass, in one place.

    Extracted so the bulk endpoint runs the SAME sequence rather than a second
    copy of it. A parallel implementation of a guard list is the defect this
    codebase has now corrected five times over — the copy agrees on the day it
    is written and never again, and here the list includes the hosted agent's
    write boundary, which is not a thing to re-derive.

    Returns (todo, created). `created=False` is the idempotent hit: the same
    assignment is already open and is handed back.

    Does not commit. The caller decides whether one failure ends the batch.
    """
    tenant_id = actor.tenant_id
    get_scoped_or_404(db, Employee, tenant_id, payload.employee_id)
    ensure_todo_entity_exists(db, tenant_id, payload.entity_type, payload.entity_id)
    if actor.write_scope is not None:
        require_hosted_write_scope(
            actor, payload.entity_type,
            scoped_write_target(db, tenant_id, payload.entity_type, payload.entity_id),
            ignore=("status",),
        )
    existing = db.scalar(
        select(Todo).where(
            Todo.tenant_id == tenant_id,
            Todo.employee_id == payload.employee_id,
            Todo.entity_type == payload.entity_type,
            Todo.entity_id == payload.entity_id,
            Todo.status == "open",
        )
    )
    if existing is not None:
        # Idempotency on the assignment's natural key, matching how approval
        # records answer a retry: a flow agent that crashed after writing —
        # or was fired twice for one signal — gets the assignment it already
        # made back, instead of an error it cannot distinguish from a real one.
        # A DIFFERENT assignment colliding with the open one is still a
        # conflict: the flow moved on and this caller's view is stale.
        if same_todo_assignment(existing, payload):
            return existing, False
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="open todo already exists for this entity")
    todo = Todo(
        tenant_id=tenant_id,
        employee_id=payload.employee_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        title=payload.title,
        description=payload.description,
        todo_type=payload.todo_type,
        status=payload.status,
        due_at=payload.due_at,
        created_by=attributed(actor, payload.created_by),
        metadata_jsonb=payload.metadata,
    )
    if payload.status == "completed":
        todo.completed_at = datetime.now(timezone.utc)
        todo.completed_by = attributed(actor, payload.created_by or payload.employee_id)
    db.add(todo)
    db.flush()
    record_audit(
        db,
        tenant_id=tenant_id,
        action="todo.created",
        entity_type="todo",
        entity_id=todo.id,
        actor=actor.label,
        detail={
            "employee_id": todo.employee_id,
            "title": todo.title,
            "todo_type": todo.todo_type,
            "target_entity_type": todo.entity_type,
            "target_entity_id": todo.entity_id,
        },
    )
    return todo, True


@router.post(
    "/todos/bulk",
    response_model=BulkTodoEnvelope,
    response_model_exclude_unset=True,
)
def bulk_create_todos(
    payload: BulkTodoCreateRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    """One routing decision, many records.

    The flow agent reads its whole queue in one call and every approval trail in
    another, then had to write one todo per record — so three hundred timesheets
    on the same map cost three hundred round-trips and three hundred rounds of
    reasoning about a map that had not changed. This is the leg that stayed
    serial.

    Every item runs `assign_todo`, the same guard sequence the single endpoint
    runs. Nothing here is a second implementation of a check, and the check that
    makes that matter most is the hosted agent's write boundary.

    Audited as ONE event with its counts, like every other bulk import here:
    three hundred near-identical `todo.created` rows would bury the trail the
    assignment audit exists to keep readable. Each todo's own creation is still
    recorded by `assign_todo`; what this adds is that they were one decision.
    """
    require_permission(actor, "todos.assign")
    if payload.on_error == "abort":
        outcome = _assign_all_or_nothing(db, actor, payload.items)
    else:
        outcome = _assign_what_it_can(db, actor, payload.items)
    if not outcome["applied"]:
        return envelope(outcome)
    record_audit(
        db,
        tenant_id=actor.tenant_id,
        action="todo.bulk_assigned",
        entity_type="tenant",
        entity_id=actor.tenant_id,
        actor=actor.label,
        detail={**outcome["summary"], "on_error": payload.on_error},
    )
    db.commit()
    return envelope(outcome)


def _row(index: int, item: CreateTodoRequest, outcome: str, **extra) -> dict:
    return {"index": index, "entity_id": item.entity_id, "outcome": outcome, **extra}


def _summary(items: list, results: list[dict]) -> dict:
    counts = {"created": 0, "unchanged": 0, "error": 0}
    for row in results:
        counts[row["outcome"]] += 1
    return {"total": len(items), "created": counts["created"],
            "unchanged": counts["unchanged"], "failed": counts["error"]}


class _BatchAborted(Exception):
    """Unwinds the one savepoint the whole batch runs in."""

    def __init__(self, results: list[dict]) -> None:
        super().__init__("batch aborted")
        self.results = results


def _assign_all_or_nothing(db: Session, actor: Actor, items: list) -> dict:
    """`abort`: the whole batch in ONE savepoint, unwound on the first failure.

    Deliberately not "write per item, then roll the transaction back" — that
    reads the same and is not the same. A savepoint that has been RELEASED is
    beyond the reach of an outer rollback under pysqlite, which does not emit
    its own BEGIN, so the undo would work on Postgres and silently keep the rows
    on SQLite. One savepoint that is never released until the batch is whole has
    nothing to take back and behaves identically on both.
    """
    results: list[dict] = []
    try:
        with db.begin_nested():
            for index, item in enumerate(items):
                try:
                    todo, created = assign_todo(db, actor, item)
                    db.flush()
                except (HTTPException, IntegrityError) as exc:
                    results.append(_row(index, item, "error", error=_assign_error(exc)))
                    raise _BatchAborted(results) from None
                results.append(_row(
                    index, item, "created" if created else "unchanged", id=todo.id,
                ))
    except _BatchAborted as aborted:
        return {"applied": False, "summary": _summary(items, aborted.results),
                "results": aborted.results}
    return {"applied": True, "summary": _summary(items, results), "results": results}


def _assign_what_it_can(db: Session, actor: Actor, items: list) -> dict:
    """`skip`, the default: one bad item costs that item and nothing else.

    The likely failure is one record having moved on since the agent read the
    queue. Aborting for it would discard the correct assignments and then fail
    identically on the retry; skipping leaves that one in the queue, where the
    next pass rediscovers it — the same self-healing the work queue rests on.

    Each item gets its own savepoint so a failure at the database (rather than
    at one of the look-ahead checks) does not abort the transaction and take
    every later item with it. No outer rollback follows a released savepoint
    here: what succeeded is kept.
    """
    results: list[dict] = []
    for index, item in enumerate(items):
        try:
            with db.begin_nested():
                todo, created = assign_todo(db, actor, item)
                db.flush()
        except (HTTPException, IntegrityError) as exc:
            results.append(_row(index, item, "error", error=_assign_error(exc)))
            continue
        results.append(_row(index, item, "created" if created else "unchanged", id=todo.id))
    summary = _summary(items, results)
    applied = summary["created"] > 0 or summary["unchanged"] > 0
    return {"applied": applied, "summary": summary, "results": results}


def _assign_error(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    # Named rather than echoed from the driver, which spells the open-todo
    # constraint differently on Postgres and SQLite.
    return "open todo already exists for this entity"


@router.get(
    "/todos/{todo_id}",
    response_model=TodoEnvelope,
    response_model_exclude_unset=True,
)
def get_todo(
    todo_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    todo = get_scoped_or_404(db, Todo, tenant_id, todo_id)
    return envelope(TodoRead.model_validate(todo).model_dump(by_alias=True))


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


@router.patch(
    "/todos/{todo_id}",
    response_model=TodoEnvelope,
    response_model_exclude_unset=True,
)
def update_todo(
    todo_id: str,
    payload: UpdateTodoRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    todo = get_scoped_or_404(db, Todo, actor.tenant_id, todo_id)
    require_permission(actor, "todos.complete_own")
    enforce_member_employee(actor, todo.employee_id)
    updates = payload.model_dump(exclude_unset=True)
    if "due_at" in updates:
        todo.due_at = updates.pop("due_at")
    if "status" in updates:
        was = todo.status
        todo.status = updates["status"]
        if todo.status == "completed":
            todo.completed_at = datetime.now(timezone.utc)
            todo.completed_by = attributed(actor, updates.get("completed_by") or todo.completed_by)
        else:
            # `cancelled` leaves these null on purpose. The columns say
            # COMPLETED, and a report counting `completed_at is not null` must
            # not pick up work that nobody did — who cancelled it and when is
            # in the audit row below, which is where an administrative act
            # belongs anyway.
            todo.completed_at = None
            todo.completed_by = None
        if todo.status != was and todo.status in ("completed", "cancelled"):
            record_audit(
                db,
                tenant_id=actor.tenant_id,
                action=f"todo.{todo.status}",
                entity_type="todo",
                entity_id=todo.id,
                actor=actor.label,
                detail={
                    "employee_id": todo.employee_id,
                    "title": todo.title,
                    "target_entity_type": todo.entity_type,
                    "target_entity_id": todo.entity_id,
                },
            )
    elif "completed_by" in updates:
        todo.completed_by = attributed(actor, updates["completed_by"])
    db.commit()
    db.refresh(todo)
    return envelope(TodoRead.model_validate(todo).model_dump(by_alias=True))


@router.post(
    "/approval-records",
    status_code=status.HTTP_201_CREATED,
    response_model=ApprovalRecordEnvelope,
    response_model_exclude_unset=True,
)
def create_approval_record(
    payload: CreateApprovalRecordRequest,
    actor: Annotated[Actor, Depends(get_actor)],
    db: Annotated[Session, Depends(get_db)],
):
    tenant_id = actor.tenant_id
    require_permission(actor, "approval.record")
    if actor.write_scope is not None:
        require_hosted_write_scope(
            actor, payload.entity_type,
            scoped_write_target(db, tenant_id, payload.entity_type, payload.entity_id),
            ignore=("status",),
        )
    target = ensure_referenced_entity_exists(
        db, tenant_id, payload.entity_type, payload.entity_id,
        allowed=ALLOWED_APPROVAL_ENTITY_TYPES, label="approval",
    )
    acted_at = resolve_acted_at(payload.acted_at, target)
    require_submission_before_decision(payload)
    ensure_no_operator_closure_marker(payload.metadata)
    # idempotency on the natural key: an agent retrying the same action gets
    # the already-recorded fact back instead of a duplicate
    existing = db.scalar(
        select(ApprovalRecord).where(
            ApprovalRecord.tenant_id == tenant_id,
            ApprovalRecord.entity_type == payload.entity_type,
            ApprovalRecord.entity_id == payload.entity_id,
            ApprovalRecord.round_no == payload.round_no,
            ApprovalRecord.sequence_no == payload.sequence_no,
            ApprovalRecord.action == payload.action,
            ApprovalRecord.historical_conflict_closed.is_(False),
        )
    )
    if existing is not None:
        return envelope(ApprovalRecordRead.model_validate(existing).model_dump(by_alias=True))
    ensure_node_undecided(db, tenant_id, payload)
    record = ApprovalRecord(
        tenant_id=tenant_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        round_no=payload.round_no,
        sequence_no=payload.sequence_no,
        action=payload.action,
        approver_id=attributed(actor, payload.approver_id),
        approver_role=payload.approver_role,
        comment=payload.comment,
        source=payload.source,
        metadata_jsonb=payload.metadata,
        acted_at=acted_at,
    )
    db.add(record)
    db.flush()
    record_audit(
        db,
        tenant_id=tenant_id,
        action="approval.recorded",
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        actor=actor.label,
        detail={
            "action": record.action,
            "round_no": record.round_no,
            "sequence_no": record.sequence_no,
            "approver_id": record.approver_id,
            "approver_role": record.approver_role,
            "comment": record.comment,
        },
    )
    db.commit()
    db.refresh(record)
    return envelope(ApprovalRecordRead.model_validate(record).model_dump(by_alias=True))


@router.get(
    "/approval-records/{approval_record_id}",
    response_model=ApprovalRecordEnvelope,
    response_model_exclude_unset=True,
)
def get_approval_record(
    approval_record_id: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: Annotated[Session, Depends(get_db)],
):
    record = get_scoped_or_404(db, ApprovalRecord, tenant_id, approval_record_id)
    return envelope(ApprovalRecordRead.model_validate(record).model_dump(by_alias=True))
