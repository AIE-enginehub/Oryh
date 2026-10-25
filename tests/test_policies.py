"""company policies — a published rule of the house, and the number an agent may act on.

Two things have to hold here and they pull in opposite directions.

A policy must be *readable*: an employee handbook nobody may open is not a
handbook, so an internal policy needs no capability at all. And a policy must be
*withholdable*: a draft redundancy plan and a compensation policy are the two documents a
workspace most wants unread, and "everyone in the tenant" is the wrong audience
for both.

There is no separate table for the figures inside a policy. That shape exists in
traditional systems because their consumer cannot read prose; ours can, and a
second table would only be a second source of truth free to drift from the body.
A workspace that wants the numbers in a machine shape puts them in `rules_json`
on the same row — versioned, published and frozen with the document, and never
parsed by the server.
"""

from __future__ import annotations

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_policies.json').read_text(encoding="utf-8"))


from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


from conftest import seeded_tenants

TEST_TENANT = "cccccccc-8888-4888-8888-cccccccccccc"
TEST_API_KEY = "policy-test-key"
HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    yield from seeded_tenants((TEST_TENANT, "Policy Co", TEST_API_KEY))


def post(client: TestClient, path: str, body: dict, expect: int = 201) -> dict:
    response = client.post(path, json=body, headers=HEADERS)
    assert response.status_code == expect, response.text
    return response.json()["data"] if expect < 400 else response.json()


def draft(client: TestClient, expect: int = 201, **overrides) -> dict:
    body = {
        "code": "HR-001",
        "category": "hr",
        "title": _ZH_TEXT['TEXT_29DB8FCC1CCF1A6A'],
        "body": _ZH_TEXT['TEXT_DBA08A0930C1C1BF'],
    }
    body.update(overrides)
    return post(client, "/api/v1/business-rules", {"kind": "policy", **body}, expect=expect)


def publish(client: TestClient, policy_id: str, expect: int = 200, **body) -> dict:
    response = client.post(f"/api/v1/business-rules/{policy_id}/publish", json=body, headers=HEADERS)
    assert response.status_code == expect, response.text
    return response.json()["data"] if expect < 400 else response.json()


def test_a_policy_starts_as_a_draft_and_publishing_is_a_separate_act(client: TestClient) -> None:
    made = draft(client)
    assert made["status"] == "draft"
    assert made["version"] == 1
    assert made["published_at"] is None

    live = publish(client, made["id"], effective_from="2026-02-01")
    assert live["current"]["status"] == "published"
    assert live["current"]["effective_from"] == "2026-02-01"
    assert live["current"]["published_by"] is not None
    assert live["superseded"] is None


def test_a_new_version_closes_the_previous_one_the_day_before(client: TestClient) -> None:
    """The same handover POST /pay-histories performs, and for the same reason:
    a policy history with a gap in it cannot answer what applied in March."""
    first = draft(client)
    publish(client, first["id"], effective_from="2026-01-01")

    second = draft(client, title=_ZH_TEXT['TEXT_247E579370ACFF82'], body=_ZH_TEXT['TEXT_1BE1552AE2968489'])
    assert second["version"] == 2
    assert second["supersedes_id"] == first["id"]

    change = publish(client, second["id"], effective_from="2026-07-01")
    assert change["superseded"]["id"] == first["id"]
    assert change["superseded"]["status"] == "superseded"
    assert change["superseded"]["effective_thru"] == "2026-06-30"
    assert change["current"]["effective_from"] == "2026-07-01"


def test_what_applied_in_march_is_answerable(client: TestClient) -> None:
    """Status is a marker; the dates are the truth. v1 is `superseded` today and
    is still the document that governed March."""
    first = draft(client)
    publish(client, first["id"], effective_from="2026-01-01")
    second = draft(client, title=_ZH_TEXT['TEXT_247E579370ACFF82'], body=_ZH_TEXT['TEXT_3C2E8A4C055A5B4E'])
    publish(client, second["id"], effective_from="2026-07-01")

    def in_force(on: str) -> list[int]:
        rows = client.get(f"/api/v1/business-rules?in_force_on={on}", headers=HEADERS).json()["data"]
        return [row["version"] for row in rows]

    assert in_force("2026-03-15") == [1]
    assert in_force("2026-08-15") == [2]


