"""External identity mapping: a platform's numbers translated into ours.

Two tables with OPPOSITE uniqueness semantics, and the difference is the
design: external_product_maps is reference data where multiple rows per
external id are the point (a bundle listing is several rows with
quantities), while external_document_links is a transactional claim whose
full tuple is hard-unique — recording the same link twice is a retry, and
that constraint is what makes "have we imported TM2026… already?" a
reliable dedup query instead of a convention. Splits and merges are rows:
one platform order fulfilled as two of ours is two link rows.

Authority is not its own capability. Maps are catalog curation
(master_data.manage); a link follows the DOCUMENT it annotates — whoever
may record a sales order may say where it came from, whoever may post
stock movements may name the parcel a movement belongs to, and a
business-object link is scoped by that object's own type. Without the
per-type gate, "links are harmless annotations" would quietly become a
write surface any credential could reach.

The server also lowercases `source` everywhere: "Tmall" and "tmall"
silently splitting the mapping space is the exact mess these tables exist
to prevent.
"""

from __future__ import annotations

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant

FAKE = "00000000-0000-0000-0000-000000000000"


@pytest.fixture()
def channel():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Channel Co", email="admin@channel.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        seq = {"n": 0}

        def key_holding(*permissions: str) -> dict:
            seq["n"] += 1
            role = f"desk{seq['n']}"
            client.post("/api/v1/roles", json={"name": role, "permissions": list(permissions)},
                        headers=admin)
            uid = client.post("/api/v1/auth/invitations",
                              json={"email": f"{role}@channel.example", "role": role},
                              headers=admin).json()["data"]["id"]
            token = next(l.rsplit("token=", 1)[1].strip()
                         for l in outbox.messages[-1].body.splitlines() if "token=" in l)
            client.post("/api/v1/auth/invitations/accept",
                        json={"token": token, "password": "invitee-pass1"})
            plain = client.post("/api/v1/tenant/api-keys", json={"label": role, "user_id": uid},
                                headers=admin).json()["data"]["plain_text_api_key"]
            return {"X-API-Key": plain}

        emp = client.post("/api/v1/employees", json={"name": "Seller"},
                          headers=admin).json()["data"]["id"]
        cust = client.post("/api/v1/customers", json={"name": "Marketplace Buyer"},
                           headers=admin).json()["data"]["id"]
        product_a = client.post("/api/v1/products", json={"name": "Cup", "product_code": "CUP-1"},
                                headers=admin).json()["data"]["id"]
        product_b = client.post("/api/v1/products", json={"name": "Lid", "product_code": "LID-1"},
                                headers=admin).json()["data"]["id"]

        def order(title: str) -> str:
            return client.post("/api/v1/sales-orders", json={
                "employee_id": emp, "customer_id": cust, "title": title,
            }, headers=admin).json()["data"]["id"]

        yield {
            "client": client, "admin": admin, "key_holding": key_holding,
            "employee": emp, "customer": cust,
            "product_a": product_a, "product_b": product_b, "order": order,
        }


# --- the product map: reference data, curated like the catalog --------------


def test_map_curation_is_catalog_authority_and_source_is_normalized(channel) -> None:
    seller = channel["key_holding"]("order.submit_own")
    body = {"source": "Tmall ", "external_product_id": "TB-6543",
            "product_id": channel["product_a"]}
    refused = channel["client"].post("/api/v1/external-product-maps", json=body, headers=seller)
    assert refused.status_code == 403, "the map is catalog curation, not a seller's whiteboard"

    created = channel["client"].post("/api/v1/external-product-maps", json=body,
                                     headers=channel["admin"])
    assert created.status_code == 201, created.text
    assert created.json()["data"]["source"] == "tmall", \
        "'Tmall ' and 'tmall' must be one source, not two mapping spaces"
    assert float(created.json()["data"]["quantity"]) == 1.0


