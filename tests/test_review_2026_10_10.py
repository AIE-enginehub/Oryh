"""The 2026-10-10 architecture review's reproductions, kept as regressions.

Each test is one of the review's probes (`docs/system-architecture-review-
2026-10-10.zh.md`, R01–R13): the request that produced the wrong answer, now
asserting the right one. Synthetic data, the test stack's SQLite.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from conftest import create, make_stack, provision_tenant
from app.core import idempotency
from app.core.idempotency import IdempotencyMiddleware
from app.models import ApiKey, Customer, IdempotencyRecord
from app.services.bundles import eligible_skills


@pytest.fixture()
def shop():
    with make_stack([]) as (client, engine):
        t = provision_tenant(client, company_name="Review Co", email="admin@review.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        emp = create(client, admin, "employees", name="Synthetic employee")["id"]
        yield {"client": client, "admin": admin, "tenant": t, "employee": emp}


# --- R01: a replay is re-gated by the credential that asks for it ----------


def test_a_revoked_key_cannot_replay_the_answer_it_once_got(shop) -> None:
    c, admin, t = shop["client"], shop["admin"], shop["tenant"]
    keyed = {**admin, "Idempotency-Key": "review-revoked"}
    first = c.post("/api/v1/customers", headers=keyed, json={"name": "Synthetic review customer"})
    assert first.status_code == 201, first.text
    with c.session_factory() as db:
        db.get(ApiKey, t["api_key"]["id"]).is_active = False
        db.commit()
    assert c.get("/api/v1/customers", headers=admin).status_code == 401
    replay = c.post("/api/v1/customers", headers=keyed, json={"name": "Synthetic review customer"})
    assert replay.status_code == 401, replay.text
    assert "Idempotency-Replayed" not in replay.headers
    assert "customer" not in replay.text.lower() or "invalid" in replay.text.lower(), "the stored answer must not leak"


# --- R02: a claim that never reported back is not re-run with the same key --


def test_a_write_that_committed_before_its_answer_was_stored_is_not_written_twice(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    keyed = {**admin, "Idempotency-Key": "review-settle-failure"}
    body = {"name": "Synthetic commit window"}
    with patch.object(IdempotencyMiddleware, "_settle", side_effect=RuntimeError("synthetic settle failure")):
        first = c.post("/api/v1/customers", headers=keyed, json=body)
    assert first.status_code == 201, "the handler committed and answered; only the bookkeeping failed"
    with c.session_factory() as db:
        record = db.scalar(select(IdempotencyRecord))
        record.created_at = idempotency._now() - timedelta(minutes=6)
        db.commit()
    again = c.post("/api/v1/customers", headers=keyed, json=body)
    assert again.status_code == 409, again.text
    assert "never reported its outcome" in again.text
    with c.session_factory() as db:
        assert len(list(db.scalars(select(Customer).where(Customer.name == body["name"])))) == 1


def test_a_stale_claim_from_a_different_request_is_still_a_reuse(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    with c.session_factory() as db:
        scope = hashlib.sha256(("key:" + admin["X-API-Key"]).encode()).hexdigest()
        db.add(IdempotencyRecord(scope_hash=scope, key="stale", fingerprint="x", method="POST", path="/api/v1/customers",
                                 created_at=idempotency._now() - timedelta(minutes=6)))
        db.commit()
    other = c.post("/api/v1/customers", json={"name": "y"}, headers={**admin, "Idempotency-Key": "stale"})
    assert other.status_code == 422 and "idempotency_key_reused" in other.text


# --- R03: the three numbers of a line agree at the column's scale -----------


def test_a_unit_price_finer_than_the_column_is_refused_with_the_arithmetic(shop) -> None:
    c, admin, emp = shop["client"], shop["admin"], shop["employee"]
    r = c.post("/api/v1/sales-orders", headers=admin, json={
        "employee_id": emp, "title": "Precision test", "customer_name_snapshot": "Synthetic buyer",
        "items": [{"product_name_snapshot": "Synthetic line", "quantity": 2, "unit_price": 0.335}],
    })
    assert r.status_code == 422, r.text
    assert "unit_price 0.335 has more than two decimals" in r.text


def test_a_line_at_the_columns_scale_stores_numbers_that_agree(shop) -> None:
    c, admin, emp = shop["client"], shop["admin"], shop["employee"]
    order = create(c, admin, "sales-orders", employee_id=emp, title="Precision test", customer_name_snapshot="Synthetic buyer",
                   items=[{"product_name_snapshot": "Synthetic line", "quantity": 3, "unit_price": 0.1}])
    line = c.get("/api/v1/sales-order-items", headers=admin, params={"order_id": order["id"]}).json()["data"][0]
    assert (line["quantity"], line["unit_price"], line["amount"]) == (3.0, 0.1, 0.3), "0.30, not 0.30000000000000004"


# --- R05 / R06: what applies on a date is one row, and never a future one ---


def _publish(c, admin, body, date, object_type="expense_claim"):
    r = c.post("/api/v1/business-rules/publish", headers=admin, json={
        "kind": "approval_flow", "object_type": object_type, "body": body, "effective_from": date})
    return r


def test_the_version_in_force_today_is_not_the_one_dated_next_year(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    assert _publish(c, admin, "current rule", "2026-01-01").status_code == 201
    assert _publish(c, admin, "future rule", "2027-01-01").status_code == 201
    published = c.get("/api/v1/business-rules", headers=admin, params={
        "kind": "approval_flow", "object_type": "expense_claim", "status": "published"}).json()["data"]
    assert [x["body"] for x in published] == ["future rule"], "status=published is the latest version"
    today = c.get("/api/v1/business-rules", headers=admin, params={
        "kind": "approval_flow", "object_type": "expense_claim", "in_force_on": "2026-10-10"}).json()["data"]
    assert [x["body"] for x in today] == ["current rule"], "in_force_on is what governs"
    area = c.get("/api/v1/workspace/setup-report", headers=admin).json()["data"]["areas"]["expense_claim"]
    assert area["facts"]["rules"]["expense_claim"]["approval_flow"]["version"] == 1, \
        "the setup report names the version in force today, not the one that starts next year"


def test_a_version_cannot_start_before_the_one_it_replaces(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    assert _publish(c, admin, "v1", "2026-01-01").status_code == 201
    assert _publish(c, admin, "v2", "2027-01-01").status_code == 201
    backdated = _publish(c, admin, "v3", "2026-06-01")
    assert backdated.status_code == 422, backdated.text
    assert "cannot start earlier" in backdated.text
    on_date = c.get("/api/v1/business-rules", headers=admin, params={
        "kind": "approval_flow", "object_type": "expense_claim", "in_force_on": "2027-01-01"}).json()["data"]
    assert [(x["version"], x["effective_from"]) for x in on_date] == [(2, "2027-01-01")]


def test_two_versions_published_on_one_day_answer_with_the_later(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    assert _publish(c, admin, "morning", "2026-10-10").status_code == 201
    assert _publish(c, admin, "afternoon", "2026-10-10").status_code == 201
    on_date = c.get("/api/v1/business-rules", headers=admin, params={
        "kind": "approval_flow", "object_type": "expense_claim", "in_force_on": "2026-10-10"}).json()["data"]
    assert [x["body"] for x in on_date] == ["afternoon"], "one answer for a date"


# --- R09: the rules skill reaches every desk that may maintain a rule -------


def test_the_business_rules_skill_reaches_the_flow_publisher_too(shop) -> None:
    c, t = shop["client"], shop["tenant"]
    with c.session_factory() as db:
        reach = {
            grant: "oryh-business-rules" in [s.name for s in eligible_skills(db, t["tenant"]["id"], frozenset({grant}))]
            for grant in ("workflows.publish", "policy.publish", "policy.manage", "order.submit_own")
        }
    assert reach == {"workflows.publish": True, "policy.publish": True, "policy.manage": True, "order.submit_own": False}


def test_a_custom_skill_may_name_alternatives_and_each_is_validated(shop) -> None:
    c, admin = shop["client"], shop["admin"]
    ok = c.post("/api/v1/skills", headers=admin, json={
        "name": "rc-two-desks", "title": "Two desks", "description": "Use when either desk asks.",
        "required_capability": "policy.publish|workflows.publish", "files": {"SKILL.md": "# Two desks\n"}})
    assert ok.status_code == 201, ok.text
    bad = c.post("/api/v1/skills", headers=admin, json={
        "name": "rc-bad", "title": "Bad", "description": "x",
        "required_capability": "policy.publish|no.such", "files": {"SKILL.md": "# Bad\n"}})
    assert bad.status_code == 422 and "unknown capability" in bad.text


# --- R12 / R13: shared capacity is a peak, and a merged period is validated --


@pytest.fixture()
def pool(shop):
    c, admin, emp = shop["client"], shop["admin"], shop["employee"]
    resource = create(c, admin, "resources", name="Synthetic pool", resource_type="equipment", booking_mode="shared", max_quantity=2)["id"]

    def book(start, end, quantity=1, day="2026-11-01"):
        return c.post("/api/v1/resource-bookings", headers=admin, json={
            "resource_id": resource, "booked_by_employee_id": emp, "title": "Synthetic booking",
            "start_at": f"{day}T{start}:00+00:00", "end_at": f"{day}T{end}:00+00:00", "quantity": quantity})
    return {**shop, "book": book, "resource": resource}


def test_a_shared_resource_counts_what_is_held_at_once_not_every_overlap(pool) -> None:
    book = pool["book"]
    assert book("09:00", "10:00").status_code == 201
    assert book("10:00", "11:00").status_code == 201
    covering = book("09:00", "11:00")
    assert covering.status_code == 201, covering.text
    assert book("09:30", "10:30").status_code == 409, "now every instant of 09:30–10:30 holds two"


def test_a_partial_patch_is_judged_on_the_merged_period(pool) -> None:
    c, admin, book = pool["client"], pool["admin"], pool["book"]
    booking = book("09:00", "10:00").json()["data"]["id"]
    bad = c.patch(f"/api/v1/resource-bookings/{booking}", headers=admin, json={"start_at": "2026-11-02T09:00:00+00:00"})
    assert bad.status_code == 422, bad.text
    assert "must be after start_at" in bad.text
    cleared = c.patch(f"/api/v1/resource-bookings/{booking}", headers=admin, json={"end_at": None})
    assert cleared.status_code == 422
