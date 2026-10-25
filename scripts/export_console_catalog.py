#!/usr/bin/env python3
"""Export the console's data-browser catalogue from the API contract.

The console's generic data browser renders one page per collection: its
filters are the list endpoint's query parameters, its columns the row
model's scalar fields, its sort control the same `order_by` every list
accepts. None of that is hand-written in the frontend — it is read from
`app.openapi()` here, at build time, into a small JSON the page imports.
`tests/test_frontend_contract.py` pins the committed file to the API, the
way `frontend/openapi.json` is pinned.

Deterministic, no database.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app.main import app
from app.locales.zh_CN.console_catalog import GROUPS, RESOURCES, RELATED

PREFIX = "/api/v1"
SKIP_PARAMS = {"page", "size", "order_by"}

# Where a collection sits in the browser and what a person calls it. Paths
# not named here still appear, under "other", labelled from the path.





# A record's own sub-collections: the child collection and the filter that
# names the parent. The detail drawer links "lines", "adjustments", and the
# like straight into the browser, already filtered to this record.



def _deref(spec: dict, schema: dict | None) -> dict:
    while schema and "$ref" in schema:
        name = schema["$ref"].removeprefix("#/components/schemas/")
        schema = spec["components"]["schemas"].get(name, {})
    return schema or {}


def _scalar(spec: dict, schema: dict) -> dict | None:
    """type/format/enum of a schema, seeing through `anyOf: [X, null]`."""
    schema = _deref(spec, schema)
    if "anyOf" in schema:
        options = [_deref(spec, o) for o in schema["anyOf"] if _deref(spec, o).get("type") != "null"]
        if len(options) != 1:
            return None
        schema = options[0]
    kind = schema.get("type")
    if kind not in ("string", "integer", "number", "boolean"):
        return None
    out: dict = {"type": kind}
    if schema.get("format"):
        out["format"] = schema["format"]
    if schema.get("enum"):
        out["enum"] = [v for v in schema["enum"] if v is not None]
    return out


def _row_schema(spec: dict, get: dict) -> dict:
    body = get.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {})
    envelope = _deref(spec, body.get("schema"))
    data = _deref(spec, envelope.get("properties", {}).get("data"))
    if data.get("type") == "array":
        return _deref(spec, data.get("items"))
    return {}


def _humanize(path: str) -> str:
    return path.strip("/").replace("/", " ").replace("-", " ").capitalize()


def _body_fields(spec: dict, operation: dict) -> list[dict] | None:
    """The scalar fields of an operation's JSON request body, in schema
    order, with `required` — the console builds its form from these. None
    when the operation takes no body; [] when the body has no scalar field
    (a verb that takes nothing an admin types)."""
    fields, _unrenderable = _body_contract(spec, operation)
    return fields


def _body_contract(spec: dict, operation: dict) -> tuple[list[dict] | None, list[str]]:
    """The renderable fields, and the REQUIRED fields the console cannot
    render (objects, arrays). An operation with any of the latter cannot be
    submitted from the console's form: it used to be shown anyway and sent
    `{}` (review N04) — four visible verbs that were a guaranteed 422."""
    body = operation.get("requestBody")
    if not body:
        return None, []
    schema = _deref(spec, body.get("content", {}).get("application/json", {}).get("schema"))
    if not schema:
        return None, []
    required = set(schema.get("required", []))
    fields = []
    unrenderable = []
    for name, sub in schema.get("properties", {}).items():
        scalar = _scalar(spec, sub)
        if scalar is None:
            if name in required:
                unrenderable.append(name)
            continue
        raw = _deref(spec, sub)
        field = {"name": name, "required": name in required, **scalar}
        if raw.get("maxLength"):
            field["maxLength"] = raw["maxLength"]
        if raw.get("description"):
            field["description"] = raw["description"]
        fields.append(field)
    return fields, unrenderable


def _writes(spec: dict, short: str) -> dict:
    """What the API lets a person do to one collection: create (POST on the
    collection), update (PATCH on the record), remove (DELETE on the
    record), and the record's verbs — `POST /{collection}/{id}/<verb>`,
    exactly one segment deep, so `/products/{id}/skus/batch` is not one."""
    paths = spec["paths"]
    collection = PREFIX + short
    record = None
    for path in paths:
        if re.fullmatch(re.escape(collection) + r"/\{[^/}]+\}", path):
            record = path
            break
    out: dict = {}
    post = paths.get(collection, {}).get("post")
    if post:
        out["create"] = _body_fields(spec, post) or []
    if record:
        patch = paths[record].get("patch")
        if patch:
            out["update"] = _body_fields(spec, patch) or []
        if paths[record].get("delete"):
            out["remove"] = True
        actions = []
        # the record path's parameter NAME is not part of the match: a verb
        # written as `/{collection}/{object_id}/post-stock` beside a record
        # path of `/{collection}/{business_object_id}` is the same record
        # (review N04 — two ledger bridges were invisible for this)
        record_pattern = re.escape(collection) + r"/\{[^/}]+\}"
        for path, item in paths.items():
            match = re.fullmatch(record_pattern + r"/([a-z][a-z0-9-]*)", path)
            if not match or "post" not in item:
                continue
            verb = item["post"]
            fields, unrenderable = _body_contract(spec, verb)
            action = {
                "verb": match.group(1),
                "path": path,
                "summary": verb.get("summary") or match.group(1).replace("-", " ").capitalize(),
                "fields": fields or [],
            }
            if unrenderable:
                # shown as what it is: a verb an agent or the API drives,
                # not a form the console can fill in
                action["unsupported"] = unrenderable
            actions.append(action)
        actions.sort(key=lambda a: a["verb"])
        out["actions"] = actions
        out["recordPath"] = record
    return out


def _bilingual_catalog() -> dict:
    spec = app.openapi()
    resources = []
    for path, item in spec["paths"].items():
        get = item.get("get")
        if not get or not path.startswith(PREFIX) or "{" in path:
            continue  # a per-record sub-list is the record's, not a collection
        params = get.get("parameters", [])
        names = {p["name"] for p in params}
        if "size" not in names or "order_by" not in names:
            continue
        short = path.removeprefix(PREFIX)
        group, zh, en = RESOURCES.get(short, ("other", _humanize(short), _humanize(short)))
        filters = []
        for p in params:
            if p.get("in") != "query" or p["name"] in SKIP_PARAMS:
                continue
            scalar = _scalar(spec, p.get("schema", {})) or {"type": "string"}
            filters.append({
                "name": p["name"],
                "description": p.get("description") or "",
                **scalar,
            })
        columns = []
        for name, schema in _row_schema(spec, get).get("properties", {}).items():
            scalar = _scalar(spec, schema)
            if scalar is None:
                continue
            columns.append({"name": name, **scalar})
        resources.append({
            "key": re.sub(r"[^a-z0-9]+", "-", short.strip("/").lower()),
            "path": path,
            "group": group,
            "label": [zh, en],
            "filters": filters,
            "columns": columns,
            **_writes(spec, short),
            "related": [
                {"resource": re.sub(r"[^a-z0-9]+", "-", child.strip("/").lower()), "param": param, "label": [zh_, en_]}
                for child, param, zh_, en_ in RELATED.get(short, [])
                if PREFIX + child in spec["paths"]
                and param in {p["name"] for p in spec["paths"][PREFIX + child]["get"].get("parameters", [])}
            ],
        })
    resources.sort(key=lambda r: (list(GROUPS).index(r["group"]), r["label"][1]))
    return {
        "groups": [{"key": key, "label": list(label)} for key, label in GROUPS.items()],
        "resources": resources,
    }


def catalog_artifacts() -> tuple[dict, dict]:
    """Separate the English API-derived catalog from Chinese display labels.

    Label pairs remain the same shape for callers. Their first slot uses the
    English fallback in the base artifact; the console restores the original
    Chinese labels from the separately generated locale resource.
    """
    catalog = _bilingual_catalog()
    locale: dict = {"groups": {}, "resources": {}}
    for group in catalog["groups"]:
        locale["groups"][group["key"]] = group["label"][0]
        group["label"][0] = group["label"][1]
    for resource in catalog["resources"]:
        localized = {"label": resource["label"][0], "related": {}}
        locale["resources"][resource["key"]] = localized
        resource["label"][0] = resource["label"][1]
        for related in resource["related"]:
            key = f"{related['resource']}:{related['param']}"
            localized["related"][key] = related["label"][0]
            related["label"][0] = related["label"][1]
    return catalog, locale


def console_catalog() -> dict:
    """English API structure; localized labels live in a separate resource."""
    return catalog_artifacts()[0]


def console_catalog_labels() -> dict:
    """Chinese label overlay, keyed by stable resource and relationship IDs."""
    return catalog_artifacts()[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", type=Path, default=Path("frontend/src/api/data-catalog.json"))
    parser.add_argument("--locale-output", type=Path, help="Chinese label resource path")
    args = parser.parse_args()
    default_output = Path("frontend/src/api/data-catalog.json")
    locale_output = args.locale_output or (
        Path("frontend/src/locales/zh-CN/data-catalog.json")
        if args.output == default_output else args.output.with_name("data-catalog.zh-CN.json")
    )
    catalog, locale = catalog_artifacts()
    for output, value in ((args.output, catalog), (locale_output, locale)):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {output}")


if __name__ == "__main__":
    main()
