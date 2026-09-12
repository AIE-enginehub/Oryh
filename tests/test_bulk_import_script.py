"""The bundled bulk-import script: a stock take is a kind, and a file that
lost rows on the way is refused before anything is sent.

A tenant imported a 1,000-position stock take and 999 landed — every one the
server received, in three clean chunks. The row went missing between the
sheet and the request: the agent's file reader stops at 1,000 lines, the
header took one, and nothing in the chain counted the sheet. The script now
takes the sheet's own count and refuses a shortfall; the inventory skill
makes passing it mandatory.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from app.services.provisioning import PRODUCT_SKILLS_DIR, read_skill_dir

SCRIPT = PRODUCT_SKILLS_DIR / "_common" / "scripts" / "bulk_import.py"


def _module():
    # never leave bytecode inside the skills tree: the reader skips it now,
    # but a .pyc beside a bundled script is still litter nobody wants shipped
    before, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec = importlib.util.spec_from_file_location("bulk_import", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = before
    return module


def test_the_skill_reader_ignores_bytecode(tmp_path: Path) -> None:
    (tmp_path / "_common").mkdir()
    skill = tmp_path / "oryh-thing"
    (skill / "scripts" / "__pycache__").mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: oryh-thing\ndescription: x\n---\n", encoding="utf-8")
    (skill / "scripts" / "tool.py").write_text("print(1)\n", encoding="utf-8")
    (skill / "scripts" / "__pycache__" / "tool.cpython-313.pyc").write_bytes(b"\xf3\r\r\n\x00")
    files = read_skill_dir(skill)
    assert set(files) == {"SKILL.md", "scripts/tool.py"}


def test_a_stock_take_is_a_kind_with_its_own_route() -> None:
    module = _module()
    assert "inventory" in module.KINDS
    assert module.ENDPOINTS["inventory"] == "/inventory-items/bulk"
    assert module.ENDPOINTS["products"] == "/products/bulk"
    assert module.SERVER_MAX_ROWS == 500


def test_a_file_that_lost_rows_is_refused_before_anything_is_sent(tmp_path: Path) -> None:
    rows = tmp_path / "rows.json"
    rows.write_text(json.dumps([{"product_code": f"P-{i}", "quantity": 1} for i in range(999)]))
    # no network is reachable at this address; the refusal must come first
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--kind", "inventory", str(rows), "--expected-rows", "1000",
         "--base-url", "http://127.0.0.1:9", "--api-key", "x"],
        capture_output=True, text=True, timeout=30,
    )
    assert run.returncode == 2, run.stderr
    report = json.loads(run.stdout)
    assert report["total_rows"] == 999 and report["expected_rows"] == 1000
    assert report["rows_missing_before_send"] == 1 and report["chunks_sent"] == 0
    assert "re-read the sheet in parts" in report["error"]


def test_both_importing_skills_ship_the_script_expanded() -> None:
    for name in ("oryh-master-data", "oryh-inventory"):
        files = read_skill_dir(PRODUCT_SKILLS_DIR / name)
        body = files.get("scripts/bulk_import.py") or ""
        assert "ENDPOINTS" in body and "{{include:" not in body, name
        skill = files["SKILL.md"]
        assert "--expected-rows" in skill, f"{name} never tells the agent to pass the sheet's count"
    inventory = (PRODUCT_SKILLS_DIR / "oryh-inventory" / "SKILL.md").read_text(encoding="utf-8")
    assert "at most 500 rows per call" in inventory
    assert "--kind inventory" in inventory
    assert "sheet 1,000 rows" in inventory, "the read-back chain is what makes a lost row visible"
