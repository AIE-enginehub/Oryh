"""A doc that names an API endpoint must name one the API serves.

Written after three wrong answers about how stale these docs are — 72 dead
references, then everything dead, then 21. The real number is zero, and each
wrong answer came from a checker that did not understand what it was reading.
So the notations are handled explicitly here, and each exemption says why it
exists:

- `frontend/openapi.json` is the source of truth. It is generated from the
  running app, regenerated on release, and already gates the frontend types.
  Scanning `routes.py` misses `bundles.py`, `auth.py` and five other modules;
  importing the app yields ten routes because the routers mount conditionally.
- `` `POST`/`PATCH`/`DELETE /policies*` `` is one reference, not three, and the
  `*` means "and its sub-paths". A checker that reads it as `DELETE /policies`
  reports fifteen failures against a correct document.
- `/web/...` is server-rendered HTML, not API, and is deliberately absent from
  the OpenAPI document. Its routes live in `app/web/routes.py`.
- Findings reports quote what an agent actually sent, including paths that
  never existed — `GET /totally-made-up-path` is the point of that paragraph.
  Rewriting those would make the record lie, so records are exempt.

A checker with false positives is worse than none: it teaches everyone to
ignore the one time it is right.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SPEC = ROOT / "frontend/openapi.json"

# A reference is `VERB /path`. A trailing `*` widens it to sub-paths, and a
# run of verbs before one path applies to all of them.
_REFERENCE = re.compile(
    r"(?P<verbs>(?:`?(?:GET|POST|PATCH|PUT|DELETE)`?\s*/?\s*)+)"
    r"`?(?P<path>/[A-Za-z0-9\-{}/_.]+)(?P<wild>\*?)"
)
_VERB = re.compile(r"GET|POST|PATCH|PUT|DELETE")

# Server-rendered pages and the static site: real routes, not API operations.
_NOT_API = ("/web/", "/static/", "/assets/")

# Documents that record what happened rather than specify what is true — and
# design documents (`*-design.md`), which name the endpoints they PROPOSE;
# those become true only when the design is built, and the doc says so.
_RECORDS = re.compile(r"finding|scenario|-plan$|report|-design$")


def _normalise(path: str) -> str:
    path = re.sub(r"\{[^}]+\}", "{}", path.rstrip("`.,;):"))
    if path.startswith("/api/v1"):
        path = path[len("/api/v1"):]
    return path.rstrip("/") or "/"


def _served() -> tuple[set[tuple[str, str]], set[str]]:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    operations = {
        (method.upper(), _normalise(path))
        for path, methods in spec["paths"].items()
        for method in methods
        if method.upper() in {"GET", "POST", "PATCH", "PUT", "DELETE"}
    }
    return operations, {path for _verb, path in operations}


def _spec_docs() -> list[pathlib.Path]:
    return [p for p in sorted(DOCS.rglob("*.md")) if not _RECORDS.search(p.stem)]


def _unresolved(doc: pathlib.Path) -> list[str]:
    operations, paths = _served()
    bad: list[str] = []
    for match in _REFERENCE.finditer(doc.read_text(encoding="utf-8")):
        path = _normalise(match.group("path"))
        if any(path.startswith(prefix.rstrip("/")) for prefix in _NOT_API):
            continue
        if match.group("wild"):
            # `/policies*` covers the collection and everything under it, so it
            # resolves if anything does.
            if any(p == path or p.startswith(path + "/") for p in paths):
                continue
            bad.append(f"{match.group('path')}* — nothing under this path")
            continue
        for verb in _VERB.findall(match.group("verbs")):
            # A verb list before a collection means those verbs on the
            # RESOURCE: `POST`/`PATCH`/`DELETE /roles` is how these docs write
            # "create one, edit one, remove one", and the edit and remove are
            # served at `/roles/{id}`. Reading it literally reports fifteen
            # failures against a correct table, which is how a checker teaches
            # people to ignore it.
            if (verb, path) in operations or (verb, f"{path}/{{}}") in operations:
                continue
            bad.append(f"{verb} {match.group('path')}")
    return sorted(set(bad))


def test_the_spec_is_readable() -> None:
    operations, paths = _served()
    assert len(paths) > 150, "the OpenAPI document looks truncated — regenerate it"
    assert ("GET", "/todos") in operations


def test_there_are_specification_docs_to_check() -> None:
    assert len(_spec_docs()) >= 10, "no specification docs found — has docs/ moved?"


@pytest.mark.parametrize("doc", _spec_docs(), ids=lambda p: p.name)
def test_a_doc_names_only_endpoints_the_api_serves(doc: pathlib.Path) -> None:
    unresolved = _unresolved(doc)
    assert not unresolved, (
        f"{doc.relative_to(ROOT)} names endpoints the API does not serve:\n  "
        + "\n  ".join(unresolved)
        + "\n\nEither the doc is stale, or the endpoint moved and the doc was "
        "not updated with it. Regenerate frontend/openapi.json first if the "
        "API changed in this branch."
    )
