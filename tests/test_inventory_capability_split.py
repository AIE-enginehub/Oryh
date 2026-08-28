"""`inventory.manage` is split out of `master_data.manage`, and the split is real.

A warehouse keeper is not a catalog administrator. Under one capability a
warehouse role held every product, vendor and customer record or nothing at
all; the stock ledger — receiving, issuing, stock-takes, the informal
movements nobody has a document for — is a different desk's daily work.

Two halves are pinned. The split: a key holding only the new capability can
post movements and cannot touch products, and a key holding only the old one
can touch products and can no longer post movements — without the second
assertion the "split" would be an alias. And the continuity: the seeded
warehouse desk holds the capability, and the skill that teaches the ledger is
gated on it, so a keeper receives the instructions the capability makes
usable.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app.core.permissions import SYSTEM_CAPABILITY_NAMES
from app.services.emails import outbox

from conftest import make_client, provision_tenant

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture()
def desks():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Split Co", email="admin@split.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        seq = {"n": 0}

        def key_holding(*permissions: str) -> dict:
            seq["n"] += 1
            role = f"desk{seq['n']}"
            client.post("/api/v1/roles", json={"name": role, "permissions": list(permissions)},
                        headers=admin)
            uid = client.post("/api/v1/auth/invitations",
                              json={"email": f"{role}@split.example", "role": role},
                              headers=admin).json()["data"]["id"]
            token = next(l.rsplit("token=", 1)[1].strip()
                         for l in outbox.messages[-1].body.splitlines() if "token=" in l)
            client.post("/api/v1/auth/invitations/accept",
                        json={"token": token, "password": "invitee-pass1"})
            plain = client.post("/api/v1/tenant/api-keys", json={"label": role, "user_id": uid},
                                headers=admin).json()["data"]["plain_text_api_key"]
            return {"X-API-Key": plain}

        product = client.post("/api/v1/products", json={"name": "Widget", "product_code": "W-1"},
                              headers=admin).json()["data"]["id"]
        item = client.post("/api/v1/inventory-items",
                           json={"product_id": product, "facility": "main", "initial_quantity": 10},
                           headers=admin).json()["data"]["id"]
        yield {"client": client, "key_holding": key_holding, "product": product, "item": item}


def test_the_capability_exists() -> None:
    assert "inventory.manage" in SYSTEM_CAPABILITY_NAMES


def test_a_keeper_moves_stock_and_cannot_touch_the_catalog(desks) -> None:
    keeper = desks["key_holding"]("inventory.manage")
    moved = desks["client"].post("/api/v1/inventory-item-details", headers=keeper, json={
        "inventory_item_id": desks["item"], "quantity_on_hand_diff": -1, "reason": "issued",
        "description": "one out"})
    assert moved.status_code == 201, moved.text

    catalog = desks["client"].post("/api/v1/products", headers=keeper,
                                   json={"name": "Gadget", "product_code": "G-1"})
    assert catalog.status_code == 403, "inventory.manage must not reach the catalog"


def test_a_catalog_administrator_no_longer_moves_stock(desks) -> None:
    """Without this the split is an alias. master_data.manage was the gate
    on the ledger; it is not any more, and migration 0063 is what keeps the
    roles that relied on it working — by granting them the new capability,
    not by keeping the old one honoured."""
    admin_only = desks["key_holding"]("master_data.manage")
    catalog = desks["client"].post("/api/v1/products", headers=admin_only,
                                   json={"name": "Gadget", "product_code": "G-2"})
    assert catalog.status_code == 201, catalog.text

    moved = desks["client"].post("/api/v1/inventory-item-details", headers=admin_only, json={
        "inventory_item_id": desks["item"], "quantity_on_hand_diff": -1, "reason": "issued"})
    assert moved.status_code == 403, moved.text
    assert "inventory.manage" in moved.json()["detail"]


def test_every_inventory_write_is_on_the_new_gate(desks) -> None:
    """The four writes and the archive, named — a fifth inventory write added
    on the old gate would reopen the catalog-or-nothing problem for one route
    and nobody would notice from the others passing."""
    admin_only = desks["key_holding"]("master_data.manage")
    c = desks["client"]
    refused = {
        "POST /inventory-items": c.post("/api/v1/inventory-items", headers=admin_only,
                                        json={"product_id": desks["product"], "facility": "b"}),
        "PATCH /inventory-items/{id}": c.patch(f"/api/v1/inventory-items/{desks['item']}",
                                               headers=admin_only, json={"bin_number": "A1"}),
        "DELETE /inventory-items/{id}": c.delete(f"/api/v1/inventory-items/{desks['item']}",
                                                 headers=admin_only),
        # a VALID body, or pydantic answers 422 before the handler's gate runs
        # and the probe proves nothing — the same lesson the member-surface
        # probe learned
        "POST /inventory-items/bulk": c.post("/api/v1/inventory-items/bulk", headers=admin_only,
                                             json={"rows": [{"product_code": "W-1",
                                                             "facility": "main",
                                                             "quantity": 5}],
                                                   "dry_run": True}),
    }
    still_open = {route: r.status_code for route, r in refused.items() if r.status_code != 403}
    assert not still_open, f"inventory writes master_data.manage can still reach: {still_open}"


def test_the_seeded_warehouse_desk_holds_it() -> None:
    """The lesson of 0060: a capability announces itself to nobody. The demo
    keeper must hold it, or the first person to try the warehouse arc finds
    a 403 where the product claims a feature."""
    seed_path = ROOT / "scripts/seed_demo.py"
    if not seed_path.is_file():
        pytest.skip("open-core tree ships no demo seed — the pin lives with the seed")
    seed = seed_path.read_text(encoding="utf-8")
    warehouse = seed[seed.index('b.add_role("warehouse"'):]
    warehouse = warehouse[: warehouse.index("])")]
    assert "inventory.manage" in warehouse


def test_the_ledger_skill_is_gated_on_it() -> None:
    """The instructions travel with the capability. A keeper holding
    inventory.manage and not master_data.manage must still receive the skill
    that teaches the ledger — including the doctrine about recording reality."""
    front = (ROOT / "skills/oryh-inventory/SKILL.md").read_text(encoding="utf-8")
    gate = re.search(r"^required_capability:\s*(\S+)", front, re.M)
    assert gate and gate.group(1) == "inventory.manage", gate and gate.group(0)
