"""Budget consumption, derived from the documents, and the rules for tagging
spend — plan docs/plans/budgets-2026-10-27.md.

A budget's plan is its ledger (`budget_entries`). Everything else a budget
reports is read here, on every call, from the documents that already hold
the facts, and stored nowhere:

* a SPEND budget — `requested` (approved purchase requests not yet ordered),
  `committed` (confirmed purchase orders not yet invoiced), `actual` (issued
  purchase invoices, approved expenses, issued payslips' gross pay and the
  employer's contribution lines), `paid` (cash out against actual);
* an INCOME budget — `ordered` (confirmed sales orders not yet invoiced),
  `invoiced` (issued sales invoices), `received` (cash in), and beside them
  the `pipeline` forecast from open deals, never counted as achieved.

Each amount counts once, at the furthest stage it has reached, through the
line-to-line links the documents already carry.

Which budget line a document line falls to is decided once, by `_target`:
an explicit `budget_line_id` tag wins; otherwise the budget's collecting line
for the document line's kind (`labour`, `marketing`, `sales`); otherwise it
is unbudgeted, and reported as such so spend no plan covers is visible.

A budget scoped to a cost centre (phase 3) reads only documents booked to
that centre or one under it; the company budget (no centre) reads them all,
so a centre's budget is a breakdown beside it, never added to it. A tag
names one line of one budget: a budget at another level — the company's
for a centre's tag, or a centre's for the company's — collects that line
by rule as if it bore no tag.

A sales line's sub-targets (phase 2) take nothing of their own: each reads
the part of its parent's amounts whose salesperson, territory, customer or
product category matches it (`facets`), beside the parent and never added
to it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import and_, event, inspect, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Budget,
    BudgetEntry,
    BudgetLine,
    ExpenseClaim,
    ExpenseItem,
    Invoice,
    InvoiceItem,
    Customer,
    Opportunity,
    OpportunityItem,
    Payment,
    PaymentApplication,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
    Product,
    ProductCategory,
    SalesOrder,
    SalesOrderItem,
    Territory,
)
from app.services.cost_centers import centres_under
from app.services.state_machines import counted_states, get_builtin_machine, is_terminal_state, state_for_role

# category -> the direction of the budget it collects for. The server reads
# these three names; a workspace may retitle them, not rename them.
COLLECTING_CATEGORIES: dict[str, str] = {"labour": "spend", "marketing": "spend", "sales": "income"}

# a budget's header states in which spend may be tagged to it or collected:
# frozen pauses it while finance reviews, closed is final

# Labour (§5.3): gross pay is a payslip's earning lines, every payroll type
# except what was withheld from the person; the employer's own contributions
# arrive on remittance invoices typed below; the withheld shares passed on
# with them are counted nowhere, because they are already inside gross pay.
PAYROLL_WITHHOLDINGS = frozenset({"payroll_iit", "payroll_other_deduction"})
EMPLOYER_CONTRIBUTIONS = frozenset({"employer_social_insurance", "employer_housing_fund"})
WITHHELD_REMITTANCE = "withheld_remittance"
TAX_LINE = "tax"

# a sub-target's dimension column -> the facet of a sales amount it matches
DIMENSION_FACETS = {
    "employee_id": "salesperson",
    "territory_id": "territory",
    "customer_id": "customer",
    "product_category_id": "product_category",
}

ZERO = Decimal("0")
CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)) if value is not None else ZERO


def cents(value: Decimal) -> float:
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _paid_against(paid: Decimal, amount: Decimal) -> Decimal:
    """Cap cash at the line's signed amount without inventing a refund."""
    if amount > 0:
        return min(paid, amount)
    if amount < 0:
        return max(paid, amount)
    return ZERO


@dataclass(frozen=True)
class BudgetStates:
    """A budget's lifecycle in the workspace's own words, by role."""

    active: str
    closed: str
    taking_tags: frozenset[str]      # new spend may name a line
    live: frozenset[str]             # past draft, not closed: collects beside others
    unclosed: frozenset[str]         # the plan may still move


def budget_states(db: Session, tenant_id: str) -> BudgetStates:
    machine = get_builtin_machine(db, tenant_id, "budget")
    active = state_for_role(machine, "budget", "active")
    closed = state_for_role(machine, "budget", "closed")
    states, initial = frozenset(machine["states"]), machine["initial"]
    return BudgetStates(active=active, closed=closed, taking_tags=frozenset({initial, active}),
                        live=states - {initial, closed}, unclosed=states - {closed})


def month_of(day: date) -> date:
    return day.replace(day=1)


def is_withholding(item_type: str | None) -> bool:
    return bool(item_type) and (item_type in PAYROLL_WITHHOLDINGS or item_type.endswith("_ee"))


def _live(model):
    """Rows of a soft-deleting table that are not deleted."""
    return model.deleted_at.is_(None)


@dataclass
class Contribution:
    """One amount reaching (or missing) a budget line at one stage."""

    line_id: str | None          # None: no line of this budget takes it
    stage: str
    month: date
    amount: Decimal
    source: str                  # purchase_invoice, expense, payroll, …
    entity_type: str
    entity_id: str
    number: str | None
    labour: bool = False         # payroll-grade: needs payroll.read to read
    # a sales amount's salesperson, territory, customer and product category,
    # read only when the budget has sub-targets to match them against
    facets: dict | None = None


