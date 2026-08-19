from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.email_domains import company_domain, normalize_email_address
from app.core.permissions import (
    HOSTED_FLOW_AGENT_PERMISSIONS,
    PRINCIPAL_HOSTED_FLOW_AGENT,
    PRINCIPAL_TENANT_SERVICE,
)
from app.core.entity_types import (
    APPROVAL_ENTITY_TYPES,
    BUILTIN_QUEUE_PATHS,
    TODO_ENTITY_TYPES,
    TODO_STATUSES,
)
from app.core.type_options import TYPE_NAME_PATTERN


PrincipalKind = Literal["tenant_service", "hosted_flow_agent"]
ProjectStatus = Literal["active", "archived"]
EmployeeStatus = Literal["active", "inactive"]
ResourceStatus = Literal["active", "inactive", "archived"]
VendorStatus = Literal["active", "archived"]
CustomerStatus = Literal["active", "archived"]
# 自然人 vs 组织 — the CLOSED axis of customer master data, and OFBiz's
# Person/PartyGroup distinction without the Party table. Not a type option: the
# distinction is universal rather than the tenant's to extend, so the database
# constrains it. The open axis is `CustomerType` below, which IS one. Absent
# means nobody stated it — not a third kind.
CustomerKind = Literal["person", "company"]
ProductStatus = Literal["active", "archived"]
ProductSkuStatus = Literal["active", "archived"]
BookingMode = Literal["exclusive", "shared"]
ResourceBookingStatus = Literal["confirmed", "cancelled"]
# Tenant-configurable via the builtin state machine; legality is validated
# at the endpoint against the tenant's definition, not by this type.
TimesheetStatus = str
# Tenant-configurable via the builtin state machine, same as TimesheetStatus.
LeaveStatus = str
ExpenseStatus = str
PurchaseStatus = str
QuotationStatus = str
QuotationOutcome = Literal["accepted", "declined", "expired"]
OrderStatus = str
# Type vocabularies (work types, expense categories, price types,
# adjustment types) are tenant-customizable via /type-options: the schema
# pins only the name shape, the route layer validates against the
# tenant's vocabulary and answers 422 with the active options.
TypeOptionName = Annotated[str, Field(pattern=TYPE_NAME_PATTERN)]
WorkType = TypeOptionName
ExpenseCategory = TypeOptionName
# 零售/批发/经销/电商/政企 — how a tenant segments its own customer book.
CustomerType = TypeOptionName
InvoiceType = Literal["vat_special", "vat_general", "vat_electronic", "receipt", "other"]
# The invoice family's own tax-document kind. Same vocabulary as the literal
# above (the `invoice_type` type-option family ships those names), but
# tenant-extensible — a workspace that issues 形式发票 or its own 内部结算单
# adds the value rather than waiting for a release.
InvoiceTypeOption = TypeOptionName
InvoiceItemType = TypeOptionName
PaymentMethod = TypeOptionName
# OFBiz's invoiceTypeId, which this column was named `direction` after when it
# only had the two money-flow values. `payroll` is OFBiz's PAYROL_INVOICE: a
# payslip, whose counterparty is an employee rather than a customer or a
# supplier. Not a type option — every settlement and visibility guard branches
# on it, so an extensible vocabulary would leave them undecidable.
InvoiceDirection = Literal["sales", "purchase", "payroll"]
PayPeriodType = TypeOptionName
PayrollItemType = TypeOptionName
PayComponentType = TypeOptionName
PaymentDirection = Literal["inbound", "outbound"]
# What a payment application may settle. `payment` is OFBiz's toPaymentId —
# netting a refund against an earlier receipt; `billing_account` is its
# billingAccountId — money paid into a standing account.
PaymentApplicationTarget = Literal["invoice", "expense_claim", "billing_account", "payment"]
# What an account counts. Not a type option: every settlement guard branches on
# it, so money must never reach a points account.
BillingAccountUnitType = Literal["currency", "points"]
BillingAccountStatus = Literal["active", "frozen", "closed"]
BillingAccountUnit = TypeOptionName
BillingAccountEntryReason = TypeOptionName
# Tenant-configurable via the builtin state machines, same as TimesheetStatus.
InvoiceStatus = str
PaymentStatus = str
ApprovalAction = Literal["submitted", "approved", "rejected", "returned", "commented"]
SourceType = Literal["web", "api", "ai", "system"]
# What an approval fact or a todo may point at.
#
# Derived from the state-machine registry, not typed out. This list used to live
# in four places — here, an if-chain in the API layer, a CHECK constraint in
# the migrations, and DOCUMENT_FAMILIES — all four had drifted: purchase orders
# were missing here, invoices and payments were missing from the constraint, and
# the approval if-chain checked neither. The visible symptom was a 500 on
# "create the approval todo for this payment".
ApprovalEntityType = Literal[APPROVAL_ENTITY_TYPES]  # type: ignore[valid-type]
TodoEntityType = Literal[TODO_ENTITY_TYPES]  # type: ignore[valid-type]
TenantStatus = Literal["active", "inactive"]
# `cancelled` is not a third flavour of done — it is the honest word for a work
# item that stopped being actionable without anybody doing it. The server sets
# it when the record a todo points at is deleted, and a flow agent sets it when
# the workspace's own rules retire the work. Recording either as `completed`
# would make a person's queue history claim they did something they did not.
# Derived, not restated. The third copy of this list is what let the
# database keep a narrower one than the API for the whole life of the
# product.
TodoStatus = Literal[TODO_STATUSES]
# tenant-defined role names; validated against the tenant roles table
UserRole = str
RegistrationStatus = Literal["pending_email", "pending_review", "approved", "rejected"]
EnterprisePilotApplicationStatus = Literal["submitted", "contacted", "accepted", "rejected"]
EnterprisePilotReviewStatus = Literal["contacted", "accepted", "rejected"]
EnterprisePilotAgent = Literal["Codex", "Claude Cowork", "Hermes Agent", "OpenClaw", "Other"]
EnterprisePilotWorkflow = Literal[
    "Timesheet submission & approval",
    "Customer quotation & approval",
    "Expense filing & approval",
    "Purchase request & order",
    "Resource booking",
    "Custom record type",
    "Other",
]
EnterprisePilotCompanySize = Literal["1-20", "20-50", "50-100", "100-200", "200+"]
EnterprisePilotAgentManagement = Literal["employee_selected", "company_managed", "both"]
EnterprisePilotWriteReadiness = Literal[
    "process_ready",
    "security_review",
    "considering",
    "exploring",
]
EnterprisePilotTiming = Literal[
    "asap",
    "within_30_days",
    "30_60_days",
    "60_90_days",
    "exploring",
]
UserStatus = Literal["invited", "active", "disabled"]
# Tenant-configurable per object type via state machines; validated at the
# endpoint against the tenant's definition.
BusinessObjectStatus = str
ObjectTypeDefinitionStatus = Literal["active", "archived"]
EntityKind = Literal["business_object", "builtin"]
ApprovalTargetStatus = BusinessObjectStatus


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class RequestModel(BaseModel):
    """Base for every model validated from a client-sent body, nested rows
    included. Unknown fields are rejected (422 naming the field), never
    silently dropped: the callers are agents, and a misspelled field or a
    create-only field sent to a PATCH that the server quietly ignores turns
    into a confident wrong report with no error anywhere to read.
    tests/test_request_strictness.py enumerates the models this must cover."""

    model_config = ConfigDict(extra="forbid")


T = TypeVar("T")


class EnvelopeMeta(BaseModel):
    request_id: str | None = None
    total: int | None = None
    page: int | None = None
    page_size: int | None = None
    pages: int | None = None


class ListEnvelope(BaseModel, Generic[T]):
    data: list[T]
    meta: EnvelopeMeta = Field(default_factory=EnvelopeMeta)


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: EnvelopeMeta = Field(default_factory=EnvelopeMeta)


SingleEnvelope = Envelope


class ProjectBase(RequestModel):
    project_code: str | None = Field(default=None, max_length=64)
    project_name: str | None = Field(default=None, max_length=200)
    client: str | None = Field(default=None, max_length=200)
    status: ProjectStatus = "active"
    start_date: date | None = None
    end_date: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateProjectRequest(ProjectBase):
    project_name: str = Field(max_length=200)


class UpdateProjectRequest(ProjectBase):
    pass


class ProjectRead(APIModel):
    id: str
    project_code: str | None = None
    project_name: str
    client: str | None = None
    status: ProjectStatus
    start_date: date | None = None
    end_date: date | None = None
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime | None = None


ProjectListEnvelope = ListEnvelope[ProjectRead]


ProjectEnvelope = Envelope[ProjectRead]


class VendorBase(RequestModel):
    vendor_code: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, max_length=64)
    contact: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    status: VendorStatus = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateVendorRequest(VendorBase):
    name: str = Field(max_length=200)


class UpdateVendorRequest(VendorBase):
    pass


class VendorRead(APIModel):
    id: str
    vendor_code: str | None = None
    name: str
    tax_id: str | None = None
    contact: str | None = None
    email: str | None = None
    phone: str | None = None
    status: VendorStatus
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime | None = None


VendorListEnvelope = ListEnvelope[VendorRead]


VendorEnvelope = Envelope[VendorRead]


class CustomerBase(RequestModel):
    customer_code: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=200)
    # 自然人还是组织 — omit it rather than guessing; null is a legal answer
    customer_kind: CustomerKind | None = None
    # the tenant's own segmentation (customer_type vocabulary)
    customer_type: CustomerType | None = None
    tax_id: str | None = Field(default=None, max_length=64)
    contact: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    status: CustomerStatus = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateCustomerRequest(CustomerBase):
    name: str = Field(max_length=200)


class UpdateCustomerRequest(CustomerBase):
    pass


class CustomerRead(APIModel):
    id: str
    customer_code: str | None = None
    name: str
    customer_kind: CustomerKind | None = None
    customer_type: CustomerType | None = None
    tax_id: str | None = None
    contact: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    status: CustomerStatus
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime | None = None


CustomerListEnvelope = ListEnvelope[CustomerRead]


CustomerEnvelope = Envelope[CustomerRead]


class ProductBase(RequestModel):
    product_code: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=200)
    spec: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, max_length=50)
    list_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    status: ProductStatus = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateProductRequest(ProductBase):
    name: str = Field(max_length=200)


class UpdateProductRequest(ProductBase):
    pass


class ProductRead(APIModel):
    id: str
    product_code: str | None = None
    name: str
    spec: str | None = None
    unit: str | None = None
    list_price: float | None = None
    currency: str
    status: ProductStatus
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    # Tells the agent whether requisitioning this product needs a currently
    # usable variant conversation. sku_count remains the historical total,
    # while has_skus only reflects active variants.
    has_skus: bool = False
    sku_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None


ProductListEnvelope = ListEnvelope[ProductRead]


ProductEnvelope = Envelope[ProductRead]


# --- bulk master-data upsert (spreadsheet import) -------------------------
#
# One shape for products, vendors, and customers. The row models below reuse
# each family's own Base, so a bulk row accepts exactly the fields a single
# create does — with the tenant's code promoted to REQUIRED, because it is the
# key the upsert matches on. A row without a code cannot be matched, and
# inventing one would silently create a duplicate on the next import, so the
# server rejects it and the agent goes back to the person for the real code.

# Bounded so one request cannot pin the worker on a 50k-row paste; the skill
# chunks anything larger and reports per chunk.
BULK_MAX_ROWS = 500


# The shipped catalog (list/default/promo/wholesale/competitive/minimum/
# maximum/cost) plus whatever the tenant defined via /type-options.
ProductPriceType = TypeOptionName
ProductPriceStatus = Literal["active", "archived"]
SupplierProductStatus = Literal["active", "archived"]


class BulkProductPriceRow(RequestModel):
    """A price-book entry riding a bulk product row. Upserted on
    (price_type, currency): an equal live price is unchanged, a different one
    archives the old row and creates the new — history via status."""

    price_type: ProductPriceType
    price: float = Field(ge=0, le=9_999_999.99)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    tax_in_price: bool = True
    tax_percentage: float | None = Field(default=None, ge=0, le=100)


class BulkSupplierRow(RequestModel):
    """A supply source riding a bulk product row, joined to vendor master data
    by the tenant's own vendor_code. Upserted on (product, vendor): fields
    update in place, and re-importing an archived pair revives it."""

    vendor_code: str = Field(min_length=1, max_length=64)
    supplier_product_code: str | None = Field(default=None, max_length=64)
    supplier_product_name: str | None = Field(default=None, max_length=200)
    last_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    min_order_quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    order_increment: float | None = Field(default=None, gt=0, le=9_999_999.99)
    preference: int | None = Field(default=None, ge=1, le=100)


class BulkProductRow(ProductBase):
    product_code: str = Field(min_length=1, max_length=64)
    name: str = Field(max_length=200)
    # optional price-book and supply-source writes alongside the product;
    # omitted lists leave existing rows alone, like every omitted field
    prices: list[BulkProductPriceRow] = Field(default_factory=list, max_length=50)
    suppliers: list[BulkSupplierRow] = Field(default_factory=list, max_length=50)


class BulkVendorRow(VendorBase):
    vendor_code: str = Field(min_length=1, max_length=64)
    name: str = Field(max_length=200)


class BulkCustomerRow(CustomerBase):
    customer_code: str = Field(min_length=1, max_length=64)
    name: str = Field(max_length=200)


class BulkUpsertRequest(RequestModel):
    """`dry_run` runs the identical code path and rolls back, so the preview an
    agent shows the person is what the write would actually do — not a
    separately-computed guess that can drift from it.

    `on_error` decides what a bad row costs. The default `abort` applies
    nothing, which is the safe pairing with dry_run: the person fixes the
    spreadsheet and re-runs, and because the upsert is idempotent, re-running
    is free. `skip` is the deliberate escape hatch for "import the 497 good
    rows and tell me about the 3"."""

    rows: list[Any] = Field(min_length=1, max_length=BULK_MAX_ROWS)
    dry_run: bool = False
    on_error: Literal["abort", "skip"] = "abort"


class BulkProductUpsertRequest(BulkUpsertRequest):
    rows: list[BulkProductRow] = Field(min_length=1, max_length=BULK_MAX_ROWS)


class BulkVendorUpsertRequest(BulkUpsertRequest):
    rows: list[BulkVendorRow] = Field(min_length=1, max_length=BULK_MAX_ROWS)


class BulkCustomerUpsertRequest(BulkUpsertRequest):
    rows: list[BulkCustomerRow] = Field(min_length=1, max_length=BULK_MAX_ROWS)


# --- historical document import (quotations, orders) -----------------------
#
# A migration, not day-to-day filing: the documents already happened, carry
# their own numbers, and sit in terminal states. So the contract differs from
# the live endpoints in three deliberate ways — the number is REQUIRED (a
# historical document keeps its identity; nothing is server-allocated, which
# also skips the per-tenant number lock that would serialize a 300k-row
# import), any state of the tenant's machine is accepted (成交/流失 documents
# are not walked through the lifecycle), and master data is referenced by the
# tenant's own codes rather than ids, because that is what an export holds.


