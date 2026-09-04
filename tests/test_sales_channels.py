"""Sales channels: the keys orders arrive under, kept as master data.

`source` used to be a string three tables agreed on by convention. Now a
channel is a row whose `channel_code` IS that key — lowercase, immutable,
unique per tenant regardless of status (an archived channel REVIVES, never
forks) — so "which channels do we sell through" has an answer and two
Amazon stores are two rows under one channel. What is pinned: the code's
identity and revival, the kind from the tenant's vocabulary, stores naming
their channel by id or by code (an unregistered code is refused with its
fix, never invented), the store list answering by channel key, and the
product map refusing a source nobody registered.
"""

from __future__ import annotations

import pytest

from conftest import make_client, provision_tenant, invite_member


@pytest.fixture()
def market():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Market Co", email="admin@market.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        member = invite_member(client, admin, "nobody", [])

        def channel(code: str, name: str, kind: str = "marketplace", **extra) -> dict:
            r = client.post("/api/v1/sales-channels", headers=admin,
                            json={"channel_code": code, "name": name, "channel_kind": kind, **extra})
            assert r.status_code == 201, r.text
            return r.json()["data"]

        yield {"client": client, "admin": admin, "member": member, "channel": channel}


def test_the_code_is_the_key_and_an_archived_channel_revives(market) -> None:
    client, admin = market["client"], market["admin"]
    amazon = market["channel"]("  Amazon ", "亚马逊")
    assert amazon["channel_code"] == "amazon", "the key lowercases like every source"

    doubled = client.post("/api/v1/sales-channels", headers=admin, json={
        "channel_code": "AMAZON", "name": "亚马逊北美", "channel_kind": "marketplace"})
    assert doubled.status_code == 409 and amazon["id"] in doubled.json()["detail"], \
        "one code is one channel — the refusal hands over the row"

    same_name = client.post("/api/v1/sales-channels", headers=admin, json={
        "channel_code": "jd", "name": "亚马逊", "channel_kind": "marketplace"})
    assert same_name.status_code == 409, "two live channels cannot share a name"

    odd_kind = client.post("/api/v1/sales-channels", headers=admin, json={
        "channel_code": "shop", "name": "小程序", "channel_kind": "telepathy"})
    assert odd_kind.status_code == 422, "the kind comes from the tenant's vocabulary"

    assert client.delete(f"/api/v1/sales-channels/{amazon['id']}", headers=admin).status_code == 204
    still = client.post("/api/v1/sales-channels", headers=admin, json={
        "channel_code": "amazon", "name": "亚马逊", "channel_kind": "marketplace"})
    assert still.status_code == 409 and amazon["id"] in still.json()["detail"], \
        "archiving does not free the code — the refusal names the row to revive"
    revived = client.patch(f"/api/v1/sales-channels/{amazon['id']}", headers=admin,
                           json={"status": "active", "channel_kind": "own_site"})
    assert revived.status_code == 200 and revived.json()["data"]["channel_kind"] == "own_site"

    listed = client.get("/api/v1/sales-channels", headers=market["member"],
                        params={"channel_kind": "own_site"})
    assert listed.status_code == 200, "channels are master data — everyone reads them"
    assert [r["channel_code"] for r in listed.json()["data"]] == ["amazon"]
    refused = client.post("/api/v1/sales-channels", headers=market["member"], json={
        "channel_code": "ebay", "name": "eBay", "channel_kind": "marketplace"})
    assert refused.status_code == 403, "registering a channel is catalog work"


def test_two_stores_hang_under_one_channel(market) -> None:
    client, admin = market["client"], market["admin"]
    amazon = market["channel"]("amazon", "亚马逊")

    by_code = client.post("/api/v1/stores", headers=admin, json={
        "name": "Amazon US", "channel": "online", "source": "Amazon"})
    assert by_code.status_code == 201, by_code.text
    by_id = client.post("/api/v1/stores", headers=admin, json={
        "name": "Amazon EU", "channel": "online", "sales_channel_id": amazon["id"]})
    assert by_id.status_code == 201, by_id.text
    for store in (by_code.json()["data"], by_id.json()["data"]):
        assert store["source"] == "amazon" and store["sales_channel_name"] == "亚马逊", \
            "a store read says its channel by key and by name, no second query"

    under = client.get("/api/v1/stores", headers=admin, params={"source": "AMAZON"})
    assert {r["name"] for r in under.json()["data"]} == {"Amazon US", "Amazon EU"}, \
        "one channel, two stores — the key lists them together"

    ghost = client.post("/api/v1/stores", headers=admin, json={
        "name": "eBay", "channel": "online", "source": "ebay"})
    assert ghost.status_code == 422 and "register it first" in ghost.json()["detail"], \
        "an unregistered key is refused with its fix, never invented"

    client.delete(f"/api/v1/sales-channels/{amazon['id']}", headers=admin)
    onto_archived = client.post("/api/v1/stores", headers=admin, json={
        "name": "Amazon JP", "channel": "online", "source": "amazon"})
    assert onto_archived.status_code == 409, "an archived channel names its fix: revive first"
    kept = client.get(f"/api/v1/stores/{by_code.json()['data']['id']}", headers=admin).json()["data"]
    assert kept["sales_channel_id"] == amazon["id"], "existing stores keep their pointer"

    cleared = client.patch(f"/api/v1/stores/{by_id.json()['data']['id']}", headers=admin,
                           json={"sales_channel_id": None})
    assert cleared.status_code == 200 and cleared.json()["data"]["source"] is None, \
        "explicit null takes the store off the channel"


def test_a_map_row_names_a_registered_channel(market) -> None:
    client, admin = market["client"], market["admin"]
    product = client.post("/api/v1/products", headers=admin,
                          json={"name": "Cup"}).json()["data"]["id"]
    unregistered = client.post("/api/v1/external-product-maps", headers=admin, json={
        "source": "ebay", "external_product_id": "E-1", "product_id": product})
    assert unregistered.status_code == 422 and "register it first" in unregistered.json()["detail"]
    market["channel"]("ebay", "eBay")
    mapped = client.post("/api/v1/external-product-maps", headers=admin, json={
        "source": "eBay", "external_product_id": "E-1", "product_id": product})
    assert mapped.status_code == 201, mapped.text