@dataclass
class Scope:
    budget: Budget
    lines: list[BudgetLine]
    collectors: dict[str, str] = field(default_factory=dict)   # category -> line id
    line_ids: set[str] = field(default_factory=set)
    labour_line_ids: set[str] = field(default_factory=set)
    # parent line id -> its sub-targets
    children: dict[str, list[BudgetLine]] = field(default_factory=dict)
    # a cost-centre budget's centre and every centre under it; None for the
    # company budget, which reads every document
    centres: set[str] | None = None
    # another budget's line id -> that budget's cost centre (None: company)
    foreign: dict[str, str | None] = field(default_factory=dict)

    @classmethod
    def of(cls, db: Session, budget: Budget) -> "Scope":
        lines = list(db.scalars(
            select(BudgetLine).where(BudgetLine.tenant_id == budget.tenant_id, BudgetLine.budget_id == budget.id)
            .order_by(BudgetLine.sort_order.asc().nulls_last(), BudgetLine.line_code.asc())
        ))
        scope = cls(budget=budget, lines=lines)
        if budget.cost_center_id:
            scope.centres = centres_under(db, budget.tenant_id, budget.cost_center_id)
        scope.foreign = dict(db.execute(
            select(BudgetLine.id, Budget.cost_center_id).join(Budget, Budget.id == BudgetLine.budget_id).where(
                BudgetLine.tenant_id == budget.tenant_id, BudgetLine.budget_id != budget.id)).all())
        for line in lines:
            scope.line_ids.add(line.id)
            if line.parent_line_id:
                scope.children.setdefault(line.parent_line_id, []).append(line)
                continue
            if line.category == "labour":
                scope.labour_line_ids.add(line.id)
            if line.status == "active" and COLLECTING_CATEGORIES.get(line.category) == budget.direction:
                scope.collectors[line.category] = line.id
        return scope

    @property
    def top(self) -> list[BudgetLine]:
        """The lines the budget is divided into; sub-targets sit under them."""
        return [line for line in self.lines if not line.parent_line_id]

    def line(self, line_id: str) -> BudgetLine | None:
        return next((line for line in self.lines if line.id == line_id), None)

    def in_period(self, day: date | None) -> bool:
        return day is not None and self.budget.period_start <= day <= self.budget.period_end

    def covers(self, centre: str | None) -> bool:
        """Whether a document booked to `centre` is this budget's to read."""
        return self.centres is None or centre in self.centres


def _target(scope: Scope, tag: str | None, kind: str | None) -> tuple[str | None, bool]:
    """(line id or None, skip). A tag wins; a tag naming another budget's
    line means this budget does not see the amount at all; otherwise the
    collecting line for `kind`; otherwise unbudgeted."""
    if tag:
        if tag in scope.line_ids:
            return tag, False
        if scope.foreign.get(tag, scope.budget.cost_center_id) == scope.budget.cost_center_id:
            return None, True
        # another level's tag: this budget collects the line by rule
    if kind and kind in scope.collectors:
        return scope.collectors[kind], False
    return None, False


def _document_day(*candidates) -> date | None:
    """The first of the candidate dates that is set; a timestamp counts as
    its calendar day."""
    for value in candidates:
        if value is not None:
            return value.date() if isinstance(value, datetime) else value
    return None


class _Applications:
    """Cash applied by paid payments: by invoice line, by whole invoice, by
    expense claim — read once per derivation."""

    def __init__(self, db: Session, tenant_id: str):
        paid = counted_states(db, tenant_id, "payment")
        rows = db.execute(
            select(PaymentApplication).join(Payment, Payment.id == PaymentApplication.payment_id).where(
                PaymentApplication.tenant_id == tenant_id, _live(Payment), Payment.status.in_(paid),
            )
        ).scalars()
        self.by_item: dict[str, Decimal] = defaultdict(lambda: ZERO)
        self.by_invoice: dict[str, Decimal] = defaultdict(lambda: ZERO)
        self.by_claim: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for row in rows:
            amount = money(row.amount_applied)
            if row.invoice_item_id:
                self.by_item[row.invoice_item_id] += amount
            elif row.invoice_id:
                self.by_invoice[row.invoice_id] += amount
            elif row.expense_claim_id:
                self.by_claim[row.expense_claim_id] += amount

    def spread(self, whole: Decimal, parts: list[tuple[str, Decimal]]) -> dict[str, Decimal]:
        """A whole-document application over its lines, in proportion to
        their amounts."""
        total = sum((amount for _, amount in parts), ZERO)
        if not whole or not total:
            return {}
        return {key: whole * amount / total for key, amount in parts}


def _counted(model, states, counting: tuple[type, str, bool] | None = None):
    """Read a hypothetical counting state without changing any stored document."""
    condition = model.status.in_(states)
    if counting is None or counting[0] is not model:
        return condition
    _, document_id, included = counting
    return or_(condition, model.id == document_id) if included else and_(condition, model.id != document_id)


def _invoices(db: Session, scope: Scope, direction: str, counting: tuple[type, str, bool] | None = None):
    """Counted invoices of one direction in this budget's currency, with
    their live lines and the day each belongs to."""
    budget = scope.budget
    states = counted_states(db, budget.tenant_id, "invoice")
    invoices = db.scalars(select(Invoice).where(
        Invoice.tenant_id == budget.tenant_id, Invoice.direction == direction, _live(Invoice),
        _counted(Invoice, states, counting), Invoice.currency == budget.currency,
    )).all()
    if not invoices:
        return []
    items = defaultdict(list)
    for item in db.scalars(select(InvoiceItem).where(
        InvoiceItem.tenant_id == budget.tenant_id, InvoiceItem.invoice_id.in_([i.id for i in invoices]), _live(InvoiceItem),
    )):
        items[item.invoice_id].append(item)
    out = []
    for invoice in invoices:
        if direction == "payroll":
            day = invoice.period_start or invoice.invoice_date or _document_day(invoice.created_at)
        else:
            day = invoice.invoice_date or _document_day(getattr(invoice, "issued_at", None), invoice.created_at)
        out.append((invoice, items[invoice.id], day))
    return out