class BulkDocumentLineRow(RequestModel):
    """One line of a historical quotation/order. Shared shape: the two
    families differ only in the delivery-promise field, so both are accepted
    and the irrelevant one is ignored per family."""

    line_no: int | None = Field(default=None, ge=1, le=9999)
    # resolved against master data by the tenant's own code
    product_code: str | None = Field(default=None, max_length=64)
    sku_code: str | None = Field(default=None, max_length=64)
    # what the historical document printed; also the fallback when the
    # product is gone from the catalog and the caller allows snapshots
    product_name_snapshot: str | None = Field(default=None, max_length=200)
    spec: str | None = Field(default=None, max_length=200)
    quantity: float = Field(gt=0, le=9_999_999.99)
    unit: str | None = Field(default=None, max_length=50)
    list_price_snapshot: float | None = Field(default=None, ge=0, le=9_999_999.99)
    unit_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    is_gift: bool = False
    lead_time: str | None = Field(default=None, max_length=100)  # quotations
    promised_date: date | None = None  # orders
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class BulkDocumentAdjustmentRow(RequestModel):
    """A historical adjustment. Pinned to a line by that line's `line_no`
    within the same row — ids do not exist yet at import time."""

    adjustment_type: str = Field(max_length=20)
    description: str | None = Field(default=None, max_length=500)
    amount: float = Field(ge=-9_999_999.99, le=9_999_999.99)
    source_percentage: float | None = Field(default=None, ge=0, le=100)
    line_no: int | None = Field(default=None, ge=1, le=9999)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BulkDocumentRowBase(RequestModel):
    # the salesperson: by code, or by id when the export carries one
    employee_code: str | None = Field(default=None, max_length=64)
    employee_id: str | None = None
    customer_code: str | None = Field(default=None, max_length=64)
    customer_id: str | None = None
    customer_name_snapshot: str | None = Field(default=None, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_phone: str | None = Field(default=None, max_length=50)
    title: str | None = Field(default=None, max_length=200)
    project_code: str | None = Field(default=None, max_length=64)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    payment_terms: str | None = Field(default=None, max_length=2000)
    delivery_terms: str | None = Field(default=None, max_length=2000)
    total_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    remarks: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    items: list[BulkDocumentLineRow] = Field(default_factory=list, max_length=200)
    adjustments: list[BulkDocumentAdjustmentRow] = Field(default_factory=list, max_length=50)


class BulkSalesQuotationRow(BulkDocumentRowBase):
    quote_number: str = Field(min_length=1, max_length=64)
    contact_email: str | None = Field(default=None, max_length=320)
    quote_date: date | None = None
    valid_until: date | None = None
    # any state of the tenant's machine: historical quotations arrive closed
    status: str = Field(default="draft", max_length=30)
    outcome_note: str | None = Field(default=None, max_length=2000)


class BulkSalesOrderRow(BulkDocumentRowBase):
    order_no: str = Field(min_length=1, max_length=64)
    # links the order to its won quotation by that quotation's number
    source_quote_number: str | None = Field(default=None, max_length=64)
    ship_to_address: str | None = Field(default=None, max_length=500)
    contract_no: str | None = Field(default=None, max_length=64)
    order_date: date | None = None
    promised_date: date | None = None
    status: str = Field(default="draft", max_length=30)


class BulkPurchaseOrderRow(RequestModel):
    """A historical purchase order. The vendor is to a PO what the
    salesperson is to a quotation: the document cannot exist without one, so
    an unmatched vendor_code is always an error — create the vendor first
    (archived is fine; they are history too)."""

    po_number: str = Field(min_length=1, max_length=64)
    employee_code: str | None = Field(default=None, max_length=64)
    employee_id: str | None = None
    vendor_code: str | None = Field(default=None, max_length=64)
    vendor_id: str | None = None
    vendor_name_snapshot: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    contract_no: str | None = Field(default=None, max_length=64)
    order_date: date | None = None
    promised_date: date | None = None
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    payment_terms: str | None = Field(default=None, max_length=2000)
    delivery_terms: str | None = Field(default=None, max_length=2000)
    total_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    status: str = Field(default="draft", max_length=30)
    remarks: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    items: list[BulkDocumentLineRow] = Field(default_factory=list, max_length=200)
    adjustments: list[BulkDocumentAdjustmentRow] = Field(default_factory=list, max_length=50)


class BulkInvoiceLineRow(RequestModel):
    """A historical invoice line. Unlike order lines, quantity and price are
    both optional — a 运费 or 折扣 line has neither, and a 汇总开票 line carries
    an amount alone."""

    line_no: int | None = Field(default=None, ge=1, le=9999)
    invoice_item_type: str = Field(default="goods", max_length=30)
    product_code: str | None = Field(default=None, max_length=64)
    sku_code: str | None = Field(default=None, max_length=64)
    product_name_snapshot: str | None = Field(default=None, max_length=200)
    spec: str | None = Field(default=None, max_length=200)
    quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    unit: str | None = Field(default=None, max_length=50)
    unit_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    amount: float | None = Field(default=None, ge=-9_999_999.99, le=9_999_999.99)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    tax_amount: float | None = Field(default=None, ge=-9_999_999.99, le=9_999_999.99)
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class BulkInvoiceRow(RequestModel):
    """One historical invoice — 期初应收应付, the open bills a company carries
    across the switch. The direction decides which counterparty code is
    required; an unmatched one is reported per row like everywhere else.

    Settlement is NOT imported here: how much of this invoice was already paid
    is a payment fact, so it arrives as payments and their applications. An
    invoice imported alone is simply fully outstanding, which is what 期初
    balances are."""

    invoice_no: str = Field(min_length=1, max_length=64)
    direction: InvoiceDirection
    invoice_type: str | None = Field(default=None, max_length=30)
    employee_code: str | None = Field(default=None, max_length=64)
    employee_id: str | None = None
    customer_code: str | None = Field(default=None, max_length=64)
    customer_id: str | None = None
    vendor_code: str | None = Field(default=None, max_length=64)
    vendor_id: str | None = None
    counterparty_name_snapshot: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    project_code: str | None = Field(default=None, max_length=64)
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    total_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    tax_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    tax_invoice_code: str | None = Field(default=None, max_length=32)
    tax_invoice_number: str | None = Field(default=None, max_length=64)
    # any state of the tenant's machine: historical invoices arrive issued
    status: str = Field(default="draft", max_length=30)
    remarks: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    items: list[BulkInvoiceLineRow] = Field(default_factory=list, max_length=200)


class BulkPaymentRow(RequestModel):
    """One historical money movement, keyed on its own `payment_no`.

    What each payment SETTLED is deliberately not a column here. Writing
    applications straight into the ledger would bypass the over-application,
    direction and currency guards that are the only reason the ledger can be
    trusted — so opening balances arrive as invoices and payments, and the
    matching is done through POST /payments/{id}/apply, which checks all three.
    """

    payment_no: str = Field(min_length=1, max_length=64)
    direction: PaymentDirection
    payment_method: str | None = Field(default=None, max_length=30)
    employee_code: str | None = Field(default=None, max_length=64)
    employee_id: str | None = None
    customer_code: str | None = Field(default=None, max_length=64)
    customer_id: str | None = None
    vendor_code: str | None = Field(default=None, max_length=64)
    vendor_id: str | None = None
    payee_employee_code: str | None = Field(default=None, max_length=64)
    payee_employee_id: str | None = None
    counterparty_name_snapshot: str | None = Field(default=None, max_length=200)
    payment_date: date | None = None
    amount: float = Field(gt=0, le=9_999_999_999.99)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    bank_account: str | None = Field(default=None, max_length=200)
    counterparty_account: str | None = Field(default=None, max_length=200)
    reference_no: str | None = Field(default=None, max_length=100)
    status: str = Field(default="draft", max_length=30)
    remarks: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class BulkDocumentImportRequest(RequestModel):
    """`on_error` defaults to `skip` here, unlike master data. A bad master-
    data row usually means the column mapping is wrong, so aborting the whole
    file is the useful answer. A bad historical document usually means ONE
    document references a customer that no longer exists — and stopping a
    300k-row migration for it helps nobody. The report names every skipped
    document."""

    dry_run: bool = False
    on_error: Literal["abort", "skip"] = "skip"
    # what to do when a customer/product code matches nothing: report the
    # document (default — the person decides whether to import the missing
    # master data first), or keep the historical text and import anyway
    on_missing_reference: Literal["error", "snapshot"] = "error"


class BulkSalesQuotationImportRequest(BulkDocumentImportRequest):
    rows: list[BulkSalesQuotationRow] = Field(min_length=1, max_length=BULK_MAX_ROWS)


class BulkSalesOrderImportRequest(BulkDocumentImportRequest):
    rows: list[BulkSalesOrderRow] = Field(min_length=1, max_length=BULK_MAX_ROWS)


class BulkPurchaseOrderImportRequest(BulkDocumentImportRequest):
    rows: list[BulkPurchaseOrderRow] = Field(min_length=1, max_length=BULK_MAX_ROWS)


class BulkInvoiceImportRequest(BulkDocumentImportRequest):
    rows: list[BulkInvoiceRow] = Field(min_length=1, max_length=BULK_MAX_ROWS)


class BulkPaymentImportRequest(BulkDocumentImportRequest):
    rows: list[BulkPaymentRow] = Field(min_length=1, max_length=BULK_MAX_ROWS)


class BulkRowResult(APIModel):
    """Per-row outcome, carrying the source `index` so the agent can point the
    person at the spreadsheet line that needs fixing."""

    index: int
    code: str | None = None
    outcome: Literal["created", "updated", "unchanged", "error"]
    id: str | None = None
    # which fields an update actually changed — lets the agent report "12
    # updated, all of them price only" instead of an opaque count
    changed: list[str] = Field(default_factory=list)
    error: str | None = None


class BulkUpsertSummary(APIModel):
    total: int
    created: int
    updated: int
    unchanged: int
    failed: int


class BulkUpsertResult(APIModel):
    dry_run: bool
    applied: bool
    summary: BulkUpsertSummary
    results: list[BulkRowResult]


BulkUpsertEnvelope = Envelope[BulkUpsertResult]


class BulkDocumentRowResult(APIModel):
    """Same shape as a master-data row result, keyed by the document's own
    number instead of a master-data code — that number is what the person
    finds the row by in their spreadsheet."""

    index: int
    number: str | None = None
    outcome: Literal["created", "updated", "unchanged", "error"]
    id: str | None = None
    changed: list[str] = Field(default_factory=list)
    error: str | None = None


class BulkDocumentImportResult(APIModel):
    dry_run: bool
    applied: bool
    summary: BulkUpsertSummary
    results: list[BulkDocumentRowResult]


BulkDocumentImportEnvelope = Envelope[BulkDocumentImportResult]


class ProductSkuBase(RequestModel):
    product_id: str | None = None
    sku_code: str | None = Field(default=None, max_length=64)
    variant_attrs: dict[str, Any] = Field(default_factory=dict)
    list_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    status: ProductSkuStatus = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateProductSkuRequest(ProductSkuBase):
    product_id: str


class BatchCreateProductSkusRequest(RequestModel):
    dimension: str = Field(min_length=1, max_length=50)
    values: list[str] = Field(min_length=1, max_length=200)
    list_price: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("9999999.99"),
        decimal_places=2,
    )

    @field_validator("dimension", mode="before")
    @classmethod
    def normalize_dimension(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("values", mode="before")
    @classmethod
    def normalize_values(cls, value):
        if not isinstance(value, list):
            return value
        if len(value) > 200:
            raise ValueError("at most 200 values are allowed")

        unique: list[str] = []
        seen: set[str] = set()
        for item in value:
            # Leave non-string values to Pydantic's item-level type validation.
            if not isinstance(item, str):
                return value
            normalized = item.strip()
            if not normalized:
                raise ValueError("values must not contain blank strings")
            if len(normalized) > 200:
                raise ValueError("each value must be at most 200 characters")
            if normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)
        return unique


class UpdateProductSkuRequest(RequestModel):
    sku_code: str | None = Field(default=None, max_length=64)
    variant_attrs: dict[str, Any] | None = None
    list_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    status: ProductSkuStatus | None = None
    metadata: dict[str, Any] | None = None


class ProductSkuRead(APIModel):
    id: str
    product_id: str
    sku_code: str | None = None
    variant_attrs: dict[str, Any]
    list_price: float | None = None
    status: ProductSkuStatus
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime | None = None


ProductSkuListEnvelope = ListEnvelope[ProductSkuRead]


ProductSkuEnvelope = Envelope[ProductSkuRead]


class BatchCreateProductSkusRead(BaseModel):
    created: list[ProductSkuRead]
    skipped: list[str]


BatchCreateProductSkusEnvelope = Envelope[BatchCreateProductSkusRead]


class ProductPriceBase(RequestModel):
    price_type: ProductPriceType
    price: float = Field(ge=0, le=9_999_999.99)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    tax_in_price: bool = True
    tax_percentage: float | None = Field(default=None, ge=0, le=100)
    status: ProductPriceStatus = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateProductPriceRequest(ProductPriceBase):
    product_id: str
    sku_id: str | None = None


class UpdateProductPriceRequest(RequestModel):
    # identity (product/sku/type/currency) is not editable — a different key
    # is a different price row; supersede instead
    price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    tax_in_price: bool | None = None
    tax_percentage: float | None = Field(default=None, ge=0, le=100)
    status: ProductPriceStatus | None = None
    metadata: dict[str, Any] | None = None


class ProductPriceRead(APIModel):
    id: str
    product_id: str
    sku_id: str | None = None
    price_type: ProductPriceType
    price: float
    currency: str
    tax_in_price: bool
    tax_percentage: float | None = None
    status: ProductPriceStatus
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime


ProductPriceListEnvelope = ListEnvelope[ProductPriceRead]


ProductPriceEnvelope = Envelope[ProductPriceRead]


class SupplierProductBase(RequestModel):
    supplier_product_code: str | None = Field(default=None, max_length=64)
    supplier_product_name: str | None = Field(default=None, max_length=200)
    last_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    min_order_quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    order_increment: float | None = Field(default=None, gt=0, le=9_999_999.99)
    preference: int | None = Field(default=None, ge=1, le=100)
    status: SupplierProductStatus = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateSupplierProductRequest(SupplierProductBase):
    product_id: str
    vendor_id: str


class UpdateSupplierProductRequest(RequestModel):
    # the (product, vendor) pair is the row's identity and is not editable
    supplier_product_code: str | None = Field(default=None, max_length=64)
    supplier_product_name: str | None = Field(default=None, max_length=200)
    last_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    min_order_quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    order_increment: float | None = Field(default=None, gt=0, le=9_999_999.99)
    preference: int | None = Field(default=None, ge=1, le=100)
    status: SupplierProductStatus | None = None
    metadata: dict[str, Any] | None = None


class SupplierProductRead(APIModel):
    id: str
    product_id: str
    vendor_id: str
    vendor_name: str | None = None
    supplier_product_code: str | None = None
    supplier_product_name: str | None = None
    last_price: float | None = None
    currency: str
    lead_time_days: int | None = None
    min_order_quantity: float | None = None
    order_increment: float | None = None
    preference: int | None = None
    status: SupplierProductStatus
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime


SupplierProductListEnvelope = ListEnvelope[SupplierProductRead]


SupplierProductEnvelope = Envelope[SupplierProductRead]


# Why stock moved. `import_override` is reserved for the bulk import finding
# the system count different from the imported count — the difference lands
# as a movement, never as an edit of the item's totals.
InventoryMovementReason = Literal[
    "initial", "import_initial", "import_override", "received", "issued",
    "adjustment", "damaged", "returned", "transfer", "other",
]
InventoryItemStatus = Literal["active", "archived"]


class CreateInventoryItemRequest(RequestModel):
    product_id: str
    sku_id: str | None = None
    facility: str = Field(default="", max_length=100)
    lot_id: str = Field(default="", max_length=64)
    bin_number: str | None = Field(default=None, max_length=64)
    expire_date: date | None = None
    received_at: datetime | None = None
    unit_cost: float | None = Field(default=None, ge=0, le=9_999_999.99)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    status: InventoryItemStatus = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
    # optional opening balance — lands as the item's first ledger detail,
    # never as a bare number on the item
    initial_quantity: float | None = Field(default=None, ge=-9_999_999.99, le=9_999_999.99)
    initial_reason: InventoryMovementReason = "initial"
    initial_description: str | None = Field(default=None, max_length=500)


class UpdateInventoryItemRequest(RequestModel):
    # deliberately NO quantity fields: totals move only through details —
    # sending quantity_on_hand here is a 422 naming the field
    facility: str | None = Field(default=None, max_length=100)
    lot_id: str | None = Field(default=None, max_length=64)
    bin_number: str | None = Field(default=None, max_length=64)
    expire_date: date | None = None
    received_at: datetime | None = None
    unit_cost: float | None = Field(default=None, ge=0, le=9_999_999.99)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    status: InventoryItemStatus | None = None
    metadata: dict[str, Any] | None = None


class InventoryItemRead(APIModel):
    id: str
    product_id: str
    product_code: str | None = None
    sku_id: str | None = None
    facility: str
    lot_id: str
    bin_number: str | None = None
    expire_date: date | None = None
    received_at: datetime | None = None
    quantity_on_hand: float
    available_to_promise: float
    unit_cost: float | None = None
    currency: str
    status: InventoryItemStatus
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime


InventoryItemListEnvelope = ListEnvelope[InventoryItemRead]


InventoryItemEnvelope = Envelope[InventoryItemRead]


class CreateInventoryItemDetailRequest(RequestModel):
    inventory_item_id: str
    quantity_on_hand_diff: float = Field(ge=-9_999_999.99, le=9_999_999.99)
    # omitted → follows quantity_on_hand_diff; reservations later move it alone
    available_to_promise_diff: float | None = Field(default=None, ge=-9_999_999.99, le=9_999_999.99)
    reason: InventoryMovementReason
    description: str | None = Field(default=None, max_length=500)
    entity_type: str | None = Field(default=None, max_length=50)
    entity_id: str | None = None
    unit_cost: float | None = Field(default=None, ge=0, le=9_999_999.99)
    effective_at: datetime | None = None
    created_by: str | None = Field(default=None, max_length=100)


class InventoryItemDetailRead(APIModel):
    id: str
    inventory_item_id: str
    quantity_on_hand_diff: float
    available_to_promise_diff: float
    reason: InventoryMovementReason
    description: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    unit_cost: float | None = None
    effective_at: datetime
    created_by: str | None = None
    created_at: datetime


InventoryItemDetailListEnvelope = ListEnvelope[InventoryItemDetailRead]


InventoryItemDetailEnvelope = Envelope[InventoryItemDetailRead]


class BulkInventoryRow(RequestModel):
    """One stock-take line. Matches products by the tenant's own code, the
    stock position by (product-or-sku, facility, lot). `quantity` is what the
    person counted — the import records the DIFFERENCE from the system count
    as a ledger detail (`import_override`), never an edit of the item."""

    product_code: str = Field(min_length=1, max_length=64)
    sku_code: str | None = Field(default=None, max_length=64)
    facility: str = Field(default="", max_length=100)
    lot_id: str = Field(default="", max_length=64)
    quantity: float = Field(ge=-9_999_999.99, le=9_999_999.99)
    bin_number: str | None = Field(default=None, max_length=64)
    expire_date: date | None = None
    unit_cost: float | None = Field(default=None, ge=0, le=9_999_999.99)
    description: str | None = Field(default=None, max_length=500)


class BulkInventoryUpsertRequest(RequestModel):
    rows: list[BulkInventoryRow] = Field(min_length=1, max_length=BULK_MAX_ROWS)
    dry_run: bool = False
    on_error: Literal["abort", "skip"] = "abort"


class ResourceBase(RequestModel):
    resource_type: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, max_length=200)
    code: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=200)
    capacity: int | None = Field(default=None, ge=1)
    booking_mode: BookingMode = "exclusive"
    max_quantity: int | None = Field(default=None, ge=1)
    status: ResourceStatus = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateResourceRequest(ResourceBase):
    resource_type: str = Field(max_length=100)
    name: str = Field(max_length=200)


class UpdateResourceRequest(ResourceBase):
    pass


class ResourceRead(APIModel):
    id: str
    resource_type: str
    name: str
    code: str | None = None
    location: str | None = None
    capacity: int | None = None
    booking_mode: BookingMode
    max_quantity: int | None = None
    status: ResourceStatus
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime | None = None


ResourceListEnvelope = ListEnvelope[ResourceRead]


ResourceEnvelope = Envelope[ResourceRead]


class TenantBase(RequestModel):
    name: str | None = Field(default=None, max_length=200)
    status: TenantStatus = "active"


class CreateTenantRequest(TenantBase):
    name: str = Field(max_length=200)
    initial_api_key_label: str | None = Field(default="default", max_length=200)


class TenantRead(APIModel):
    id: str
    name: str
    email_domain: str | None = None
    slug: str | None = None
    status: TenantStatus
    created_at: datetime
    updated_at: datetime | None = None


