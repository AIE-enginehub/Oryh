"""Payroll — the salary record, and the payslip as an invoice.

`PayHistory` exists for its history: what someone was paid last March has to
stay answerable, because a payslip issued last March has to stay explainable.
So what must hold here is that a raise never overwrites a number — it closes one
record and opens another, in one call — that two salaries are never in force on
the same day, and that a record a payslip has cited is frozen.

The confidentiality half lives in `test_payroll_visibility.py`.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.models import ApiKey, Tenant, hash_api_key

from conftest import make_client

from conftest import provision_tenant as bootstrap_tenant

TEST_TENANT = "bbbbbbbb-7777-4777-8777-bbbbbbbbbbbb"
TEST_API_KEY = "payroll-test-key"
HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with make_client(
        [
            Tenant(id=TEST_TENANT, name="Payroll Co"),
            ApiKey(tenant_id=TEST_TENANT, key_hash=hash_api_key(TEST_API_KEY), label="primary"),
        ]
    ) as test_client:
        yield test_client


def post(client: TestClient, path: str, body: dict, expect: int = 201) -> dict:
    response = client.post(path, json=body, headers=HEADERS)
    assert response.status_code == expect, response.text
    return response.json()["data"] if expect < 400 else response.json()


def employee(client: TestClient, name: str = "员工小周") -> str:
    return post(client, "/api/v1/employees", {"name": name})["id"]


def set_salary(client: TestClient, employee_id: str, amount: float, effective_from: str,
               expect: int = 201, **overrides) -> dict:
    body = {"employee_id": employee_id, "amount": amount, "effective_from": effective_from}
    body.update(overrides)
    return post(client, "/api/v1/pay-histories", body, expect=expect)


def test_setting_a_salary_records_the_first_period(client: TestClient) -> None:
    person = employee(client)
    change = set_salary(client, person, 12000.0, "2026-01-01")

    assert change["current"]["amount"] == 12000.0
    assert change["current"]["effective_thru"] is None
    assert change["current"]["period_type"] == "month"
    # nothing was superseded — this is the first record
    assert change["superseded"] is None


def test_a_raise_closes_the_old_record_and_opens_a_new_one(client: TestClient) -> None:
    """The whole point of the entity: the old number does not disappear."""
    person = employee(client)
    set_salary(client, person, 12000.0, "2026-01-01")
    change = set_salary(client, person, 15000.0, "2026-07-01")

    assert change["current"]["amount"] == 15000.0
    assert change["current"]["effective_from"] == "2026-07-01"
    assert change["current"]["effective_thru"] is None
    # the old record was closed the day before, in the same call
    assert change["superseded"]["amount"] == 12000.0
    assert change["superseded"]["effective_thru"] == "2026-06-30"

    trail = client.get(f"/api/v1/employees/{person}/pay-history", headers=HEADERS).json()["data"]
    assert [row["amount"] for row in trail] == [15000.0, 12000.0]


def test_what_was_in_force_on_a_date_is_answerable(client: TestClient) -> None:
    person = employee(client)
    set_salary(client, person, 12000.0, "2026-01-01")
    set_salary(client, person, 15000.0, "2026-07-01")

    for on, expected in (("2026-03-15", 12000.0), ("2026-07-01", 15000.0), ("2026-12-31", 15000.0)):
        rows = client.get(
            f"/api/v1/pay-histories?employee_id={person}&in_force_on={on}", headers=HEADERS
        ).json()["data"]
        assert [row["amount"] for row in rows] == [expected], on


def test_two_salaries_are_never_in_force_on_the_same_day(client: TestClient) -> None:
    person = employee(client)
    set_salary(client, person, 12000.0, "2026-01-01", effective_thru="2026-12-31")

    body = set_salary(client, person, 15000.0, "2026-06-01", expect=409)
    assert "already in force" in body["detail"]

    # ...but a different component on the same days is the ordinary case
    post(
        client, "/api/v1/pay-histories",
        {"employee_id": person, "component": "allowance", "effective_from": "2026-06-01",
         "amount": 800.0},
    )

    # the same start date twice is refused too
    set_salary(client, person, 9000.0, "2026-01-01", expect=409)


def test_a_record_a_payslip_cited_cannot_be_edited(client: TestClient) -> None:
    """Moving it would change what an issued document says without touching
    that document."""
    person = employee(client)
    hr = employee(client, "HR小孙")
    record = set_salary(client, person, 12000.0, "2026-07-01")["current"]

    payslip = post(
        client, "/api/v1/invoices",
        {
            "direction": "payroll",
            "employee_id": hr,
            "payee_employee_id": person,
            "title": "2026年7月工资",
            "period_start": "2026-07-01",
            "period_end": "2026-07-31",
            "items": [
                {"invoice_item_type": "payroll_salary", "product_name_snapshot": "基本工资",
                 "amount": 12000.0, "pay_history_id": record["id"]},
            ],
        },
    )
    assert payslip["items"][0]["pay_history_id"] == record["id"]

    response = client.patch(
        f"/api/v1/pay-histories/{record['id']}", json={"amount": 20000.0}, headers=HEADERS
    )
    assert response.status_code == 409
    assert "payslip line" in response.json()["detail"]

    # an untouched record is still correctable
    other = set_salary(client, employee(client, "新人"), 8000.0, "2026-07-01")["current"]
    assert client.patch(
        f"/api/v1/pay-histories/{other['id']}", json={"amount": 8500.0}, headers=HEADERS
    ).status_code == 200


def test_a_commission_rate_lives_beside_the_salary(client: TestClient) -> None:
    """The reason it lives here and not in a tenant business object: business
    objects are readable by any credential in the workspace, and somebody's
    commission rate is as confidential as their salary."""
    person = employee(client)
    set_salary(client, person, 12000.0, "2026-01-01")

    commission = post(
        client, "/api/v1/pay-histories",
        {"employee_id": person, "component": "commission", "effective_from": "2026-01-01",
         "rate": 0.03, "basis": "当月本人负责合同的回款额",
         "notes": "季度结算，随次月工资发放"},
    )["current"]
    assert commission["rate"] == 0.03
    assert commission["amount"] is None

    # both are in force on the same day, and both are answerable
    in_force = client.get(
        f"/api/v1/employees/{person}/pay-history?in_force_on=2026-03-01", headers=HEADERS
    ).json()["data"]
    assert {row["component"] for row in in_force} == {"base_salary", "commission"}

    only_commission = client.get(
        "/api/v1/pay-histories?component=commission", headers=HEADERS
    ).json()["data"]
    assert [row["employee_id"] for row in only_commission] == [person]


def test_an_arrangement_that_is_neither_a_number_nor_a_rate_is_stated_in_words(
    client: TestClient,
) -> None:
    """阶梯提成 has no scalar and no single rate. The server stores the sentence
    and never parses it — the agent reads it, exactly as it reads a workflow
    definition."""
    person = employee(client)
    stated = post(
        client, "/api/v1/pay-histories",
        {"employee_id": person, "component": "bonus", "effective_from": "2026-01-01",
         "formula": "季度回款达标 100% 发 2 个月工资，120% 以上按 3 个月，未达标不发"},
    )["current"]
    assert stated["formula"].startswith("季度回款")
    assert stated["amount"] is None and stated["rate"] is None


def test_a_term_that_states_nothing_is_refused(client: TestClient) -> None:
    person = employee(client)
    body = post(
        client, "/api/v1/pay-histories",
        {"employee_id": person, "component": "allowance", "effective_from": "2026-01-01"},
        expect=422,
    )
    assert "states none of them" in body["detail"]

    # a proportion with nothing to apply it to is half a rule
    body = post(
        client, "/api/v1/pay-histories",
        {"employee_id": person, "component": "commission", "effective_from": "2026-01-01",
         "rate": 0.05},
        expect=422,
    )
    assert "basis" in body["detail"]

    # and it cannot be emptied by a correction either
    record = set_salary(client, person, 12000.0, "2026-01-01")["current"]
    emptied = client.patch(
        f"/api/v1/pay-histories/{record['id']}", json={"amount": None}, headers=HEADERS
    )
    assert emptied.status_code == 422


def test_a_raise_does_not_close_someone_s_commission_arrangement(client: TestClient) -> None:
    """The trap this test exists for: superseding by employee alone would end a
    commission deal every time someone got a pay rise, and nobody would notice
    until the quarter closed."""
    person = employee(client)
    set_salary(client, person, 12000.0, "2026-01-01")
    commission = post(
        client, "/api/v1/pay-histories",
        {"employee_id": person, "component": "commission", "effective_from": "2026-01-01",
         "rate": 0.03, "basis": "回款额"},
    )["current"]

    raise_ = set_salary(client, person, 15000.0, "2026-07-01")
    assert raise_["superseded"]["amount"] == 12000.0
    assert raise_["superseded"]["component"] == "base_salary"

    still_open = client.get(f"/api/v1/pay-histories/{commission['id']}", headers=HEADERS).json()["data"]
    assert still_open["effective_thru"] is None

    # ...and raising the commission closes the commission, not the salary
    bumped = post(
        client, "/api/v1/pay-histories",
        {"employee_id": person, "component": "commission", "effective_from": "2026-07-01",
         "rate": 0.05, "basis": "回款额"},
    )
    assert bumped["superseded"]["id"] == commission["id"]
    assert bumped["superseded"]["effective_thru"] == "2026-06-30"
    current_salary = client.get(
        f"/api/v1/pay-histories?component=base_salary&in_force_on=2026-08-01", headers=HEADERS
    ).json()["data"]
    assert [row["amount"] for row in current_salary] == [15000.0]


def test_the_component_vocabulary_is_gated(client: TestClient) -> None:
    person = employee(client)
    body = set_salary(client, person, 500.0, "2026-01-01", component="stock_options", expect=422)
    assert "commission" in body["detail"]


def test_a_contribution_base_is_a_fact_about_the_person(client: TestClient) -> None:
    """五险一金 RATES are national policy and deliberately absent — but the base
    they apply to is this person's own number, and it changes on its own
    schedule, so it inherits this table's effective dating."""
    person = employee(client)
    record = set_salary(
        client, person, 12000.0, "2026-07-01",
        custom_fields={"social_insurance_base": 11000, "housing_fund_base": 11000},
    )["current"]
    assert record["custom_fields"]["social_insurance_base"] == 11000


