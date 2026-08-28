"""Returns live in the order tables, and the kind picks the machine.

The deciding requirement: 退单跟订单一张表. A sales return is a `sales_orders`
row with order_kind='return', pointing at the order it reverses through
`original_order_id` — and one order carrying MANY returns is simply many rows
naming the same original. What the kind buys is the LIFECYCLE: an e-commerce
return runs 申请→发出→收到→验货入库→退款 (the shipped `sales_return` machine),
which is not an order's life, and the tenant renames or reshapes either
machine independently — the same one-sentence customization every builtin has.

The guards pinned here are the ones that keep money and history honest: a
return never occupies a billing account's credit (the refund is a payment
document — letting a return charge credit would count the customer's money
against them twice), a return reverses an ORDER (never another return), and
`original_order_id` never appears on an order. The number series splits
(SR- beside SO-) so a human tells them apart at a glance.
"""

from __future__ import annotations

import pytest

from conftest import make_client, provision_tenant


@pytest.fixture()
def shop():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Shop Co", email="admin@shop.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        emp = client.post("/api/v1/employees", json={"name": "店长"},
                          headers=admin).json()["data"]["id"]
        cust = client.post("/api/v1/customers", json={"name": "买家"},
                           headers=admin).json()["data"]["id"]

        def order(**extra) -> dict:
            body = {"employee_id": emp, "customer_id": cust, "title": "一单货", **extra}
            r = client.post("/api/v1/sales-orders", json=body, headers=admin)
            assert r.status_code == 201, r.text
            return r.json()["data"]

        yield {"client": client, "admin": admin, "employee": emp, "customer": cust,
               "order": order, "tenant_id": t["tenant"]["id"]}


def test_a_return_links_its_order_and_one_order_takes_many(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    original = shop["order"](status="signed")

    first = shop["order"](order_kind="return", original_order_id=original["id"],
                          title="第一次退两件")
    second = shop["order"](order_kind="return", original_order_id=original["id"],
                           title="第二次又退一件")
    assert first["order_kind"] == "return" and second["order_kind"] == "return"
    assert first["original_order_id"] == original["id"]

    returns = client.get("/api/v1/sales-orders",
                         params={"original_order_id": original["id"]},
                         headers=admin).json()["data"]
    assert {r["id"] for r in returns} == {first["id"], second["id"]}, \
        "one order, many returns — the linkage is the query"

    only_returns = client.get("/api/v1/sales-orders", params={"order_kind": "return"},
                              headers=admin).json()["data"]
    assert original["id"] not in {r["id"] for r in only_returns}


def test_the_number_series_splits_so_a_human_tells_them_apart(shop) -> None:
    order = shop["order"]()
    ret = shop["order"](order_kind="return", original_order_id=order["id"])
    assert order["order_no"].startswith("SO-"), order["order_no"]
    assert ret["order_no"].startswith("SR-"), ret["order_no"]


def test_a_return_reverses_an_order_never_another_return(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    original = shop["order"]()
    ret = shop["order"](order_kind="return", original_order_id=original["id"])

    chained = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": shop["employee"], "customer_id": shop["customer"],
        "title": "退退单?", "order_kind": "return", "original_order_id": ret["id"]})
    assert chained.status_code == 422, chained.text
    assert "itself a" in chained.json()["detail"]

    on_an_order = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": shop["employee"], "customer_id": shop["customer"],
        "title": "订单带原单?", "original_order_id": original["id"]})
    assert on_an_order.status_code == 422, "original_order_id belongs on returns only"

    ghost = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": shop["employee"], "customer_id": shop["customer"],
        "title": "查无此单", "order_kind": "return",
        "original_order_id": "00000000-0000-0000-0000-000000000000"})
    assert ghost.status_code == 404