class ApiKeyRead(APIModel):
    id: str
    tenant_id: str
    label: str | None = None
    user_id: str | None = None
    role: str
    # Tenant-level keys only: `tenant_service` is the tenant's own automation
    # credential, `hosted_flow_agent` is the platform-issued principal ORYH
    # operates. Read-only to tenants — issuance is a platform action.
    principal_kind: PrincipalKind = PRINCIPAL_TENANT_SERVICE
    # Present only on a hosted principal, where "what may this key do" is a
    # question the customer is owed a literal answer to. A tenant's own service
    # key has no grant set to report — it bypasses the permission layer — and a
    # user-bound key follows its owner's live role, reported by GET /auth/me.
    permissions: list[str] | None = None
    is_active: bool

    @field_validator("principal_kind", mode="before")
    @classmethod
    def default_unset_principal_kind(cls, value):
        # A key with nothing recorded is a tenant service key — the same rule
        # the migration backfills with, applied to rows read before it ran and
        # to instances not yet flushed (the column default is an INSERT default).
        return PRINCIPAL_TENANT_SERVICE if value is None else value

    @model_validator(mode="after")
    def describe_hosted_principal(self):
        # Derived, never stored: the grant set is fixed in code, so a key row
        # cannot drift from what the permission layer will actually enforce.
        if self.principal_kind == PRINCIPAL_HOSTED_FLOW_AGENT:
            self.permissions = sorted(HOSTED_FLOW_AGENT_PERMISSIONS)
        return self
    user_name: str | None = None
    user_email: str | None = None
    user_status: UserStatus | None = None
    # This is distinct from ``is_active``: an enabled user-bound key is still
    # unusable when its owner is disabled or no longer exists.
    effective_active: bool | None = None
    # Only usable keys have an effective role. User-bound keys follow the
    # active owner's current role; service keys use the role stored on the key.
    effective_role: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


ApiKeyListEnvelope = ListEnvelope[ApiKeyRead]


ApiKeyEnvelope = Envelope[ApiKeyRead]


class ApiKeyOwnerRead(APIModel):
    id: str
    name: str | None = None
    email: str
    role: str
    employee_id: str | None = None
    status: Literal["active"]


ApiKeyOwnerListEnvelope = ListEnvelope[ApiKeyOwnerRead]


class CreateApiKeyRequest(RequestModel):
    label: str | None = Field(default="default", max_length=200)
    user_id: str | None = None


class UpdateApiKeyRequest(RequestModel):
    label: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None


class CreateTenantResponse(BaseModel):
    tenant: TenantRead
    api_key: ApiKeyRead
    plain_text_api_key: str


class CreateApiKeyResponse(BaseModel):
    api_key: ApiKeyRead
    plain_text_api_key: str


CreateApiKeyEnvelope = Envelope[CreateApiKeyResponse]


def _validated_email(value: str) -> str:
    return normalize_email_address(value)


class RegisterRequest(RequestModel):
    company_name: str = Field(min_length=2, max_length=200)
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _validated_email(value)

    @field_validator("company_name")
    @classmethod
    def normalize_company_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("company name is too short")
        return normalized


class VerifyEmailRequest(RequestModel):
    token: str = Field(max_length=200)


