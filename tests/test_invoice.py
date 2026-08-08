"""Invoices — one family, both directions, as OFBiz's `Invoice` is.

What must hold: the direction decides which counterparty is legal and which
order may be billed, and it never changes afterwards; a tax invoice number may
only be booked once per workspace — across BOTH an expense item and a vendor
bill, which is the duplicate-booking hole a single-table check leaves open; a
header-only invoice with no lines is settleable, because that is how most
汇总开票 arrive; and `invoice.manage` may be scoped to one direction so 应收
and 应付 can be different people.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.models import ApiKey, Tenant, hash_api_key
from app.services.emails import outbox

from conftest import make_client

from conftest import provision_tenant as bootstrap_tenant

TEST_TENANT = "88888888-1111-4111-8111-888888888888"
TEST_API_KEY = "invoice-test-key"
HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with make_client(
        [
            Tenant(id=TEST_TENANT, name="Invoice Co"),
            ApiKey(tenant_id=TEST_TENANT, key_hash=hash_api_key(TEST_API_KEY), label="primary"),
        ]
    ) as test_client:
        yield test_client


def extract_token(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError("no token in email")


def client_post(ctx: dict, path: str, body: dict) -> dict:
    response = ctx["client"].post(path, json=body, headers=ctx["headers"])
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.fixture()
def scoped_client() -> Generator[tuple[dict, dict], None, None]:
    """A real registered tenant (so roles and capabilities are provisioned)
    plus a user-bound key holding only `invoice.manage:sales`."""
    with make_client([]) as test_client:
        data = bootstrap_tenant(test_client, company_name="AR Co", email="admin@ar-co.com", password="ar-pass1234")
        service = {"client": test_client, "headers": {"X-API-Key": data["plain_text_api_key"]}}

        assert test_client.post(
            "/api/v1/roles",
            json={"name": "ar_clerk", "permissions": ["invoice.manage:sales"]},
            headers=service["headers"],
        ).status_code == 201
        user_id = test_client.post(
            "/api/v1/auth/invitations",
            json={"email": "ar@ar-co.com", "role": "ar_clerk"},
            headers=service["headers"],
        ).json()["data"]["id"]
        invite_token = extract_token(outbox.messages[-1].body)
        test_client.post(
            "/api/v1/auth/invitations/accept",
            json={"token": invite_token, "password": "invitee-pass1"},
        )
        key = test_client.post(
            "/api/v1/tenant/api-keys",
            json={"label": "ar-agent", "user_id": user_id},
            headers=service["headers"],
        ).json()["data"]["plain_text_api_key"]
        yield service, {"client": test_client, "headers": {"X-API-Key": key}}


def create_employee(client: TestClient, **overrides) -> str:
    payload = {"name": "财务小陈"}
    payload.update(overrides)
    response = client.post("/api/v1/employees", json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def create_customer(client: TestClient, **overrides) -> dict:
    payload = {"name": "上海市第一医院", "customer_code": "C-SH1"}
    payload.update(overrides)
    response = client.post("/api/v1/customers", json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_vendor(client: TestClient, **overrides) -> dict:
    payload = {"name": "戴尔（中国）有限公司", "vendor_code": "V-DELL"}
    payload.update(overrides)
    response = client.post("/api/v1/vendors", json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_invoice(client: TestClient, **overrides) -> dict:
    employee_id = overrides.pop("employee_id", None) or create_employee(client)
    payload = {
        "direction": "sales",
        "employee_id": employee_id,
        "title": "2026年7月货款",
    }
    payload.update(overrides)
    # an invoice has to bill something; tests that are about lines or about a
    # declared total say so themselves, and everything else gets a plain figure
    if payload.get("total_amount") is None and not payload.get("items"):
        payload["total_amount"] = 1000.0
    response = client.post("/api/v1/invoices", json=payload, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_a_sales_invoice_takes_a_customer_and_allocates_its_own_number(client: TestClient) -> None:
    customer = create_customer(client)
    invoice = create_invoice(client, customer_id=customer["id"])

    assert invoice["direction"] == "sales"
    assert invoice["customer_id"] == customer["id"]
    assert invoice["vendor_id"] is None
    # the counterparty name is snapshotted from master data
    assert invoice["counterparty_name_snapshot"] == "上海市第一医院"
    assert invoice["invoice_no"].startswith("INV-")
    assert invoice["status"] == "draft"
    assert invoice["applied_amount"] == 0
    # the tax document's own number is absent until it is actually issued
    assert invoice["tax_invoice_number"] is None


def test_the_direction_decides_which_counterparty_is_legal(client: TestClient) -> None:
    employee_id = create_employee(client)
    vendor = create_vendor(client)
    customer = create_customer(client)

    # a sales invoice pointed at a vendor is refused, not silently re-filed
    wrong_side = client.post(
        "/api/v1/invoices",
        json={
            "direction": "sales",
            "employee_id": employee_id,
            "title": "错方向",
            "vendor_id": vendor["id"],
        },
        headers=HEADERS,
    )
    assert wrong_side.status_code == 422
    assert "customer_id" in wrong_side.json()["detail"]

    missing = client.post(
        "/api/v1/invoices",
        json={"direction": "purchase", "employee_id": employee_id, "title": "缺对手方"},
        headers=HEADERS,
    )
    assert missing.status_code == 422
    assert "vendor_id" in missing.json()["detail"]

    # and both sides work when named correctly
    assert create_invoice(client, direction="sales", customer_id=customer["id"])["customer_id"]
    assert create_invoice(client, direction="purchase", vendor_id=vendor["id"])["vendor_id"]


def test_the_direction_is_immutable_once_filed(client: TestClient) -> None:
    """Flipping it would silently reinterpret the counterparty, the capability
    scope, the billable order and what a payment may settle."""
    customer = create_customer(client)
    invoice = create_invoice(client, customer_id=customer["id"])

    response = client.patch(
        f"/api/v1/invoices/{invoice['id']}",
        json={"direction": "purchase"},
        headers=HEADERS,
    )
    # the field is simply not on the update schema — an unknown field is refused
    assert response.status_code == 422
    after = client.get(f"/api/v1/invoices/{invoice['id']}", headers=HEADERS).json()["data"]
    assert after["direction"] == "sales"


def test_a_tax_invoice_number_cannot_be_booked_twice(client: TestClient) -> None:
    vendor = create_vendor(client)
    create_invoice(
        client, direction="purchase", vendor_id=vendor["id"], tax_invoice_number="24312000000098765432"
    )

    duplicate = client.post(
        "/api/v1/invoices",
        json={
            "direction": "purchase",
            "employee_id": create_employee(client),
            "title": "重复进项票",
            "vendor_id": vendor["id"],
            "tax_invoice_number": "24312000000098765432",
        },
        headers=HEADERS,
    )
    assert duplicate.status_code == 409
    assert "already booked" in duplicate.json()["detail"]


def test_the_same_number_is_legal_on_the_other_side(client: TestClient) -> None:
    """Sales numbers are ours to issue and purchase numbers are the vendor's;
    they live in different number spaces, so a collision across the two is not
    a double booking."""
    vendor = create_vendor(client)
    customer = create_customer(client)
    create_invoice(
        client, direction="purchase", vendor_id=vendor["id"], tax_invoice_number="24312000000011112222"
    )
    same_number_other_side = create_invoice(
        client, direction="sales", customer_id=customer["id"], tax_invoice_number="24312000000011112222"
    )
    assert same_number_other_side["tax_invoice_number"] == "24312000000011112222"


def test_an_invoice_number_already_reimbursed_cannot_also_be_billed(client: TestClient) -> None:
    """The expensive duplicate: the same 进项发票 reimbursed to an employee AND
    paid again against the supplier's own invoice."""
    employee_id = create_employee(client)
    vendor = create_vendor(client)
    claim = client.post(
        "/api/v1/expense-claims",
        json={"employee_id": employee_id, "title": "7月差旅"},
        headers=HEADERS,
    )
    assert claim.status_code == 201, claim.text
    item = client.post(
        "/api/v1/expense-items",
        json={
            "claim_id": claim.json()["data"]["id"],
            "employee_id": employee_id,
            "expense_date": "2026-07-11",
            "amount": 480.0,
            "invoice_number": "24312000000055556666",
        },
        headers=HEADERS,
    )
    assert item.status_code == 201, item.text

    also_billed = client.post(
        "/api/v1/invoices",
        json={
            "direction": "purchase",
            "employee_id": employee_id,
            "title": "供应商账单",
            "vendor_id": vendor["id"],
            "tax_invoice_number": "24312000000055556666",
        },
        headers=HEADERS,
    )
    assert also_billed.status_code == 409
    assert "expense item" in also_billed.json()["detail"]


