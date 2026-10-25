"""Policy read access — the second gated read in this API, after pay.

The handbook and the compensation policy live in the same table and want opposite
things. So the gate has three jobs and is only worth what its weakest one is:

- an INTERNAL policy is readable by anyone here, with no capability at all. A
  handbook nobody may open is not a handbook, and a gate that got this wrong by
  being cautious would be just as broken as one that leaked.
- a RESTRICTED policy is readable only by whoever holds the capability the row
  names.
- a DRAFT is readable only by its authors. This is the one people forget: the
  draft redundancy plan is more dangerous than the published one, because it says what
  is coming before anyone has decided.

Every path is checked from both sides, and the counts are checked too — how
many restricted policies exist is itself worth hiding.
"""

from __future__ import annotations

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_policy_visibility.json').read_text(encoding="utf-8"))


from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


from conftest import invite_member, make_client

from conftest import provision_tenant as bootstrap_tenant


@pytest.fixture()
def workspace() -> Generator[dict, None, None]:
    """One tenant, four documents, three credentials:

    - `hr`       the tenant service key (bypasses permissions by design)
    - `manager`  holds `payroll.read` only — sees the restricted compensation policy
    - `staff`    holds nothing relevant — sees the handbook and nothing else
    """
    with make_client([]) as client:
        data = bootstrap_tenant(client, company_name="Rule Co", email="admin@rule-co.com", password="rule-pass1234")
        hr = {"X-API-Key": data["plain_text_api_key"]}

        def invite(email: str, role: str, permissions: list[str]) -> dict:
            return dict(invite_member(client, hr, role, permissions, email=email))

        manager = invite("manager@rule-co.com", "pay_viewer", ["payroll.read"])
        staff = invite("staff@rule-co.com", "plain_member", ["todos.complete_own"])

        def make(code: str, title: str, category: str, publish: bool = True, **extra) -> dict:
            body = {"code": code, "category": category, "title": title, "body": f"# {title}"}
            body.update(extra)
            made = client.post("/api/v1/business-rules", json={"kind": "policy", **body}, headers=hr).json()["data"]
            if publish:
                made = client.post(
                    f"/api/v1/business-rules/{made['id']}/publish",
                    json={"effective_from": "2026-01-01"}, headers=hr,
                ).json()["data"]["current"]
            return made

        handbook = make("HR-001", _ZH_TEXT['TEXT_29DB8FCC1CCF1A6A'], "hr",
                        rules_json={"leave": {"annual_days": 10}})
        # the figures ride the document, so gating the document gates them
        pay_rules = make("PAY-001", _ZH_TEXT['TEXT_6EB14D5B59109360'], "payroll",
                         visibility="restricted", required_capability="payroll.read",
                         rules_json={"bonus": {"pool_rate": 0.15}})
        layoffs = make("HR-900", _ZH_TEXT['TEXT_5D96C765DDD96D1D'], "hr", publish=False)
        repealed = make("FIN-OLD", _ZH_TEXT['TEXT_07EC8AB5CDDD8083'], "expense")
        client.post(f"/api/v1/business-rules/{repealed['id']}/repeal", json={}, headers=hr)

        yield {
            "client": client, "hr": hr, "manager": manager, "staff": staff,
            "handbook": handbook, "pay_rules": pay_rules, "layoffs": layoffs,
            "repealed": repealed,
        }


def codes(client: TestClient, headers: dict) -> set[str]:
    return {row["code"] for row in client.get("/api/v1/business-rules?kind=policy", headers=headers).json()["data"]}


def test_the_handbook_is_readable_without_any_capability(workspace: dict) -> None:
    """The failure mode worth naming: a gate so cautious that the handbook
    becomes unreadable is just as broken as one that leaks the salary policy."""
    client, staff = workspace["client"], workspace["staff"]
    assert "HR-001" in codes(client, staff)
    detail = client.get(f"/api/v1/business-rules/{workspace['handbook']['id']}", headers=staff)
    assert detail.status_code == 200
    assert detail.json()["data"]["body"].startswith(_ZH_TEXT['TEXT_43EE074329335B51'])


