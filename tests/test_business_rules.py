"""Business rules: four kinds, one lifecycle, one table.

What `policies` and `workflow_definitions` were — and two kinds neither held
— as rows of `business_rules` told apart by `kind` and keyed by scope
(docs/plans/business-rules-refactor-2026-10-06.zh.md). The policy lifecycle
is the shared one: draft, publish with the previous version closed the day
before, `in_force_on`, repeal, visibility, audit. The scoped kinds get their
code generated, so every one of those holds for them with no second
mechanism. The two retired routes stay one release as views.
"""

from __future__ import annotations

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_business_rules.json').read_text(encoding="utf-8"))


import pytest
from fastapi.testclient import TestClient

from app.core.business_date import business_today
from conftest import create, invite_member, make_client, provision_tenant


@pytest.fixture()
def office():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Rules Co", email="admin@rules.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        emp = create(client, admin, "employees", name="Clerk")["id"]
        member = invite_member(client, admin, "clerk", role="member", employee_id=emp)
        flows = invite_member(client, admin, "flows", ["workflows.publish"], employee_id=create(client, admin, "employees", name="Flow Admin")["id"])
        drafter = invite_member(client, admin, "hr_drafter", ["policy.manage"], employee_id=create(client, admin, "employees", name="HR")["id"])

        def publish(who: dict, **fields):
            r = client.post("/api/v1/business-rules/publish", headers=who, json=fields)
            assert r.status_code == 201, r.text
            return r.json()["data"]

        yield {"client": client, "admin": admin, "member": member, "flows": flows, "drafter": drafter,
               "publish": publish, "emp": emp}


# --- identity and scope -------------------------------------------------------------


def test_a_scoped_kind_gets_its_code_from_its_scope(office) -> None:
    c, admin = office["client"], office["admin"]
    drafted = c.post("/api/v1/business-rules", headers=admin, json={
        "kind": "approval_flow", "object_type": "timesheet_header", "body": _ZH_TEXT['TEXT_A65ED888594265CA']})
    assert drafted.status_code == 201, drafted.text
    row = drafted.json()["data"]
    assert row["code"] == "approval_flow:builtin:timesheet_header:default"
    assert row["entity_kind"] == "builtin" and row["name"] == "default" and row["category"] is None
    # the catalog seeded a draft for this scope; drafting adopts it rather than opening a second one
    assert row["status"] == "draft" and row["origin"] == "catalog" and row["version"] == 1
    assert row["title"], "the seed's own title is kept"
    # the next draft of the same scope is the next version of the same code
    again = c.post("/api/v1/business-rules", headers=admin, json={
        "kind": "data_rule", "object_type": "timesheet_header", "body": _ZH_TEXT['TEXT_542AC3EFE772759F']}).json()["data"]
    assert again["code"] == "data_rule:builtin:timesheet_header:default" and again["version"] == 1
    third = c.post("/api/v1/business-rules", headers=admin, json={
        "kind": "approval_flow", "object_type": "timesheet_header", "body": "v2"}).json()["data"]
    assert third["version"] == 2 and third["supersedes_id"] == row["id"]
    assert third["origin"] == "tenant" and third["title"].startswith("timesheet_header"), "a fresh row, titled by its scope"


def test_a_policy_brings_its_own_code_and_category(office) -> None:
    c, admin = office["client"], office["admin"]
    missing = c.post("/api/v1/business-rules", headers=admin, json={"kind": "policy", "title": _ZH_TEXT['TEXT_5FE4E25D932CD06E'], "body": "x"})
    assert missing.status_code == 422 and "code" in missing.json()["detail"]
    no_category = c.post("/api/v1/business-rules", headers=admin, json={
        "kind": "policy", "code": "HR-001", "title": _ZH_TEXT['TEXT_5FE4E25D932CD06E'], "body": "x"})
    assert no_category.status_code == 422 and "category" in no_category.json()["detail"]
    ok = c.post("/api/v1/business-rules", headers=admin, json={
        "kind": "policy", "code": "HR-001", "category": "hr", "title": _ZH_TEXT['TEXT_29DB8FCC1CCF1A6A'], "body": _ZH_TEXT['TEXT_0393212391453B21']})
    assert ok.status_code == 201, ok.text
    assert ok.json()["data"]["object_type"] is None
    # a scoped kind refuses a category: it is classified by kind
    refused = c.post("/api/v1/business-rules", headers=admin, json={
        "kind": "linkage", "object_type": "sales_order", "category": "hr", "body": "x"})
    assert refused.status_code == 422 and "category" in refused.json()["detail"]


