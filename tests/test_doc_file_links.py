"""A markdown link to a file in this repository must point at a file that exists.

The README's architecture list linked `app/api/routes.py` for as long as that
file existed and would have gone on linking it afterwards, because nothing reads
a markdown link. A decomposition renames and deletes source files; a reader
arriving at the README wants the map to be true, and a dead link is worse than
no link — it says confidently that a file exists.

Only repo-relative links are checked. `http(s)://` targets are somebody else's
uptime, `#anchors` are within-page, and `mailto:` is not a path. A link with a
`:42` line suffix is checked as the file it names; whether line 42 is still the
interesting one is not something this can know.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Directories whose markdown is a record of what was true at the time — issue
# histories, dated findings — rather than a map somebody navigates today.
#
# `public/` is exempt for a different reason: `scripts/export_open_core.py`
# copies its files to the ROOT of the exported tree, so `public/README.md`'s
# `docs/policies.md` resolves there and cannot resolve here. It is still
# checked — this same test runs inside the export, by which point that file IS
# the root README.
RECORDS = {"ops", "artifacts", "test-results", "site", "public"}
SKIP = {".git", ".venv", "node_modules", "__pycache__", ".claude", "dist", "build"}

_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _markdown_files() -> list[pathlib.Path]:
    return [
        path for path in ROOT.rglob("*.md")
        if not (set(path.relative_to(ROOT).parts) & SKIP)
        and path.relative_to(ROOT).parts[0] not in RECORDS
    ]


def test_markdown_files_were_found() -> None:
    """Guard the guard: a glob that stops matching must fail, not pass."""
    found = _markdown_files()
    assert len(found) > 10, f"only {len(found)} markdown files found"
    assert ROOT / "README.md" in found


def test_every_repo_relative_markdown_link_resolves() -> None:
    dead: list[str] = []
    for path in _markdown_files():
        for target in _LINK.findall(path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#", "mailto:", "data:")):
                continue
            named = target.split("#")[0]
            named = re.sub(r":\d+(-\d+)?$", "", named)   # a `file.py:42` anchor
            if not named:
                continue
            resolved = (path.parent / named).resolve()
            if not resolved.exists():
                dead.append(f"{path.relative_to(ROOT)} -> {target}")

    assert not dead, (
        "markdown links pointing at files that do not exist:\n  "
        + "\n  ".join(sorted(dead))
    )
