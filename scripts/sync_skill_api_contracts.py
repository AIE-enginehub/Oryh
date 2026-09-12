#!/usr/bin/env python3
"""Render each skill's `references/api-contract.md` from the server's contract.

A skill names the endpoints it uses in prose. Prose says what to do, not what
the parameter is called, what type it takes, or whether it is required — and
an agent that has to find out by trying spends the person's time on 422s. So
every product skill that names an endpoint carries a generated reference:
the operations it mentions, with query parameters, request-body fields (type,
required, enum, limits) and the summary, straight from the OpenAPI document.
Generated only; `tests/test_api_contracts.py` fails when a file drifts.

    python scripts/sync_skill_api_contracts.py          # write
    python scripts/sync_skill_api_contracts.py --check  # exit 1 when out of date
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SPEC = ROOT / "frontend" / "openapi.json"
TARGET = "api-contract.md"
HEADER = (
    "<!-- generated from the API contract by the api-contract sync "
    "(sync_skill_api_contracts) — edit the server, not this file -->\n\n"
)
PREFIX = "/api/v1"

REQUEST_LINE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9_\-/{}.]+)")
_CJK = re.compile(r"[一-鿿　-〿＀-￯]")
_WS = re.compile(r"\s+")


def _normalize(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


def _spec() -> dict:
    return json.loads(SPEC.read_text(encoding="utf-8"))


def _operations(spec: dict) -> dict[tuple[str, str], tuple[str, dict]]:
    table: dict[tuple[str, str], tuple[str, dict]] = {}
    for path, item in spec["paths"].items():
        shared = item.get("parameters", [])
        for method, op in item.items():
            if method == "parameters":
                continue
            merged = dict(op)
            merged["parameters"] = shared + op.get("parameters", [])
            table[(method.upper(), _normalize(path))] = (path, merged)
    return table


def _resolve(spec: dict, schema: dict) -> dict:
    seen = 0
    while "$ref" in schema and seen < 10:
        schema = spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
        seen += 1
    if "allOf" in schema:
        merged: dict = {"properties": {}, "required": []}
        for part in schema["allOf"]:
            part = _resolve(spec, part)
            merged["properties"].update(part.get("properties", {}))
            merged["required"] += part.get("required", [])
        return merged
    return schema


def _english(text: str | None) -> str:
    """Prose in the export is English; a description written in Chinese is
    dropped here rather than shipped into the public tree."""
    if not text or _CJK.search(text):
        return ""
    return _WS.sub(" ", text).strip()


def _type(spec: dict, schema: dict) -> str:
    schema = _resolve(spec, schema)
    if "anyOf" in schema:
        parts = [_type(spec, s) for s in schema["anyOf"] if s.get("type") != "null"]
        parts = [p for p in parts if p]
        return " | ".join(dict.fromkeys(parts)) or "any"
    if "enum" in schema:
        return " | ".join(f"`{v}`" for v in schema["enum"])
    kind = schema.get("type", "object" if "properties" in schema else "any")
    if kind == "array":
        inner = schema.get("items", {})
        inner_r = _resolve(spec, inner)
        if "properties" in inner_r:
            return "array of objects (fields below)"
        return f"array of {_type(spec, inner)}"
    if kind == "string" and schema.get("format"):
        return schema["format"]
    limits = []
    if "maxLength" in schema:
        limits.append(f"≤{schema['maxLength']} chars")
    if "minimum" in schema:
        limits.append(f"≥{schema['minimum']}")
    if "maximum" in schema:
        limits.append(f"≤{schema['maximum']}")
    if "pattern" in schema:
        limits.append(f"pattern `{schema['pattern']}`")
    return kind + (f" ({', '.join(limits)})" if limits else "")


def _body_rows(spec: dict, schema: dict, indent: str = "") -> list[str]:
    schema = _resolve(spec, schema)
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    rows = []
    for name in sorted(props, key=lambda n: (n not in required, n)):
        prop = props[name]
        desc = _english(_resolve(spec, prop).get("description")) or _english(prop.get("description"))
        flag = "required" if name in required else "optional"
        rows.append(f"{indent}| `{name}` | {_type(spec, prop)} | {flag} | {desc} |")
        inner = _resolve(spec, prop)
        items = inner.get("items") if inner.get("type") == "array" else None
        if items and "properties" in _resolve(spec, items):
            rows.append(f"{indent}| ↳ each `{name}[]` item: | | | |")
            rows += _body_rows(spec, items, indent + "  ")
    return rows


# A skill that names a collection at all works its whole family: the record
# routes, the verbs, the lines. The old rule kept only "METHOD /path" lines,
# so `PATCH {"status": "confirmed"}` written without its path, or a
# collection named in prose, left the very write a flow skill exists for out
# of its contract (F-10) — while api-conventions.md told the agent "what is
# not in the contract does not exist".
COLLECTION = re.compile(r"(?<![\w/])(/[a-z][a-z0-9-]*)(?=[/?`\s)\]}.,;:]|$)")
# roots whose members are named one by one, never as a family
FAMILY_NEVER_WIDENED = frozenset({"auth", "admin", "enterprise-pilot-applications", "oauth", "device", "mcp", "tenant"})
# every skill resolves people, works todos and reads option vocabularies
UNIVERSAL = (
    ("GET", "/employees"), ("GET", "/employees/{}"), ("GET", "/todos"), ("GET", "/todos/{}"),
    ("PATCH", "/todos/{}"), ("GET", "/type-options"),
)


def render(skill_dir: Path, spec: dict, ops: dict) -> str | None:
    mentioned: set[tuple[str, str]] = set()
    roots: set[str] = set()
    for md in sorted(skill_dir.rglob("*.md")):
        if md.name == TARGET:
            continue
        if skill_dir.name == "oryh-help" and md.parent.name == "references" and md.name != "faq.md":
            # the help skill's references are the user manual mirrored; the
            # endpoints they mention are the product's, not this skill's calls
            continue
        text = md.read_text(encoding="utf-8")
        for method, path in REQUEST_LINE.findall(text):
            if not path.startswith("/api"):
                path = PREFIX + path
            mentioned.add((method, _normalize(path)))
        for match in COLLECTION.finditer(text):
            roots.add(match.group(1).strip("/"))
    if mentioned:
        # the family of every collection the skill names, plus the universal calls
        roots.update(path[len(PREFIX):].split("/")[1] for _m, path in mentioned if path.startswith(PREFIX + "/"))
        # identity and platform routes are not a family a skill "works": a
        # skill that names /auth/me must not inherit /auth/register, which
        # only the SaaS assembly serves — the open-core contract would name
        # an endpoint the open-core API does not have
        roots -= FAMILY_NEVER_WIDENED
        # a skill that quotes no write anywhere is a read-only skill: naming a
        # collection hands it the reads of the family, never the writes
        writes = any(m != "GET" for m, _p in mentioned)
        for method, path in ops:
            if path.startswith(PREFIX + "/") and path[len(PREFIX):].split("/")[1] in roots:
                if writes or method == "GET":
                    mentioned.add((method, path))
        mentioned.update((m, PREFIX + p) for m, p in UNIVERSAL if (m, PREFIX + p) in ops and (writes or m == "GET"))
    found = sorted(k for k in mentioned if k in ops)
    if not found:
        return None
    lines = [HEADER.rstrip("\n"), "", f"# {skill_dir.name}: API contract", "",
             "Every endpoint this skill names, with the parameters the server actually",
             "accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and",
             "lists page with `page`/`size` (see the conventions in this skill).", ""]
    for method, npath in found:
        path, op = ops[(method, npath)]
        shown = path[len(PREFIX):] if path.startswith(PREFIX) else path
        lines.append(f"## {method} {shown}")
        summary = _english(op.get("summary"))
        if summary:
            lines.append("")
            lines.append(summary)
        params = [p for p in op["parameters"] if p.get("in") in ("query", "path") and p["name"] != "X-API-Key"]
        if params:
            lines += ["", "| parameter | in | type | required | notes |", "|---|---|---|---|---|"]
            for p in params:
                note = _english(p.get("description"))
                if "clamped to 200" in note:
                    note = "paging — see the conventions in this skill"
                lines.append(
                    f"| `{p['name']}` | {p['in']} | {_type(spec, p.get('schema', {}))} | "
                    f"{'yes' if p.get('required') else 'no'} | {note} |"
                )
        body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
        if body:
            lines += ["", "Body:", "", "| field | type | | notes |", "|---|---|---|---|"]
            lines += _body_rows(spec, body)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def expected() -> dict[Path, str]:
    spec = _spec()
    ops = _operations(spec)
    out: dict[Path, str] = {}
    for skill_dir in sorted(p for p in SKILLS.iterdir() if p.is_dir() and not p.name.startswith("_")):
        if skill_dir.name == "oryh-help":
            # its references directory is the user manual mirrored, pinned as
            # such; the few live-fact calls it makes are documented in prose
            continue
        text = render(skill_dir, spec, ops)
        if text is not None:
            out[skill_dir / "references" / TARGET] = text
    return out


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for path, text in expected().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        stale.append(path)
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    if check and stale:
        for path in stale:
            print(f"out of date: {path.relative_to(ROOT)}")
        return 1
    print(f"{'stale' if check else 'wrote'} {len(stale)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