def test_a_restricted_policy_needs_the_capability_it_names(workspace: dict) -> None:
    client = workspace["client"]
    assert "PAY-001" in codes(client, workspace["manager"])
    assert "PAY-001" not in codes(client, workspace["staff"])

    # 404 rather than 403 — that a compensation policy exists is part of what it hides
    assert client.get(
        f"/api/v1/business-rules/{workspace['pay_rules']['id']}", headers=workspace["staff"]
    ).status_code == 404
    assert client.get(
        f"/api/v1/business-rules/{workspace['pay_rules']['id']}", headers=workspace["manager"]
    ).status_code == 200


def test_a_draft_is_invisible_to_everyone_but_its_authors(workspace: dict) -> None:
    """The draft reorganization plan says what is coming before anyone has decided."""
    client = workspace["client"]
    for headers in (workspace["staff"], workspace["manager"]):
        assert "HR-900" not in codes(client, headers)
        assert client.get(
            f"/api/v1/business-rules/{workspace['layoffs']['id']}", headers=headers
        ).status_code == 404
    assert "HR-900" in codes(client, workspace["hr"])


def test_a_repealed_policy_leaves_the_handbook(workspace: dict) -> None:
    """Leaving it visible is how somebody follows a rule that no longer
    applies."""
    client = workspace["client"]
    assert "FIN-OLD" not in codes(client, workspace["staff"])
    # ...but it is not deleted: what people were told, and until when, survives
    assert "FIN-OLD" in codes(client, workspace["hr"])


def test_what_governed_a_date_is_readable_by_whoever_could_read_it_then(workspace: dict) -> None:
    """"What were the rules in March" is an employee's question too. A repealed
    policy answers the date question and is fetchable by id — it is only the
    default list, the handbook of what applies now, that it has left."""
    client, staff = workspace["client"], workspace["staff"]
    # repealed today (effective_thru defaulted to today), so it governed January
    then = client.get("/api/v1/business-rules?in_force_on=2026-01-15", headers=staff).json()["data"]
    assert "FIN-OLD" in {row["code"] for row in then}
    assert client.get(f"/api/v1/business-rules/{workspace['repealed']['id']}", headers=staff).status_code == 200
    # a draft stays the authors' alone, on any read
    assert client.get(f"/api/v1/business-rules/{workspace['layoffs']['id']}", headers=staff).status_code == 404