def test_the_reverse_direction_of_the_duplicate_check_also_holds(client: TestClient) -> None:
    """A number booked on a vendor bill must not then be reimbursed."""
    employee_id = create_employee(client)
    vendor = create_vendor(client)
    create_invoice(
        client, direction="purchase", employee_id=employee_id, vendor_id=vendor["id"],
        tax_invoice_number="24312000000077778888",
    )
    claim = client.post(
        "/api/v1/expense-claims",
        json={"employee_id": employee_id, "title": "8月差旅"},
        headers=HEADERS,
    ).json()["data"]

    reimbursed = client.post(
        "/api/v1/expense-items",
        json={
            "claim_id": claim["id"],
            "employee_id": employee_id,
            "expense_date": "2026-08-01",
            "amount": 480.0,
            "invoice_number": "24312000000077778888",
        },
        headers=HEADERS,
    )
    assert reimbursed.status_code == 409
    assert "already booked" in reimbursed.json()["detail"]


def test_lines_carry_the_money_and_the_detail_reports_both_totals(client: TestClient) -> None:
    """No declared header total, so the line sum is what settlement measures."""
    customer = create_customer(client)
    invoice = create_invoice(
        client,
        customer_id=customer["id"],
        items=[
            {
                "product_name_snapshot": "27寸显示器",
                "quantity": 3,
                "unit_price": 3000.0,
                "tax_rate": 13.0,
                "tax_amount": 1035.4,
            },
            {
                "invoice_item_type": "shipping",
                # a pure charge line has no quantity and no unit price
                "product_name_snapshot": "运费",
                "amount": 300.0,
            },
        ],
    )
    # the create response reads back what landed, line by line
    assert [item["product_name_snapshot"] for item in invoice["items"]] == ["27寸显示器", "运费"]

    detail = client.get(f"/api/v1/invoices/{invoice['id']}/detail", headers=HEADERS).json()["data"]
    assert detail["computed_total"] == 9300.0
    assert detail["computed_tax_total"] == 1035.4
    # no declared header total, so the line sum is what settlement measures
    assert detail["billed_total"] == 9300.0
    assert detail["outstanding_amount"] == 9300.0
    assert detail["applications"] == []