def test_a_period_that_ends_before_it_starts_is_refused(client: TestClient) -> None:
    person = employee(client)
    body = set_salary(
        client, person, 12000.0, "2026-07-01", effective_thru="2026-06-01", expect=422
    )
    assert "cannot precede" in body["detail"]


def test_the_period_type_vocabulary_is_gated(client: TestClient) -> None:
    person = employee(client)
    body = set_salary(client, person, 60.0, "2026-01-01", period_type="fortnight", expect=422)
    assert "hour" in body["detail"]

    hourly = set_salary(client, employee(client, "钟点工"), 60.0, "2026-01-01", period_type="hour")
    assert hourly["current"]["period_type"] == "hour"


def payslip(client: TestClient, hr: str, person: str, items: list[dict],
            period: str = "2026-07", expect: int = 201, **overrides) -> dict:
    year, month = period.split("-")
    last = {"01": 31, "02": 28, "03": 31, "04": 30, "05": 31, "06": 30,
            "07": 31, "08": 31, "09": 30, "10": 31, "11": 30, "12": 31}[month]
    body = {
        "direction": "payroll",
        "employee_id": hr,
        "payee_employee_id": person,
        "title": f"{year}年{int(month)}月工资",
        "period_start": f"{year}-{month}-01",
        "period_end": f"{year}-{month}-{last}",
        "items": items,
    }
    body.update(overrides)
    return post(client, "/api/v1/invoices", body, expect=expect)


