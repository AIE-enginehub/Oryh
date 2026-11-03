"""Points redeemed on an order — docs/billing-accounts.md, "Redeeming points
on an order".

"500 points for ¥5 off" is two facts written in one act: a `redeemed` entry
on the customer's points account and a `points` discount on the order that
names it. Points come back only by naming the redemption, never beyond what
it spent — how many is the workspace's rule; the discount is changed only
together with its points; billing it
on the invoice moves no points and bills it at most once.
"""

from __future__ import annotations

import pathlib

import pytest
from sqlalchemy import text as sql_text

from conftest import make_client, provision_tenant


@pytest.fixture()
def shop():
    with make_client([]) as c:
        t = provision_tenant(c, company_name="Points Shop", email="owner@points-shop.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def call(method: str, path: str, body: dict | None = None, **params):
            return c.request(method, f"/api/v1/{path}", headers=admin, json=body, params=params or None)

        def ok(response, code=201):
            assert response.status_code == code, response.text
            return response.json()["data"] if response.content else None

        clerk = ok(call("POST", "employees", {"name": "Clerk"}))["id"]
        buyer = ok(call("POST", "customers", {"name": "Member"}))["id"]
        other = ok(call("POST", "customers", {"name": "Someone else"}))["id"]
        points = ok(call("POST", "billing-accounts", {"name": "Member points", "unit_type": "points",
                                                      "unit": "point", "customer_id": buyer}))
        ok(call("POST", "object-type-definitions", {"object_type": "points_award", "state_machine": {
            "initial": "approved", "states": ["approved"], "transitions": {"approved": []},
            "account_effect": {"reason": "earned", "state": "approved"}}}))
        award = ok(call("POST", "business-objects", {"object_type": "points_award", "title": "welcome",
                                                     "status": "approved",
                                                     "payload": {"lines": [{"billing_account_id": points["id"],
                                                                            "amount": 1000}]}}))
        ok(call("POST", f"business-objects/{award['id']}/post-entries", {}), 200)

        def order(status: str | None = None, customer: str | None = None) -> dict:
            body = {"employee_id": clerk, "customer_id": customer or buyer, "title": "basket",
                    "items": [{"product_name_snapshot": "tea", "quantity": 2, "unit_price": 50}]}
            if status:
                body["status"] = status
            return ok(call("POST", "sales-orders", body))

        yield dict(c=c, call=call, ok=ok, clerk=clerk, buyer=buyer, other=other, points=points, order=order)


def _balance(s) -> float:
    return s["ok"](s["call"]("GET", f"billing-accounts/{s['points']['id']}"), 200)["balance"]


def _redeem(s, order_id: str, points: float = 500, discount: float = 5, **extra):
    return s["call"]("POST", f"sales-orders/{order_id}/redeem-points",
                     {"billing_account_id": s["points"]["id"], "points": points, "discount_amount": discount, **extra})


def _audit(names: tuple[str, ...]) -> dict[str, int]:
    from app.db.session import get_db
    from app.main import app

    source = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "data_integrity_audit.py"
    text = source.read_text(encoding="utf-8")
    namespace: dict = {"__file__": str(source)}
    exec(text[: text.index("def main()")], namespace)
    checks = dict(namespace["STRUCTURAL_CHECKS"]) | dict(namespace["ADVISORY_CHECKS"])
    db = next(app.dependency_overrides[get_db]())
    try:
        return {name: db.execute(sql_text(checks[name])).scalar() for name in names}
    finally:
        db.close()


THREADED = "points discounts and points lines name their redemption"
BOUNDED = "redemptions given back beyond what they spent"
FORGOTTEN = "points spent on orders where no discount stands, not given back"


def test_redeeming_spends_the_points_and_discounts_the_order_in_one_act(shop) -> None:
    s = shop
    basket = s["order"]()
    redemption = s["ok"](_redeem(s, basket["id"]))
    assert (redemption["points"], redemption["outstanding"], redemption["balance"]) == (500.0, 500.0, 500.0)
    adjustment = redemption["adjustment"]
    assert (adjustment["adjustment_type"], adjustment["amount"]) == ("points", -5.0)
    assert adjustment["billing_account_entry_id"] == redemption["entry_id"]

    over = _redeem(s, basket["id"], points=600)
    assert over.status_code == 409 and "500.00 point available" in over.text, "the floor holds: 500 left"
    too_much = _redeem(s, basket["id"], points=10, discount=96)
    assert too_much.status_code == 422 and "below zero" in too_much.text, "100 less 5 leaves 95"
    pooled = s["ok"](_redeem(s, s["order"](customer=s["other"])["id"], points=10, discount=1))
    assert pooled["balance"] == 490.0, "whose points may pay is the workspace's rule, not the server's"


def test_a_points_discount_changes_only_with_its_points(shop) -> None:
    s = shop
    basket = s["order"]()
    adjustment = s["ok"](_redeem(s, basket["id"]))["adjustment"]
    edited = s["call"]("PATCH", f"sales-order-adjustments/{adjustment['id']}", {"amount": -50})
    assert edited.status_code == 409 and "restore-points" in edited.text
    assert s["call"]("DELETE", f"sales-order-adjustments/{adjustment['id']}").status_code == 409
    forged = s["call"]("POST", "sales-order-adjustments", {"order_id": basket["id"], "adjustment_type": "points",
                                                            "amount": -5})
    assert forged.status_code == 422 and "redeem-points" in forged.text


def test_taking_the_discount_off_gives_back_what_the_rule_says(shop) -> None:
    s = shop
    basket = s["order"]()
    s["ok"](_redeem(s, basket["id"]))
    back = s["ok"](s["call"]("POST", f"sales-orders/{basket['id']}/restore-points", {"remove_discount": True}), 200)
    assert (back["given_back"], back["outstanding"], back["adjustment"], back["balance"]) == (500.0, 0.0, None, 1000.0)
    again = s["call"]("POST", f"sales-orders/{basket['id']}/restore-points", {})
    assert again.status_code == 409 and "already been given back" in again.text
    assert _audit((THREADED, BOUNDED, FORGOTTEN)) == {THREADED: 0, BOUNDED: 0, FORGOTTEN: 0}

    forfeited = s["order"]()
    s["ok"](_redeem(s, forfeited["id"]))
    nothing = s["call"]("POST", f"sales-orders/{forfeited['id']}/restore-points", {"points": 0})
    assert nothing.status_code == 422 and "remove_discount" in nothing.text
    kept = s["ok"](s["call"]("POST", f"sales-orders/{forfeited['id']}/restore-points",
                             {"points": 200, "remove_discount": True}), 200)
    assert (kept["given_back"], kept["outstanding"], kept["adjustment"], kept["balance"]) == (200.0, 300.0, None, 700.0)
    assert _audit((FORGOTTEN,)) == {FORGOTTEN: 1}, "the forfeited points are named, for the agent to read"


def test_a_return_gives_back_part_and_never_more_than_was_spent(shop) -> None:
    s = shop
    basket = s["order"]()
    s["ok"](_redeem(s, basket["id"]))
    s["ok"](s["call"]("PATCH", f"sales-orders/{basket['id']}", {"status": "submitted"}), 200)
    part = s["ok"](s["call"]("POST", f"sales-orders/{basket['id']}/restore-points",
                             {"points": 200, "expires_at": "2027-12-31T00:00:00Z"}), 200)
    assert (part["given_back"], part["outstanding"]) == (200.0, 300.0)
    assert part["adjustment"] is not None, "the discount stands; the credit note handles the money"
    beyond = s["call"]("POST", f"sales-orders/{basket['id']}/restore-points", {"points": 400})
    assert beyond.status_code == 409 and "300" in beyond.text
    keeping = s["call"]("POST", f"sales-orders/{basket['id']}/restore-points", {"remove_discount": True})
    assert keeping.status_code == 409, "a submitted order is past editing; its discount stays"
    assert _balance(s) == 700.0


def test_billing_the_discount_moves_no_points_and_bills_it_once(shop) -> None:
    s = shop
    basket = s["order"]()
    redemption = s["ok"](_redeem(s, basket["id"]))
    lines = [{"invoice_item_type": "goods", "product_name_snapshot": "tea", "amount": 100,
              "sales_order_item_id": basket["items"][0]["id"]},
             {"invoice_item_type": "points", "product_name_snapshot": "500 points", "amount": -5,
              "billing_account_entry_id": redemption["entry_id"]}]
    invoice = s["ok"](s["call"]("POST", "invoices", {
        "direction": "sales", "employee_id": s["clerk"], "customer_id": s["buyer"], "title": "tea",
        "sales_order_id": basket["id"], "items": lines}))
    assert _balance(s) == 500.0
    twice = s["call"]("POST", "invoice-items", {
        "invoice_id": invoice["id"], "invoice_item_type": "points", "product_name_snapshot": "again", "amount": -1,
        "billing_account_entry_id": redemption["entry_id"]})
    assert twice.status_code == 422 and "at most once" in twice.text
    loose = s["call"]("POST", "invoice-items", {
        "invoice_id": invoice["id"], "invoice_item_type": "points", "product_name_snapshot": "x", "amount": -1})
    assert loose.status_code == 422 and "names the order's redemption" in loose.text
    assert _audit((THREADED, BOUNDED)) == {THREADED: 0, BOUNDED: 0}


def test_a_revision_carries_the_discount_with_its_points(shop) -> None:
    s = shop
    basket = s["order"]()
    redemption = s["ok"](_redeem(s, basket["id"]))
    for state in ("submitted", "confirmed"):
        s["ok"](s["call"]("PATCH", f"sales-orders/{basket['id']}", {"status": state}), 200)
    revision = s["ok"](s["call"]("POST", f"sales-orders/{basket['id']}/revise", {}))
    revision_id = revision.get("id") or revision["order"]["id"]
    carried = s["ok"](s["call"]("GET", f"sales-orders/{revision_id}/points-redemptions"), 200)
    assert [(row["entry_id"], row["adjustment"]["order_id"]) for row in carried] == [(redemption["entry_id"], revision_id)]
    source = s["ok"](s["call"]("GET", f"sales-orders/{basket['id']}/points-redemptions"), 200)[0]
    assert source["adjustment"]["order_id"] == revision_id, "read from the source, the discount stands on the revision"
    assert _audit((FORGOTTEN,)) == {FORGOTTEN: 0}, "the points still buy a standing discount"


def test_the_audit_names_a_cancelled_orders_points_not_given_back(shop) -> None:
    s = shop
    basket = s["order"]()
    s["ok"](_redeem(s, basket["id"]))
    s["ok"](s["call"]("PATCH", f"sales-orders/{basket['id']}", {"status": "cancelled"}), 200)
    assert _audit((FORGOTTEN,)) == {FORGOTTEN: 1}
    s["ok"](s["call"]("POST", f"sales-orders/{basket['id']}/restore-points", {}), 200)
    assert _audit((FORGOTTEN,)) == {FORGOTTEN: 0}
    assert _balance(s) == 1000.0


def test_a_pooled_redemption_bills_to_the_discounted_orders_customer(shop) -> None:
    s = shop
    theirs = s["order"](customer=s["other"])
    redemption = s["ok"](_redeem(s, theirs["id"], points=100, discount=1))
    wrong = s["call"]("POST", "invoices", {
        "direction": "sales", "employee_id": s["clerk"], "customer_id": s["buyer"], "title": "tea",
        "items": [{"invoice_item_type": "points", "product_name_snapshot": "100 points", "amount": -1,
                   "billing_account_entry_id": redemption["entry_id"]}]})
    assert wrong.status_code == 422 and "another customer" in wrong.text
    s["ok"](s["call"]("POST", "invoices", {
        "direction": "sales", "employee_id": s["clerk"], "customer_id": s["other"], "title": "tea",
        "sales_order_id": theirs["id"], "items": [
            {"invoice_item_type": "goods", "product_name_snapshot": "tea", "amount": 100,
             "sales_order_item_id": theirs["items"][0]["id"]},
            {"invoice_item_type": "points", "product_name_snapshot": "100 points", "amount": -1,
             "billing_account_entry_id": redemption["entry_id"]}]}))