class LoginRequest(RequestModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class DeviceStartRequest(RequestModel):
    # shown verbatim on the browser approval page so the person can tell
    # which agent is asking
    client_name: str | None = Field(default=None, max_length=200)


class DeviceTokenRequest(RequestModel):
    device_code: str = Field(max_length=200)


class SendNotificationRequest(RequestModel):
    """One work event, to one employee.

    No recipient address and no message body: the server resolves the first
    from the employee record and assembles the second. See
    app/api/notifications.py for why both are withheld from the caller.
    """

    employee_id: str
    event: str = Field(max_length=20)
    title: str = Field(max_length=200)
    # The approver's own words, carried verbatim. Optional because an approval
    # rarely needs one and a return always does.
    detail: str | None = Field(default=None, max_length=4000)
    actor_name: str | None = Field(default=None, max_length=200)
    # What the message is about, for the audit trail's sake.
    entity_type: str | None = Field(default=None, max_length=50)
    entity_id: str | None = None
    # Checked to belong to this employee when given, so a link never points at
    # somebody else's queue item.
    todo_id: str | None = None


class TokenRefreshRequest(RequestModel):
    refresh_token: str = Field(max_length=200)


class UserRead(APIModel):
    id: str
    tenant_id: str
    email: str
    name: str | None = None
    role: UserRole
    employee_id: str | None = None
    status: UserStatus
    invitation_pending: bool
    email_verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


UserListEnvelope = ListEnvelope[UserRead]


UserEnvelope = Envelope[UserRead]


class DisplayNameResolveRequest(RequestModel):
    employee_ids: list[str] = Field(default_factory=list)
    actor_labels: list[str] = Field(default_factory=list)

    @field_validator("employee_ids", "actor_labels", mode="before")
    @classmethod
    def deduplicate_bounded_values(cls, value):
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        # Reject an oversized raw collection before doing any de-duplication.
        # Besides making the API contract unambiguous, this keeps validation
        # linear even for an adversarial request full of unique values.
        if len(value) > 200:
            raise ValueError("at most 200 values are allowed")
        unique = []
        seen: set[str] = set()
        for item in value:
            # Let Pydantic produce the normal item-level validation error for
            # non-string JSON values instead of trying to hash them here.
            if not isinstance(item, str):
                return value
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique


class DisplayNameResolutionRead(BaseModel):
    employees: dict[str, str]
    actors: dict[str, str]
    # Structural identity beside the display string, keyed by the same actor
    # label. Only principals that are more than a tenant-issued key appear here,
    # so a console can badge ORYH's hosted agent from the kind rather than from
    # text a tenant could have typed into a key label.
    actor_kinds: dict[str, PrincipalKind] = Field(default_factory=dict)


DisplayNameResolutionEnvelope = Envelope[DisplayNameResolutionRead]


class InvitationUserRead(UserRead):
    # Returned only by the console email backend, where no real email is
    # delivered. SMTP responses omit it so one-time tokens are never exposed
    # by the production API.
    invitation_url: str | None = None
    # The invitation is committed before delivery is attempted, so a mail
    # outage used to surface as a 500 on a request that had in fact created the
    # user and the token — the caller could not tell which half happened, and
    # retrying created nothing. False means: this invitation exists and the
    # person has not been told. Same contract `PasswordResetEmailRead` keeps.
    email_sent: bool = True


InvitationUserEnvelope = Envelope[InvitationUserRead]


class PasswordResetEmailRead(BaseModel):
    user: UserRead
    email_sent: bool


PasswordResetEmailEnvelope = Envelope[PasswordResetEmailRead]


class PasswordResetRequest(RequestModel):
    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _validated_email(value)


class PasswordResetRequestRead(BaseModel):
    message: str


PasswordResetRequestEnvelope = Envelope[PasswordResetRequestRead]


class SessionResponse(BaseModel):
    session_token: str
    expires_at: datetime
    user: UserRead


class VerifyEmailResponse(BaseModel):
    tenant: TenantRead
    user: UserRead
    api_key: ApiKeyRead
    plain_text_api_key: str
    session_token: str


class PendingRegistrationRead(APIModel):
    id: str
    company_name: str
    email: str
    email_domain: str
    status: RegistrationStatus
    expires_at: datetime
    verification_sent_at: datetime
    verified_at: datetime | None = None
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    rejection_reason: str | None = None
    tenant_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class CreateEnterprisePilotApplicationRequest(RequestModel):
    company_name: str = Field(min_length=2, max_length=200)
    email: str = Field(max_length=320)
    company_size: EnterprisePilotCompanySize
    agents: list[EnterprisePilotAgent] = Field(min_length=1, max_length=5)
    other_agents: str | None = Field(default=None, max_length=500)
    agent_management: EnterprisePilotAgentManagement
    weekly_active_agent_users: int | None = Field(default=None, ge=0, le=1_000_000)
    workflows: list[EnterprisePilotWorkflow] = Field(min_length=1, max_length=7)
    other_workflow: str | None = Field(default=None, max_length=500)
    agent_write_readiness: EnterprisePilotWriteReadiness
    executive_sponsor_role: str | None = Field(default=None, max_length=200)
    pilot_timing: EnterprisePilotTiming
    notes: str | None = Field(default=None, max_length=2000)
    privacy_accepted: Literal[True]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _validated_email(value)

    @field_validator("company_name")
    @classmethod
    def normalize_company_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("company name is too short")
        return normalized

    @field_validator("agents", "workflows")
    @classmethod
    def deduplicate_choices(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @field_validator(
        "other_agents",
        "other_workflow",
        "executive_sponsor_role",
        "notes",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value):
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        return normalized or None

    @model_validator(mode="after")
    def require_other_details(self):
        if "Other" in self.agents and not self.other_agents:
            raise ValueError("describe the other agent runtime")
        if "Other" in self.workflows and not self.other_workflow:
            raise ValueError("describe the other workflow")
        return self


class EnterprisePilotApplicationRead(APIModel):
    id: str
    company_name: str
    email: str
    email_domain: str
    company_size: EnterprisePilotCompanySize
    agents: list[EnterprisePilotAgent] = Field(validation_alias="agents_jsonb")
    other_agents: str | None = None
    agent_management: EnterprisePilotAgentManagement
    weekly_active_agent_users: int | None = None
    workflows: list[EnterprisePilotWorkflow] = Field(validation_alias="workflows_jsonb")
    other_workflow: str | None = None
    agent_write_readiness: EnterprisePilotWriteReadiness
    executive_sponsor_role: str | None = None
    pilot_timing: EnterprisePilotTiming
    notes: str | None = None
    privacy_policy_version: str
    privacy_accepted_at: datetime
    acknowledgement_sent_at: datetime | None = None
    status: EnterprisePilotApplicationStatus
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    review_note: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class CreateEnterprisePilotApplicationResponse(BaseModel):
    application: EnterprisePilotApplicationRead
    acknowledgement_email_sent: bool


class ReviewEnterprisePilotApplicationRequest(RequestModel):
    status: EnterprisePilotReviewStatus
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value):
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        return normalized or None

    @model_validator(mode="after")
    def require_rejection_reason(self):
        if self.status == "rejected" and not self.note:
            raise ValueError("a rejection reason is required")
        return self


class ReviewEnterprisePilotApplicationResponse(BaseModel):
    application: EnterprisePilotApplicationRead
    notification_email_sent: bool


EnterprisePilotApplicationEnvelope = Envelope[EnterprisePilotApplicationRead]
EnterprisePilotApplicationListEnvelope = ListEnvelope[EnterprisePilotApplicationRead]
CreateEnterprisePilotApplicationEnvelope = Envelope[CreateEnterprisePilotApplicationResponse]
ReviewEnterprisePilotApplicationEnvelope = Envelope[ReviewEnterprisePilotApplicationResponse]


class RegistrationVerificationResponse(BaseModel):
    registration: PendingRegistrationRead
    message: str


RegistrationVerificationEnvelope = Envelope[RegistrationVerificationResponse]


VerifyEmailEnvelope = Envelope[VerifyEmailResponse]


PendingRegistrationListEnvelope = ListEnvelope[PendingRegistrationRead]


class RejectRegistrationRequest(RequestModel):
    reason: str = Field(min_length=2, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return " ".join(value.split())


class ReviewRegistrationResponse(BaseModel):
    registration: PendingRegistrationRead
    tenant: TenantRead | None = None
    admin_user: UserRead | None = None
    email_sent: bool


ReviewRegistrationEnvelope = Envelope[ReviewRegistrationResponse]


class InviteUserRequest(RequestModel):
    email: str = Field(max_length=320)
    name: str | None = Field(default=None, max_length=200)
    role: UserRole = "member"
    employee_id: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _validated_email(value)


class AcceptInvitationRequest(RequestModel):
    token: str = Field(max_length=200)
    password: str = Field(min_length=8, max_length=200)
    name: str | None = Field(default=None, max_length=200)


class UpdateUserRequest(RequestModel):
    name: str | None = Field(default=None, max_length=200)
    # login identifier; like invitations, exempt from the corporate-domain
    # check (external collaborators). Uniqueness enforced in the endpoint.
    email: str | None = Field(default=None, max_length=320)
    role: UserRole | None = None
    status: Literal["active", "disabled"] | None = None
    employee_id: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return _validated_email(value) if value is not None else None


class EmployeeBase(RequestModel):
    employee_code: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    timezone: str | None = Field(default=None, max_length=100)
    # 入职日期 — what 工龄 is measured from, and therefore what a leave
    # entitlement is computed against. Null means nobody stated it, which an
    # agent should ask about rather than guess around.
    hire_date: date | None = None
    status: EmployeeStatus = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateEmployeeRequest(EmployeeBase):
    name: str = Field(max_length=200)


class UpdateEmployeeRequest(EmployeeBase):
    pass


class EmployeeRead(APIModel):
    id: str
    employee_code: str | None = None
    name: str
    email: str | None = None
    timezone: str | None = None
    hire_date: date | None = None
    status: EmployeeStatus
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime | None = None


EmployeeListEnvelope = ListEnvelope[EmployeeRead]


EmployeeEnvelope = Envelope[EmployeeRead]


class RoleRead(APIModel):
    id: str
    tenant_id: str
    name: str
    title: str | None = None
    description: str | None = None
    permissions_jsonb: list[str] = Field(
        validation_alias=AliasChoices("permissions_jsonb", "permissions"),
        serialization_alias="permissions",
    )
    is_system: bool
    # how many active people hold it. `$oryh-access-admin` must state the
    # headcount before widening or narrowing a role, and deriving it needed a
    # second call plus users.manage — a mandated sentence nobody could afford
    # to say correctly.
    user_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None


RoleListEnvelope = ListEnvelope[RoleRead]


RoleEnvelope = Envelope[RoleRead]


class CreateRoleRequest(RequestModel):
    name: str = Field(max_length=50, pattern=r"^[a-z0-9_]+$")
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    permissions: list[str] = Field(default_factory=list)


class UpdateRoleRequest(RequestModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    permissions: list[str] | None = None


class CapabilityRead(APIModel):
    id: str
    name: str
    kind: Literal["system", "custom"]
    title: str | None = None
    description: str | None = None
    scopable: bool
    created_at: datetime


class CapabilityCatalog(BaseModel):
    capabilities: list[CapabilityRead]
    object_types: list[str]


CapabilityCatalogEnvelope = Envelope[CapabilityCatalog]


CapabilityEnvelope = Envelope[CapabilityRead]


class CreateCapabilityRequest(RequestModel):
    name: str = Field(max_length=100, pattern=r"^[a-z0-9_.]+$")
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class TypeOptionRead(APIModel):
    id: str
    family: str
    name: str
    kind: Literal["system", "custom"]
    title: str | None = None
    description: str | None = None
    status: Literal["active", "archived"]
    created_at: datetime
    updated_at: datetime


class CreateTypeOptionRequest(RequestModel):
    family: str
    name: TypeOptionName
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class UpdateTypeOptionRequest(RequestModel):
    # status is editable on BOTH kinds (archiving a shipped value is the
    # tenant's call); title/description only on custom rows — system rows'
    # wording follows the catalog and would be overwritten on deploy
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal["active", "archived"] | None = None


TypeOptionEnvelope = Envelope[TypeOptionRead]


TypeOptionListEnvelope = ListEnvelope[TypeOptionRead]


class PlatformAdminRead(APIModel):
    id: str
    email: str
    name: str | None = None
    status: Literal["active", "disabled"]
    created_at: datetime
    updated_at: datetime | None = None


class CreatePlatformAdminRequest(RequestModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=200)
    name: str | None = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _validated_email(value)


class AdminSessionResponse(BaseModel):
    session_token: str
    expires_at: datetime
    admin: PlatformAdminRead


class UpdateTenantAdminRequest(RequestModel):
    name: str | None = Field(default=None, max_length=200)
    status: TenantStatus | None = None


class CreateTenantAdminRequest(RequestModel):
    """Platform-operator tenant provisioning: a tenant is never created
    without its first tenant admin. An initial password is generated and
    emailed to the admin; it is never returned in the API response."""

    name: str = Field(max_length=200)
    admin_email: str = Field(max_length=320)
    admin_name: str | None = Field(default=None, max_length=200)
    # The company's own domain, when the first admin's mailbox does not carry
    # it — an external consultant setting the workspace up, say. Omitted, the
    # domain is derived from admin_email as before.
    email_domain: str | None = Field(default=None, max_length=255)

    @field_validator("admin_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _validated_email(value)

    @field_validator("email_domain")
    @classmethod
    def normalize_domain(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return company_domain(value)


class CreateTenantAdminResponse(BaseModel):
    tenant: TenantRead
    admin_user: UserRead
    # False when SMTP delivery failed: the tenant exists, use the
    # reset-password action to retry credential delivery.
    email_sent: bool


class ResetPasswordResponse(BaseModel):
    user: UserRead
    email_sent: bool


class ResetLinkResponse(BaseModel):
    user: UserRead
    reset_link: str


class CreateObjectTypeDefinitionRequest(RequestModel):
    object_type: str = Field(max_length=100)
    entity_kind: EntityKind = "business_object"
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    json_schema: dict[str, Any] = Field(default_factory=dict)
    state_machine: dict[str, Any] | None = None
    created_by: str | None = Field(default=None, max_length=100)


class UpdateObjectTypeDefinitionRequest(RequestModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    json_schema: dict[str, Any] | None = None
    state_machine: dict[str, Any] | None = None
    status: ObjectTypeDefinitionStatus | None = None


class ObjectTypeDefinitionRead(APIModel):
    id: str
    tenant_id: str
    entity_kind: EntityKind
    object_type: str
    title: str | None = None
    description: str | None = None
    json_schema: dict[str, Any]
    state_machine: dict[str, Any] | None = None
    version: int
    status: ObjectTypeDefinitionStatus
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


ObjectTypeDefinitionListEnvelope = ListEnvelope[ObjectTypeDefinitionRead]


ObjectTypeDefinitionEnvelope = Envelope[ObjectTypeDefinitionRead]


class ObjectDirectoryEntryRead(BaseModel):
    entity_kind: EntityKind
    object_type: str
    count: int = Field(ge=0)
    title: str | None = None
    definition_status: ObjectTypeDefinitionStatus | None = None


ObjectDirectoryEnvelope = ListEnvelope[ObjectDirectoryEntryRead]


class BuiltinObjectTypeRead(APIModel):
    """One shipped collection, and the words that mean it.

    `also_called` carries the singular and the handful of synonyms people reach
    for — enough for an agent to recognise "建一个 Product 对象" as this, and
    short enough that it is a hint rather than a claim to have thought of
    everything. Semantic near-misses (`merchandise`, `货品`) are not in here and
    are not meant to be: that is the judgement this endpoint exists to inform,
    not to replace.
    """

    object_type: str
    path: str
    also_called: list[str] = Field(default_factory=list)


BuiltinObjectTypeEnvelope = ListEnvelope[BuiltinObjectTypeRead]


class CreateWorkflowDefinitionRequest(RequestModel):
    entity_kind: EntityKind = "business_object"
    object_type: str = Field(max_length=100)
    name: str = Field(default="default", max_length=100)
    definition_text: str = Field(min_length=1, max_length=20000)
    created_by: str | None = Field(default=None, max_length=100)


class WorkflowDefinitionRead(APIModel):
    id: str
    tenant_id: str
    entity_kind: EntityKind
    object_type: str
    name: str
    version: int
    definition_text: str
    status: Literal["active", "superseded"]
    created_by: str | None = None
    created_at: datetime


WorkflowDefinitionListEnvelope = ListEnvelope[WorkflowDefinitionRead]


WorkflowDefinitionEnvelope = Envelope[WorkflowDefinitionRead]


FlowRunTrigger = Literal["cadence", "signal", "manual"]
FlowRunStatus = Literal["running", "succeeded", "failed", "skipped"]


class FlowSubscriptionRead(APIModel):
    id: str
    tenant_id: str
    entity_type: str
    driver_skill: str
    queue_filter: dict[str, Any] = Field(
        validation_alias=AliasChoices("queue_filter", "queue_filter_jsonb")
    )
    cadence_seconds: int
    enabled: bool
    api_key_id: str | None = None
    created_by: str | None = None
    unmoved_runs: int = 0
    parked_at: datetime | None = None
    parked_reason: str | None = None
    # When a runner last reported anything for this subscription. An enabled
    # subscription writes at least an hourly "looked, nothing here" row, so a
    # last run long in the past means nobody is driving it — which `enabled`
    # alone cannot tell you, since that only says the tenant has not switched it
    # off. Reported as the fact; how stale counts as dead is the reader's call,
    # because the heartbeat interval is the runner's configuration and not
    # something the record layer knows.
    last_run_at: datetime | None = None
    # Where this subscription's work queue lives, and which workflow-definition
    # namespace its map is in. Told to the runner rather than looked up there:
    # the runner used to hold its own entity_type → path table, in a process
    # that cannot import this one, and it went stale exactly the way a second
    # copy does. An unlisted type fell through to `/business-objects`, which
    # answers nothing, which reads as an empty queue — so a subscription that
    # could never work was indistinguishable from one with nothing to do.
    queue_path: str | None = None
    entity_kind: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _locate_queue(self) -> "FlowSubscriptionRead":
        """Derived here rather than at each of the seven call sites that
        serialize this, so the one added next month cannot omit it."""
        builtin_path = BUILTIN_QUEUE_PATHS.get(self.entity_type)
        self.queue_path = builtin_path or "/business-objects"
        self.entity_kind = "builtin" if builtin_path else "business_object"
        return self


FlowSubscriptionListEnvelope = ListEnvelope[FlowSubscriptionRead]
FlowSubscriptionEnvelope = Envelope[FlowSubscriptionRead]


class CreateFlowSubscriptionRequest(RequestModel):
    entity_type: str = Field(max_length=100)
    driver_skill: str = Field(max_length=150)
    queue_filter: dict[str, Any] = Field(default_factory=lambda: {"status": "submitted"})
    cadence_seconds: int = Field(default=300, ge=30, le=86_400)
    api_key_id: str | None = None


class UpdateFlowSubscriptionRequest(RequestModel):
    """Platform-side edits. The tenant's own PATCH accepts `enabled` only."""

    driver_skill: str | None = Field(default=None, max_length=150)
    queue_filter: dict[str, Any] | None = None
    cadence_seconds: int | None = Field(default=None, ge=30, le=86_400)
    enabled: bool | None = None
    api_key_id: str | None = None
    # The operator's "the reason is dealt with, let it spend again". The
    # endpoint has always read this field and the console has always sent it —
    # it was simply never declared, so `RequestModel`'s extra_forbidden made the
    # console's Clear park button raise before it reached the API and made the
    # JSON caller's `clear_park` silently vanish. A parked subscription could
    # only be revived by the tenant toggling it off and on, or by SQL.
    clear_park: bool = False


class ReportDriverStateRequest(RequestModel):
    """The runner's own operational bookkeeping about one subscription.

    The threshold that decides when to give up is the runner's policy, not the
    record layer's, so the runner counts and reports rather than asking the
    server to count for it.
    """

    unmoved_runs: int = Field(ge=0)
    parked: bool = False
    parked_reason: str | None = Field(default=None, max_length=2000)


class TenantUpdateFlowSubscriptionRequest(RequestModel):
    """What a tenant may change about a service the platform runs for them:
    whether it runs at all. Everything else is the subscription's terms."""

    enabled: bool


class FlowRunRead(APIModel):
    id: str
    tenant_id: str
    subscription_id: str | None = None
    entity_type: str
    trigger: FlowRunTrigger
    status: FlowRunStatus
    started_at: datetime
    finished_at: datetime | None = None
    queue_size: int | None = None
    items_advanced: int | None = None
    error: str | None = None
    detail: dict[str, Any] = Field(
        validation_alias=AliasChoices("detail", "detail_jsonb"),
        serialization_alias="detail",
    )
    recorded_by: str | None = None
    created_at: datetime


FlowRunListEnvelope = ListEnvelope[FlowRunRead]
FlowRunEnvelope = Envelope[FlowRunRead]


class OpenFlowRunRequest(RequestModel):
    entity_type: str = Field(max_length=100)
    subscription_id: str | None = None
    trigger: FlowRunTrigger = "cadence"
    started_at: datetime
    queue_size: int | None = Field(default=None, ge=0)
    detail: dict[str, Any] = Field(default_factory=dict)


class CloseFlowRunRequest(RequestModel):
    status: Literal["succeeded", "failed", "skipped"]
    finished_at: datetime
    items_advanced: int | None = Field(default=None, ge=0)
    error: str | None = Field(default=None, max_length=4000)
    detail: dict[str, Any] | None = None


class AuditLogRead(APIModel):
    id: int
    action: str
    entity_type: str
    entity_id: str
    actor: str | None = None
    detail_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("detail_jsonb", "detail"),
        serialization_alias="detail",
    )
    created_at: datetime


_SKILL_NAME_RE = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class TenantSkillBase(RequestModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


DistributionMode = Literal["capability", "targeted"]


class CreateTenantSkillRequest(TenantSkillBase):
    name: str = Field(max_length=100, pattern=_SKILL_NAME_RE)
    files: dict[str, str]
    required_capability: str | None = Field(default=None, max_length=100)
    # new skills reach whoever the capability allows; narrowing to an audience
    # is a deliberate second step, never a default
    distribution_mode: DistributionMode = "capability"
    created_by: str | None = Field(default=None, max_length=100)


class UpdateTenantSkillRequest(TenantSkillBase):
    files: dict[str, str] | None = None
    required_capability: str | None = Field(default=None, max_length=100)
    distribution_mode: DistributionMode | None = None
    # The workspace's refinement of a skill it did not write. Unlike `files`,
    # setting this does NOT fork a product skill — that is the whole point:
    # a preference should not cost every future catalog update. Empty string
    # clears it.
    calibration: str | None = Field(default=None, max_length=4000)
    status: Literal["active", "archived"] | None = None


class TenantSkillRead(APIModel):
    id: str
    tenant_id: str
    name: str
    kind: Literal["product", "custom"]
    title: str | None = None
    description: str | None = None
    required_capability: str | None = None
    calibration: str | None = None
    # the shipped catalog's gate for a product skill (null on custom) — what
    # required_capability returns to if the tenant resets it to resume
    # tracking the catalog
    catalog_required_capability: str | None = None
    files_jsonb: dict[str, str] = Field(
        validation_alias=AliasChoices("files_jsonb", "files"),
        serialization_alias="files",
    )
    distribution_mode: DistributionMode = "capability"
    version: int
    status: Literal["active", "archived"]
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    # who it is currently aimed at, so a detail view needs no second call
    audience: "SkillAudienceSummary | None" = None


class SkillAudienceSummary(APIModel):
    """Enough for a list row: the role names, and how many individuals."""

    roles: list[str] = Field(default_factory=list)
    user_count: int = 0


class TenantSkillSummary(APIModel):
    id: str
    name: str
    kind: Literal["product", "custom"]
    title: str | None = None
    description: str | None = None
    required_capability: str | None = None
    distribution_mode: DistributionMode = "capability"
    audience: SkillAudienceSummary | None = None
    version: int
    status: Literal["active", "archived"]
    updated_at: datetime | None = None


class CreateSkillAssignmentRequest(RequestModel):
    subject_type: Literal["user", "role"]
    subject_id: str = Field(min_length=1, max_length=100)


class SkillAssignmentRead(APIModel):
    id: str
    skill_id: str
    subject_type: Literal["user", "role"]
    subject_id: str
    # resolved for display so the console never has to join by hand
    subject_label: str | None = None
    # people this row brings in who CANNOT run the skill — their role lacks
    # required_capability, so they would install it and 403 on every call
    blocked_members: list[str] = Field(default_factory=list)
    created_by: str | None = None
    created_at: datetime


class SkillAudienceImpact(APIModel):
    """What changing the audience would do, computed before anyone commits.

    `losing` is the one that gets missed: switching a skill from capability
    mode to targeted takes it away from everyone left out, and nobody
    complains about a skill they silently stopped receiving.
    """

    distribution_mode: DistributionMode
    reaches_now: list[str] = Field(default_factory=list)
    would_reach: list[str] = Field(default_factory=list)
    gaining: list[str] = Field(default_factory=list)
    losing: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)


class SkillAudienceRead(APIModel):
    assignments: list[SkillAssignmentRead] = Field(default_factory=list)
    impact: SkillAudienceImpact


SkillReachReason = Literal[
    # received
    "capability",  # passes required_capability, and the skill targets nobody
    "targeted_role",  # named through a role in the audience
    "targeted_user",  # named individually
    # withheld
    "missing_capability",  # role does not grant required_capability
    "not_in_audience",  # could run it, but the skill is targeted elsewhere
]


class SkillReachEntry(APIModel):
    name: str
    title: str | None = None
    # What the skill is FOR, in the words its author used. `title` is a label
    # ("Oryh Payroll"); this is the sentence an agent matches a request against
    # — "生成工资条 for a period" is what makes 做工资单 find it. A withheld
    # entry without it is a name the agent cannot connect to anything it was
    # asked to do, which is the whole failure this field exists to prevent.
    description: str | None = None
    kind: Literal["product", "custom"]
    required_capability: str | None = None
    distribution_mode: DistributionMode
    received: bool
    # every reason that applies. A withheld skill can fail both axes at once,
    # and fixing only the one named leaves it exactly as unreachable.
    reasons: list[SkillReachReason]
    # which audience rows put the subject in scope ("user", "role:<name>")
    named_via: list[str] = Field(default_factory=list)
    # for missing_capability: roles in this tenant that DO hold the gate. A
    # fact for an admin deciding whom to copy — NOT a suggestion that the
    # subject ask to be made one of them, which is usually an escalation.
    granted_by_roles: list[str] = Field(default_factory=list)


class SkillReachRead(APIModel):
    """Which skills a person or role receives, and why not for the rest.

    The withheld half is the point. "Why doesn't my agent have that skill" is
    otherwise answerable only by deriving the capability matrix by hand.
    """

    subject_type: Literal["user", "role"]
    subject_id: str
    subject_label: str
    # the role whose grants were used; for a user subject, the role they hold
    role: str | None = None
    received: list[SkillReachEntry] = Field(default_factory=list)
    withheld: list[SkillReachEntry] = Field(default_factory=list)


SkillReachEnvelope = Envelope[SkillReachRead]
SkillAudienceEnvelope = Envelope[SkillAudienceRead]
SkillAssignmentEnvelope = Envelope[SkillAssignmentRead]
TenantSkillListEnvelope = ListEnvelope[TenantSkillSummary]


TenantSkillEnvelope = Envelope[TenantSkillRead]


class BusinessObjectBase(RequestModel):
    object_type: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)
    source_text: str | None = Field(default=None, max_length=10000)
    status: BusinessObjectStatus = "open"
    created_by: str | None = Field(default=None, max_length=100)


class CreateBusinessObjectRequest(BusinessObjectBase):
    object_type: str = Field(max_length=100)
    title: str = Field(max_length=200)


class UpdateBusinessObjectRequest(RequestModel):
    object_type: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
    payload: dict[str, Any] | None = None
    source_text: str | None = Field(default=None, max_length=10000)
    status: BusinessObjectStatus | None = None
    created_by: str | None = Field(default=None, max_length=100)


class DeleteBusinessObjectRequest(RequestModel):
    deleted_by: str | None = Field(default=None, max_length=100)
    delete_reason: str | None = Field(default=None, max_length=2000)


class RestoreBusinessObjectRequest(RequestModel):
    restored_by: str | None = Field(default=None, max_length=100)


class BusinessObjectRead(APIModel):
    id: str
    object_type: str
    title: str
    summary: str | None = None
    payload_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("payload_jsonb", "payload"),
        serialization_alias="payload",
    )
    source_text: str | None = None
    status: BusinessObjectStatus
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    deleted_by: str | None = None
    delete_reason: str | None = None


BusinessObjectListEnvelope = ListEnvelope[BusinessObjectRead]


BusinessObjectEnvelope = Envelope[BusinessObjectRead]


class ApprovalTargetBase(RequestModel):
    target_type: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)
    source_text: str | None = Field(default=None, max_length=10000)
    status: ApprovalTargetStatus = "open"
    created_by: str | None = Field(default=None, max_length=100)


class CreateApprovalTargetRequest(ApprovalTargetBase):
    target_type: str = Field(max_length=100)
    title: str = Field(max_length=200)


class UpdateApprovalTargetRequest(RequestModel):
    target_type: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
    payload: dict[str, Any] | None = None
    source_text: str | None = Field(default=None, max_length=10000)
    status: ApprovalTargetStatus | None = None
    created_by: str | None = Field(default=None, max_length=100)


DeleteApprovalTargetRequest = DeleteBusinessObjectRequest
RestoreApprovalTargetRequest = RestoreBusinessObjectRequest


class ApprovalTargetRead(BusinessObjectRead):
    object_type: str = Field(
        validation_alias=AliasChoices("object_type", "target_type"),
        exclude=True,
    )
    target_type: str = Field(validation_alias=AliasChoices("object_type", "target_type"))


ApprovalTargetListEnvelope = ListEnvelope[ApprovalTargetRead]


ApprovalTargetEnvelope = Envelope[ApprovalTargetRead]


class CreateBusinessObjectLinkRequest(RequestModel):
    source_object_id: str
    target_object_id: str
    link_type: str = Field(max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BusinessObjectLinkRead(APIModel):
    id: str
    source_object_id: str
    target_object_id: str
    link_type: str
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime


BusinessObjectLinkListEnvelope = ListEnvelope[BusinessObjectLinkRead]


BusinessObjectLinkEnvelope = Envelope[BusinessObjectLinkRead]


class ResourceBookingBase(RequestModel):
    resource_id: str | None = None
    booked_by_employee_id: str | None = None
    booking_type: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    start_at: datetime | None = None
    end_at: datetime | None = None
    quantity: int = Field(default=1, ge=1)
    status: ResourceBookingStatus = "confirmed"
    source_text: str | None = Field(default=None, max_length=10000)
    notes: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("end_at")
    @classmethod
    def validate_booking_period(cls, value: datetime | None, info):
        start = info.data.get("start_at")
        if value is not None and start is not None and value <= start:
            raise ValueError("end_at must be greater than start_at")
        return value


class CreateResourceBookingRequest(ResourceBookingBase):
    resource_id: str
    booked_by_employee_id: str
    title: str = Field(max_length=200)
    start_at: datetime
    end_at: datetime


class UpdateResourceBookingRequest(RequestModel):
    booking_type: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    start_at: datetime | None = None
    end_at: datetime | None = None
    quantity: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=2000)
    source_text: str | None = Field(default=None, max_length=10000)
    metadata: dict[str, Any] | None = None

    @field_validator("end_at")
    @classmethod
    def validate_update_booking_period(cls, value: datetime | None, info):
        start = info.data.get("start_at")
        if value is not None and start is not None and value <= start:
            raise ValueError("end_at must be greater than start_at")
        return value


class DeleteResourceBookingRequest(RequestModel):
    cancelled_by: str | None = Field(default=None, max_length=100)
    cancel_reason: str | None = Field(default=None, max_length=2000)


class ResourceBookingRead(APIModel):
    id: str
    resource_id: str
    booked_by_employee_id: str
    booking_type: str | None = None
    title: str
    start_at: datetime
    end_at: datetime
    quantity: int
    status: ResourceBookingStatus
    source_text: str | None = None
    notes: str | None = None
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancelled_by: str | None = None
    cancel_reason: str | None = None


ResourceBookingListEnvelope = ListEnvelope[ResourceBookingRead]


class ResourceAvailabilityRead(BaseModel):
    resource_id: str
    start_at: datetime
    end_at: datetime
    booking_mode: BookingMode
    available: bool
    available_quantity: int | None = None
    conflicting_booking_ids: list[str] = Field(default_factory=list)


class TimesheetHeaderBase(RequestModel):
    employee_id: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    status: TimesheetStatus = "draft"
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("period_end")
    @classmethod
    def validate_period(cls, value: date | None, info):
        start = info.data.get("period_start")
        if value is not None and start is not None and value < start:
            raise ValueError("period_end must be greater than or equal to period_start")
        return value


class CreateTimesheetHeaderRequest(TimesheetHeaderBase):
    employee_id: str
    period_start: date
    period_end: date
    # the whole document in one request: rows ride the same transaction, so a
    # half-filled draft can no longer be left behind by a crash mid-entries,
    # and an agent stops spending one turn (~12s) per line
    entries: list[TimesheetEntryBase] = Field(default_factory=list, max_length=100)


class UpdateTimesheetHeaderRequest(RequestModel):
    status: TimesheetStatus | None = None
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] | None = None


class DeleteTimesheetHeaderRequest(RequestModel):
    deleted_by: str | None = Field(default=None, max_length=100)
    delete_reason: str | None = Field(default=None, max_length=2000)


class RestoreTimesheetHeaderRequest(RequestModel):
    restored_by: str | None = Field(default=None, max_length=100)


class SubmitTimesheetRequest(RequestModel):
    submitted_by: str | None = None
    source: SourceType | None = None


class TimesheetHeaderRead(APIModel):
    id: str
    employee_id: str
    period_start: date
    period_end: date
    status: TimesheetStatus
    submitted_at: datetime | None = None
    source_report_text: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime | None = None


TimesheetHeaderListEnvelope = ListEnvelope[TimesheetHeaderRead]


class CreateEmployeeLeaveRequest(RequestModel):
    """One absence. Note what is NOT here: any statement about entitlement.

    The server is not told, and does not ask, how many days this person has —
    that follows from the tenant's leave policy applied to their 工龄 and their
    other leave, and it is recomputed every time somebody wants to know. A
    request that exceeds the allowance is still a legal record of a request;
    whether it is granted is the approver's call, informed by the same
    computation.
    """

    employee_id: str
    # a `leave_type` type-option value, validated against the tenant's list
    leave_type: str = Field(max_length=50)
    from_date: date
    thru_date: date
    # Days, halves allowed. The agent computes it from the tenant's rules about
    # weekends and holidays BEFORE filing; the server records the figure that
    # was agreed rather than subtracting two dates itself.
    duration_days: float = Field(gt=0)
    reason: str | None = Field(default=None, max_length=2000)
    status: LeaveStatus = "draft"
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class UpdateEmployeeLeaveRequest(RequestModel):
    leave_type: str | None = Field(default=None, max_length=50)
    from_date: date | None = None
    thru_date: date | None = None
    duration_days: float | None = Field(default=None, gt=0)
    reason: str | None = Field(default=None, max_length=2000)
    status: LeaveStatus | None = None
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] | None = None


