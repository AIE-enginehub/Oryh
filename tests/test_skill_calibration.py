"""A workspace refines a shipped skill without forking it.

Two tenants want the same skill to behave differently — one wants todos listed
bare, the other wants the linked record's detail alongside. Before this, the
only route was editing the skill's files, which forks it to `custom` and stops
catalog syncs forever: a workspace that wanted one sentence changed would stop
receiving every correction shipped afterwards. In one week that would have cost
three of them.

`calibration` is the tenant's own text, appended as a section at render time
and never touched by the sync. It is the third knob a tenant owns outright,
beside `required_capability` (who may receive) and `distribution_mode` (who is
targeted) — and the only one that changes what the skill SAYS.

What it must never do is widen the skill: the rendered section states that the
skill's own rules win on contradiction, so a tenant cannot calibrate an agent
past an approval boundary.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.services.bundles import (
    CALIBRATION_BOUNDARY,
    CALIBRATION_HEADING,
    calibration_section,
    skill_files_hash,
)
from conftest import provision_tenant


@pytest.fixture()
def workspace(client):
    tenant = provision_tenant(client, company_name="Calib Co", email="admin@calib.example")
    return {"X-API-Key": tenant["plain_text_api_key"]}


def _skill(client, headers, name="oryh-my-work"):
    response = client.get(f"/api/v1/skills/{name}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _bundle_text(client, headers, skill_name="my-work"):
    bundle = client.get("/api/v1/my/skill-bundle", headers=headers)
    assert bundle.status_code == 200, bundle.text
    archive = zipfile.ZipFile(io.BytesIO(bundle.content))
    path = next(n for n in archive.namelist() if n.endswith(f"-{skill_name}/SKILL.md"))
    return archive.read(path).decode("utf-8")


def test_calibrating_a_product_skill_does_not_fork_it(client, workspace):
    before = _skill(client, workspace)
    assert before["kind"] == "product"

    response = client.patch(
        "/api/v1/skills/oryh-my-work",
        headers=workspace,
        json={"calibration": "报待办时只列标题、到期和状态，不展开关联对象详情。"},
    )
    assert response.status_code == 200, response.text
    after = response.json()["data"]

    # The whole point: content keeps tracking the catalog.
    assert after["kind"] == "product", "calibration must not fork a shipped skill"
    assert after["version"] == before["version"] + 1
    assert "只列标题" in after["calibration"]


def test_editing_files_still_forks(client, workspace):
    """The expensive route stays expensive, and stays available."""
    before = _skill(client, workspace)
    files = dict(before.get("files") or {}) or {"SKILL.md": "---\nname: x\n---\n# x\n"}
    files["SKILL.md"] = files["SKILL.md"] + "\n<!-- a real rewrite -->\n"

    response = client.patch(
        "/api/v1/skills/oryh-my-work", headers=workspace, json={"files": files}
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["kind"] == "custom"


def test_the_calibration_reaches_the_rendered_bundle(client, workspace):
    client.patch(
        "/api/v1/skills/oryh-my-work",
        headers=workspace,
        json={"calibration": "报待办时只列标题。"},
    )
    rendered = _bundle_text(client, workspace)
    assert CALIBRATION_HEADING in rendered
    assert "报待办时只列标题。" in rendered
    # The section is last, so it reads after the rules it refines.
    assert rendered.index(CALIBRATION_HEADING) > rendered.index("## ")


def test_the_rendered_section_states_the_skill_wins(client, workspace):
    """A preference must not read as a licence."""
    client.patch(
        "/api/v1/skills/oryh-my-work",
        headers=workspace,
        json={"calibration": "凡事从简。"},
    )
    rendered = _bundle_text(client, workspace)
    assert "the skill wins" in rendered
    assert "What This Skill Never Does" in rendered


def test_an_uncalibrated_skill_gets_no_empty_heading(client, workspace):
    rendered = _bundle_text(client, workspace)
    assert CALIBRATION_HEADING not in rendered, (
        "an empty section in every bundle trains readers to skip the heading"
    )


def test_calibration_moves_the_files_hash(client, workspace):
    """What makes the session-entry staleness check notice.

    A refinement that did not move the hash would sit in the registry while
    every installed copy kept the old wording, and nothing would say so.
    """
    before = _skill(client, workspace)
    response = client.patch(
        "/api/v1/skills/oryh-my-work", headers=workspace, json={"calibration": "从简。"}
    )
    after = response.json()["data"]
    assert after["version"] == before["version"] + 1

    # `/my/skills/manifest` needs a USER-bound key, and this fixture drives a
    # service key — so assert on what the manifest is built from. The endpoint's
    # own coverage lives in the bundle tests.
    files = before.get("files") or {"SKILL.md": "x"}
    assert skill_files_hash(files, after["calibration"]) != skill_files_hash(files, None)


def test_clearing_calibration_removes_the_section(client, workspace):
    client.patch(
        "/api/v1/skills/oryh-my-work", headers=workspace, json={"calibration": "从简。"}
    )
    assert CALIBRATION_HEADING in _bundle_text(client, workspace)

    response = client.patch(
        "/api/v1/skills/oryh-my-work", headers=workspace, json={"calibration": ""}
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["calibration"] is None
    assert CALIBRATION_HEADING not in _bundle_text(client, workspace)


def test_two_workspaces_calibrate_the_same_skill_differently(client):
    """The question this feature was built for."""
    brief = provision_tenant(client, company_name="Brief Co", email="admin@brief.example")
    full = provision_tenant(client, company_name="Full Co", email="admin@full.example")
    brief_headers = {"X-API-Key": brief["plain_text_api_key"]}
    full_headers = {"X-API-Key": full["plain_text_api_key"]}

    client.patch(
        "/api/v1/skills/oryh-my-work",
        headers=brief_headers,
        json={"calibration": "只列标题、到期、状态。"},
    )
    client.patch(
        "/api/v1/skills/oryh-my-work",
        headers=full_headers,
        json={"calibration": "同时带上每条待办关联单据的明细。"},
    )

    brief_text = _bundle_text(client, brief_headers)
    full_text = _bundle_text(client, full_headers)
    assert "只列标题、到期、状态。" in brief_text
    assert "只列标题、到期、状态。" not in full_text
    assert "同时带上每条待办关联单据的明细。" in full_text
    # Both still the shipped skill, both still tracking the catalog.
    assert _skill(client, brief_headers)["kind"] == "product"
    assert _skill(client, full_headers)["kind"] == "product"


def test_the_section_helper_is_empty_for_nothing() -> None:
    assert calibration_section(None) == ""
    assert calibration_section("") == ""
    assert calibration_section("   \n  ") == ""
    assert CALIBRATION_BOUNDARY in calibration_section("something")


def test_absent_calibration_leaves_every_existing_hash_unchanged() -> None:
    files = {"SKILL.md": "---\nname: x\n---\n"}
    assert skill_files_hash(files) == skill_files_hash(files, None)
    assert skill_files_hash(files) == skill_files_hash(files, "  ")
    assert skill_files_hash(files) != skill_files_hash(files, "brief please")


def test_a_calibration_cannot_collide_with_a_file() -> None:
    """What the `calibration\\0` marker is actually for: domain separation.

    Without it the calibration's bytes would join the same stream the file
    paths and contents feed, so a calibration could be written to produce the
    digest of some other skill's files — and a client comparing hashes would
    believe an installed copy current when it is not. A mutation aimed at that
    marker line survived the first suite, because every other assertion only
    ever compared "calibrated" with "uncalibrated".
    """
    # These two differ ONLY in where the boundary between fields falls.
    a = skill_files_hash({"SKILL.md": "one"}, "two")
    b = skill_files_hash({"SKILL.md": "one\x00two"}, None)
    assert a != b, "calibration bytes must not be confusable with file bytes"


def test_the_hash_reads_the_calibration_TEXT_not_just_its_presence() -> None:
    """Two different refinements must not share a hash.

    A mutation run caught this: deleting the line that feeds the text into the
    digest left every assertion passing, because they all compared "calibrated"
    against "not calibrated" — a difference the length-prefixed marker alone
    still produced. An admin who REVISED a calibration would then move nothing,
    and every installed copy would keep the old wording with nothing to say so.
    """
    files = {"SKILL.md": "---\nname: x\n---\n"}
    assert skill_files_hash(files, "list titles only") != skill_files_hash(
        files, "include the linked record's detail"
    )
