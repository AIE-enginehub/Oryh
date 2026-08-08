"""Purchase orders — the commitment to a vendor, split from the sales side.

What must hold: the vendor is required (a PO without a counterparty is not a
document), one capability (`purchase_order.manage`) drives filing AND
advancement, receiving records facts (received_quantity + inventory ledger)
without moving status, and the 按单采购 chain is visible from both ends —
the PO line names its request line, the request detail names its PO lines.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.models import ApiKey, Tenant, hash_api_key

from conftest import make_client

TEST_TENANT = "77777777-7777-7777-7777-777777777777"
TEST_API_KEY = "po-test-key"
HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with make_client(
        [
            Tenant(id=TEST_TENANT, name="PO Co"),
            ApiKey(tenant_id=TEST_TENANT, key_hash=hash_api_key(TEST_API_KEY), label="primary"),
        ]
    ) as test_client:
        yield test_client


def create_employee(client: TestClient, **overrides) -> str:
    payload = {"name": "采购员小赵"}
    payload.update(overrides)
    response = client.post("/api/v1/employees", json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def create_vendor(client: TestClient, **overrides) -> dict:
    payload = {"name": "戴尔（中国）有限公司", "vendor_code": "V-DELL"}
    payload.update(overrides)
    response = client.post("/api/v1/vendors", json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_product(client: TestClient, **overrides) -> dict:
    payload = {"name": "27寸显示器", "product_code": "PRD-MON", "unit": "台", "list_price": 3199.0}
    payload.update(overrides)
    response = client.post("/api/v1/products", json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_po(client: TestClient, vendor_id: str, employee_id: str, **overrides) -> dict:
    payload = {"vendor_id": vendor_id, "employee_id": employee_id, "title": "显示器采购"}
    payload.update(overrides)
    response = client.post("/api/v1/purchase-orders", json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def add_po_item(client: TestClient, po_id: str, **overrides) -> dict:
    payload = {"po_id": po_id, "quantity": 10}
    payload.update(overrides)
    response = client.post("/api/v1/purchase-order-items", json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_po_lifecycle_numbering_and_machine(client: TestClient) -> None:
    vendor = create_vendor(client)
    employee_id = create_employee(client)

    po = create_po(client, vendor["id"], employee_id)
    assert po["po_number"].startswith("PO-")
    assert po["status"] == "draft"
    # snapshot defaults from the vendor when not provided
    assert po["vendor_name_snapshot"] == "戴尔（中国）有限公司"

    # BYO number for migrated/self-numbered tenants, and the number is unique
    byo = create_po(client, vendor["id"], employee_id, po_number="CG-2019-001")
    assert byo["po_number"] == "CG-2019-001"
    dup = client.post(
        "/api/v1/purchase-orders",
        json={"vendor_id": vendor["id"], "employee_id": employee_id, "po_number": "CG-2019-001"},
        headers=HEADERS,
    )
    assert dup.status_code == 409

    # a status outside the tenant's machine is rejected at create
    weird = client.post(
        "/api/v1/purchase-orders",
        json={"vendor_id": vendor["id"], "employee_id": employee_id, "status": "shipped"},
        headers=HEADERS,
    )
    assert weird.status_code == 422

    # machine transitions: draft → submitted → confirmed is legal…
    for target in ("submitted", "confirmed"):
        moved = client.patch(
            f"/api/v1/purchase-orders/{po['id']}", json={"status": target}, headers=HEADERS
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["data"]["status"] == target
    # …while draft → received is not
    jump = client.patch(
        f"/api/v1/purchase-orders/{byo['id']}", json={"status": "received"}, headers=HEADERS
    )
    assert jump.status_code == 409

    # vendor must exist
    ghost = client.post(
        "/api/v1/purchase-orders",
        json={"vendor_id": "00000000-0000-0000-0000-000000000009", "employee_id": employee_id},
        headers=HEADERS,
    )
    assert ghost.status_code == 404

    listed = client.get("/api/v1/purchase-orders?keyword=戴尔", headers=HEADERS).json()["data"]
    assert {row["id"] for row in listed} == {po["id"], byo["id"]}


def test_po_items_lock_once_the_order_leaves_draft(client: TestClient) -> None:
    vendor = create_vendor(client)
    employee_id = create_employee(client)
    product = create_product(client)
    po = create_po(client, vendor["id"], employee_id)

    item = add_po_item(client, po["id"], product_id=product["id"], unit_price=2800.0, line_no=1)
    # product context is normalized from the catalog
    assert item["product_name_snapshot"] == "27寸显示器"
    assert item["unit"] == "台"

    client.patch(f"/api/v1/purchase-orders/{po['id']}", json={"status": "submitted"}, headers=HEADERS)
    locked = client.post(
        "/api/v1/purchase-order-items",
        json={"po_id": po["id"], "quantity": 1, "product_name_snapshot": "加购"},
        headers=HEADERS,
    )
    assert locked.status_code == 409
    locked_edit = client.patch(
        f"/api/v1/purchase-order-items/{item['id']}", json={"quantity": 99}, headers=HEADERS
    )
    assert locked_edit.status_code == 409


def test_procure_to_order_chain_is_visible_from_both_ends(client: TestClient) -> None:
    """按单采购: the PO line pins the approved request line it fulfils, and
    both details surface the chain."""
    vendor = create_vendor(client)
    employee_id = create_employee(client)
    product = create_product(client)

    request = client.post(
        "/api/v1/purchase-requests",
        json={"employee_id": employee_id, "title": "客户A专项采购", "request_date": "2026-07-20"},
        headers=HEADERS,
    ).json()["data"]
    request_line = client.post(
        "/api/v1/purchase-request-items",
        json={"request_id": request["id"], "product_id": product["id"], "quantity": 5},
        headers=HEADERS,
    ).json()["data"]

    po = create_po(client, vendor["id"], employee_id)
    po_line = add_po_item(
        client, po["id"],
        product_id=product["id"], quantity=5, unit_price=2750.0,
        purchase_request_item_id=request_line["id"],
    )

    po_detail = client.get(f"/api/v1/purchase-orders/{po['id']}/detail", headers=HEADERS).json()["data"]
    [line] = po_detail["items"]
    assert line["purchase_request"]["purchase_request_item_id"] == request_line["id"]
    assert line["purchase_request"]["request_id"] == request["id"]

    request_detail = client.get(
        f"/api/v1/purchase-requests/{request['id']}/detail", headers=HEADERS
    ).json()["data"]
    [req_line] = request_detail["items"]
    [linked] = req_line["purchase_order_items"]
    assert linked["po_id"] == po["id"]
    assert linked["po_number"] == po["po_number"]
    assert linked["quantity"] == 5.0

    # filter endpoint answers "which PO lines order this request line"
    filtered = client.get(
        f"/api/v1/purchase-order-items?purchase_request_item_id={request_line['id']}", headers=HEADERS
    ).json()["data"]
    assert [row["id"] for row in filtered] == [po_line["id"]]

    # the link can be detached while the PO is editable
    detached = client.patch(
        f"/api/v1/purchase-order-items/{po_line['id']}",
        json={"purchase_request_item_id": None},
        headers=HEADERS,
    )
    assert detached.status_code == 200
    assert detached.json()["data"].get("purchase_request_item_id") is None


def test_po_adjustments_use_the_shared_vocabulary_and_shift_the_total(client: TestClient) -> None:
    vendor = create_vendor(client)
    employee_id = create_employee(client)
    po = create_po(client, vendor["id"], employee_id)
    item = add_po_item(client, po["id"], product_name_snapshot="运费杂项", quantity=10, unit_price=100.0)

    unknown = client.post(
        "/api/v1/purchase-order-adjustments",
        json={"po_id": po["id"], "adjustment_type": "mystery", "amount": -50},
        headers=HEADERS,
    )
    assert unknown.status_code == 422
    assert "sales_adjustment_type" in unknown.json()["detail"]

    discount = client.post(
        "/api/v1/purchase-order-adjustments",
        json={"po_id": po["id"], "adjustment_type": "discount", "amount": -100.0, "description": "年框返点"},
        headers=HEADERS,
    )
    assert discount.status_code == 201, discount.text
    freight = client.post(
        "/api/v1/purchase-order-adjustments",
        json={"po_id": po["id"], "po_item_id": item["id"], "adjustment_type": "shipping", "amount": 80.0},
        headers=HEADERS,
    )
    assert freight.status_code == 201, freight.text

    detail = client.get(f"/api/v1/purchase-orders/{po['id']}/detail", headers=HEADERS).json()["data"]
    assert detail["computed_total"] == 1000.0
    assert detail["adjustments_total"] == -20.0
    assert detail["adjusted_total"] == 980.0
    assert {a["adjustment_type"] for a in detail["adjustments"]} == {"discount", "shipping"}


def test_receiving_records_facts_and_lands_in_the_inventory_ledger(client: TestClient) -> None:
    vendor = create_vendor(client)
    employee_id = create_employee(client)
    product = create_product(client)
    po = create_po(client, vendor["id"], employee_id)
    stocked = add_po_item(client, po["id"], product_id=product["id"], quantity=10, unit_price=2800.0)
    direct = add_po_item(client, po["id"], product_name_snapshot="定制支架（直发客户）", quantity=3)

    received = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={"lines": [
            {"po_item_id": stocked["id"], "quantity": 6, "facility": "上海仓"},
            {"po_item_id": direct["id"], "quantity": 3},
        ]},
        headers=HEADERS,
    )
    assert received.status_code == 200, received.text
    lines = {row["po_item_id"]: row for row in received.json()["data"]["lines"]}
    assert lines[stocked["id"]]["received_quantity"] == 6.0
    assert lines[stocked["id"]]["inventory_item_id"] is not None
    # the 直发 line accumulates received_quantity but never touches stock
    assert lines[direct["id"]]["received_quantity"] == 3.0
    assert lines[direct["id"]].get("inventory_item_id") is None

    position_id = lines[stocked["id"]]["inventory_item_id"]
    position = client.get(f"/api/v1/inventory-items/{position_id}", headers=HEADERS).json()["data"]
    assert position["facility"] == "上海仓"
    assert position["quantity_on_hand"] == 6.0

    ledger = client.get(
        f"/api/v1/inventory-item-details?inventory_item_id={position_id}", headers=HEADERS
    ).json()["data"]
    [entry] = ledger
    assert entry["reason"] == "received"
    assert entry["entity_type"] == "purchase_order_item"
    assert entry["entity_id"] == stocked["id"]
    assert entry["quantity_on_hand_diff"] == 6.0

    # a second receipt accumulates — and over-receiving is recorded as stated
    again = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={"lines": [{"po_item_id": stocked["id"], "quantity": 5, "facility": "上海仓"}]},
        headers=HEADERS,
    )
    assert again.status_code == 200
    assert again.json()["data"]["lines"][0]["received_quantity"] == 11.0
    assert again.json()["data"]["lines"][0]["inventory_item_id"] == position_id

    detail = client.get(f"/api/v1/purchase-orders/{po['id']}/detail", headers=HEADERS).json()["data"]
    assert detail["ordered_quantity"] == 13.0
    assert detail["received_quantity"] == 14.0

    # a free-text line cannot land in inventory — there is no product to stock
    grounded = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={"lines": [{"po_item_id": direct["id"], "quantity": 1, "facility": "上海仓"}]},
        headers=HEADERS,
    )
    assert grounded.status_code == 422

    # a line from another PO is refused
    other_po = create_po(client, vendor["id"], employee_id)
    stray = client.post(
        f"/api/v1/purchase-orders/{other_po['id']}/receive",
        json={"lines": [{"po_item_id": stocked["id"], "quantity": 1}]},
        headers=HEADERS,
    )
    assert stray.status_code == 400


def test_receiving_updates_last_price_only_on_an_existing_supplier_link(client: TestClient) -> None:
    vendor = create_vendor(client)
    employee_id = create_employee(client)
    linked = create_product(client)
    unlinked = create_product(client, name="键盘", product_code="PRD-KBD")
    link = client.post(
        "/api/v1/supplier-products",
        json={"product_id": linked["id"], "vendor_id": vendor["id"], "last_price": 2900.0},
        headers=HEADERS,
    )
    assert link.status_code == 201, link.text

    po = create_po(client, vendor["id"], employee_id)
    linked_line = add_po_item(client, po["id"], product_id=linked["id"], quantity=2, unit_price=2750.0)
    unlinked_line = add_po_item(client, po["id"], product_id=unlinked["id"], quantity=2, unit_price=99.0)

    receipt = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={"lines": [
            {"po_item_id": linked_line["id"], "quantity": 2},
            {"po_item_id": unlinked_line["id"], "quantity": 2},
        ]},
        headers=HEADERS,
    )
    assert receipt.status_code == 200, receipt.text

    links = client.get(
        f"/api/v1/supplier-products?vendor_id={vendor['id']}", headers=HEADERS
    ).json()["data"]
    by_product = {row["product_id"]: row for row in links}
    # the existing link learned the freshest price…
    assert by_product[linked["id"]]["last_price"] == 2750.0
    # …and no link was invented for the other product
    assert unlinked["id"] not in by_product


def test_purchase_order_manage_is_not_a_member_default(client: TestClient) -> None:
    from app.core.permissions import DEFAULT_ROLE_PERMISSIONS

    assert "purchase_order.manage" not in DEFAULT_ROLE_PERMISSIONS["member"]

    vendor = create_vendor(client)
    employee_id = create_employee(client)
    invited = client.post(
        "/api/v1/auth/invitations",
        json={"email": "buyer@po.example", "role": "member", "employee_id": employee_id},
        headers=HEADERS,
    )
    assert invited.status_code == 201, invited.text
    from app.services.emails import outbox

    token = next(
        line.rsplit("token=", 1)[1].strip()
        for line in outbox.messages[-1].body.splitlines()
        if "token=" in line
    )
    accepted = client.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "password": "buyer-pw1"}
    )
    assert accepted.status_code in (200, 201), accepted.text
    member_key = client.post(
        "/api/v1/tenant/api-keys",
        json={"label": "member-agent", "user_id": invited.json()["data"]["id"]},
        headers=HEADERS,
    ).json()["data"]["plain_text_api_key"]

    denied = client.post(
        "/api/v1/purchase-orders",
        json={"vendor_id": vendor["id"], "employee_id": employee_id},
        headers={"X-API-Key": member_key},
    )
    assert denied.status_code == 403
    assert "purchase_order.manage" in denied.json()["detail"]

    denied_bulk = client.post(
        "/api/v1/purchase-orders/bulk",
        json={"rows": [{"po_number": "CG-1", "vendor_code": "V-DELL", "employee_id": employee_id}]},
        headers={"X-API-Key": member_key},
    )
    assert denied_bulk.status_code == 403


def po_row(**overrides) -> dict:
    row = {
        "po_number": "CG-2019-042",
        "vendor_code": "V-DELL",
        "employee_code": "E-001",
        "title": "2019年显示器框架采购",
        "order_date": "2019-03-15",
        "status": "closed",
        "total_amount": 28000.0,
        "items": [
            {"line_no": 1, "product_code": "PRD-MON", "quantity": 10, "unit_price": 2800.0, "amount": 28000.0},
        ],
        "adjustments": [
            {"adjustment_type": "freight", "amount": 200.0, "description": "到付运费"},
        ],
    }
    row.update(overrides)
    return row


def test_bulk_po_import_upserts_by_number_and_requires_the_vendor(client: TestClient) -> None:
    create_vendor(client)
    create_employee(client, employee_code="E-001")
    create_product(client)

    # dry run previews without writing
    preview = client.post(
        "/api/v1/purchase-orders/bulk",
        json={"rows": [po_row()], "dry_run": True},
        headers=HEADERS,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["data"]["summary"] == {
        "total": 1, "created": 1, "updated": 0, "unchanged": 0, "failed": 0,
    }
    assert client.get("/api/v1/purchase-orders", headers=HEADERS).json()["data"] == []

    # an unmatched vendor is ALWAYS an error — even in snapshot mode — while
    # the rest of the file still lands; historical states import as-is
    applied = client.post(
        "/api/v1/purchase-orders/bulk",
        json={
            "rows": [
                po_row(),
                po_row(po_number="CG-2019-043", vendor_code="V-GONE"),
                po_row(po_number="CG-2019-044", status="shipped"),
            ],
            "on_missing_reference": "snapshot",
        },
        headers=HEADERS,
    )
    assert applied.status_code == 200, applied.text
    rows = applied.json()["data"]["results"]
    by_number = {row["number"]: row for row in rows}
    assert by_number["CG-2019-042"]["outcome"] == "created"
    assert by_number["CG-2019-043"]["outcome"] == "error"
    assert "vendor_code V-GONE" in by_number["CG-2019-043"]["error"]
    assert by_number["CG-2019-044"]["outcome"] == "error"
    assert "shipped" in by_number["CG-2019-044"]["error"]

    listed = client.get("/api/v1/purchase-orders", headers=HEADERS).json()["data"]
    [imported] = listed
    assert imported["po_number"] == "CG-2019-042"
    assert imported["status"] == "closed"
    assert imported["vendor_name_snapshot"] == "戴尔（中国）有限公司"

    # re-running the same file is a resume: unchanged, not duplicated
    rerun = client.post(
        "/api/v1/purchase-orders/bulk", json={"rows": [po_row()]}, headers=HEADERS
    )
    assert rerun.json()["data"]["results"][0]["outcome"] == "unchanged"

    # a corrected re-import updates in place, children replaced wholesale
    fixed = po_row()
    fixed["items"][0]["quantity"] = 12
    corrected = client.post(
        "/api/v1/purchase-orders/bulk", json={"rows": [fixed]}, headers=HEADERS
    )
    assert corrected.json()["data"]["results"][0]["outcome"] == "updated"
    detail = client.get(
        f"/api/v1/purchase-orders/{imported['id']}/detail", headers=HEADERS
    ).json()["data"]
    [line] = detail["items"]
    assert line["quantity"] == 12.0
    [adjustment] = detail["adjustments"]
    assert adjustment["adjustment_type"] == "freight"


def test_bulk_po_import_keeps_the_printed_vendor_name(client: TestClient) -> None:
    """The snapshot is what the historical document PRINTED. A matched
    vendor_code must not overwrite it with the master-data name of today."""
    create_vendor(client)  # 现名：戴尔（中国）有限公司
    create_employee(client, employee_code="E-001")
    create_product(client)

    applied = client.post(
        "/api/v1/purchase-orders/bulk",
        json={"rows": [po_row(vendor_name_snapshot="戴尔计算机（中国）有限公司")]},
        headers=HEADERS,
    )
    assert applied.status_code == 200, applied.text
    [imported] = client.get("/api/v1/purchase-orders", headers=HEADERS).json()["data"]
    assert imported["vendor_name_snapshot"] == "戴尔计算机（中国）有限公司"
    # and the row still resolved the vendor id
    vendor_id = client.get("/api/v1/vendors", headers=HEADERS).json()["data"][0]["id"]
    assert imported["vendor_id"] == vendor_id


def test_a_po_may_be_placed_with_its_lines_in_one_call(client: TestClient) -> None:
    """Every other document family raises its children with the parent; the PO
    was the odd one out. One call, one transaction."""
    vendor = create_vendor(client)
    employee_id = create_employee(client)
    product = create_product(client)

    po = create_po(
        client, vendor["id"], employee_id,
        items=[
            {"product_id": product["id"], "quantity": 6, "unit_price": 3199.0, "line_no": 1},
            {"product_name_snapshot": "线材", "quantity": 20, "line_no": 2},
        ],
    )
    # the response reads back what landed
    assert [item["line_no"] for item in po["items"]] == [1, 2]
    assert po["items"][0]["product_id"] == product["id"]

    detail = client.get(f"/api/v1/purchase-orders/{po['id']}/detail", headers=HEADERS).json()["data"]
    assert len(detail["items"]) == 2
    assert detail["ordered_quantity"] == 26.0


def test_a_bad_inline_po_line_rolls_the_whole_order_back(client: TestClient) -> None:
    vendor = create_vendor(client)
    employee_id = create_employee(client)
    before = len(client.get("/api/v1/purchase-orders", headers=HEADERS).json()["data"])

    response = client.post(
        "/api/v1/purchase-orders",
        json={
            "vendor_id": vendor["id"],
            "employee_id": employee_id,
            "title": "半成品",
            "items": [
                {"product_name_snapshot": "显示器", "quantity": 3},
                # neither a catalog product nor a free-text name
                {"quantity": 1},
            ],
        },
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert len(client.get("/api/v1/purchase-orders", headers=HEADERS).json()["data"]) == before