def test_only_one_published_version_per_code(client: TestClient) -> None:
    """Two documents both claiming to be the current expense policy is the failure
    this table exists to prevent — and it is held by the database, not by the
    publish endpoint's good manners. Poke the old version back to `published`
    behind the API and the index refuses."""
    from sqlalchemy.exc import IntegrityError

    from app.db.session import get_db
    from app.main import app
    from app.models import Policy

    first = draft(client)
    publish(client, first["id"], effective_from="2026-01-01")
    second = draft(client, title="v2", body="v2")
    publish(client, second["id"], effective_from="2026-07-01")

    # via the ORM rather than raw SQL: SQLite stores the UUID without hyphens,
    # so a hand-written `where id = '<api id>'` matches nothing and the test
    # would pass while asserting exactly nothing
    db = next(app.dependency_overrides[get_db]())
    try:
        row = db.get(Policy, first["id"])
        assert row is not None and row.status == "superseded"
        row.status = "published"
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_a_published_policy_is_not_edited_in_place(client: TestClient) -> None:
    made = draft(client)
    publish(client, made["id"])

    response = client.patch(
        f"/api/v1/business-rules/{made['id']}", json={"body": _ZH_TEXT['TEXT_3A42E31C94919B62']}, headers=HEADERS
    )
    assert response.status_code == 409
    assert "new version" in response.json()["detail"]

    # ...and it is repealed rather than deleted, because people acted on it
    deleted = client.delete(f"/api/v1/business-rules/{made['id']}", headers=HEADERS)
    assert deleted.status_code == 409
    assert "repeal" in deleted.json()["detail"]

    repealed = post(client, f"/api/v1/business-rules/{made['id']}/repeal",
                    {"effective_thru": "2026-12-31"}, expect=200)
    assert repealed["status"] == "repealed"
    assert repealed["effective_thru"] == "2026-12-31"


def test_repealing_a_superseded_version_would_punch_a_hole(client: TestClient) -> None:
    """Found by a black-box step that expected a 409 and got a 200.

    v1 was closed at 2026-06-30 when v2 took over from 2026-07-01. Repealing v1
    as of 2026-03-31 would move that date, and then nothing at all governs April
    through June — `in_force_on` returns an empty list and no other check
    notices."""
    first = draft(client)
    publish(client, first["id"], effective_from="2026-01-01")
    second = draft(client, title="v2", body="v2")
    publish(client, second["id"], effective_from="2026-07-01")

    refused = post(client, f"/api/v1/business-rules/{first['id']}/repeal",
                   {"effective_thru": "2026-03-31"}, expect=409)
    assert "gap in the history" in refused["detail"]

    # the handover date is untouched, so every month still has a governing version
    for on, version in (("2026-03-15", 1), ("2026-06-30", 1), ("2026-07-01", 2)):
        rows = client.get(f"/api/v1/business-rules?in_force_on={on}", headers=HEADERS).json()["data"]
        assert [row["version"] for row in rows] == [version], on

    # ...and repealing the CURRENT version is still the ordinary case
    repealed = post(client, f"/api/v1/business-rules/{second['id']}/repeal",
                    {"effective_thru": "2026-12-31"}, expect=200)
    assert repealed["status"] == "repealed"


def test_a_draft_is_still_editable_and_deletable(client: TestClient) -> None:
    made = draft(client)
    edited = client.patch(
        f"/api/v1/business-rules/{made['id']}", json={"title": _ZH_TEXT['TEXT_33A218B557B0AC04']}, headers=HEADERS
    )
    assert edited.status_code == 200
    assert edited.json()["data"]["title"] == _ZH_TEXT['TEXT_33A218B557B0AC04']
    assert client.delete(f"/api/v1/business-rules/{made['id']}", headers=HEADERS).status_code == 204


