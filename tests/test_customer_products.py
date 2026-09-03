"""Customer price agreements: SupplierProduct's sell-side mirror.

One customer's standing terms for one product — THEIR code and name for it,
the agreed price, order rules. What is pinned here: the (product, customer)
pair is one row whose lapse is status (archiving does not free the pair —
the agreement REVIVES, because "we used to sell them this" and "we sell
them this again" are the same relationship, not two); the customer's own
item code answers the reverse lookup their purchase orders force; the whole
workspace reads agreements, the catalog desk writes them; and the pair's
identity is not editable — an agreement does not move to another customer.
"""

from __future__ import annotations

import pytest

from conftest import make_client, provision_tenant, invite_member


@pytest.fixture()
def desk():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Agree Co", email="admin@agree.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        product = client.post("/api/v1/products", json={"name": "工业阀门DN50"},
                              headers=admin).json()["data"]["id"]
        hospital = client.post("/api/v1/customers", json={"name": "市一医院"},
                               headers=admin).json()["data"]["id"]

        member = invite_member(client, admin, "nobody", [])

        yield {"client": client, "admin": admin, "member": member,
               "product": product, "customer": hospital}


def test_one_agreement_per_pair_that_revives_instead_of_duplicating(desk) -> None:
    client, admin = desk["client"], desk["admin"]
    made = client.post("/api/v1/customer-products", headers=admin, json={
        "product_id": desk["product"], "customer_id": desk["customer"],
        "customer_product_code": "KH-3301", "agreed_price": 88.0})
    assert made.status_code == 201, made.text
    agreement = made.json()["data"]
    assert agreement["customer_name"] == "市一医院", \
        "a list of agreements says whose they are without a query per row"

    doubled = client.post("/api/v1/customer-products", headers=admin, json={
        "product_id": desk["product"], "customer_id": desk["customer"]})
    assert doubled.status_code == 409
    assert agreement["id"] in doubled.json()["detail"], \
        "the refusal hands over the existing row — PATCH it, do not fork it"

    client.delete(f"/api/v1/customer-products/{agreement['id']}", headers=admin)
    still_409 = client.post("/api/v1/customer-products", headers=admin, json={
        "product_id": desk["product"], "customer_id": desk["customer"]})
    assert still_409.status_code == 409, (
        "archiving does not free the pair — a lapsed agreement and a new one "
        "with the same customer are the same relationship, so it revives"
    )
    revived = client.patch(f"/api/v1/customer-products/{agreement['id']}",
                           headers=admin, json={"status": "active", "agreed_price": 92.0})
    assert revived.status_code == 200
    assert float(revived.json()["data"]["agreed_price"]) == 92.0


def test_the_customers_own_code_answers_their_purchase_order(desk) -> None:
    client, admin = desk["client"], desk["admin"]
    client.post("/api/v1/customer-products", headers=admin, json={
        "product_id": desk["product"], "customer_id": desk["customer"],
        "customer_product_code": "KH-3301", "customer_product_name": "阀门（医用）",
        "agreed_price": 88.0, "min_order_quantity": 10})
    other = client.post("/api/v1/products", json={"name": "法兰垫片"},
                        headers=admin).json()["data"]["id"]
    client.post("/api/v1/customer-products", headers=admin, json={
        "product_id": other, "customer_id": desk["customer"],
        "customer_product_code": "KH-9902"})
    found = client.get("/api/v1/customer-products",
                       params={"customer_id": desk["customer"],
                               "customer_product_code": "KH-3301"},
                       headers=desk["member"])
    assert found.status_code == 200, "agreements are master data — everyone reads them"
    rows = found.json()["data"]
    assert [r["product_id"] for r in rows] == [desk["product"]], \
        "货号 KH-3301 on their PO resolves to exactly our product"

    refused = client.post("/api/v1/customer-products", headers=desk["member"], json={
        "product_id": desk["product"], "customer_id": desk["customer"]})
    assert refused.status_code == 403, "writing agreements is catalog work"


def test_the_pair_is_identity_and_ghosts_are_refused(desk) -> None:
    client, admin = desk["client"], desk["admin"]
    ghost = "00000000-0000-0000-0000-000000000000"
    for body in ({"product_id": ghost, "customer_id": desk["customer"]},
                 {"product_id": desk["product"], "customer_id": ghost}):
        assert client.post("/api/v1/customer-products", headers=admin,
                           json=body).status_code == 404

    made = client.post("/api/v1/customer-products", headers=admin, json={
        "product_id": desk["product"], "customer_id": desk["customer"]}).json()["data"]
    other = client.post("/api/v1/customers", json={"name": "另一家"},
                        headers=admin).json()["data"]["id"]
    moved = client.patch(f"/api/v1/customer-products/{made['id']}",
                         headers=admin, json={"customer_id": other})
    assert moved.status_code == 422, \
        "the (product, customer) pair is the row's identity — not editable"


def test_same_product_different_customers_different_terms(desk) -> None:
    client, admin = desk["client"], desk["admin"]
    factory = client.post("/api/v1/customers", json={"name": "钢厂"},
                          headers=admin).json()["data"]["id"]
    client.post("/api/v1/customer-products", headers=admin, json={
        "product_id": desk["product"], "customer_id": desk["customer"],
        "agreed_price": 88.0})
    ok = client.post("/api/v1/customer-products", headers=admin, json={
        "product_id": desk["product"], "customer_id": factory,
        "agreed_price": 79.5, "customer_product_code": "GT-77"})
    assert ok.status_code == 201, "the exception is per customer — pairs do not collide"
    by_product = client.get("/api/v1/customer-products",
                            params={"product_id": desk["product"]},
                            headers=admin).json()["data"]
    assert sorted(float(r["agreed_price"]) for r in by_product) == [79.5, 88.0]
