"""A migration named in prose must be a migration that exists.

`tests/test_migration_imports.py` checks what migrations import. This checks the
other direction: what the rest of the repository claims about them. A revision
id in a comment is a load-bearing statement — "rows written before X are
legitimately in this shape" tells the next person exactly which data to trust —
and it is the kind of statement that is written from memory.

It caught its own reason for existing on the first run: an advisory check in
`scripts/data_integrity_audit.py` cited `20260816_0056`, a revision that was
never created, in a change that needed no schema at all. Nothing would have
found that. The comment reads perfectly.

Only `NNNNNNNN_NNNN` tokens are checked — the shape this repo's revisions
actually take. A bare date, or `head`, or a table name, is not a claim about a
migration.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERSIONS = ROOT / "alembic" / "versions"

# `20260816_0055`, optionally with a trailing slug as the filenames carry.
REVISION = re.compile(r"\b(\d{8}_\d{4})(?:_[a-z0-9_]+)?\b")

SEARCHED = ("*.py", "*.md", "*.sh", "*.sql", "*.yaml", "*.yml")
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".claude", "dist", "build"}
# This file names the revision that was never written, on purpose, as the story
# of why it exists. Checking itself would be the one false positive.
SKIP_FILES = {"tests/test_migration_references.py"}


def known_revisions() -> set[str]:
    return {path.name[:13] for path in VERSIONS.glob("*.py")}


def searched_files() -> list[pathlib.Path]:
    files = []
    for pattern in SEARCHED:
        for path in ROOT.rglob(pattern):
            if SKIP_DIRS & set(path.relative_to(ROOT).parts):
                continue
            files.append(path)
    return files


def test_every_revision_id_in_the_repository_names_a_real_migration() -> None:
    known = known_revisions()
    assert known, "no migrations found — the glob is wrong, not the repository"

    dangling: dict[str, list[str]] = {}
    for path in searched_files():
        if path.parent == VERSIONS:
            continue  # a migration's own down_revision chain is checked by alembic
        if str(path.relative_to(ROOT)) in SKIP_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for revision in {m.group(1) for m in REVISION.finditer(text)}:
            if revision not in known:
                dangling.setdefault(revision, []).append(str(path.relative_to(ROOT)))

    assert dangling == {}, (
        f"{dangling} name revisions that do not exist. A comment citing a migration is "
        "telling the next person which data to trust; one citing a migration nobody "
        "wrote is worse than no comment at all"
    )