def test_a_bundle_is_rows_and_an_exact_duplicate_is_a_conflict(channel) -> None:
    admin, client = channel["admin"], channel["client"]
    listing = {"source": "jd", "external_product_id": "JD-9001"}
    two_cups = client.post("/api/v1/external-product-maps", headers=admin, json={
        **listing, "product_id": channel["product_a"], "quantity": 2,
        "external_name": "两杯一盖套装"})
    one_lid = client.post("/api/v1/external-product-maps", headers=admin, json={
        **listing, "product_id": channel["product_b"], "quantity": 1})
    assert two_cups.status_code == 201 and one_lid.status_code == 201, \
        "a bundle listing IS several rows — that is the many-to-many"

    dup = client.post("/api/v1/external-product-maps", headers=admin, json={
        **listing, "product_id": channel["product_a"], "quantity": 3})
    assert dup.status_code == 409, dup.text
    assert two_cups.json()["data"]["id"] in dup.json()["detail"], \
        "the conflict must name the existing row so the agent PATCHes instead of retrying"

    rows = client.get(
        "/api/v1/external-product-maps",
        params={"source": "JD", "external_product_id": "JD-9001"},
        headers=admin).json()["data"]
    assert {r["product_id"] for r in rows} == {channel["product_a"], channel["product_b"]}
    assert sum(float(r["quantity"]) for r in rows) == 3.0

    sku_level = client.post("/api/v1/external-product-maps", headers=admin, json={
        **listing, "external_sku_id": "sku-red", "product_id": channel["product_a"]})
    assert sku_level.status_code == 201, \
        "a platform SKU under the same listing is its own identity, not a duplicate"


def test_a_listing_swap_is_windows_and_swapping_back_is_legal(channel) -> None:
    """A merchant keeps the promotion slot: same Tmall id, different goods
    over time. The map must answer "what did this listing mean on the ORDER's
    date" — back-dated imports are the norm — and must not refuse a listing
    returning to a product it meant before."""
    admin, client = channel["admin"], channel["client"]
    a, b = channel["product_a"], channel["product_b"]
    listing = {"source": "tmall", "external_product_id": "SLOT-1"}

    def resolve(at: str) -> list[dict]:
        return client.get("/api/v1/external-product-maps",
                          params={**listing, "at": at},
                          headers=admin).json()["data"]

    first = client.post("/api/v1/external-product-maps", headers=admin,
                        json={**listing, "product_id": a}).json()["data"]["id"]

    # the swap: close the old window, open the new — the old row stays ACTIVE
    closed = client.patch(f"/api/v1/external-product-maps/{first}", headers=admin,
                          json={"effective_to": "2026-08-15"})
    assert closed.status_code == 200, closed.text
    assert closed.json()["data"]["status"] == "active", \
        "a superseded pairing is history, not a mistake — it stays active"
    swapped = client.post("/api/v1/external-product-maps", headers=admin, json={
        **listing, "product_id": b, "effective_from": "2026-08-15"})
    assert swapped.status_code == 201, \
        "a closed window frees the slot — supersession must not 409"

    assert [r["product_id"] for r in resolve("2026-08-10")] == [a], \
        "an order from before the swap translates against what the listing meant THEN"
    assert [r["product_id"] for r in resolve("2026-08-20")] == [b]
    assert [r["product_id"] for r in resolve("2026-08-15")] == [b], \
        "[from, to) — the swap day belongs to the new meaning"

    # the swap BACK: the listing means product A again. The old constraint
    # made this a permanent 409; a closed A row must not block a new open one.
    client.patch(f"/api/v1/external-product-maps/{swapped.json()['data']['id']}",
                 headers=admin, json={"effective_to": "2026-08-25"})
    again = client.post("/api/v1/external-product-maps", headers=admin, json={
        **listing, "product_id": a, "effective_from": "2026-08-25"})
    assert again.status_code == 201, \
        "swapping back to a product the listing meant before is reality, not a duplicate"
    assert [r["product_id"] for r in resolve("2026-08-27")] == [a]

    # while an OPEN pairing stands, a second open one for the same product is
    # the only thing refused
    dup = client.post("/api/v1/external-product-maps", headers=admin,
                      json={**listing, "product_id": a})
    assert dup.status_code == 409, dup.text
    assert "open-ended" in dup.json()["detail"]

    # reopening a closed row against a standing open one hits the same wall
    reopen = client.patch(f"/api/v1/external-product-maps/{first}", headers=admin,
                          json={"effective_to": None})
    assert reopen.status_code == 409, \
        "two open-ended assertions for one pairing is the ambiguity the index exists to stop"

    # a purely historical pairing (both bounds set) never fights the open
    # one — the mid-year onboarding case: map last month to import last month
    history = client.post("/api/v1/external-product-maps", headers=admin, json={
        **listing, "product_id": a,
        "effective_from": "2026-07-01", "effective_to": "2026-07-10"})
    assert history.status_code == 201, \
        "a closed window is history, and history never conflicts with the present"

    everything = client.get("/api/v1/external-product-maps", params=listing,
                            headers=admin).json()["data"]
    assert len(everything) == 4, "history is rows kept, not rows replaced"