def test_a_scope_must_be_a_family_with_a_lifecycle(office) -> None:
    c, admin = office["client"], office["admin"]
    typo = c.post("/api/v1/business-rules", headers=admin, json={
        "kind": "approval_flow", "object_type": "timesheet_headers", "body": "x"})
    assert typo.status_code == 422 and "unknown builtin" in typo.json()["detail"]
    machineless = c.post("/api/v1/business-rules", headers=admin, json={
        "kind": "approval_flow", "object_type": "resource_booking", "body": "x"})
    assert machineless.status_code == 422
    unknown_custom = c.post("/api/v1/business-rules", headers=admin, json={
        "kind": "approval_flow", "entity_kind": "business_object", "object_type": "ghost", "body": "x"})
    assert unknown_custom.status_code == 422 and "neither" in unknown_custom.json()["detail"]
    nothing = c.post("/api/v1/business-rules", headers=admin, json={"kind": "data_rule", "body": "x"})
    assert nothing.status_code == 422 and "object_type" in nothing.json()["detail"]


# --- the shared lifecycle --------------------------------------------------------------


def test_publishing_hands_over_in_one_transaction_for_every_kind(office) -> None:
    c, admin, publish = office["client"], office["admin"], office["publish"]
    first = publish(admin, kind="approval_flow", object_type="expense_claim", body="v1", effective_from="2026-01-01")
    assert first["current"]["status"] == "published" and first["superseded"] is None
    second = publish(admin, kind="approval_flow", object_type="expense_claim", body="v2", effective_from="2026-07-01")
    assert second["current"]["version"] == 2
    assert second["superseded"]["id"] == first["current"]["id"]
    assert second["superseded"]["status"] == "superseded"
    assert second["superseded"]["effective_thru"] == "2026-06-30"
    # the date question reads across versions
    march = c.get("/api/v1/business-rules?kind=approval_flow&object_type=expense_claim&in_force_on=2026-03-15",
                  headers=admin).json()["data"]
    assert [row["version"] for row in march] == [1]
    # twice in one afternoon: the previous one closes on its own first day, not before it began
    # the server's today is the workspace's (ORYH_BUSINESS_TIMEZONE), not this machine's
    today = business_today().isoformat()
    third = publish(admin, kind="data_rule", object_type="expense_claim", body="a")
    fourth = publish(admin, kind="data_rule", object_type="expense_claim", body="b")
    assert third["current"]["effective_from"] == today
    assert fourth["superseded"]["effective_thru"] == today


def test_drafts_are_the_authors_and_the_published_rule_is_everyones(office) -> None:
    c, admin, member, flows = office["client"], office["admin"], office["member"], office["flows"]
    draft = c.post("/api/v1/business-rules", headers=flows, json={
        "kind": "data_rule", "object_type": "timesheet_header", "body": _ZH_TEXT['TEXT_0353328D93B26784']}).json()["data"]
    assert c.get(f"/api/v1/business-rules/{draft['id']}", headers=member).status_code == 404
    assert draft["id"] not in {r["id"] for r in c.get("/api/v1/business-rules", headers=member).json()["data"]}
    assert c.get(f"/api/v1/business-rules/{draft['id']}", headers=flows).status_code == 200
    published = c.post(f"/api/v1/business-rules/{draft['id']}/publish", headers=flows)
    assert published.status_code == 200, published.text
    seen = c.get("/api/v1/business-rules?kind=data_rule&object_type=timesheet_header", headers=member).json()["data"]
    assert [r["id"] for r in seen] == [draft["id"]], "a member reads the data rules of what it files, with no grant"


def test_the_gates_follow_the_kind(office) -> None:
    c, member, flows, drafter = office["client"], office["member"], office["flows"], office["drafter"]
    assert c.post("/api/v1/business-rules", headers=member, json={
        "kind": "approval_flow", "object_type": "timesheet_header", "body": "x"}).status_code == 403
    assert c.post("/api/v1/business-rules", headers=drafter, json={
        "kind": "approval_flow", "object_type": "timesheet_header", "body": "x"}).status_code == 403, \
        "policy.manage drafts policies, not flows"
    assert c.post("/api/v1/business-rules", headers=flows, json={
        "kind": "policy", "code": "HR-9", "category": "hr", "title": "x", "body": "x"}).status_code == 403, \
        "workflows.publish is the three scoped kinds, not policies"
    policy = c.post("/api/v1/business-rules", headers=drafter, json={
        "kind": "policy", "code": "HR-9", "category": "hr", "title": "x", "body": "x"})
    assert policy.status_code == 201, policy.text
    assert c.post(f"/api/v1/business-rules/{policy.json()['data']['id']}/publish", headers=drafter).status_code == 403, \
        "drafting a policy is not publishing it"
    linkage = c.post("/api/v1/business-rules/publish", headers=flows, json={
        "kind": "linkage", "object_type": "sales_order", "body": _ZH_TEXT['TEXT_4CA4C4F3EAF57FAA']})
    assert linkage.status_code == 201, linkage.text


