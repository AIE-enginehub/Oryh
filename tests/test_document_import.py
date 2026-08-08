"""Historical quotation/order import — the migration path.

The behaviours a several-hundred-thousand-row Excel migration depends on:
the document keeps its own number (and that number is the upsert key, so a
half-finished run resumes by re-running), terminal states import as-is,
master data resolves by the tenant's own codes, and a document whose
customer or product no longer exists is REPORTED while the rest of the file
still lands.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.models import ApiKey, Tenant, hash_api_key

from conftest import make_client

TEST_TENANT = "44444444-4444-4444-4444-444444444444"
TEST_API_KEY = "doc-import-key"
HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with make_client(
        [
            Tenant(id=TEST_TENANT, name="Migration Co"),
            ApiKey(tenant_id=TEST_TENANT, key_hash=hash_api_key(TEST_API_KEY), label="primary"),
        ]
    ) as test_client:
        yield test_client


def seed_master_data(client: TestClient) -> None:
    assert client.post(
        "/api/v1/employees", json={"name": "李雷", "employee_code": "E-001"}, headers=HEADERS
    ).status_code == 201
    assert client.post(
        "/api/v1/customers/bulk",
        json={"rows": [{"customer_code": "C-001", "name": "华欣机械有限公司"}]},
        headers=HEADERS,
    ).status_code == 200
    assert client.post(
        "/api/v1/products/bulk",
        json={"rows": [{"product_code": "P-001", "name": "四刃立铣刀", "list_price": 120.0}]},
        headers=HEADERS,
    ).status_code == 200


def quotation_row(**overrides) -> dict:
    row = {
        "quote_number": "QT-2023-0001",
        "employee_code": "E-001",
        "customer_code": "C-001",
        "title": "2023年刀具年度报价",
        "quote_date": "2023-03-15",
        "status": "accepted",
        "total_amount": 1180.0,
        "items": [
            {"line_no": 1, "product_code": "P-001", "quantity": 10, "unit_price": 100.0, "amount": 1000.0},
        ],
        "adjustments": [
            {"adjustment_type": "tax", "amount": 130.0, "source_percentage": 13},
            {"adjustment_type": "rounding", "amount": -0.5, "line_no": 1},
        ],
    }
    row.update(overrides)
    return row


def import_quotations(client: TestClient, rows, **options) -> dict:
    response = client.post(
        "/api/v1/sales-quotations/bulk", json={"rows": rows, **options}, headers=HEADERS
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_historical_quotations_keep_their_numbers_states_and_children(client: TestClient) -> None:
    seed_master_data(client)
    rows = [quotation_row()]

    preview = import_quotations(client, rows, dry_run=True)
    assert preview["applied"] is False and preview["summary"]["created"] == 1
    assert client.get("/api/v1/sales-quotations", headers=HEADERS).json()["data"] == []

    applied = import_quotations(client, rows)
    assert applied["summary"] == {"total": 1, "created": 1, "updated": 0, "unchanged": 0, "failed": 0}

    listed = client.get("/api/v1/sales-quotations", headers=HEADERS).json()["data"]
    assert len(listed) == 1
    quotation = listed[0]
    # the historical number survives; no QT-000001 was allocated over it
    assert quotation["quote_number"] == "QT-2023-0001"
    assert quotation["status"] == "accepted"  # terminal state imported as-is
    assert quotation["quote_date"] == "2023-03-15"

    detail = client.get(
        f"/api/v1/sales-quotations/{quotation['id']}/detail", headers=HEADERS
    ).json()["data"]
    assert detail["computed_total"] == 1000.0
    assert detail["adjustments_total"] == 129.5
    assert detail["adjusted_total"] == 1129.5
    assert len(detail["items"]) == 1
    # the line-pinned adjustment found its line by line_no
    pinned = [a for a in detail["adjustments"] if a["adjustment_type"] == "rounding"][0]
    assert pinned["quotation_item_id"] == detail["items"][0]["id"]
    # codes resolved to real master data
    assert detail["items"][0]["product_id"] is not None
    assert quotation["customer_id"] is not None

    # re-running the same file is a no-op — how a half-finished migration resumes
    rerun = import_quotations(client, rows)
    assert rerun["summary"]["unchanged"] == 1, rerun["results"]
    assert len(client.get("/api/v1/sales-quotations", headers=HEADERS).json()["data"]) == 1

    # a corrected file updates the same document in place
    corrected = [quotation_row(total_amount=1200.0)]
    updated = import_quotations(client, corrected)
    assert updated["summary"]["updated"] == 1
    assert "total_amount" in updated["results"][0]["changed"]


def test_unknown_references_report_the_document_and_the_rest_still_imports(client: TestClient) -> None:
    """The user's requirement: name the problem documents, import the others."""
    seed_master_data(client)
    rows = [
        quotation_row(),
        quotation_row(quote_number="QT-2023-0002", customer_code="C-GONE"),
        quotation_row(quote_number="QT-2023-0003", items=[
            {"line_no": 1, "product_code": "P-GONE", "quantity": 1, "unit_price": 5.0},
        ]),
        quotation_row(quote_number="QT-2023-0004", employee_code="E-GONE"),
    ]
    report = import_quotations(client, rows)

    assert report["applied"] is True
    assert report["summary"] == {"total": 4, "created": 1, "updated": 0, "unchanged": 0, "failed": 3}
    errors = {r["number"]: r["error"] for r in report["results"] if r["outcome"] == "error"}
    assert "C-GONE" in errors["QT-2023-0002"]
    assert "P-GONE" in errors["QT-2023-0003"]
    assert "E-GONE" in errors["QT-2023-0004"]
    # only the good document landed
    assert [q["quote_number"] for q in
            client.get("/api/v1/sales-quotations", headers=HEADERS).json()["data"]] == ["QT-2023-0001"]

    # snapshot mode imports them anyway, keeping the historical text; a missing
    # SALESPERSON is still an error, because the document cannot exist without one
    snapshot = import_quotations(
        client, rows, on_missing_reference="snapshot",
    )
    assert snapshot["summary"]["failed"] == 1
    assert snapshot["summary"]["created"] == 2  # the customer- and product-gap rows
    still_failing = [r for r in snapshot["results"] if r["outcome"] == "error"][0]
    assert still_failing["number"] == "QT-2023-0004"
    landed = {q["quote_number"]: q for q in
              client.get("/api/v1/sales-quotations", headers=HEADERS).json()["data"]}
    assert landed["QT-2023-0002"]["customer_id"] is None  # text stands alone