def test_a_restricted_policy_must_name_who_may_read_it(client: TestClient) -> None:
    """One that names nothing is readable by everyone, which is the opposite of
    what it says."""
    body = draft(client, code="HR-002", visibility="restricted", expect=422)
    assert "required_capability" in body["detail"]

    ok = draft(client, code="HR-002", title=_ZH_TEXT['TEXT_6EB14D5B59109360'], category="payroll",
               visibility="restricted", required_capability="payroll.read")
    assert ok["required_capability"] == "payroll.read"


def test_the_category_vocabulary_is_gated(client: TestClient) -> None:
    body = draft(client, category="invented_category", expect=422)
    assert "external_standard" in body["detail"]


def _audit_policy_checks() -> list[tuple[str, str]]:
    """The policy invariants out of scripts/data_integrity_audit.py, loaded
    textually because scripts/ is not an importable package."""
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "data_integrity_audit.py"
    text = source.read_text(encoding="utf-8")
    # everything above main(), so the helpers the check SQL is built from come
    # along with it — slicing at STRUCTURAL_CHECKS would leave them undefined
    namespace: dict = {"__file__": str(source)}
    exec(text[: text.index("def main()")], namespace)
    return [(name, sql) for name, sql in namespace["STRUCTURAL_CHECKS"] if "business_rules" in sql]


def test_repealing_the_current_version_while_the_next_is_a_draft_is_ordinary(client: TestClient) -> None:
    """The audit's "only the newest version is repealed" once counted a DRAFT
    as a newer version, so this legal sequence read as a hole in the history."""
    from sqlalchemy import text as sql_text

    from app.db.session import get_db
    from app.main import app

    first = draft(client)
    publish(client, first["id"], effective_from="2026-01-01")
    draft(client, title="v2 in the making", body="v2")
    repealed = post(client, f"/api/v1/business-rules/{first['id']}/repeal",
                    {"effective_thru": "2026-09-30"}, expect=200)
    assert repealed["status"] == "repealed"
    newest = next(sql for name, sql in _audit_policy_checks() if "newest version" in name)
    db = next(app.dependency_overrides[get_db]())
    try:
        assert db.execute(sql_text(newest)).scalar() == 0
    finally:
        db.close()


def test_the_integrity_audits_policy_invariants_hold_on_real_policies(client: TestClient) -> None:
    """The audit is a script — nothing imports it, so nothing else notices it
    drifting from the schema. Build a workspace exercising every shape a policy
    has, then run the audit's own SQL over it."""
    from sqlalchemy import text as sql_text

    from app.db.session import get_db
    from app.main import app

    handbook = draft(client)
    publish(client, handbook["id"], effective_from="2026-01-01")
    revised = draft(client, title=_ZH_TEXT['TEXT_5AA97CF0AD67B1C0'], body=_ZH_TEXT['TEXT_3C2E8A4C055A5B4E'])
    publish(client, revised["id"], effective_from="2026-07-01")

    pay = draft(client, code="PAY-001", category="payroll", title=_ZH_TEXT['TEXT_6EB14D5B59109360'],
                visibility="restricted", required_capability="payroll.read")
    publish(client, pay["id"])

    draft(client, code="FIN-2026-03", category="external_standard",
          title=_ZH_TEXT['TEXT_BE3F09F7F1CEDAC5'],
          body=_ZH_TEXT['TEXT_F28899D3BF3B52B5'],
          rules_json={"social_insurance": {"base": {"cap": 36921, "floor": 7384}},
                      "housing_fund": {"base": {"cap": 36921, "floor": 2690}}})

    old = draft(client, code="FIN-OLD", category="expense", title=_ZH_TEXT['TEXT_07EC8AB5CDDD8083'])
    publish(client, old["id"], effective_from="2025-01-01")
    post(client, f"/api/v1/business-rules/{old['id']}/repeal", {"effective_thru": "2025-12-31"},
         expect=200)

    checks = _audit_policy_checks()
    names = [name for name, _ in checks]
    assert len(checks) >= 6, f"the audit lost its policy invariants: {names}"

    db = next(app.dependency_overrides[get_db]())
    try:
        assert db.execute(sql_text("select count(*) from business_rules")).scalar() == 5
        for name, sql in checks:
            offending = db.execute(sql_text(sql)).scalar()
            assert offending == 0, f"{name}: {offending} offending rows"

        # a planted violation must be caught, or a check that silently matches
        # nothing looks exactly like a clean database. "only the newest version
        # is repealed" is the one guarded by the API alone — nothing in the
        # schema forbids it — so it is the load-bearing check here.
        newest = next(sql for name, sql in checks if "newest version" in name)
        assert db.execute(sql_text(newest)).scalar() == 0
        db.execute(sql_text(
            "update business_rules set status = 'repealed' where code = :c and version = 1"),
            {"c": "HR-001"})
        assert db.execute(sql_text(newest)).scalar() == 1, (
            "a repealed superseded version went unnoticed"
        )
        db.rollback()
    finally:
        db.close()


