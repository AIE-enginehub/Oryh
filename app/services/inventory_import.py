"""Inventory: the append-only ledger and the stock-take import that feeds it.

The design rule everything here serves: an InventoryItem's totals are DERIVED.
Nothing writes quantity_on_hand or available_to_promise directly — every
movement is an InventoryItemDetail, and post_inventory_detail() is the only
place the running sums move. A bulk import that finds the system count
different from the counted quantity records the DIFFERENCE as a movement with
reason `import_override`; the item row is never edited into agreement.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import InventoryItem, InventoryItemDetail, Product, ProductSku
from app.services.master_data_import import _payload, _same_value


def post_inventory_detail(
    db: Session,
    *,
    item: InventoryItem,
    quantity_on_hand_diff: float,
    reason: str,
    available_to_promise_diff: float | None = None,
    description: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    sales_order_id: str | None = None,
    purchase_order_id: str | None = None,
    custom_fields: dict | None = None,
    unit_cost: float | None = None,
    effective_at=None,
    created_by: str | None = None,
) -> InventoryItemDetail:
    """The single write path for stock movement: append the ledger row and
    move the item's running sums in the same flush. ATP follows QOH unless the
    caller moves it separately (reservations, later).

    The totals move by a RELATIVE update — `SET x = x + :diff` computed by the
    database, never `SET x = <a number Python worked out>`. Two concurrent
    postings against one item both read the same starting total under READ
    COMMITTED, and an absolute write means the second silently overwrites the
    first: both ledger rows survive, one movement vanishes from the total, and
    nothing errors. Stock is exactly where that happens — receiving, issuing
    and stock-takes all hit the same item row.

    A relative update needs no lock and no retry: the database serializes the
    two writes and both increments land.
    """
    atp_diff = quantity_on_hand_diff if available_to_promise_diff is None else available_to_promise_diff
    detail = InventoryItemDetail(
        tenant_id=item.tenant_id,
        inventory_item_id=item.id,
        quantity_on_hand_diff=quantity_on_hand_diff,
        available_to_promise_diff=atp_diff,
        reason=reason,
        description=description,
        sales_order_id=sales_order_id,
        purchase_order_id=purchase_order_id,
        entity_type=entity_type,
        entity_id=entity_id,
        unit_cost=unit_cost,
        custom_fields_jsonb=custom_fields or {},
        created_by=created_by,
    )
    if effective_at is not None:
        detail.effective_at = effective_at
    db.add(detail)
    db.flush()
    db.execute(
        update(InventoryItem)
        .where(InventoryItem.id == item.id)
        .values(
            quantity_on_hand=InventoryItem.quantity_on_hand + quantity_on_hand_diff,
            available_to_promise=InventoryItem.available_to_promise + atp_diff,
        )
        # the point of the relative form is that the database computes it;
        # letting the ORM mirror it in Python would need the stale value the
        # whole change exists to stop trusting
        .execution_options(synchronize_session=False)
    )
    # the row moved underneath the ORM's copy; expire so any later read of
    # `item` reflects the total the database actually holds
    db.expire(item, ["quantity_on_hand", "available_to_promise"])
    return detail


def _find_item(
    db: Session, tenant_id: str, product_id: str, sku_id: str | None, facility: str, lot_id: str
) -> InventoryItem | None:
    stmt = select(InventoryItem).where(
        InventoryItem.tenant_id == tenant_id,
        InventoryItem.product_id == product_id,
        InventoryItem.facility == facility,
        InventoryItem.lot_id == lot_id,
    )
    stmt = stmt.where(InventoryItem.sku_id == sku_id) if sku_id else stmt.where(InventoryItem.sku_id.is_(None))
    return db.scalar(stmt)


def bulk_inventory_upsert(
    db: Session,
    *,
    tenant_id: str,
    rows: list[Any],
    dry_run: bool = False,
    on_error: str = "abort",
    created_by: str | None = None,
) -> dict:
    """Stock-take import. Same contract as the master-data bulk upserts —
    dry_run runs the identical path and the caller rolls back, on_error abort
    writes nothing when any row is bad, per-row results carry the source
    index — with the ledger rule on top:

    - no stock position yet → create the item and post its opening balance as
      a detail (reason `import_initial`)
    - counted quantity equals the system count → unchanged
    - counted quantity differs → post a detail whose diff is exactly
      (counted - system), reason `import_override`, description naming both
      numbers — the item's totals move only through that detail
    """
    results: list[dict] = []
    seen: dict[tuple, int] = {}
    prepared: list[tuple[int, Any]] = []

    # Pass 1 — row-local validation, no session access.
    for index, row in enumerate(rows):
        code = row.product_code.strip()
        if not code:
            results.append({"index": index, "code": None, "outcome": "error",
                            "error": "product_code is required and cannot be blank"})
            continue
        key = (code, (row.sku_code or "").strip(), row.facility.strip(), row.lot_id.strip())
        if key in seen:
            results.append({"index": index, "code": code, "outcome": "error",
                            "error": f"duplicate stock position in this batch (also row {seen[key]}) — "
                                     "one row per (product, sku, facility, lot)"})
            continue
        seen[key] = index
        prepared.append((index, row))

    # Resolve product codes (and sku codes within them) in bulk reads before
    # anything writes: unknown master data is the row's error to take back to
    # the person, never something to invent.
    codes = sorted({row.product_code.strip() for _i, row in prepared})
    products: dict[str, Product] = {}
    if codes:
        found = db.scalars(
            select(Product).where(Product.tenant_id == tenant_id, Product.product_code.in_(codes))
        ).all()
        products = {p.product_code: p for p in found}
    sku_map: dict[tuple[str, str], ProductSku] = {}
    wanted_skus = sorted({(row.product_code.strip(), row.sku_code.strip())
                          for _i, row in prepared if row.sku_code and row.sku_code.strip()})
    if wanted_skus:
        sku_rows = db.scalars(
            select(ProductSku).where(
                ProductSku.tenant_id == tenant_id,
                ProductSku.sku_code.in_(sorted({s for _p, s in wanted_skus})),
            )
        ).all()
        by_product = {(sku.product_id, sku.sku_code): sku for sku in sku_rows}
        for product_code, sku_code in wanted_skus:
            product = products.get(product_code)
            if product and (product.id, sku_code) in by_product:
                sku_map[(product_code, sku_code)] = by_product[(product.id, sku_code)]

    kept: list[tuple[int, Any]] = []
    for index, row in prepared:
        code = row.product_code.strip()
        if code not in products:
            results.append({"index": index, "code": code, "outcome": "error",
                            "error": f"unknown product_code {code} — import products first, never invent them"})
            continue
        sku_code = (row.sku_code or "").strip()
        if sku_code and (code, sku_code) not in sku_map:
            results.append({"index": index, "code": code, "outcome": "error",
                            "error": f"unknown sku_code {sku_code} for product {code}"})
            continue
        kept.append((index, row))
    prepared = kept

    if on_error == "abort" and any(r["outcome"] == "error" for r in results):
        return _payload(results, dry_run=dry_run, applied=False, total=len(rows))

    for index, row in prepared:
        code = row.product_code.strip()
        product = products[code]
        sku = sku_map.get((code, (row.sku_code or "").strip()))
        facility, lot_id = row.facility.strip(), row.lot_id.strip()
        item = _find_item(db, tenant_id, product.id, sku.id if sku else None, facility, lot_id)

        if item is None:
            item = InventoryItem(
                tenant_id=tenant_id,
                product_id=product.id,
                sku_id=sku.id if sku else None,
                facility=facility,
                lot_id=lot_id,
                bin_number=row.bin_number,
                expire_date=row.expire_date,
                unit_cost=row.unit_cost,
            )
            db.add(item)
            db.flush()
            post_inventory_detail(
                db, item=item,
                quantity_on_hand_diff=row.quantity,
                reason="import_initial",
                description=row.description or f"批量导入建账：数量 {row.quantity}",
                unit_cost=row.unit_cost,
                created_by=created_by,
            )
            results.append({"index": index, "code": code, "outcome": "created", "id": item.id})
            continue

        changed = []
        for field in ("bin_number", "expire_date", "unit_cost"):
            value = getattr(row, field)
            if value is not None and not _same_value(getattr(item, field), value):
                setattr(item, field, value)
                changed.append(field)
        if not _same_value(item.quantity_on_hand, row.quantity):
            system = float(item.quantity_on_hand)
            diff = round(float(row.quantity) - system, 2)
            note = f"导入覆盖：系统数量 {system:g} → 导入数量 {row.quantity:g}（差异 {diff:+g}）"
            if row.description:
                note = f"{note} {row.description}"
            post_inventory_detail(
                db, item=item,
                quantity_on_hand_diff=diff,
                reason="import_override",
                description=note,
                unit_cost=row.unit_cost,
                created_by=created_by,
            )
            changed.append("quantity_on_hand")
        if changed:
            db.flush()
        results.append({
            "index": index,
            "code": code,
            "outcome": "updated" if changed else "unchanged",
            "id": item.id,
            "changed": changed,
        })

    return _payload(results, dry_run=dry_run, applied=not dry_run, total=len(rows))