JULY = [
    {"invoice_item_type": "payroll_salary", "product_name_snapshot": "基本工资",
     "amount": 12000.0, "notes": "月薪 12000.00"},
    {"invoice_item_type": "payroll_allowance", "product_name_snapshot": "交通补贴",
     "amount": 500.0, "notes": "岗位交通补贴 500.00/月"},
    {"invoice_item_type": "payroll_pension_ee", "product_name_snapshot": "养老",
     "amount": -960.0, "notes": "缴费基数 12000.00 × 8%"},
    {"invoice_item_type": "payroll_medical_ee", "product_name_snapshot": "医疗",
     "amount": -240.0, "notes": "缴费基数 12000.00 × 2%"},
    {"invoice_item_type": "payroll_unemploy_ee", "product_name_snapshot": "失业",
     "amount": -60.0, "notes": "缴费基数 12000.00 × 0.5%"},
    {"invoice_item_type": "payroll_housing_ee", "product_name_snapshot": "公积金",
     "amount": -1440.0, "notes": "缴费基数 12000.00 × 12%"},
    {"invoice_item_type": "payroll_iit", "product_name_snapshot": "个税",
     "amount": -253.8, "notes": "累计预扣法：应纳税所得额 8460.00 × 3%"},
]


def test_a_payslip_nets_its_earnings_against_its_deductions(client: TestClient) -> None:
    person, hr = employee(client), employee(client, "HR")
    slip = payslip(client, hr, person, JULY)

    detail = client.get(f"/api/v1/invoices/{slip['id']}/detail", headers=HEADERS).json()["data"]
    # 12000 + 500 − 960 − 240 − 60 − 1440 − 253.8
    assert detail["computed_total"] == 9546.2
    # net pay IS the line sum; a payslip never declares a total
    assert detail["billed_total"] == 9546.2
    assert detail["outstanding_amount"] == 9546.2
    assert detail["invoice"]["payee_employee_id"] == person
    assert detail["invoice"]["period_start"] == "2026-07-01"


