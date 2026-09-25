"""Billing-account charging: what a document occupies, exposure, credit checks, linked lines.

Part of app/api/common — see its __init__ for the whole shared core.
"""

from __future__ import annotations


from types import SimpleNamespace


from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy import (
    select,
)
from sqlalchemy.orm import Session

from app.models import (
    BillingAccount,
    Customer,
    ExpenseClaim,
    ExpenseItem,
    Invoice,
    InvoiceItem,
    PurchaseOrder,
    PurchaseOrderAdjustment,
    PurchaseOrderItem,
    SalesOrder,
    SalesOrderAdjustment,
    SalesOrderItem,
    Vendor,
)
from dataclasses import (
    dataclass,
)
from app.api.common.core import (
    get_scoped_or_404,
)

# --- billing-account charging: who carries a document, and what it occupies --
#
# A document charged to an account (`billing_account_id`) says WHO CARRIES the
# obligation, never that it is paid. Settlement stays exclusively the
# payment-applications ledger; the account's own ledger stays exclusively real
# money. What charging changes is one derived number:
#
#     available = balance + credit_limit - exposure
#
# where exposure is the sum of what charged documents still stand to draw: a
# charged ORDER occupies its live total minus what same-account invoices have
# already billed of it (so occupation TRANSFERS to the invoice at billing time
# rather than doubling), and a charged INVOICE occupies its unsettled
# outstanding. Nothing is stored — applied_amount and the ledger balance are
# already materialized, and a fourth running sum would have two directions to
# drift in.
#
# The occupation begins when the document is charged and ends when it is
# settled, uncharged, or deleted — never when a status changes. Status names
# are the tenant's vocabulary; `cancelled` and `completed` are both terminal
# states and mean opposite things for credit, so the release on cancellation
# is the AGENT's explicit write (clear the field), with the reads and the
# integrity audit making a forgotten one visible.
#
# Why this window matters: between order and invoice — an e-commerce wait, a
# walk-in customer's 缺货 two-day gap, a toB delivery months out — the same
# balance must not be spendable twice. That is the double-spend charging
# exists to refuse.

def effective_line_amount(item) -> float:
    """A line's value the way `document_total` reads it: explicit amount wins,
    then unit price × quantity; a gift is 0 by definition; an unpriced line
    contributes 0 — occupation is computed from what is priced, the same
    honesty `estimated_total` keeps."""
    if getattr(item, "amount", None) is not None:
        return float(item.amount)
    if getattr(item, "unit_price", None) is not None:
        return float(item.unit_price) * float(item.quantity or 0)
    if getattr(item, "is_gift", False):
        return 0.0
    return 0.0


def _live_sum(db: Session, model, parent_field: str, parent_id: str, *, lines: bool) -> float:
    rows = db.scalars(
        select(model).where(
            getattr(model, parent_field) == parent_id,
            model.deleted_at.is_(None),
        )
    ).all()
    if lines:
        return sum(effective_line_amount(row) for row in rows)
    return sum(float(row.amount or 0) for row in rows)


def invoice_billed_amount(db: Session, invoice: Invoice) -> float:
    """What this invoice bills: the declared total, else the live line sum —
    the same coalesce the settlement ceiling and the integrity audit use."""
    if invoice.total_amount is not None:
        return float(invoice.total_amount)
    return _live_sum(db, InvoiceItem, "invoice_id", invoice.id, lines=True)


_CHARGEABLE_ORDERS = {
    SalesOrder: SimpleNamespace(
        item_model=SalesOrderItem, item_field="order_id",
        adjustment_model=SalesOrderAdjustment, adjustment_field="order_id",
        invoice_link="sales_order_id", owner_field="customer_id", label="sales order",
        kind="sales_order", number_field="order_no",
    ),
    PurchaseOrder: SimpleNamespace(
        item_model=PurchaseOrderItem, item_field="po_id",
        adjustment_model=PurchaseOrderAdjustment, adjustment_field="po_id",
        invoice_link="purchase_order_id", owner_field="vendor_id", label="purchase order",
        kind="purchase_order", number_field="po_number",
    ),
}


