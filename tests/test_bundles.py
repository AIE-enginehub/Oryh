from __future__ import annotations

import io
import json
import re
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api.bundles import skill_bundle_user_for_update
from app.services.emails import outbox
from app.services.provisioning import PRODUCT_SKILLS_DIR

from conftest import provision_tenant as bootstrap_tenant


def extract_token(body: str) -> str:
    for line in body.splitlines():
        if "token=" in line:
            return line.rsplit("token=", 1)[1].strip()
    raise AssertionError("no token in email")


def provision_tenant(client: TestClient) -> dict:
    data = bootstrap_tenant(client, company_name="Bundle Co", email="admin@bundle-co.com", password="bundle-pass1")
    return {"service": {"X-API-Key": data["plain_text_api_key"]}}


def invite(client: TestClient, headers: dict, email: str, role: str, employee_id: str) -> str:
    user_id = client.post(
        "/api/v1/auth/invitations",
        json={"email": email, "role": role, "employee_id": employee_id},
        headers=headers,
    ).json()["data"]["id"]
    token = extract_token(outbox.messages[-1].body)
    client.post("/api/v1/auth/invitations/accept", json={"token": token, "password": "invitee-pass1"})
    return user_id


def bundle_zip(client: TestClient, headers: dict, user_id: str) -> zipfile.ZipFile:
    response = client.post(f"/api/v1/users/{user_id}/skill-bundle", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "no-store"
    return zipfile.ZipFile(io.BytesIO(response.content))


# provision_tenant registers admin@bundle-co.com, so the tenant's slug — and
# with it the install directory and every skill name in the bundle — is derived
# from bundle-co.com.
SLUG = "bundle-co"
ROOT = f"oryh-skills-{SLUG}"


def installed_name(registry_name: str) -> str:
    base = registry_name[len("oryh-") :] if registry_name.startswith("oryh-") else registry_name
    return f"oryh-{SLUG}-{base}"


def skill_md(archive: zipfile.ZipFile, registry_name: str) -> str:
    return archive.read(f"{ROOT}/{installed_name(registry_name)}/SKILL.md").decode()


def installed_dir_names(archive: zipfile.ZipFile) -> set[str]:
    """The skill directories actually written into the tenant's install root."""
    prefix = f"{ROOT}/"
    return {
        name[len(prefix) :].split("/")[0]
        for name in archive.namelist()
        if name.startswith(prefix) and name.count("/") >= 2
    }


def bundle_skill_names(archive: zipfile.ZipFile) -> set[str]:
    """Registry names of the skills in the bundle — what capability gating is
    about, independent of the tenant-scoped names they install under."""
    installed = json.loads(archive.read(f"{ROOT}/manifest.json"))
    return {skill["name"] for skill in installed["skills"]}


def test_bundle_contents_follow_capabilities(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    employee_id = client.post("/api/v1/employees", json={"name": "小王"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "wang@bundle-co.com", "member", employee_id)

    archive = bundle_zip(client, service, user_id)
    names = bundle_skill_names(archive)
    # member baseline covers submit/approve/business-object/booking + ungated my-work
    assert "oryh-my-work" in names
    assert "oryh-timesheet-submit" in names
    assert "oryh-approve" in names
    # timesheet.advance is not in the member baseline: no flow skill
    assert "oryh-timesheet-approval-flow" not in names
    # todos.assign is not in the member baseline either: the flow-side
    # notifier must not land in every member's bundle
    assert "approval-notifier" not in names

    # rendered credentials: real key, no leftover placeholders
    rendered = skill_md(archive, "oryh-my-work")
    assert "{{ORYH_API_KEY}}" not in rendered and "{{ORYH_BASE_URL}}" not in rendered
    key = re.search(r"calw_[A-Za-z0-9_-]+", rendered).group(0)

    # the embedded key works and is attributed to the user
    me = client.get("/api/v1/todos?status=open", headers={"X-API-Key": key})
    assert me.status_code == 200

    # README carries the security note
    readme = archive.read(f"{ROOT}/README.md").decode()
    assert "rotate" in readme or "rotates" in readme


def make_skill(client: TestClient, headers: dict, name: str, *, capability: str | None = None,
               mode: str | None = None) -> dict:
    body = {
        "name": name,
        "title": name,
        "description": f"Use when {name} is needed.",
        "files": {"SKILL.md": f"---\nname: {name}\n---\n\n# {name}\n\nsteps\n"},
    }
    if capability is not None:
        body["required_capability"] = capability
    if mode is not None:
        body["distribution_mode"] = mode
    response = client.post("/api/v1/skills", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def assign(client: TestClient, headers: dict, name: str, subject_type: str, subject_id: str) -> dict:
    response = client.post(
        f"/api/v1/skills/{name}/assignments",
        json={"subject_type": subject_type, "subject_id": subject_id},
        headers=headers,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["data"]


def test_untargeted_skills_keep_reaching_everyone_who_passes_the_gate(client: TestClient) -> None:
    """The compatibility case: a skill with no audience behaves exactly as
    before — capability alone decides."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    employee_id = client.post("/api/v1/employees", json={"name": "小王"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "wang@bundle-co.com", "member", employee_id)

    make_skill(client, service, "acme-open")                                  # ungated
    make_skill(client, service, "acme-gated", capability="timesheet.advance")  # member lacks it

    names = bundle_skill_names(bundle_zip(client, service, user_id))
    assert "acme-open" in names
    assert "acme-gated" not in names


def test_targeted_skill_reaches_only_its_audience(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]

    def member(local: str) -> str:
        emp = client.post("/api/v1/employees", json={"name": local}, headers=service).json()["data"]["id"]
        return invite(client, service, f"{local}@bundle-co.com", "member", emp)

    chosen = member("chosen")
    other = member("other")

    make_skill(client, service, "acme-targeted", mode="targeted")
    # before any audience row: targeted with an empty audience reaches nobody
    assert "acme-targeted" not in bundle_skill_names(bundle_zip(client, service, chosen))

    assign(client, service, "acme-targeted", "user", chosen)
    assert "acme-targeted" in bundle_skill_names(bundle_zip(client, service, chosen))
    assert "acme-targeted" not in bundle_skill_names(bundle_zip(client, service, other))


def test_role_audience_covers_everyone_currently_in_that_role(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    emp = client.post("/api/v1/employees", json={"name": "销售"}, headers=service).json()["data"]["id"]
    seller = invite(client, service, "seller@bundle-co.com", "member", emp)

    make_skill(client, service, "acme-by-role", mode="targeted")
    assign(client, service, "acme-by-role", "role", "member")

    assert "acme-by-role" in bundle_skill_names(bundle_zip(client, service, seller))


def test_audience_narrows_but_never_grants_past_the_capability_gate(client: TestClient) -> None:
    """The AND, stated as a test. Naming someone in the audience must not
    hand them a skill their role cannot execute — that would produce an agent
    that 403s on every call, which is worse than not shipping it.
    """
    ctx = provision_tenant(client)
    service = ctx["service"]
    emp = client.post("/api/v1/employees", json={"name": "小李"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "li@bundle-co.com", "member", emp)

    make_skill(client, service, "acme-privileged", capability="timesheet.advance", mode="targeted")
    assign(client, service, "acme-privileged", "user", user_id)

    assert "acme-privileged" not in bundle_skill_names(bundle_zip(client, service, user_id))


def test_service_key_is_not_subject_to_audience(client: TestClient) -> None:
    """The flow agent runs on the service key and must keep receiving every
    flow skill. It has no user id and no role, so audience filtering cannot
    apply to it — the same reason service_permissions() bypasses the
    capability gate."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    emp = client.post("/api/v1/employees", json={"name": "某人"}, headers=service).json()["data"]["id"]
    someone = invite(client, service, "someone@bundle-co.com", "member", emp)

    make_skill(client, service, "acme-targeted-elsewhere", mode="targeted")
    assign(client, service, "acme-targeted-elsewhere", "user", someone)

    response = client.get("/api/v1/my/skill-bundle", headers=service)
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "acme-targeted-elsewhere" in bundle_skill_names(archive)


def test_manifest_tracks_audience_changes_so_sync_picks_them_up(client: TestClient) -> None:
    """Audience lives in eligible_skills, which the manifest also goes
    through — so 'installed on next sync' needs no sync-side change."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    emp = client.post("/api/v1/employees", json={"name": "同步"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "sync@bundle-co.com", "member", emp)
    key = client.post(
        "/api/v1/tenant/api-keys", json={"label": "agent", "user_id": user_id}, headers=service
    ).json()["data"]["plain_text_api_key"]
    agent = {"X-API-Key": key}

    def manifest_names() -> set[str]:
        rows = client.get("/api/v1/my/skills/manifest", headers=agent).json()["data"]
        return {row["name"] for row in rows}

    make_skill(client, service, "acme-later", mode="targeted")
    assert "acme-later" not in manifest_names()

    assign(client, service, "acme-later", "user", user_id)
    assert "acme-later" in manifest_names()


def test_audience_preview_names_who_would_lose_the_skill(client: TestClient) -> None:
    """Narrowing is the dangerous direction and the silent one — nobody
    reports a skill they quietly stopped receiving. The preview has to say so
    BEFORE the mode is switched, which is why impact is computed against the
    audience as it stands rather than after the fact.
    """
    ctx = provision_tenant(client)
    service = ctx["service"]

    def member(local: str) -> str:
        emp = client.post("/api/v1/employees", json={"name": local}, headers=service).json()["data"]["id"]
        return invite(client, service, f"{local}@bundle-co.com", "member", emp)

    keeper = member("keeper")
    member("dropped")

    make_skill(client, service, "acme-wide")           # capability mode: everyone
    assign(client, service, "acme-wide", "user", keeper)

    impact = client.get("/api/v1/skills/acme-wide/assignments", headers=service).json()["data"]["impact"]
    # still in capability mode, so nothing has changed yet…
    assert impact["distribution_mode"] == "capability"
    # labels are the user's own name, falling back to their email — these
    # invitees were created without one
    assert {"keeper@bundle-co.com", "dropped@bundle-co.com"} <= set(impact["reaches_now"])
    # …but switching to targeted would drop everyone not named
    assert impact["would_reach"] == ["keeper@bundle-co.com"]
    assert "dropped@bundle-co.com" in impact["losing"]
    assert impact["gaining"] == []


def test_audience_preview_flags_people_who_could_not_run_it(client: TestClient) -> None:
    """Naming someone who lacks the capability is not an error — it is a
    misunderstanding to surface. They simply never receive it, and the admin
    needs to know that rather than wonder why the agent stayed silent."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    emp = client.post("/api/v1/employees", json={"name": "小李"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "li@bundle-co.com", "member", emp)

    make_skill(client, service, "acme-privileged", capability="timesheet.advance", mode="targeted")
    row = assign(client, service, "acme-privileged", "user", user_id)
    assert row["blocked_members"] == ["li@bundle-co.com"]

    impact = client.get(
        "/api/v1/skills/acme-privileged/assignments", headers=service
    ).json()["data"]["impact"]
    assert impact["blocked"] == ["li@bundle-co.com"]
    assert impact["would_reach"] == []


def test_assignment_is_idempotent_and_removable_and_audited(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    emp = client.post("/api/v1/employees", json={"name": "小张"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "zhang@bundle-co.com", "member", emp)
    make_skill(client, service, "acme-idem", mode="targeted")

    first = client.post(
        "/api/v1/skills/acme-idem/assignments",
        json={"subject_type": "user", "subject_id": user_id},
        headers=service,
    )
    assert first.status_code == 201
    again = client.post(
        "/api/v1/skills/acme-idem/assignments",
        json={"subject_type": "user", "subject_id": user_id},
        headers=service,
    )
    # naming the same subject twice is the caller's intent already met
    assert again.status_code == 200
    assert again.json()["data"]["id"] == first.json()["data"]["id"]

    audit = client.get("/api/v1/audit-logs?limit=50", headers=service).json()["data"]
    assigned = [row for row in audit if row["action"] == "skill.assigned"]
    assert len(assigned) == 1, "the idempotent repeat must not write a second trail entry"
    assert assigned[0]["detail"]["skill"] == "acme-idem"

    removed = client.delete(
        f"/api/v1/skills/acme-idem/assignments/{first.json()['data']['id']}", headers=service
    )
    assert removed.status_code == 204
    assert "acme-idem" not in bundle_skill_names(bundle_zip(client, service, user_id))
    audit = client.get("/api/v1/audit-logs?limit=50", headers=service).json()["data"]
    assert any(row["action"] == "skill.unassigned" for row in audit)


def test_assignment_rejects_subjects_that_do_not_exist(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    make_skill(client, service, "acme-strict", mode="targeted")
    for body in (
        {"subject_type": "user", "subject_id": "00000000-0000-0000-0000-000000000009"},
        {"subject_type": "role", "subject_id": "no-such-role"},
    ):
        response = client.post("/api/v1/skills/acme-strict/assignments", json=body, headers=service)
        assert response.status_code == 404, response.text


def test_bundle_rotation_kills_previous_key(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    employee_id = client.post("/api/v1/employees", json={"name": "小李"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "li@bundle-co.com", "member", employee_id)

    first = bundle_zip(client, service, user_id)
    key1 = re.search(
        r"calw_[A-Za-z0-9_-]+", skill_md(first, "oryh-my-work")
    ).group(0)
    assert client.get("/api/v1/tenant", headers={"X-API-Key": key1}).status_code == 200

    second = bundle_zip(client, service, user_id)
    key2 = re.search(
        r"calw_[A-Za-z0-9_-]+", skill_md(second, "oryh-my-work")
    ).group(0)
    assert key1 != key2
    assert client.get("/api/v1/tenant", headers={"X-API-Key": key1}).status_code == 401
    assert client.get("/api/v1/tenant", headers={"X-API-Key": key2}).status_code == 200

    # audit trail records issuance and the rotation
    audit = client.get("/api/v1/audit-logs?action=skill_bundle.issued", headers=service).json()
    assert audit["meta"]["total"] == 2
    assert audit["data"][0]["detail"]["rotated_key_ids"]


def test_bundle_rotation_locks_the_user_row_on_postgres() -> None:
    statement = skill_bundle_user_for_update("tenant-1", "user-1")
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql
    assert "users.id" in sql and "users.tenant_id" in sql


def test_custom_capability_gates_custom_skill(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]

    client.post("/api/v1/capabilities", json={"name": "jc.warranty.approve"}, headers=service)
    client.post(
        "/api/v1/roles",
        json={
            "name": "vendor",
            "permissions": ["business_object.write:warranty_card", "todos.complete_own", "jc.warranty.approve"],
        },
        headers=service,
    )
    client.post(
        "/api/v1/skills",
        json={
            "name": "jc-warranty-card-approve",
            "required_capability": "jc.warranty.approve",
            "files": {"SKILL.md": "---\nname: jc-warranty-card-approve\n---\nkey: \"{{ORYH_API_KEY}}\"\n"},
        },
        headers=service,
    )

    e1 = client.post("/api/v1/employees", json={"name": "张伟"}, headers=service).json()["data"]["id"]
    e2 = client.post("/api/v1/employees", json={"name": "小王"}, headers=service).json()["data"]["id"]
    vendor_id = invite(client, service, "vendor@partner.com", "vendor", e1)
    member_id = invite(client, service, "wang@bundle-co.com", "member", e2)

    vendor_names = bundle_skill_names(bundle_zip(client, service, vendor_id))
    member_names = bundle_skill_names(bundle_zip(client, service, member_id))
    assert "jc-warranty-card-approve" in vendor_names
    assert "jc-warranty-card-approve" not in member_names
    # vendor lacks timesheet.submit_own → no submit skill
    assert "oryh-timesheet-submit" not in vendor_names


def test_scoped_system_capability_gates_custom_skill_by_object_type(client: TestClient) -> None:
    """A tenant-authored skill can gate on a SCOPED system verb (no custom
    capability needed): required_capability="business_object.write:daily_report"
    should only reach roles whose grant covers that exact type, `:*`, or the
    bare verb — mirroring how the same string already gates the core API."""
    ctx = provision_tenant(client)
    service = ctx["service"]

    for object_type in ("daily_report", "weekly_report"):
        client.post(
            "/api/v1/object-type-definitions",
            json={"object_type": object_type, "json_schema": {}},
            headers=service,
        )
    skill = client.post(
        "/api/v1/skills",
        json={
            "name": "daily-report-submit",
            "required_capability": "business_object.write:daily_report",
            "files": {"SKILL.md": "---\nname: daily-report-submit\n---\nkey: \"{{ORYH_API_KEY}}\"\n"},
        },
        headers=service,
    )
    assert skill.status_code == 201, skill.text

    # a scope only makes sense on a scopable verb
    rejected = client.post(
        "/api/v1/skills",
        json={
            "name": "bad-skill",
            "required_capability": "approval.record:daily_report",
            "files": {"SKILL.md": "x"},
        },
        headers=service,
    )
    assert rejected.status_code == 422

    client.post(
        "/api/v1/roles",
        json={"name": "daily_only", "permissions": ["business_object.write:daily_report"]},
        headers=service,
    )
    client.post(
        "/api/v1/roles",
        json={"name": "weekly_only", "permissions": ["business_object.write:weekly_report"]},
        headers=service,
    )
    client.post(
        "/api/v1/roles",
        json={"name": "any_type", "permissions": ["business_object.write:*"]},
        headers=service,
    )

    e1 = client.post("/api/v1/employees", json={"name": "日报员"}, headers=service).json()["data"]["id"]
    e2 = client.post("/api/v1/employees", json={"name": "周报员"}, headers=service).json()["data"]["id"]
    e3 = client.post("/api/v1/employees", json={"name": "全权员"}, headers=service).json()["data"]["id"]
    daily_id = invite(client, service, "daily@bundle-co.com", "daily_only", e1)
    weekly_id = invite(client, service, "weekly@bundle-co.com", "weekly_only", e2)
    any_id = invite(client, service, "any@bundle-co.com", "any_type", e3)

    daily_names = bundle_skill_names(bundle_zip(client, service, daily_id))
    weekly_names = bundle_skill_names(bundle_zip(client, service, weekly_id))
    any_names = bundle_skill_names(bundle_zip(client, service, any_id))

    assert "daily-report-submit" in daily_names
    assert "daily-report-submit" not in weekly_names  # wrong object type, no skill
    assert "daily-report-submit" in any_names  # wildcard covers every type

    # the API enforces the exact same scope, independently of skill distribution
    daily_key = client.post(
        "/api/v1/tenant/api-keys", json={"label": "d", "user_id": daily_id}, headers=service
    ).json()["data"]["plain_text_api_key"]
    assert client.post(
        "/api/v1/business-objects",
        json={"object_type": "daily_report", "title": "今日日报", "payload": {}},
        headers={"X-API-Key": daily_key},
    ).status_code == 201
    assert client.post(
        "/api/v1/business-objects",
        json={"object_type": "weekly_report", "title": "本周周报", "payload": {}},
        headers={"X-API-Key": daily_key},
    ).status_code == 403


def test_summary_skill_gated_by_business_object_summarize(client: TestClient) -> None:
    """oryh-business-object-summary is a product skill (ships for every
    tenant); only roles granted the business_object.summarize system
    capability receive it — the plain member baseline does not."""
    ctx = provision_tenant(client)
    service = ctx["service"]

    client.post(
        "/api/v1/roles",
        json={
            "name": "manager",
            "permissions": [
                "timesheet.submit_own",
                "business_object.write:*",
                "business_object.summarize:*",
                "todos.complete_own",
            ],
        },
        headers=service,
    )

    e1 = client.post("/api/v1/employees", json={"name": "李经理"}, headers=service).json()["data"]["id"]
    e2 = client.post("/api/v1/employees", json={"name": "小王"}, headers=service).json()["data"]["id"]
    manager_id = invite(client, service, "manager@bundle-co.com", "manager", e1)
    member_id = invite(client, service, "wang@bundle-co.com", "member", e2)

    manager_names = bundle_skill_names(bundle_zip(client, service, manager_id))
    member_names = bundle_skill_names(bundle_zip(client, service, member_id))
    assert "oryh-business-object-summary" in manager_names
    assert "oryh-business-object-summary" not in member_names
    # both still get the generic record skill regardless of the summarize grant
    assert "oryh-business-object" in manager_names
    assert "oryh-business-object" in member_names


def test_self_service_manifest_and_sync(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    employee_id = client.post("/api/v1/employees", json={"name": "小王"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "wang@bundle-co.com", "member", employee_id)

    archive = bundle_zip(client, service, user_id)
    assert "oryh-skill-sync" in bundle_skill_names(archive)
    key = re.search(
        r"calw_[A-Za-z0-9_-]+", skill_md(archive, "oryh-my-work")
    ).group(0)
    installed = json.loads(archive.read(f"{ROOT}/manifest.json"))
    # the manifest cannot lie about what is on disk: every entry's installed_as
    # is exactly a directory in the install root, and vice versa
    assert {s["installed_as"] for s in installed["skills"]} == installed_dir_names(archive)

    # manifest requires a user-bound key: service key and no key are rejected
    assert client.get("/api/v1/my/skills/manifest").status_code == 401
    assert client.get("/api/v1/my/skills/manifest", headers=service).status_code == 403

    manifest = client.get("/api/v1/my/skills/manifest", headers={"X-API-Key": key}).json()["data"]
    assert {s["name"] for s in manifest} == {s["name"] for s in installed["skills"]}
    by_name = {s["name"]: s for s in manifest}
    for s in installed["skills"]:
        assert by_name[s["name"]]["version"] == s["version"]
        assert by_name[s["name"]]["files_hash"] == s["files_hash"]

    # a skill update bumps version and changes the server manifest
    client.post(
        "/api/v1/skills",
        json={"name": "team-glossary", "files": {"SKILL.md": "---\nname: team-glossary\n---\nv1\n"}},
        headers=service,
    )
    client.patch(
        "/api/v1/skills/team-glossary",
        json={"files": {"SKILL.md": "---\nname: team-glossary\n---\nv2\n"}},
        headers=service,
    )
    manifest2 = client.get("/api/v1/my/skills/manifest", headers={"X-API-Key": key}).json()["data"]
    glossary = next(s for s in manifest2 if s["name"] == "team-glossary")
    assert glossary["version"] == 2
    assert glossary["name"] not in by_name  # newly appeared vs the installed manifest

    # self-service refresh: same key in, same key rendered out, no rotation
    response = client.get("/api/v1/my/skill-bundle", headers={"X-API-Key": key})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "no-store"
    refreshed = zipfile.ZipFile(io.BytesIO(response.content))
    assert "team-glossary" in bundle_skill_names(refreshed)
    rendered = skill_md(refreshed, "oryh-my-work")
    assert key in rendered
    assert client.get("/api/v1/todos?status=open", headers={"X-API-Key": key}).status_code == 200

    # refreshed manifest.json matches the server manifest
    installed2 = json.loads(refreshed.read(f"{ROOT}/manifest.json"))
    assert {(s["name"], s["version"], s["files_hash"]) for s in installed2["skills"]} == {
        (s["name"], s["version"], s["files_hash"]) for s in manifest2
    }

    # sync is audited without rotating anything
    audit = client.get("/api/v1/audit-logs?action=skill_bundle.synced", headers=service).json()
    assert audit["meta"]["total"] == 1
    assert audit["data"][0]["detail"]["skills"]


def register_tenant(client: TestClient, company: str, domain: str) -> dict:
    """A second employer, with its own domain — the whole point of the slug."""
    data = bootstrap_tenant(client, email=f"admin@{domain}", password="second-pass1")
    return {"X-API-Key": data["plain_text_api_key"]}


def test_two_employers_install_side_by_side(client: TestClient) -> None:
    """The same person works for two companies and their agent holds both
    bundles. Nothing may collide: not the install directory, not a skill name,
    not a cross-reference between skills — otherwise the second install
    silently destroys the first, and the agent cannot tell whose timesheet it
    is filling."""
    first = provision_tenant(client)["service"]
    second = register_tenant(client, "Starbridge 咨询", "starbridge-consulting.com")

    e1 = client.post("/api/v1/employees", json={"name": "小王"}, headers=first).json()["data"]["id"]
    e2 = client.post("/api/v1/employees", json={"name": "小王"}, headers=second).json()["data"]["id"]
    u1 = invite(client, first, "wang@bundle-co.com", "member", e1)
    u2 = invite(client, second, "wang@starbridge-consulting.com", "member", e2)

    a1 = bundle_zip(client, first, u1)
    a2 = bundle_zip(client, second, u2)

    # different install roots: extracting both leaves both standing
    roots1 = {name.split("/")[0] for name in a1.namelist()}
    roots2 = {name.split("/")[0] for name in a2.namelist()}
    assert roots1 == {"oryh-skills-bundle-co", "oryh-connect"}
    assert roots2 == {"oryh-skills-starbridge-consulting", "oryh-connect"}

    # ...and no skill name is shared between them, so the agent's choice of
    # skill IS a choice of company
    names1 = installed_dir_names(a1)
    names2 = {
        name[len("oryh-skills-starbridge-consulting/") :].split("/")[0]
        for name in a2.namelist()
        if name.startswith("oryh-skills-starbridge-consulting/") and name.count("/") >= 2
    }
    assert "oryh-bundle-co-timesheet-submit" in names1
    assert "oryh-starbridge-consulting-timesheet-submit" in names2
    assert names1.isdisjoint(names2)

    # the company is in the description — the only thing an agent reads when it
    # decides which skill a request means
    submit = skill_md(a1, "oryh-timesheet-submit")
    assert "Bundle Co" in submit.splitlines()[2]
    assert "oryh-connect" in a2.read(
        "oryh-skills-starbridge-consulting/oryh-starbridge-consulting-skill-sync/SKILL.md"
    ).decode()

    # each bundle's key reaches only its own company
    key1 = re.search(r"calw_[A-Za-z0-9_-]+", skill_md(a1, "oryh-my-work")).group(0)
    me1 = client.get("/api/v1/auth/me", headers={"X-API-Key": key1}).json()["data"]
    assert me1["tenant"]["slug"] == "bundle-co"
    assert me1["install_dir"] == "oryh-skills-bundle-co"

    # the manifest an agent syncs against agrees with what it installed
    manifest = client.get("/api/v1/my/skills/manifest", headers={"X-API-Key": key1}).json()
    assert manifest["meta"]["tenant"]["slug"] == "bundle-co"
    assert {s["installed_as"] for s in manifest["data"]} == names1


def test_cross_references_between_skills_are_rewritten(client: TestClient) -> None:
    """Skills name each other in prose ($oryh-skill-sync, and tenants write such
    references into their own custom skills). A reference left unprefixed points
    at a skill that does not exist locally — or worse, at the other employer's."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    client.post(
        "/api/v1/skills",
        json={
            "name": "team-playbook",
            "files": {
                "SKILL.md": (
                    "---\nname: team-playbook\ndescription: house rules\n---\n"
                    "Hand over to $oryh-timesheet-submit, then $oryh-business-object,\n"
                    "never $oryh-business-object-summary. Reconnect via $oryh-connect.\n"
                )
            },
        },
        headers=service,
    )
    employee_id = client.post("/api/v1/employees", json={"name": "小王"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "wang@bundle-co.com", "member", employee_id)

    body = skill_md(bundle_zip(client, service, user_id), "team-playbook")
    assert "$oryh-bundle-co-timesheet-submit" in body
    # the strict-prefix pair survives: business-object must not eat the summary
    assert "$oryh-bundle-co-business-object," in body
    assert "$oryh-bundle-co-business-object-summary" in body
    # ...and the one shared, company-agnostic skill is left alone
    assert "$oryh-connect." in body
    assert "oryh-bundle-co-connect" not in body


def test_frontmatter_name_matches_installed_directory(client: TestClient) -> None:
    """The frontmatter `name:` is what an agent runtime presents as the skill's
    identity. It must equal the directory the copy installs under — for product
    and custom skills alike, under the default brand too — or two employers'
    copies of the same skill would introduce themselves identically."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    client.post(
        "/api/v1/skills",
        json={"name": "team-wiki", "files": {"SKILL.md": "---\nname: team-wiki\ndescription: wiki\n---\nx\n"}},
        headers=service,
    )
    employee_id = client.post("/api/v1/employees", json={"name": "小名"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "ming@bundle-co.com", "member", employee_id)

    archive = bundle_zip(client, service, user_id)
    for registry_name in ("oryh-my-work", "team-wiki"):
        first_lines = skill_md(archive, registry_name).splitlines()[:2]
        assert first_lines == ["---", f"name: {installed_name(registry_name)}"]
    connect_md = archive.read("oryh-connect/SKILL.md").decode()
    assert connect_md.splitlines()[1] == "name: oryh-connect"
    # default brand renders prose untouched
    assert " in oryh" in skill_md(archive, "oryh-my-work")


def test_common_word_custom_skill_does_not_corrupt_other_skills(client: TestClient) -> None:
    """A custom skill named for a common word must only rewrite DELIMITED
    references to it ($report, `report`) — never the bare word in another
    skill's prose, and never an API token like source_report_text."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    client.post(
        "/api/v1/skills",
        json={"name": "report", "files": {"SKILL.md": "---\nname: report\ndescription: house report\n---\nbody\n"}},
        headers=service,
    )
    employee_id = client.post("/api/v1/employees", json={"name": "小王"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "wang@bundle-co.com", "member", employee_id)

    submit = skill_md(bundle_zip(client, service, user_id), "oryh-timesheet-submit")
    # the timesheet skill talks about source_report_text and returned reports;
    # none of that may have been mangled into the custom skill's name
    assert "source_report_text" in submit
    assert "oryh-bundle-co-report" not in submit


def test_custom_skill_name_colliding_with_a_product_base_is_disambiguated(client: TestClient) -> None:
    """A custom `my-work` and the product `oryh-my-work` both want the installed
    name oryh-<slug>-my-work. The product keeps it; the custom one gets a
    distinct name, so neither clobbers the other in the zip and the manifest's
    installed_as stays unique."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    client.post(
        "/api/v1/skills",
        json={"name": "my-work", "files": {"SKILL.md": "---\nname: my-work\ndescription: custom\n---\nx\n"}},
        headers=service,
    )
    employee_id = client.post("/api/v1/employees", json={"name": "小王"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "wang@bundle-co.com", "member", employee_id)

    archive = bundle_zip(client, service, user_id)
    installed = json.loads(archive.read(f"{ROOT}/manifest.json"))
    installed_as = [s["installed_as"] for s in installed["skills"]]
    # the product skill keeps the clean name; the custom one is elsewhere
    assert "oryh-bundle-co-my-work" in installed_as
    assert len(installed_as) == len(set(installed_as))  # no collision
    # every manifest entry is a real directory and vice versa
    assert set(installed_as) == installed_dir_names(archive)


def test_service_key_gets_the_tenant_bundle_for_the_flow_agent(client: TestClient) -> None:
    """The workflow admin agent runs on the tenant service key by design, so
    it must be able to fetch its own skills.

    This used to 403 on the rationale that a service key should not enumerate
    skill content — but `GET /skills/{ref}/files/{path}` already serves full
    skill text to any authenticated actor, so the refusal protected nothing
    and only broke the deployment the flow skills document.
    """
    ctx = provision_tenant(client)
    response = client.get("/api/v1/my/skill-bundle", headers=ctx["service"])
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        readme = next(n for n in names if n.endswith("/README.md"))
        text = archive.read(readme).decode()
    # rendered as the tenant's, not as some person's
    assert "tenant service skill bundle" in text
    assert "- role: service" in text
    # and it carries the flow skills the service key exists to run — when the
    # catalog ships any. The hosted approval flows are the cloud service's, so
    # a deployment without them still gets a valid service bundle; what must
    # hold either way is that the bundle is not empty.
    catalog_has_flows = any(
        path.name.endswith("-approval-flow") for path in PRODUCT_SKILLS_DIR.iterdir()
    )
    if catalog_has_flows:
        assert any("approval-flow" in n for n in names)
    else:
        assert any(n.endswith("/SKILL.md") for n in names)


def test_browser_session_still_cannot_mint_a_bundle(client: TestClient) -> None:
    """The boundary that does hold: a session must not produce a long-lived
    credential file."""
    ctx = provision_tenant(client)
    response = client.get("/api/v1/my/skill-bundle", headers={"Authorization": "Bearer nonsense"})
    assert response.status_code in (401, 403)


def test_bundle_requires_management_capabilities(client: TestClient) -> None:
    ctx = provision_tenant(client)
    service = ctx["service"]
    employee_id = client.post("/api/v1/employees", json={"name": "小王"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "wang2@bundle-co.com", "member", employee_id)
    member_key = client.post(
        "/api/v1/tenant/api-keys", json={"label": "m", "user_id": user_id}, headers=service
    ).json()["data"]["plain_text_api_key"]
    response = client.post(
        f"/api/v1/users/{user_id}/skill-bundle", headers={"X-API-Key": member_key}
    )
    assert response.status_code == 403


def test_skill_brand_rebrands_outbound_bundles_only(client: TestClient) -> None:
    """ORYH_SKILL_BRAND renames everything outbound — install dir, installed
    skill names, cross-references, the connect skill — while registry names
    and template hashes (the sync keys) stay canonical and unchanged."""
    from app.core.config import settings as app_settings

    ctx = provision_tenant(client)
    service = ctx["service"]
    employee_id = client.post("/api/v1/employees", json={"name": "小品"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "brand@bundle-co.com", "member", employee_id)

    # baseline under the default brand: capture the sync keys
    default_archive = bundle_zip(client, service, user_id)
    default_manifest = json.loads(default_archive.read(f"{ROOT}/manifest.json"))
    default_hashes = {s["name"]: s["files_hash"] for s in default_manifest["skills"]}

    original = app_settings.skill_brand
    app_settings.skill_brand = "calwbiz"
    try:
        archive = bundle_zip(client, service, user_id)
        root = f"calwbiz-skills-{SLUG}"
        top_level = {name.split("/")[0] for name in archive.namelist()}
        assert root in top_level
        assert f"oryh-skills-{SLUG}" not in top_level

        prefix = f"{root}/"
        dirs = {
            name[len(prefix):].split("/")[0]
            for name in archive.namelist()
            if name.startswith(prefix) and name.count("/") >= 2
        }
        assert f"calwbiz-{SLUG}-my-work" in dirs
        assert not any(d.startswith("oryh-") for d in dirs)

        # the connect skill rides along under the brand
        assert "calwbiz-connect" in top_level
        assert "oryh-connect" not in top_level

        manifest = json.loads(archive.read(f"{root}/manifest.json"))
        assert manifest["install_dir"] == root
        by_name = {s["name"]: s for s in manifest["skills"]}
        # registry names stay canonical; installed names carry the brand
        assert "oryh-my-work" in by_name
        assert by_name["oryh-my-work"]["installed_as"] == f"calwbiz-{SLUG}-my-work"
        # sync keys are brand-independent: hashes identical across brands
        assert {s["name"]: s["files_hash"] for s in manifest["skills"]} == default_hashes

        # cross-references in prose follow the brand
        rendered = archive.read(f"{root}/calwbiz-{SLUG}-my-work/SKILL.md").decode()
        assert f"calwbiz-{SLUG}-approve" in rendered
        assert "$oryh-approve" not in rendered

        # the frontmatter `name:` — the identity an agent runtime reads — is
        # the installed name, and standalone product mentions speak the brand
        assert rendered.splitlines()[1] == f"name: calwbiz-{SLUG}-my-work"
        assert "in calwbiz" in rendered
        assert " in oryh" not in rendered

        # the ride-along connect skill is fully branded too…
        connect_md = archive.read("calwbiz-connect/SKILL.md").decode()
        assert connect_md.splitlines()[1] == "name: calwbiz-connect"
        assert "连接 calwbiz" in connect_md
        assert "连接 oryh" not in connect_md
        # …while identifiers and the real domain stay untouched
        api_ref = archive.read("calwbiz-connect/references/api.md").decode()
        assert "https://oryh.ai/web/device" in api_ref

        # README names the branded connect skill
        readme = archive.read(f"{root}/README.md").decode()
        assert "calwbiz-connect" in readme

        # the public connect download is branded too — filename, frontmatter,
        # and prose alike
        response = client.get("/api/v1/connect-skill")
        assert response.status_code == 200
        assert 'filename="calwbiz-connect.zip"' in response.headers["content-disposition"]
        connect = zipfile.ZipFile(io.BytesIO(response.content))
        assert all(name.startswith("calwbiz-connect/") for name in connect.namelist())
        public_md = connect.read("calwbiz-connect/SKILL.md").decode()
        assert public_md.splitlines()[1] == "name: calwbiz-connect"
        assert "连接 calwbiz" in public_md
    finally:
        app_settings.skill_brand = original


def test_branded_connect_never_points_at_another_deployments_directories(
    client: TestClient,
) -> None:
    """Regression: a calwbiz-branded connect skill told the agent to list
    `oryh-skills-*/`, so on a laptop already holding the PRODUCTION bundles it
    found those directories and reported their companies as connected here.

    Every install-dir/bootstrap path in rendered output must carry this
    deployment's brand, or one environment's agent claims another's tenants."""
    from app.core.config import settings as app_settings

    original = app_settings.skill_brand
    app_settings.skill_brand = "calwbiz"
    try:
        response = client.get("/api/v1/connect-skill")
        connect = zipfile.ZipFile(io.BytesIO(response.content))
        for entry in connect.namelist():
            body = connect.read(entry).decode()
            # the scan target, the bootstrap dir, and the name template all
            # follow the brand — no canonical path survives anywhere
            assert "oryh-skills" not in body, entry
            assert "oryh-connect" not in body, entry
            assert "oryh-<slug>" not in body, entry
        skill_md = connect.read("calwbiz-connect/SKILL.md").decode()
        assert "calwbiz-skills-*/" in skill_md
        assert "calwbiz-skills-<slug>/" in skill_md
        assert "calwbiz-<slug>-skill-sync" in skill_md
        # the real domain is still not a brand-derived string
        assert "https://oryh.ai" in connect.read("calwbiz-connect/references/api.md").decode()
    finally:
        app_settings.skill_brand = original


def test_brand_leaves_skill_sync_and_author_names_intact() -> None:
    """`oryh-skill-sync`/`oryh-skill-author` start with the same 11 characters
    as the install-dir prefix; the derived-path rule must not eat them."""
    from app.core.config import settings as app_settings
    from app.services.bundles import apply_brand

    original = app_settings.skill_brand
    app_settings.skill_brand = "calwbiz"
    try:
        assert apply_brand("$oryh-skill-sync and oryh-skill-author") == (
            "$oryh-skill-sync and oryh-skill-author"
        )
        assert apply_brand("`oryh-skills-acme/`") == "`calwbiz-skills-acme/`"
    finally:
        app_settings.skill_brand = original


def test_skill_brand_rejects_unsafe_values() -> None:
    """The brand becomes directory and skill names on machines we do not
    control — only short lowercase kebab-case is acceptable."""
    from app.core.config import Settings

    for bad in ("Calwbiz", "has_underscore", "-leading", "way-toooooo-long-brand", "a b"):
        with pytest.raises(Exception):
            Settings(skill_brand=bad)
    assert Settings(skill_brand="calwbiz").skill_brand == "calwbiz"


def reach(client: TestClient, headers: dict, path: str) -> dict:
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return {
        "received": {entry["name"]: entry for entry in data["received"]},
        "withheld": {entry["name"]: entry for entry in data["withheld"]},
        "raw": data,
    }


def test_reach_view_agrees_with_the_bundle_it_describes(client: TestClient) -> None:
    """The load-bearing property. A troubleshooting view that disagrees with
    the bundle sends the admin chasing a problem that is not there, so
    `received` must be exactly what the next sync would install — not a second
    implementation of the same rule that drifts from the first.
    """
    ctx = provision_tenant(client)
    service = ctx["service"]
    emp = client.post("/api/v1/employees", json={"name": "小周"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "zhou@bundle-co.com", "member", emp)

    make_skill(client, service, "acme-open")
    make_skill(client, service, "acme-gated", capability="timesheet.advance")
    make_skill(client, service, "acme-mine", mode="targeted")
    assign(client, service, "acme-mine", "user", user_id)
    make_skill(client, service, "acme-elsewhere", mode="targeted")

    view = reach(client, service, f"/api/v1/users/{user_id}/skills")
    assert set(view["received"]) == bundle_skill_names(bundle_zip(client, service, user_id))


def test_reach_view_names_the_reason_and_the_way_out(client: TestClient) -> None:
    """The withheld half is the whole point: today "why doesn't my agent have
    that skill" is answerable only by deriving the capability matrix by hand."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    emp = client.post("/api/v1/employees", json={"name": "小吴"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "wu@bundle-co.com", "member", emp)

    make_skill(client, service, "acme-open")
    make_skill(client, service, "acme-gated", capability="timesheet.advance")
    make_skill(client, service, "acme-elsewhere", mode="targeted")
    make_skill(client, service, "acme-mine", mode="targeted")
    assign(client, service, "acme-mine", "user", user_id)
    make_skill(client, service, "acme-by-role", mode="targeted")
    assign(client, service, "acme-by-role", "role", "member")

    view = reach(client, service, f"/api/v1/users/{user_id}/skills")
    assert view["received"]["acme-open"]["reasons"] == ["capability"]
    assert view["received"]["acme-mine"]["reasons"] == ["targeted_user"]
    assert view["received"]["acme-by-role"]["reasons"] == ["targeted_role"]
    assert view["received"]["acme-by-role"]["named_via"] == ["role:member"]

    # could run it, but it is targeted at nobody — an audience problem
    assert view["withheld"]["acme-elsewhere"]["reasons"] == ["not_in_audience"]

    # cannot run it — and the answer to "how do I get it" is on screen
    gated = view["withheld"]["acme-gated"]
    assert gated["reasons"] == ["missing_capability"]
    assert gated["required_capability"] == "timesheet.advance"
    assert "admin" in gated["granted_by_roles"]
    assert "member" not in gated["granted_by_roles"]


def test_reach_names_both_reasons_when_a_skill_fails_both_axes(client: TestClient) -> None:
    """Regression, found by an agent relaying the answer to a real person.

    An earlier version named only the capability here, on the reasoning that
    an audience edit alone could not help. Equally true in reverse: granting
    the capability alone leaves the skill just as unreachable, so the person
    asks their admin for half a fix and comes back a day later. Both blockers
    are real; both are named.
    """
    ctx = provision_tenant(client)
    service = ctx["service"]
    emp = client.post("/api/v1/employees", json={"name": "小赵"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "zhao@bundle-co.com", "member", emp)

    make_skill(client, service, "acme-both", capability="timesheet.advance", mode="targeted")

    view = reach(client, service, f"/api/v1/users/{user_id}/skills")
    assert view["withheld"]["acme-both"]["reasons"] == ["missing_capability", "not_in_audience"]

    # closing only the capability half must NOT make it reachable, which is
    # exactly why reporting one reason was wrong
    assign(client, service, "acme-both", "user", user_id)
    view = reach(client, service, f"/api/v1/users/{user_id}/skills")
    assert view["withheld"]["acme-both"]["reasons"] == ["missing_capability"]
    assert "acme-both" not in view["received"]


def test_role_reach_answers_for_the_role_not_its_current_members(client: TestClient) -> None:
    """A skill targeted at one person who happens to hold the role is not the
    role's — the next person hired into it would not get the skill, and the
    role view must say so."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    emp = client.post("/api/v1/employees", json={"name": "小孙"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "sun@bundle-co.com", "member", emp)

    make_skill(client, service, "acme-personal", mode="targeted")
    assign(client, service, "acme-personal", "user", user_id)
    make_skill(client, service, "acme-role-wide", mode="targeted")
    assign(client, service, "acme-role-wide", "role", "member")

    view = reach(client, service, "/api/v1/roles/member/skills")
    assert view["raw"]["subject_type"] == "role"
    assert view["received"]["acme-role-wide"]["reasons"] == ["targeted_role"]
    assert view["withheld"]["acme-personal"]["reasons"] == ["not_in_audience"]

    # the individual grant still shows up where it belongs
    personal = reach(client, service, f"/api/v1/users/{user_id}/skills")
    assert "acme-personal" in personal["received"]


def test_an_agent_can_ask_why_it_lacks_a_skill_without_being_an_admin(
    client: TestClient,
) -> None:
    """The person who asks "why don't you have that skill" is usually not the
    admin. Their own agent must be able to answer with its own user key."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    emp = client.post("/api/v1/employees", json={"name": "小钱"}, headers=service).json()["data"]["id"]
    user_id = invite(client, service, "qian@bundle-co.com", "member", emp)
    make_skill(client, service, "acme-gated", capability="timesheet.advance")

    archive = bundle_zip(client, service, user_id)
    key = re.search(r"calw_[A-Za-z0-9_-]+", skill_md(archive, "oryh-my-work")).group(0)
    mine = {"X-API-Key": key}

    view = reach(client, mine, "/api/v1/my/skills/reach")
    assert view["raw"]["subject_id"] == user_id
    assert view["withheld"]["acme-gated"]["reasons"] == ["missing_capability"]

    # ...but it cannot look at anyone else
    assert client.get(f"/api/v1/users/{user_id}/skills", headers=mine).status_code == 403


def test_reach_view_leaves_out_the_connect_skill(client: TestClient) -> None:
    """oryh-connect ships outside every tenant bundle, so listing it as
    withheld would be a lie about a skill the person already has."""
    ctx = provision_tenant(client)
    view = reach(client, ctx["service"], "/api/v1/roles/member/skills")
    assert "oryh-connect" not in view["received"]
    assert "oryh-connect" not in view["withheld"]


def user_key(client: TestClient, service: dict, user_id: str) -> dict:
    """A real user-bound key — service keys bypass permission checks, so an
    access test written against one proves nothing."""
    archive = bundle_zip(client, service, user_id)
    key = re.search(r"calw_[A-Za-z0-9_-]+", skill_md(archive, "oryh-my-work")).group(0)
    return {"X-API-Key": key}


def test_a_member_cannot_sweep_the_whole_audit_trail(client: TestClient) -> None:
    """Found by an agent that diagnosed a colleague's skill change by reading
    the tenant log — including their `skill_bundle.synced` rows and the
    `key_id` in the detail.

    `GET /auth/users` correctly refused the same key the directory of the very
    people whose actions it was reading.
    """
    ctx = provision_tenant(client)
    service = ctx["service"]
    emp = client.post("/api/v1/employees", json={"name": "小陈"}, headers=service).json()["data"]["id"]
    other_emp = client.post("/api/v1/employees", json={"name": "小孙"}, headers=service).json()["data"]["id"]
    me = invite(client, service, "chen@bundle-co.com", "member", emp)
    colleague = invite(client, service, "sun@bundle-co.com", "member", other_emp)

    mine = user_key(client, service, me)
    user_key(client, service, colleague)  # leaves a skill_bundle.issued row carrying their key_id

    # the sweep is refused, and the message says what may be asked instead
    swept = client.get("/api/v1/audit-logs?limit=100", headers=mine)
    assert swept.status_code == 403, swept.text
    assert "users.manage" in swept.json()["detail"]

    # ...specifically, the colleague's credential events stay out of reach
    assert client.get(
        f"/api/v1/audit-logs?entity_type=user&entity_id={colleague}", headers=mine
    ).status_code == 403
    assert client.get(
        "/api/v1/audit-logs?action=skill_bundle.issued", headers=mine
    ).status_code == 403

    # an admin still reads the lot — it is their troubleshooting tool
    assert client.get("/api/v1/audit-logs?limit=100", headers=service).status_code == 200


def test_a_member_still_reads_their_own_trail_and_a_named_record(client: TestClient) -> None:
    """Narrowing must not take away the two things the log is legitimately
    for: what I did, and what happened to this record. The console's
    object-detail trail and $oryh-business-object both depend on the latter.
    """
    ctx = provision_tenant(client)
    service = ctx["service"]
    emp = client.post("/api/v1/employees", json={"name": "小陈"}, headers=service).json()["data"]["id"]
    me = invite(client, service, "chen@bundle-co.com", "member", emp)
    mine = user_key(client, service, me)

    obj = client.post(
        "/api/v1/business-objects",
        json={"object_type": "daily_report", "title": "周一日报", "payload": {}},
        headers=mine,
    )
    assert obj.status_code == 201, obj.text
    object_id = obj.json()["data"]["id"]

    # what happened to this record — the record's history, not anyone's person
    trail = client.get(
        f"/api/v1/audit-logs?entity_type=business_object&entity_id={object_id}", headers=mine
    )
    assert trail.status_code == 200, trail.text
    assert [row["action"] for row in trail.json()["data"]] == ["business_object.created"]

    # what I did
    assert client.get(f"/api/v1/audit-logs?actor=user:{me}", headers=mine).status_code == 200
    # what happened to my own account
    assert client.get(
        f"/api/v1/audit-logs?entity_type=user&entity_id={me}", headers=mine
    ).status_code == 200
    # but not by claiming to be someone else
    assert client.get("/api/v1/audit-logs?actor=user:someone-else", headers=mine).status_code == 403


def test_the_bundle_says_what_this_person_is_not_equipped_to_do(client: TestClient) -> None:
    """The incident: an HR person asked their agent to 做7月份员工工资单, and it
    filed the wrong kind of record.

    The payroll skill was not at fault — its description says 生成工资条, its
    triggers include "生成 7 月份的工资条", its body says a payslip is a
    `direction=payroll` invoice. It was never handed over, because the tenant's
    HR role holds no payroll verb. And the bundle described only what it
    contained, which reads as a complete account of the workspace and is not
    one: no payroll skill, no mention that payroll exists, no route to
    `/my/skills/reach`. The agent could not know, so it improvised, and nobody
    was told a capability was missing.

    A bundle now carries the other half. Not to grant anything — to let the
    agent recognise the request and refuse it usefully.
    """
    ctx = provision_tenant(client)
    service = ctx["service"]
    employee_id = client.post(
        "/api/v1/employees", json={"name": "任嘉"}, headers=service
    ).json()["data"]["id"]
    # the shipped `member` baseline holds no payroll verb, which is exactly the
    # position a tenant-authored `hr_admin` was in
    user_id = invite(client, service, "hr@bundle-co.com", "member", employee_id)

    archive = bundle_zip(client, service, user_id)
    assert "oryh-payroll" not in bundle_skill_names(archive)

    withheld = {
        item["name"]: item
        for item in json.loads(archive.read(f"{ROOT}/withheld.json"))["withheld"]
    }
    assert "oryh-payroll" in withheld, sorted(withheld)
    payroll = withheld["oryh-payroll"]
    assert payroll["required_capability"] == "payroll.manage"
    assert "missing_capability" in payroll["reasons"]
    # the sentence the agent matches 工资单 against — a bare name would leave it
    # unable to connect the request to anything
    assert "工资条" in (payroll["description"] or ""), payroll["description"]
    # who could grant it, so the person asks the right admin
    assert "admin" in payroll["granted_by_roles"]

    readme = archive.read(f"{ROOT}/README.md").decode()
    assert "NOT equipped" in readme
    assert "oryh-payroll" in readme and "payroll.manage" in readme
    assert "improvise" in readme, "the instruction is the point, not the list"

    # A plain member is withheld most of the catalog, so the README carries
    # excerpts — but the excerpt has to keep the words that make 做工资单 find
    # this entry. Truncating past them would leave a tidy list that matches
    # nothing, which is the original failure with better formatting.
    entry = readme[readme.index("- **oryh-payroll**"):]
    entry = entry[: entry.index("\n- **")]
    assert "生成工资条" in entry, entry
    # …and the full text is still one file away
    assert len(payroll["description"]) > len(entry)
    assert payroll["description"].endswith(".")


def test_a_bundle_that_withholds_nothing_says_nothing(client: TestClient) -> None:
    """An empty section in every bundle would train readers to skip it, and a
    service key is withheld nothing at all — it bypasses the permission layer,
    so an empty list there is the truth rather than a gap."""
    ctx = provision_tenant(client)
    service = ctx["service"]

    response = client.get("/api/v1/my/skill-bundle", headers=service)
    assert response.status_code == 200, response.text
    archive = zipfile.ZipFile(io.BytesIO(response.content))

    assert f"{ROOT}/withheld.json" not in archive.namelist()
    assert "NOT equipped" not in archive.read(f"{ROOT}/README.md").decode()


def test_reach_carries_the_description_an_agent_matches_on(client: TestClient) -> None:
    """`/my/skills/reach` is the live version of the same answer. It reported a
    name and a title — "Oryh Payroll" — which is a label, not something a
    request for 工资单 connects to."""
    ctx = provision_tenant(client)
    service = ctx["service"]
    employee_id = client.post(
        "/api/v1/employees", json={"name": "任嘉"}, headers=service
    ).json()["data"]["id"]
    user_id = invite(client, service, "hr2@bundle-co.com", "member", employee_id)

    key = re.search(
        r"calw_[A-Za-z0-9_-]+",
        skill_md(bundle_zip(client, service, user_id), "oryh-my-work"),
    ).group(0)
    reach = client.get("/api/v1/my/skills/reach", headers={"X-API-Key": key})
    assert reach.status_code == 200, reach.text
    withheld = {item["name"]: item for item in reach.json()["data"]["withheld"]}
    assert "工资条" in (withheld["oryh-payroll"]["description"] or "")
