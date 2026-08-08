"""Bulk master-data upsert — the spreadsheet-import path.

The behaviours worth pinning are the ones a person re-importing a corrected
price list depends on: the code is the identity, running twice changes nothing
the second time, a preview equals the write it previews, and a partial
spreadsheet never blanks out fields it simply does not carry.
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
    verified = bootstrap_tenant(client, company_name="Import Co", email="admin@import-co.example", password="admin-pass1")
    return {"X-API-Key": verified["plain_text_api_key"]}


def upsert(client: TestClient, headers, rows, **options) -> dict:
    response = client.post(
        "/api/v1/products/bulk", json={"rows": rows, **options}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def list_products(client: TestClient, headers) -> list[dict]:
    return client.get("/api/v1/products?size=200", headers=headers).json()["data"]


def test_bulk_import_creates_then_upserts_idempotently(client: TestClient) -> None:
    """The second run of the same spreadsheet is a no-op, not a duplicate set —
    which is what makes "just re-run it after fixing a row" safe advice."""
    headers = provision(client)
    rows = [
        {"product_code": "P-001", "name": "内窥镜镜头", "unit": "个", "list_price": 1200.00},
        {"product_code": "P-002", "name": "光源模块", "unit": "台", "list_price": 8600.50},
    ]

    first = upsert(client, headers, rows)
    assert first["summary"] == {"total": 2, "created": 2, "updated": 0, "unchanged": 0, "failed": 0}
    assert first["applied"] is True

    second = upsert(client, headers, rows)
    assert second["summary"]["created"] == 0
    assert second["summary"]["unchanged"] == 2
    assert len(list_products(client, headers)) == 2

    # a changed price updates in place and names the field that moved
    rows[1]["list_price"] = 7900.00
    third = upsert(client, headers, rows)
    assert third["summary"]["updated"] == 1
    assert third["summary"]["unchanged"] == 1
    changed = [r for r in third["results"] if r["outcome"] == "updated"][0]
    assert changed["changed"] == ["list_price"]
    assert len(list_products(client, headers)) == 2


def test_partial_spreadsheet_does_not_blank_curated_fields(client: TestClient) -> None:
    """A price-only sheet must not erase the spec someone curated in the
    console. Absent is not empty."""
    headers = provision(client)
    upsert(
        client,
        headers,
        [{"product_code": "P-100", "name": "手术台", "spec": "标准型 2.1m", "unit": "台", "list_price": 30000}],
    )

    upsert(client, headers, [{"product_code": "P-100", "name": "手术台", "list_price": 27500}])

    product = [p for p in list_products(client, headers) if p["product_code"] == "P-100"][0]
    assert product["list_price"] == 27500
    assert product["spec"] == "标准型 2.1m"
    assert product["unit"] == "台"


def test_dry_run_previews_exactly_and_writes_nothing(client: TestClient) -> None:
    """The preview is produced by the write path itself, so what the agent
    shows the person cannot drift from what committing would do."""
    headers = provision(client)
    upsert(client, headers, [{"product_code": "P-200", "name": "旧名", "list_price": 100}])

    preview = upsert(
        client,
        headers,
        [
            {"product_code": "P-200", "name": "新名", "list_price": 150},
            {"product_code": "P-201", "name": "新产品", "list_price": 90},
        ],
        dry_run=True,
    )
    assert preview["dry_run"] is True
    assert preview["applied"] is False
    assert preview["summary"]["created"] == 1
    assert preview["summary"]["updated"] == 1

    # nothing moved
    products = list_products(client, headers)
    assert len(products) == 1
    assert products[0]["name"] == "旧名"

    # and committing for real produces the same counts the preview promised
    real = upsert(
        client,
        headers,
        [
            {"product_code": "P-200", "name": "新名", "list_price": 150},
            {"product_code": "P-201", "name": "新产品", "list_price": 90},
        ],
    )
    assert real["summary"]["created"] == preview["summary"]["created"]
    assert real["summary"]["updated"] == preview["summary"]["updated"]


def test_blank_code_is_rejected_and_never_invented(client: TestClient) -> None:
    headers = provision(client)
    response = client.post(
        "/api/v1/products/bulk",
        json={"rows": [{"product_code": "   ", "name": "无编码"}]},
        headers=headers,
    )
    # min_length=1 catches an empty string at the schema; whitespace-only is
    # caught by the service after trimming. Either way it never becomes a row.
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        data = response.json()["data"]
        assert data["applied"] is False
        assert data["results"][0]["outcome"] == "error"
    assert list_products(client, headers) == []


def test_duplicate_code_within_one_batch_is_an_error(client: TestClient) -> None:
    """Two rows claiming one code is a defect in the sheet. Picking a winner
    would apply a value nobody chose."""
    headers = provision(client)
    data = upsert(
        client,
        headers,
        [
            {"product_code": "P-300", "name": "第一行", "list_price": 10},
            {"product_code": "P-300", "name": "第二行", "list_price": 20},
        ],
    )
    assert data["applied"] is False
    assert data["summary"]["failed"] == 1
    error = [r for r in data["results"] if r["outcome"] == "error"][0]
    assert error["index"] == 1
    assert "duplicate" in error["error"]
    assert list_products(client, headers) == []


def test_on_error_abort_writes_nothing_while_skip_imports_the_rest(client: TestClient) -> None:
    headers = provision(client)
    rows = [
        {"product_code": "P-400", "name": "好行一"},
        {"product_code": "P-400", "name": "重复行"},
        {"product_code": "P-401", "name": "好行二"},
    ]

    aborted = upsert(client, headers, rows)
    assert aborted["applied"] is False
    assert list_products(client, headers) == []

    skipped = upsert(client, headers, rows, on_error="skip")
    assert skipped["applied"] is True
    assert skipped["summary"]["created"] == 2
    assert skipped["summary"]["failed"] == 1
    assert {p["product_code"] for p in list_products(client, headers)} == {"P-400", "P-401"}


def test_code_is_trimmed_so_stray_whitespace_is_not_a_second_product(client: TestClient) -> None:
    headers = provision(client)
    upsert(client, headers, [{"product_code": "P-500", "name": "产品"}])
    again = upsert(client, headers, [{"product_code": "  P-500  ", "name": "产品"}])
    assert again["summary"]["unchanged"] == 1
    assert len(list_products(client, headers)) == 1


def test_reimporting_an_archived_code_revives_it(client: TestClient) -> None:
    """Archived rows keep their code, so a re-import updates the original
    instead of leaving a second product beside it."""
    headers = provision(client)
    upsert(client, headers, [{"product_code": "P-600", "name": "停用品"}])
    product_id = list_products(client, headers)[0]["id"]
    assert client.delete(f"/api/v1/products/{product_id}", headers=headers).status_code == 204

    data = upsert(client, headers, [{"product_code": "P-600", "name": "复活品", "status": "active"}])
    assert data["summary"]["updated"] == 1
    products = list_products(client, headers)
    assert len(products) == 1
    assert products[0]["id"] == product_id
    assert products[0]["status"] == "active"


def test_bulk_import_requires_master_data_manage(client: TestClient) -> None:
    headers = provision(client)
    client.post(
        "/api/v1/roles",
        json={"name": "reader", "permissions": ["timesheet.submit_own"]},
        headers=headers,
    )
    invited = client.post(
        "/api/v1/auth/invitations",
        json={"email": "reader@import-co.example", "role": "reader"},
        headers=headers,
    )
    user_id = invited.json()["data"]["id"]
    client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": extract_token(outbox.messages[-1].body), "password": "reader-pass1"},
    )
    key = client.post(
        "/api/v1/tenant/api-keys", json={"label": "r", "user_id": user_id}, headers=headers
    ).json()["data"]["plain_text_api_key"]

    denied = client.post(
        "/api/v1/products/bulk",
        json={"rows": [{"product_code": "X-1", "name": "越权"}]},
        headers={"X-API-Key": key},
    )
    assert denied.status_code == 403


def test_vendors_and_customers_share_the_same_contract(client: TestClient) -> None:
    headers = provision(client)

    vendors = client.post(
        "/api/v1/vendors/bulk",
        json={
            "rows": [
                {"vendor_code": "V-001", "name": "华东医疗器械", "tax_id": "91310000MA1K3"},
                {"vendor_code": "V-002", "name": "南方光学"},
            ]
        },
        headers=headers,
    )
    assert vendors.status_code == 200, vendors.text
    assert vendors.json()["data"]["summary"]["created"] == 2

    customers = client.post(
        "/api/v1/customers/bulk",
        json={
            "rows": [
                {"customer_code": "C-001", "name": "市第一医院", "address": "上海市黄浦区"},
            ],
            "dry_run": True,
        },
        headers=headers,
    )
    assert customers.status_code == 200, customers.text
    assert customers.json()["data"]["applied"] is False
    assert client.get("/api/v1/customers", headers=headers).json()["data"] == []


def test_single_create_reports_a_duplicate_code_as_conflict(client: TestClient) -> None:
    """The unique index must surface as a 409 the caller can act on, never as
    an unhandled integrity error."""
    headers = provision(client)
    upsert(client, headers, [{"product_code": "P-700", "name": "已存在"}])

    clash = client.post(
        "/api/v1/products", json={"name": "重复编码", "product_code": "P-700"}, headers=headers
    )
    assert clash.status_code == 409, clash.text
    assert "P-700" in clash.json()["detail"]

    other = client.post(
        "/api/v1/products", json={"name": "另一个", "product_code": "P-701"}, headers=headers
    )
    assert other.status_code == 201
    rename = client.patch(
        f"/api/v1/products/{other.json()['data']['id']}",
        json={"product_code": "P-700"},
        headers=headers,
    )
    assert rename.status_code == 409


def test_import_is_audited_once_with_a_uuid_entity_id(client: TestClient) -> None:
    """One audit entry per import, not per row.

    `entity_id` is a uuid column. SQLite stores any string there happily, so
    this asserts the VALUE parses as a UUID — otherwise a family name like
    "product" passes the whole suite here and only fails on PostgreSQL, in
    production, at commit time.
    """
    import uuid

    headers = provision(client)
    upsert(
        client,
        headers,
        [
            {"product_code": "A-1", "name": "甲"},
            {"product_code": "A-2", "name": "乙"},
        ],
    )

    entries = client.get("/api/v1/audit-logs?action=master_data.imported", headers=headers)
    assert entries.status_code == 200, entries.text
    logs = entries.json()["data"]
    assert len(logs) == 1, f"expected exactly one import entry, got {len(logs)}"
    entry = logs[0]
    uuid.UUID(entry["entity_id"])  # raises if it is not a real uuid
    assert entry["detail"]["family"] == "product"
    assert entry["detail"]["created"] == 2

    # a dry run is not an import and must leave no trail
    upsert(client, headers, [{"product_code": "A-3", "name": "丙"}], dry_run=True)
    after = client.get("/api/v1/audit-logs?action=master_data.imported", headers=headers)
    assert len(after.json()["data"]) == 1


def test_master_data_skill_ships_only_to_authorized_bundles(client: TestClient) -> None:
    """The skill that can rewrite the catalog must not sit in an ordinary
    member's bundle, where the agent would offer to use it and then 403."""
    import io
    import zipfile

    headers = provision(client)

    def bundle_names(role: str, permissions: list[str], email: str) -> list[str]:
        client.post(
            "/api/v1/roles", json={"name": role, "permissions": permissions}, headers=headers
        )
        invited = client.post(
            "/api/v1/auth/invitations", json={"email": email, "role": role}, headers=headers
        )
        user_id = invited.json()["data"]["id"]
        client.post(
            "/api/v1/auth/invitations/accept",
            json={"token": extract_token(outbox.messages[-1].body), "password": "some-pass1"},
        )
        response = client.post(f"/api/v1/users/{user_id}/skill-bundle", headers=headers)
        assert response.status_code == 200, response.text
        return zipfile.ZipFile(io.BytesIO(response.content)).namelist()

    keeper = bundle_names(
        "catalog_keeper", ["master_data.manage"], "keeper@import-co.example"
    )
    assert any("master-data" in name for name in keeper)

    plain = bundle_names("plain", ["timesheet.submit_own"], "plain@import-co.example")
    assert not any("master-data" in name for name in plain)


