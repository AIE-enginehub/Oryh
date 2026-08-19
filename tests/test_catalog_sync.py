"""The product-catalog sync must respect tenant tuning.

Content (files, and the description that lives in SKILL.md frontmatter)
follows the shipped catalog. Gating (required_capability) and archival
(status) belong to the tenant once they change them: the sync tells an
untouched default from a tenant re-gate by comparing against the recorded
catalog baseline. These tests drive provision_product_skills against a
temporary catalog directory and mutate it like successive deploys.
"""

from __future__ import annotations

import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.services.provisioning as provisioning
from app.models import Tenant, TenantSkill, TenantSkillAssignment

from conftest import make_session

TENANT = "33333333-3333-3333-3333-333333333333"


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    with make_session([Tenant(id=TENANT, name="Sync Co")]) as session:
        yield session


@pytest.fixture()
def catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(provisioning, "PRODUCT_SKILLS_DIR", tmp_path)
    return tmp_path


def write_skill(catalog: Path, name: str, *, capability: str | None, body: str = "steps") -> None:
    skill_dir = catalog / name
    skill_dir.mkdir(exist_ok=True)
    gate = f"required_capability: {capability}\n" if capability else ""
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: does {name} things ({body})\n{gate}---\n\n# {name}\n\n{body}\n",
        encoding="utf-8",
    )


def get_skill(db: Session, name: str) -> TenantSkill:
    skill = db.scalar(select(TenantSkill).where(TenantSkill.tenant_id == TENANT, TenantSkill.name == name))
    assert skill is not None
    return skill


def test_seed_records_the_catalog_baseline(db: Session, catalog: Path) -> None:
    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own")
    assert provisioning.provision_product_skills(db, TENANT) == 1
    db.commit()
    skill = get_skill(db, "oryh-thing-submit")
    assert skill.required_capability == "thing.submit_own"
    assert skill.catalog_required_capability == "thing.submit_own"
    assert skill.version == 1


def test_untouched_gate_tracks_the_catalog(db: Session, catalog: Path) -> None:
    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()

    # next deploy renames the capability in the frontmatter (a file change)
    write_skill(catalog, "oryh-thing-submit", capability="thing.file_own")
    assert provisioning.provision_product_skills(db, TENANT) == 1
    db.commit()
    skill = get_skill(db, "oryh-thing-submit")
    assert skill.required_capability == "thing.file_own"
    assert skill.catalog_required_capability == "thing.file_own"
    assert skill.version == 2  # frontmatter is file content


def test_tenant_regate_survives_content_updates(db: Session, catalog: Path) -> None:
    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()

    skill = get_skill(db, "oryh-thing-submit")
    skill.required_capability = "acme.thing.gate"  # tenant re-gates
    db.commit()

    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own", body="better steps")
    assert provisioning.provision_product_skills(db, TENANT) == 1
    db.commit()
    skill = get_skill(db, "oryh-thing-submit")
    assert skill.required_capability == "acme.thing.gate"  # override kept
    assert skill.version == 2  # content still followed the catalog
    assert "better steps" in skill.files_jsonb["SKILL.md"]
    assert "better steps" in skill.description


def test_regate_survives_even_when_the_catalog_gate_moves(db: Session, catalog: Path) -> None:
    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()
    skill = get_skill(db, "oryh-thing-submit")
    skill.required_capability = "acme.thing.gate"
    db.commit()

    write_skill(catalog, "oryh-thing-submit", capability="thing.file_own")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()
    skill = get_skill(db, "oryh-thing-submit")
    assert skill.required_capability == "acme.thing.gate"  # still the tenant's
    assert skill.catalog_required_capability == "thing.file_own"  # baseline moved

    # resetting to the (new) baseline resumes tracking on the next change
    skill.required_capability = "thing.file_own"
    db.commit()
    write_skill(catalog, "oryh-thing-submit", capability="thing.record_own")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()
    skill = get_skill(db, "oryh-thing-submit")
    assert skill.required_capability == "thing.record_own"
    assert skill.catalog_required_capability == "thing.record_own"


def test_archived_product_skill_stays_archived_but_content_refreshes(db: Session, catalog: Path) -> None:
    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()
    skill = get_skill(db, "oryh-thing-submit")
    skill.status = "archived"  # tenant switched it off
    db.commit()

    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own", body="v2 steps")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()
    skill = get_skill(db, "oryh-thing-submit")
    assert skill.status == "archived"  # not force-revived
    assert "v2 steps" in skill.files_jsonb["SKILL.md"]  # revival would be current


