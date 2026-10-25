"""The shipped rule catalog seeds drafts, and the sync respects what the
workspace made its own.

`rules/<kind>/<object_type>.md` becomes a DRAFT `business_rules` row per
tenant — never a published one, because the hosted runner drives a family
only on a published approval flow and a default nobody here wrote must not
decide who approves. The sync rule is the product skills': an untouched seed
follows the catalog, an edited or published scope is the tenant's, a
withdrawn file soft-deletes the untouched drafts it seeded.
"""

from __future__ import annotations

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_rule_catalog.json').read_text(encoding="utf-8"))


import hashlib
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.services.provisioning as provisioning
from app.core.entity_types import HOSTED_FAMILIES
from app.models import BusinessRule, Tenant

from conftest import make_session

TENANT = "44444444-4444-4444-4444-444444444444"


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    with make_session([Tenant(id=TENANT, name="Rules Co")]) as session:
        yield session


@pytest.fixture()
def catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(provisioning, "RULES_DIR", tmp_path)
    monkeypatch.setattr(provisioning.settings, "locale", "en", raising=False)
    return tmp_path


def write_rule(catalog: Path, kind: str, object_type: str, en: str, zh: str = _ZH_TEXT['TEXT_72726D8818F69306'], *, title: str = "T") -> None:
    (catalog / kind).mkdir(exist_ok=True)
    (catalog / kind / f"{object_type}.md").write_text(
        f"---\nkind: {kind}\nentity_kind: builtin\nobject_type: {object_type}\nname: default\ntitle: {title}{_ZH_TEXT['TEXT_DD61C990E7A498AE']}{en}\n\n<!-- zh -->\n{zh}\n",
        encoding="utf-8",
    )


def rows(db: Session, code: str) -> list[BusinessRule]:
    return db.scalars(select(BusinessRule).where(BusinessRule.tenant_id == TENANT, BusinessRule.code == code)
                      .order_by(BusinessRule.version)).all()


