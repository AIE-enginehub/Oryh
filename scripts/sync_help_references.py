#!/usr/bin/env python3
"""Render the user-facing documentation into `skills/oryh-help/references/`.

The help skill answers questions ABOUT oryh — what a capability means, whether
a role is needed, which desk does what — from the same documentation people
read, so the two can never disagree. This script is the only writer of the
generated files; `tests/test_help_skill.py` fails when they drift.

Relative markdown links are flattened to their text: inside a skill bundle
there is no docs tree for them to point at. Absolute http(s) links survive.

    python scripts/sync_help_references.py          # write
    python scripts/sync_help_references.py --check  # exit 1 when out of date
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "skills" / "oryh-help" / "references"

# (source under the repo, file name inside references/)
SOURCES: tuple[tuple[str, str], ...] = (
    ("docs/manual/index.md", "manual-index.md"),
    ("docs/manual/first-boot.md", "manual-first-boot.md"),
    ("docs/manual/workspace.md", "manual-workspace.md"),
    ("docs/manual/daily-use.md", "manual-daily-use.md"),
    ("docs/manual/administration.md", "manual-administration.md"),
    ("docs/manual/connect-agent.md", "manual-connect-agent.md"),
    ("docs/capabilities-skills-api.md", "capabilities-skills-api.md"),
    ("docs/scoped-skill-capabilities.md", "scoped-skill-capabilities.md"),
)

HEADER = "<!-- generated from {source} by the help-references sync (sync_help_references) — edit the source, not this file -->\n\n"
_RELATIVE_LINK = re.compile(r"\[([^\]]+)\]\((?!https?://|mailto:)[^)]+\)")


def render(source: str) -> str:
    text = (ROOT / source).read_text(encoding="utf-8")
    return HEADER.format(source=source) + _RELATIVE_LINK.sub(r"\1", text)


def expected() -> dict[str, str]:
    return {name: render(source) for source, name in SOURCES}


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale: list[str] = []
    for name, content in expected().items():
        path = TARGET / name
        if path.exists() and path.read_text(encoding="utf-8") == content:
            continue
        stale.append(name)
        if not check:
            path.write_text(content, encoding="utf-8")
    if check and stale:
        print("out of date: " + ", ".join(stale))
        return 1
    print(("would rewrite " if check else "wrote ") + str(len(stale)) + " file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