def test_repeal_and_rescope_and_the_audit_trail(office) -> None:
    c, admin, publish = office["client"], office["admin"], office["publish"]
    row = publish(admin, kind="linkage", object_type="sales_order", body=_ZH_TEXT['TEXT_F43130010E4774E5'])["current"]
    closed = c.post(f"/api/v1/business-rules/{row['id']}/visibility", headers=admin,
                    json={"visibility": "restricted", "required_capability": "order.advance"})
    assert closed.status_code == 200 and closed.json()["data"]["visibility"] == "restricted"
    assert c.get(f"/api/v1/business-rules/{row['id']}", headers=office["member"]).status_code == 404
    repealed = c.post(f"/api/v1/business-rules/{row['id']}/repeal", headers=admin, json={"effective_thru": "2026-12-31"})
    assert repealed.status_code == 200 and repealed.json()["data"]["status"] == "repealed"
    actions = {e["action"] for e in c.get("/api/v1/audit-logs?entity_type=business_rule", headers=admin).json()["data"]}
    assert {"linkage.drafted", "linkage.published", "linkage.visibility_changed", "linkage.repealed"} <= actions


# --- what the server does with an approval flow -----------------------------------------


def test_publishing_an_approval_flow_lifts_a_park_and_is_what_the_report_counts(office) -> None:
    c, admin, publish = office["client"], office["admin"], office["publish"]
    before = c.get("/api/v1/workspace/setup-report", headers=admin).json()["data"]["areas"]["expense_claim"]
    assert before["facts"]["workflow_definitions"]["expense_claim"] is False
    publish(admin, kind="approval_flow", object_type="expense_claim", body=_ZH_TEXT['TEXT_8B316FD2FDC42E30'])
    # a data rule alone is not a map: the family is routed by its approval flow only
    publish(admin, kind="data_rule", object_type="purchase_request", body="x")
    after = c.get("/api/v1/workspace/setup-report", headers=admin).json()["data"]["areas"]
    assert after["expense_claim"]["facts"]["workflow_definitions"]["expense_claim"] is True
    assert after["purchase_request"]["facts"]["workflow_definitions"]["purchase_request"] is False


# --- the detail --------------------------------------------------------------------------


def test_the_business_object_detail_carries_its_types_rules(office) -> None:
    c, admin = office["client"], office["admin"]
    assert c.post("/api/v1/object-type-definitions", headers=admin, json={
        "object_type": "warranty_card", "json_schema": {}}).status_code == 201
    card = create(c, admin, "business-objects", object_type="warranty_card", title="WC-1")
    c.post("/api/v1/business-rules/publish", headers=admin, json={
        "kind": "approval_flow", "entity_kind": "business_object", "object_type": "warranty_card", "body": _ZH_TEXT['TEXT_BC63F69D49C76AC2']})
    c.post("/api/v1/business-rules/publish", headers=admin, json={
        "kind": "data_rule", "entity_kind": "business_object", "object_type": "warranty_card", "body": _ZH_TEXT['TEXT_2E98589F848F8B1D']})
    detail = c.get(f"/api/v1/business-objects/{card['id']}/detail", headers=admin).json()["data"]
    assert [r["body"] for r in detail["rules"] if r["kind"] == "approval_flow"] == [_ZH_TEXT['TEXT_BC63F69D49C76AC2']]
    assert sorted(r["kind"] for r in detail["rules"]) == ["approval_flow", "data_rule"]


# --- the shipped catalog ----------------------------------------------------------------


def test_a_new_workspace_starts_with_seeded_drafts_nobody_can_act_on_yet(office) -> None:
    c, admin, member, flows = office["client"], office["admin"], office["member"], office["flows"]
    seeded = c.get("/api/v1/business-rules?status=draft&origin=catalog", headers=admin).json()["data"]
    assert seeded, "provisioning seeded the catalog"
    assert {r["kind"] for r in seeded} == {"approval_flow", "data_rule", "linkage"}
    assert all(r["status"] == "draft" and r["origin"] == "catalog" and r["catalog_hash"] for r in seeded)
    assert "expense_claim" in {r["object_type"] for r in seeded if r["kind"] == "approval_flow"}
    # drafts are the authors' — a member reads nothing, the flow publisher reads them all
    assert c.get("/api/v1/business-rules?status=draft&origin=catalog", headers=member).json()["data"] == []
    assert len(c.get("/api/v1/business-rules?status=draft&origin=catalog", headers=flows).json()["data"]) == len(seeded)
    # and a seed is published like any draft: read it, change a sentence, publish
    draft = next(r for r in seeded if r["kind"] == "approval_flow" and r["object_type"] == "expense_claim")
    edited = c.patch(f"/api/v1/business-rules/{draft['id']}", headers=flows, json={"body": _ZH_TEXT['TEXT_F9AFF14841589F6B']})
    assert edited.status_code == 200, edited.text
    published = c.post(f"/api/v1/business-rules/{draft['id']}/publish", headers=flows)
    assert published.status_code == 200, published.text
    assert published.json()["data"]["current"]["origin"] == "catalog"
    report = c.get("/api/v1/workspace/setup-report", headers=admin).json()["data"]["areas"]
    assert report["expense_claim"]["facts"]["workflow_definitions"]["expense_claim"] is True
