"""A person hands out only what they hold.

A tenant made an order-and-stock administrator role, gave it `users.manage`
so that desk could invite warehouse staff, and found it could invite an
administrator (2026-10-14). `users.manage` is the verb for inviting and
shaping roles; it is not a ladder. Only the system administrator role and
the tenant's own service key may assign or build a role wider than
themselves.
"""

from __future__ import annotations

import pytest

from conftest import invite_member, make_stack, provision_tenant

DESK = ["users.manage", "inventory.manage", "order.submit_own"]


@pytest.fixture()
def shop():
    with make_stack([]) as (client, engine):
        t = provision_tenant(client, company_name="Ladder Co", email="admin@ladder.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        desk = dict(invite_member(client, admin, "stock_desk", DESK, email="desk@ladder.example", employee="desk"))
        yield {"client": client, "admin": admin, "desk": desk}


def _invite(c, headers, role, email):
    return c.post("/api/v1/auth/invitations", headers=headers, json={"email": email, "name": "x", "role": role})


def test_a_users_manage_holder_cannot_invite_an_administrator(shop) -> None:
    c, desk = shop["client"], shop["desk"]
    r = _invite(c, desk, "admin", "new-admin@ladder.example")
    assert r.status_code == 403, r.text
    assert "grants what you do not hold" in r.text
    assert _invite(c, desk, "stock_desk", "colleague@ladder.example").status_code == 201, "its own role is within reach"
    assert _invite(c, desk, "member", "member@ladder.example").status_code == 403, \
        "member carries grants the desk lacks (its own documents), so even member is wider"


def test_a_users_manage_holder_cannot_build_or_widen_a_role_past_itself(shop) -> None:
    c, desk, admin = shop["client"], shop["desk"], shop["admin"]
    wider = c.post("/api/v1/roles", headers=desk, json={"name": "keys_desk", "title": "Keys", "permissions": ["keys.manage"]})
    assert wider.status_code == 403 and "keys.manage" in wider.text
    narrower = c.post("/api/v1/roles", headers=desk, json={"name": "picker", "title": "Picker", "permissions": ["inventory.manage"]})
    assert narrower.status_code == 201, narrower.text
    widen = c.patch("/api/v1/roles/stock_desk", headers=desk, json={"permissions": DESK + ["keys.manage"]})
    assert widen.status_code == 403, "it cannot grant itself what it lacks"
    assert c.patch("/api/v1/roles/admin", headers=desk, json={"description": "x"}).status_code == 403, "the admin role is the administrator's"
    assert c.patch("/api/v1/roles/stock_desk", headers=admin, json={"permissions": DESK + ["keys.manage"]}).status_code == 200, \
        "the administrator still may"


def test_moving_a_person_into_admin_is_the_same_grant(shop) -> None:
    c, desk, admin = shop["client"], shop["desk"], shop["admin"]
    colleague = _invite(c, admin, "stock_desk", "colleague@ladder.example").json()["data"]
    users = c.get("/api/v1/auth/users", headers=admin, params={"role": "stock_desk"}).json()["data"]
    target = next(u for u in users if u["email"] == "colleague@ladder.example")
    moved = c.patch(f"/api/v1/auth/users/{target['id']}", headers=desk, json={"role": "admin"})
    assert moved.status_code == 403, moved.text
    assert c.patch(f"/api/v1/auth/users/{target['id']}", headers=admin, json={"role": "admin"}).status_code == 200
