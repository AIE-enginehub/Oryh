"""Bills, the money that settles them, and the standing balances beside both.

Split out of `routes.py`: invoices and their lines, payments, payment
applications, billing accounts and their entry ledger.

Invoices are one family in both directions (OFBiz's `Invoice` shape). The
direction decides which counterparty is required, which capability scope is
checked, which order the lines may bill, and — in the settlement path — what a
payment may apply to. Everything else about a bill is the same either way.

Payments and 核销 are the settlement half. A payment is money that moved; an
application is one act of saying which document that money settles. The ledger
is append-only, so a mistake is corrected by a counter-entry, never by editing
history. AMOUNTS are guarded by the server — nothing may be over-applied, in
either direction, in either currency. STATUS is not: state names are
tenant-editable, so the server cannot know which of them mean "settled". That
judgement is the agent's, reading the workflow definition.

Invoices and payments were measured as separate modules and are deliberately
one. Settlement is not something invoices do or payments do; it is the relation
between them, and splitting it would have promoted `SettlementTarget`,
`live_invoice_items`, `invoice_billed_total` and five more into `common.py` to
hold two halves of one subject apart.

Imports run one way: this module reads `app.api.common` and no other endpoint
module, and nothing in `app/api` reads this one. Only `app/main.py` mounts its
router.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.api.common import (
    CENT,
    DOCUMENT_FAMILIES,
    _run_document_import,
    account_position,
    allocate_document_number,
    allocate_number,
    apply_status_change,
    delete_document,
    document_approvals,
    ensure_document_editable,
    ensure_document_not_deleted,
    ensure_invoice_not_duplicated,
    ensure_nothing_applied,
    ensure_within_credit,
    envelope,
    exclude_rows_with_open_todo,
    get_active_document_or_404,
    get_live_or_404,
    get_scoped_or_404,
    get_tenant_id,
    invoice_billed_amount,
    list_rows,
    load_item_catalog_context,
    may_read_payroll,
    normalize_product_context,
    order_billed_on_account,
    order_live_total,
    own_employee_id,
    page_only_pagination,
    recheck_charged_document,
    record_line_audit,
    require_live_line,
    require_machine_state,
    resolve_chargeable_account,
    resolve_item_refs,
    restore_document,
    submit_document,
    visible_payroll_filter,
)
from app.api.deps import Actor, attributed, get_actor, has_permission, require_permission
from app.db.session import get_db
from app.models import (
    Attachment,
    BillingAccount,
    BillingAccountEntry,
    Customer,
    Employee,
    ExpenseClaim,
    ExpenseItem,
    Invoice,
    InvoiceItem,
    PayHistory,
    Payment,
    PaymentApplication,
    Project,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    SalesOrderItem,
    Vendor,
)
from app.schemas import (
    ApplyPaymentEnvelope,
    ApplyPaymentRequest,
    ApplyPaymentResult,
    ApprovalRecordRead,
    BillingAccountDetailEnvelope,
    BillingAccountDetailRead,
    BillingAccountEntryListEnvelope,
    BillingAccountEntryRead,
    BillingAccountEnvelope,
    BillingAccountListEnvelope,
    BillingAccountRead,
    BulkDocumentImportEnvelope,
    BulkInvoiceImportRequest,
    BulkPaymentImportRequest,
    ChargedDocumentRead,
    CreateBillingAccountRequest,
    CreateInvoiceItemRequest,
    CreateInvoiceRequest,
    CreatePaymentRequest,
    DeleteBillingAccountRequest,
    DeleteInvoiceRequest,
    DeletePaymentRequest,
    ExpiringBillingAccountEntriesEnvelope,
    ExpiringBillingAccountEntriesRead,
    InvoiceCreatedEnvelope,
    InvoiceDetailEnvelope,
    InvoiceDetailRead,
    InvoiceEnvelope,
    InvoiceItemDetailRead,
    InvoiceItemEnvelope,
    InvoiceItemListEnvelope,
    InvoiceItemRead,
    InvoiceListEnvelope,
    InvoiceOrderMatchLineRead,
    InvoiceOrderMatchRead,
    InvoiceRead,
    PaymentApplicationDetailRead,
    PaymentApplicationListEnvelope,
    PaymentApplicationRead,
    PaymentDetailEnvelope,
    PaymentDetailRead,
    PaymentEnvelope,
    PaymentListEnvelope,
    PaymentRead,
    PostBillingAccountEntriesEnvelope,
    PostBillingAccountEntriesRequest,
    PostBillingAccountEntriesResult,
    PurchaseProductReferenceRead,
    PurchaseSkuReferenceRead,
    SettlementTargetRead,
    UpdateBillingAccountRequest,
    UpdateInvoiceItemRequest,
    UpdateInvoiceRequest,
    UpdatePaymentRequest,
)
from app.services.audit import record_audit
from app.core.type_options import SIGNED_TYPE_FAMILIES
from app.services.type_options import require_type_option, type_option_sign
from app.services.state_machines import editable_states, get_builtin_machine, validate_status_filter

router = APIRouter()


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
# Owner column a charged document's counterparty must match, per direction.
# Payroll is deliberately absent: an employee-owned account takes deposits and
# refunds, not charges. Lives here rather than common.py because only invoices
# resolve their side dynamically — the order modules each know theirs.
CHARGE_OWNER_BY_DIRECTION = {"sales": "customer_id", "purchase": "vendor_id"}


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


# --- invoices: one family, both directions -----------------------------------


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
    billing_account_id: str | None = None,
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
            Invoice.billing_account_id: billing_account_id,
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
    charged_account = None
    if payload.billing_account_id:
        owner_field = CHARGE_OWNER_BY_DIRECTION.get(payload.direction)
        if owner_field is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="a payroll invoice cannot be charged to a billing account",
            )
        charged_account = resolve_chargeable_account(
            db, tenant_id, payload.billing_account_id,
            owner_field=owner_field, owner_id=counterparty.get(owner_field),
            currency=payload.currency, label="invoice",
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
        billing_account_id=payload.billing_account_id,
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
        if charged_account is not None:
            # after the lines exist, so the occupation counts what this invoice
            # actually bills — and after any same-account order link, so the
            # order's occupation has already transferred here rather than
            # double-counting
            ensure_within_credit(db, charged_account, label="invoice")
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
    # same line common.py's `ensure_content_edit_allowed` draws for timesheets
    # and expense claims, which is why the hosted agent can advance those and
    # — until now — could not advance the two money documents it is subscribed
    # to by default.
    #
    # Status itself stays guarded, harder: `apply_status_change` requires
    # `invoice.advance` AND the hosted write boundary AND a legal transition.
    if any(field != "status" for field in updates):
        require_permission(actor, "invoice.manage", invoice.direction)
    # what this invoice bills is what settlement measures against — freeze it
    # once the invoice is no longer editable, or /apply's over-application guard
    # can be walked around with a plain PATCH
    ensure_money_fields_editable(
        db, invoice, updates, ("total_amount", "tax_amount", "currency", "billing_account_id")
    )
    if "billing_account_id" in updates and updates["billing_account_id"] != invoice.billing_account_id:
        if float(invoice.applied_amount or 0) != 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "this invoice already has settlements — the account it was "
                    "charged to is part of what was settled and stays"
                ),
            )
        if updates["billing_account_id"]:
            owner_field = CHARGE_OWNER_BY_DIRECTION.get(invoice.direction)
            if owner_field is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="a payroll invoice cannot be charged to a billing account",
                )
            resolve_chargeable_account(
                db, actor.tenant_id, updates["billing_account_id"],
                owner_field=owner_field,
                owner_id=updates.get(owner_field, getattr(invoice, owner_field)),
                currency=updates.get("currency", invoice.currency), label="invoice",
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
    # any update to a charged invoice re-runs the occupation guard: amounts can
    # grow, and the account it now names must absorb what it now bills
    recheck_charged_document(db, invoice, label="invoice")
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
    record_line_audit(
        db, actor, Invoice, item.invoice_id, item.id, "line_added",
    )
    parent = db.get(Invoice, item.invoice_id)
    if parent is not None:
        recheck_charged_document(db, parent, label="invoice")
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
    record_line_audit(
        db, actor, Invoice, item.invoice_id, item.id, "line_changed",
        changed=payload.model_dump(exclude_unset=True),
    )
    parent = db.get(Invoice, item.invoice_id)
    if parent is not None:
        recheck_charged_document(db, parent, label="invoice")
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
    record_line_audit(
        db, actor, Invoice, item.invoice_id, item.id, "line_removed",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    # Before the balance is read, not after: everything below this line —
    # the status check, the floor check, the new balance — is computed from
    # values that must not move underneath it.
    account = lock_for_update(db, tenant_id, BillingAccount, account.id) or account
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


def ensure_replay_matches(recorded: list[tuple], requested: list[tuple], *, key: str, label: str) -> None:
    """A replayed idempotency key must be replaying the SAME request.

    Both settlement paths answered a known key by handing back what that key
    already wrote, without looking at what the caller had just asked for. So
    the same key carrying a DIFFERENT body returned `replayed: true` and a
    200 — the caller was told its request succeeded, and none of it happened.
    An agent that reuses a key across a retry it edited (a corrected amount, an
    extra line) gets silence exactly where it needed an error.

    Compared against the ROWS the key wrote rather than a hash of the request:
    a hash of the wire format changes when a field is reordered or a number is
    spelled `100` instead of `100.0`, neither of which is a different request,
    and it needs a column to store it in. The recorded effect is the thing that
    actually has to match.
    """
    if recorded == requested:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"idempotency key {key!r} was used for a different {label}: it recorded "
            f"{recorded}, this request asks for {requested}. Use a new key, or resend "
            "the request the key belongs to"
        ),
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


# --- billing accounts: a party's standing balance, in money or in points ----


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
    balance, exposure, available = account_position(db, account)
    credit_limit = float(account.credit_limit or 0)

    def charged_order_reads(model, spec_label):
        rows = []
        for order in db.scalars(
            select(model).where(
                model.tenant_id == tenant_id,
                model.billing_account_id == account.id,
                model.deleted_at.is_(None),
            )
        ):
            total = order_live_total(db, order)
            billed = order_billed_on_account(db, order, account.id)
            occupied = round(max(total - billed, 0.0), 2)
            if occupied <= 0:
                continue        # fully billed: the invoice side carries it now
            rows.append(ChargedDocumentRead(
                id=order.id, kind=spec_label,
                number=getattr(order, "order_number", None) or getattr(order, "po_number", None),
                title=order.title, total=round(total, 2),
                consumed=round(billed, 2), occupied=occupied,
            ))
        return rows

    charged_orders = (
        charged_order_reads(SalesOrder, "sales_order")
        + charged_order_reads(PurchaseOrder, "purchase_order")
    )
    charged_invoices = []
    for invoice in db.scalars(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.billing_account_id == account.id,
            Invoice.deleted_at.is_(None),
        )
    ):
        billed = invoice_billed_amount(db, invoice)
        applied = float(invoice.applied_amount or 0)
        occupied = round(max(billed - applied, 0.0), 2)
        if occupied <= 0:
            continue            # settled: it occupies nothing any more
        charged_invoices.append(ChargedDocumentRead(
            id=invoice.id, kind="invoice", number=invoice.invoice_no,
            title=invoice.title, total=round(billed, 2),
            consumed=round(applied, 2), occupied=occupied,
        ))

    detail = BillingAccountDetailRead(
        account=BillingAccountRead.model_validate(account),
        entries=[BillingAccountEntryRead.model_validate(row) for row in entries],
        balance=round(balance, 2),
        credit_limit=round(credit_limit, 2),
        # what a new charge is measured against: balance + limit - occupied.
        # Before charging existed exposure was always zero, so this is the same
        # number every earlier reader saw.
        available_amount=available,
        exposure_amount=exposure,
        charged_orders=charged_orders,
        charged_invoices=charged_invoices,
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
            ensure_replay_matches(
                [(round(float(row.amount), 2), row.reason) for row in replay],
                [(round(float(line.amount), 2), line.reason) for line in payload.lines],
                key=payload.idempotency_key, label="set of account entries",
            )
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


@dataclass(frozen=True)
class SettlementTarget:
    """One kind of document a payment may settle. The parallel of
    `objects.py`'s TODO_TARGET_MODELS for the money side.

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
        # Which payment direction DEPOSITS depends on whose account it is.
        # A customer's account holds THEIR money with US, so their inbound
        # payment fills it; our account AT a vendor holds OUR money with THEM,
        # so our outbound prepayment fills it. Before this was owner-aware, a
        # prepayment to a vendor was recorded as a refund and drove the balance
        # negative — the mirror image written down wrong.
        effect_sign=lambda payment, row: (
            1.0
            if payment.direction == ("outbound" if row.vendor_id is not None else "inbound")
            else -1.0
        ),
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