class DeleteEmployeeLeaveRequest(RequestModel):
    deleted_by: str | None = Field(default=None, max_length=100)
    delete_reason: str | None = Field(default=None, max_length=2000)


class EmployeeLeaveRead(APIModel):
    id: str
    employee_id: str
    leave_type: str
    from_date: date
    thru_date: date
    duration_days: float
    reason: str | None = None
    status: LeaveStatus
    submitted_at: datetime | None = None
    source_report_text: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime | None = None


EmployeeLeaveListEnvelope = ListEnvelope[EmployeeLeaveRead]
EmployeeLeaveEnvelope = Envelope[EmployeeLeaveRead]


class TimesheetEntryBase(RequestModel):
    header_id: str | None = None
    employee_id: str | None = None
    work_date: date | None = None
    project_id: str | None = None
    project_name_snapshot: str | None = Field(default=None, max_length=200)
    client: str | None = Field(default=None, max_length=200)
    task: str | None = Field(default=None, max_length=200)
    hours: float | None = Field(default=None, gt=0, le=24)
    work_type: WorkType = "regular"
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreateTimesheetEntryRequest(TimesheetEntryBase):
    header_id: str
    employee_id: str
    work_date: date
    hours: float = Field(gt=0, le=24)


class UpdateTimesheetEntryRequest(RequestModel):
    project_id: str | None = None
    project_name_snapshot: str | None = Field(default=None, max_length=200)
    client: str | None = Field(default=None, max_length=200)
    task: str | None = Field(default=None, max_length=200)
    hours: float | None = Field(default=None, gt=0, le=24)
    work_type: WorkType | None = None
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] | None = None


class TimesheetEntryRead(APIModel):
    id: str
    header_id: str
    employee_id: str
    work_date: date
    project_id: str | None = None
    project_name_snapshot: str | None = None
    client: str | None = None
    task: str | None = None
    hours: float
    work_type: WorkType
    notes: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime | None = None


class ExpenseClaimBase(RequestModel):
    employee_id: str | None = None
    title: str | None = Field(default=None, max_length=200)
    claim_date: date | None = None
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    status: ExpenseStatus = "draft"
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreateExpenseClaimRequest(ExpenseClaimBase):
    employee_id: str
    items: list[ExpenseItemBase] = Field(default_factory=list, max_length=100)
    title: str = Field(max_length=200)


class UpdateExpenseClaimRequest(RequestModel):
    title: str | None = Field(default=None, max_length=200)
    claim_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    status: ExpenseStatus | None = None
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] | None = None


class DeleteExpenseClaimRequest(RequestModel):
    deleted_by: str | None = Field(default=None, max_length=100)
    delete_reason: str | None = Field(default=None, max_length=2000)


class RestoreExpenseClaimRequest(RequestModel):
    restored_by: str | None = Field(default=None, max_length=100)


class SubmitExpenseClaimRequest(RequestModel):
    submitted_by: str | None = None
    source: SourceType | None = None


class ExpenseClaimRead(APIModel):
    id: str
    employee_id: str
    title: str
    claim_date: date | None = None
    currency: str
    status: ExpenseStatus
    submitted_at: datetime | None = None
    source_report_text: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime | None = None


ExpenseClaimListEnvelope = ListEnvelope[ExpenseClaimRead]


class ExpenseItemBase(RequestModel):
    claim_id: str | None = None
    employee_id: str | None = None
    expense_date: date | None = None
    category: ExpenseCategory = "other"
    amount: float | None = Field(default=None, gt=0, le=9_999_999.99)
    tax_amount: float | None = Field(default=None, ge=0, le=9_999_999.99)
    vendor_id: str | None = None
    merchant: str | None = Field(default=None, max_length=200)
    invoice_number: str | None = Field(default=None, max_length=100)
    invoice_type: InvoiceType | None = None
    project_id: str | None = None
    project_name_snapshot: str | None = Field(default=None, max_length=200)
    client: str | None = Field(default=None, max_length=200)
    attachment_id: str | None = None
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreateExpenseItemRequest(ExpenseItemBase):
    claim_id: str
    employee_id: str
    expense_date: date
    amount: float = Field(gt=0, le=9_999_999.99)


class UpdateExpenseItemRequest(RequestModel):
    expense_date: date | None = None
    category: ExpenseCategory | None = None
    amount: float | None = Field(default=None, gt=0, le=9_999_999.99)
    tax_amount: float | None = Field(default=None, ge=0, le=9_999_999.99)
    vendor_id: str | None = None
    merchant: str | None = Field(default=None, max_length=200)
    invoice_number: str | None = Field(default=None, max_length=100)
    invoice_type: InvoiceType | None = None
    project_id: str | None = None
    project_name_snapshot: str | None = Field(default=None, max_length=200)
    client: str | None = Field(default=None, max_length=200)
    attachment_id: str | None = None
    extracted_fields: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] | None = None


class ExpenseItemRead(APIModel):
    id: str
    claim_id: str
    employee_id: str
    expense_date: date
    category: ExpenseCategory
    amount: float
    tax_amount: float | None = None
    vendor_id: str | None = None
    merchant: str | None = None
    invoice_number: str | None = None
    invoice_type: InvoiceType | None = None
    project_id: str | None = None
    project_name_snapshot: str | None = None
    client: str | None = None
    attachment_id: str | None = None
    extracted_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("extracted_fields_jsonb", "extracted_fields"),
        serialization_alias="extracted_fields",
    )
    notes: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime | None = None


class ExpenseItemDetailRead(ExpenseItemRead):
    """Expense line enriched for review screens without changing the write model."""

    vendor_name: str | None = None


class PurchaseRequestBase(RequestModel):
    employee_id: str | None = None
    title: str | None = Field(default=None, max_length=200)
    request_date: date | None = None
    needed_by: date | None = None
    vendor_id: str | None = None
    vendor_name_snapshot: str | None = Field(default=None, max_length=200)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    status: PurchaseStatus = "draft"
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreatePurchaseRequestRequest(PurchaseRequestBase):
    employee_id: str
    title: str = Field(max_length=200)
    items: list[PurchaseRequestItemBase] = Field(default_factory=list, max_length=200)


class UpdatePurchaseRequestRequest(RequestModel):
    title: str | None = Field(default=None, max_length=200)
    request_date: date | None = None
    needed_by: date | None = None
    vendor_id: str | None = None
    vendor_name_snapshot: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    status: PurchaseStatus | None = None
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] | None = None


class DeletePurchaseRequestRequest(RequestModel):
    deleted_by: str | None = Field(default=None, max_length=100)
    delete_reason: str | None = Field(default=None, max_length=2000)


class RestorePurchaseRequestRequest(RequestModel):
    restored_by: str | None = Field(default=None, max_length=100)


class SubmitPurchaseRequestRequest(RequestModel):
    submitted_by: str | None = None
    source: SourceType | None = None


class PurchaseRequestRead(APIModel):
    id: str
    employee_id: str
    title: str
    request_date: date | None = None
    needed_by: date | None = None
    vendor_id: str | None = None
    vendor_name_snapshot: str | None = None
    currency: str
    status: PurchaseStatus
    submitted_at: datetime | None = None
    source_report_text: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime | None = None


PurchaseRequestListEnvelope = ListEnvelope[PurchaseRequestRead]


class PurchaseRequestItemBase(RequestModel):
    request_id: str | None = None
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = Field(default=None, max_length=200)
    spec: str | None = Field(default=None, max_length=200)
    quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    unit: str | None = Field(default=None, max_length=50)
    unit_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    amount: float | None = Field(default=None, ge=0, le=9_999_999.99)
    # 按单采购: the confirmed sales order line this purchase line fulfils
    sales_order_item_id: str | None = None
    attachment_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreatePurchaseRequestItemRequest(PurchaseRequestItemBase):
    request_id: str
    quantity: float = Field(gt=0, le=9_999_999.99)


class UpdatePurchaseRequestItemRequest(RequestModel):
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = Field(default=None, max_length=200)
    spec: str | None = Field(default=None, max_length=200)
    quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    unit: str | None = Field(default=None, max_length=50)
    unit_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    amount: float | None = Field(default=None, ge=0, le=9_999_999.99)
    # explicit null detaches the line from the sales order (back to stock)
    sales_order_item_id: str | None = None
    attachment_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] | None = None


class PurchaseRequestItemRead(APIModel):
    id: str
    request_id: str
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = None
    spec: str | None = None
    quantity: float
    unit: str | None = None
    unit_price: float | None = None
    amount: float | None = None
    sales_order_item_id: str | None = None
    attachment_id: str | None = None
    notes: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime | None = None


class PurchaseProductReferenceRead(BaseModel):
    id: str
    product_code: str | None = None
    name: str
    spec: str | None = None
    unit: str | None = None


class PurchaseSkuReferenceRead(BaseModel):
    id: str
    product_id: str
    sku_code: str | None = None
    variant_attrs: dict[str, Any] = Field(default_factory=dict)


class PurchaseSalesOrderReferenceRead(BaseModel):
    """Where a procure-to-order line came from — the fact a purchase
    reviewer routes on (按着订单审采购)."""

    sales_order_item_id: str
    order_id: str
    order_no: str | None = None
    order_status: str
    customer_name_snapshot: str | None = None
    quantity: float


class LinkedPurchaseOrderItemRead(BaseModel):
    """A PO line ordering this request line — with the PO's status and the
    received progress, the two facts 按单采购 traceability runs on."""

    id: str
    po_id: str
    po_number: str
    po_status: str
    quantity: float
    received_quantity: float
    unit_price: float | None = None


class PurchaseRequestItemDetailRead(PurchaseRequestItemRead):
    """Purchase line plus tenant-scoped catalog labels used by reviewers."""

    product: PurchaseProductReferenceRead | None = None
    sku: PurchaseSkuReferenceRead | None = None
    sku_pending: bool = False
    # resolved when the line is pinned to a confirmed sales order line
    sales_order: PurchaseSalesOrderReferenceRead | None = None
    # PO lines ordering this line, oldest first
    purchase_order_items: list[LinkedPurchaseOrderItemRead] = Field(default_factory=list)


class CreateAttachmentRequest(RequestModel):
    filename: str = Field(max_length=255)
    content_type: str = Field(max_length=100)
    content_base64: str