def test_one_payslip_per_person_per_period(client: TestClient) -> None:
    """双发工资 is the expensive mistake here, so it is a database fact."""
    person, hr = employee(client), employee(client, "HR")
    payslip(client, hr, person, JULY)

    body = payslip(client, hr, person, JULY, expect=409)
    assert "already" in body["detail"].lower()

    # the next month is fine, and so is another person in the same month
    assert payslip(client, hr, person, JULY, period="2026-08")
    assert payslip(client, hr, employee(client, "另一位"), JULY)


def test_the_duplicate_payslip_409_names_the_person_not_the_number(client: TestClient) -> None:
    """Both collisions raise IntegrityError from the same `db.commit()`, and
    they mean opposite things. An agent told its NUMBER is taken retries with a
    different one, gets the same answer, and never learns that the real problem
    is it is about to pay somebody twice."""
    person, hr = employee(client), employee(client, "HR小孙")

    def payslip(title: str, expect: int, **extra) -> dict:
        body = {"direction": "payroll", "employee_id": hr, "payee_employee_id": person,
                "title": title, "period_start": "2026-07-01", "period_end": "2026-07-31",
                "items": [{"invoice_item_type": "payroll_salary",
                           "product_name_snapshot": "基本工资", "amount": 12000.0,
                           "notes": "月薪 12000.00"}]}
        body.update(extra)
        return post(client, "/api/v1/invoices", body, expect=expect)

    first = payslip("2026年7月工资", 201)

    same_period = payslip("2026年7月工资（重复）", 409)
    assert "pay them twice" in same_period["detail"]
    assert "2026-07-01" in same_period["detail"]
    # it names the payslip that already covers the period, which is the thing
    # the agent needs next
    assert first["invoice_no"] in same_period["detail"]

    # ...and a genuine numbering clash still says so
    clash = payslip(
        "2026年8月工资", 409,
        invoice_no=first["invoice_no"], period_start="2026-08-01", period_end="2026-08-31",
    )
    assert "invoice_no" in clash["detail"]