def target_effect_sign(spec: SettlementTarget, payment: Payment, row) -> float:
    return spec.effect_sign(payment, row) if spec.effect_sign else 1.0


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


def lock_for_update(db: Session, tenant_id: str, model, row_id: str):
    """Take the row lock before reading a running total, and refresh what the
    session already holds.

    Every balance in this module is a stored sum of an append-only ledger, and
    every one of them moves by read-compute-write. Without the lock two
    transactions read the same total, both pass their limit check, both append,
    and the second absolute write erases the first — the ledger then disagrees
    with the number that is supposed to be its sum, both callers were told they
    succeeded, and `data_integrity_audit.py` notices some hours later.

    `populate_existing` matters as much as the lock: `with_for_update()` alone
    returns the identity-mapped instance the session already had, stale value
    and all, so the lock would be held while the arithmetic used the number
    that was read before it.

    On SQLite the dialect renders no FOR UPDATE at all. That is fine and is why
    the concurrency tests for this live in `tests/postgres/` — a lock the test
    database ignores is not something the test database can prove.
    """
    return db.scalar(
        select(model)
        .where(model.tenant_id == tenant_id, model.id == row_id)
        .with_for_update()
        .execution_options(populate_existing=True)
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


# --- payments and 核销: the settlement half ----------------------------------


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
            ensure_replay_matches(
                [(row.applied_to_type, row.applied_to_id, round(float(row.amount_applied), 2))
                 for row in replay],
                [(line.applied_to_type, line.applied_to_id, round(float(line.amount_applied), 2))
                 for line in payload.lines],
                key=payload.idempotency_key, label="set of applications",
            )
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
            # the payment's counterparty must be the account's owner — without
            # this, one customer's cheque could quietly fund another's account
            for account_field, payment_field in (
                ("customer_id", "customer_id"),
                ("vendor_id", "vendor_id"),
                ("employee_id", "payee_employee_id"),
            ):
                owner = getattr(row, account_field)
                if owner is not None and getattr(payment, payment_field) != owner:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"account {row.account_code} belongs to a different party "
                            "than this payment's counterparty"
                        ),
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

    # Every running total this call is about to read and overwrite gets its row
    # lock here — the payment's `applied_amount` and each target's, all before
    # the first of them is read.
    #
    # ONE sorted order over the whole set, payment included. Sorting the
    # targets and then taking the payment separately is not enough: a payment
    # is itself a settlement target type, so this call's payment can be another
    # call's target, and the two would take the same two locks in opposite
    # orders. Sorted by (table, id) — the table name is stable across requests
    # in a way the caller's line order is not.
    to_lock: dict[tuple[str, str], object] = {
        (SETTLEMENT_TARGETS[target_type].model.__tablename__, target_id):
            SETTLEMENT_TARGETS[target_type].model
        for target_type, target_id in target_rows
    }
    to_lock[(Payment.__tablename__, payment.id)] = Payment
    locked_rows = {}
    for (table, row_id), model in sorted(to_lock.items()):
        locked_rows[(table, row_id)] = lock_for_update(db, tenant_id, model, row_id)
    # `populate_existing` refreshed the instances the session already held, so
    # `target_rows` and `resolved` point at the same objects, now current.
    payment = locked_rows[(Payment.__tablename__, payment.id)] or payment

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
        after = running + delta * target_effect_sign(spec, payment, row)
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
            signed = delta * target_effect_sign(spec, payment, row)
            # A negative movement that funds another target in the SAME request
            # is the account paying a document (词表: charge, 扣款), not money
            # leaving the relationship (refund). The distinction is what makes
            # a statement readable: 划拨到发票 and 退款给客户 are different facts.
            paying_out = any(kind != "billing_account" for _, kind, _ in resolved)
            post_account_entries(
                db, actor, row,
                [
                    SimpleNamespace(
                        amount=signed,
                        reason="deposit" if signed > 0 else ("charge" if paying_out else "refund"),
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