def _spend(db: Session, scope: Scope, cash: _Applications, counting: tuple[type, str, bool] | None = None) -> list[Contribution]:
    budget = scope.budget
    tenant_id = budget.tenant_id
    out: list[Contribution] = []
    labour_line = scope.collectors.get("labour")

    def add(line_id, stage, day, amount, source, entity_type, entity_id, number, labour=False):
        if amount:
            out.append(Contribution(line_id, stage, month_of(day), amount, source, entity_type,
                                    entity_id, number, labour or (line_id in scope.labour_line_ids)))

    # purchase invoices: actual, and paid against it
    invoiced_by_po_item: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for invoice, lines, day in _invoices(db, scope, "purchase", counting):
        for item in lines:
            if item.purchase_order_item_id:
                invoiced_by_po_item[item.purchase_order_item_id] += money(item.amount)
        if not scope.in_period(day) or not scope.covers(invoice.cost_center_id):
            continue
        spread = cash.spread(cash.by_invoice.get(invoice.id, ZERO),
                             [(item.id, money(item.amount)) for item in lines if item.invoice_item_type != TAX_LINE])
        for item in lines:
            kind = item.invoice_item_type
            if kind == TAX_LINE:
                continue
            paid = cash.by_item.get(item.id, ZERO) + spread.get(item.id, ZERO)
            if kind == WITHHELD_REMITTANCE:
                # counted nowhere as cost (it is inside gross pay), but the
                # cash that carries it out is labour's cash
                add(labour_line, "paid", day, _paid_against(paid, money(item.amount)), "payroll", "invoice", invoice.id,
                    invoice.invoice_no, labour=True)
                continue
            category = "labour" if kind in EMPLOYER_CONTRIBUTIONS else ("marketing" if kind == "marketing" else None)
            line_id, skip = _target(scope, item.budget_line_id, category)
            if skip:
                continue
            labour = kind in EMPLOYER_CONTRIBUTIONS
            source = "payroll" if labour and line_id is None else "purchase_invoice"
            add(line_id, "actual", day, money(item.amount), source, "invoice", invoice.id, invoice.invoice_no, labour)
            add(line_id, "paid", day, _paid_against(paid, money(item.amount)), source, "invoice", invoice.id,
                invoice.invoice_no, labour)

    # payslips: gross pay is actual; what was paid out against them is paid
    for invoice, lines, day in _invoices(db, scope, "payroll"):
        if not scope.in_period(day) or not scope.covers(invoice.cost_center_id):
            continue
        gross = sum((money(item.amount) for item in lines
                     if not is_withholding(item.invoice_item_type) and item.invoice_item_type != TAX_LINE), ZERO)
        source = "payroll"
        add(labour_line, "actual", day, gross, source, "invoice", invoice.id, invoice.invoice_no, labour=True)
        paid = cash.by_invoice.get(invoice.id, ZERO) + sum((cash.by_item.get(i.id, ZERO) for i in lines), ZERO)
        add(labour_line, "paid", day, paid, source, "invoice", invoice.id, invoice.invoice_no, labour=True)

    # Reimbursement invoices mirror expenses, so only their cash is carried
    # back through the line links. The claim still supplies the cost and date.
    reimbursed: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for invoice, lines, _ in _invoices(db, scope, "reimbursement"):
        spread = cash.spread(cash.by_invoice.get(invoice.id, ZERO), [(i.id, money(i.amount)) for i in lines])
        for item in lines:
            if item.expense_item_id:
                reimbursed[item.expense_item_id] += cash.by_item.get(item.id, ZERO) + spread.get(item.id, ZERO)

    # expenses: actual from approval on; paid directly or through reimbursement
    states = counted_states(db, tenant_id, "expense_claim")
    claims = {c.id: c for c in db.scalars(select(ExpenseClaim).where(
        ExpenseClaim.tenant_id == tenant_id, _live(ExpenseClaim), _counted(ExpenseClaim, states, counting),
        ExpenseClaim.currency == budget.currency,
    ))}
    if claims:
        by_claim = defaultdict(list)
        for item in db.scalars(select(ExpenseItem).where(
            ExpenseItem.tenant_id == tenant_id, ExpenseItem.claim_id.in_(list(claims)), _live(ExpenseItem),
        )):
            by_claim[item.claim_id].append(item)
        for claim_id, items in by_claim.items():
            claim = claims[claim_id]
            spread = cash.spread(cash.by_claim.get(claim_id, ZERO), [(i.id, money(i.amount)) for i in items])
            if not scope.covers(claim.cost_center_id):
                continue
            for item in items:
                if not scope.in_period(item.expense_date):
                    continue
                line_id, skip = _target(scope, item.budget_line_id, "marketing" if item.category == "marketing" else None)
                if skip:
                    continue
                add(line_id, "actual", item.expense_date, money(item.amount), "expense", "expense_claim",
                    claim.id, claim.title)
                paid = spread.get(item.id, ZERO) + reimbursed.get(item.id, ZERO)
                add(line_id, "paid", item.expense_date, _paid_against(paid, money(item.amount)),
                    "expense", "expense_claim", claim.id, claim.title)

    # purchase orders: committed until invoiced
    po_states = counted_states(db, tenant_id, "purchase_order")
    orders = {o.id: o for o in db.scalars(select(PurchaseOrder).where(
        PurchaseOrder.tenant_id == tenant_id, _live(PurchaseOrder), _counted(PurchaseOrder, po_states, counting),
        PurchaseOrder.currency == budget.currency, PurchaseOrder.order_kind == "order",
    ))}
    ordered_by_pr_item: dict[str, Decimal] = defaultdict(lambda: ZERO)
    if orders:
        for item in db.scalars(select(PurchaseOrderItem).where(
            PurchaseOrderItem.tenant_id == tenant_id, PurchaseOrderItem.po_id.in_(list(orders)), _live(PurchaseOrderItem),
        )):
            if item.purchase_request_item_id:
                ordered_by_pr_item[item.purchase_request_item_id] += money(item.amount)
            order = orders[item.po_id]
            day = order.order_date or _document_day(order.created_at)
            if not scope.in_period(day) or not scope.covers(order.cost_center_id):
                continue
            line_id, skip = _target(scope, item.budget_line_id, None)
            if skip:
                continue
            remaining = max(ZERO, money(item.amount) - invoiced_by_po_item.get(item.id, ZERO))
            add(line_id, "committed", day, remaining, "purchase_order", "purchase_order", order.id, order.po_number)

    # purchase requests: requested until ordered
    pr_states = counted_states(db, tenant_id, "purchase_request")
    requests = {r.id: r for r in db.scalars(select(PurchaseRequest).where(
        PurchaseRequest.tenant_id == tenant_id, _live(PurchaseRequest), _counted(PurchaseRequest, pr_states, counting),
        PurchaseRequest.currency == budget.currency,
    ))}
    if requests:
        for item in db.scalars(select(PurchaseRequestItem).where(
            PurchaseRequestItem.tenant_id == tenant_id, PurchaseRequestItem.request_id.in_(list(requests)),
            _live(PurchaseRequestItem),
        )):
            request = requests[item.request_id]
            day = request.request_date or _document_day(request.created_at)
            if not scope.in_period(day) or not scope.covers(request.cost_center_id):
                continue
            line_id, skip = _target(scope, item.budget_line_id, None)
            if skip:
                continue
            remaining = max(ZERO, money(item.amount) - ordered_by_pr_item.get(item.id, ZERO))
            add(line_id, "requested", day, remaining, "purchase_request", "purchase_request", request.id,
                request.title)
    return out