def test_an_invoice_must_bill_something(client: TestClient) -> None:
    """An invoice is raised WITH what it bills. With neither lines nor a
    declared total it is not a draft awaiting detail — it is a document that
    says nothing and can never be settled."""
    customer = create_customer(client)
    employee_id = create_employee(client)

    empty = client.post(
        "/api/v1/invoices",
        json={
            "direction": "sales",
            "employee_id": employee_id,
            "title": "空单",
            "customer_id": customer["id"],
        },
        headers=HEADERS,
    )
    assert empty.status_code == 422
    assert "something to bill" in empty.json()["detail"]

    # either half satisfies it
    assert create_invoice(client, customer_id=customer["id"], total_amount=9000.0)
    assert create_invoice(
        client, customer_id=customer["id"],
        items=[{"product_name_snapshot": "显示器", "quantity": 3, "unit_price": 3000.0}],
    )


def test_a_bad_inline_line_rolls_the_whole_invoice_back(client: TestClient) -> None:
    """One call, one transaction: a validation failure on the second line must
    not leave a half-raised invoice behind."""
    customer = create_customer(client)
    employee_id = create_employee(client)
    before = len(client.get("/api/v1/invoices", headers=HEADERS).json()["data"])

    response = client.post(
        "/api/v1/invoices",
        json={
            "direction": "sales",
            "employee_id": employee_id,
            "title": "半成品",
            "customer_id": customer["id"],
            "items": [
                {"product_name_snapshot": "显示器", "amount": 3000.0},
                # no product and no free-text name — this line cannot stand
                {"amount": 500.0},
            ],
        },
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert len(client.get("/api/v1/invoices", headers=HEADERS).json()["data"]) == before


def test_an_inline_line_may_not_name_another_invoice(client: TestClient) -> None:
    customer = create_customer(client)
    other = create_invoice(client, customer_id=customer["id"])

    response = client.post(
        "/api/v1/invoices",
        json={
            "direction": "sales",
            "employee_id": create_employee(client),
            "title": "串单",
            "customer_id": customer["id"],
            "items": [
                {"invoice_id": other["id"], "product_name_snapshot": "显示器", "amount": 100.0}
            ],
        },
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert "inline lines belong to the invoice being created" in response.json()["detail"]


def test_a_declared_header_total_wins_over_the_line_sum(client: TestClient) -> None:
    """抹零 and 汇总开票 both make the stated total the truth; the line sum stays
    visible so an agent can judge the gap."""
    customer = create_customer(client)
    invoice = create_invoice(client, customer_id=customer["id"], total_amount=9300.0)
    client.post(
        "/api/v1/invoice-items",
        json={
            "invoice_id": invoice["id"],
            "product_name_snapshot": "27寸显示器",
            "quantity": 3,
            "unit_price": 3100.0,
        },
        headers=HEADERS,
    )

    detail = client.get(f"/api/v1/invoices/{invoice['id']}/detail", headers=HEADERS).json()["data"]
    assert detail["computed_total"] == 9300.0
    assert detail["billed_total"] == 9300.0


def test_a_header_only_invoice_is_settleable(client: TestClient) -> None:
    customer = create_customer(client)
    invoice = create_invoice(client, customer_id=customer["id"], total_amount=12800.0)

    detail = client.get(f"/api/v1/invoices/{invoice['id']}/detail", headers=HEADERS).json()["data"]
    assert detail["items"] == []
    assert detail["billed_total"] == 12800.0
    assert detail["outstanding_amount"] == 12800.0


def test_lines_are_frozen_once_the_invoice_leaves_its_editable_states(client: TestClient) -> None:
    customer = create_customer(client)
    invoice = create_invoice(client, customer_id=customer["id"])
    client.post(f"/api/v1/invoices/{invoice['id']}/submit", headers=HEADERS)
    issued = client.patch(
        f"/api/v1/invoices/{invoice['id']}", json={"status": "issued"}, headers=HEADERS
    )
    assert issued.status_code == 200, issued.text
    assert issued.json()["data"]["issued_at"] is not None

    late_line = client.post(
        "/api/v1/invoice-items",
        json={"invoice_id": invoice["id"], "product_name_snapshot": "追加", "amount": 10.0},
        headers=HEADERS,
    )
    assert late_line.status_code == 409
    assert "invoice lines" in late_line.json()["detail"]


def test_an_illegal_status_move_names_the_allowed_targets(client: TestClient) -> None:
    customer = create_customer(client)
    invoice = create_invoice(client, customer_id=customer["id"])

    response = client.patch(
        f"/api/v1/invoices/{invoice['id']}", json={"status": "paid"}, headers=HEADERS
    )
    assert response.status_code == 409
    assert "illegal transition" in response.json()["detail"]


def test_a_line_may_only_bill_a_line_of_the_order_this_invoice_bills(client: TestClient) -> None:
    customer = create_customer(client)
    employee_id = create_employee(client)
    order = client.post(
        "/api/v1/sales-orders",
        json={"employee_id": employee_id, "title": "SO-1", "customer_id": customer["id"]},
        headers=HEADERS,
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["data"]["id"]
    order_line = client.post(
        "/api/v1/sales-order-items",
        json={"order_id": order_id, "product_name_snapshot": "显示器", "quantity": 3, "unit_price": 3000.0},
        headers=HEADERS,
    ).json()["data"]

    unlinked = create_invoice(client, customer_id=customer["id"], employee_id=employee_id)
    orphan = client.post(
        "/api/v1/invoice-items",
        json={
            "invoice_id": unlinked["id"],
            "product_name_snapshot": "显示器",
            "amount": 9000.0,
            "sales_order_item_id": order_line["id"],
        },
        headers=HEADERS,
    )
    # the invoice does not bill that order yet, so the line has nothing to pin to
    assert orphan.status_code == 422
    assert "sales_order_id" in orphan.json()["detail"]

    linked = create_invoice(
        client, customer_id=customer["id"], employee_id=employee_id, sales_order_id=order_id
    )
    pinned = client.post(
        "/api/v1/invoice-items",
        json={
            "invoice_id": linked["id"],
            "product_name_snapshot": "显示器",
            "amount": 9000.0,
            "sales_order_item_id": order_line["id"],
        },
        headers=HEADERS,
    )
    assert pinned.status_code == 201, pinned.text
    assert pinned.json()["data"]["sales_order_item_id"] == order_line["id"]


def test_a_sales_invoice_cannot_bill_a_purchase_order(client: TestClient) -> None:
    customer = create_customer(client)
    vendor = create_vendor(client)
    employee_id = create_employee(client)
    po = client.post(
        "/api/v1/purchase-orders",
        json={"vendor_id": vendor["id"], "employee_id": employee_id, "title": "PO-1"},
        headers=HEADERS,
    )
    assert po.status_code == 201, po.text

    response = client.post(
        "/api/v1/invoices",
        json={
            "direction": "sales",
            "employee_id": employee_id,
            "title": "跨方向",
            "customer_id": customer["id"],
            "purchase_order_id": po.json()["data"]["id"],
        },
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert "sales_order" in response.json()["detail"]


def test_soft_delete_hides_the_invoice_and_restore_brings_it_back(client: TestClient) -> None:
    customer = create_customer(client)
    invoice = create_invoice(client, customer_id=customer["id"])

    assert client.delete(
        f"/api/v1/invoices/{invoice['id']}", headers=HEADERS
    ).status_code == 204
    assert client.get(f"/api/v1/invoices/{invoice['id']}", headers=HEADERS).status_code == 404
    listed = client.get("/api/v1/invoices", headers=HEADERS).json()["data"]
    assert invoice["id"] not in {row["id"] for row in listed}

    restored = client.post(f"/api/v1/invoices/{invoice['id']}/restore", headers=HEADERS)
    assert restored.status_code == 200
    assert client.get(f"/api/v1/invoices/{invoice['id']}", headers=HEADERS).status_code == 200


def test_an_unknown_status_filter_names_this_workspaces_states(client: TestClient) -> None:
    response = client.get("/api/v1/invoices?status=settled", headers=HEADERS)
    assert response.status_code == 422
    assert "issued" in response.json()["detail"]


def test_opening_balances_import_by_their_own_numbers(client: TestClient) -> None:
    """期初应收应付: historical invoices keep their own numbers, arrive already
    issued, and a re-run of the same file changes nothing."""
    create_employee(client, name="王会计", employee_code="E-王")
    create_customer(client, customer_code="C-SH1")
    create_vendor(client, vendor_code="V-DELL")
    rows = [
        {
            "invoice_no": "2025-AR-0001",
            "direction": "sales",
            "employee_code": "E-王",
            "customer_code": "C-SH1",
            "title": "2025年12月货款",
            "due_date": "2026-01-31",
            "total_amount": 48000.0,
            "status": "issued",
            "items": [
                {"line_no": 1, "product_name_snapshot": "监护仪", "quantity": 4, "unit_price": 12000.0},
            ],
        },
        {
            "invoice_no": "2025-AP-0007",
            "direction": "purchase",
            "employee_code": "E-王",
            "vendor_code": "V-DELL",
            "title": "服务器尾款",
            "total_amount": 26000.0,
            "status": "issued",
            "items": [{"invoice_item_type": "goods", "product_name_snapshot": "服务器", "amount": 26000.0}],
        },
    ]

    preview = client.post("/api/v1/invoices/bulk", json={"rows": rows, "dry_run": True}, headers=HEADERS)
    assert preview.status_code == 200, preview.text
    assert preview.json()["data"]["summary"]["created"] == 2
    assert preview.json()["data"]["applied"] is False
    assert client.get("/api/v1/invoices", headers=HEADERS).json()["data"] == []

    applied = client.post("/api/v1/invoices/bulk", json={"rows": rows}, headers=HEADERS)
    assert applied.status_code == 200, applied.text
    assert applied.json()["data"]["summary"]["created"] == 2

    imported = client.get("/api/v1/invoices", headers=HEADERS).json()["data"]
    assert {row["invoice_no"] for row in imported} == {"2025-AR-0001", "2025-AP-0007"}
    ar = next(row for row in imported if row["direction"] == "sales")
    assert ar["status"] == "issued"
    assert ar["due_date"] == "2026-01-31"
    # nothing is settled by an import — that is a payment fact, not a column
    assert ar["applied_amount"] == 0

    rerun = client.post("/api/v1/invoices/bulk", json={"rows": rows}, headers=HEADERS)
    assert rerun.json()["data"]["summary"]["unchanged"] == 2


def test_an_import_row_on_the_wrong_side_is_reported_not_filed(client: TestClient) -> None:
    create_employee(client, name="王会计", employee_code="E-王")
    create_vendor(client, vendor_code="V-DELL")

    response = client.post(
        "/api/v1/invoices/bulk",
        json={
            "rows": [
                {
                    "invoice_no": "2025-AR-0002",
                    "direction": "sales",
                    "employee_code": "E-王",
                    "vendor_code": "V-DELL",
                    "title": "方向搞反了",
                    "status": "issued",
                }
            ]
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    row = response.json()["data"]["results"][0]
    assert row["outcome"] == "error"
    assert "customer" in row["error"]
    assert client.get("/api/v1/invoices", headers=HEADERS).json()["data"] == []


def test_invoice_manage_can_be_scoped_to_one_direction(scoped_client: TestClient) -> None:
    """不相容职务分离: an 应收会计 granted only `invoice.manage:sales` files and
    edits sales invoices and cannot touch the purchase side — the scope
    dimension the permission grammar already has, applied to a direction."""
    service, ar_only = scoped_client
    employee_id = client_post(service, "/api/v1/employees", {"name": "应收会计"})["id"]
    customer = client_post(service, "/api/v1/customers", {"name": "上海市第一医院"})
    vendor = client_post(service, "/api/v1/vendors", {"name": "戴尔"})

    allowed = ar_only["client"].post(
        "/api/v1/invoices",
        json={
            "direction": "sales",
            "employee_id": employee_id,
            "title": "销项",
            "customer_id": customer["id"],
            "total_amount": 1000.0,
        },
        headers=ar_only["headers"],
    )
    assert allowed.status_code == 201, allowed.text

    refused = ar_only["client"].post(
        "/api/v1/invoices",
        json={
            "direction": "purchase",
            "employee_id": employee_id,
            "title": "进项",
            "vendor_id": vendor["id"],
            "total_amount": 1000.0,
        },
        headers=ar_only["headers"],
    )
    assert refused.status_code == 403
    assert "invoice.manage:purchase" in refused.json()["detail"]

    # and the same scope holds on the shared document plumbing, not just create:
    # a purchase invoice filed by the admin key is out of this role's reach
    others = client_post(
        service,
        "/api/v1/invoices",
        {
            "direction": "purchase",
            "employee_id": employee_id,
            "title": "别人的进项",
            "vendor_id": vendor["id"],
            "total_amount": 1000.0,
        },
    )
    assert ar_only["client"].post(
        f"/api/v1/invoices/{others['id']}/submit", headers=ar_only["headers"]
    ).status_code == 403
    assert ar_only["client"].delete(
        f"/api/v1/invoices/{others['id']}", headers=ar_only["headers"]
    ).status_code == 403


def test_the_type_vocabularies_are_gated_and_extensible(client: TestClient) -> None:
    customer = create_customer(client)
    employee_id = create_employee(client)

    unknown = client.post(
        "/api/v1/invoices",
        json={
            "direction": "sales",
            "employee_id": employee_id,
            "title": "未知票种",
            "customer_id": customer["id"],
            "invoice_type": "made_up",
        },
        headers=HEADERS,
    )
    assert unknown.status_code == 422
    assert "vat_special" in unknown.json()["detail"]

    assert client.post(
        "/api/v1/type-options",
        json={"family": "invoice_type", "name": "internal_settlement", "title": "内部结算单"},
        headers=HEADERS,
    ).status_code == 201
    accepted = create_invoice(
        client, customer_id=customer["id"], employee_id=employee_id,
        invoice_type="internal_settlement",
    )
    assert accepted["invoice_type"] == "internal_settlement"