class AttachmentRead(APIModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by: str | None = None
    created_at: datetime


class ApprovalHandoffRequest(RequestModel):
    """Who holds the document next, stated in the call that decides it.

    Same fields `POST /todos` takes, minus the two the approval fact already
    knows: what it points at. There is no `status` — a handoff opens work.
    """

    employee_id: str
    title: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    todo_type: str | None = Field(default=None, max_length=50)
    due_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateApprovalRecordRequest(RequestModel):
    entity_type: ApprovalEntityType
    entity_id: str
    round_no: int = Field(default=1, ge=1)
    sequence_no: int = Field(default=1, ge=1)
    action: ApprovalAction
    approver_id: str | None = None
    approver_role: str | None = Field(default=None, max_length=100)
    comment: str | None = Field(default=None, max_length=2000)
    source: SourceType | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    # The other two thirds of a round transition, optional and atomic.
    #
    # Recording a `returned` fact is one call; moving the document to
    # `returned` is a second; opening the submitter's rework todo is a third.
    # Every approval-flow skill spells all three out in order, and the first
    # one landing without the others is a document whose trail says one thing
    # and whose status says another, with nobody assigned to it — which is what
    # HKG-015 looked like from the console.
    #
    # The server still decides nothing here. Which status, and whose queue the
    # document lands in, are the flow agent's judgment exactly as before; this
    # only lets it state them in the call that already carries the decision, so
    # the three facts commit together or not at all.
    document_status: str | None = Field(default=None, max_length=30)
    handoff: ApprovalHandoffRequest | None = None
    # Omit it. The server stamps the moment of the call, which is what the
    # decision moment is for every approval made through this API.
    #
    # It was required, and a required timestamp is a question an agent cannot
    # answer — it has no clock, so it took the most plausible date in front of
    # it, usually one off the document being approved. That is how production
    # acquired approvals recorded before their target existed. Supply it only
    # when the person you act for said the decision happened at another time;
    # the server refuses a future time and one before the target existed.
    acted_at: datetime | None = None


class ApprovalRecordRead(APIModel):
    id: str
    entity_type: ApprovalEntityType
    entity_id: str
    round_no: int
    sequence_no: int
    action: ApprovalAction
    # Historical conflict closure is operator-only remediation metadata; the
    # create request deliberately has no matching field.
    historical_conflict_closed: bool = False
    approver_id: str | None = None
    approver_role: str | None = None
    comment: str | None = None
    source: SourceType | None = None
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    acted_at: datetime
    created_at: datetime


ApprovalRecordListEnvelope = ListEnvelope[ApprovalRecordRead]


ApprovalRecordEnvelope = Envelope[ApprovalRecordRead]


class UpdateTodoRequest(RequestModel):
    status: TodoStatus | None = None
    completed_by: str | None = Field(default=None, max_length=100)
    due_at: datetime | None = None


class CreateTodoRequest(RequestModel):
    employee_id: str
    entity_type: TodoEntityType
    entity_id: str
    title: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    todo_type: str | None = Field(default=None, max_length=50)
    status: TodoStatus = "open"
    due_at: datetime | None = None
    created_by: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BulkTodoCreateRequest(RequestModel):
    """A routing decision applied to many records at once.

    The flow agent's only write was one todo per call, so a queue of three
    hundred timesheets that all follow the same map cost three hundred
    round-trips plus a round of reasoning apiece. Its reads were already
    batchable — the queue comes back in one list and `GET /approval-records`
    takes the entity type alone — so this was the one leg that stayed serial.

    `on_error` defaults to `skip` rather than `abort`, which is the opposite of
    master data and the same as document import, for a reason that is specific
    to assignment: the likely failure is one record having moved on since the
    agent read the queue, and aborting the batch for it would discard forty-nine
    correct assignments and then fail identically on the retry. Skipping leaves
    that one in the queue, where the next pass rediscovers it — the same
    self-healing the whole work-queue design rests on.

    Each item is the SAME `CreateTodoRequest` the single endpoint takes, and
    runs through the same guards. Descriptions stay per-record: what an approver
    needs to see is what this document says, and a shared sentence would make
    every todo in the batch equally uninformative.
    """

    items: list[CreateTodoRequest] = Field(min_length=1, max_length=BULK_MAX_ROWS)
    on_error: Literal["abort", "skip"] = "skip"


class BulkTodoRowResult(APIModel):
    """Per-item outcome, keyed by the entity the todo points at — that is what
    an agent matches back to its own list, the way a spreadsheet row is matched
    by its code."""

    index: int
    entity_id: str | None = None
    # `unchanged` is the idempotent case the single endpoint already has: the
    # same assignment already open, handed back rather than refused.
    outcome: Literal["created", "unchanged", "error"]
    id: str | None = None
    error: str | None = None


class BulkTodoSummary(APIModel):
    total: int
    created: int
    unchanged: int
    failed: int


class BulkTodoResult(APIModel):
    applied: bool
    summary: BulkTodoSummary
    results: list[BulkTodoRowResult]


BulkTodoEnvelope = Envelope[BulkTodoResult]


class TodoLastApproval(APIModel):
    """The newest approval fact on the todo's target — enough for the one-line
    "经理已批，正在财务复核" a briefing needs, without a per-todo detail call."""

    action: str
    round_no: int
    sequence_no: int
    approver_name: str | None = None
    approver_role: str | None = None
    comment: str | None = None
    acted_at: datetime | None = None


class TodoTargetSummary(APIModel):
    """What the todo points at, summarized. Requested with `?include=target`.

    The check-in used to spend one detail call per todo to learn exactly this
    much — the only part of it that grew with how busy the person was. The
    summary carries the same facts the target's own detail endpoint would show
    the same caller, so it widens nothing.
    """

    object_type: str
    title: str | None = None
    status: str | None = None
    employee_id: str | None = None
    employee_name: str | None = None
    # one number per family: document total, summed item amounts, or summed
    # hours for a timesheet — `unit` says which
    amount: float | None = None
    unit: str | None = None
    currency: str | None = None
    customer_name: str | None = None
    approval_count: int = 0
    last_approval: TodoLastApproval | None = None
    # no row of this type carries this id at all. Either the id never named
    # anything here, or the row was removed by something other than the API.
    # This is a data-integrity report, not a workflow state.
    missing: bool = False
    # the row exists and is soft-deleted, so its own detail endpoint answers
    # 404 while this list happily described it. That disagreement is what the
    # flag exists to end: an agent that reads a target here and then fetches it
    # got a summary and then nothing, with no way to tell a deletion from an
    # outage.
    #
    # Deleting a document cancels its open todos, so an open todo on a deleted
    # target is from before that was true, or from a route that bypassed the
    # API. Either way it is worth a person's attention rather than an agent's
    # cleanup — `_common/stale-todo-sweep.md` tells agents to report these and
    # not to close them.
    deleted: bool = False


class TodoRead(APIModel):
    id: str
    employee_id: str
    entity_type: TodoEntityType
    entity_id: str
    title: str
    description: str | None = None
    todo_type: str | None = None
    status: TodoStatus
    due_at: datetime | None = None
    created_by: str | None = None
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    completed_by: str | None = None
    # present only when the list was asked for it (?include=target)
    target: TodoTargetSummary | None = None


TodoListEnvelope = ListEnvelope[TodoRead]


TodoEnvelope = Envelope[TodoRead]


class BusinessObjectDetailRead(BaseModel):
    business_object: BusinessObjectRead
    links: list[BusinessObjectLinkRead]
    approval_records: list[ApprovalRecordRead]
    todos: list[TodoRead]
    audit_logs: list[AuditLogRead]
    object_type_definition: ObjectTypeDefinitionRead | None = None
    workflow_definitions: list[WorkflowDefinitionRead]


BusinessObjectDetailEnvelope = Envelope[BusinessObjectDetailRead]


class TimesheetDetailRead(BaseModel):
    header: TimesheetHeaderRead
    entries: list[TimesheetEntryRead]
    approval_records: list[ApprovalRecordRead]


class ExpenseClaimDetailRead(BaseModel):
    claim: ExpenseClaimRead
    items: list[ExpenseItemDetailRead]
    approval_records: list[ApprovalRecordRead]
    attachments: list[AttachmentRead]
    total_amount: float
    total_tax_amount: float


ExpenseClaimDetailEnvelope = Envelope[ExpenseClaimDetailRead]


class PurchaseRequestDetailRead(BaseModel):
    request: PurchaseRequestRead
    items: list[PurchaseRequestItemDetailRead]
    approval_records: list[ApprovalRecordRead]
    attachments: list[AttachmentRead]
    # pricing is optional per line, so the total is honest about coverage:
    # estimated_total sums the priced lines only
    estimated_total: float
    unpriced_item_count: int
    # lines whose product has SKUs but whose sku_id is still null — the
    # variant (尺码配比 etc.) is undecided, a fact for approvers and the flow
    pending_sku_count: int


PurchaseRequestDetailEnvelope = Envelope[PurchaseRequestDetailRead]


class SalesQuotationBase(RequestModel):
    employee_id: str | None = None
    # server-allocated when omitted; bring your own for tenant conventions
    quote_number: str | None = Field(default=None, max_length=64)
    customer_id: str | None = None
    customer_name_snapshot: str | None = Field(default=None, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_phone: str | None = Field(default=None, max_length=50)
    contact_email: str | None = Field(default=None, max_length=320)
    title: str | None = Field(default=None, max_length=200)
    project_id: str | None = None
    quote_date: date | None = None
    valid_until: date | None = None
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    payment_terms: str | None = Field(default=None, max_length=2000)
    delivery_terms: str | None = Field(default=None, max_length=2000)
    total_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    status: QuotationStatus = "draft"
    remarks: str | None = Field(default=None, max_length=2000)
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreateSalesQuotationRequest(SalesQuotationBase):
    employee_id: str
    # lines may ride the create: one call, one transaction, no half-built
    # draft. Each row follows CreateSalesQuotationItemRequest's rules minus
    # quotation_id, which is the document being created.
    items: list[SalesQuotationItemBase] = Field(default_factory=list, max_length=200)
    title: str = Field(max_length=200)


class UpdateSalesQuotationRequest(RequestModel):
    customer_id: str | None = None
    customer_name_snapshot: str | None = Field(default=None, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_phone: str | None = Field(default=None, max_length=50)
    contact_email: str | None = Field(default=None, max_length=320)
    title: str | None = Field(default=None, max_length=200)
    project_id: str | None = None
    quote_date: date | None = None
    valid_until: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    payment_terms: str | None = Field(default=None, max_length=2000)
    delivery_terms: str | None = Field(default=None, max_length=2000)
    total_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    status: QuotationStatus | None = None
    outcome_note: str | None = Field(default=None, max_length=2000)
    remarks: str | None = Field(default=None, max_length=2000)
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] | None = None


class DeleteSalesQuotationRequest(RequestModel):
    deleted_by: str | None = Field(default=None, max_length=100)
    delete_reason: str | None = Field(default=None, max_length=2000)


class RestoreSalesQuotationRequest(RequestModel):
    restored_by: str | None = Field(default=None, max_length=100)


class SubmitSalesQuotationRequest(RequestModel):
    submitted_by: str | None = None
    source: SourceType | None = None


class SendSalesQuotationRequest(RequestModel):
    sent_by: str | None = None
    source: SourceType | None = None


class CloseSalesQuotationRequest(RequestModel):
    outcome: QuotationOutcome
    outcome_note: str | None = Field(default=None, max_length=2000)
    closed_by: str | None = None
    source: SourceType | None = None


class ReviseSalesQuotationRequest(RequestModel):
    reason: str | None = Field(default=None, max_length=2000)
    revised_by: str | None = None
    source: SourceType | None = None


class SalesQuotationRead(APIModel):
    id: str
    quote_number: str
    revision_no: int
    revision_of_id: str | None = None
    employee_id: str
    customer_id: str | None = None
    customer_name_snapshot: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    title: str
    project_id: str | None = None
    quote_date: date | None = None
    valid_until: date | None = None
    currency: str
    payment_terms: str | None = None
    delivery_terms: str | None = None
    total_amount: float | None = None
    status: QuotationStatus
    submitted_at: datetime | None = None
    sent_at: datetime | None = None
    closed_at: datetime | None = None
    outcome_note: str | None = None
    remarks: str | None = None
    source_report_text: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime | None = None


SalesQuotationListEnvelope = ListEnvelope[SalesQuotationRead]


SalesQuotationEnvelope = Envelope[SalesQuotationRead]


class SalesQuotationItemBase(RequestModel):
    quotation_id: str | None = None
    line_no: int | None = Field(default=None, ge=1)
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = Field(default=None, max_length=200)
    spec: str | None = Field(default=None, max_length=200)
    quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    unit: str | None = Field(default=None, max_length=50)
    list_price_snapshot: float | None = Field(default=None, ge=0, le=9_999_999.99)
    unit_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    amount: float | None = Field(default=None, ge=0, le=9_999_999.99)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    is_gift: bool = False
    lead_time: str | None = Field(default=None, max_length=100)
    attachment_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreateSalesQuotationItemRequest(SalesQuotationItemBase):
    quotation_id: str
    quantity: float = Field(gt=0, le=9_999_999.99)


class UpdateSalesQuotationItemRequest(RequestModel):
    line_no: int | None = Field(default=None, ge=1)
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = Field(default=None, max_length=200)
    spec: str | None = Field(default=None, max_length=200)
    quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    unit: str | None = Field(default=None, max_length=50)
    list_price_snapshot: float | None = Field(default=None, ge=0, le=9_999_999.99)
    unit_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    amount: float | None = Field(default=None, ge=0, le=9_999_999.99)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    is_gift: bool | None = None
    lead_time: str | None = Field(default=None, max_length=100)
    attachment_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] | None = None


class SalesQuotationItemRead(APIModel):
    id: str
    quotation_id: str
    line_no: int | None = None
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = None
    spec: str | None = None
    quantity: float
    unit: str | None = None
    list_price_snapshot: float | None = None
    unit_price: float | None = None
    amount: float | None = None
    tax_rate: float | None = None
    is_gift: bool
    lead_time: str | None = None
    attachment_id: str | None = None
    notes: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime | None = None


class QuotationProductReferenceRead(BaseModel):
    id: str
    product_code: str | None = None
    name: str
    spec: str | None = None
    unit: str | None = None
    list_price: float | None = None


class QuotationSkuReferenceRead(BaseModel):
    id: str
    product_id: str
    sku_code: str | None = None
    variant_attrs: dict[str, Any] = Field(default_factory=dict)
    list_price: float | None = None


class SalesQuotationItemDetailRead(SalesQuotationItemRead):
    """Quotation line plus tenant-scoped catalog labels used by reviewers."""

    product: QuotationProductReferenceRead | None = None
    sku: QuotationSkuReferenceRead | None = None
    sku_pending: bool = False


# The shipped catalog (discount/promotion/tax/shipping/fee/surcharge/
# rounding/other) plus whatever the tenant defined via /type-options.
SalesAdjustmentType = TypeOptionName


class SalesQuotationAdjustmentBase(RequestModel):
    adjustment_type: SalesAdjustmentType
    description: str | None = Field(default=None, max_length=500)
    # signed: negative reduces the total, positive adds to it
    amount: float = Field(ge=-9_999_999.99, le=9_999_999.99)
    source_percentage: float | None = Field(default=None, ge=0, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateSalesQuotationAdjustmentRequest(SalesQuotationAdjustmentBase):
    quotation_id: str
    # pins the adjustment to one line; omitted = a header-level adjustment
    quotation_item_id: str | None = None


class UpdateSalesQuotationAdjustmentRequest(RequestModel):
    adjustment_type: SalesAdjustmentType | None = None
    description: str | None = Field(default=None, max_length=500)
    amount: float | None = Field(default=None, ge=-9_999_999.99, le=9_999_999.99)
    source_percentage: float | None = Field(default=None, ge=0, le=100)
    # explicit null detaches the adjustment back to header level
    quotation_item_id: str | None = None
    metadata: dict[str, Any] | None = None


class SalesQuotationAdjustmentRead(APIModel):
    id: str
    quotation_id: str
    quotation_item_id: str | None = None
    adjustment_type: SalesAdjustmentType
    description: str | None = None
    amount: float
    source_percentage: float | None = None
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime


SalesQuotationAdjustmentEnvelope = Envelope[SalesQuotationAdjustmentRead]


SalesQuotationAdjustmentListEnvelope = ListEnvelope[SalesQuotationAdjustmentRead]


class SalesOrderAdjustmentBase(RequestModel):
    adjustment_type: SalesAdjustmentType
    description: str | None = Field(default=None, max_length=500)
    amount: float = Field(ge=-9_999_999.99, le=9_999_999.99)
    source_percentage: float | None = Field(default=None, ge=0, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateSalesOrderAdjustmentRequest(SalesOrderAdjustmentBase):
    order_id: str
    order_item_id: str | None = None


class UpdateSalesOrderAdjustmentRequest(RequestModel):
    adjustment_type: SalesAdjustmentType | None = None
    description: str | None = Field(default=None, max_length=500)
    amount: float | None = Field(default=None, ge=-9_999_999.99, le=9_999_999.99)
    source_percentage: float | None = Field(default=None, ge=0, le=100)
    order_item_id: str | None = None
    metadata: dict[str, Any] | None = None


class SalesOrderAdjustmentRead(APIModel):
    id: str
    order_id: str
    order_item_id: str | None = None
    adjustment_type: SalesAdjustmentType
    description: str | None = None
    amount: float
    source_percentage: float | None = None
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime


SalesOrderAdjustmentEnvelope = Envelope[SalesOrderAdjustmentRead]


SalesOrderAdjustmentListEnvelope = ListEnvelope[SalesOrderAdjustmentRead]


# --- purchase orders: the commitment to a vendor ---------------------------


class PurchaseOrderBase(RequestModel):
    # server-allocated when omitted; bring your own for tenant conventions
    po_number: str | None = Field(default=None, max_length=64)
    vendor_name_snapshot: str | None = Field(default=None, max_length=200)
    employee_id: str | None = None
    title: str | None = Field(default=None, max_length=200)
    contract_no: str | None = Field(default=None, max_length=64)
    order_date: date | None = None
    promised_date: date | None = None
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    payment_terms: str | None = Field(default=None, max_length=2000)
    delivery_terms: str | None = Field(default=None, max_length=2000)
    total_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    status: str = Field(default="draft", max_length=30)
    remarks: str | None = Field(default=None, max_length=2000)
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreatePurchaseOrderRequest(PurchaseOrderBase):
    # the counterparty is the point of the document — required
    vendor_id: str
    billing_account_id: str | None = None
    employee_id: str
    # lines ride the create, as on every other document family: one call, one
    # transaction, and a bad row rolls the order back instead of leaving an
    # empty PO behind
    items: list[PurchaseOrderItemBase] = Field(default_factory=list, max_length=200)


class UpdatePurchaseOrderRequest(RequestModel):
    vendor_id: str | None = None
    billing_account_id: str | None = None
    vendor_name_snapshot: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    contract_no: str | None = Field(default=None, max_length=64)
    order_date: date | None = None
    promised_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    payment_terms: str | None = Field(default=None, max_length=2000)
    delivery_terms: str | None = Field(default=None, max_length=2000)
    total_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    status: str | None = Field(default=None, max_length=30)
    remarks: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] | None = None


class PurchaseOrderRead(APIModel):
    id: str
    po_number: str
    vendor_id: str
    billing_account_id: str | None = None
    vendor_name_snapshot: str | None = None
    employee_id: str
    title: str | None = None
    contract_no: str | None = None
    order_date: date | None = None
    promised_date: date | None = None
    currency: str
    payment_terms: str | None = None
    delivery_terms: str | None = None
    total_amount: float | None = None
    status: str
    remarks: str | None = None
    source_report_text: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime


PurchaseOrderListEnvelope = ListEnvelope[PurchaseOrderRead]


PurchaseOrderEnvelope = Envelope[PurchaseOrderRead]


class PurchaseOrderCreatedRead(PurchaseOrderRead):
    """Reads back the lines that rode the create call."""

    items: list[PurchaseOrderItemRead] = Field(default_factory=list)


PurchaseOrderCreatedEnvelope = Envelope[PurchaseOrderCreatedRead]


class PurchaseOrderItemBase(RequestModel):
    po_id: str | None = None
    line_no: int | None = Field(default=None, ge=1)
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = Field(default=None, max_length=200)
    spec: str | None = Field(default=None, max_length=200)
    quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    unit: str | None = Field(default=None, max_length=50)
    unit_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    amount: float | None = Field(default=None, ge=0, le=9_999_999.99)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    promised_date: date | None = None
    # 按单采购: the approved request line this PO line orders
    purchase_request_item_id: str | None = None
    attachment_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreatePurchaseOrderItemRequest(PurchaseOrderItemBase):
    po_id: str
    quantity: float = Field(gt=0, le=9_999_999.99)


class UpdatePurchaseOrderItemRequest(RequestModel):
    line_no: int | None = Field(default=None, ge=1)
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = Field(default=None, max_length=200)
    spec: str | None = Field(default=None, max_length=200)
    quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    unit: str | None = Field(default=None, max_length=50)
    unit_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    amount: float | None = Field(default=None, ge=0, le=9_999_999.99)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    promised_date: date | None = None
    # explicit null detaches the line from the request (direct purchase)
    purchase_request_item_id: str | None = None
    attachment_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] | None = None


class PurchaseOrderItemRead(APIModel):
    id: str
    po_id: str
    line_no: int | None = None
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = None
    spec: str | None = None
    quantity: float
    unit: str | None = None
    unit_price: float | None = None
    amount: float | None = None
    tax_rate: float | None = None
    promised_date: date | None = None
    purchase_request_item_id: str | None = None
    received_quantity: float
    attachment_id: str | None = None
    notes: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime


PurchaseOrderItemListEnvelope = ListEnvelope[PurchaseOrderItemRead]


PurchaseOrderItemEnvelope = Envelope[PurchaseOrderItemRead]


class PurchaseOrderAdjustmentBase(RequestModel):
    adjustment_type: SalesAdjustmentType
    description: str | None = Field(default=None, max_length=500)
    amount: float = Field(ge=-9_999_999.99, le=9_999_999.99)
    source_percentage: float | None = Field(default=None, ge=0, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatePurchaseOrderAdjustmentRequest(PurchaseOrderAdjustmentBase):
    po_id: str
    po_item_id: str | None = None


class UpdatePurchaseOrderAdjustmentRequest(RequestModel):
    adjustment_type: SalesAdjustmentType | None = None
    description: str | None = Field(default=None, max_length=500)
    amount: float | None = Field(default=None, ge=-9_999_999.99, le=9_999_999.99)
    source_percentage: float | None = Field(default=None, ge=0, le=100)
    po_item_id: str | None = None
    metadata: dict[str, Any] | None = None


class PurchaseOrderAdjustmentRead(APIModel):
    id: str
    po_id: str
    po_item_id: str | None = None
    adjustment_type: SalesAdjustmentType
    description: str | None = None
    amount: float
    source_percentage: float | None = None
    metadata_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_jsonb", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime


PurchaseOrderAdjustmentEnvelope = Envelope[PurchaseOrderAdjustmentRead]


PurchaseOrderAdjustmentListEnvelope = ListEnvelope[PurchaseOrderAdjustmentRead]


class PurchaseOrderRequestReferenceRead(BaseModel):
    """The request line a PO line orders — with the request's status, so a
    reviewer sees the demand behind the commitment."""

    purchase_request_item_id: str
    request_id: str
    request_status: str
    quantity: float


class PurchaseOrderItemDetailRead(PurchaseOrderItemRead):
    product: PurchaseProductReferenceRead | None = None
    sku: PurchaseSkuReferenceRead | None = None
    # a variant product ordered at product level — the SKU decision is open
    sku_pending: bool = False
    purchase_request: PurchaseOrderRequestReferenceRead | None = None


class PurchaseOrderDetailRead(BaseModel):
    po: PurchaseOrderRead
    items: list[PurchaseOrderItemDetailRead]
    adjustments: list[PurchaseOrderAdjustmentRead]
    approval_records: list[ApprovalRecordRead]
    computed_total: float
    adjustments_total: float
    adjusted_total: float
    # ordered vs received across all live lines — the receiving progress
    ordered_quantity: float
    received_quantity: float


PurchaseOrderDetailEnvelope = Envelope[PurchaseOrderDetailRead]


class ReceivePurchaseOrderLine(RequestModel):
    po_item_id: str
    quantity: float = Field(gt=0, le=9_999_999.99)
    # give a facility to land the goods in the inventory ledger; omit it for
    # 直发/零库存 receipts that never touch stock
    facility: str | None = Field(default=None, max_length=100)
    lot_id: str | None = Field(default=None, max_length=64)
    bin_number: str | None = Field(default=None, max_length=64)
    expire_date: date | None = None
    unit_cost: float | None = Field(default=None, ge=0, le=9_999_999.99)


class ReceivePurchaseOrderRequest(RequestModel):
    lines: list[ReceivePurchaseOrderLine] = Field(min_length=1, max_length=200)


class ReceivedLineRead(BaseModel):
    po_item_id: str
    received_quantity: float
    inventory_item_id: str | None = None


class ReceivePurchaseOrderResult(BaseModel):
    lines: list[ReceivedLineRead]


ReceivePurchaseOrderEnvelope = Envelope[ReceivePurchaseOrderResult]


class InvoiceBase(RequestModel):
    # server-allocated when omitted; bring your own for tenant conventions
    invoice_no: str | None = Field(default=None, max_length=64)
    invoice_type: InvoiceTypeOption | None = None
    employee_id: str | None = None
    customer_id: str | None = None
    # charged to the counterparty's standing account — see billing-accounts.md
    billing_account_id: str | None = None
    vendor_id: str | None = None
    # 工资条: the person being paid. `employee_id` above is whoever ran payroll.
    payee_employee_id: str | None = None
    counterparty_name_snapshot: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    # the pay period a payslip covers — required on payroll, meaningless elsewhere
    period_start: date | None = None
    period_end: date | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    total_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    tax_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    # the tax document's own identity — absent until the invoice is issued or
    # the vendor's copy is entered, which is a normal fact, not an error
    tax_invoice_code: str | None = Field(default=None, max_length=32)
    tax_invoice_number: str | None = Field(default=None, max_length=64)
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    attachment_id: str | None = None
    sales_order_id: str | None = None
    purchase_order_id: str | None = None
    project_id: str | None = None
    status: str = Field(default="draft", max_length=30)
    remarks: str | None = Field(default=None, max_length=2000)
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class DeleteInvoiceRequest(RequestModel):
    deleted_by: str | None = Field(default=None, max_length=100)
    delete_reason: str | None = Field(default=None, max_length=2000)


class CreateInvoiceRequest(InvoiceBase):
    # the direction decides which counterparty is required; the route says so
    # with a message that names the missing field
    direction: InvoiceDirection
    employee_id: str
    title: str = Field(max_length=200)
    # Lines ride the create, as on quotations and orders: an invoice is raised
    # WITH what it bills, not assembled from an empty shell. One call, one
    # transaction — a bad row rolls the whole document back rather than leaving
    # a half-built draft. Each row follows CreateInvoiceItemRequest's rules
    # minus invoice_id, which is the document being created.
    items: list[InvoiceItemBase] = Field(default_factory=list, max_length=200)


class UpdateInvoiceRequest(RequestModel):
    invoice_type: InvoiceTypeOption | None = None
    customer_id: str | None = None
    billing_account_id: str | None = None
    vendor_id: str | None = None
    payee_employee_id: str | None = None
    counterparty_name_snapshot: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    period_start: date | None = None
    period_end: date | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    total_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    tax_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    tax_invoice_code: str | None = Field(default=None, max_length=32)
    tax_invoice_number: str | None = Field(default=None, max_length=64)
    extracted_fields: dict[str, Any] | None = None
    attachment_id: str | None = None
    sales_order_id: str | None = None
    purchase_order_id: str | None = None
    project_id: str | None = None
    status: str | None = Field(default=None, max_length=30)
    remarks: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] | None = None


class InvoiceRead(APIModel):
    id: str
    invoice_no: str
    direction: InvoiceDirection
    invoice_type: str | None = None
    employee_id: str
    customer_id: str | None = None
    billing_account_id: str | None = None
    vendor_id: str | None = None
    payee_employee_id: str | None = None
    counterparty_name_snapshot: str | None = None
    title: str
    period_start: date | None = None
    period_end: date | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str
    total_amount: float | None = None
    tax_amount: float | None = None
    # running sum of this invoice's payment applications
    applied_amount: float
    tax_invoice_code: str | None = None
    tax_invoice_number: str | None = None
    extracted_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("extracted_fields_jsonb", "extracted_fields"),
        serialization_alias="extracted_fields",
    )
    attachment_id: str | None = None
    sales_order_id: str | None = None
    purchase_order_id: str | None = None
    project_id: str | None = None
    status: str
    submitted_at: datetime | None = None
    issued_at: datetime | None = None
    remarks: str | None = None
    source_report_text: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime


