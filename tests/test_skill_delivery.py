"""A skill reads right for how it arrives.

A bundle is files on the person's machine: a key rendered in, HTTP calls,
bundled scripts, a manifest to re-sync. An MCP connection carries its OAuth
token in the client, makes every call through a tool, and always serves the
registry's current text. Text true of only one is fenced with
`<!-- only: bundle -->` / `<!-- only: mcp -->` … `<!-- /only -->`
(app/services/delivery.py); these tests hold every product skill to it."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.api.mcp import BUNDLE_ONLY_SKILLS, _is_mcp_resource
from app.services.delivery import delivery_blocks_error, for_delivery
from app.services.provisioning import PRODUCT_SKILLS_DIR, read_skill_dir

# What an MCP agent must never be told about ITSELF: a credential, a header to
# send it in, a local script to run, its own bundle to fetch or re-sync, a URL
# to prefix.
MCP_FORBIDDEN = re.compile(
    r"X-API-Key|\{\{ORYH_API_KEY\}\}|\bapi_key\b|\{\{INSTALL_DIR\}\}|refresh_token"
    r"|python3? scripts/|scripts/[A-Za-z_]+\.py"
    r"|GET /my/skill-bundle|/my/skills/manifest|manifest\.json|\$oryh-skill-sync"
    r"|this bundle|bundle was rendered|\bapi_base_url\b|\{\{ORYH_API_BASE_URL\}\}|oryh-connect"
)
# Administrators manage OTHER people's bundles whatever their own client is:
# issuing one, and telling a colleague to run skill-sync, are product facts.
ABOUT_OTHERS_BUNDLES = re.compile(r"POST /users/\{[a-z_]+\}/skill-bundle|\$oryh-skill-sync|/my/skills/manifest")
ADMIN_SKILLS = frozenset({"oryh-access-admin", "oryh-workspace-setup", "oryh-skill-author"})
# A generated contract lists every endpoint its skill's text names; a listed
# endpoint is not an instruction, so only its credential wording is held.
CONTRACT_FORBIDDEN = re.compile(r"X-API-Key|\bapi_key\b|\bapi_base_url\b")

# Not served by MCP at all: installing and re-syncing bundles is all they do.
NOT_SERVED = BUNDLE_ONLY_SKILLS | {"oryh-connect"}
# oryh-help's references mirror the user manual, which documents bundles and
# keys for the people who use them; answering questions about them is the job.
MANUAL_MIRROR = ("oryh-help", "references/")


def _skill_dirs() -> list[Path]:
    return sorted(p for p in PRODUCT_SKILLS_DIR.iterdir() if p.is_dir() and not p.name.startswith("_"))


def _mcp_files():
    for skill_dir in _skill_dirs():
        if skill_dir.name in NOT_SERVED:
            continue
        for path, content in read_skill_dir(skill_dir).items():
            if path != "SKILL.md" and not _is_mcp_resource(path):
                continue
            if (skill_dir.name, path[: len(MANUAL_MIRROR[1])]) == MANUAL_MIRROR:
                continue
            yield skill_dir.name, path, content


def test_marker_blocks_keep_one_delivery_and_drop_the_other() -> None:
    text = "a\n<!-- only: bundle -->\nkey\n<!-- /only -->\n<!-- only: mcp -->\ntool\n<!-- /only -->\nb\n"
    assert for_delivery(text, "bundle") == "a\nkey\nb\n"
    assert for_delivery(text, "mcp") == "a\ntool\nb\n"
    quoted = "> one\n> <!-- only: bundle -->\n> key\n> <!-- /only -->\n> two\n"
    assert for_delivery(quoted, "mcp") == "> one\n> two\n"
    with pytest.raises(ValueError):
        for_delivery(text, "email")


@pytest.mark.parametrize("text, problem", [
    ("<!-- only: bundle -->\nx\n", "never closed"),
    ("x\n<!-- /only -->\n", "no block open"),
    ("<!-- only: mcp -->\n<!-- only: bundle -->\n<!-- /only -->\n", "inside"),
    ("see <!-- only: mcp --> here\n", "alone on its line"),
])
def test_malformed_markers_are_named(text: str, problem: str) -> None:
    assert problem in (delivery_blocks_error(text) or "")


def test_markers_do_not_reach_either_delivery() -> None:
    for skill_dir in _skill_dirs():
        for path, content in read_skill_dir(skill_dir).items():
            for delivery in ("bundle", "mcp"):
                assert "<!-- only:" not in for_delivery(content, delivery), f"{skill_dir.name}/{path}"
                assert "<!-- /only" not in for_delivery(content, delivery), f"{skill_dir.name}/{path}"


def test_mcp_text_carries_no_credential_script_or_bundle_instruction() -> None:
    found = []
    for name, path, content in _mcp_files():
        rule = CONTRACT_FORBIDDEN if path.endswith("api-contract.md") else MCP_FORBIDDEN
        for number, line in enumerate(for_delivery(content, "mcp").splitlines(), 1):
            hit = rule.search(line)
            if hit and name in ADMIN_SKILLS and ABOUT_OTHERS_BUNDLES.fullmatch(hit.group(0)):
                continue
            if hit:
                found.append(f"{name}/{path}:{number}: {hit.group(0)} — {line.strip()[:90]}")
    assert not found, "MCP-delivered skill text still says:\n  " + "\n  ".join(found)


def test_the_bundle_keeps_its_key_and_its_scripts() -> None:
    """Fencing must not strip the bundle: its skills still render the key and
    still name the scripts that ship beside them."""
    bundle = "\n".join(
        for_delivery(content, "bundle")
        for skill_dir in _skill_dirs()
        for content in read_skill_dir(skill_dir).values()
    )
    assert "{{ORYH_API_KEY}}" in bundle
    assert "X-API-Key" in bundle
    assert "scripts/bulk_import.py" in bundle