def test_a_payslip_line_must_show_its_working(client: TestClient) -> None:
    """The other half of a deliberate omission: 五险一金 rates are not stored
    here, so the line is the only record of how the number was reached."""
    person, hr = employee(client), employee(client, "HR小孙")
    record = set_salary(client, person, 12000.0, "2026-07-01")["current"]

    def payslip(items: list[dict], expect: int, period: str = "2026-07") -> dict:
        return post(
            client, "/api/v1/invoices",
            {"direction": "payroll", "employee_id": hr, "payee_employee_id": person,
             "title": f"{period} 工资", "period_start": f"{period}-01",
             "period_end": f"{period}-28", "items": items},
            expect=expect,
        )

    unexplained = payslip(
        [{"invoice_item_type": "payroll_housing_ee",
          "product_name_snapshot": "住房公积金（个人）", "amount": -1440.0}],
        expect=422,
    )
    assert "show its working" in unexplained["detail"]

    # spelling the arithmetic out is enough...
    payslip(
        [{"invoice_item_type": "payroll_housing_ee",
          "product_name_snapshot": "住房公积金（个人）", "amount": -1440.0,
          "notes": "缴费基数 12000.00 × 12% = 1440.00"}],
        expect=201,
    )
    # ...and so is citing the record the number came from
    payslip(
        [{"invoice_item_type": "payroll_salary", "product_name_snapshot": "基本工资",
          "amount": 12000.0, "pay_history_id": record["id"]}],
        expect=201, period="2026-08",
    )

    # whitespace is not an explanation
    assert payslip(
        [{"invoice_item_type": "payroll_allowance", "product_name_snapshot": "交通补贴",
          "amount": 500.0, "notes": "   "}],
        expect=422, period="2026-09",
    )

    # and an ordinary sales line is unaffected — this is a payslip rule
    buyer = post(client, "/api/v1/customers", {"name": "客户"})["id"]
    post(
        client, "/api/v1/invoices",
        {"direction": "sales", "employee_id": hr, "customer_id": buyer, "title": "货款",
         "items": [{"product_name_snapshot": "货物", "amount": 5000.0}]},
    )


def test_a_correction_cannot_strip_the_explanation(client: TestClient) -> None:
    person, hr = employee(client), employee(client, "HR小孙")
    payslip = post(
        client, "/api/v1/invoices",
        {"direction": "payroll", "employee_id": hr, "payee_employee_id": person,
         "title": "2026年7月工资", "period_start": "2026-07-01", "period_end": "2026-07-31",
         "items": [{"invoice_item_type": "payroll_iit", "product_name_snapshot": "个人所得税",
                    "amount": -300.0, "notes": "累计预扣法：应纳税所得额 10000 × 3%"}]},
    )
    line = payslip["items"][0]["id"]
    emptied = client.patch(
        f"/api/v1/invoice-items/{line}", json={"notes": None}, headers=HEADERS
    )
    assert emptied.status_code == 422


def test_a_deduction_written_positive_is_refused(client: TestClient) -> None:
    """个税 as +253.8 rather than −253.8 pays the person 507.6 too much, and
    nothing downstream would notice."""
    person, hr = employee(client), employee(client, "HR")
    body = payslip(
        client, hr, person,
        [
            {"invoice_item_type": "payroll_salary", "product_name_snapshot": "基本工资",
             "amount": 12000.0, "notes": "月薪 12000.00"},
            {"invoice_item_type": "payroll_iit", "product_name_snapshot": "个税",
             "amount": 253.8, "notes": "累计预扣法"},
        ],
        expect=422,
    )
    assert "deduction" in body["detail"]
    assert "negative" in body["detail"]

    # and an earning written negative is refused the same way
    body = payslip(
        client, hr, person,
        [{"invoice_item_type": "payroll_salary", "product_name_snapshot": "基本工资",
          "amount": -12000.0, "notes": "月薪 12000.00"}],
        expect=422,
    )
    assert "earning" in body["detail"]