InvoiceListEnvelope = ListEnvelope[InvoiceRead]


InvoiceEnvelope = Envelope[InvoiceRead]


class InvoiceCreatedRead(InvoiceRead):
    """The create response reads back the lines that rode the call, so the
    caller sees what landed without a second request."""

    items: list[InvoiceItemRead] = Field(default_factory=list)


InvoiceCreatedEnvelope = Envelope[InvoiceCreatedRead]


class InvoiceItemBase(RequestModel):
    invoice_id: str | None = None
    line_no: int | None = Field(default=None, ge=1)
    invoice_item_type: InvoiceItemType = "goods"
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = Field(default=None, max_length=200)
    spec: str | None = Field(default=None, max_length=200)
    # both optional: a pure charge line (运费 300) has neither
    quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    unit: str | None = Field(default=None, max_length=50)
    unit_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    # signed, because a discount line is a negative amount
    amount: float | None = Field(default=None, ge=-9_999_999.99, le=9_999_999.99)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    tax_amount: float | None = Field(default=None, ge=-9_999_999.99, le=9_999_999.99)
    sales_order_item_id: str | None = None
    purchase_order_item_id: str | None = None
    # a payslip's salary line names the pay_histories row it was computed from
    pay_history_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreateInvoiceItemRequest(InvoiceItemBase):
    invoice_id: str


class UpdateInvoiceItemRequest(RequestModel):
    line_no: int | None = Field(default=None, ge=1)
    invoice_item_type: InvoiceItemType | None = None
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = Field(default=None, max_length=200)
    spec: str | None = Field(default=None, max_length=200)
    quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    unit: str | None = Field(default=None, max_length=50)
    unit_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    amount: float | None = Field(default=None, ge=-9_999_999.99, le=9_999_999.99)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    tax_amount: float | None = Field(default=None, ge=-9_999_999.99, le=9_999_999.99)
    # explicit null detaches the line from the order it billed
    sales_order_item_id: str | None = None
    purchase_order_item_id: str | None = None
    pay_history_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] | None = None


class InvoiceItemRead(APIModel):
    id: str
    invoice_id: str
    line_no: int | None = None
    invoice_item_type: str
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = None
    spec: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    amount: float | None = None
    tax_rate: float | None = None
    tax_amount: float | None = None
    sales_order_item_id: str | None = None
    purchase_order_item_id: str | None = None
    pay_history_id: str | None = None
    notes: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime


InvoiceItemListEnvelope = ListEnvelope[InvoiceItemRead]


InvoiceItemEnvelope = Envelope[InvoiceItemRead]


class CreatePayHistoryRequest(RequestModel):
    """Setting or changing one term of someone's pay.

    There is no "change the amount" call. Posting a new record from a date
    closes whatever was in force for that COMPONENT the day before and opens
    this one, in a single transaction — as two calls they would eventually
    drift, and a compensation history with a hole in it cannot explain a
    payslip.

    State the term in whichever shape fits: an `amount` (12000 a month), a
    `rate` with the `basis` it applies to (3% of collections), or a `formula` in
    words. At least one is required, and a rate without a basis is refused —
    a proportion with nothing to apply it to is not a rule."""

    employee_id: str
    effective_from: date
    component: PayComponentType = "base_salary"
    amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    rate: float | None = Field(default=None, ge=0, le=1000)
    basis: str | None = Field(default=None, max_length=200)
    formula: str | None = Field(default=None, max_length=4000)
    period_type: PayPeriodType = "month"
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    # only for closing a record with no successor (someone leaving)
    effective_thru: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    # the person's own facts that are not the term itself — 社保缴费基数 lives
    # here, where it inherits this table's effective dating for free
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class UpdatePayHistoryRequest(RequestModel):
    """Correcting a mistake, not recording a change — a change is a new record.
    Refused once a payslip has cited this one."""

    amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    rate: float | None = Field(default=None, ge=0, le=1000)
    basis: str | None = Field(default=None, max_length=200)
    formula: str | None = Field(default=None, max_length=4000)
    period_type: PayPeriodType | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    effective_from: date | None = None
    effective_thru: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] | None = None


class PayHistoryRead(APIModel):
    id: str
    employee_id: str
    component: str
    effective_from: date
    effective_thru: date | None = None
    amount: float | None = None
    rate: float | None = None
    basis: str | None = None
    formula: str | None = None
    period_type: str
    currency: str
    notes: str | None = None
    created_by: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime


PayHistoryListEnvelope = ListEnvelope[PayHistoryRead]


PayHistoryEnvelope = Envelope[PayHistoryRead]


class PayHistoryChangeRead(BaseModel):
    """What a raise actually did: the record it opened, and the one it closed."""

    current: PayHistoryRead
    superseded: PayHistoryRead | None = None


PayHistoryChangeEnvelope = Envelope[PayHistoryChangeRead]


PolicyCategory = TypeOptionName


class CreatePolicyRequest(RequestModel):
    """Drafting a policy. Publishing it is a separate call and a separate
    capability, because publishing is an authority act rather than an edit.

    Reusing a `code` opens the NEXT version of that policy; the version number
    is the server's to allocate, so two drafts of v2 cannot exist."""

    code: str = Field(min_length=1, max_length=50)
    category: PolicyCategory
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    summary: str | None = Field(default=None, max_length=2000)
    # the same rules in whatever structure suits, for an agent that would rather
    # read a figure than a paragraph. Never interpreted by the server.
    rules_json: dict[str, Any] | None = None
    # internal = anyone in the workspace; restricted = whoever holds
    # `required_capability`; public = intended for people outside it too
    visibility: Literal["internal", "restricted", "public"] = "internal"
    required_capability: str | None = Field(default=None, max_length=100)
    # when it APPLIES, which is not when it was published
    effective_from: date | None = None
    effective_thru: date | None = None
    attachment_id: str | None = None
    owner_employee_id: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class UpdatePolicyRequest(RequestModel):
    """Drafts only. A published policy is corrected by publishing a new
    version — editing one in place would change what people were told without
    leaving a trace that they were told something else."""

    category: PolicyCategory | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1)
    summary: str | None = Field(default=None, max_length=2000)
    rules_json: dict[str, Any] | None = None
    visibility: Literal["internal", "restricted", "public"] | None = None
    required_capability: str | None = Field(default=None, max_length=100)
    effective_from: date | None = None
    effective_thru: date | None = None
    attachment_id: str | None = None
    owner_employee_id: str | None = None
    custom_fields: dict[str, Any] | None = None


class PublishPolicyRequest(RequestModel):
    """`effective_from` may be moved at publication — a policy approved today
    and applying next month is the ordinary case, not an exception."""

    effective_from: date | None = None
    note: str | None = Field(default=None, max_length=2000)


class RescopePolicyRequest(RequestModel):
    """Who may read a policy, changed after it was published.

    What the rule SAYS is frozen once published — that is what makes the
    handbook answerable about what people were told. Who may read it is not the
    same kind of fact: it is a standing administrative decision that outlives
    the publication and legitimately changes when a department reorganizes, or
    when a rule announced to管理层 becomes company-wide.

    Treating the two as one thing left a workspace with no remedy at all for a
    policy published to a wider audience than intended: the edit is refused, a
    published policy cannot be deleted, and repealing it retires a rule that is
    still in force. The only way to close it was to stop applying it.
    """

    visibility: Literal["internal", "restricted", "public"]
    required_capability: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=2000)


class RepealPolicyRequest(RequestModel):
    """废止. `effective_thru` is when it STOPS applying, which is usually today
    but need not be — a policy can be repealed retroactively to the day a law
    changed."""

    effective_thru: date | None = None
    note: str | None = Field(default=None, max_length=2000)


class PolicyRead(APIModel):
    id: str
    code: str
    version: int
    category: str
    title: str
    summary: str | None = None
    body: str
    rules_json: dict[str, Any] | None = None
    visibility: str
    required_capability: str | None = None
    status: str
    effective_from: date | None = None
    effective_thru: date | None = None
    published_at: datetime | None = None
    published_by: str | None = None
    supersedes_id: str | None = None
    attachment_id: str | None = None
    owner_employee_id: str | None = None
    created_by: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime


PolicyListEnvelope = ListEnvelope[PolicyRead]


PolicyEnvelope = Envelope[PolicyRead]


class PolicyPublishRead(BaseModel):
    """What publishing did: the version now in force, and the one it closed."""

    current: PolicyRead
    superseded: PolicyRead | None = None


PolicyPublishEnvelope = Envelope[PolicyPublishRead]


class BillingAccountBase(RequestModel):
    account_code: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, max_length=30)
    customer_id: str | None = None
    vendor_id: str | None = None
    employee_id: str | None = None
    owner_name_snapshot: str | None = Field(default=None, max_length=200)
    # how far the balance may go negative; 0 means no overdraft
    credit_limit: float = Field(default=0, ge=0, le=9_999_999_999.99)
    valid_from: date | None = None
    valid_until: date | None = None
    status: BillingAccountStatus = "active"
    external_account_id: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    remarks: str | None = Field(default=None, max_length=2000)
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreateBillingAccountRequest(BillingAccountBase):
    name: str = Field(max_length=200)
    # decides which owner is required, which vocabulary `unit` is checked
    # against, and whether a payment may ever settle against this account
    unit_type: BillingAccountUnitType
    unit: str = Field(max_length=30)
    # an opening balance is recorded as the account's first entry, never as a
    # column — the balance must always be the ledger's sum
    opening_balance: float | None = Field(default=None, ge=-9_999_999_999.99, le=9_999_999_999.99)


class UpdateBillingAccountRequest(RequestModel):
    name: str | None = Field(default=None, max_length=200)
    owner_name_snapshot: str | None = Field(default=None, max_length=200)
    credit_limit: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    valid_from: date | None = None
    valid_until: date | None = None
    status: BillingAccountStatus | None = None
    external_account_id: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    remarks: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] | None = None


class DeleteBillingAccountRequest(RequestModel):
    deleted_by: str | None = Field(default=None, max_length=100)
    delete_reason: str | None = Field(default=None, max_length=2000)


class BillingAccountRead(APIModel):
    id: str
    account_code: str
    name: str
    unit_type: BillingAccountUnitType
    unit: str
    customer_id: str | None = None
    vendor_id: str | None = None
    employee_id: str | None = None
    owner_name_snapshot: str | None = None
    credit_limit: float
    # running sum of this account's entries
    balance: float
    # balance + credit_limit: what may still be spent
    available_amount: float
    valid_from: date | None = None
    valid_until: date | None = None
    status: BillingAccountStatus
    external_account_id: str | None = None
    description: str | None = None
    remarks: str | None = None
    source_report_text: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime


BillingAccountListEnvelope = ListEnvelope[BillingAccountRead]


BillingAccountEnvelope = Envelope[BillingAccountRead]


class BillingAccountEntryRead(APIModel):
    """One movement. Rows are immutable — a correction is a second row with the
    opposite sign, never an edit of this one."""

    id: str
    billing_account_id: str
    amount: float
    reason: str
    description: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    expires_at: datetime | None = None
    effective_at: datetime
    idempotency_key: str | None = None
    created_by: str | None = None
    created_at: datetime


BillingAccountEntryListEnvelope = ListEnvelope[BillingAccountEntryRead]


class PostBillingAccountEntryLine(RequestModel):
    # signed: positive adds, negative spends or reverses
    amount: float = Field(ge=-9_999_999_999.99, le=9_999_999_999.99)
    reason: BillingAccountEntryReason
    description: str | None = Field(default=None, max_length=500)
    # what caused this movement, when it is a record in the system
    entity_type: str | None = Field(default=None, max_length=50)
    entity_id: str | None = None
    # only meaningful on a points account
    expires_at: datetime | None = None
    effective_at: datetime | None = None


class PostBillingAccountEntriesRequest(RequestModel):
    lines: list[PostBillingAccountEntryLine] = Field(min_length=1, max_length=200)
    # this writes a balance, and agents retry
    idempotency_key: str | None = Field(default=None, max_length=64)


class PostBillingAccountEntriesResult(BaseModel):
    entries: list[BillingAccountEntryRead]
    balance: float
    available_amount: float
    replayed: bool = False


PostBillingAccountEntriesEnvelope = Envelope[PostBillingAccountEntriesResult]


class ChargedDocumentRead(BaseModel):
    """One document still drawing on an account's credit: a charged order not
    yet fully billed, or a charged invoice not yet settled. `occupied` is the
    part still counted against the account; `consumed` is what has already
    moved on (billed by same-account invoices, or settled by payments)."""

    id: str
    kind: str
    number: str | None = None
    title: str | None = None
    total: float
    consumed: float
    occupied: float


class BillingAccountDetailRead(BaseModel):
    account: BillingAccountRead
    # most recent movements first
    entries: list[BillingAccountEntryRead]
    balance: float
    credit_limit: float
    # balance + credit_limit - exposure: what one more charge is measured
    # against. Exposure was always zero before charging existed, so old
    # readers keep seeing the number they always saw.
    available_amount: float
    exposure_amount: float = 0.0
    charged_orders: list[ChargedDocumentRead] = []
    charged_invoices: list[ChargedDocumentRead] = []
    # positive entries past or nearing expiry that nothing has expired yet —
    # empty on a money account
    expiring_amount: float
    expiring_entry_count: int


