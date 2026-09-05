"""Bulk import of historical sales documents — quotations and orders.

A migration path, not a second way to file today's work. Hundreds of
thousands of rows arrive from an Excel export of a retired system, so three
things differ from the live create endpoints, each on purpose:

- **The document number is required and is the identity.** Historical
  documents keep their own QT-/SO- numbers, so nothing is server-allocated —
  which also means the per-tenant advisory lock that serializes number
  allocation is never taken, and an import is not throttled by it. The number
  is also the upsert key, so re-running a file is idempotent and a
  half-finished migration resumes by simply running it again.

- **Any state of the tenant's machine is accepted.** These documents already
  ended (成交/流失/过期); walking them through the lifecycle would fabricate a
  history that did not happen.

- **Master data is referenced by the tenant's own codes**, because that is
  what an export holds — customer_code, product_code, employee_code. A code
  that matches nothing is reported per document rather than invented, and the
  caller chooses whether such a document is skipped or imported with the
  historical text kept as a snapshot.

The judgment half stays in the conversation, as everywhere in this family:
which spreadsheet column meant what, whether an unmatched customer should be
created first or accepted as text. This module only executes the decision.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Customer,
    Employee,
    Invoice,
    InvoiceItem,
    Payment,
    Product,
    ProductSku,
    Project,
    PurchaseOrder,
    PurchaseOrderAdjustment,
    PurchaseOrderItem,
    SalesOrder,
    SalesOrderAdjustment,
    SalesOrderItem,
    SalesQuotation,
    SalesQuotationAdjustment,
    SalesQuotationItem,
)
from app.models import Vendor
from app.services.master_data_import import _payload, _same_value

# family key → everything that differs between quotations and orders
FAMILIES: dict[str, dict[str, Any]] = {
    "quotation": {
        "model": SalesQuotation,
        "item_model": SalesQuotationItem,
        "adjustment_model": SalesQuotationAdjustment,
        "number_field": "quote_number",
        "parent_field": "quotation_id",
        "adjustment_item_field": "quotation_item_id",
        "date_field": "quote_date",
        "label": "sales_quotation",
    },
    "order": {
        "model": SalesOrder,
        "item_model": SalesOrderItem,
        "adjustment_model": SalesOrderAdjustment,
        "number_field": "order_no",
        "parent_field": "order_id",
        "adjustment_item_field": "order_item_id",
        "date_field": "order_date",
        "label": "sales_order",
    },
    "purchase_order": {
        "model": PurchaseOrder,
        "item_model": PurchaseOrderItem,
        "adjustment_model": PurchaseOrderAdjustment,
        "number_field": "po_number",
        "parent_field": "po_id",
        "adjustment_item_field": "po_item_id",
        "date_field": "order_date",
        "label": "purchase_order",
    },
    # 期初应收应付: the open bills a company carries across the switch. No
    # adjustment model — charges and allowances are line TYPES on an invoice
    # (OFBiz invoiceItemTypeId), so this family imports lines only.
    "invoice": {
        "model": Invoice,
        "item_model": InvoiceItem,
        "adjustment_model": None,
        "number_field": "invoice_no",
        "parent_field": "invoice_id",
        "adjustment_item_field": None,
        "date_field": "invoice_date",
        "label": "invoice",
        # one column for either side, since the direction already says which
        "snapshot_field": "counterparty_name_snapshot",
    },
    # Historical money movements. No lines and no adjustments — a payment is a
    # single fact. What each imported payment SETTLED is deliberately not part
    # of a row: writing applications straight into the ledger would bypass the
    # over-application, direction and currency guards that make the ledger
    # trustworthy. Import the money, then 核销 through POST /payments/{id}/apply.
    "payment": {
        "model": Payment,
        "item_model": None,
        "adjustment_model": None,
        "number_field": "payment_no",
        "parent_field": None,
        "adjustment_item_field": None,
        "date_field": "payment_date",
        "label": "payment",
        "snapshot_field": "counterparty_name_snapshot",
    },
}

# header columns that map straight through, per family
_COMMON_HEADER_FIELDS = (
    "customer_name_snapshot", "contact_name", "contact_phone", "title",
    "currency", "payment_terms", "delivery_terms", "total_amount", "remarks",
)
_QUOTATION_HEADER_FIELDS = _COMMON_HEADER_FIELDS + (
    "contact_email", "quote_date", "valid_until", "status", "outcome_note",
)
_ORDER_HEADER_FIELDS = _COMMON_HEADER_FIELDS + (
    "source_quote_number", "ship_to_address", "contract_no", "order_date",
    "promised_date", "status",
)
_PURCHASE_ORDER_HEADER_FIELDS = (
    "vendor_name_snapshot", "title", "contract_no", "order_date",
    "promised_date", "currency", "payment_terms", "delivery_terms",
    "total_amount", "remarks", "status",
)
_INVOICE_HEADER_FIELDS = (
    "direction", "invoice_type", "counterparty_name_snapshot", "title",
    "invoice_date", "due_date", "currency", "total_amount", "tax_amount",
    "tax_invoice_code", "tax_invoice_number", "remarks", "status",
)
HEADER_FIELDS: dict[str, tuple[str, ...]] = {
    "quotation": _QUOTATION_HEADER_FIELDS,
    "order": _ORDER_HEADER_FIELDS,
    "purchase_order": _PURCHASE_ORDER_HEADER_FIELDS,
    "invoice": _INVOICE_HEADER_FIELDS,
    "payment": (
        "direction", "payment_method", "counterparty_name_snapshot", "payment_date",
        "amount", "currency", "bank_account", "counterparty_account", "reference_no",
        "remarks", "status",
    ),
}

_COMMON_LINE_FIELDS = (
    "line_no", "product_name_snapshot", "spec", "quantity", "unit",
    "list_price_snapshot", "unit_price", "amount", "tax_rate", "is_gift", "notes",
)
# purchase lines carry no list price and are never gifts — those two columns
# simply do not exist on purchase_order_items
_PURCHASE_LINE_FIELDS = (
    "line_no", "product_name_snapshot", "spec", "quantity", "unit",
    "unit_price", "amount", "tax_rate", "notes",
)
# invoice lines carry their own type and a per-line tax amount; quantity and
# price are both optional, since a pure charge line has neither
_INVOICE_LINE_FIELDS = (
    "line_no", "invoice_item_type", "product_name_snapshot", "spec", "quantity",
    "unit", "unit_price", "amount", "tax_rate", "tax_amount", "notes",
)
# keyed by the spec label, which is what _replace_children has in hand
LINE_FIELDS: dict[str, tuple[str, ...]] = {
    "purchase_order": _PURCHASE_LINE_FIELDS,
    "invoice": _INVOICE_LINE_FIELDS,
}


def _normalize(raw: Any) -> str:
    return str(raw).strip() if raw is not None else ""


class _References:
    """Every master-data code the file mentions, resolved in one query per
    family. A 500-row file with 1500 lines costs five reads, not fifteen
    hundred — the difference between a migration that finishes and one that
    is still running tomorrow."""

    def __init__(self, db: Session, tenant_id: str, rows: list[Any], number_field: str):
        employee_codes, customer_codes, project_codes = set(), set(), set()
        vendor_codes: set[str] = set()
        product_codes, sku_codes = set(), set()
        for row in rows:
            if row.employee_code:
                employee_codes.add(row.employee_code.strip())
            if getattr(row, "customer_code", None):
                customer_codes.add(row.customer_code.strip())
            if getattr(row, "project_code", None):
                project_codes.add(row.project_code.strip())
            if getattr(row, "vendor_code", None):
                vendor_codes.add(row.vendor_code.strip())
            if getattr(row, "payee_employee_code", None):
                employee_codes.add(row.payee_employee_code.strip())
            for line in getattr(row, "items", ()):
                if line.product_code:
                    product_codes.add(line.product_code.strip())
                if line.sku_code:
                    sku_codes.add(line.sku_code.strip())

        def by_code(model, column, codes):
            if not codes:
                return {}
            found = db.scalars(
                select(model).where(model.tenant_id == tenant_id, column.in_(sorted(codes)))
            ).all()
            return {getattr(obj, column.key): obj for obj in found}

        # explicit ids are checked the same way codes are: an id that is not
        # this tenant's is a missing reference, never a silent cross-tenant
        # pointer (review R06)
        def by_id(model, ids):
            if not ids:
                return set()
            return set(db.scalars(select(model.id).where(model.tenant_id == tenant_id, model.id.in_(ids))))

        employee_ids = {r.employee_id for r in rows if getattr(r, "employee_id", None)}
        employee_ids |= {r.payee_employee_id for r in rows if getattr(r, "payee_employee_id", None)}
        self.employee_ids = by_id(Employee, employee_ids)
        self.vendor_ids = by_id(Vendor, {r.vendor_id for r in rows if getattr(r, "vendor_id", None)})
        self.customer_ids = by_id(Customer, {r.customer_id for r in rows if getattr(r, "customer_id", None)})
        self.employees = by_code(Employee, Employee.employee_code, employee_codes)
        self.customers = by_code(Customer, Customer.customer_code, customer_codes)
        self.projects = by_code(Project, Project.project_code, project_codes)
        self.vendors = by_code(Vendor, Vendor.vendor_code, vendor_codes)
        self.products = by_code(Product, Product.product_code, product_codes)
        self.skus = by_code(ProductSku, ProductSku.sku_code, sku_codes)


def _resolve_row(
    row: Any, refs: _References, on_missing_reference: str, snapshot_field: str | None = None
) -> tuple[dict[str, Any], list[str]]:
    """Turn the row's codes into ids. Returns (resolved, missing) — `missing`
    names every code that matched nothing, which the caller turns into a row
    error or tolerates as snapshot text.

    `snapshot_field` overrides where the counterparty's name lands. Orders keep
    a column per side (`customer_name_snapshot` / `vendor_name_snapshot`)
    because a document has only one kind of counterparty; an invoice has one
    column for either side, since its direction already says which."""
    resolved: dict[str, Any] = {}
    missing: list[str] = []

    if row.employee_id:
        if row.employee_id in refs.employee_ids:
            resolved["employee_id"] = row.employee_id
        else:
            missing.append(f"employee_id {row.employee_id} (not in this workspace)")
    elif row.employee_code:
        employee = refs.employees.get(row.employee_code.strip())
        if employee is None:
            # the salesperson is NOT optional on these documents, so an
            # unmatched one is always a row error, snapshot mode or not
            missing.append(f"employee_code {row.employee_code}")
        else:
            resolved["employee_id"] = employee.id

    if getattr(row, "vendor_id", None):
        if row.vendor_id in refs.vendor_ids:
            resolved["vendor_id"] = row.vendor_id
        else:
            missing.append(f"vendor_id {row.vendor_id} (not in this workspace)")
    elif getattr(row, "vendor_code", None):
        vendor = refs.vendors.get(row.vendor_code.strip())
        if vendor is None:
            # a PO's counterparty is not optional, snapshot mode or not
            missing.append(f"vendor_code {row.vendor_code}")
        else:
            resolved["vendor_id"] = vendor.id
            # the file's own snapshot is what the document PRINTED — it wins;
            # the master-data name only fills a blank
            field = snapshot_field or "vendor_name_snapshot"
            if not getattr(row, field, None):
                resolved[field] = vendor.name

    if getattr(row, "customer_id", None):
        if row.customer_id in refs.customer_ids:
            resolved["customer_id"] = row.customer_id
        else:
            missing.append(f"customer_id {row.customer_id} (not in this workspace)")
    elif getattr(row, "customer_code", None):
        customer = refs.customers.get(row.customer_code.strip())
        if customer is None:
            if on_missing_reference == "error":
                missing.append(f"customer_code {row.customer_code}")
            # snapshot mode: customer_id stays null and the historical name
            # on the row stands alone — the document is still true
        else:
            resolved["customer_id"] = customer.id
            field = snapshot_field or "customer_name_snapshot"
            if not getattr(row, field, None):
                resolved[field] = customer.name

    if getattr(row, "project_code", None):
        project = refs.projects.get(row.project_code.strip())
        if project is None:
            if on_missing_reference == "error":
                missing.append(f"project_code {row.project_code}")
        else:
            resolved["project_id"] = project.id

    return resolved, missing


def _resolve_line(line: Any, refs: _References, on_missing_reference: str) -> tuple[dict, list[str]]:
    resolved: dict[str, Any] = {}
    missing: list[str] = []
    product = refs.products.get(line.product_code.strip()) if line.product_code else None
    sku = refs.skus.get(line.sku_code.strip()) if line.sku_code else None
    if line.product_code and product is None and on_missing_reference == "error":
        missing.append(f"product_code {line.product_code}")
    if line.sku_code and sku is None and on_missing_reference == "error":
        missing.append(f"sku_code {line.sku_code}")
    if product is not None:
        resolved["product_id"] = product.id
    if sku is not None:
        resolved["sku_id"] = sku.id
        resolved.setdefault("product_id", sku.product_id)
    return resolved, missing


def bulk_import_documents(
    db: Session,
    *,
    tenant_id: str,
    family: str,
    rows: list[Any],
    machine_states: set[str],
    # the tenant machine's own initial — a row that states no status starts
    # here, because "draft" is the shipped machine's word, not necessarily
    # this workspace's
    initial_state: str,
    dry_run: bool = False,
    on_error: str = "skip",
    on_missing_reference: str = "error",
) -> dict:
    """Upsert historical documents keyed on their own number.

    Flushed, never committed: the caller owns the transaction, so dry_run is
    an honest preview of the identical write path (same contract as the
    master-data import).
    """
    spec = FAMILIES[family]
    model = spec["model"]
    number_field = spec["number_field"]
    header_fields = HEADER_FIELDS[family]

    results: list[dict] = []
    seen: dict[str, int] = {}
    prepared: list[tuple[int, str, Any, dict]] = []

    # Pass 1 — row-local validation and reference resolution. Nothing touches
    # the session, so an abort costs no writes at all.
    refs = _References(db, tenant_id, rows, number_field)
    for index, row in enumerate(rows):
        number = _normalize(getattr(row, number_field))
        if not number:
            results.append({
                "index": index, "number": None, "outcome": "error",
                "error": f"{number_field} is required and cannot be blank",
            })
            continue
        if number in seen:
            results.append({
                "index": index, "number": number, "outcome": "error",
                "error": f"duplicate {number_field} in this batch (also row {seen[number]})",
            })
            continue
        if row.status is None:
            row.status = initial_state
        if row.status not in machine_states:
            results.append({
                "index": index, "number": number, "outcome": "error",
                "error": (
                    f"status {row.status!r} is not a state of the tenant's "
                    f"{spec['label']} machine — active states: {', '.join(sorted(machine_states))}"
                ),
            })
            continue

        resolved, missing = _resolve_row(
            row, refs, on_missing_reference, spec.get("snapshot_field")
        )
        rows_items = getattr(row, "items", ())
        line_numbers = [line.line_no for line in rows_items if line.line_no is not None]
        if len(line_numbers) != len(set(line_numbers)):
            missing.append("duplicate line_no within the document")
        for line in rows_items:
            _, line_missing = _resolve_line(line, refs, on_missing_reference)
            missing.extend(line_missing)
        pinned = {a.line_no for a in getattr(row, "adjustments", ()) if a.line_no is not None}
        unknown_pins = sorted(pinned - set(line_numbers))
        if unknown_pins:
            missing.append(
                f"adjustment pinned to line_no {', '.join(str(p) for p in unknown_pins)} "
                "which this document does not have"
            )
        if "employee_id" not in resolved:
            missing.append("employee_code or employee_id is required")
        if family == "purchase_order" and "vendor_id" not in resolved:
            missing.append("vendor_code or vendor_id is required")
        if family == "invoice":
            # the direction decides which counterparty is the legal one, and the
            # database CHECK refuses the wrong pairing anyway — catching it here
            # reports the row instead of aborting the batch
            required = "customer_id" if row.direction == "sales" else "vendor_id"
            forbidden = "vendor_id" if row.direction == "sales" else "customer_id"
            if required not in resolved:
                missing.append(
                    f"a {row.direction!r} invoice needs "
                    f"{'customer_code or customer_id' if required == 'customer_id' else 'vendor_code or vendor_id'}"
                )
            if forbidden in resolved:
                missing.append(f"a {row.direction!r} invoice carries {required}, not {forbidden}")
        if family == "payment":
            # exactly one counterparty, same rule the live endpoint keeps
            if row.payee_employee_id:
                if row.payee_employee_id in refs.employee_ids:
                    resolved["payee_employee_id"] = row.payee_employee_id
                else:
                    missing.append(f"payee_employee_id {row.payee_employee_id} (not in this workspace)")
            elif row.payee_employee_code:
                payee = refs.employees.get(row.payee_employee_code.strip())
                if payee is None:
                    missing.append(f"payee_employee_code {row.payee_employee_code}")
                else:
                    resolved["payee_employee_id"] = payee.id
                    if not row.counterparty_name_snapshot:
                        resolved["counterparty_name_snapshot"] = payee.name
            named = [
                field for field in ("customer_id", "vendor_id", "payee_employee_id")
                if resolved.get(field)
            ]
            if len(named) != 1:
                missing.append(
                    "a payment names exactly one counterparty: customer_code, vendor_code "
                    "or payee_employee_code"
                )
        if missing:
            results.append({
                "index": index, "number": number, "outcome": "error",
                "error": "; ".join(dict.fromkeys(missing)),
            })
            continue

        seen[number] = index
        prepared.append((index, number, row, resolved))

    if on_error == "abort" and any(r["outcome"] == "error" for r in results):
        return _payload(results, dry_run=dry_run, applied=False, total=len(rows))

    # Pass 2 — resolve existing documents in ONE query.
    numbers = [number for _i, number, _r, _res in prepared]
    existing: dict[str, Any] = {}
    if numbers:
        found = db.scalars(
            select(model).where(
                model.tenant_id == tenant_id,
                getattr(model, number_field).in_(numbers),
                model.deleted_at.is_(None),
            )
        ).all()
        existing = {getattr(obj, number_field): obj for obj in found}

    for index, number, row, resolved in prepared:
        document = existing.get(number)
        values = {field: getattr(row, field) for field in header_fields}
        values.update(resolved)
        values["custom_fields_jsonb"] = row.custom_fields

        if document is not None:
            frozen = _why_not_rewritable(db, document)
            if frozen:
                # the importer follows the same rule every other entrance does:
                # a settled, posted or issued document is corrected by a
                # counter-entry, a void or a credit note — never rewritten
                # under its own number (review R01)
                results.append({"index": index, "number": number, "outcome": "error",
                                "id": document.id, "error": frozen})
                continue

        if document is None:
            document = model(tenant_id=tenant_id, **{number_field: number}, **values)
            db.add(document)
            db.flush()
            _replace_children(db, tenant_id, spec, document, row, refs, on_missing_reference)
            results.append({
                "index": index, "number": number, "outcome": "created", "id": document.id,
            })
            existing[number] = document
            continue

        changed = [
            field for field, value in values.items()
            if field != "custom_fields_jsonb" and not _same_value(getattr(document, field), value)
        ]
        for field, value in values.items():
            setattr(document, field, value)
        # children are replaced wholesale: a historical document is a single
        # fact, and a re-import is the corrected version of that whole fact
        if _replace_children(db, tenant_id, spec, document, row, refs, on_missing_reference):
            changed.append("items")
        if changed:
            db.flush()
        results.append({
            "index": index, "number": number,
            "outcome": "updated" if changed else "unchanged",
            "id": document.id, "changed": changed,
        })

    return _payload(results, dry_run=dry_run, applied=not dry_run, total=len(rows))


def _why_not_rewritable(db: Session, document) -> str | None:
    """A historical document may be corrected by re-import — that is what a
    migration is — right up to the point where something else stands on it.
    Money applied to or from it, an order written from it, a shipment or a
    stock posting that names it: from then on the document is the baseline
    those facts are measured against, and a rewrite would leave them
    contradicting it. The importer used to skip this and rewrote a
    fully-settled payment's amount to 1 while its 100 of applications stood
    (review R01). Corrections past this point are counter-entries, voids and
    credit notes — the same answer every other entrance gives."""
    from fastapi import HTTPException

    from app.api.common import ensure_not_consumed_by_an_order
    from app.models import Shipment

    applied = float(getattr(document, "applied_amount", 0) or 0)
    if applied > 0:
        return (
            f"{applied} is already applied to this document — a settled document is "
            "corrected by a counter-entry or a void, never rewritten by re-import"
        )
    try:
        ensure_not_consumed_by_an_order(db, document)
    except HTTPException as exc:
        return f"{exc.detail} — not rewritable by re-import"
    order_column = {"SalesOrder": Shipment.sales_order_id, "PurchaseOrder": Shipment.purchase_order_id}.get(type(document).__name__)
    if order_column is not None and db.scalar(
        select(Shipment.id).where(order_column == document.id, Shipment.deleted_at.is_(None)).limit(1)
    ):
        return "a shipment already names this order — its lines are what the warehouse shipped against; correct by a return or a counter-entry, not by re-import"
    return None


def _replace_children(
    db: Session, tenant_id: str, spec: dict, document: Any, row: Any,
    refs: _References, on_missing_reference: str,
) -> bool:
    """Rewrite the document's lines and adjustments from the row. Returns
    whether anything differs from what was there — so a re-import of an
    unchanged file still reports `unchanged`."""
    item_model = spec["item_model"]
    adjustment_model = spec["adjustment_model"]
    parent_field = spec["parent_field"]
    if item_model is None:
        # a family whose document IS the whole fact (a payment) — nothing hangs
        # off it, so there is never a child difference to report
        return False

    current_items = db.scalars(
        select(item_model).where(
            item_model.tenant_id == tenant_id,
            getattr(item_model, parent_field) == document.id,
            item_model.deleted_at.is_(None),
        ).order_by(item_model.line_no.asc().nulls_last(), item_model.created_at.asc())
    ).all()
    current_adjustments = (
        db.scalars(
            select(adjustment_model).where(
                adjustment_model.tenant_id == tenant_id,
                getattr(adjustment_model, parent_field) == document.id,
                adjustment_model.deleted_at.is_(None),
            )
        ).all()
        if adjustment_model is not None
        else []
    )

    incoming_items = []
    line_fields = LINE_FIELDS.get(spec["label"], _COMMON_LINE_FIELDS)
    for line in row.items:
        values = {field: getattr(line, field) for field in line_fields}
        if spec["label"] == "sales_quotation":
            values["lead_time"] = line.lead_time
        elif spec["label"] == "invoice":
            # the billed order line, when the migration knows it
            values["sales_order_item_id"] = None
            values["purchase_order_item_id"] = None
        else:
            values["promised_date"] = line.promised_date
        resolved, _ = _resolve_line(line, refs, on_missing_reference)
        values.update(resolved)
        values["custom_fields_jsonb"] = line.custom_fields
        incoming_items.append(values)

    incoming_adjustments = [
        {
            "adjustment_type": adjustment.adjustment_type,
            "description": adjustment.description,
            "amount": adjustment.amount,
            "source_percentage": adjustment.source_percentage,
            "line_no": adjustment.line_no,
            "metadata_jsonb": adjustment.metadata,
        }
        for adjustment in getattr(row, "adjustments", ())
    ]

    def unchanged(current_rows: list, incoming: list[dict], order_key) -> bool:
        """Field-by-field through _same_value — the stored side is Decimal for
        every money/quantity column while the incoming side is a JSON float,
        and comparing those raw is the phantom-update trap that made every
        re-import report a change forever.

        BOTH sides are sorted by the same key: the stored rows come back in
        whatever order the database chose, so comparing them positionally
        against the file's order would call a re-import "changed" purely
        because two adjustments swapped places."""
        if len(current_rows) != len(incoming):
            return False
        fields = list(incoming[0]) if incoming else []
        current_values = [{field: getattr(row, field) for field in fields} for row in current_rows]
        pairs = zip(sorted(current_values, key=order_key), sorted(incoming, key=order_key))
        return all(
            all(_same_value(current[field], values[field]) for field in fields)
            for current, values in pairs
        )

    same_items = unchanged(
        current_items, incoming_items, lambda v: (v.get("line_no") is None, v.get("line_no") or 0)
    )
    same_adjustments = unchanged(
        current_adjustments,
        [{k: v for k, v in a.items() if k != "line_no"} for a in incoming_adjustments],
        lambda v: (v.get("adjustment_type") or "", float(v.get("amount") or 0)),
    )
    if same_items and same_adjustments:
        return False

    for item in current_items:
        db.delete(item)
    for adjustment in current_adjustments:
        db.delete(adjustment)
    db.flush()

    line_ids: dict[int, str] = {}
    for values in incoming_items:
        item = item_model(tenant_id=tenant_id, **{parent_field: document.id}, **values)
        db.add(item)
        db.flush()
        if values.get("line_no") is not None:
            line_ids[values["line_no"]] = item.id
    # a family without an adjustment model never has incoming adjustments —
    # its rows carry no such column — so this loop simply does not run
    for values in incoming_adjustments:
        line_no = values.pop("line_no")
        db.add(adjustment_model(
            tenant_id=tenant_id,
            **{parent_field: document.id},
            **{spec["adjustment_item_field"]: line_ids.get(line_no)},
            **values,
        ))
    db.flush()
    return True
