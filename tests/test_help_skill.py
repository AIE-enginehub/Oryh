"""The help skill: questions ABOUT oryh are answered from the documentation,
not by researching the API. What is pinned: the references are the docs,
byte for byte, rendered by one script; the skill carries no gate and lands
in every bundle, including a member's with no permissions; the one rule and
the first FAQ answer (a role is not needed to grant one capability) are in
the text."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import make_client, provision_tenant, invite_member

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "oryh-help"


def test_the_references_are_the_documentation_byte_for_byte() -> None:
    check = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync_help_references.py"), "--check"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    for path in SKILL.glob("references/*.md"):
        text = path.read_text(encoding="utf-8")
        if path.name != "faq.md":
            assert text.startswith("<!-- generated from docs/"), path.name
        assert "](../" not in text and "](docs/" not in text, \
            f"{path.name}: a relative link has nothing to point at inside a bundle"


def test_everyone_gets_the_help_skill() -> None:
    skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "required_capability" not in skill_md.split("---")[1], "help is ungated"
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Help Co", email="admin@help.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        nobody = invite_member(client, admin, "nobody", [])
        names = {row["name"] for row in client.get("/api/v1/my/skills/manifest",
                                                   headers=nobody).json()["data"]}
        assert "oryh-help" in names, "a member with no permissions still gets the manual"


def test_the_rule_and_the_first_answer_are_in_the_text() -> None:
    skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "Documentation first, API only for live facts" in skill_md
    assert "never research the API" in skill_md
    faq = (SKILL / "references" / "faq.md").read_text(encoding="utf-8")
    assert "do I have to make them an admin" in faq and "`master_data.manage`" in faq
    assert "No. Capabilities are the unit of grant" in faq