def test_archived_means_withdrawn_and_never_translates(channel) -> None:
    admin, client = channel["admin"], channel["client"]
    row = client.post("/api/v1/external-product-maps", headers=admin, json={
        "source": "tmall", "external_product_id": "MISTAKE-1",
        "product_id": channel["product_a"],
        "effective_from": "2026-08-01", "effective_to": "2026-08-05"}).json()["data"]["id"]
    client.patch(f"/api/v1/external-product-maps/{row}", headers=admin,
                 json={"status": "archived"})
    covered = client.get("/api/v1/external-product-maps",
                         params={"source": "tmall", "external_product_id": "MISTAKE-1",
                                 "at": "2026-08-03"},
                         headers=admin).json()["data"]
    assert covered == [], \
        "archived is withdrawn — a voided pairing never described the listing, window or not"


def test_a_window_must_run_forward(channel) -> None:
    admin, client = channel["admin"], channel["client"]
    backwards = client.post("/api/v1/external-product-maps", headers=admin, json={
        "source": "tmall", "external_product_id": "TIME-1",
        "product_id": channel["product_a"],
        "effective_from": "2026-08-15", "effective_to": "2026-08-15"})
    assert backwards.status_code == 422, backwards.text

    row = client.post("/api/v1/external-product-maps", headers=admin, json={
        "source": "tmall", "external_product_id": "TIME-1",
        "product_id": channel["product_a"],
        "effective_from": "2026-08-15"}).json()["data"]["id"]
    crossed = client.patch(f"/api/v1/external-product-maps/{row}", headers=admin,
                           json={"effective_to": "2026-08-01"})
    assert crossed.status_code == 422, \
        "a PATCH can move one bound against the other already on the row"


def test_a_sku_of_another_product_is_refused(channel) -> None:
    admin, client = channel["admin"], channel["client"]
    sku_b = client.post("/api/v1/product-skus", headers=admin, json={
        "product_id": channel["product_b"], "sku_code": "LID-RED"}).json()["data"]["id"]
    crossed = client.post("/api/v1/external-product-maps", headers=admin, json={
        "source": "jd", "external_product_id": "JD-9002",
        "product_id": channel["product_a"], "sku_id": sku_b})
    assert crossed.status_code == 422, crossed.text
    assert channel["product_b"] in crossed.json()["detail"]


# --- the document link: a hard-unique transactional claim -------------------


def test_an_order_link_dedups_and_a_split_is_two_rows(channel) -> None:
    client = channel["client"]
    seller = channel["key_holding"]("order.submit_own")
    first, second = channel["order"]("拆单 part 1"), channel["order"]("拆单 part 2")

    link = {"source": "Tmall", "external_kind": "order",
            "external_no": "TM2026082800101", "entity_type": "sales_order"}
    created = client.post("/api/v1/external-document-links", headers=seller,
                          json={**link, "entity_id": first})
    assert created.status_code == 201, created.text
    assert created.json()["data"]["source"] == "tmall"
    assert created.json()["data"]["created_by"], "a claim without an author is not attributable"

    retry = client.post("/api/v1/external-document-links", headers=seller,
                        json={**link, "entity_id": first})
    assert retry.status_code == 409, "recording the same link twice is a retry, not a new fact"
    assert created.json()["data"]["id"] in retry.json()["detail"]

    split = client.post("/api/v1/external-document-links", headers=seller,
                        json={**link, "entity_id": second})
    assert split.status_code == 201, "拆单: one platform order, two of ours — two rows"

    by_number = client.get("/api/v1/external-document-links",
                           params={"source": "Tmall", "external_no": "TM2026082800101"},
                           headers=seller).json()["data"]
    assert {r["entity_id"] for r in by_number} == {first, second}

    by_document = client.get("/api/v1/external-document-links",
                             params={"entity_type": "sales_order", "entity_id": first},
                             headers=seller).json()["data"]
    assert [r["external_no"] for r in by_document] == ["TM2026082800101"]