def test_an_orphan_return_is_recordable_and_matched_later(shop) -> None:
    """Reality outruns paperwork: the parcel is on the shelf before anyone
    knows which order sent it. Record now, link later — the same doctrine the
    warehouse ledger keeps."""
    client, admin = shop["client"], shop["admin"]
    orphan = shop["order"](order_kind="return", title="不知道哪单的退货")
    assert orphan["original_order_id"] is None

    original = shop["order"]()
    matched = client.patch(f"/api/v1/sales-orders/{orphan['id']}", headers=admin,
                           json={"original_order_id": original["id"]})
    assert matched.status_code == 200, matched.text
    assert matched.json()["data"]["original_order_id"] == original["id"]

    not_a_return = client.patch(f"/api/v1/sales-orders/{original['id']}", headers=admin,
                                json={"original_order_id": orphan["id"]})
    assert not_a_return.status_code == 422


def test_the_kind_picks_the_machine(shop) -> None:
    """An order and a return in one table, two lifecycles: the return walks
    申请→发出→收到→验货入库→退款 and the ORDER machine's states are not legal
    on it — without this, one table would have meant one smeared vocabulary,
    which is the mess the kind split exists to prevent."""
    client, admin = shop["client"], shop["admin"]
    ret = shop["order"](order_kind="return", title="走完整退货流程")

    for state in ("submitted", "approved", "in_transit", "received", "inspected", "refunded"):
        moved = client.patch(f"/api/v1/sales-orders/{ret['id']}", headers=admin,
                             json={"status": state})
        assert moved.status_code == 200, f"{state}: {moved.text}"

    done = client.patch(f"/api/v1/sales-orders/{ret['id']}", headers=admin,
                        json={"status": "approved"})
    assert done.status_code == 409, "refunded is terminal in the return machine"

    order = shop["order"]()
    not_an_order_state = client.patch(f"/api/v1/sales-orders/{order['id']}", headers=admin,
                                      json={"status": "in_transit"})
    assert not_an_order_state.status_code == 409, \
        "the order machine knows nothing of the return's states"
    crossed = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": shop["employee"], "customer_id": shop["customer"],
        "title": "订单不能生在退货状态里", "status": "in_transit"})
    assert crossed.status_code == 422, crossed.text

    born_mid_flow = shop["order"](order_kind="return", status="received",
                                  title="平台同步来的既成事实")
    assert born_mid_flow["status"] == "received", \
        "e-commerce returns arrive as facts — create accepts any state of the RETURN machine"


def test_the_status_vocabulary_follows_the_kind_filter(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    scoped = client.get("/api/v1/sales-orders",
                        params={"order_kind": "order", "status": "in_transit"},
                        headers=admin)
    assert scoped.status_code == 422, \
        "a kind-scoped list is checked against that kind's machine"

    unscoped = client.get("/api/v1/sales-orders", params={"status": "in_transit"},
                          headers=admin)
    assert unscoped.status_code == 200, \
        "an unscoped list spans both machines — the union is the vocabulary"

    nonsense = client.get("/api/v1/sales-orders", params={"status": "levitating"},
                          headers=admin)
    assert nonsense.status_code == 422


def test_a_return_never_occupies_credit(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    account = client.post("/api/v1/billing-accounts", headers=admin, json={
        "name": "买家往来户", "unit_type": "currency", "unit": "CNY",
        "customer_id": shop["customer"], "credit_limit": 1000.0}).json()["data"]["id"]
    refused = client.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": shop["employee"], "customer_id": shop["customer"],
        "title": "退货还想挂账", "order_kind": "return",
        "billing_account_id": account, "total_amount": 100.0})
    assert refused.status_code == 422, refused.text
    assert "payment document" in refused.json()["detail"], \
        "the refusal must say where the refund actually lives"


