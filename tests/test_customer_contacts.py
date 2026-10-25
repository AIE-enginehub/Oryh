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

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_customer_contacts.json').read_text(encoding="utf-8"))


import pytest

from conftest import make_client, provision_tenant, invite_member


@pytest.fixture()
def rolodex():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Rolodex Co", email="admin@rolodex.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        hospital = client.post("/api/v1/customers", json={"name": _ZH_TEXT['TEXT_85DED9E803B8D55E']},
                               headers=admin).json()["data"]["id"]

        member = invite_member(client, admin, "nobody", [])

        def add(name: str, **extra) -> dict:
            r = client.post("/api/v1/customer-contacts", headers=admin,
                            json={"customer_id": hospital, "name": name, **extra})
            assert r.status_code == 201, r.text
            return r.json()["data"]

        yield {"client": client, "admin": admin, "member": member,
               "customer": hospital, "add": add}


def test_many_people_at_one_customer_and_everyone_reads(rolodex) -> None:
    rolodex["add"](_ZH_TEXT['TEXT_185D6F0188FE96A7'], title=_ZH_TEXT['TEXT_F3FC9DF74C281403'], phone="13800000001")
    rolodex["add"](_ZH_TEXT['TEXT_2BF61438CAE7EFAF'], title=_ZH_TEXT['TEXT_D15D1AF246AFF7F1'], phone="13800000002")
    rolodex["add"](_ZH_TEXT['TEXT_58412163FD36E4BA'], title=_ZH_TEXT['TEXT_506C068A2A1EB95A'], phone="13800000003", is_primary=True)

    listed = rolodex["client"].get("/api/v1/customer-contacts",
                                   params={"customer_id": rolodex["customer"]},
                                   headers=rolodex["member"])
    assert listed.status_code == 200, "the rolodex is master data — everyone reads it"
    rows = listed.json()["data"]
    assert len(rows) == 3
    assert rows[0]["name"] == _ZH_TEXT['TEXT_58412163FD36E4BA'] and rows[0]["is_primary"], \
        _ZH_TEXT['TEXT_7A33C493EE200B17']

    refused = rolodex["client"].post("/api/v1/customer-contacts", headers=rolodex["member"],
                                     json={"customer_id": rolodex["customer"], "name": _ZH_TEXT['TEXT_B150F2AD49D79B4E']})
    assert refused.status_code == 403, "writing the rolodex is catalog work"


def test_a_new_primary_demotes_the_old_in_the_same_write(rolodex) -> None:
    first = rolodex["add"](_ZH_TEXT['TEXT_A59B695412782D60'], is_primary=True)
    second = rolodex["add"](_ZH_TEXT['TEXT_FDCAD4420BE94DC7'], is_primary=True)
    assert second["is_primary"]

    old = rolodex["client"].get(f"/api/v1/customer-contacts/{first['id']}",
                                headers=rolodex["admin"]).json()["data"]
    assert old["is_primary"] is False, \
        "one question, one answer — the old primary steps down in the same write"

    third = rolodex["add"](_ZH_TEXT['TEXT_BAC6AB7A0C6F1D05'])
    promoted = rolodex["client"].patch(f"/api/v1/customer-contacts/{third['id']}",
                                       headers=rolodex["admin"], json={"is_primary": True})
    assert promoted.status_code == 200
    again = rolodex["client"].get(f"/api/v1/customer-contacts/{second['id']}",
                                  headers=rolodex["admin"]).json()["data"]
    assert again["is_primary"] is False


def test_the_same_phone_twice_is_a_duplicate_person(rolodex) -> None:
    kept = rolodex["add"](_ZH_TEXT['TEXT_185D6F0188FE96A7'], phone="13911112222")
    dup = rolodex["client"].post("/api/v1/customer-contacts", headers=rolodex["admin"],
                                 json={"customer_id": rolodex["customer"],
                                       "name": _ZH_TEXT['TEXT_0FBE44DF63BF1049'], "phone": "13911112222"})
    assert dup.status_code == 409, dup.text
    assert "duplicate person" in dup.json()["detail"]

    assert rolodex["client"].delete(f"/api/v1/customer-contacts/{kept['id']}",
                                    headers=rolodex["admin"]).status_code == 204
    revived = rolodex["client"].post("/api/v1/customer-contacts", headers=rolodex["admin"],
                                     json={"customer_id": rolodex["customer"],
                                           "name": _ZH_TEXT['TEXT_185D6F0188FE96A7'], "phone": "13911112222"})
    assert revived.status_code == 201, "archiving frees the slot — the person came back"

    other = rolodex["client"].post("/api/v1/customers", json={"name": _ZH_TEXT['TEXT_E77A169E0975EB30']},
                                   headers=rolodex["admin"]).json()["data"]["id"]
    elsewhere = rolodex["client"].post("/api/v1/customer-contacts", headers=rolodex["admin"],
                                       json={"customer_id": other, "name": _ZH_TEXT['TEXT_AD953DC9A2FB0243'],
                                             "phone": "13911112222"})
    assert elsewhere.status_code == 201, \
        "the dedup is per customer — one person may sit in two rolodexes"


def test_a_contact_belongs_to_a_real_customer_here(rolodex) -> None:
    ghost = rolodex["client"].post("/api/v1/customer-contacts", headers=rolodex["admin"],
                                   json={"customer_id": "00000000-0000-0000-0000-000000000000",
                                         "name": _ZH_TEXT['TEXT_90623098906CC8D8']})
    assert ghost.status_code == 404