def test_a_payslip_may_not_declare_a_total(client: TestClient) -> None:
    person, hr = employee(client), employee(client, "HR")
    body = payslip(client, hr, person, JULY, total_amount=9999.0, expect=422)
    assert "sum of its lines" in body["detail"]


def test_a_payslip_needs_a_period_and_lines(client: TestClient) -> None:
    person, hr = employee(client), employee(client, "HR")

    no_period = post(
        client, "/api/v1/invoices",
        {
            "direction": "payroll", "employee_id": hr, "payee_employee_id": person,
            "title": "无期间", "items": JULY,
        },
        expect=422,
    )
    assert "pay period" in no_period["detail"]

    no_lines = payslip(client, hr, person, [], expect=422)
    assert "is its lines" in no_lines["detail"]


def test_a_payslip_carries_no_customer_vendor_or_order(client: TestClient) -> None:
    person, hr = employee(client), employee(client, "HR")
    buyer = post(client, "/api/v1/customers", {"name": "客户"})["id"]

    wrong_party = payslip(client, hr, person, JULY, customer_id=buyer, expect=422)
    assert "payee_employee_id" in wrong_party["detail"]

    order = post(
        client, "/api/v1/sales-orders",
        {"employee_id": hr, "title": "SO", "customer_id": buyer},
    )
    wrong_order = payslip(client, hr, person, JULY, sales_order_id=order["id"], expect=422)
    assert "bills no order" in wrong_order["detail"]


def test_a_payslip_uses_the_payroll_vocabulary_not_the_goods_one(client: TestClient) -> None:
    person, hr = employee(client), employee(client, "HR")
    body = payslip(
        client, hr, person,
        [{"invoice_item_type": "goods", "product_name_snapshot": "货物", "amount": 100.0}],
        expect=422,
    )
    assert "payroll_salary" in body["detail"]

    # and a sales invoice cannot use payroll types
    buyer = post(client, "/api/v1/customers", {"name": "客户"})["id"]
    cross = post(
        client, "/api/v1/invoices",
        {
            "direction": "sales", "employee_id": hr, "customer_id": buyer, "title": "串词表",
            "items": [{"invoice_item_type": "payroll_salary", "product_name_snapshot": "x",
                       "amount": 1.0, "notes": "月薪 1.00"}],
        },
        expect=422,
    )
    assert "goods" in cross["detail"]


def test_a_tenant_deduction_type_must_declare_its_sign(client: TestClient) -> None:
    person, hr = employee(client), employee(client, "HR")
    assert post(
        client, "/api/v1/type-options",
        {"family": "payroll_item_type", "name": "union_dues", "title": "工会费"},
    )

    unsigned = payslip(
        client, hr, person,
        [{"invoice_item_type": "union_dues", "product_name_snapshot": "工会费", "amount": -50.0}],
        expect=422,
    )
    assert "does not say whether it adds" in unsigned["detail"]


def test_a_payslip_is_settled_by_an_outbound_payment(client: TestClient) -> None:
    """The whole payables chain is reused: no new settlement code at all."""
    person, hr = employee(client), employee(client, "HR")
    slip = payslip(client, hr, person, JULY)
    payout = post(
        client, "/api/v1/payments",
        {
            "direction": "outbound", "employee_id": hr, "payee_employee_id": person,
            "amount": 9546.2, "status": "paid",
            # the bank batch every payslip in this run shares
            "reference_no": "PAYROLL-2026-07",
        },
    )
    result = post(
        client, f"/api/v1/payments/{payout['id']}/apply",
        {"lines": [{"applied_to_type": "invoice", "applied_to_id": slip["id"],
                    "amount_applied": 9546.2}]},
        expect=200,
    )
    assert result["targets"][0]["outstanding_amount"] == 0.0

    over = post(
        client, "/api/v1/payments",
        {"direction": "outbound", "employee_id": hr, "payee_employee_id": person,
         "amount": 100.0, "status": "paid"},
    )
    body = post(
        client, f"/api/v1/payments/{over['id']}/apply",
        {"lines": [{"applied_to_type": "invoice", "applied_to_id": slip["id"],
                    "amount_applied": 100.0}]},
        expect=409,
    )
    assert "over-applying" in body["detail"]