def test_the_figures_are_gated_with_the_document_that_carries_them(workspace: dict) -> None:
    """`rules_json` rides the policy row, so there is no separate surface to
    gate — and no way to read a restricted compensation policy one number at a time,
    which a rule table would have offered."""
    client = workspace["client"]

    def rules_seen(headers: dict) -> dict:
        return {
            row["code"]: row.get("rules_json")
            for row in client.get("/api/v1/business-rules?kind=policy", headers=headers).json()["data"]
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
        body = client.get("/api/v1/business-rules?kind=policy&page=1&size=1", headers=headers).json()
        return body["meta"]["total"]

    assert total(workspace["hr"]) == 4          # handbook, pay, draft, repealed
    assert total(workspace["manager"]) == 2     # handbook + pay
    assert total(workspace["staff"]) == 1       # handbook only


def test_writing_a_policy_needs_the_capability(workspace: dict) -> None:
    client, staff = workspace["client"], workspace["staff"]
    refused = client.post(
        "/api/v1/business-rules",
        json={"kind": "policy", "code": "X-1", "category": "hr", "title": _ZH_TEXT['TEXT_578622B572E27C8C'], "body": "x"},
        headers=staff,
    )
    assert refused.status_code == 403
    assert "policy.manage" in refused.json()["detail"]

    # and publishing is a separate grant from drafting
    made = client.post(
        "/api/v1/business-rules",
        json={"kind": "policy", "code": "X-2", "category": "hr", "title": _ZH_TEXT['TEXT_2A2FD29BD27A6EB9'], "body": "x"},
        headers=workspace["hr"],
    ).json()["data"]
    assert client.post(
        f"/api/v1/business-rules/{made['id']}/publish", json={}, headers=staff
    ).status_code == 403


def test_a_published_policy_can_be_closed_without_being_repealed(workspace: dict) -> None:
    """The case that had no remedy. A rule published to the whole company that
    should have been restricted could not be edited (409), could not be deleted
    (published policies never are), and repealing it would retire a rule that
    is still in force — so the only way to stop people reading it was to stop
    applying it."""
    client, hr, staff = workspace["client"], workspace["hr"], workspace["staff"]
    handbook = workspace["handbook"]
    assert "HR-001" in codes(client, staff)

    # the edit is still refused, and now says where to go instead
    frozen = client.patch(
        f"/api/v1/business-rules/{handbook['id']}",
        json={"visibility": "restricted", "required_capability": "payroll.read"},
        headers=hr,
    )
    assert frozen.status_code == 409
    assert "/visibility" in frozen.json()["detail"]

    rescoped = client.post(
        f"/api/v1/business-rules/{handbook['id']}/visibility",
        json={"visibility": "restricted", "required_capability": "payroll.read",
              "note": _ZH_TEXT['TEXT_E17B02791DF3F195']},
        headers=hr,
    )
    assert rescoped.status_code == 200, rescoped.text
    assert rescoped.json()["data"]["visibility"] == "restricted"

    assert "HR-001" not in codes(client, staff)
    assert "HR-001" in codes(client, workspace["manager"])
    # still in force: closing the reading must not have retired the rule
    assert rescoped.json()["data"]["status"] == "published"


def test_rescoping_never_touches_what_the_rule_says(workspace: dict) -> None:
    """The half that stays frozen. If this call could move a word of the body,
    it would be the in-place edit the freeze exists to prevent, wearing a
    different name."""
    client, hr = workspace["client"], workspace["hr"]
    handbook = workspace["handbook"]
    before = client.get(f"/api/v1/business-rules/{handbook['id']}", headers=hr).json()["data"]

    client.post(
        f"/api/v1/business-rules/{handbook['id']}/visibility",
        json={"visibility": "public"}, headers=hr,
    )
    after = client.get(f"/api/v1/business-rules/{handbook['id']}", headers=hr).json()["data"]

    for field in ("code", "version", "title", "body", "rules_json",
                  "effective_from", "effective_thru", "published_at", "status"):
        assert after[field] == before[field], f"{field} moved"


def test_a_superseded_version_is_closable_after_the_fact(workspace: dict) -> None:
    """Where it matters most. A superseded version stays readable to whoever
    could read it, so one that should never have been broadly visible has to be
    closable once somebody notices."""
    client, hr, staff = workspace["client"], workspace["hr"], workspace["staff"]
    v2 = client.post(
        "/api/v1/business-rules",
        json={"kind": "policy", "code": "HR-001", "category": "hr", "title": _ZH_TEXT['TEXT_8FC1004561AFA499'], "body": "# v2"},
        headers=hr,
    ).json()["data"]
    client.post(f"/api/v1/business-rules/{v2['id']}/publish",
                json={"effective_from": "2026-06-01"}, headers=hr)

    old = client.get(f"/api/v1/business-rules/{workspace['handbook']['id']}", headers=hr).json()["data"]
    assert old["status"] == "superseded"

    closed = client.post(
        f"/api/v1/business-rules/{old['id']}/visibility",
        json={"visibility": "restricted", "required_capability": "payroll.read"},
        headers=hr,
    )
    assert closed.status_code == 200, closed.text
    visible = {
        row["id"] for row in client.get("/api/v1/business-rules?status=superseded",
                                        headers=staff).json()["data"]
    }
    assert old["id"] not in visible


def test_rescoping_is_a_publisher_act_and_is_audited(workspace: dict) -> None:
    """Drafting and publishing are separate capabilities because publishing is
    an authority act. Deciding who may read a published rule is the same kind
    of act, and leaves the same kind of trace."""
    client, hr = workspace["client"], workspace["hr"]
    drafter = {"X-API-Key": client.post(
        "/api/v1/tenant/api-keys", json={"label": "drafter-probe"}, headers=hr
    ).json()["data"]["plain_text_api_key"]}
    drafter = dict(invite_member(client, hr, "drafter", ["policy.manage"], email="drafter@rule-co.com"))

    refused = client.post(
        f"/api/v1/business-rules/{workspace['handbook']['id']}/visibility",
        json={"visibility": "public"}, headers=drafter,
    )
    assert refused.status_code == 403
    assert "policy.publish" in refused.json()["detail"]

    client.post(
        f"/api/v1/business-rules/{workspace['handbook']['id']}/visibility",
        json={"visibility": "restricted", "required_capability": "payroll.read",
              "note": _ZH_TEXT['TEXT_9C021C58A04B9471']},
        headers=hr,
    )
    trail = client.get("/api/v1/audit-logs?action=policy.visibility_changed",
                       headers=hr).json()
    assert trail["meta"]["total"] == 1
    detail = trail["data"][0]["detail"]
    assert detail["from"]["visibility"] == "internal"
    assert detail["to"] == {"visibility": "restricted", "required_capability": "payroll.read"}
    assert detail["note"] == _ZH_TEXT['TEXT_9C021C58A04B9471']


def test_a_restricted_rescope_must_still_name_its_capability(workspace: dict) -> None:
    """The same shape check the write path applies: restricted-and-nameless is
    readable by everyone, which is the opposite of what it says."""
    client, hr = workspace["client"], workspace["hr"]
    bad = client.post(
        f"/api/v1/business-rules/{workspace['handbook']['id']}/visibility",
        json={"visibility": "restricted"}, headers=hr,
    )
    assert bad.status_code == 422
    assert "required_capability" in bad.json()["detail"]


def test_every_policy_lifecycle_act_leaves_a_trail(workspace: dict) -> None:
    """None of these were being written. `record_audit` adds to the caller's
    transaction — "committed if and only if the business write commits" — and
    all four policy endpoints called it AFTER their own `db.commit()`, so the
    row went into a session nothing committed again and was dropped at request
    end. Drafting, publishing, re-scoping and repealing a company rule are
    exactly the acts a trail exists for, and the trail was empty.

    No test looked, which is why it survived: each endpoint was checked for the
    state it produced and never for the record of having produced it."""
    client, hr = workspace["client"], workspace["hr"]

    drafted = client.post(
        "/api/v1/business-rules",
        json={"code": "AUD-1", "category": "hr", "title": _ZH_TEXT['TEXT_3E7D87804AF60EE8'], "body": "# t"},
        headers=hr,
    ).json()["data"]
    client.post(f"/api/v1/business-rules/{drafted['id']}/publish",
                json={"effective_from": "2026-03-01"}, headers=hr)
    client.post(f"/api/v1/business-rules/{drafted['id']}/visibility",
                json={"visibility": "public"}, headers=hr)
    client.post(f"/api/v1/business-rules/{drafted['id']}/repeal", json={}, headers=hr)

    for action in ("policy.drafted", "policy.published",
                   "policy.visibility_changed", "policy.repealed"):
        rows = client.get(
            f"/api/v1/audit-logs?action={action}&entity_id={drafted['id']}", headers=hr
        ).json()
        assert rows["meta"]["total"] == 1, f"{action} wrote no audit row"
        assert rows["data"][0]["detail"]["code"] == "AUD-1"


def test_a_rescope_that_changes_nothing_writes_no_audit(workspace: dict) -> None:
    """The trail should read as a list of decisions. Re-sending the visibility
    a policy already has is a retry, not a decision."""
    client, hr = workspace["client"], workspace["hr"]
    pay_rules = workspace["pay_rules"]
    same = client.post(
        f"/api/v1/business-rules/{pay_rules['id']}/visibility",
        json={"visibility": "restricted", "required_capability": "payroll.read"},
        headers=hr,
    )
    assert same.status_code == 200
    rows = client.get(
        f"/api/v1/audit-logs?action=policy.visibility_changed&entity_id={pay_rules['id']}",
        headers=hr,
    ).json()
    assert rows["meta"]["total"] == 0