def test_purchase_returns_mirror_the_shape(shop) -> None:
    client, admin = shop["client"], shop["admin"]
    vendor = client.post("/api/v1/vendors", json={"name": "供应商"},
                         headers=admin).json()["data"]["id"]
    po = client.post("/api/v1/purchase-orders", headers=admin, json={
        "vendor_id": vendor, "employee_id": shop["employee"], "title": "进一批货"})
    assert po.status_code == 201, po.text
    po = po.json()["data"]
    assert po["order_no" if "order_no" in po else "po_number"].startswith("PO-")

    ret = client.post("/api/v1/purchase-orders", headers=admin, json={
        "vendor_id": vendor, "employee_id": shop["employee"], "title": "退给供应商",
        "order_kind": "return", "original_order_id": po["id"]})
    assert ret.status_code == 201, ret.text
    ret = ret.json()["data"]
    assert ret["po_number"].startswith("PR-")

    for state in ("submitted", "approved", "shipped", "refunded"):
        moved = client.patch(f"/api/v1/purchase-orders/{ret['id']}", headers=admin,
                             json={"status": state})
        assert moved.status_code == 200, f"{state}: {moved.text}"

    by_original = client.get("/api/v1/purchase-orders",
                             params={"original_order_id": po["id"]},
                             headers=admin).json()["data"]
    assert [r["id"] for r in by_original] == [ret["id"]]


def test_the_tenant_renames_the_return_machine_in_a_sentence(shop) -> None:
    """The one-sentence customization holds for the new machine: rename the
    return's `submitted` to the tenant's own word, and /submit on a RETURN
    lands there — proof that the submit path reads the return machine, not
    the order's, which also has a state named `submitted` and would silently
    absorb the write if the kind were ignored."""
    client, admin = shop["client"], shop["admin"]
    definition = client.get(
        "/api/v1/object-type-definitions",
        params={"entity_kind": "builtin", "object_type": "sales_return"},
        headers=admin).json()["data"][0]
    machine = definition["state_machine"]
    machine["states"] = ["requested" if s == "submitted" else s for s in machine["states"]]
    machine["transitions"] = {
        ("requested" if k == "submitted" else k): [
            "requested" if t == "submitted" else t for t in targets
        ]
        for k, targets in machine["transitions"].items()
    }
    machine["roles"] = {"submitted": "requested"}
    renamed = client.patch(f"/api/v1/object-type-definitions/{definition['id']}",
                           json={"state_machine": machine}, headers=admin)
    assert renamed.status_code == 200, renamed.text

    ret = shop["order"](order_kind="return", title="用租户自己的词")
    submitted = client.post(f"/api/v1/sales-orders/{ret['id']}/submit", json={},
                            headers=admin)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["status"] == "requested", \
        "/submit must land where the RETURN machine's submitted role points"

    order = shop["order"]()
    plain = client.post(f"/api/v1/sales-orders/{order['id']}/submit", json={},
                        headers=admin)
    assert plain.json()["data"]["status"] == "submitted", \
        "the ORDER machine is untouched by the return machine's rename"


def test_the_side_doors_hold_what_the_front_door_refuses(shop) -> None:
    """Create-time guards that PATCH could have walked around: a return must
    not acquire a quotation or a billing account after the fact (credit
    occupied for money flowing the other way), an invoice must not bill a
    return (the three-way match would read it as the order billed), and
    /receive must not book phantom stock against a purchase return — on a
    return the goods LEAVE."""
    client, admin = shop["client"], shop["admin"]
    ret = shop["order"](order_kind="return")

    account = client.post("/api/v1/billing-accounts", headers=admin, json={
        "name": "买家往来户2", "unit_type": "currency", "unit": "CNY",
        "customer_id": shop["customer"], "credit_limit": 1000.0}).json()["data"]["id"]
    assert client.patch(f"/api/v1/sales-orders/{ret['id']}", headers=admin,
                        json={"billing_account_id": account}).status_code == 422, \
        "a return acquiring an account by PATCH would occupy credit after all"

    quote_on_return = client.patch(f"/api/v1/sales-orders/{ret['id']}", headers=admin,
                                   json={"source_quote_number": "QT-000001"})
    assert quote_on_return.status_code == 422

    billed = client.post("/api/v1/invoices", headers=admin, json={
        "direction": "sales", "employee_id": shop["employee"],
        "customer_id": shop["customer"], "title": "给退货开发票?",
        "total_amount": 10.0, "sales_order_id": ret["id"]})
    assert billed.status_code == 422, billed.text
    assert "refund payment" in billed.json()["detail"]

    vendor = client.post("/api/v1/vendors", json={"name": "供应商B"},
                         headers=admin).json()["data"]["id"]
    product = client.post("/api/v1/products", json={"name": "货", "product_code": "G-9"},
                          headers=admin).json()["data"]["id"]
    po_return = client.post("/api/v1/purchase-orders", headers=admin, json={
        "vendor_id": vendor, "employee_id": shop["employee"], "title": "退回去",
        "order_kind": "return",
        "items": [{"line_no": 1, "product_id": product, "quantity": 2, "unit_price": 5.0}],
    }).json()["data"]
    received = client.post(f"/api/v1/purchase-orders/{po_return['id']}/receive",
                           headers=admin,
                           json={"lines": [{"po_item_id": po_return["items"][0]["id"],
                                            "quantity": 2}]})
    assert received.status_code == 422, received.text
    assert "issued" in received.json()["detail"], \
        "the refusal must point at the movement that IS correct"

    po_account = client.patch(f"/api/v1/purchase-orders/{po_return['id']}",
                              headers=admin, json={"billing_account_id": account})
    assert po_account.status_code == 422, \
        "the purchase side holds the same PATCH door shut"


