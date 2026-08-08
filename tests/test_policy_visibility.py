"""制度的读取门禁 — the second gated read in this API, after pay.

The handbook and the 薪酬管理办法 live in the same table and want opposite
things. So the gate has three jobs and is only worth what its weakest one is:

- an INTERNAL policy is readable by anyone here, with no capability at all. A
  handbook nobody may open is not a handbook, and a gate that got this wrong by
  being cautious would be just as broken as one that leaked.
- a RESTRICTED policy is readable only by whoever holds the capability the row
  names.
- a DRAFT is readable only by its authors. This is the one people forget: the
  draft 裁员方案 is more dangerous than the published one, because it says what
  is coming before anyone has decided.

Every path is checked from both sides, and the counts are checked too — how
many restricted policies exist is itself worth hiding.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.services.emails import outbox

from conftest import make_client

from conftest import provision_tenant as bootstrap_tenant


def token_from(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError("no token in email")


@pytest.fixture()
def workspace() -> Generator[dict, None, None]:
    """One tenant, four documents, three credentials:

    - `hr`       the tenant service key (bypasses permissions by design)
    - `manager`  holds `payroll.read` only — sees the restricted 薪酬管理办法
    - `staff`    holds nothing relevant — sees the handbook and nothing else
    """
    with make_client([]) as client:
        data = bootstrap_tenant(client, company_name="Rule Co", email="admin@rule-co.com", password="rule-pass1234")
        hr = {"X-API-Key": data["plain_text_api_key"]}

        def invite(email: str, role: str, permissions: list[str]) -> dict:
            client.post("/api/v1/roles", json={"name": role, "permissions": permissions},
                        headers=hr)
            user_id = client.post(
                "/api/v1/auth/invitations", json={"email": email, "role": role}, headers=hr
            ).json()["data"]["id"]
            client.post(
                "/api/v1/auth/invitations/accept",
                json={"token": token_from(outbox.messages[-1].body), "password": "invitee-pass1"},
            )
            key = client.post(
                "/api/v1/tenant/api-keys", json={"label": role, "user_id": user_id}, headers=hr
            ).json()["data"]["plain_text_api_key"]
            return {"X-API-Key": key}

        manager = invite("manager@rule-co.com", "pay_viewer", ["payroll.read"])
        staff = invite("staff@rule-co.com", "plain_member", ["todos.complete_own"])

        def make(code: str, title: str, category: str, publish: bool = True, **extra) -> dict:
            body = {"code": code, "category": category, "title": title, "body": f"# {title}"}
            body.update(extra)
            made = client.post("/api/v1/policies", json=body, headers=hr).json()["data"]
            if publish:
                made = client.post(
                    f"/api/v1/policies/{made['id']}/publish",
                    json={"effective_from": "2026-01-01"}, headers=hr,
                ).json()["data"]["current"]
            return made

        handbook = make("HR-001", "员工手册", "hr",
                        rules_json={"leave": {"annual_days": 10}})
        # the figures ride the document, so gating the document gates them
        pay_rules = make("PAY-001", "薪酬管理办法", "payroll",
                         visibility="restricted", required_capability="payroll.read",
                         rules_json={"bonus": {"pool_rate": 0.15}})
        layoffs = make("HR-900", "组织调整方案", "hr", publish=False)
        repealed = make("FIN-OLD", "旧差旅标准", "expense")
        client.post(f"/api/v1/policies/{repealed['id']}/repeal", json={}, headers=hr)

        yield {
            "client": client, "hr": hr, "manager": manager, "staff": staff,
            "handbook": handbook, "pay_rules": pay_rules, "layoffs": layoffs,
            "repealed": repealed,
        }


def codes(client: TestClient, headers: dict) -> set[str]:
    return {row["code"] for row in client.get("/api/v1/policies", headers=headers).json()["data"]}


def test_the_handbook_is_readable_without_any_capability(workspace: dict) -> None:
    """The failure mode worth naming: a gate so cautious that the handbook
    becomes unreadable is just as broken as one that leaks the salary policy."""
    client, staff = workspace["client"], workspace["staff"]
    assert "HR-001" in codes(client, staff)
    detail = client.get(f"/api/v1/policies/{workspace['handbook']['id']}", headers=staff)
    assert detail.status_code == 200
    assert detail.json()["data"]["body"].startswith("# 员工手册")


def test_a_restricted_policy_needs_the_capability_it_names(workspace: dict) -> None:
    client = workspace["client"]
    assert "PAY-001" in codes(client, workspace["manager"])
    assert "PAY-001" not in codes(client, workspace["staff"])

    # 404 rather than 403 — that a 薪酬管理办法 exists is part of what it hides
    assert client.get(
        f"/api/v1/policies/{workspace['pay_rules']['id']}", headers=workspace["staff"]
    ).status_code == 404
    assert client.get(
        f"/api/v1/policies/{workspace['pay_rules']['id']}", headers=workspace["manager"]
    ).status_code == 200


def test_a_draft_is_invisible_to_everyone_but_its_authors(workspace: dict) -> None:
    """The draft 组织调整方案 says what is coming before anyone has decided."""
    client = workspace["client"]
    for headers in (workspace["staff"], workspace["manager"]):
        assert "HR-900" not in codes(client, headers)
        assert client.get(
            f"/api/v1/policies/{workspace['layoffs']['id']}", headers=headers
        ).status_code == 404
    assert "HR-900" in codes(client, workspace["hr"])


def test_a_repealed_policy_leaves_the_handbook(workspace: dict) -> None:
    """Leaving it visible is how somebody follows a rule that no longer
    applies."""
    client = workspace["client"]
    assert "FIN-OLD" not in codes(client, workspace["staff"])
    # ...but it is not deleted: what people were told, and until when, survives
    assert "FIN-OLD" in codes(client, workspace["hr"])


def test_the_figures_are_gated_with_the_document_that_carries_them(workspace: dict) -> None:
    """`rules_json` rides the policy row, so there is no separate surface to
    gate — and no way to read a restricted 薪酬管理办法 one number at a time,
    which a rule table would have offered."""
    client = workspace["client"]

    def rules_seen(headers: dict) -> dict:
        return {
            row["code"]: row.get("rules_json")
            for row in client.get("/api/v1/policies", headers=headers).json()["data"]
        }

    staff = rules_seen(workspace["staff"])
    assert staff == {"HR-001": {"leave": {"annual_days": 10}}}

    manager = rules_seen(workspace["manager"])
    assert manager["PAY-001"] == {"bonus": {"pool_rate": 0.15}}

def test_the_count_is_filtered_not_just_the_rows(workspace: dict) -> None:
    """Paging through a list whose total includes documents you cannot see is
    itself a leak — how many restricted policies exist is worth hiding."""
    client = workspace["client"]

    def total(headers: dict) -> int:
        body = client.get("/api/v1/policies?page=1&size=1", headers=headers).json()
        return body["meta"]["total"]

    assert total(workspace["hr"]) == 4          # handbook, pay, draft, repealed
    assert total(workspace["manager"]) == 2     # handbook + pay
    assert total(workspace["staff"]) == 1       # handbook only


def test_writing_a_policy_needs_the_capability(workspace: dict) -> None:
    client, staff = workspace["client"], workspace["staff"]
    refused = client.post(
        "/api/v1/policies",
        json={"code": "X-1", "category": "hr", "title": "自封的制度", "body": "x"},
        headers=staff,
    )
    assert refused.status_code == 403
    assert "policy.manage" in refused.json()["detail"]

    # and publishing is a separate grant from drafting
    made = client.post(
        "/api/v1/policies",
        json={"code": "X-2", "category": "hr", "title": "草稿", "body": "x"},
        headers=workspace["hr"],
    ).json()["data"]
    assert client.post(
        f"/api/v1/policies/{made['id']}/publish", json={}, headers=staff
    ).status_code == 403
