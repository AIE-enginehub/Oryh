"""Sales and marketing review, 2026-10-26: what reaches the customer and the
figures the flow reads stay in one currency and on one customer.

1. The deal-to-quotation bridge prices in the deal's currency: a catalog or
   agreed price in another currency answers nothing.
2. An order fulfils a quotation made to its own customer, in its own
   currency, that is still alive.
3. A deal's customer does not change from under the people on its cast.
4. A campaign's won estimate is one total per currency.
5. Campaign parents never form a loop.
"""

from __future__ import annotations

import pytest

from conftest import invite_member, make_client, provision_tenant

SALES = ["crm.own", "quotation.submit_own", "order.submit_own"]


@pytest.fixture()
def shop():
    with make_client([]) as c:
        t = provision_tenant(c, company_name="Review Sales Co", email="admin@review-sales.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        rep = invite_member(c, admin, "rep", SALES, employee="Rep One", email="rep@review-sales.example")

        def post(path: str, body: dict, who: dict | None = None):
            return c.post(f"/api/v1/{path}", headers=who or admin, json=body)

        acme = post("customers", {"name": "Acme"}).json()["data"]["id"]
        other = post("customers", {"name": "Other Corp"}).json()["data"]["id"]
        widget = post("products", {"name": "Widget", "list_price": 100, "currency": "CNY"}).json()["data"]["id"]
        gadget = post("products", {"name": "Gadget", "list_price": 50, "currency": "CNY"}).json()["data"]["id"]
        agreed = post("customer-products", {"customer_id": acme, "product_id": gadget, "agreed_price": 45, "currency": "CNY"})
        assert agreed.status_code == 201, agreed.text
        yield dict(c=c, admin=admin, rep=dict(rep), emp=rep.employee_id, acme=acme, other=other,
                   widget=widget, gadget=gadget, post=post)


def _deal(s, currency: str, *, customer: str | None = None) -> dict:
    r = s["post"]("opportunities", {"employee_id": s["emp"], "customer_id": customer or s["acme"],
                                    "title": f"{currency} deal", "currency": currency}, s["rep"])
    assert r.status_code == 201, r.text
    deal = r.json()["data"]
    for product in (s["widget"], s["gadget"]):
        assert s["post"]("opportunity-items", {"opportunity_id": deal["id"], "product_id": product, "quantity": 10},
                         s["rep"]).status_code == 201
    return deal


def test_a_usd_deal_is_not_quoted_at_cny_prices(shop) -> None:
    s = shop
    quoted = s["post"](f"opportunities/{_deal(s, 'USD')['id']}/quote", {}, s["rep"])
    assert quoted.status_code == 201, quoted.text
    data = quoted.json()["data"]
    assert data["currency"] == "USD"
    assert [(i["unit_price"], i["price_basis"], i["list_price_snapshot"]) for i in data["items"]] == [
        (None, "unpriced", None), (None, "unpriced", None)], "a CNY price is no USD price"


def test_a_cny_deal_reports_the_catalog_and_the_agreement_and_picks_neither(shop) -> None:
    s = shop
    data = s["post"](f"opportunities/{_deal(s, 'CNY')['id']}/quote", {}, s["rep"]).json()["data"]
    assert [(i["unit_price"], i["price_basis"], i["list_price_snapshot"], i["agreed_price"]) for i in data["items"]] == [
        (None, "unpriced", 100.0, None), (None, "unpriced", 50.0, 45.0)]


def _quotation(s, *, customer: str, currency: str = "CNY", state: str = "accepted") -> dict:
    r = s["post"]("sales-quotations", {"employee_id": s["emp"], "customer_id": customer, "title": f"{state} quote",
                                       "currency": currency, "status": state,
                                       "items": [{"product_id": s["widget"], "quantity": 1, "unit_price": 100}]})
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _order(s, quotation_id: str, *, customer: str, currency: str = "CNY"):
    return s["post"]("sales-orders", {"employee_id": s["emp"], "customer_id": customer, "title": "order",
                                      "currency": currency, "quotation_id": quotation_id,
                                      "items": [{"product_id": s["widget"], "quantity": 1, "unit_price": 100}]},
                     s["rep"])


def test_an_order_fulfils_its_own_customers_quotation_in_its_own_currency(shop) -> None:
    s = shop
    theirs = _quotation(s, customer=s["other"])
    crossed = _order(s, theirs["id"], customer=s["acme"])
    assert crossed.status_code == 422 and "another customer" in crossed.text
    usd = _quotation(s, customer=s["acme"], currency="USD")
    mixed = _order(s, usd["id"], customer=s["acme"])
    assert mixed.status_code == 422 and "USD" in mixed.text
    ours = _quotation(s, customer=s["acme"])
    placed = _order(s, ours["id"], customer=s["acme"])
    assert placed.status_code == 201, placed.text

    order_id = placed.json()["data"]["id"]
    moved = s["c"].patch(f"/api/v1/sales-orders/{order_id}", headers=s["rep"], json={"customer_id": s["other"]})
    assert moved.status_code == 422, "the PATCH is judged on the merged order"
    repointed = s["c"].patch(f"/api/v1/sales-orders/{order_id}", headers=s["rep"], json={"quotation_id": theirs["id"]})
    assert repointed.status_code == 422


@pytest.mark.parametrize("state", ["declined", "expired", "rejected", "superseded"])
def test_an_order_does_not_fulfil_a_dead_quotation(shop, state) -> None:
    s = shop
    refused = _order(s, _quotation(s, customer=s["acme"], state=state)["id"], customer=s["acme"])
    assert refused.status_code == 409 and state in refused.text


@pytest.mark.parametrize("state", ["draft", "approved", "sent", "accepted"])
def test_a_live_or_draft_quotation_is_still_orderable(shop, state) -> None:
    s = shop
    assert _order(s, _quotation(s, customer=s["acme"], state=state)["id"], customer=s["acme"]).status_code == 201


def test_a_deals_customer_does_not_change_from_under_its_people(shop) -> None:
    s = shop
    alice = s["post"]("customer-contacts", {"customer_id": s["acme"], "name": "Alice at Acme"}).json()["data"]["id"]
    deal = _deal(s, "CNY")
    row = s["post"]("opportunity-contacts", {"opportunity_id": deal["id"], "contact_id": alice, "is_primary": True},
                    s["rep"])
    assert row.status_code == 201, row.text
    moved = s["c"].patch(f"/api/v1/opportunities/{deal['id']}", headers=s["rep"], json={"customer_id": s["other"]})
    assert moved.status_code == 409 and "Alice at Acme" in moved.text

    assert s["c"].delete(f"/api/v1/opportunity-contacts/{row.json()['data']['id']}", headers=s["rep"]).status_code == 204
    assert s["c"].patch(f"/api/v1/opportunities/{deal['id']}", headers=s["rep"],
                        json={"customer_id": s["other"]}).status_code == 200
    quoted = s["post"](f"opportunities/{deal['id']}/quote", {}, s["rep"]).json()["data"]
    assert quoted["customer_id"] == s["other"] and quoted["contact_name"] is None


def test_a_campaigns_won_estimate_is_one_total_per_currency(shop) -> None:
    s = shop
    campaign = s["post"]("campaigns", {"name": "Expo", "employee_id": s["emp"], "currency": "CNY"}).json()["data"]
    for currency, amount in (("CNY", 10000), ("CNY", 2500), ("USD", 10000)):
        deal = s["post"]("opportunities", {"employee_id": s["emp"], "customer_id": s["acme"], "title": currency,
                                           "campaign_id": campaign["id"], "currency": currency,
                                           "expected_amount": amount, "status": "won"}, s["rep"])
        assert deal.status_code == 201, deal.text
    detail = s["c"].get(f"/api/v1/campaigns/{campaign['id']}/detail", headers=s["admin"]).json()["data"]
    assert detail["opportunities_won"] == 3
    assert detail["won_expected_amount"] == 12500.0
    assert detail["won_expected_other_currencies"] == {"USD": 10000.0}


def test_campaign_parents_never_loop(shop) -> None:
    s = shop
    a = s["post"]("campaigns", {"name": "A", "employee_id": s["emp"]}).json()["data"]
    b = s["post"]("campaigns", {"name": "B", "employee_id": s["emp"], "parent_campaign_id": a["id"]}).json()["data"]
    c = s["post"]("campaigns", {"name": "C", "employee_id": s["emp"], "parent_campaign_id": b["id"]}).json()["data"]
    for child, parent in ((a, c), (a, b), (b, c), (a, a)):
        loop = s["c"].patch(f"/api/v1/campaigns/{child['id']}", headers=s["admin"], json={"parent_campaign_id": parent["id"]})
        assert loop.status_code == 422 and "own parent" in loop.text, (child["name"], parent["name"])
    d = s["post"]("campaigns", {"name": "D", "employee_id": s["emp"]}).json()["data"]
    assert s["c"].patch(f"/api/v1/campaigns/{d['id']}", headers=s["admin"],
                        json={"parent_campaign_id": c["id"]}).status_code == 200, "a deeper chain is still fine"