def test_catalog_sync_leaves_the_tenant_audience_alone(db: Session, catalog: Path) -> None:
    """Narrowing a product skill to one team is a distribution decision, not a
    content edit — it must survive deploys and must not fork the skill."""
    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()

    skill = get_skill(db, "oryh-thing-submit")
    skill.distribution_mode = "targeted"
    db.add(TenantSkillAssignment(
        tenant_id=TENANT, skill_id=skill.id, subject_type="role", subject_id="procurement",
    ))
    db.commit()

    # a deploy ships new content for the same skill
    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own", body="revised steps")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()

    skill = get_skill(db, "oryh-thing-submit")
    assert skill.version == 2, "content still follows the catalog"
    assert skill.kind == "product", "a distribution decision must not fork the skill"
    assert skill.distribution_mode == "targeted"
    rows = db.scalars(
        select(TenantSkillAssignment).where(TenantSkillAssignment.skill_id == skill.id)
    ).all()
    assert [(r.subject_type, r.subject_id) for r in rows] == [("role", "procurement")]


def test_withdrawn_product_skill_is_archived_so_it_stops_shipping(db: Session, catalog: Path) -> None:
    """A skill removed from the catalog must stop reaching agents. Left active
    it would ship forever, frozen at its last content, instructing agents to
    call endpoints that may no longer exist."""
    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own")
    write_skill(catalog, "oryh-gone", capability="thing.submit_own")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()
    assert get_skill(db, "oryh-gone").status == "active"

    # next deploy withdraws it from the shipped catalog
    shutil.rmtree(catalog / "oryh-gone")
    assert provisioning.provision_product_skills(db, TENANT) == 1
    db.commit()
    assert get_skill(db, "oryh-gone").status == "archived"
    # the survivor is untouched
    assert get_skill(db, "oryh-thing-submit").status == "active"

    # and it stays retired: reviving it under the product name is archived
    # again, because nothing upstream stands behind that content anymore
    get_skill(db, "oryh-gone").status = "active"
    db.commit()
    assert provisioning.provision_product_skills(db, TENANT) == 1
    db.commit()
    assert get_skill(db, "oryh-gone").status == "archived"


def test_withdrawal_never_touches_a_tenants_own_skill(db: Session, catalog: Path) -> None:
    """Custom skills are the fork path out of a retirement — the catalog has
    no claim on them, whatever their name."""
    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()
    db.add(TenantSkill(tenant_id=TENANT, name="our-own-thing", kind="custom", status="active"))
    db.commit()

    shutil.rmtree(catalog / "oryh-thing-submit")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()
    assert get_skill(db, "our-own-thing").status == "active"


def test_an_empty_catalog_directory_retires_nothing(db: Session, catalog: Path) -> None:
    """A catalog that failed to ship (empty directory, bad deploy) must not be
    read as 'every skill was withdrawn' — that would silently disarm every
    tenant's agents."""
    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()

    shutil.rmtree(catalog / "oryh-thing-submit")
    assert provisioning.provision_product_skills(db, TENANT) == 0
    db.commit()
    assert get_skill(db, "oryh-thing-submit").status == "active"


def test_idempotent_when_nothing_changed(db: Session, catalog: Path) -> None:
    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()
    assert provisioning.provision_product_skills(db, TENANT) == 0
    skill = get_skill(db, "oryh-thing-submit")
    assert skill.version == 1


def test_calibration_survives_every_content_update(db: Session, catalog: Path) -> None:
    """The durability promise the whole feature rests on.

    Calibration is worth having only because it is NOT a fork: the workspace
    keeps receiving catalog corrections while its own refinement stays. Today
    that holds because the sync writes four named columns and calibration is
    not among them — true by construction, which is exactly the kind of
    property a later "copy the catalog row over" refactor erases silently. The
    tenant would lose text they wrote, on a deploy that changed something
    unrelated, with nothing reporting it.
    """
    write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own")
    provisioning.provision_product_skills(db, TENANT)
    db.commit()

    skill = get_skill(db, "oryh-thing-submit")
    skill.calibration = "List titles only; never expand the linked record."
    db.commit()

    for body in ("better steps", "better steps again", "and once more"):
        write_skill(catalog, "oryh-thing-submit", capability="thing.submit_own", body=body)
        provisioning.provision_product_skills(db, TENANT)
        db.commit()

    skill = get_skill(db, "oryh-thing-submit")
    assert skill.calibration == "List titles only; never expand the linked record."
    assert skill.kind == "product"                      # still tracking
    assert "and once more" in skill.files_jsonb["SKILL.md"]  # still receiving