def order_live_total(db: Session, order) -> float:
    """The order's agreed total, else live lines plus live adjustments — the
    same contract `document_total` states: null means the line math IS it."""
    if order.total_amount is not None:
        return float(order.total_amount)
    spec = _CHARGEABLE_ORDERS[type(order)]
    return (
        _live_sum(db, spec.item_model, spec.item_field, order.id, lines=True)
        + _live_sum(db, spec.adjustment_model, spec.adjustment_field, order.id, lines=False)
    )


def order_billed_on_account(db: Session, order, account_id: str) -> float:
    """What invoices carrying the SAME account have already billed of this
    order. Only same-account invoices release the order's occupation: an
    invoice issued without the account would otherwise silently release credit
    nothing else guards — refusing too little is a leak, refusing too much is
    a re-read."""
    spec = _CHARGEABLE_ORDERS[type(order)]
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.tenant_id == order.tenant_id,
            getattr(Invoice, spec.invoice_link) == order.id,
            Invoice.billing_account_id == account_id,
            Invoice.deleted_at.is_(None),
        )
    ).all()
    return sum(invoice_billed_amount(db, invoice) for invoice in invoices)


@dataclass(frozen=True)
class ChargedDocument:
    """One document still drawing on an account: a charged order not yet
    fully billed, or a charged invoice not yet settled. `consumed` is what
    already moved on (billed by same-account invoices, or settled by
    payments); `occupied` is what still counts against the account."""

    kind: str
    document: object
    number: str | None
    total: float
    consumed: float

    @property
    def occupied(self) -> float:
        return max(self.total - self.consumed, 0.0)


def charged_documents(db: Session, account: BillingAccount) -> list[ChargedDocument]:
    """Everything charged to this account that still stands to draw from it.
    One walk serves the exposure figure and the account's detail read: two
    copies of it had drifted, and the detail's asked an order for a column
    that does not exist."""
    found: list[ChargedDocument] = []
    for order_model, spec in _CHARGEABLE_ORDERS.items():
        for order in db.scalars(
            select(order_model).where(
                order_model.tenant_id == account.tenant_id,
                order_model.billing_account_id == account.id,
                order_model.deleted_at.is_(None),
            )
        ):
            found.append(ChargedDocument(
                spec.kind, order, getattr(order, spec.number_field),
                order_live_total(db, order), order_billed_on_account(db, order, account.id),
            ))
    for invoice in db.scalars(
        select(Invoice).where(
            Invoice.tenant_id == account.tenant_id,
            Invoice.billing_account_id == account.id,
            Invoice.deleted_at.is_(None),
        )
    ):
        found.append(ChargedDocument(
            "invoice", invoice, invoice.invoice_no,
            invoice_billed_amount(db, invoice), float(invoice.applied_amount or 0),
        ))
    return found


def account_exposure(db: Session, account: BillingAccount, charged: list[ChargedDocument] | None = None) -> float:
    """Everything charged to this account still stands to draw from it."""
    if charged is None:
        charged = charged_documents(db, account)
    return round(sum(doc.occupied for doc in charged), 2)


def account_position(
    db: Session, account: BillingAccount, charged: list[ChargedDocument] | None = None
) -> tuple[float, float, float]:
    """(balance, exposure, available) — the three numbers every charge guard,
    detail read and refusal message speak in. A caller that already walked
    the charged documents passes them, so the walk happens once."""
    balance = float(account.balance or 0)
    exposure = account_exposure(db, account, charged)
    return balance, exposure, round(balance + float(account.credit_limit or 0) - exposure, 2)