BillingAccountDetailEnvelope = Envelope[BillingAccountDetailRead]


class ExpiringBillingAccountEntriesRead(BaseModel):
    """What the expiry sweep works from: earn entries whose `expires_at` has
    passed the given date and which no `expired` entry points at yet."""

    billing_account_id: str
    unit: str
    balance: float
    before: datetime
    entries: list[BillingAccountEntryRead]
    # the sum of those entries, NOT the amount that should be expired — how much
    # of each batch survives redemption is the tenant's FIFO question, answered
    # by the agent against the workflow definition
    expiring_amount: float


ExpiringBillingAccountEntriesEnvelope = Envelope[ExpiringBillingAccountEntriesRead]


class PaymentApplicationRead(APIModel):
    """One 核销 fact. Rows are immutable — a correction is a second row with a
    negative amount, never an edit of this one."""

    id: str
    payment_id: str
    applied_to_type: PaymentApplicationTarget
    applied_to_id: str
    invoice_item_id: str | None = None
    amount_applied: float
    note: str | None = None
    idempotency_key: str | None = None
    applied_at: datetime
    created_by: str | None = None
    created_at: datetime


PaymentApplicationListEnvelope = ListEnvelope[PaymentApplicationRead]


class InvoiceItemDetailRead(InvoiceItemRead):
    product: PurchaseProductReferenceRead | None = None
    sku: PurchaseSkuReferenceRead | None = None


class InvoiceOrderMatchLineRead(BaseModel):
    """One order line, against everything invoiced for it. `received_quantity`
    is present only on the purchase side — the sales side has no receiving
    fact, so a two-way match is all there is to report there."""

    order_item_id: str
    line_no: int | None = None
    product_name: str | None = None
    ordered_quantity: float
    ordered_amount: float | None = None
    received_quantity: float | None = None
    # summed across EVERY invoice pinned to this order line, not just this one
    billed_quantity: float
    billed_amount: float
    # billed - ordered, and billed - received; positive means over-billed
    quantity_variance: float
    receipt_variance: float | None = None


class InvoiceOrderMatchRead(BaseModel):
    """三单匹配 as facts, not as a verdict. The server reports what was ordered,
    what arrived and what has been billed; whether a gap is acceptable is the
    agent's judgment against the tenant's workflow definition — a tolerance
    baked in here would be business policy in the record layer."""

    order_type: Literal["sales_order", "purchase_order"]
    order_id: str
    order_no: str
    order_status: str
    lines: list[InvoiceOrderMatchLineRead]
    # document-level roll-up across every invoice against this order
    ordered_total: float
    billed_total: float
    unbilled_total: float
    # lines this invoice bills that are not pinned to any order line — they
    # cannot be matched, and saying so is more useful than omitting them
    unmatched_line_count: int


class InvoiceDetailRead(BaseModel):
    invoice: InvoiceRead
    items: list[InvoiceItemDetailRead]
    approval_records: list[ApprovalRecordRead]
    # present when the invoice names the order it bills
    order_match: InvoiceOrderMatchRead | None = None
    # every 核销 against this invoice, oldest first — including counter-entries
    applications: list[PaymentApplicationRead]
    # the line sum; the declared header total may legitimately differ (抹零,
    # a header-only invoice with no lines at all) — /detail reports both and
    # the agent judges the gap, as on quotations and orders
    computed_total: float
    computed_tax_total: float
    # what settlement is measured against: the declared total when there is
    # one, else the line sum
    billed_total: float
    applied_amount: float
    # billed_total - applied_amount; the number aging and collection work from
    outstanding_amount: float


InvoiceDetailEnvelope = Envelope[InvoiceDetailRead]


class PaymentBase(RequestModel):
    payment_no: str | None = Field(default=None, max_length=64)
    payment_method: PaymentMethod | None = None
    employee_id: str | None = None
    customer_id: str | None = None
    vendor_id: str | None = None
    payee_employee_id: str | None = None
    counterparty_name_snapshot: str | None = Field(default=None, max_length=200)
    payment_date: date | None = None
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    bank_account: str | None = Field(default=None, max_length=200)
    # the account the money is going to / came from — what a payment approver
    # compares against the vendor's master record before releasing funds
    counterparty_account: str | None = Field(default=None, max_length=200)
    reference_no: str | None = Field(default=None, max_length=100)
    attachment_id: str | None = None
    status: str = Field(default="draft", max_length=30)
    remarks: str | None = Field(default=None, max_length=2000)
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreatePaymentRequest(PaymentBase):
    direction: PaymentDirection
    employee_id: str
    amount: float = Field(gt=0, le=9_999_999_999.99)


class UpdatePaymentRequest(RequestModel):
    payment_method: PaymentMethod | None = None
    customer_id: str | None = None
    vendor_id: str | None = None
    payee_employee_id: str | None = None
    counterparty_name_snapshot: str | None = Field(default=None, max_length=200)
    payment_date: date | None = None
    amount: float | None = Field(default=None, gt=0, le=9_999_999_999.99)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    bank_account: str | None = Field(default=None, max_length=200)
    counterparty_account: str | None = Field(default=None, max_length=200)
    reference_no: str | None = Field(default=None, max_length=100)
    attachment_id: str | None = None
    status: str | None = Field(default=None, max_length=30)
    remarks: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] | None = None


class DeletePaymentRequest(RequestModel):
    deleted_by: str | None = Field(default=None, max_length=100)
    delete_reason: str | None = Field(default=None, max_length=2000)


class PaymentRead(APIModel):
    id: str
    payment_no: str
    direction: PaymentDirection
    payment_method: str | None = None
    employee_id: str
    customer_id: str | None = None
    vendor_id: str | None = None
    payee_employee_id: str | None = None
    counterparty_name_snapshot: str | None = None
    payment_date: date | None = None
    amount: float
    currency: str
    # amount - applied_amount is the 预收/预付 balance still looking for a home
    applied_amount: float
    bank_account: str | None = None
    counterparty_account: str | None = None
    reference_no: str | None = None
    attachment_id: str | None = None
    status: str
    submitted_at: datetime | None = None
    paid_at: datetime | None = None
    remarks: str | None = None
    source_report_text: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime


PaymentListEnvelope = ListEnvelope[PaymentRead]


PaymentEnvelope = Envelope[PaymentRead]


class SettlementTargetRead(BaseModel):
    """What one document looks like after the applications against it — the
    numbers a collection or payables agent reasons over.

    A billing account reports the last two fields instead of the first three: a
    deposit is not a claim, so it has no total to settle and nothing
    outstanding — it has a balance and a spendable amount."""

    applied_to_type: PaymentApplicationTarget
    applied_to_id: str
    label: str
    currency: str
    settleable_total: float | None = None
    applied_amount: float | None = None
    outstanding_amount: float | None = None
    # accounts only
    balance: float | None = None
    available_amount: float | None = None


class PaymentApplicationDetailRead(PaymentApplicationRead):
    target: SettlementTargetRead | None = None


class PaymentDetailRead(BaseModel):
    payment: PaymentRead
    approval_records: list[ApprovalRecordRead]
    # every application this payment made, oldest first, including reversals
    applications: list[PaymentApplicationDetailRead]
    applied_amount: float
    # what is still looking for a document to settle: 预收款 on an inbound
    # payment, 预付款 on an outbound one
    unapplied_amount: float


PaymentDetailEnvelope = Envelope[PaymentDetailRead]


class ApplyPaymentLine(RequestModel):
    applied_to_type: PaymentApplicationTarget
    applied_to_id: str
    # signed: a negative amount is the counter-entry that reverses an earlier
    # application. Zero would be a no-op row in an append-only ledger.
    amount_applied: float = Field(ge=-9_999_999_999.99, le=9_999_999_999.99)
    # optional line-level refinement when the target is an invoice
    invoice_item_id: str | None = None
    note: str | None = Field(default=None, max_length=500)


class ApplyPaymentRequest(RequestModel):
    lines: list[ApplyPaymentLine] = Field(min_length=1, max_length=200)
    # agents retry, and this writes money: repeating a call with the same key
    # returns what was recorded instead of applying twice
    idempotency_key: str | None = Field(default=None, max_length=64)


class ApplyPaymentResult(BaseModel):
    applications: list[PaymentApplicationRead]
    # the payment after this call
    applied_amount: float
    unapplied_amount: float
    # and each document it touched
    targets: list[SettlementTargetRead]
    # true when an idempotency key replayed an earlier call — nothing was written
    replayed: bool = False


ApplyPaymentEnvelope = Envelope[ApplyPaymentResult]


class SalesQuotationDetailRead(BaseModel):
    quotation: SalesQuotationRead
    items: list[SalesQuotationItemDetailRead]
    approval_records: list[ApprovalRecordRead]
    attachments: list[AttachmentRead]
    # every revision sharing this quote_number, oldest first — the negotiation
    # trail is a fact agents reason over
    revisions: list[SalesQuotationRead]
    # header- and line-level adjustments, oldest first
    adjustments: list[SalesQuotationAdjustmentRead]
    # pricing facts for the approval-flow agent's calibration: the line sum
    # is arithmetic, the declared header total may legitimately differ (抹零)
    # — judging the gap is the agent's job
    computed_total: float
    # signed sum of adjustments, and the line sum with adjustments applied —
    # the number the declared total_amount should now match; any residual
    # gap is undocumented and worth an approver's question
    adjustments_total: float
    adjusted_total: float
    unpriced_item_count: int
    # lines whose product has SKUs but whose sku_id is still null
    pending_sku_count: int


SalesQuotationDetailEnvelope = Envelope[SalesQuotationDetailRead]


class SalesOrderBase(RequestModel):
    employee_id: str | None = None
    # server-allocated when omitted; bring your own for tenant conventions
    order_no: str | None = Field(default=None, max_length=64)
    quotation_id: str | None = None
    source_quote_number: str | None = Field(default=None, max_length=64)
    customer_id: str | None = None
    billing_account_id: str | None = None
    customer_name_snapshot: str | None = Field(default=None, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_phone: str | None = Field(default=None, max_length=50)
    ship_to_address: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=200)
    project_id: str | None = None
    contract_no: str | None = Field(default=None, max_length=64)
    order_date: date | None = None
    promised_date: date | None = None
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    payment_terms: str | None = Field(default=None, max_length=2000)
    delivery_terms: str | None = Field(default=None, max_length=2000)
    total_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    status: OrderStatus = "draft"
    logistics_company: str | None = Field(default=None, max_length=100)
    logistics_tracking_no: str | None = Field(default=None, max_length=100)
    remarks: str | None = Field(default=None, max_length=2000)
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreateSalesOrderRequest(SalesOrderBase):
    employee_id: str
    title: str = Field(max_length=200)
    items: list[SalesOrderItemBase] = Field(default_factory=list, max_length=200)


class UpdateSalesOrderRequest(RequestModel):
    quotation_id: str | None = None
    source_quote_number: str | None = Field(default=None, max_length=64)
    customer_id: str | None = None
    billing_account_id: str | None = None
    customer_name_snapshot: str | None = Field(default=None, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_phone: str | None = Field(default=None, max_length=50)
    ship_to_address: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=200)
    project_id: str | None = None
    contract_no: str | None = Field(default=None, max_length=64)
    order_date: date | None = None
    promised_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    payment_terms: str | None = Field(default=None, max_length=2000)
    delivery_terms: str | None = Field(default=None, max_length=2000)
    total_amount: float | None = Field(default=None, ge=0, le=9_999_999_999.99)
    status: OrderStatus | None = None
    logistics_company: str | None = Field(default=None, max_length=100)
    logistics_tracking_no: str | None = Field(default=None, max_length=100)
    remarks: str | None = Field(default=None, max_length=2000)
    source_report_text: str | None = Field(default=None, max_length=10000)
    custom_fields: dict[str, Any] | None = None


class DeleteSalesOrderRequest(RequestModel):
    deleted_by: str | None = Field(default=None, max_length=100)
    delete_reason: str | None = Field(default=None, max_length=2000)


class RestoreSalesOrderRequest(RequestModel):
    restored_by: str | None = Field(default=None, max_length=100)


class SubmitSalesOrderRequest(RequestModel):
    submitted_by: str | None = None
    source: SourceType | None = None


class SalesOrderRead(APIModel):
    id: str
    order_no: str
    quotation_id: str | None = None
    source_quote_number: str | None = None
    employee_id: str
    customer_id: str | None = None
    billing_account_id: str | None = None
    customer_name_snapshot: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    ship_to_address: str | None = None
    title: str
    project_id: str | None = None
    contract_no: str | None = None
    order_date: date | None = None
    promised_date: date | None = None
    currency: str
    payment_terms: str | None = None
    delivery_terms: str | None = None
    total_amount: float | None = None
    status: OrderStatus
    submitted_at: datetime | None = None
    shipped_at: datetime | None = None
    signed_at: datetime | None = None
    logistics_company: str | None = None
    logistics_tracking_no: str | None = None
    remarks: str | None = None
    source_report_text: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime | None = None


SalesOrderListEnvelope = ListEnvelope[SalesOrderRead]


SalesOrderEnvelope = Envelope[SalesOrderRead]


class SalesOrderItemBase(RequestModel):
    order_id: str | None = None
    line_no: int | None = Field(default=None, ge=1)
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = Field(default=None, max_length=200)
    spec: str | None = Field(default=None, max_length=200)
    quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    unit: str | None = Field(default=None, max_length=50)
    list_price_snapshot: float | None = Field(default=None, ge=0, le=9_999_999.99)
    unit_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    amount: float | None = Field(default=None, ge=0, le=9_999_999.99)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    is_gift: bool = False
    promised_date: date | None = None
    attachment_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CreateSalesOrderItemRequest(SalesOrderItemBase):
    order_id: str
    quantity: float = Field(gt=0, le=9_999_999.99)


class UpdateSalesOrderItemRequest(RequestModel):
    line_no: int | None = Field(default=None, ge=1)
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = Field(default=None, max_length=200)
    spec: str | None = Field(default=None, max_length=200)
    quantity: float | None = Field(default=None, gt=0, le=9_999_999.99)
    unit: str | None = Field(default=None, max_length=50)
    list_price_snapshot: float | None = Field(default=None, ge=0, le=9_999_999.99)
    unit_price: float | None = Field(default=None, ge=0, le=9_999_999.99)
    amount: float | None = Field(default=None, ge=0, le=9_999_999.99)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    is_gift: bool | None = None
    promised_date: date | None = None
    attachment_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    custom_fields: dict[str, Any] | None = None


class SalesOrderItemRead(APIModel):
    id: str
    order_id: str
    line_no: int | None = None
    product_id: str | None = None
    sku_id: str | None = None
    product_name_snapshot: str | None = None
    spec: str | None = None
    quantity: float
    unit: str | None = None
    list_price_snapshot: float | None = None
    unit_price: float | None = None
    amount: float | None = None
    tax_rate: float | None = None
    is_gift: bool
    promised_date: date | None = None
    attachment_id: str | None = None
    notes: str | None = None
    custom_fields_jsonb: dict[str, Any] = Field(
        validation_alias=AliasChoices("custom_fields_jsonb", "custom_fields"),
        serialization_alias="custom_fields",
    )
    created_at: datetime
    updated_at: datetime | None = None


class LinkedPurchaseItemRead(BaseModel):
    """A purchase line filed to fulfil this order line (按单采购). The
    request's status is the supply signal a fulfilment agent reads before
    shipping — a 零库存 order line with no ordered purchase behind it has
    nothing to ship."""

    id: str
    request_id: str
    request_status: str
    quantity: float
    unit_price: float | None = None


class SalesOrderItemDetailRead(SalesOrderItemRead):
    """Order line plus tenant-scoped catalog labels used by reviewers."""

    product: QuotationProductReferenceRead | None = None
    sku: QuotationSkuReferenceRead | None = None
    sku_pending: bool = False
    # procure-to-order lines filed against this line, oldest first
    purchase_items: list[LinkedPurchaseItemRead] = Field(default_factory=list)


class QuoteDriftRead(BaseModel):
    """What was agreed, against what was ordered — as arithmetic, not a verdict.

    A live E2E found an order 10.29% above its quotation confirmed with nobody
    looking. The agent had disclosed the gap in prose, which is the weakest
    place for a number to live: it could be computed, so it could also be
    computed differently, or not at all.

    So the server states it. It does NOT decide what an acceptable gap is —
    that is the tenant's, written in the workflow definition the flow agent
    reads — and it does not gate anything on it. Both bases are reported
    because the comparison is only meaningful if you can see what was
    compared: a document's total is its declared `total_amount` when it has
    one, and its line sum when it does not, and comparing a declared total
    against a line sum is a different question from comparing like with like.
    """

    quote_total: float
    # "declared" (the header's own total_amount) or "line_sum" (lines plus
    # adjustments, which is what the total means when none was declared)
    quote_basis: str
    order_total: float
    order_basis: str
    # order − quote: positive means the customer is being charged more than
    # the quotation they accepted
    amount: float
    # null when the quotation totals zero — a percentage of nothing is not 0%,
    # it is undefined, and reporting 0 there would read as "no drift"
    percent: float | None = None


class SalesOrderDetailRead(BaseModel):
    order: SalesOrderRead
    items: list[SalesOrderItemDetailRead]
    approval_records: list[ApprovalRecordRead]
    attachments: list[AttachmentRead]
    # the won quotation this order fulfils, when linked — the closure fact
    quotation: SalesQuotationRead | None = None
    # present only when a quotation is linked: there is no baseline otherwise,
    # and a drift of 0 against nothing would be a lie
    quote_drift: QuoteDriftRead | None = None
    # header- and line-level adjustments, oldest first
    adjustments: list[SalesOrderAdjustmentRead]
    computed_total: float
    adjustments_total: float
    adjusted_total: float
    unpriced_item_count: int
    pending_sku_count: int


SalesOrderDetailEnvelope = Envelope[SalesOrderDetailRead]
