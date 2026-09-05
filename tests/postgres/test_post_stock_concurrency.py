"""One shipment, two postings at once. Stock must leave the ledger once.

Review R02 (2026-09-05): `post_shipment_stock` judged "already posted" from
`stock_posted_at` read without a lock, so two requests that both read the
unposted shipment both posted — two `issued` rows, stock 10 → 4 for a
3-unit line. The posting now locks the shipment row before reading the
stamp, and the ledger carries a unique (source line, effect) index as the
last defence. Deterministic shape: a barrier after the first read; realistic
shape: N callers, no barrier.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.deps import Actor
from app.models import InventoryItem, InventoryItemDetail, Product, Shipment, ShipmentItem, Tenant
from tests.postgres.conftest import needs_postgres

pytestmark = [needs_postgres, pytest.mark.usefixtures("clean_tables")]


def make_actor(tenant_id: str) -> Actor:
    return Actor(tenant_id=tenant_id, kind="service", role="service", credential_id=uuid.uuid4().hex)


@pytest.fixture()
def parcel(pg_sessionmaker):
    with pg_sessionmaker() as db:
        tenant = Tenant(name="Dock PG", email_domain="dock-pg.example", slug="dock-pg")
        db.add(tenant)
        db.flush()
        product = Product(tenant_id=tenant.id, name="Cup", product_code="CUP-1")
        db.add(product)
        db.flush()
        position = InventoryItem(tenant_id=tenant.id, product_id=product.id, facility="main",
                                 quantity_on_hand=10, available_to_promise=10)
        db.add(position)
        db.flush()
        shipment = Shipment(tenant_id=tenant.id, shipment_no="SH-PG-1", direction="outbound", status="shipped")
        db.add(shipment)
        db.flush()
        db.add(ShipmentItem(tenant_id=tenant.id, shipment_id=shipment.id, product_id=product.id,
                            quantity=3, inventory_item_id=position.id, line_no=1))
        db.commit()
        return {"tenant_id": tenant.id, "shipment_id": shipment.id, "position_id": position.id}


def post_in_thread(pg_sessionmaker, parcel, outcomes, *, barrier=None):
    from app.api import shipments as shipments_api

    original = shipments_api._live_lines

    def gated(db, document, item_model, parent_column):
        if barrier is not None:
            try:
                barrier.wait(timeout=3)  # the lock makes the second caller late on purpose
            except threading.BrokenBarrierError:
                pass
        return original(db, document, item_model, parent_column)

    try:
        with pg_sessionmaker() as db:
            shipments_api._live_lines = gated
            try:
                shipments_api.post_shipment_stock(parcel["shipment_id"], make_actor(parcel["tenant_id"]), db)
            finally:
                shipments_api._live_lines = original
        outcomes.append("posted")
    except HTTPException as exc:
        outcomes.append(exc.status_code)
    except Exception as exc:  # noqa: BLE001
        outcomes.append(repr(exc))


def _stock(pg_sessionmaker, position_id: str) -> tuple[float, int]:
    with pg_sessionmaker() as db:
        qoh = db.scalar(select(InventoryItem.quantity_on_hand).where(InventoryItem.id == position_id))
        rows = db.scalar(select(func.count()).select_from(InventoryItemDetail).where(
            InventoryItemDetail.inventory_item_id == position_id, InventoryItemDetail.reason == "issued"))
        return float(qoh), int(rows)


def test_two_postings_of_one_shipment_move_stock_once(pg_sessionmaker, parcel) -> None:
    barrier = threading.Barrier(2)
    outcomes: list = []
    threads = [threading.Thread(target=post_in_thread, args=(pg_sessionmaker, parcel, outcomes), kwargs={"barrier": barrier})
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(map(str, outcomes)) == ["409", "posted"], outcomes
    assert _stock(pg_sessionmaker, parcel["position_id"]) == (7.0, 1), "one issued row, stock 10 → 7"


def test_many_postings_of_one_shipment_move_stock_once(pg_sessionmaker, parcel) -> None:
    outcomes: list = []
    threads = [threading.Thread(target=post_in_thread, args=(pg_sessionmaker, parcel, outcomes)) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert outcomes.count("posted") == 1 and outcomes.count(409) == 4, outcomes
    assert _stock(pg_sessionmaker, parcel["position_id"]) == (7.0, 1)