def test_rules_json_rides_the_policy_it_restates(client: TestClient) -> None:
    """The reason there is no rule table: a second home for the same figures
    would be free to drift from the prose, with nothing in the schema to
    notice. Here they version, publish and freeze together — because they ARE
    the document."""
    made = draft(
        client, code="FIN-2026-03", category="external_standard",
        title=_ZH_TEXT['TEXT_BE3F09F7F1CEDAC5'],
        body=_ZH_TEXT['TEXT_F28899D3BF3B52B5'],
        rules_json={"social_insurance": {"base": {"cap": 36921, "floor": 7384}}},
    )
    assert made["rules_json"]["social_insurance"]["base"]["cap"] == 36921

    live = publish(client, made["id"], effective_from="2026-07-01")["current"]
    assert live["rules_json"]["social_insurance"]["base"]["floor"] == 7384

    # frozen with the body, by the same guard — no separate freeze to forget
    refused = client.patch(
        f"/api/v1/business-rules/{made['id']}",
        json={"rules_json": {"social_insurance": {"base": {"cap": 1}}}}, headers=HEADERS,
    )
    assert refused.status_code == 409
    assert "new version" in refused.json()["detail"]

    # a new figure is a new version, published by a named person, and the old
    # one still answers for the period it governed
    nxt = draft(client, code="FIN-2026-03", category="external_standard",
                title=_ZH_TEXT['TEXT_824CDBE6818DF692'], body=_ZH_TEXT['TEXT_1CE196F5E9ED6555'],
                rules_json={"social_insurance": {"base": {"cap": 39000, "floor": 7800}}})
    publish(client, nxt["id"], effective_from="2027-07-01")

    def cap_on(on: str) -> int:
        rows = client.get(
            f"/api/v1/business-rules?code=FIN-2026-03&in_force_on={on}", headers=HEADERS
        ).json()["data"]
        assert len(rows) == 1, on
        return rows[0]["rules_json"]["social_insurance"]["base"]["cap"]

    assert cap_on("2026-09-01") == 36921
    assert cap_on("2027-09-01") == 39000


def test_rules_json_is_optional_and_never_interpreted(client: TestClient) -> None:
    """It has no more standing than `body`: any shape is accepted, and a policy
    with only prose is complete."""
    prose_only = draft(client, code="HR-010", title=_ZH_TEXT['TEXT_C4E98659690110D1'])
    assert prose_only["rules_json"] is None

    odd = draft(client, code="HR-011", title=_ZH_TEXT['TEXT_FC62BD28C2644B6D'],
                rules_json={_ZH_TEXT['TEXT_F5FAD31729CE1F05']: [{_ZH_TEXT['TEXT_8E7DDBEEE310A5A5']: 500000, _ZH_TEXT['TEXT_82A59F3D1C16BBD2']: 0.03}, {_ZH_TEXT['TEXT_82A59F3D1C16BBD2']: 0.05}],
                            _ZH_TEXT['TEXT_DAEDE9881787ABE7']: _ZH_TEXT['TEXT_ED1A8E58B50C0F29']})
    assert odd["rules_json"][_ZH_TEXT['TEXT_F5FAD31729CE1F05']][1][_ZH_TEXT['TEXT_82A59F3D1C16BBD2']] == 0.05
