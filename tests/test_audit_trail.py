"""Master data changed through an agent must be traceable to whoever did it.

The reported defect: an agent adds or edits master data and nothing records it.
It was wider than master data — 115 of 195 write endpoints recorded nothing,
because the hand-written trail covered the flow (submissions, approvals, status
changes) and not the content. These tests pin the mechanism that closes it, and
they are written against the HTTP surface an agent actually uses, because a
listener that works in a unit test and not behind the API would be no answer at
all.
"""

from __future__ import annotations

import pytest

from conftest import provision_tenant


@pytest.fixture()
def service_headers(client) -> dict:
    tenant = provision_tenant(client, company_name="Trail Co", email="admin@trail.example")
    return {"X-API-Key": tenant["plain_text_api_key"]}


def _audit(client, headers, **params) -> list[dict]:
    response = client.get("/api/v1/audit-logs", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_creating_master_data_through_the_api_is_recorded(client, service_headers):
    response = client.post(
        "/api/v1/customers",
        headers=service_headers,
        json={"name": "Traceable Trading", "customer_kind": "company"},
    )
    assert response.status_code == 201, response.text
    customer_id = response.json()["data"]["id"]

    entries = _audit(client, service_headers, entity_type="customer", entity_id=customer_id)
    assert entries, "creating a customer left no trail — the reported defect"
    created = [entry for entry in entries if entry["action"] == "customer.created"]
    assert len(created) == 1, [entry["action"] for entry in entries]
    assert created[0]["detail"]["fields"]["name"] == "Traceable Trading"


def test_editing_master_data_records_before_and_after(client, service_headers):
    created = client.post(
        "/api/v1/products",
        headers=service_headers,
        json={"name": "Bench Lamp", "unit": "件"},
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["data"]["id"]

    edited = client.patch(
        f"/api/v1/products/{product_id}",
        headers=service_headers,
        json={"name": "Bench Lamp II"},
    )
    assert edited.status_code == 200, edited.text

    entries = _audit(client, service_headers, entity_type="product", entity_id=product_id)
    updates = [entry for entry in entries if entry["action"] == "product.updated"]
    assert len(updates) == 1, [entry["action"] for entry in entries]
    change = updates[0]["detail"]["changes"]["name"]
    # The delta, not just the result: finding F25 settled that a log carrying
    # only the post-change value cannot answer what was taken away.
    assert change == {"before": "Bench Lamp", "after": "Bench Lamp II"}


def test_the_entry_names_the_credential_that_made_the_change(client, service_headers):
    response = client.post(
        "/api/v1/vendors",
        headers=service_headers,
        json={"name": "Attributed Supply"},
    )
    assert response.status_code == 201, response.text
    vendor_id = response.json()["data"]["id"]

    entry = _audit(client, service_headers, entity_type="vendor", entity_id=vendor_id)[0]
    # Server-side attribution: decided by the credential, never by what the
    # caller says about itself.
    assert entry["actor"] and entry["actor"].startswith(("key:", "user:")), entry["actor"]


def test_a_price_change_is_answerable(client, service_headers):
    """The question the report was really about: who changed this, from what."""
    product = client.post(
        "/api/v1/products", headers=service_headers, json={"name": "Priced Thing", "unit": "件"}
    )
    product_id = product.json()["data"]["id"]
    price = client.post(
        "/api/v1/product-prices",
        headers=service_headers,
        json={"product_id": product_id, "price_type": "list", "price": 100.00},
    )
    assert price.status_code == 201, price.text
    price_id = price.json()["data"]["id"]

    bumped = client.patch(
        f"/api/v1/product-prices/{price_id}",
        headers=service_headers,
        json={"price": 125.00},
    )
    assert bumped.status_code == 200, bumped.text

    updates = [
        entry
        for entry in _audit(
            client, service_headers, entity_type="product_price", entity_id=price_id
        )
        if entry["action"] == "product_price.updated"
    ]
    assert len(updates) == 1
    change = updates[0]["detail"]["changes"]["price"]
    # Both sides in the same units. `before` comes from the database with the
    # column's scale; `after` is the request's own number, which has not been
    # near the database — left alone it reads `100.00 → 125.5` on a change to
    # 125.50, and a reader cannot tell that from a lost digit.
    assert change == {"before": "100.00", "after": "125.00"}, change


def test_a_secret_is_recorded_as_changed_but_never_copied(client, service_headers):
    """A trail must not become the second place a credential hash lives."""
    response = client.post(
        "/api/v1/tenant/api-keys", headers=service_headers, json={"label": "trail-probe"}
    )
    assert response.status_code == 201, response.text
    key_id = response.json()["data"]["api_key"]["id"]

    entries = _audit(client, service_headers, entity_type="api_key", entity_id=key_id)
    assert entries, "issuing a credential left no trail"
    fields = entries[0]["detail"]["fields"]
    assert "key_hash" in fields, "the change itself should be recorded"
    assert fields["key_hash"] == "«redacted»", fields["key_hash"]
    serialized = str(entries[0]["detail"])
    assert "$argon2" not in serialized and "$2b$" not in serialized


def test_reads_write_nothing(client, service_headers):
    """A GET must not grow the trail — otherwise it drowns in its own noise."""
    before = len(_audit(client, service_headers, limit=200))
    for _ in range(3):
        assert client.get("/api/v1/customers", headers=service_headers).status_code == 200
    after = len(_audit(client, service_headers, limit=200))
    assert after == before, f"reads added {after - before} audit rows"


def test_provisioning_the_catalogue_does_not_flood_the_trail(client, service_headers):
    """A new workspace opens with its own history, not the catalogue's.

    Provisioning writes 33 product skills, 111 type options, 40 capabilities and
    the system roles. Recorded, the tenant's first real change arrives on page
    three. Found on a running deployment, where a workspace nobody had used held
    200 entries — the suppression was on the aggregate `provision_tenant_defaults`
    while `scripts/sync_tenant_defaults.py` calls the five underneath it directly.
    """
    entries = _audit(client, service_headers, limit=200)
    assert len(entries) < 20, f"a fresh workspace opened with {len(entries)} entries"
    catalogue = [
        entry
        for entry in entries
        if entry["entity_type"] in ("type_option", "capability", "tenant_skill", "role")
    ]
    assert not catalogue, f"the shipped catalogue reached the trail: {catalogue[:3]}"


def test_a_tenants_own_edit_to_the_catalogue_is_still_recorded(client, service_headers):
    """Suppression covers provisioning, not the tenant. What they do TO the
    catalogue is their decision and stays traceable."""
    response = client.post(
        "/api/v1/type-options",
        headers=service_headers,
        json={"family": "product_price_type", "name": "partner", "title": "Partner price"},
    )
    assert response.status_code == 201, response.text
    option_id = response.json()["data"]["id"]
    entries = _audit(client, service_headers, entity_type="type_option", entity_id=option_id)
    assert entries, "a tenant's own vocabulary entry left no trail"


@pytest.mark.parametrize(
    "table",
    ["audit_logs", "user_sessions", "device_authorizations"],
    ids=["no recursion", "session churn", "device churn"],
)
def test_the_excluded_tables_are_excluded_on_purpose(table):
    # Guard the exclusions: dropping one silently would either recurse forever
    # or bury the business trail under machinery.
    from app.services.audit_trail import NEVER_AUDITED

    assert table in NEVER_AUDITED
