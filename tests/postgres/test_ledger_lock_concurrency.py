"""Two holds, two receipts, at once. The ledger's bounds must hold.

Review N02 (2026-09-12) reproduced both on PostgreSQL: two `reserve` calls
that each read ATP=10 and each held 7 left -4, because the position was
read before it was locked; two purchase receipts of 7 each kept both ledger
rows and a `received_quantity` of 7, because the PO line's running total
moved by a Python read-modify-write. The hold now takes the position's row
lock before the bound is read, and the receipt moves the line's total with
a relative SQL update.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.deps import Actor
from app.models import (
    Employee, InventoryItem, InventoryItemDetail, Product, PurchaseOrder, PurchaseOrderItem,
    SalesOrder, SalesOrderItem, Tenant, Vendor,
)
from app.schemas import ReceivePurchaseOrderRequest, ReserveStockRequest
from tests.postgres.conftest import needs_postgres

pytestmark = [needs_postgres, pytest.mark.usefixtures("clean_tables")]


def make_actor(tenant_id: str) -> Actor:
    return Actor(tenant_id=tenant_id, kind="service", role="service", credential_id=uuid.uuid4().hex)


@pytest.fixture()
def stockroom(pg_sessionmaker):
    with pg_sessionmaker() as db:
        tenant = Tenant(name="Lock PG", email_domain="lock-pg.example", slug="lock-pg")
        db.add(tenant)
        db.flush()
        employee = Employee(tenant_id=tenant.id, name="keeper")
        vendor = Vendor(tenant_id=tenant.id, name="supplier")
        product = Product(tenant_id=tenant.id, name="Cup", product_code="CUP-1")
        db.add_all([employee, vendor, product])
        db.flush()
        position = InventoryItem(tenant_id=tenant.id, product_id=product.id, facility="main",
                                 quantity_on_hand=10, available_to_promise=10)
        db.add(position)
        db.flush()
        order = SalesOrder(tenant_id=tenant.id, order_no="SO-PG-1", employee_id=employee.id, title="hold", status="confirmed")
        db.add(order)
        db.flush()
        db.add(SalesOrderItem(tenant_id=tenant.id, order_id=order.id, product_id=product.id, quantity=7, line_no=1))
        po = PurchaseOrder(tenant_id=tenant.id, po_number="PO-PG-1", vendor_id=vendor.id, employee_id=employee.id,
                           title="restock", status="ordered")
        db.add(po)
        db.flush()
        po_line = PurchaseOrderItem(tenant_id=tenant.id, po_id=po.id, product_id=product.id, quantity=14, line_no=1)
        db.add(po_line)
        db.commit()
        return {"tenant_id": tenant.id, "position_id": position.id, "order_id": order.id,
                "po_id": po.id, "po_line_id": po_line.id}


def _atp(pg_sessionmaker, position_id: str) -> float:
    with pg_sessionmaker() as db:
        return float(db.scalar(select(InventoryItem.available_to_promise).where(InventoryItem.id == position_id)))


def test_two_holds_of_seven_on_ten_leave_one(pg_sessionmaker, stockroom) -> None:
    from app.api import master_data

    barrier = threading.Barrier(2)
    outcomes: list = []
    original = master_data._position_for_order

    def gated(db, order, inventory_item_id):
        item = original(db, order, inventory_item_id)
        try:
            barrier.wait(timeout=3)  # both callers have read the position; the lock decides
        except threading.BrokenBarrierError:
            pass
        return item

    def hold():
        try:
            with pg_sessionmaker() as db:
                master_data.reserve_stock_for_order(
                    stockroom["order_id"],
                    ReserveStockRequest(lines=[{"inventory_item_id": stockroom["position_id"], "quantity": 7}]),
                    make_actor(stockroom["tenant_id"]), db,
                )
            outcomes.append("held")
        except HTTPException as exc:
            outcomes.append(exc.status_code)
        except Exception as exc:  # noqa: BLE001
            outcomes.append(repr(exc))

    master_data._position_for_order = gated
    try:
        threads = [threading.Thread(target=hold) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
    finally:
        master_data._position_for_order = original
    assert sorted(map(str, outcomes)) == ["409", "held"], outcomes
    assert _atp(pg_sessionmaker, stockroom["position_id"]) == 3.0, "one hold of 7 on 10; never -4"


def test_two_receipts_of_seven_both_count(pg_sessionmaker, stockroom) -> None:
    from app.api import purchasing

    barrier = threading.Barrier(2)
    outcomes: list = []
    original = purchasing.require_line_on_document

    def gated(*args, **kwargs):
        item = original(*args, **kwargs)
        try:
            barrier.wait(timeout=3)
        except threading.BrokenBarrierError:
            pass
        return item

    def receive():
        try:
            with pg_sessionmaker() as db:
                purchasing.receive_purchase_order(
                    stockroom["po_id"],
                    ReceivePurchaseOrderRequest(lines=[{"po_item_id": stockroom["po_line_id"], "quantity": 7, "facility": "main"}]),
                    make_actor(stockroom["tenant_id"]), db,
                )
            outcomes.append("received")
        except Exception as exc:  # noqa: BLE001
            outcomes.append(repr(exc))

    purchasing.require_line_on_document = gated
    try:
        threads = [threading.Thread(target=receive) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
    finally:
        purchasing.require_line_on_document = original
    assert outcomes == ["received", "received"], outcomes
    with pg_sessionmaker() as db:
        received = float(db.scalar(select(PurchaseOrderItem.received_quantity).where(PurchaseOrderItem.id == stockroom["po_line_id"])))
        rows = db.scalar(select(InventoryItemDetail.id).where(InventoryItemDetail.purchase_order_id == stockroom["po_id"]).limit(1))
        on_hand = float(db.scalar(select(InventoryItem.quantity_on_hand).where(InventoryItem.id == stockroom["position_id"])))
    assert received == 14.0, "both receipts count on the line, not just the last writer's"
    assert on_hand == 24.0 and rows is not None
