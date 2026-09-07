"""An agent should know an endpoint's parameters before its first call.

Skills say what to do with an endpoint; they cannot carry every parameter's
name, type and requiredness without drifting from the server. So each skill
that names an endpoint ships a generated `references/api-contract.md` rendered
from the OpenAPI document, and every such skill includes the one conventions
fragment (envelope, ids, lists, paging, writes, status codes). Both are pinned
here: the contract byte for byte, the fragment by presence.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from app.services.provisioning import PRODUCT_SKILLS_DIR

ROOT = Path(__file__).resolve().parents[1]
REQUEST_LINE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9_\-/{}.]+)")


def _sync_module():
    spec = importlib.util.spec_from_file_location(
        "sync_skill_api_contracts", ROOT / "scripts" / "sync_skill_api_contracts.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _api_skills() -> list[Path]:
    out = []
    for d in sorted(PRODUCT_SKILLS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        prose = [p for p in d.rglob("*.md") if p.name != "api-contract.md"]
        if any(REQUEST_LINE.search(p.read_text(encoding="utf-8")) for p in prose):
            out.append(d)
    return out


def test_the_contract_files_are_the_openapi_document_byte_for_byte() -> None:
    expected = _sync_module().expected()
    assert expected, "no skill names an endpoint?"
    stale = [
        str(path.relative_to(ROOT))
        for path, text in expected.items()
        if not path.exists() or path.read_text(encoding="utf-8") != text
    ]
    assert not stale, (
        "api-contract.md drifted from the server's contract in: "
        + ", ".join(stale)
        + " — run `python scripts/sync_skill_api_contracts.py`"
    )
    orphans = [
        str(p.relative_to(ROOT))
        for p in PRODUCT_SKILLS_DIR.glob("*/references/api-contract.md")
        if p not in expected
    ]
    assert not orphans, f"contract files for skills that name no endpoint: {orphans}"


def test_every_skill_that_names_an_endpoint_carries_the_conventions() -> None:
    include = "{{include:_common/api-conventions.md}}"
    missing = [
        d.name for d in _api_skills()
        if not any(include in p.read_text(encoding="utf-8") for p in d.rglob("*.md"))
    ]
    assert not missing, f"skills calling the API without the conventions: {missing}"
    fragment = (PRODUCT_SKILLS_DIR / "_common" / "api-conventions.md").read_text(encoding="utf-8")
    for phrase in ("references/api-contract.md", "meta.total", "clamped", "One try per fact", "`409`"):
        assert phrase in fragment, phrase


def test_the_contract_names_what_an_agent_used_to_guess() -> None:
    contract = (PRODUCT_SKILLS_DIR / "oryh-timesheet-submit" / "references" / "api-contract.md").read_text(encoding="utf-8")
    assert "## POST /timesheet-headers" in contract
    assert "| `validate_only` | query | boolean | no |" in contract
    assert "| `entries` | array of objects (fields below) | optional |" in contract
    assert "| `employee_id` | string | required |" in contract
    assert "| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |" in contract


def test_every_skill_with_the_conventions_ships_the_request_helper() -> None:
    """The conventions say "one call is one command — scripts/oryh_request.py in
    this skill's own directory"; a skill that says so and does not carry it
    sends the agent back to writing a script per request."""
    include = "{{include:_common/api-conventions.md}}"
    missing = [
        d.name for d in _api_skills()
        if any(include in p.read_text(encoding="utf-8") for p in d.rglob("*.md"))
        and not (d / "scripts" / "oryh_request.py").is_file()
    ]
    assert not missing, f"these carry the conventions but no scripts/oryh_request.py: {missing}"
    helper = (PRODUCT_SKILLS_DIR / "_common" / "scripts" / "oryh_request.py").read_text(encoding="utf-8")
    assert "Never retries" in helper and "ORYH_API_KEY" in helper