def test_batch_level_guards(client: TestClient) -> None:
    seed_master_data(client)
    duplicate = import_quotations(client, [quotation_row(), quotation_row()])
    assert duplicate["summary"]["failed"] == 1
    assert "duplicate quote_number" in [
        r["error"] for r in duplicate["results"] if r["outcome"] == "error"
    ][0]

    bad_state = import_quotations(client, [quotation_row(status="没这个状态")])
    assert bad_state["summary"]["failed"] == 1
    assert "not a state" in bad_state["results"][0]["error"]

    bad_pin = import_quotations(client, [quotation_row(
        quote_number="QT-2023-0009",
        adjustments=[{"adjustment_type": "tax", "amount": 1.0, "line_no": 7}],
    )])
    assert bad_pin["summary"]["failed"] == 1
    assert "line_no 7" in bad_pin["results"][0]["error"]

    # abort is still available for the "my mapping is wrong" case
    aborted = import_quotations(
        client, [quotation_row(quote_number="QT-A"), quotation_row(quote_number="QT-B", customer_code="C-GONE")],
        on_error="abort",
    )
    assert aborted["applied"] is False
    assert client.get("/api/v1/sales-quotations?keyword=QT-A", headers=HEADERS).json()["data"] == []


def test_historical_orders_import_and_link_to_their_quotation(client: TestClient) -> None:
    seed_master_data(client)
    import_quotations(client, [quotation_row()])

    response = client.post(
        "/api/v1/sales-orders/bulk",
        json={"rows": [{
            "order_no": "SO-2023-0001",
            "employee_code": "E-001",
            "customer_code": "C-001",
            "source_quote_number": "QT-2023-0001",
            "title": "2023年首批订单",
            "order_date": "2023-04-01",
            "status": "signed",
            "contract_no": "HT-2023-088",
            "items": [
                {"line_no": 1, "product_code": "P-001", "quantity": 10, "unit_price": 100.0,
                 "amount": 1000.0, "promised_date": "2023-04-20"},
            ],
            "adjustments": [{"adjustment_type": "shipping", "amount": 80.0}],
        }]},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["summary"]["created"] == 1

    order = client.get("/api/v1/sales-orders", headers=HEADERS).json()["data"][0]
    assert order["order_no"] == "SO-2023-0001"
    assert order["status"] == "signed"
    assert order["source_quote_number"] == "QT-2023-0001"
    detail = client.get(f"/api/v1/sales-orders/{order['id']}/detail", headers=HEADERS).json()["data"]
    assert detail["computed_total"] == 1000.0
    assert detail["adjusted_total"] == 1080.0
    assert detail["items"][0]["promised_date"] == "2023-04-20"


def test_a_full_chunk_of_documents_costs_a_bounded_number_of_queries(client: TestClient) -> None:
    """The point of the endpoint: 300k documents finish. A 500-row chunk must
    resolve its master data in a handful of reads, not one per row — and it
    must not touch the number allocator, whose per-tenant advisory lock would
    serialize the whole migration."""
    seed_master_data(client)
    rows = [
        quotation_row(
            quote_number=f"QT-2023-{index:05d}",
            items=[{"line_no": 1, "product_code": "P-001", "quantity": 1, "unit_price": 10.0}],
            adjustments=[],
        )
        for index in range(500)
    ]

    statements: list[str] = []
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    def before_execute(conn, clauseelement, multiparams, params, execution_options):
        text = str(clauseelement)
        if text.lstrip().upper().startswith("SELECT"):
            statements.append(text)

    event.listen(Engine, "before_execute", before_execute)
    try:
        report = import_quotations(client, rows)
    finally:
        event.remove(Engine, "before_execute", before_execute)

    assert report["summary"]["created"] == 500
    # five master-data lookups + the existing-documents probe + per-document
    # child reads; the guard is that it does not scale with LINES
    lookups = [s for s in statements if " IN (" in s or "employee_code" in s]
    assert len(lookups) < 20, f"{len(lookups)} lookup queries for 500 rows"
    assert not any("pg_advisory" in s for s in statements)


def test_a_member_key_cannot_backfill_history_under_a_colleagues_name(client: TestClient) -> None:
    """The single-document endpoints stop a member from filing for someone
    else (enforce_member_employee). A bulk import writes for many people at
    once, so it demands the capability that lifts that limit outright — or a
    member could quietly attribute historical quotations to colleagues."""
    seed_master_data(client)
    employee_id = client.post(
        "/api/v1/employees", json={"name": "韩梅梅", "employee_code": "E-002"}, headers=HEADERS
    ).json()["data"]["id"]
    from app.core.permissions import DEFAULT_ROLE_PERMISSIONS

    assert "tenant.act_for_any_employee" not in DEFAULT_ROLE_PERMISSIONS["member"]

    # a user-bound key on the default member role
    invited = client.post(
        "/api/v1/auth/invitations",
        json={"email": "mei@migration.example", "role": "member", "employee_id": employee_id},
        headers=HEADERS,
    )
    assert invited.status_code == 201, invited.text
    from app.services.emails import outbox

    token = next(
        line.rsplit("token=", 1)[1].strip()
        for line in outbox.messages[-1].body.splitlines()
        if "token=" in line
    )
    accepted = client.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "password": "mei-pass1"}
    )
    assert accepted.status_code in (200, 201), accepted.text
    member_key = client.post(
        "/api/v1/tenant/api-keys",
        json={"label": "member-agent", "user_id": invited.json()["data"]["id"]},
        headers=HEADERS,
    ).json()["data"]["plain_text_api_key"]

    denied = client.post(
        "/api/v1/sales-quotations/bulk",
        json={"rows": [quotation_row()]},
        headers={"X-API-Key": member_key},
    )
    assert denied.status_code == 403
    assert "tenant.act_for_any_employee" in denied.json()["detail"]