def resolve_chargeable_account(
    db: Session,
    tenant_id: str,
    account_id: str,
    *,
    owner_field: str,
    owner_id: str | None,
    currency: str,
    label: str,
) -> BillingAccount:
    """The account a document may be charged to, LOCKED for the check that
    follows. Row-locked (`FOR UPDATE`) so two agents charging concurrently
    serialize on the account and cannot both pass the same remaining credit —
    the same discipline the SKU parent lock keeps for variant identity."""
    account = db.scalar(
        select(BillingAccount)
        .where(BillingAccount.tenant_id == tenant_id, BillingAccount.id == account_id)
        .with_for_update()
    )
    if account is None or account.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BillingAccount not found")
    if account.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"account {account.account_code} is {account.status} and takes no new charges",
        )
    if account.unit_type != "currency":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{account.account_code} counts {account.unit}, not money — a {label} "
                "cannot be charged to a points account"
            ),
        )
    if account.unit != currency:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"currency mismatch: this {label} is in {currency} and account "
                f"{account.account_code} is in {account.unit}"
            ),
        )
    owner = getattr(account, owner_field, None)
    if owner is None or owner_id is None or owner != owner_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"account {account.account_code} does not belong to this {label}'s "
                "counterparty — a document is charged to its own party's account"
            ),
        )
    return account


def ensure_within_credit(db: Session, account: BillingAccount, *, label: str) -> None:
    """The occupation guard. Call AFTER the charged document is flushed, so the
    exposure it computes already counts the document being charged; a refusal
    raises and the transaction rolls the flush back with it."""
    db.flush()
    balance, exposure, available = account_position(db, account)
    if available < -CENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"charging this {label} exceeds the account's credit: balance "
                f"{balance:.2f} + credit limit {float(account.credit_limit or 0):.2f} "
                f"- occupied {exposure:.2f} leaves {available:.2f}. Deposit more, "
                "raise the limit, or shrink the document"
            ),
        )


def recheck_charged_document(db: Session, document, *, label: str) -> None:
    """Re-run the occupation guard after a write that may have GROWN a charged
    document — a new line, a raised amount, a restore. Shrinking needs no
    guard, and a document that carries no account is a no-op."""
    account_id = getattr(document, "billing_account_id", None)
    if not account_id:
        return
    account = db.scalar(
        select(BillingAccount)
        .where(BillingAccount.tenant_id == document.tenant_id, BillingAccount.id == account_id)
        .with_for_update()
    )
    if account is None:
        return
    ensure_within_credit(db, account, label=label)


# --- the last five, promoted so the document families can be split ---------
#
# Step 2a took the helpers three or more domains called. These five are called
# by exactly two — but by two of the four groups routes.py is about to split
# into, which is the same problem one size smaller. A helper two modules need
# has two possible homes: here, or one module importing another. This series
# has spent five commits keeping the second one from happening.
#
#   CENT, ensure_invoice_not_duplicated,
#   ensure_nothing_applied          billing needs them, so do expense claims
#   grouped_linked_lines            purchasing and sales both walk link rows
#   normalize_vendor_context        an expense names a vendor, so does a PR


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


def normalize_customer_context(
    db: Session,
    tenant_id: str,
    customer_id: str | None,
    customer_name: str | None,
) -> tuple[str | None, str | None]:
    """The vendor twin's contract, sell-side: a customer_id must be a real
    record (404 otherwise) and backfills the free-text snapshot; without one,
    the snapshot stands alone (a prospect not yet in master data)."""
    if not customer_id:
        return None, customer_name
    customer = get_scoped_or_404(db, Customer, tenant_id, customer_id)
    return customer.id, customer_name or customer.name


def normalize_vendor_context(
    db: Session,
    tenant_id: str,
    vendor_id: str | None,
    merchant: str | None,
) -> tuple[str | None, str | None]:
    """Same contract as `claims.py`'s normalize_project_context: a vendor_id
    must be a real record (404 otherwise) and backfills the free-text merchant
    snapshot; without one, merchant stays whatever the receipt said."""
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


# money comparisons are on values the database stores as numeric(12,2); half a
# cent of slack absorbs float round-tripping without ever admitting a real
# over-application
CENT = 0.005


def _live_lines_of(db: Session, tenant_id: str, model, parent_field: str, parent_id: str) -> list:
    return list(db.scalars(
        select(model).where(
            model.tenant_id == tenant_id, getattr(model, parent_field) == parent_id,
            model.deleted_at.is_(None),
        ).order_by(model.created_at.asc(), model.id.asc())
    ))
