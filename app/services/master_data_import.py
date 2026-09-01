"""Bulk upsert for the master-data families a spreadsheet import feeds:
products, vendors, and customers.

The three tables share a shape — a tenant-scoped `{entity}_code`, a name, a
status, a metadata blob — so they share one implementation here rather than
three drifting copies in the route layer.

What the server owns and what it does NOT own is the whole design. The server
owns identity and idempotency: the code is the key, an existing code updates,
a new code creates, and running the same import twice changes nothing the
second time. It does NOT own the spreadsheet: which column held the code,
whether 单价 meant list_price, what to do about a row whose code is blank —
that is judgment about a human artifact, and it belongs to the agent talking
to the person who has the file open.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Product, ProductCategory, ProductPrice, SupplierProduct, Vendor
from app.services.type_options import allowed_type_options

# entity key → (model, code attribute). The route layer picks one; everything
# below is family-agnostic.
FAMILIES: dict[str, tuple[type, str]] = {
    "product": (Product, "product_code"),
    "vendor": (Vendor, "vendor_code"),
    "customer": (Customer, "customer_code"),
}

# `metadata` is the API name; `metadata_jsonb` is the column. Every other bulk
# field maps straight through.
COLUMN_ALIASES = {"metadata": "metadata_jsonb"}

# entity family → its columns whose values come from a tenant type vocabulary,
# as (column, type-option family). Same doctrine the nested price rows already
# follow: a value the tenant's catalog does not hold is the ROW's error, taken
# back to the person, never a vocabulary entry the import invents on their
# behalf. A spreadsheet column of 客户分类 is exactly where that would be
# tempting — every unfamiliar word in it looks like a new segment.
TYPE_OPTION_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "customer": (("customer_type", "customer_type"),),
}


def _same_value(current: Any, incoming: Any) -> bool:
    """Change detection must compare in the COLUMN's domain, not Python's.

    Numeric(12,2) columns come back as Decimal while JSON rows carry floats,
    and `Decimal("19.90") == 19.9` is False — float equality is against the
    exact binary expansion. Compared raw, every price a float cannot represent
    reported `updated, changed: ["list_price"]` on each re-run of the same
    file, forever: a phantom of exactly the "every row updated the same odd
    field" alarm agents are told to escalate. So quantize the incoming number
    to what the database will actually store — two decimals, half-up, the
    scale of the families' only numeric column — and compare that."""
    if isinstance(current, Decimal) and isinstance(incoming, (int, float)) and not isinstance(incoming, bool):
        return current == Decimal(str(incoming)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return current == incoming


def _normalize_code(raw: Any) -> str:
    """Spreadsheet cells arrive with stray whitespace far more often than not
    ("P-001 " from a merged cell, "\\tP-002" from a paste). Trimming here means
    the same product does not enter twice under codes that look identical to
    the person who typed them."""
    return str(raw).strip()


def _validate_nested(prices: list[dict] | None, suppliers: list[dict] | None) -> str | None:
    """Row-local checks for the nested lists, pass-1 style: a spreadsheet
    claiming two prices for one (type, currency) or two entries for one
    vendor is the person's conflict to resolve, never last-wins."""
    if prices:
        keys = [(p["price_type"], p.get("currency", "CNY")) for p in prices]
        if len(keys) != len(set(keys)):
            return "duplicate (price_type, currency) in prices — one live price per type"
    if suppliers:
        vendor_codes = [s["vendor_code"] for s in suppliers]
        if len(vendor_codes) != len(set(vendor_codes)):
            return "duplicate vendor_code in suppliers"
    return None


def _resolve_vendors(
    db: Session, tenant_id: str, prepared: list, results: list[dict]
) -> dict[str, Vendor]:
    """Map every referenced vendor_code to its Vendor in one read. Rows naming
    a code that does not exist become error rows — the doctrine everywhere in
    this skill family: never invent master data, take the gap to the person."""
    wanted = sorted({s["vendor_code"] for _i, _c, _f, _p, sups in prepared for s in (sups or [])})
    if not wanted:
        return {}
    found = db.scalars(
        select(Vendor).where(Vendor.tenant_id == tenant_id, Vendor.vendor_code.in_(wanted))
    ).all()
    vendors_by_code = {vendor.vendor_code: vendor for vendor in found}
    if len(vendors_by_code) != len(wanted):
        kept = []
        for entry in prepared:
            index, code, _fields, _prices, sups = entry
            unknown = sorted({s["vendor_code"] for s in (sups or []) if s["vendor_code"] not in vendors_by_code})
            if unknown:
                results.append(
                    {
                        "index": index,
                        "code": code,
                        "outcome": "error",
                        "error": f"unknown vendor_code {', '.join(unknown)} — import the vendor first, never invent one",
                    }
                )
            else:
                kept.append(entry)
        prepared[:] = kept
    return vendors_by_code


def _apply_prices(db: Session, tenant_id: str, product_id: str, specs: list[dict] | None) -> bool:
    """Upsert price-book entries on (price_type, currency), history via
    status: an equal live price is a no-op, a different one archives the old
    row and creates the new. The .get defaults mirror BulkProductPriceRow's —
    exclude_unset dumps omit unsent fields."""
    changed = False
    for spec in specs or []:
        currency = spec.get("currency", "CNY")
        current = db.scalar(
            select(ProductPrice).where(
                ProductPrice.tenant_id == tenant_id,
                ProductPrice.product_id == product_id,
                ProductPrice.sku_id.is_(None),
                ProductPrice.price_type == spec["price_type"],
                ProductPrice.currency == currency,
                ProductPrice.status == "active",
            )
        )
        tax_in_price = spec.get("tax_in_price", True)
        tax_percentage = spec.get("tax_percentage")
        if (
            current is not None
            and _same_value(current.price, spec["price"])
            and current.tax_in_price == tax_in_price
            and _same_value(current.tax_percentage, tax_percentage)
        ):
            continue
        if current is not None:
            current.status = "archived"
        db.add(
            ProductPrice(
                tenant_id=tenant_id,
                product_id=product_id,
                sku_id=None,
                price_type=spec["price_type"],
                price=spec["price"],
                currency=currency,
                tax_in_price=tax_in_price,
                tax_percentage=tax_percentage,
            )
        )
        changed = True
    if changed:
        db.flush()
    return changed


# the SupplierProduct columns a bulk supplier spec may carry, verbatim
_SUPPLIER_FIELDS = (
    "supplier_product_code",
    "supplier_product_name",
    "last_price",
    "currency",
    "lead_time_days",
    "min_order_quantity",
    "order_increment",
    "preference",
)


def _apply_suppliers(
    db: Session,
    tenant_id: str,
    product_id: str,
    specs: list[dict] | None,
    vendors_by_code: dict[str, Vendor],
) -> bool:
    """Upsert supply sources on (product, vendor). Fields update in place —
    last_price means "most recent", price history belongs to ProductPrice —
    only fields the row actually sent are touched, and re-importing an
    archived pair revives it."""
    changed = False
    for spec in specs or []:
        vendor = vendors_by_code[spec["vendor_code"]]
        link = db.scalar(
            select(SupplierProduct).where(
                SupplierProduct.tenant_id == tenant_id,
                SupplierProduct.product_id == product_id,
                SupplierProduct.vendor_id == vendor.id,
            )
        )
        if link is None:
            db.add(
                SupplierProduct(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    vendor_id=vendor.id,
                    currency=spec.get("currency", "CNY"),
                    **{f: spec.get(f) for f in _SUPPLIER_FIELDS if f != "currency"},
                )
            )
            changed = True
            continue
        for field in _SUPPLIER_FIELDS:
            if field in spec and not _same_value(getattr(link, field), spec[field]):
                setattr(link, field, spec[field])
                changed = True
        if link.status != "active":
            link.status = "active"
            changed = True
    if changed:
        db.flush()
    return changed


def bulk_upsert(
    db: Session,
    *,
    tenant_id: str,
    family: str,
    rows: list[Any],
    dry_run: bool = False,
    on_error: str = "abort",
) -> dict:
    """Upsert `rows` (validated Pydantic models) keyed on the family's code.

    Returns the result payload: a summary plus one entry per input row, in
    input order, each carrying its source index so the agent can name the
    offending spreadsheet line.

    Only fields the caller actually SET are written. A spreadsheet with just
    code/name/price must not blank out the `spec` and `unit` a colleague
    curated in the console last month — absent is not the same as empty, and
    conflating them turns a partial import into silent data loss.

    Rows are flushed, never committed: the CALLER owns the transaction, so it
    can record one audit entry for the import in the same one and commit both
    together — or roll back, which is how `dry_run` stays honest. A preview
    that ran the real code path cannot drift from the write it previews.
    """
    model, code_attr = FAMILIES[family]

    results: list[dict] = []
    seen_codes: dict[str, int] = {}
    prepared: list[tuple[int, str, dict]] = []

    # Pass 1 — validate row-locally. Nothing touches the session yet, so an
    # abort costs no writes at all.
    for index, row in enumerate(rows):
        code = _normalize_code(getattr(row, code_attr))
        if not code:
            results.append(
                {
                    "index": index,
                    "code": None,
                    "outcome": "error",
                    "error": f"{code_attr} is required and cannot be blank",
                }
            )
            continue
        if code in seen_codes:
            # Two rows claiming the same code is a defect in the spreadsheet,
            # not something to resolve by picking one: last-wins would apply a
            # value the person never chose, and silently.
            results.append(
                {
                    "index": index,
                    "code": code,
                    "outcome": "error",
                    "error": f"duplicate {code_attr} in this batch (also row {seen_codes[code]})",
                }
            )
            continue
        seen_codes[code] = index
        fields = row.model_dump(exclude_unset=True, by_alias=False)
        fields.pop(code_attr, None)
        # nested price-book / supply-source writes (product rows only); they
        # are handled apart from the column loop — there are no such columns
        prices = fields.pop("prices", None)
        suppliers = fields.pop("suppliers", None)
        nested_error = _validate_nested(prices, suppliers)
        if nested_error:
            results.append({"index": index, "code": code, "outcome": "error", "error": nested_error})
            continue
        prepared.append((index, code, fields, prices, suppliers))

    # Resolve supplier vendor_codes in one read before anything writes: an
    # unknown vendor is the row's error to take back to the person, never a
    # vendor to invent.
    vendors_by_code = _resolve_vendors(db, tenant_id, prepared, results)

    # Category codes join product rows to the shelving tree — the vendor
    # doctrine again: an unknown code is the row's error to take back to the
    # person, never a category to invent, and an archived one names its fix.
    # Explicit null clears the product's category; the code column never
    # reaches the model (products carry category_id).
    wanted_categories = sorted({
        fields["category_code"]
        for _i, _c, fields, _p, _s in prepared
        if fields.get("category_code") is not None
    })
    categories_by_code = {}
    if wanted_categories:
        categories_by_code = {
            c.category_code: c
            for c in db.scalars(
                select(ProductCategory).where(
                    ProductCategory.tenant_id == tenant_id,
                    ProductCategory.category_code.in_(wanted_categories),
                )
            )
        }
    if any("category_code" in fields for _i, _c, fields, _p, _s in prepared):
        kept = []
        for entry in prepared:
            index, code, fields, _prices, _suppliers = entry
            if "category_code" not in fields:
                kept.append(entry)
                continue
            value = fields.pop("category_code")
            if value is None:
                fields["category_id"] = None
                kept.append(entry)
                continue
            category = categories_by_code.get(value)
            if category is None:
                results.append({
                    "index": index, "code": code, "outcome": "error",
                    "error": (
                        f"unknown category_code '{value}' — create the category "
                        "first (POST /product-categories), never invent one"
                    ),
                })
            elif category.status != "active":
                results.append({
                    "index": index, "code": code, "outcome": "error",
                    "error": (
                        f"category_code '{value}' is archived — revive it "
                        "(PATCH status active) before filing products on it"
                    ),
                })
            else:
                fields["category_id"] = category.id
                kept.append(entry)
        prepared[:] = kept

    # Price types come from the tenant's vocabulary (shipped catalog plus
    # custom entries, minus archived) — an unknown one is the row's error.
    if any(prices for _i, _c, _f, prices, _s in prepared):
        allowed_types = allowed_type_options(db, tenant_id, "product_price_type")
        kept = []
        for entry in prepared:
            index, code, _fields, prices, _suppliers = entry
            unknown = sorted({p["price_type"] for p in (prices or [])} - allowed_types)
            if unknown:
                results.append(
                    {
                        "index": index,
                        "code": code,
                        "outcome": "error",
                        "error": (
                            f"unknown price_type {', '.join(unknown)} — active options: "
                            f"{', '.join(sorted(allowed_types))}. "
                            "A price column that fits none of them is a new type: "
                            "define it via POST /type-options "
                            "(family product_price_type), then re-run."
                        ),
                    }
                )
            else:
                kept.append(entry)
        prepared[:] = kept

    # Column-level vocabularies (a customer's segment today) — same treatment,
    # one read per family rather than one per row.
    for column, option_family in TYPE_OPTION_COLUMNS.get(family, ()):
        wanted = {
            fields[column]
            for _i, _c, fields, _p, _s in prepared
            if fields.get(column) is not None
        }
        if not wanted:
            continue
        allowed_values = allowed_type_options(db, tenant_id, option_family)
        if wanted <= allowed_values:
            continue
        kept = []
        for entry in prepared:
            index, code, fields, _prices, _suppliers = entry
            value = fields.get(column)
            if value is not None and value not in allowed_values:
                results.append(
                    {
                        "index": index,
                        "code": code,
                        "outcome": "error",
                        "error": (
                            f"unknown {column} '{value}' — active options: "
                            f"{', '.join(sorted(allowed_values))}. "
                            "A column value that fits none of them is a new type: "
                            f"define it via POST /type-options (family {option_family}), "
                            "then re-run."
                        ),
                    }
                )
            else:
                kept.append(entry)
        prepared[:] = kept

    if on_error == "abort" and any(r["outcome"] == "error" for r in results):
        # Nothing was written — passes so far only read — so the caller's
        # rollback is a formality, but it keeps one exit contract.
        return _payload(results, dry_run=dry_run, applied=False, total=len(rows))

    # Pass 2 — resolve existing rows in ONE query rather than per row, so a
    # 500-row import is two round trips and not five hundred.
    codes = [code for _index, code, _fields, _p, _s in prepared]
    existing = {}
    if codes:
        found = db.scalars(
            select(model).where(
                model.tenant_id == tenant_id,
                getattr(model, code_attr).in_(codes),
            )
        ).all()
        existing = {getattr(obj, code_attr): obj for obj in found}

    for index, code, fields, prices, suppliers in prepared:
        obj = existing.get(code)
        if obj is None:
            obj = model(tenant_id=tenant_id, **{code_attr: code})
            for key, value in fields.items():
                setattr(obj, COLUMN_ALIASES.get(key, key), value)
            db.add(obj)
            db.flush()
            _apply_prices(db, tenant_id, obj.id, prices)
            _apply_suppliers(db, tenant_id, obj.id, suppliers, vendors_by_code)
            results.append({"index": index, "code": code, "outcome": "created", "id": obj.id})
            # a later row in the same batch may reference it; keep the map live
            existing[code] = obj
            continue

        changed = []
        for key, value in fields.items():
            column = COLUMN_ALIASES.get(key, key)
            if not _same_value(getattr(obj, column), value):
                setattr(obj, column, value)
                changed.append(key)
        if _apply_prices(db, tenant_id, obj.id, prices):
            changed.append("prices")
        if _apply_suppliers(db, tenant_id, obj.id, suppliers, vendors_by_code):
            changed.append("suppliers")
        if changed:
            db.flush()
        results.append(
            {
                "index": index,
                "code": code,
                # "unchanged" is not cosmetic: it is how a person re-running an
                # import sees that the second run really was a no-op.
                "outcome": "updated" if changed else "unchanged",
                "id": obj.id,
                "changed": changed,
            }
        )

    # Everything is flushed but NOT committed. The caller owns the transaction
    # so it can write one audit entry for the import inside the same one — the
    # trail then commits if and only if the rows do.
    return _payload(results, dry_run=dry_run, applied=not dry_run, total=len(rows))


def _payload(results: list[dict], *, dry_run: bool, applied: bool, total: int) -> dict:
    results = sorted(results, key=lambda r: r["index"])
    counts = {"created": 0, "updated": 0, "unchanged": 0, "error": 0}
    for row in results:
        counts[row["outcome"]] += 1
    return {
        "dry_run": dry_run,
        "applied": applied,
        "summary": {
            "total": total,
            "created": counts["created"],
            "updated": counts["updated"],
            "unchanged": counts["unchanged"],
            "failed": counts["error"],
        },
        "results": results,
    }
