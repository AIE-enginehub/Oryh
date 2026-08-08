"""Retail and B2B customers on one table.

The decision these tests pin is a refusal: no second table for 零售会员, and no
Party layer. A member and a 集团客户 differ in what their FILE holds, never in
what happens to them, so the difference rides two optional fields — a closed
`customer_kind` the database constrains, and an open `customer_type` the tenant
owns — and neither one gates anything.

What is worth pinning is therefore mostly about what the server does NOT do:
it does not invent a kind for a row that omitted one, it does not accept a
segment the tenant's vocabulary lacks, and it does not treat either field as a
permission.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import provision_tenant as bootstrap_tenant


def provision(client: TestClient) -> dict[str, str]:
    verified = bootstrap_tenant(client, company_name="Retail Co", email="admin@retail-co.example", password="admin-pass1")
    return {"X-API-Key": verified["plain_text_api_key"]}


def create_customer(client: TestClient, headers, **fields) -> dict:
    response = client.post("/api/v1/customers", json=fields, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_retail_and_b2b_customers_coexist_on_one_endpoint(client: TestClient) -> None:
    """The whole point of the design: one table, one endpoint, both books."""
    headers = provision(client)

    member = create_customer(
        client, headers,
        customer_code="M-13800000000", name="张女士",
        customer_kind="person", customer_type="retail", phone="13800000000",
    )
    hospital = create_customer(
        client, headers,
        customer_code="C-001", name="市第一医院",
        customer_kind="company", customer_type="institution",
        tax_id="12310000MB0K1XXXXX",
    )

    assert member["customer_kind"] == "person"
    assert hospital["customer_type"] == "institution"

    both = client.get("/api/v1/customers", headers=headers).json()["data"]
    assert {row["id"] for row in both} == {member["id"], hospital["id"]}


def test_each_axis_filters_independently(client: TestClient) -> None:
    """kind and type are different questions — 经销商 are companies too, so a
    filter on one must never quietly answer the other."""
    headers = provision(client)
    create_customer(
        client, headers, customer_code="M-01", name="张女士",
        customer_kind="person", customer_type="retail", phone="13800000000",
    )
    create_customer(
        client, headers, customer_code="D-01", name="华东医疗器械",
        customer_kind="company", customer_type="distributor",
    )
    create_customer(
        client, headers, customer_code="C-01", name="市第一医院",
        customer_kind="company", customer_type="institution",
    )

    def names(query: str) -> set[str]:
        response = client.get(f"/api/v1/customers?{query}", headers=headers)
        assert response.status_code == 200, response.text
        return {row["name"] for row in response.json()["data"]}

    assert names("customer_kind=company") == {"华东医疗器械", "市第一医院"}
    assert names("customer_kind=person") == {"张女士"}
    assert names("customer_type=distributor") == {"华东医疗器械"}
    # the retail identity key, as tax_id is the B2B one
    assert names("phone=13800000000") == {"张女士"}


def test_an_unstated_kind_stays_unstated(client: TestClient) -> None:
    """A row that says nothing about kind must come back saying nothing.

    Defaulting to 'company' would be a fact nobody stated, repeated by every
    later report — and 个体工商户 is genuinely both, so there is no safe guess
    to make on the person's behalf."""
    headers = provision(client)
    customer = create_customer(client, headers, customer_code="C-01", name="某某商行")

    assert customer["customer_kind"] is None
    assert customer["customer_type"] is None

    # and it stays absent through an unrelated edit
    patched = client.patch(
        f"/api/v1/customers/{customer['id']}", json={"phone": "13900000000"}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["customer_kind"] is None


def test_kind_is_a_closed_pair(client: TestClient) -> None:
    """It is a constrained column, not vocabulary: 自然人 vs 组织 is universal
    rather than the tenant's to extend, and a Party layer would take it as its
    discriminator unchanged."""
    headers = provision(client)
    response = client.post(
        "/api/v1/customers",
        json={"customer_code": "C-01", "name": "某某商行", "customer_kind": "个人"},
        headers=headers,
    )
    assert response.status_code == 422, response.text


def test_unknown_segment_is_refused_and_definable(client: TestClient) -> None:
    """The open axis behaves exactly like price types: an unfamiliar word in a
    客户分类 column is a new type to propose, never one to approximate into the
    nearest shipped value."""
    headers = provision(client)

    refused = client.post(
        "/api/v1/customers",
        json={"customer_code": "C-01", "name": "团购客户甲", "customer_type": "group_buy"},
        headers=headers,
    )
    assert refused.status_code == 422, refused.text
    assert "group_buy" in refused.json()["detail"]

    defined = client.post(
        "/api/v1/type-options",
        json={"family": "customer_type", "name": "group_buy", "title": "团购客户"},
        headers=headers,
    )
    assert defined.status_code == 201, defined.text

    accepted = create_customer(
        client, headers, customer_code="C-01", name="团购客户甲", customer_type="group_buy"
    )
    assert accepted["customer_type"] == "group_buy"


def test_archiving_a_segment_refuses_new_writes_only(client: TestClient) -> None:
    """Same contract every vocabulary has: history keeps whatever it says."""
    headers = provision(client)
    existing = create_customer(
        client, headers, customer_code="C-01", name="老经销商", customer_type="distributor"
    )

    listed = client.get("/api/v1/type-options?family=customer_type", headers=headers)
    assert listed.status_code == 200, listed.text
    option = next(row for row in listed.json()["data"] if row["name"] == "distributor")
    archived = client.patch(
        f"/api/v1/type-options/{option['id']}", json={"status": "archived"}, headers=headers
    )
    assert archived.status_code == 200, archived.text

    refused = client.post(
        "/api/v1/customers",
        json={"customer_code": "C-02", "name": "新经销商", "customer_type": "distributor"},
        headers=headers,
    )
    assert refused.status_code == 422, refused.text

    unchanged = client.get(f"/api/v1/customers/{existing['id']}", headers=headers)
    assert unchanged.json()["data"]["customer_type"] == "distributor"


def test_bulk_import_carries_both_fields_and_validates_the_segment(client: TestClient) -> None:
    """A 会员登记表 goes through the same upsert as a 客户清单, and a segment the
    tenant's catalog lacks is the ROW's error — named, with the fix, not a value
    the import invents on the person's behalf."""
    headers = provision(client)
    response = client.post(
        "/api/v1/customers/bulk",
        json={
            "rows": [
                {"customer_code": "M-01", "name": "张女士",
                 "customer_kind": "person", "customer_type": "retail", "phone": "13800000000"},
                {"customer_code": "M-02", "name": "李先生",
                 "customer_kind": "person", "customer_type": "group_buy"},
            ],
            "on_error": "skip",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert data["summary"] == {"total": 2, "created": 1, "updated": 0, "unchanged": 0, "failed": 1}
    failure = next(row for row in data["results"] if row["outcome"] == "error")
    assert failure["index"] == 1
    assert "unknown customer_type 'group_buy'" in failure["error"]
    assert "POST /type-options" in failure["error"]

    stored = client.get("/api/v1/customers?customer_kind=person", headers=headers).json()["data"]
    assert [(row["name"], row["customer_type"]) for row in stored] == [("张女士", "retail")]


def test_a_chinese_segment_word_is_refused_before_the_vocabulary_is_consulted(
    client: TestClient,
) -> None:
    """The sheet's word is not the vocabulary's name.

    Type-option names are `^[a-z][a-z0-9_]{0,49}$`, so a 客户分类 column mapped
    straight through ("团购") fails the request SHAPE and takes the whole chunk
    with it — a different, blunter failure than the per-row one above. It is the
    right refusal, but an agent that has not read that distinction will report
    "整批导入失败" for what is really one unmapped column, so it is pinned here.
    """
    headers = provision(client)
    response = client.post(
        "/api/v1/customers/bulk",
        json={
            "rows": [
                {"customer_code": "M-01", "name": "张女士", "customer_type": "retail"},
                {"customer_code": "M-02", "name": "李先生", "customer_type": "团购"},
            ],
            "on_error": "skip",
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert client.get("/api/v1/customers", headers=headers).json()["data"] == []


def test_neither_field_gates_anything(client: TestClient) -> None:
    """Pricing, 账期 and prepayment are judgments for agents and workflow
    definitions. A retail person must be able to hold an ordinary invoice and
    an ordinary standing balance, or the two columns have quietly become
    permissions."""
    headers = provision(client)
    member = create_customer(
        client, headers, customer_code="M-01", name="张女士",
        customer_kind="person", customer_type="retail", phone="13800000000",
    )

    account = client.post(
        "/api/v1/billing-accounts",
        json={
            "account_code": "BA-M-01", "name": "张女士储值",
            "unit_type": "currency", "unit": "CNY", "customer_id": member["id"],
        },
        headers=headers,
    )
    assert account.status_code == 201, account.text
    assert account.json()["data"]["customer_id"] == member["id"]