def sha(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


# --- the shipped catalog itself ----------------------------------------------------------


def test_every_shipped_rule_is_a_draft_for_a_hosted_family() -> None:
    entries = provisioning.load_rule_catalog("en")
    assert entries, "the catalog ships"
    for entry in entries:
        assert entry["kind"] in provisioning.SCOPED_RULE_KINDS
        assert entry["entity_kind"] == "builtin"
        assert entry["object_type"] in HOSTED_FAMILIES, entry
        assert entry["name"] == "default" and entry["body"] and entry["title"]
    codes = {f"{e['kind']}:{e['entity_kind']}:{e['object_type']}:{e['name']}" for e in entries}
    assert len(codes) == len(entries), "one file per scope"
    assert {e["object_type"] for e in entries if e["kind"] == "approval_flow"} == set(HOSTED_FAMILIES), \
        "every hosted family gets a starting approval flow"
    chinese = provisioning.load_rule_catalog("zh")
    assert [e["body"] for e in chinese] != [e["body"] for e in entries], "the locale picks the half"
    assert all(e["title"] and e["body"] for e in chinese)


def test_a_malformed_catalog_file_refuses_to_load(catalog: Path) -> None:
    (catalog / "data_rule").mkdir()
    (catalog / "data_rule" / "x.md").write_text("---\nkind: data_rule\nentity_kind: builtin\nobject_type: x\ntitle: t\n---\nonly english\n")
    with pytest.raises(ValueError, match="both language halves"):
        provisioning.load_rule_catalog("en")
    (catalog / "data_rule" / "x.md").write_text("---\nkind: policy\nentity_kind: builtin\nobject_type: x\ntitle: t\n---\na\n<!-- zh -->\nb\n")
    with pytest.raises(ValueError, match="kind must be"):
        provisioning.load_rule_catalog("en")


# --- seeding and the sync -----------------------------------------------------------------


def test_seeds_drafts_with_their_provenance(db: Session, catalog: Path) -> None:
    write_rule(catalog, "approval_flow", "expense_claim", "manager approves", title="Expense approval flow")
    write_rule(catalog, "data_rule", "expense_claim", "receipts attached")
    assert provisioning.provision_rule_catalog(db, TENANT) == 2
    db.commit()
    (row,) = rows(db, "approval_flow:builtin:expense_claim:default")
    assert row.status == "draft" and row.origin == "catalog" and row.version == 1
    assert row.body == "manager approves" and row.title == "Expense approval flow"
    assert row.catalog_hash == sha("manager approves") and row.created_by == "product-catalog"
    assert row.published_at is None and row.effective_from is None
    assert provisioning.provision_rule_catalog(db, TENANT) == 0, "idempotent"


def test_an_untouched_seed_follows_the_catalog(db: Session, catalog: Path) -> None:
    write_rule(catalog, "approval_flow", "expense_claim", "v1 text")
    provisioning.provision_rule_catalog(db, TENANT); db.commit()
    write_rule(catalog, "approval_flow", "expense_claim", "v2 text", title="Renamed")
    assert provisioning.provision_rule_catalog(db, TENANT) == 1
    db.commit()
    (row,) = rows(db, "approval_flow:builtin:expense_claim:default")
    assert row.body == "v2 text" and row.title == "Renamed" and row.catalog_hash == sha("v2 text")
    assert row.version == 1 and row.status == "draft", "refreshed in place, not versioned"


def test_an_edited_seed_is_the_tenants(db: Session, catalog: Path) -> None:
    write_rule(catalog, "approval_flow", "expense_claim", "v1 text")
    provisioning.provision_rule_catalog(db, TENANT); db.commit()
    (row,) = rows(db, "approval_flow:builtin:expense_claim:default")
    row.body = "our own words"; db.commit()
    write_rule(catalog, "approval_flow", "expense_claim", "v2 text")
    assert provisioning.provision_rule_catalog(db, TENANT) == 0
    db.commit()
    (row,) = rows(db, "approval_flow:builtin:expense_claim:default")
    assert row.body == "our own words"


def test_a_published_scope_never_gets_a_seed(db: Session, catalog: Path) -> None:
    from datetime import datetime, timezone

    from app.core.business_date import business_today
    db.add(BusinessRule(tenant_id=TENANT, kind="approval_flow", entity_kind="builtin", object_type="expense_claim",
                        name="default", code="approval_flow:builtin:expense_claim:default", version=1, title="ours",
                        body="published by us", status="published", effective_from=business_today(),
                        published_at=datetime.now(timezone.utc), published_by="user:1"))
    db.commit()
    write_rule(catalog, "approval_flow", "expense_claim", "catalog text")
    assert provisioning.provision_rule_catalog(db, TENANT) == 0
    db.commit()
    assert [r.body for r in rows(db, "approval_flow:builtin:expense_claim:default")] == ["published by us"]

    # a seed the tenant published later is theirs too, and the next deploy leaves it alone
    write_rule(catalog, "data_rule", "expense_claim", "seed")
    provisioning.provision_rule_catalog(db, TENANT); db.commit()
    (seed,) = rows(db, "data_rule:builtin:expense_claim:default")
    seed.status = "published"; seed.effective_from = business_today()
    seed.published_at = datetime.now(timezone.utc); seed.published_by = "user:1"; db.commit()
    write_rule(catalog, "data_rule", "expense_claim", "seed v2")
    assert provisioning.provision_rule_catalog(db, TENANT) == 0
    db.commit()
    assert rows(db, "data_rule:builtin:expense_claim:default")[0].body == "seed"


def test_a_withdrawn_file_retires_its_untouched_draft_only(db: Session, catalog: Path) -> None:
    write_rule(catalog, "linkage", "sales_order", "pick then ship")
    write_rule(catalog, "linkage", "expense_claim", "pay directly")
    write_rule(catalog, "data_rule", "sales_order", "ship-to filled in")
    provisioning.provision_rule_catalog(db, TENANT); db.commit()
    (edited,) = rows(db, "linkage:builtin:expense_claim:default")
    edited.body = "bill first, then pay"; db.commit()
    (catalog / "linkage" / "sales_order.md").unlink()
    (catalog / "linkage" / "expense_claim.md").unlink()
    assert provisioning.provision_rule_catalog(db, TENANT) == 1
    db.commit()
    (gone,) = rows(db, "linkage:builtin:sales_order:default")
    assert gone.deleted_at is not None and gone.deleted_by == "product-catalog"
    (kept,) = rows(db, "linkage:builtin:expense_claim:default")
    assert kept.deleted_at is None and kept.body == "bill first, then pay"
    (survivor,) = rows(db, "data_rule:builtin:sales_order:default")
    assert survivor.deleted_at is None
    # and a catalog that ships nothing retires nothing — an empty rules/ is a broken deploy
    for path in catalog.rglob("*.md"):
        path.unlink()
    assert provisioning.provision_rule_catalog(db, TENANT) == 0
    db.commit()
    assert rows(db, "data_rule:builtin:sales_order:default")[0].deleted_at is None


def test_the_locale_picks_the_half(db: Session, catalog: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_rule(catalog, "data_rule", "timesheet_header", "every entry names a project", _ZH_TEXT['TEXT_63FDECE42883B83F'])
    monkeypatch.setattr(type(provisioning.settings), "resolved_locale", property(lambda self: "zh"))
    provisioning.provision_rule_catalog(db, TENANT); db.commit()
    (row,) = rows(db, "data_rule:builtin:timesheet_header:default")
    assert row.body == _ZH_TEXT['TEXT_63FDECE42883B83F'] and row.title == _ZH_TEXT['TEXT_C3405F8C7D9D392A']


def test_the_catalog_travels_with_the_image_and_the_export() -> None:
    """v2026.10.7.1 shipped the seeding and no rules/ in the image: `load_rule_catalog`
    found no directory, returned nothing, and 259 workspaces were seeded with
    nothing while every log said success. The catalog is read at runtime from
    the tree, so the tree the image and the open-core export carry must hold it."""
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY rules ./rules" in dockerfile, "the image must carry rules/ beside skills/"
    export_script = root / "scripts" / "export_open_core.py"
    # the exported tree carries no scripts/ — there the export has already happened
    if export_script.exists():
        assert '"rules",' in export_script.read_text(encoding="utf-8"), "the open-core export must carry rules/"
    assert provisioning.RULES_DIR.is_dir() and any(provisioning.RULES_DIR.glob("*/*.md"))