class _SalesFacets:
    """Who sold it, where, to whom and what: the facets a sales amount is
    matched to sub-targets by. A salesperson is the sales order's owner, else
    the customer's account owner; a territory is the customer's."""

    def __init__(self, db: Session, tenant_id: str):
        self.db, self.tenant_id = db, tenant_id
        self.customers = {row.id: (row.territory_id, row.owner_employee_id) for row in db.execute(
            select(Customer.id, Customer.territory_id, Customer.owner_employee_id).where(Customer.tenant_id == tenant_id))}
        self.categories = dict(db.execute(
            select(Product.id, Product.category_id).where(Product.tenant_id == tenant_id)).all())
        self.order_owners: dict[str, str] = {}

    def of(self, *, customer_id: str | None, product_id: str | None = None,
           salesperson: str | None = None, sales_order_id: str | None = None) -> dict:
        territory, account_owner = self.customers.get(customer_id, (None, None)) if customer_id else (None, None)
        if salesperson is None and sales_order_id:
            if sales_order_id not in self.order_owners:
                self.order_owners[sales_order_id] = self.db.scalar(
                    select(SalesOrder.employee_id).where(SalesOrder.id == sales_order_id))
            salesperson = self.order_owners[sales_order_id]
        return {"salesperson": salesperson or account_owner, "territory": territory, "customer": customer_id,
                "product_category": self.categories.get(product_id) if product_id else None}


def _income(db: Session, scope: Scope, cash: _Applications) -> list[Contribution]:
    budget = scope.budget
    tenant_id = budget.tenant_id
    sales_line = scope.collectors.get("sales")
    out: list[Contribution] = []
    facets = _SalesFacets(db, tenant_id) if scope.children else None

    def add(stage, day, amount, source, entity_type, entity_id, number, found=None):
        if amount:
            out.append(Contribution(sales_line, stage, month_of(day), amount, source, entity_type, entity_id, number,
                                    facets=found))

    invoiced_by_so_item: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for invoice, lines, day in _invoices(db, scope, "sales"):
        priced = [item for item in lines if item.invoice_item_type != TAX_LINE]
        for item in priced:
            if item.sales_order_item_id:
                invoiced_by_so_item[item.sales_order_item_id] += money(item.amount)
        if not scope.in_period(day):
            continue
        spread = cash.spread(cash.by_invoice.get(invoice.id, ZERO), [(i.id, money(i.amount)) for i in priced])
        # line by line, so each amount carries its product's category
        for item in priced:
            amount = money(item.amount)
            received = cash.by_item.get(item.id, ZERO) + spread.get(item.id, ZERO)
            found = facets.of(customer_id=invoice.customer_id, product_id=item.product_id,
                              sales_order_id=invoice.sales_order_id) if facets else None
            add("invoiced", day, amount, "sales_invoice", "invoice", invoice.id, invoice.invoice_no, found)
            add("received", day, min(received, amount) if amount > 0 else received, "sales_invoice", "invoice",
                invoice.id, invoice.invoice_no, found)

    so_states = counted_states(db, tenant_id, "sales_order")
    orders = {o.id: o for o in db.scalars(select(SalesOrder).where(
        SalesOrder.tenant_id == tenant_id, _live(SalesOrder), SalesOrder.status.in_(so_states),
        SalesOrder.currency == budget.currency, SalesOrder.order_kind == "order",
    ))}
    if orders:
        for item in db.scalars(select(SalesOrderItem).where(
            SalesOrderItem.tenant_id == tenant_id, SalesOrderItem.order_id.in_(list(orders)), _live(SalesOrderItem),
        )):
            order = orders[item.order_id]
            day = order.order_date or _document_day(order.created_at)
            if not scope.in_period(day):
                continue
            remaining = max(ZERO, money(item.amount) - invoiced_by_so_item.get(item.id, ZERO))
            found = facets.of(customer_id=order.customer_id, product_id=item.product_id,
                              salesperson=order.employee_id) if facets else None
            add("ordered", day, remaining, "sales_order", "sales_order", order.id, order.order_no, found)

    machine = get_builtin_machine(db, tenant_id, "opportunity")
    closed = {state for state in machine["states"] if is_terminal_state(machine, state)}
    deals = [deal for deal in db.scalars(select(Opportunity).where(
        Opportunity.tenant_id == tenant_id, _live(Opportunity), Opportunity.status.not_in(closed),
        Opportunity.currency == budget.currency, Opportunity.expected_close_date.is_not(None),
    )) if scope.in_period(deal.expected_close_date)]
    deal_items: dict[str, list[tuple[str | None, Decimal]]] = defaultdict(list)
    if deals and facets:
        for item in db.scalars(select(OpportunityItem).where(
            OpportunityItem.tenant_id == tenant_id, OpportunityItem.opportunity_id.in_([d.id for d in deals]),
        )):
            if money(item.amount) > 0:
                deal_items[item.opportunity_id].append((item.product_id, money(item.amount)))
    for deal in deals:
        amount = money(deal.expected_amount)
        weight = Decimal(deal.probability) / Decimal(100) if deal.probability else None
        # a deal's expected amount, shared over its product lines when it has
        # priced ones, so a product-category target sees its part
        parts = deal_items.get(deal.id) or [(None, Decimal(1))]
        whole = sum((share for _, share in parts), ZERO)
        for product_id, share in parts:
            part = amount * share / whole
            found = facets.of(customer_id=deal.customer_id, product_id=product_id,
                              salesperson=deal.employee_id) if facets else None
            add("pipeline", deal.expected_close_date, part, "opportunity", "opportunity", deal.id,
                deal.opportunity_no, found)
            if weight is not None:
                add("pipeline_weighted", deal.expected_close_date, part * weight, "opportunity", "opportunity",
                    deal.id, deal.opportunity_no, found)
    return out