def test_batch_size_is_bounded(client: TestClient) -> None:
    headers = provision(client)
    rows = [{"product_code": f"B-{i:04d}", "name": f"产品{i}"} for i in range(501)]
    response = client.post("/api/v1/products/bulk", json={"rows": rows}, headers=headers)
    assert response.status_code == 422


def test_rerun_is_unchanged_for_prices_floats_cannot_represent(client: TestClient) -> None:
    """Numeric(12,2) columns come back as Decimal while rows carry JSON floats.
    Raw comparison is exact-binary — Decimal("19.90") != 19.9 — so a re-run of
    the same file reported phantom `updated, changed: ["list_price"]` on every
    price like 19.9 or 1234.56, forever. That is the exact "every row updated
    the same odd field" alarm the skill tells agents to escalate as a mapping
    mistake, fired by the server's own comparison."""
    headers = provision(client)
    rows = [
        {"product_code": "P-301", "name": "导管鞘", "list_price": 19.9},
        {"product_code": "P-302", "name": "缝合线", "list_price": 1234.56},
        {"product_code": "P-303", "name": "拉钩", "list_price": 0.01},
        {"product_code": "P-304", "name": "托盘", "list_price": 30000},
    ]
    first = upsert(client, headers, rows)
    assert first["summary"]["created"] == 4

    second = upsert(client, headers, rows)
    assert second["summary"] == {"total": 4, "created": 0, "updated": 0, "unchanged": 4, "failed": 0}, (
        second["results"]
    )

    # a real one-cent move is still a change, reported as such
    rows[0]["list_price"] = 19.91
    third = upsert(client, headers, rows)
    assert third["summary"]["updated"] == 1
    assert third["summary"]["unchanged"] == 3
    moved = [r for r in third["results"] if r["outcome"] == "updated"][0]
    assert moved["code"] == "P-301"
    assert moved["changed"] == ["list_price"]