def test_a_salary_line_may_only_cite_that_persons_record(client: TestClient) -> None:
    person, other = employee(client), employee(client, "别人")
    hr = employee(client, "HR")
    theirs = set_salary(client, other, 20000.0, "2026-07-01")["current"]

    body = payslip(
        client, hr, person,
        [{"invoice_item_type": "payroll_salary", "product_name_snapshot": "基本工资",
          "amount": 12000.0, "pay_history_id": theirs["id"]}],
        expect=422,
    )
    assert "different employee" in body["detail"]


def test_setting_a_salary_needs_the_payroll_capability(scoped_client) -> None:
    """定薪 is a different act from running payroll, so it is a different grant."""
    service, hr_only = scoped_client
    person = service["client"].post(
        "/api/v1/employees", json={"name": "员工"}, headers=service["headers"]
    ).json()["data"]["id"]

    refused = hr_only["client"].post(
        "/api/v1/pay-histories",
        json={"employee_id": person, "amount": 12000.0, "effective_from": "2026-01-01"},
        headers=hr_only["headers"],
    )
    assert refused.status_code == 403
    assert "payroll.manage" in refused.json()["detail"]


@pytest.fixture()
def scoped_client() -> Generator[tuple[dict, dict], None, None]:
    """A registered tenant plus a user-bound key that can read payroll but not
    set salaries."""
    from app.services.emails import outbox

    def token_from(body: str) -> str:
        for line in body.splitlines():
            if "token=" in line:
                return line.rsplit("token=", 1)[1].strip()
        raise AssertionError("no token in email")

    with make_client([]) as test_client:
        data = bootstrap_tenant(test_client, company_name="HR Co", email="admin@hr-co.com", password="hr-pass12345")
        service = {"client": test_client, "headers": {"X-API-Key": data["plain_text_api_key"]}}

        assert test_client.post(
            "/api/v1/roles",
            json={"name": "payroll_viewer", "permissions": ["payroll.read"]},
            headers=service["headers"],
        ).status_code == 201
        user_id = test_client.post(
            "/api/v1/auth/invitations",
            json={"email": "viewer@hr-co.com", "role": "payroll_viewer"},
            headers=service["headers"],
        ).json()["data"]["id"]
        test_client.post(
            "/api/v1/auth/invitations/accept",
            json={"token": token_from(outbox.messages[-1].body), "password": "invitee-pass1"},
        )
        key = test_client.post(
            "/api/v1/tenant/api-keys",
            json={"label": "viewer", "user_id": user_id},
            headers=service["headers"],
        ).json()["data"]["plain_text_api_key"]
        yield service, {"client": test_client, "headers": {"X-API-Key": key}}


def _audit_payroll_checks() -> list[tuple[str, str]]:
    """The payroll invariants out of scripts/data_integrity_audit.py, loaded
    textually because scripts/ is not an importable package."""
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "data_integrity_audit.py"
    text = source.read_text(encoding="utf-8")
    # everything above main(), so the helpers the check SQL is built from come
    # along with it — slicing at STRUCTURAL_CHECKS would leave them undefined
    namespace: dict = {"__file__": str(source)}
    exec(text[: text.index("def main()")], namespace)
    return [
        (name, sql)
        for name, sql in namespace["STRUCTURAL_CHECKS"]
        if "pay_histories" in sql or "'payroll'" in sql
    ]


