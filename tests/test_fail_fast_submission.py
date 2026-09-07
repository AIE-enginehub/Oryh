"""Submitting a form should take one exchange, not a search.

A person naming a project that is not in the master data used to cost them
minutes: the agent's skill said "match confidently", so it queried spellings,
paged the list, re-read the definition, and only then asked. Two server-side
aids shorten that to one call each — a keyword that forgives word order and
gaps, and a dry-run create that answers "would this land" without writing —
and one skill fragment says when to stop looking.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.provisioning import PRODUCT_SKILLS_DIR
from conftest import make_client, provision_tenant


@pytest.fixture()
def office():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Fast Co", email="admin@fast.example")
        key = {"X-API-Key": t["plain_text_api_key"]}
        who = client.post("/api/v1/employees", json={"name": "周明"}, headers=key).json()["data"]["id"]
        for name in ("华东医院信息化二期", "华东医院一期", "西南仓库改造"):
            r = client.post("/api/v1/projects", json={"project_name": name}, headers=key)
            assert r.status_code == 201, r.text
        yield client, key, who


def test_every_word_must_land_so_the_first_lookup_is_the_last(office) -> None:
    client, key, _ = office
    names = lambda r: sorted(p["project_name"] for p in r.json()["data"])  # noqa: E731
    assert names(client.get("/api/v1/projects?keyword=华东 二期", headers=key)) == ["华东医院信息化二期"]
    assert names(client.get("/api/v1/projects?keyword=二期 华东", headers=key)) == ["华东医院信息化二期"]
    assert names(client.get("/api/v1/projects?keyword=华东", headers=key)) == ["华东医院一期", "华东医院信息化二期"]
    assert names(client.get("/api/v1/projects?keyword=华东 西南", headers=key)) == []


def test_a_dry_run_create_answers_would_this_land_and_writes_nothing(office) -> None:
    client, key, who = office
    project = client.get("/api/v1/projects?keyword=二期", headers=key).json()["data"][0]["id"]
    body = {
        "employee_id": who, "period_start": "2026-06-01", "period_end": "2026-06-07",
        "entries": [
            {"work_date": "2026-06-01", "hours": 8, "task": "需求评审", "project_id": project},
            {"work_date": "2026-06-02", "hours": 6, "task": "联调"},
        ],
    }
    dry = client.post("/api/v1/timesheet-headers?validate_only=true", json=body, headers=key)
    assert dry.status_code == 201, dry.text
    assert dry.json()["meta"] == {"validate_only": True, "written": False}
    assert [e["hours"] for e in dry.json()["data"]["entries"]] == [8, 6]
    assert dry.json()["data"]["entries"][0]["project_name_snapshot"] == "华东医院信息化二期"

    listed = client.get(f"/api/v1/timesheet-headers?employee_id={who}", headers=key).json()["data"]
    assert listed == [], "a dry run leaves no draft behind"

    # the same errors the real write gives, so the agent learns them in one call
    bad = dict(body, entries=[{"work_date": "2026-07-01", "hours": 8, "task": "x"}])
    outside = client.post("/api/v1/timesheet-headers?validate_only=true", json=bad, headers=key)
    assert outside.status_code == 400 and "period" in outside.json()["detail"]
    ghost = dict(body, entries=[{"work_date": "2026-06-01", "hours": 8, "task": "x",
                                "project_id": "00000000-0000-0000-0000-000000000000"}])
    assert client.post("/api/v1/timesheet-headers?validate_only=true", json=ghost, headers=key).status_code == 404
    assert client.get(f"/api/v1/timesheet-headers?employee_id={who}", headers=key).json()["data"] == []

    # and the real write still lands afterwards
    real = client.post("/api/v1/timesheet-headers", json=body, headers=key)
    assert real.status_code == 201, real.text


def test_an_expense_dry_run_catches_the_duplicate_invoice_without_filing_anything(office) -> None:
    client, key, who = office
    first = client.post("/api/v1/expense-claims", headers=key, json={
        "employee_id": who, "title": "上海出差", "claim_date": "2026-07-10",
        "items": [{"expense_date": "2026-07-09", "amount": 120.0, "invoice_number": "INV-9"}],
    })
    assert first.status_code == 201, first.text
    again = client.post("/api/v1/expense-claims?validate_only=true", headers=key, json={
        "employee_id": who, "title": "又一张", "claim_date": "2026-07-11",
        "items": [{"expense_date": "2026-07-09", "amount": 120.0, "invoice_number": "INV-9"}],
    })
    assert again.status_code == 409 and "INV-9" in again.json()["detail"]
    claims = client.get(f"/api/v1/expense-claims?employee_id={who}", headers=key).json()["data"]
    assert [c["title"] for c in claims] == ["上海出差"]


def test_the_stop_rule_is_written_where_every_submit_skill_reads() -> None:
    fragment = (PRODUCT_SKILLS_DIR / "_common" / "fail-fast-on-master-data.md").read_text(encoding="utf-8")
    assert "look it up **once**" in fragment
    assert "free text is not a fallback" in fragment
    include = "{{include:_common/fail-fast-on-master-data.md}}"
    submitters = [
        p.parent.name for p in sorted(PRODUCT_SKILLS_DIR.glob("*/SKILL.md"))
        if p.parent.name.endswith("-submit")
    ]
    assert len(submitters) >= 6
    for name in submitters:
        text = (PRODUCT_SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
        assert include in text, f"{name} names master data but never says when to stop looking"
    # the contradiction that sent agents hunting is gone
    timesheet = (PRODUCT_SKILLS_DIR / "oryh-timesheet-submit" / "SKILL.md").read_text(encoding="utf-8")
    assert "confirm capturing it as free text" not in timesheet
    assert "validate_only" in timesheet