def test_a_link_names_a_real_document_of_a_known_kind(channel) -> None:
    seller = channel["key_holding"]("order.submit_own")
    ghost = channel["client"].post("/api/v1/external-document-links", headers=seller, json={
        "source": "jd", "external_kind": "order", "external_no": "JD-1",
        "entity_type": "sales_order", "entity_id": FAKE})
    assert ghost.status_code == 404, "a link to a document this tenant does not hold is a lie"

    unknown = channel["client"].post("/api/v1/external-document-links", headers=seller, json={
        "source": "jd", "external_kind": "order", "external_no": "JD-1",
        "entity_type": "warehouse_gossip", "entity_id": FAKE})
    assert unknown.status_code == 422, unknown.text
    assert "sales_order" in unknown.json()["detail"], \
        "the refusal must teach which kinds ARE linkable"


def test_link_authority_follows_the_document(channel) -> None:
    admin, client = channel["admin"], channel["client"]
    seller = channel["key_holding"]("order.submit_own")

    invoice = client.post("/api/v1/invoices", headers=admin, json={
        "direction": "sales", "employee_id": channel["employee"],
        "customer_id": channel["customer"], "title": "平台结算发票",
        "total_amount": 10.0, "currency": "CNY"}).json()["data"]["id"]
    refused = client.post("/api/v1/external-document-links", headers=seller, json={
        "source": "tmall", "external_kind": "settlement", "external_no": "ST-1",
        "entity_type": "invoice", "entity_id": invoice})
    assert refused.status_code == 403, \
        "order.submit_own must not annotate invoices — authority follows the document"

    item = client.post("/api/v1/inventory-items", headers=admin, json={
        "product_id": channel["product_a"], "facility": "main",
        "initial_quantity": 5}).json()["data"]["id"]
    keeper = channel["key_holding"]("inventory.manage")
    moved = client.post("/api/v1/inventory-item-details", headers=keeper, json={
        "inventory_item_id": item, "quantity_on_hand_diff": 1, "reason": "returned",
        "description": "mystery parcel, later identified"})
    assert moved.status_code == 201, moved.text
    named = client.post("/api/v1/external-document-links", headers=keeper, json={
        "source": "JD", "external_kind": "return", "external_no": "JDR-7788",
        "entity_type": "inventory_item_detail", "entity_id": moved.json()["data"]["id"]})
    assert named.status_code == 201, \
        "identifying the parcel later is a LINK on the frozen ledger row, not an edit"

    note = client.post("/api/v1/business-objects", headers=admin, json={
        "object_type": "return_note", "title": "退货单 R-1"}).json()["data"]["id"]
    outsider = client.post("/api/v1/external-document-links", headers=seller, json={
        "source": "tmall", "external_kind": "return", "external_no": "TMR-9",
        "entity_type": "business_object", "entity_id": note})
    assert outsider.status_code == 403, "business_object links are scoped by the object's type"
    clerk = channel["key_holding"]("business_object.write:return_note")
    allowed = client.post("/api/v1/external-document-links", headers=clerk, json={
        "source": "tmall", "external_kind": "return", "external_no": "TMR-9",
        "entity_type": "business_object", "entity_id": note})
    assert allowed.status_code == 201, allowed.text


def test_a_mislink_is_deletable_and_the_slot_reopens(channel) -> None:
    client = channel["client"]
    seller = channel["key_holding"]("order.submit_own")
    order = channel["order"]("linked to the wrong number")
    link = {"source": "amazon", "external_kind": "order",
            "external_no": "111-222", "entity_type": "sales_order", "entity_id": order}
    first = client.post("/api/v1/external-document-links", headers=seller, json=link)
    assert first.status_code == 201, first.text
    link_id = first.json()["data"]["id"]

    nobody = channel["key_holding"]()
    assert client.delete(f"/api/v1/external-document-links/{link_id}",
                         headers=nobody).status_code == 403, \
        "removing a claim takes the same authority as making it"

    assert client.delete(f"/api/v1/external-document-links/{link_id}",
                         headers=seller).status_code == 204
    again = client.post("/api/v1/external-document-links", headers=seller, json=link)
    assert again.status_code == 201, "deletion reopens the slot — a mislink is not history"