def test_the_integrity_audits_payroll_invariants_hold_on_real_payroll(client: TestClient) -> None:
    """The audit is a script — nothing imports it, so nothing else would notice
    it drifting from the schema. Build a workspace that exercises every payroll
    shape there is, then run the audit's own SQL over it and require zero.

    Worth doing here specifically because these are the checks that would let a
    double payment sit unnoticed, and because they are the ones most likely to
    rot: two of them reference columns (`component`, `sign`) that did not exist
    a release ago.
    """
    from sqlalchemy import text as sql_text

    from app.db.session import get_db
    from app.main import app

    person, colleague = employee(client), employee(client, "同事小林")
    hr = employee(client, "HR小孙")

    salary = set_salary(client, person, 12000.0, "2026-01-01")["current"]
    set_salary(client, person, 15000.0, "2026-07-01")            # a raise
    post(                                                        # a rate term
        client, "/api/v1/pay-histories",
        {"employee_id": person, "component": "commission", "effective_from": "2026-01-01",
         "rate": 0.03, "basis": "回款额"},
    )
    post(                                                        # a formula term
        client, "/api/v1/pay-histories",
        {"employee_id": colleague, "component": "bonus", "effective_from": "2026-01-01",
         "formula": "达标发 2 个月工资"},
    )
    colleague_salary = set_salary(client, colleague, 9000.0, "2026-01-01")["current"]

    for who, record, gross in ((person, salary, 12000.0), (colleague, colleague_salary, 9000.0)):
        payslip = post(
            client, "/api/v1/invoices",
            {
                "direction": "payroll", "employee_id": hr, "payee_employee_id": who,
                "title": "2026年6月工资", "period_start": "2026-06-01", "period_end": "2026-06-30",
                "items": [
                    {"invoice_item_type": "payroll_salary", "product_name_snapshot": "基本工资",
                     "amount": gross, "pay_history_id": record["id"]},
                    {"invoice_item_type": "payroll_allowance",
                     "product_name_snapshot": "交通补贴", "amount": 500.0,
                     "notes": "岗位交通补贴 500.00/月"},
                    {"invoice_item_type": "payroll_pension_ee",
                     "product_name_snapshot": "养老保险（个人 8%）",
                     "amount": -round(gross * 0.08, 2),
                     "notes": f"缴费基数 {gross:.2f} × 8%"},
                    {"invoice_item_type": "payroll_iit",
                     "product_name_snapshot": "个人所得税", "amount": -300.0,
                     "notes": "累计预扣法"},
                ],
            },
        )
        net = gross + 500.0 - round(gross * 0.08, 2) - 300.0
        payout = post(
            client, "/api/v1/payments",
            {"direction": "outbound", "employee_id": hr, "payee_employee_id": who,
             "amount": net, "status": "paid", "reference_no": "PAYROLL-2026-06"},
        )
        post(
            client, f"/api/v1/payments/{payout['id']}/apply",
            {"lines": [{"applied_to_type": "invoice", "applied_to_id": payslip["id"],
                        "amount_applied": net}]},
            expect=200,
        )

    checks = _audit_payroll_checks()
    names = [name for name, _ in checks]
    assert len(checks) >= 11, f"the audit lost its payroll invariants: {names}"
    # this one is in the list because the closed-set clause at the end of it was
    # silently reporting every payslip as a violation until payroll was added to
    # it — a check nobody had run against payroll data
    assert "invoice direction agrees with its counterparty" in names

    db = next(app.dependency_overrides[get_db]())
    try:
        # the checks are only worth running against data — a clean audit over an
        # empty table proves nothing
        assert db.execute(sql_text("select count(*) from pay_histories")).scalar() == 5
        assert db.execute(
            sql_text("select count(*) from invoice_items it join invoices i on it.invoice_id = i.id"
                     " where i.direction = 'payroll'")
        ).scalar() == 8

        for name, sql in checks:
            offending = db.execute(sql_text(sql)).scalar()
            assert offending == 0, f"{name}: {offending} offending rows"

        # and a planted violation is caught — otherwise a check that silently
        # matches nothing would look identical to a clean database
        sign_check = next(sql for name, sql in checks if "moves the way its type" in name)
        db.execute(sql_text(
            "update invoice_items set amount = abs(amount)"
            " where invoice_item_type = 'payroll_iit'"
        ))
        assert db.execute(sql_text(sign_check)).scalar() == 2
        db.rollback()
    finally:
        db.close()
