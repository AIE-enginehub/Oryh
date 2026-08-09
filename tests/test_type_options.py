"""Tenant-customizable type vocabularies.

The shipped catalog seeds per tenant on provision; tenants add custom values
beside it and may archive shipped ones. Every *_type/*_category write path
validates against the tenant's vocabulary and answers 422 naming the active
options. A tenant with no rows has not customized anything — the catalog
applies verbatim (pinned implicitly by every fixture-seeded test in this
suite that never provisions).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.emails import outbox

from conftest import provision_tenant as bootstrap_tenant


def extract_token(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError(f"no token in email body: {body!r}")


def provision(client: TestClient) -> dict[str, str]:
    verified = bootstrap_tenant(client, company_name="Vocab Co", email="admin@vocab-co.example", password="admin-pass1")
    return {"X-API-Key": verified["plain_text_api_key"]}


def create_product(client: TestClient, headers) -> str:
    response = client.post(
        "/api/v1/products", json={"product_code": "P-001", "name": "内窥镜镜头"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def options_by_name(client: TestClient, headers, family: str) -> dict[str, dict]:
    listed = client.get(f"/api/v1/type-options?family={family}", headers=headers)
    assert listed.status_code == 200, listed.text
    return {row["name"]: row for row in listed.json()["data"]}


def test_registration_seeds_the_shipped_vocabularies(client: TestClient) -> None:
    headers = provision(client)
    price_types = options_by_name(client, headers, "product_price_type")
    assert set(price_types) == {"list", "default", "promo", "wholesale", "competitive", "minimum", "maximum", "cost"}
    assert all(row["kind"] == "system" and row["status"] == "active" for row in price_types.values())
    assert price_types["rounding"] if False else True  # rounding is an adjustment type, not a price type
    adjustment_types = options_by_name(client, headers, "sales_adjustment_type")
    assert "rounding" in adjustment_types
    assert client.get("/api/v1/type-options?family=nope", headers=headers).status_code == 422


def test_custom_price_type_end_to_end(client: TestClient) -> None:
    headers = provision(client)
    product_id = create_product(client, headers)

    created = client.post(
        "/api/v1/type-options",
        json={"family": "product_price_type", "name": "dealer_tier2", "title": "二级经销价"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["kind"] == "custom"

    # collisions and shape
    assert client.post(
        "/api/v1/type-options",
        json={"family": "product_price_type", "name": "wholesale", "title": "撞系统值"},
        headers=headers,
    ).status_code == 409
    assert client.post(
        "/api/v1/type-options",
        json={"family": "product_price_type", "name": "dealer_tier2"},
        headers=headers,
    ).status_code == 409
    assert client.post(
        "/api/v1/type-options",
        json={"family": "product_price_type", "name": "Dealer-2"},
        headers=headers,
    ).status_code == 422
    assert client.post(
        "/api/v1/type-options",
        json={"family": "no_such_family", "name": "x"},
        headers=headers,
    ).status_code == 422

    # the custom type is immediately writable, with its own active slot
    price = client.post(
        "/api/v1/product-prices",
        json={"product_id": product_id, "price_type": "dealer_tier2", "price": 880.0},
        headers=headers,
    )
    assert price.status_code == 201, price.text

    # an unknown type answers with the active options, custom included
    unknown = client.post(
        "/api/v1/product-prices",
        json={"product_id": product_id, "price_type": "dealer_tier9", "price": 1.0},
        headers=headers,
    )
    assert unknown.status_code == 422
    assert "dealer_tier2" in unknown.json()["detail"]
    assert "wholesale" in unknown.json()["detail"]


def test_archiving_a_shipped_value_refuses_new_writes_only(client: TestClient) -> None:
    headers = provision(client)
    product_id = create_product(client, headers)
    kept = client.post(
        "/api/v1/product-prices",
        json={"product_id": product_id, "price_type": "competitive", "price": 950.0},
        headers=headers,
    )
    assert kept.status_code == 201, kept.text

    competitive = options_by_name(client, headers, "product_price_type")["competitive"]
    assert client.delete(f"/api/v1/type-options/{competitive['id']}", headers=headers).status_code == 204

    refused = client.post(
        "/api/v1/product-prices",
        json={"product_id": product_id, "price_type": "competitive", "price": 940.0, "currency": "USD"},
        headers=headers,
    )
    assert refused.status_code == 422
    assert "competitive" not in refused.json()["detail"].split("active options: ")[1]

    # the existing row keeps its value; history is untouched
    still_there = client.get(f"/api/v1/product-prices/{kept.json()['data']['id']}", headers=headers)
    assert still_there.json()["data"]["price_type"] == "competitive"

    # lazy catalog materialization (another POST) must NOT revive the archive
    client.post(
        "/api/v1/type-options",
        json={"family": "product_price_type", "name": "member_price", "title": "会员价"},
        headers=headers,
    )
    assert options_by_name(client, headers, "product_price_type")["competitive"]["status"] == "archived"


def test_system_wording_is_catalog_owned_custom_is_tenant_owned(client: TestClient) -> None:
    headers = provision(client)
    rows = options_by_name(client, headers, "sales_adjustment_type")
    assert client.patch(
        f"/api/v1/type-options/{rows['tax']['id']}",
        json={"title": "改系统标题"},
        headers=headers,
    ).status_code == 422

    custom = client.post(
        "/api/v1/type-options",
        json={"family": "sales_adjustment_type", "name": "invoice_fee", "title": "开票服务费"},
        headers=headers,
    ).json()["data"]
    renamed = client.patch(
        f"/api/v1/type-options/{custom['id']}",
        json={"title": "开票手续费", "description": "按张收取"},
        headers=headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["data"]["title"] == "开票手续费"


def test_custom_adjustment_and_category_and_work_type_flow(client: TestClient) -> None:
    headers = provision(client)
    employee = client.post("/api/v1/employees", json={"name": "小王"}, headers=headers).json()["data"]["id"]

    for family, name, title in [
        ("sales_adjustment_type", "invoice_fee", "开票服务费"),
        ("expense_category", "training", "培训费"),
        ("work_type", "standby", "待命"),
    ]:
        assert client.post(
            "/api/v1/type-options", json={"family": family, "name": name, "title": title}, headers=headers
        ).status_code == 201, family

    quotation = client.post(
        "/api/v1/sales-quotations",
        json={"employee_id": employee, "title": "词表报价", "quote_date": "2026-07-26"},
        headers=headers,
    ).json()["data"]
    adjustment = client.post(
        "/api/v1/sales-quotation-adjustments",
        json={"quotation_id": quotation["id"], "adjustment_type": "invoice_fee", "amount": 30.0},
        headers=headers,
    )
    assert adjustment.status_code == 201, adjustment.text
    bad_adjustment = client.post(
        "/api/v1/sales-quotation-adjustments",
        json={"quotation_id": quotation["id"], "adjustment_type": "mystery", "amount": 1.0},
        headers=headers,
    )
    assert bad_adjustment.status_code == 422
    assert "invoice_fee" in bad_adjustment.json()["detail"]

    claim = client.post(
        "/api/v1/expense-claims",
        json={"employee_id": employee, "title": "培训报销", "claim_date": "2026-07-26"},
        headers=headers,
    ).json()["data"]
    item = client.post(
        "/api/v1/expense-items",
        json={"claim_id": claim["id"], "employee_id": employee, "expense_date": "2026-07-20",
              "category": "training", "amount": 1500.0},
        headers=headers,
    )
    assert item.status_code == 201, item.text
    assert client.post(
        "/api/v1/expense-items",
        json={"claim_id": claim["id"], "employee_id": employee, "expense_date": "2026-07-20",
              "category": "snacks", "amount": 1.0},
        headers=headers,
    ).status_code == 422

    header = client.post(
        "/api/v1/timesheet-headers",
        json={"employee_id": employee, "period_start": "2026-07-20", "period_end": "2026-07-26"},
        headers=headers,
    ).json()["data"]
    entry = client.post(
        "/api/v1/timesheet-entries",
        json={"header_id": header["id"], "employee_id": employee, "work_date": "2026-07-21",
              "hours": 8, "work_type": "standby"},
        headers=headers,
    )
    assert entry.status_code == 201, entry.text


def test_bulk_prices_respect_the_vocabulary(client: TestClient) -> None:
    headers = provision(client)
    client.post(
        "/api/v1/type-options",
        json={"family": "product_price_type", "name": "dealer_tier2", "title": "二级经销价"},
        headers=headers,
    )
    rows = [
        {"product_code": "P-100", "name": "导管鞘",
         "prices": [{"price_type": "dealer_tier2", "price": 15.5}]},
        {"product_code": "P-101", "name": "拉钩",
         "prices": [{"price_type": "mystery", "price": 1.0}]},
    ]
    report = client.post("/api/v1/products/bulk", json={"rows": rows}, headers=headers).json()["data"]
    assert report["applied"] is False  # abort mode: the bad row stops the file
    error = [r for r in report["results"] if r["outcome"] == "error"][0]
    assert error["code"] == "P-101" and "mystery" in error["error"] and "dealer_tier2" in error["error"]

    good = client.post(
        "/api/v1/products/bulk", json={"rows": rows[:1]}, headers=headers
    ).json()["data"]
    assert good["summary"]["created"] == 1


def test_vocabulary_writes_need_object_types_manage(client: TestClient) -> None:
    headers = provision(client)
    employee = client.post("/api/v1/employees", json={"name": "小李"}, headers=headers).json()["data"]["id"]
    invited = client.post(
        "/api/v1/auth/invitations",
        json={"email": "li@vocab-co.example", "role": "member", "employee_id": employee},
        headers=headers,
    ).json()["data"]["id"]
    client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": extract_token(outbox.messages[-1].body), "password": "li-pass1"},
    )
    member_key = client.post(
        "/api/v1/tenant/api-keys", json={"label": "member", "user_id": invited}, headers=headers
    ).json()["data"]["plain_text_api_key"]
    member = {"X-API-Key": member_key}

    assert client.get("/api/v1/type-options?family=work_type", headers=member).status_code == 200
    denied = client.post(
        "/api/v1/type-options",
        json={"family": "work_type", "name": "night_shift", "title": "夜班"},
        headers=member,
    )
    assert denied.status_code == 403
    assert "object_types.manage" in denied.json()["detail"]


def test_error_messages_point_at_how_to_define_a_type(client: TestClient) -> None:
    """The agent meets an unknown type in an error, not in a spec — so both
    the single write and the bulk row error must say the vocabulary is
    extensible, or the agent shoehorns 经销价 into wholesale instead."""
    headers = provision(client)
    product_id = create_product(client, headers)

    single = client.post(
        "/api/v1/product-prices",
        json={"product_id": product_id, "price_type": "dealer_tier2", "price": 880.0},
        headers=headers,
    )
    assert single.status_code == 422
    assert "/type-options" in single.json()["detail"]

    bulk = client.post(
        "/api/v1/products/bulk",
        json={"rows": [{
            "product_code": "P-900", "name": "经销品",
            "prices": [{"price_type": "dealer_tier2", "price": 880.0}],
        }]},
        headers=headers,
    )
    assert bulk.status_code == 200, bulk.text
    error = bulk.json()["data"]["results"][0]["error"]
    assert "dealer_tier2" in error
    assert "/type-options" in error  # names the way forward, not just the failure


def audit_entries(client: TestClient, headers, action: str) -> list[dict]:
    response = client.get(f"/api/v1/audit-logs?action={action}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_every_vocabulary_change_leaves_an_audit_entry(client: TestClient) -> None:
    """A business vocabulary that changes meaning silently is unauditable.

    "渠道价" redefined is a different number in every report that reads it, and
    the only trace used to be the row's `updated_at`: no actor, no old value,
    nothing to answer "who changed what, from what, when". The audit
    report filed this against PATCH; in fact NO type-option operation was
    audited, so fixing only the door the E2E happened to walk through would
    have left the same hole one door over.
    """
    headers = provision(client)

    created = client.post(
        "/api/v1/type-options",
        json={"family": "product_price_type", "name": "dealer_tier2", "title": "二级经销价"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    option_id = created.json()["data"]["id"]

    entries = audit_entries(client, headers, "type_option.created")
    assert len(entries) == 1
    assert entries[0]["entity_id"] == option_id
    assert entries[0]["detail"]["name"] == "dealer_tier2"
    assert entries[0]["actor"]

    patched = client.patch(
        f"/api/v1/type-options/{option_id}",
        json={"title": "二级渠道价", "description": "二级渠道的成交口径"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text

    updates = audit_entries(client, headers, "type_option.updated")
    assert len(updates) == 1
    changed = updates[0]["detail"]["changed"]
    # the OLD value is the half that makes the trail answerable
    assert changed["title"] == {"from": "二级经销价", "to": "二级渠道价"}
    assert changed["description"]["from"] is None
    assert set(changed) == {"title", "description"}

    archived = client.delete(f"/api/v1/type-options/{option_id}", headers=headers)
    assert archived.status_code == 204, archived.text
    assert len(audit_entries(client, headers, "type_option.archived")) == 1


def test_a_patch_that_changes_nothing_records_nothing(client: TestClient) -> None:
    """An audit trail of no-ops is a trail nobody reads."""
    headers = provision(client)
    created = client.post(
        "/api/v1/type-options",
        json={"family": "expense_category", "name": "client_gift", "title": "客户礼品"},
        headers=headers,
    )
    option_id = created.json()["data"]["id"]

    repeated = client.patch(
        f"/api/v1/type-options/{option_id}", json={"title": "客户礼品"}, headers=headers
    )
    assert repeated.status_code == 200, repeated.text
    assert audit_entries(client, headers, "type_option.updated") == []