def test_the_hosted_queue_survives_renaming_one_machine(shop) -> None:
    """`/sales-orders?status=…` serves orders AND returns, so the hosted
    queue filter derives from BOTH machines. Both say `submitted` today; a
    tenant renaming the ORDER machine's word must not silently drop every
    submitted RETURN out of the hosted agent's queue — that coincidence of
    names is exactly what this pin refuses to depend on."""
    client, admin = shop["client"], shop["admin"]
    definition = client.get(
        "/api/v1/object-type-definitions",
        params={"entity_kind": "builtin", "object_type": "sales_order"},
        headers=admin).json()["data"][0]
    machine = definition["state_machine"]
    machine["states"] = ["pending" if s == "submitted" else s for s in machine["states"]]
    machine["transitions"] = {
        ("pending" if k == "submitted" else k): [
            "pending" if t == "submitted" else t for t in targets
        ]
        for k, targets in machine["transitions"].items()
    }
    machine["roles"] = {"submitted": "pending"}
    assert client.patch(f"/api/v1/object-type-definitions/{definition['id']}",
                        json={"state_machine": machine},
                        headers=admin).status_code == 200

    from app.db.session import get_db
    from app.main import app as fastapi_app
    from app.services.flow_subscriptions import derived_queue_filter

    db = next(fastapi_app.dependency_overrides[get_db]())
    try:
        derived = derived_queue_filter(db, shop["tenant_id"], "sales_order")
    finally:
        db.close()
    statuses = derived["status"] if isinstance(derived["status"], list) else [derived["status"]]
    assert "pending" in statuses, "the renamed order machine's word must be in the queue"
    assert "submitted" in statuses, \
        "the RETURN machine still says submitted — dropping it starves the queue"


def test_a_platform_return_number_links_the_return_row(shop) -> None:
    """The e-commerce loop closes on the existing link table: the Tmall
    aftersale number ties to the return row (a sales_orders row, so
    entity_type is sales_order), dedup works, and no new machinery exists."""
    client, admin = shop["client"], shop["admin"]
    original = shop["order"]()
    ret = shop["order"](order_kind="return", original_order_id=original["id"])

    link = client.post("/api/v1/external-document-links", headers=admin, json={
        "source": "tmall", "external_kind": "return", "external_no": "TMR-2026-88",
        "entity_type": "sales_order", "entity_id": ret["id"]})
    assert link.status_code == 201, link.text

    found = client.get("/api/v1/external-document-links",
                       params={"source": "tmall", "external_no": "TMR-2026-88"},
                       headers=admin).json()["data"]
    assert [r["entity_id"] for r in found] == [ret["id"]]