def contributions(db: Session, budget: Budget, scope: Scope | None = None) -> tuple[Scope, list[Contribution]]:
    scope = scope or Scope.of(db, budget)
    cash = _Applications(db, budget.tenant_id)
    found = _spend(db, scope, cash) if budget.direction == "spend" else _income(db, scope, cash)
    return scope, found


def planned(db: Session, budget: Budget) -> dict[tuple[str, date], Decimal]:
    totals: dict[tuple[str, date], Decimal] = defaultdict(lambda: ZERO)
    for entry in db.scalars(select(BudgetEntry).where(
        BudgetEntry.tenant_id == budget.tenant_id, BudgetEntry.budget_id == budget.id,
    )):
        totals[(entry.budget_line_id, entry.period_month)] += money(entry.amount)
    return totals


SPEND_STAGES = ("requested", "committed", "actual", "paid")
INCOME_STAGES = ("ordered", "invoiced", "received", "pipeline", "pipeline_weighted")


def _figures(direction: str, plan: Decimal, stages: dict[str, Decimal]) -> dict[str, float | None]:
    out: dict[str, float | None] = {"planned": cents(plan)}
    if direction == "spend":
        for stage in SPEND_STAGES:
            out[stage] = cents(stages.get(stage, ZERO))
        available = plan - stages.get("requested", ZERO) - stages.get("committed", ZERO) - stages.get("actual", ZERO)
        out["available"] = cents(available)
        out["percent_used"] = round(float(stages.get("actual", ZERO) / plan * 100), 1) if plan else None
        # how far the plan is spoken for: requested + committed + actual, the
        # figure a workspace's alert rule usually reads (the agent applies it)
        out["percent_consumed"] = round(float((plan - available) / plan * 100), 1) if plan else None
    else:
        for stage in INCOME_STAGES:
            out[stage] = cents(stages.get(stage, ZERO))
        out["gap"] = cents(plan - stages.get("invoiced", ZERO))
        out["percent_achieved"] = round(float(stages.get("invoiced", ZERO) / plan * 100), 1) if plan else None
    return out


def _redacted(figures: dict) -> dict:
    return {key: (value if key == "planned" else None) for key, value in figures.items()}


def months_of(budget: Budget) -> list[date]:
    out, day = [], budget.period_start
    while day <= budget.period_end:
        out.append(day)
        day = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    return out


class _Trees:
    """Territories and product categories are trees: a target for a region or
    a shelf takes what falls under it."""

    def __init__(self, db: Session, tenant_id: str):
        self.db, self.tenant_id = db, tenant_id
        self._parents: dict[str, dict[str, str | None]] = {}
        self._under: dict[tuple[str, str], set[str]] = {}

    def _tree(self, kind: str) -> dict[str, str | None]:
        if kind not in self._parents:
            model, parent = (Territory, Territory.parent_territory_id) if kind == "territory" \
                else (ProductCategory, ProductCategory.parent_id)
            self._parents[kind] = dict(self.db.execute(
                select(model.id, parent).where(model.tenant_id == self.tenant_id)).all())
        return self._parents[kind]

    def under(self, kind: str, root: str) -> set[str]:
        key = (kind, root)
        if key not in self._under:
            children: dict[str | None, list[str]] = defaultdict(list)
            for node, parent in self._tree(kind).items():
                children[parent].append(node)
            found, stack = {root}, [root]
            while stack:
                for child in children.get(stack.pop(), ()):
                    if child not in found:
                        found.add(child)
                        stack.append(child)
            self._under[key] = found
        return self._under[key]


def dimension_of(line: BudgetLine) -> tuple[str, str] | None:
    """(column, id) of a sub-target's one dimension."""
    for column in DIMENSION_FACETS:
        value = getattr(line, column)
        if value:
            return column, value
    return None


def _matches(line: BudgetLine, item: Contribution, trees: _Trees) -> bool:
    if item.line_id != line.parent_line_id or not item.facets:
        return False
    column, wanted = dimension_of(line)
    facet = DIMENSION_FACETS[column]
    value = item.facets.get(facet)
    if value is None:
        return False
    if facet in ("territory", "product_category"):
        return value in trees.under(facet, wanted)
    return value == wanted


def _of_line(scope: Scope, found: list[Contribution], line: BudgetLine, trees: _Trees) -> list[Contribution]:
    """What a line's figures are made of: its own amounts, or for a
    sub-target the matching part of its parent's."""
    if line.parent_line_id:
        return [item for item in found if _matches(line, item, trees)]
    return [item for item in found if item.line_id == line.id]


def _by_month(items: list[Contribution]) -> dict[date, dict[str, Decimal]]:
    out: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for item in items:
        out[item.month][item.stage] += item.amount
    return out


