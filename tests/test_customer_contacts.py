"""Customer contacts: the rolodex behind a B2B account.

ProductSku's shape applied to Customer — a child identity table the whole
workspace reads and the catalog desk writes. What is pinned here is the
rolodex's two honesty rules and their mechanics: setting a new PRIMARY
demotes the old one in the same write (one question, one answer — and the
partial unique index backstops the race the handler cannot see), and one
active row per (customer, phone) — the same number twice under one customer
is a duplicate person, with archiving freeing the slot. Documents keep
their free-text contact snapshots; nothing here adds a contact FK to any
document, on purpose.
"""

from __future__ import annotations

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant


@pytest.fixture()
def rolodex():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Rolodex Co", email="admin@rolodex.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        hospital = client.post("/api/v1/customers", json={"name": "市一医院"},
                               headers=admin).json()["data"]["id"]

        client.post("/api/v1/roles", json={"name": "nobody", "permissions": []}, headers=admin)
        uid = client.post("/api/v1/auth/invitations",
                          json={"email": "n@rolodex.example", "role": "nobody"},
                          headers=admin).json()["data"]["id"]
        token = next(l.rsplit("token=", 1)[1].strip()
                     for l in outbox.messages[-1].body.splitlines() if "token=" in l)
        client.post("/api/v1/auth/invitations/accept",
                    json={"token": token, "password": "invitee-pass1"})
        member = {"X-API-Key": client.post(
            "/api/v1/tenant/api-keys", json={"label": "nobody", "user_id": uid},
            headers=admin).json()["data"]["plain_text_api_key"]}

        def add(name: str, **extra) -> dict:
            r = client.post("/api/v1/customer-contacts", headers=admin,
                            json={"customer_id": hospital, "name": name, **extra})
            assert r.status_code == 201, r.text
            return r.json()["data"]

        yield {"client": client, "admin": admin, "member": member,
               "customer": hospital, "add": add}


def test_many_people_at_one_customer_and_everyone_reads(rolodex) -> None:
    rolodex["add"]("李采购", title="采购科", phone="13800000001")
    rolodex["add"]("王工", title="设备科", phone="13800000002")
    rolodex["add"]("张姐", title="财务", phone="13800000003", is_primary=True)

    listed = rolodex["client"].get("/api/v1/customer-contacts",
                                   params={"customer_id": rolodex["customer"]},
                                   headers=rolodex["member"])
    assert listed.status_code == 200, "the rolodex is master data — everyone reads it"
    rows = listed.json()["data"]
    assert len(rows) == 3
    assert rows[0]["name"] == "张姐" and rows[0]["is_primary"], \
        "the primary answers 找谁 — it lists first"

    refused = rolodex["client"].post("/api/v1/customer-contacts", headers=rolodex["member"],
                                     json={"customer_id": rolodex["customer"], "name": "冒名"})
    assert refused.status_code == 403, "writing the rolodex is catalog work"


def test_a_new_primary_demotes_the_old_in_the_same_write(rolodex) -> None:
    first = rolodex["add"]("老主联", is_primary=True)
    second = rolodex["add"]("新主联", is_primary=True)
    assert second["is_primary"]

    old = rolodex["client"].get(f"/api/v1/customer-contacts/{first['id']}",
                                headers=rolodex["admin"]).json()["data"]
    assert old["is_primary"] is False, \
        "one question, one answer — the old primary steps down in the same write"

    third = rolodex["add"]("三号")
    promoted = rolodex["client"].patch(f"/api/v1/customer-contacts/{third['id']}",
                                       headers=rolodex["admin"], json={"is_primary": True})
    assert promoted.status_code == 200
    again = rolodex["client"].get(f"/api/v1/customer-contacts/{second['id']}",
                                  headers=rolodex["admin"]).json()["data"]
    assert again["is_primary"] is False


def test_the_same_phone_twice_is_a_duplicate_person(rolodex) -> None:
    kept = rolodex["add"]("李采购", phone="13911112222")
    dup = rolodex["client"].post("/api/v1/customer-contacts", headers=rolodex["admin"],
                                 json={"customer_id": rolodex["customer"],
                                       "name": "李采购(重复)", "phone": "13911112222"})
    assert dup.status_code == 409, dup.text
    assert "duplicate person" in dup.json()["detail"]

    assert rolodex["client"].delete(f"/api/v1/customer-contacts/{kept['id']}",
                                    headers=rolodex["admin"]).status_code == 204
    revived = rolodex["client"].post("/api/v1/customer-contacts", headers=rolodex["admin"],
                                     json={"customer_id": rolodex["customer"],
                                           "name": "李采购", "phone": "13911112222"})
    assert revived.status_code == 201, "archiving frees the slot — the person came back"

    other = rolodex["client"].post("/api/v1/customers", json={"name": "二院"},
                                   headers=rolodex["admin"]).json()["data"]["id"]
    elsewhere = rolodex["client"].post("/api/v1/customer-contacts", headers=rolodex["admin"],
                                       json={"customer_id": other, "name": "同号别家",
                                             "phone": "13911112222"})
    assert elsewhere.status_code == 201, \
        "the dedup is per customer — one person may sit in two rolodexes"


def test_a_contact_belongs_to_a_real_customer_here(rolodex) -> None:
    ghost = rolodex["client"].post("/api/v1/customer-contacts", headers=rolodex["admin"],
                                   json={"customer_id": "00000000-0000-0000-0000-000000000000",
                                         "name": "查无此人"})
    assert ghost.status_code == 404