def _sum_months(months_figures: dict[date, dict[str, Decimal]]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for month_figures in months_figures.values():
        for stage, value in month_figures.items():
            totals[stage] += value
    return totals


def payroll_line_ids(scope: Scope, found: list[Contribution]) -> set[str]:
    """A tag cannot declassify pay: protect any line carrying labour facts."""
    return scope.labour_line_ids | {item.line_id for item in found if item.labour and item.line_id is not None}


def execution(db: Session, budget: Budget, *, may_read_payroll: bool, by_month: bool = True) -> dict:
    """B10: every figure per line (and month), with the unbudgeted spend no
    line takes. Labour figures are payroll-grade: without `payroll.read`
    only their plan is shown. A line's sub-targets sit under it, each with
    the same figures, and `splits` says per dimension how the sub-targets'
    plans and amounts compare with the line's own — they are a breakdown,
    never part of the budget's total."""
    scope, found = contributions(db, budget)
    plan = planned(db, budget)
    months = months_of(budget)
    trees = _Trees(db, budget.tenant_id)
    labour_unbudgeted = any(item.line_id is None and item.labour for item in found)
    private_lines = payroll_line_ids(scope, found)

    def line_plan(line_id: str) -> Decimal:
        return sum((v for (lid, _), v in plan.items() if lid == line_id), ZERO)

    def row_of(line: BudgetLine, items: list[Contribution]) -> tuple[dict, dict[str, Decimal]]:
        redact = line.id in private_lines and not may_read_payroll
        months_figures = _by_month(items)
        stage_totals = _sum_months(months_figures)
        totals = _figures(budget.direction, line_plan(line.id), stage_totals)
        row = {
            "line_id": line.id, "line_code": line.line_code, "name": line.name, "category": line.category,
            "status": line.status, "collects": line.id in scope.collectors.values(),
            "redacted": redact, "totals": _redacted(totals) if redact else totals,
        }
        if line.parent_line_id:
            column, value = dimension_of(line)
            row.update(collects=False, dimension=DIMENSION_FACETS[column], dimension_id=value)
        if by_month:
            row["by_month"] = []
            for month in months:
                figures = _figures(budget.direction, plan.get((line.id, month), ZERO), months_figures.get(month, {}))
                row["by_month"].append({"month": month.isoformat(), **(_redacted(figures) if redact else figures)})
        return row, stage_totals

    lines = []
    for line in scope.top:
        own = _of_line(scope, found, line, trees)
        row, own_totals = row_of(line, own)
        children = scope.children.get(line.id, [])
        if children:
            row["sub_targets"] = []
            splits: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
            reached: dict[str, set[int]] = defaultdict(set)
            for child in children:
                matched = _of_line(scope, found, child, trees)
                child_row, child_totals = row_of(child, matched)
                row["sub_targets"].append(child_row)
                if child.status != "active":
                    continue
                facet = child_row["dimension"]
                splits[facet]["planned"] += line_plan(child.id)
                matched_ids = {id(item) for item in matched}
                reached[facet] |= {index for index, item in enumerate(own) if id(item) in matched_ids}
            row["splits"] = {}
            for facet, sums in splits.items():
                outside: dict[str, Decimal] = defaultdict(lambda: ZERO)
                for index, item in enumerate(own):
                    if index not in reached[facet]:
                        outside[item.stage] += item.amount
                headline = "invoiced" if budget.direction == "income" else "actual"
                row["splits"][facet] = {
                    "planned": cents(sums["planned"]),
                    "line_planned": cents(line_plan(line.id)),
                    # how far the split plans fall short of (or exceed) the line's own
                    "unplanned": cents(line_plan(line.id) - sums["planned"]),
                    # what the line took that no active sub-target of this dimension matches
                    f"outside_{headline}": cents(outside.get(headline, ZERO)),
                }
        lines.append(row)
    unbudgeted = None
    if budget.direction == "spend":
        stage_totals = defaultdict(lambda: ZERO)
        payroll_totals = defaultdict(lambda: ZERO)
        for item in found:
            if item.line_id is None:
                (payroll_totals if item.labour else stage_totals)[item.stage] += item.amount
        unbudgeted = {stage: cents(stage_totals.get(stage, ZERO)) for stage in SPEND_STAGES}
        # payroll that no labour line takes is still payroll
        unbudgeted["payroll"] = (
            {stage: cents(payroll_totals.get(stage, ZERO)) for stage in SPEND_STAGES}
            if may_read_payroll else None
        ) if labour_unbudgeted else {stage: 0.0 for stage in SPEND_STAGES}
    top_ids = {line.id for line in scope.top}
    all_plan = sum((v for (lid, _), v in plan.items() if lid in top_ids), ZERO)
    all_stages: dict[str, Decimal] = defaultdict(lambda: ZERO)
    hidden = bool(private_lines) and not may_read_payroll
    for item in found:
        if item.line_id is None or (hidden and item.line_id in private_lines):
            continue
        all_stages[item.stage] += item.amount
    totals = _figures(budget.direction, all_plan, all_stages)
    return {
        "budget_id": budget.id, "budget_no": budget.budget_no, "direction": budget.direction,
        "currency": budget.currency, "period_start": budget.period_start.isoformat(),
        "period_end": budget.period_end.isoformat(), "status": budget.status,
        "months": [m.isoformat() for m in months],
        "lines": lines,
        "totals": totals,
        # the totals leave out labour's figures when the reader may not see pay
        "totals_exclude_labour": hidden,
        "unbudgeted": unbudgeted,
    }


def line_documents(db: Session, budget: Budget, line_id: str, stage: str | None) -> list[dict]:
    """The documents behind a line's figures, summed per document."""
    scope, found = contributions(db, budget)
    line = scope.line(line_id)
    grouped: dict[tuple[str, str, str], dict] = {}
    for item in _of_line(scope, found, line, _Trees(db, budget.tenant_id)):
        if stage and item.stage != stage:
            continue
        key = (item.stage, item.entity_type, item.entity_id)
        row = grouped.setdefault(key, {
            "stage": item.stage, "entity_type": item.entity_type, "entity_id": item.entity_id,
            "number": item.number, "source": item.source, "month": item.month.isoformat(), "amount": ZERO,
        })
        row["amount"] += item.amount
    return [{**row, "amount": cents(row["amount"])} for row in sorted(grouped.values(), key=lambda r: (r["stage"], r["month"]))]


def line_totals(db: Session, budget: Budget, line_id: str) -> dict[str, Decimal]:
    scope, found = contributions(db, budget)
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for item in _of_line(scope, found, scope.line(line_id), _Trees(db, budget.tenant_id)):
        totals[item.stage] += item.amount
    totals["planned"] = sum((v for (lid, _), v in planned(db, budget).items() if lid == line_id), ZERO)
    return totals


def cash_view(db: Session, income: Budget | None, spend: Budget | None, *, may_read_payroll: bool) -> dict:
    """The combined cash budget: an income budget's plan and receipts set
    against a spend budget's plan and payments, month by month, with the
    running net. Plans are the budgets' own (top-level lines); cash is what
    the execution read reports as received and paid. Cash out that no line
    takes is shown apart as `unbudgeted_paid`, since it left the bank all the
    same. Without payroll.read labour's payments are left out and the
    read says so."""
    months: set[date] = set()
    per_month: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    excludes_labour = False
    for budget in (income, spend):
        if budget is None:
            continue
        months.update(months_of(budget))
        scope, found = contributions(db, budget)
        top_ids = {line.id for line in scope.top}
        side = "income" if budget.direction == "income" else "spend"
        for (line_id, month), amount in planned(db, budget).items():
            if line_id in top_ids:
                per_month[month][f"{side}_planned"] += amount
        for item in found:
            if item.stage not in ("received", "paid"):
                continue
            if item.labour and not may_read_payroll:
                excludes_labour = True
                continue
            if item.line_id is None:
                per_month[item.month]["unbudgeted_paid"] += item.amount
            else:
                per_month[item.month][item.stage] += item.amount
    rows, running_planned, running_actual = [], ZERO, ZERO
    for month in sorted(months):
        figures = per_month.get(month, {})
        planned_net = figures.get("income_planned", ZERO) - figures.get("spend_planned", ZERO)
        actual_net = figures.get("received", ZERO) - figures.get("paid", ZERO) - figures.get("unbudgeted_paid", ZERO)
        running_planned += planned_net
        running_actual += actual_net
        rows.append({
            "month": month.isoformat(),
            "income_planned": cents(figures.get("income_planned", ZERO)),
            "received": cents(figures.get("received", ZERO)),
            "spend_planned": cents(figures.get("spend_planned", ZERO)),
            "paid": cents(figures.get("paid", ZERO)),
            "unbudgeted_paid": cents(figures.get("unbudgeted_paid", ZERO)),
            "net_planned": cents(planned_net),
            "net_actual": cents(actual_net),
            "cumulative_net_planned": cents(running_planned),
            "cumulative_net_actual": cents(running_actual),
        })
    keys = ("income_planned", "received", "spend_planned", "paid", "unbudgeted_paid", "net_planned", "net_actual")
    totals = {key: cents(sum((Decimal(str(row[key])) for row in rows), ZERO)) for key in keys}
    return {
        "income_budget_id": income.id if income else None, "spend_budget_id": spend.id if spend else None,
        "currency": (income or spend).currency, "months": rows, "totals": totals,
        "paid_excludes_labour": excludes_labour,
    }


def available(totals: dict[str, Decimal]) -> Decimal:
    return totals.get("planned", ZERO) - totals.get("requested", ZERO) - totals.get("committed", ZERO) - totals.get("actual", ZERO)


# --- budget impact of one spending document (B11) ---------------------------

SPENDING_DOCUMENTS = {
    "expense_claim": (ExpenseClaim, ExpenseItem, "claim_id"),
    "purchase_request": (PurchaseRequest, PurchaseRequestItem, "request_id"),
    "purchase_order": (PurchaseOrder, PurchaseOrderItem, "po_id"),
    "invoice": (Invoice, InvoiceItem, "invoice_id"),
}


def _item_kind(entity_type: str, item) -> str | None:
    if entity_type == "expense_claim":
        return "marketing" if item.category == "marketing" else None
    if entity_type == "invoice":
        if item.invoice_item_type in EMPLOYER_CONTRIBUTIONS:
            return "labour"
        return "marketing" if item.invoice_item_type == "marketing" else None
    return None


def document_impact(db: Session, entity_type: str, document, *, may_read_payroll: bool) -> list[dict]:
    """Which budget lines this document draws on, and what each has left
    before and after it — what an approval flow reads before money moves."""
    family = SPENDING_DOCUMENTS.get(entity_type)
    if family is None or (entity_type == "invoice" and document.direction != "purchase"):
        return []
    _, item_model, parent_field = family
    items = db.scalars(select(item_model).where(
        item_model.tenant_id == document.tenant_id, getattr(item_model, parent_field) == document.id, _live(item_model),
    )).all()
    if not items:
        return []
    counted = document.status in counted_states(db, document.tenant_id, entity_type)
    budgets = db.scalars(select(Budget).where(
        Budget.tenant_id == document.tenant_id, _live(Budget), Budget.direction == "spend",
        Budget.status.in_(budget_states(db, document.tenant_id).unclosed), Budget.currency == document.currency,
    )).all()
    out = []
    cash = _Applications(db, document.tenant_id)
    for budget in budgets:
        scope = Scope.of(db, budget)
        # Use the collector on both sides of the transition: a downstream
        # invoice replaces a commitment; it does not spend the same money again.
        before_items = _spend(db, scope, cash, (type(document), document.id, False))
        after_items = _spend(db, scope, cash, (type(document), document.id, True))
        private_lines = payroll_line_ids(scope, before_items + after_items)
        plan = planned(db, budget)

        def consumption(found):
            totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
            for contribution in found:
                if contribution.line_id and contribution.stage in ("requested", "committed", "actual"):
                    totals[contribution.line_id] += contribution.amount
            return totals

        before_used, after_used = consumption(before_items), consumption(after_items)
        drawn: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for item in items:
            day = getattr(item, "expense_date", None) or getattr(document, "invoice_date", None) \
                or getattr(document, "order_date", None) or getattr(document, "request_date", None) \
                or _document_day(document.created_at)
            if not scope.in_period(day) or not scope.covers(document.cost_center_id):
                continue
            if entity_type == "invoice" and item.invoice_item_type in (TAX_LINE, WITHHELD_REMITTANCE):
                continue
            line_id, skip = _target(scope, item.budget_line_id, _item_kind(entity_type, item))
            if line_id and not skip:
                drawn[line_id] += money(item.amount)
                if _item_kind(entity_type, item) == "labour":
                    private_lines.add(line_id)
        affected = set(drawn) | {lid for lid in before_used.keys() | after_used.keys()
                                 if before_used[lid] != after_used[lid]}
        for line in scope.lines:
            line_id = line.id
            if line_id not in affected:
                continue
            amount = drawn.get(line_id, ZERO)
            line_plan = sum((v for (lid, _), v in plan.items() if lid == line_id), ZERO)
            before, after = line_plan - before_used[line_id], line_plan - after_used[line_id]
            row = {
                "budget_id": budget.id, "budget_no": budget.budget_no, "line_id": line.id,
                "line_code": line.line_code, "line_name": line.name, "category": line.category,
                "how": "tagged" if any(i.budget_line_id == line_id for i in items) else "collected",
                "amount": cents(amount), "counted": counted,
                "available_before": cents(before), "available_after": cents(after),
                "would_go_negative": after < 0, "redacted": False,
            }
            if line_id in private_lines and not may_read_payroll:
                row.update(amount=None, available_before=None, available_after=None, would_go_negative=None, redacted=True)
            out.append(row)
    return out


# --- tagging spend (B6, B12) --------------------------------------------------

TAGGED_ITEMS = (PurchaseRequestItem, PurchaseOrderItem, InvoiceItem, ExpenseItem)


def _parent(session: Session, item):
    if isinstance(item, PurchaseRequestItem):
        return session.get(PurchaseRequest, item.request_id)
    if isinstance(item, PurchaseOrderItem):
        return session.get(PurchaseOrder, item.po_id)
    if isinstance(item, InvoiceItem):
        return session.get(Invoice, item.invoice_id)
    return session.get(ExpenseClaim, item.claim_id)


def _tag_problem(session: Session, item) -> str | None:
    line = session.get(BudgetLine, item.budget_line_id)
    if line is None or line.tenant_id != item.tenant_id:
        return f"budget line {item.budget_line_id} does not exist"
    budget = session.get(Budget, line.budget_id)
    if budget is None or budget.deleted_at is not None:
        return f"budget line {line.line_code} belongs to no live budget"
    if budget.direction != "spend" or COLLECTING_CATEGORIES.get(line.category) == "income":
        return f"budget line {line.line_code} plans income — spend is tagged to a spend budget's line"
    if line.status != "active":
        return f"budget line {line.line_code} is closed"
    if budget.status not in budget_states(session, budget.tenant_id).taking_tags:
        return f"budget {budget.budget_no} is {budget.status!r} — nothing new is tagged to it"
    parent = _parent(session, item)
    if parent is None:
        return None
    if isinstance(item, InvoiceItem) and parent.direction != "purchase":
        return "only a purchase invoice's lines are tagged to a budget line; sales and payroll are collected by rule"
    if parent.currency != budget.currency:
        return f"the document is in {parent.currency}, budget {budget.budget_no} in {budget.currency}"
    if budget.cost_center_id:
        centre = parent.cost_center_id
        if centre not in centres_under(session, budget.tenant_id, budget.cost_center_id):
            return (f"budget {budget.budget_no} is cost centre {budget.cost_center_id}'s, and the document is "
                    f"booked to {centre or 'no cost centre'} — name the centre on the document first")
    day = getattr(item, "expense_date", None) or getattr(parent, "invoice_date", None) \
        or getattr(parent, "order_date", None) or getattr(parent, "request_date", None)
    if day is not None and not (budget.period_start <= day <= budget.period_end):
        return f"the document's date {day} is outside budget {budget.budget_no}'s period"
    return None


@event.listens_for(Session, "before_flush")
def _budget_tags(session: Session, flush_context, instances) -> None:
    """Every write of a spending line passes here, whichever endpoint, import
    or bridge made it — the audit trail's reason for listening at the ORM.
    An explicit tag must fit (B12) or the write is refused; a tag copied
    forward from the request or order line is kept only where it fits, so a
    budget never blocks the purchase it did not plan."""
    candidates = [obj for obj in (*session.new, *session.dirty) if isinstance(obj, TAGGED_ITEMS)]
    if not candidates:
        return
    with session.no_autoflush:
        for item in candidates:
            copied = False
            if item in session.new and item.budget_line_id is None:
                source = None
                if isinstance(item, PurchaseOrderItem) and item.purchase_request_item_id:
                    source = session.get(PurchaseRequestItem, item.purchase_request_item_id)
                elif isinstance(item, InvoiceItem) and item.purchase_order_item_id:
                    source = session.get(PurchaseOrderItem, item.purchase_order_item_id)
                if source is not None and source.budget_line_id:
                    item.budget_line_id, copied = source.budget_line_id, True
            if item.budget_line_id is None:
                continue
            changed = item in session.new or inspect(item).attrs.budget_line_id.history.has_changes()
            if not changed:
                continue
            problem = _tag_problem(session, item)
            if problem is None:
                continue
            if copied:
                item.budget_line_id = None
                continue
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail=f"budget_line_id: {problem}")
