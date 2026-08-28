"""Pin the hand-written skill corpus to the real API.

Skills document endpoints as prose cheat sheets (`references/api.md`); nothing
in the type system ties that prose to the FastAPI routes. These tests are that
tie: an endpoint rename, a dropped query param, or a request-field change must
fail here instead of shipping stale instructions to every tenant's agents.

No DB and no client fixture — everything checks static corpus text against
`app.openapi()`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.main import app
from app.services.provisioning import PRODUCT_SKILLS_DIR, read_skill_dir

DEMO_SKILLS_DIR = PRODUCT_SKILLS_DIR.parent / "demo" / "skills"

# `GET /vendors?tax_id={销售方税号}` — method, path, optional query string.
REQUEST_LINE = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9_\-/{}.]+)(\?[^\s`）)]*)?"
)

SPEC = app.openapi()


def _normalize(path: str) -> str:
    """Docs and routes name path params differently; compare on shape."""
    return re.sub(r"\{[^}]*\}", "{}", path)


def _operations() -> dict[str, dict[str, dict]]:
    """Normalized path → {method: operation}, with path-level parameters
    folded into each operation so query-param checks see both layers."""
    table: dict[str, dict[str, dict]] = {}
    for path, item in SPEC["paths"].items():
        shared = item.get("parameters", [])
        for method, op in item.items():
            if method == "parameters":
                continue
            merged = dict(op)
            merged["parameters"] = shared + op.get("parameters", [])
            table.setdefault(_normalize(path), {})[method.upper()] = merged
    return table


OPERATIONS = _operations()


def _corpus() -> list[Path]:
    files = sorted(PRODUCT_SKILLS_DIR.rglob("*.md"))
    if DEMO_SKILLS_DIR.is_dir():
        files += sorted(DEMO_SKILLS_DIR.rglob("*.md"))
    return files


def _documented_requests() -> list[tuple[Path, str, str, str]]:
    """(file, method, normalized path, query string) for every request line
    in the corpus. Paths written without a prefix are `/api/v1` calls."""
    found = []
    for md in _corpus():
        for method, path, query in REQUEST_LINE.findall(md.read_text(encoding="utf-8")):
            if not path.startswith("/api"):
                path = "/api/v1" + path
            found.append((md, method, _normalize(path), query or ""))
    return found


def test_corpus_was_found() -> None:
    """Guard the other tests against silently checking nothing."""
    assert len(_documented_requests()) > 50


def test_documented_endpoints_exist() -> None:
    missing = {
        f"{md.relative_to(PRODUCT_SKILLS_DIR.parent)}: {method} {path}"
        for md, method, path, _ in _documented_requests()
        if method not in OPERATIONS.get(path, {})
    }
    assert not missing, "skill docs reference endpoints the API does not serve:\n" + "\n".join(
        sorted(missing)
    )


# Every document family's own write surface, and the skill that is supposed to
# teach it. The header PATCH is the one an agent needs to fix a title/date it
# got wrong before submitting — four families shipped without documenting it.
DOCUMENT_WRITE_SURFACE: tuple[tuple[str, str], ...] = (
    ("oryh-timesheet-submit", "/api/v1/timesheet-headers/{header_id}"),
    ("oryh-expense-submit", "/api/v1/expense-claims/{claim_id}"),
    ("oryh-purchase-submit", "/api/v1/purchase-requests/{request_id}"),
    ("oryh-quotation-submit", "/api/v1/sales-quotations/{quotation_id}"),
    ("oryh-order-submit", "/api/v1/sales-orders/{order_id}"),
    ("oryh-purchase-order", "/api/v1/purchase-orders/{po_id}"),
)


def test_each_submit_skill_documents_correcting_its_own_header() -> None:
    """The reverse pin: an endpoint the family depends on must be documented.

    test_documented_endpoints_exist guards one direction — docs must not name
    endpoints the API lacks. Nothing guarded the other: an endpoint the API
    serves and the skill needs can go undocumented, and the agent then has no
    way to do the thing. Found in the multi-agent e2e run, where an agent
    could not correct a claim header it had just filled in.
    """
    missing = []
    for skill, path in DOCUMENT_WRITE_SURFACE:
        skill_dir = PRODUCT_SKILLS_DIR / skill
        if not skill_dir.is_dir():
            continue
        assert "PATCH" in OPERATIONS.get(_normalize(path), {}), f"{path} lost its PATCH"
        corpus = "\n".join(p.read_text(encoding="utf-8") for p in skill_dir.rglob("*.md"))
        documented = any(
            method == "PATCH" and doc_path == _normalize(path)
            for _md, method, doc_path, _q in _documented_requests()
            if _md.is_relative_to(skill_dir)
        )
        if not documented:
            missing.append(f"{skill} never documents PATCH {path} — an agent cannot fix a wrong header")
    assert not missing, "\n".join(missing)


def test_documented_query_params_exist() -> None:
    complaints = set()
    for md, method, path, query in _documented_requests():
        op = OPERATIONS.get(path, {}).get(method)
        if op is None or not query:
            continue
        declared = {p["name"] for p in op["parameters"] if p.get("in") == "query"}
        for pair in query.lstrip("?").split("&"):
            name = pair.split("=", 1)[0]
            if name in {"", "...", "…"}:  # `?...` abbreviates "and so on"
                continue
            if name not in declared:
                complaints.add(
                    f"{md.relative_to(PRODUCT_SKILLS_DIR.parent)}: "
                    f"{method} {path} has no query param `{name}`"
                )
    assert not complaints, "\n".join(sorted(complaints))


def _resolve(schema: dict) -> dict:
    while "$ref" in schema:
        schema = SPEC["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    if "allOf" in schema:
        merged: dict = {"properties": {}}
        for part in schema["allOf"]:
            merged["properties"].update(_resolve(part).get("properties", {}))
        return merged
    return schema


def _property_enum(prop: dict) -> list | None:
    prop = _resolve(prop)
    if "enum" in prop:
        return prop["enum"]
    # Optional[Literal[...]] arrives as anyOf[{enum}, {null}].
    subs = [_resolve(s) for s in prop.get("anyOf", []) if s.get("type") != "null"]
    enums = [s["enum"] for s in subs if "enum" in s]
    return enums[0] if len(enums) == 1 else None


# ```json fences whose first line is a request line are executable examples;
# fences opening straight into `{` (responses) and ```jsonc row-shape sketches
# are not. An example abbreviated with `...`/`…` opts out of body validation.
EXAMPLE_BLOCK = re.compile(
    r"```json\n(GET|POST|PUT|PATCH|DELETE)\s+(\S+)\n(.*?)```", re.DOTALL
)


def test_documented_json_examples_match_request_schema() -> None:
    complaints = []
    for md in _corpus():
        for method, raw_path, body in EXAMPLE_BLOCK.findall(md.read_text(encoding="utf-8")):
            where = f"{md.relative_to(PRODUCT_SKILLS_DIR.parent)}: {method} {raw_path}"
            path = raw_path.split("?")[0]
            if not path.startswith("/api"):
                path = "/api/v1" + path
            op = OPERATIONS.get(_normalize(path), {}).get(method)
            if op is None:
                continue  # test_documented_endpoints_exist already flags it
            if "..." in body or "…" in body:
                continue
            try:
                # Examples annotate fields with ` // …` tails; the space-fenced
                # form never matches `//` inside a URL string value.
                example = json.loads(re.sub(r"\s+//\s.*$", "", body, flags=re.MULTILINE))
            except json.JSONDecodeError as error:
                complaints.append(f"{where}: example is not valid JSON ({error})")
                continue
            content = (op.get("requestBody") or {}).get("content", {})
            schema = content.get("application/json", {}).get("schema")
            if schema is None or not isinstance(example, dict):
                continue
            properties = _resolve(schema).get("properties", {})
            if not properties:
                continue  # free-form body; nothing to hold the example to
            unknown = set(example) - set(properties)
            if unknown:
                complaints.append(f"{where}: fields not in request schema: {sorted(unknown)}")
            for key, value in example.items():
                enum = key in properties and _property_enum(properties[key])
                if enum and isinstance(value, str) and value not in enum:
                    complaints.append(f"{where}: `{key}: {value}` not in enum {enum}")
    assert not complaints, "\n".join(sorted(complaints))


def test_demo_skill_payload_examples_satisfy_their_object_schema() -> None:
    """A tenant skill must teach the field names its own type definition
    enforces.

    `jc-warranty-card-apply` documented `customer_name` while the definition
    required `customer`, so every service provider's agent ate a 422 on its
    first write and had to self-correct. OpenAPI cannot catch this: the schema
    is tenant data, not part of the API surface.
    """
    import sys

    # The presence check comes FIRST: the demo dataset and the seed script that
    # declares its schemas travel together, so a tree without the skills has no
    # `scripts.seed_demo` to import either.
    jc_skills = DEMO_SKILLS_DIR / "jc-medical"
    if not jc_skills.is_dir():
        pytest.skip("demo skills not present")

    sys.path.insert(0, str(PRODUCT_SKILLS_DIR.parent))
    from scripts.seed_demo import JC_OBJECT_SCHEMAS

    complaints = []
    for md in sorted(jc_skills.rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        for method, raw_path, body in EXAMPLE_BLOCK.findall(text):
            if method != "POST" or "business-objects" not in raw_path or "..." in body or "…" in body:
                continue
            try:
                example = json.loads(re.sub(r"\s+//\s.*$", "", body, flags=re.MULTILINE))
            except json.JSONDecodeError:
                continue  # test_documented_json_examples_match_request_schema reports it
            schema = JC_OBJECT_SCHEMAS.get(example.get("object_type"))
            if schema is None or not isinstance(example.get("payload"), dict):
                continue
            where = f"{md.relative_to(DEMO_SKILLS_DIR)}: {example['object_type']}"
            missing = [k for k in schema["required"] if k not in example["payload"]]
            if missing:
                complaints.append(f"{where}: example omits required payload field(s) {missing}")
            unknown = [
                k for k in example["payload"]
                if k not in schema["properties"] and k not in {"customer_type", "purchase_date",
                                                               "submitted_service_provider"}
            ]
            if unknown:
                complaints.append(f"{where}: example writes field(s) the schema never declares: {sorted(unknown)}")
    assert not complaints, "\n".join(complaints)


def test_skill_author_states_workflow_definition_amend_semantics() -> None:
    """`POST /workflow-definitions` is publish-only — no `PATCH` — and every
    call replaces the whole document; the previous version is superseded, not
    merged into. An agent that doesn't know this, asked to "加一条" (add one
    clause), will happily draft prose for just the new clause and publish it —
    silently deleting every other submission requirement and routing rule the
    tenant had. Pins the guidance in place so a future edit can't trim it away.
    """
    text = (PRODUCT_SKILLS_DIR / "oryh-skill-author" / "SKILL.md").read_text(encoding="utf-8")
    assert "publish-only" in text and "no `PATCH`" in text, (
        "must state that publishing a workflow definition replaces the whole "
        "document rather than patching it"
    )
    assert "Default behavior is amend, not rewrite" in text, (
        "must default to merging the request into the current text, not "
        "drafting from scratch"
    )
    assert "what would be removed" in text, (
        "the read-back must surface anything the new version would silently drop"
    )


def test_no_unexpanded_include_markers_reach_the_registry() -> None:
    """`{{include:…}}` is a seed-time construct; a typo'd marker would ship
    literally to agents. Whatever read_skill_dir returns is what tenants get."""
    for skill_dir in sorted(PRODUCT_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
            continue
        for name, content in read_skill_dir(skill_dir).items():
            assert not re.search(r"\{\{\s*include", content), f"{skill_dir.name}/{name}"


def _skill_tree(tmp_path: Path, fragments: dict[str, str], skill_files: dict[str, str]) -> Path:
    common = tmp_path / "_common"
    common.mkdir()
    for name, text in fragments.items():
        target = common / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    skill = tmp_path / "some-skill"
    skill.mkdir()
    for name, text in skill_files.items():
        target = skill / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return skill


def test_include_expands_verbatim_in_place(tmp_path: Path) -> None:
    skill = _skill_tree(
        tmp_path,
        {"auth.md": "Use with:\n\n- header\n"},
        {"SKILL.md": "---\nname: s\n---\n", "references/api.md": "# API\n\n{{include:_common/auth.md}}\n\ntail\n"},
    )
    files = read_skill_dir(skill)
    assert files["references/api.md"] == "# API\n\nUse with:\n\n- header\n\ntail\n"


def test_include_marker_must_stand_alone(tmp_path: Path) -> None:
    skill = _skill_tree(
        tmp_path,
        {"auth.md": "x\n"},
        {"SKILL.md": "see {{include:_common/auth.md}} inline\n"},
    )
    # Not alone on its line → not a marker; the corpus test that forbids
    # `{{include` in registry output is what turns this into a hard failure.
    assert "{{include:" in read_skill_dir(skill)["SKILL.md"]


def test_include_missing_fragment_raises(tmp_path: Path) -> None:
    skill = _skill_tree(tmp_path, {}, {"SKILL.md": "{{include:_common/nope.md}}\n"})
    with pytest.raises(ValueError, match="missing include fragment"):
        read_skill_dir(skill)


def test_include_rejects_nesting(tmp_path: Path) -> None:
    skill = _skill_tree(
        tmp_path,
        {"a.md": "{{include:_common/b.md}}\n", "b.md": "x\n"},
        {"SKILL.md": "{{include:_common/a.md}}\n"},
    )
    with pytest.raises(ValueError, match="must not include further"):
        read_skill_dir(skill)


def test_include_rejects_path_traversal(tmp_path: Path) -> None:
    (tmp_path / "secret.md").write_text("leak\n", encoding="utf-8")
    skill = _skill_tree(tmp_path, {}, {"SKILL.md": "{{include:_common/../secret.md}}\n"})
    with pytest.raises(ValueError, match="escapes _common"):
        read_skill_dir(skill)


def test_bundled_scripts_compile() -> None:
    """Scripts ride files_jsonb as text; a syntax error would only surface on
    a user's machine. Compile exactly what the registry would store."""
    for skill_dir in sorted(PRODUCT_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
            continue
        for name, content in read_skill_dir(skill_dir).items():
            if name.endswith(".py"):
                compile(content, f"{skill_dir.name}/{name}", "exec")


# `GET /roles → [{id, name, title, permissions, is_system}]` — the prose
# shorthand for "what comes back". Deliberately narrow: only bare identifiers
# separated by commas, so JSON examples (quotes, colons) and prose arrows
# (`→ status=archived`) never match.
RESPONSE_SHAPE = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9_\-/{}.]+)[^\n→]*→\s*\[?\{"
    r"([A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*)\}\]?"
)


def _response_fields(op: dict) -> set[str] | None:
    """Field names of one row of a 200 response, unwrapping the {data, meta}
    envelope and a list `data`. None when the shape is not introspectable."""
    content = ((op.get("responses") or {}).get("200") or {}).get("content", {})
    schema = content.get("application/json", {}).get("schema")
    if schema is None:
        return None
    resolved = _resolve(schema)
    data = resolved.get("properties", {}).get("data")
    if data is not None:
        resolved = _resolve(data)
        if resolved.get("type") == "array":
            resolved = _resolve(resolved.get("items", {}))
    properties = resolved.get("properties")
    return set(properties) if properties else None


def test_documented_response_fields_exist() -> None:
    """A doc naming a field the API does not return is worse than a stale
    endpoint: the endpoint 404s loudly, the field reads as null.

    `oryh-access-admin` documented `GET /roles → [{…, permissions_jsonb, …}]`
    — the ORM column name, not the serialized one. An agent following it read
    None and, because `PATCH /roles/{role_ref}` replaces the whole array,
    could write that back as an empty permission set for the whole company.
    Endpoints and request bodies were already pinned; responses were not.
    """
    complaints = []
    for md in _corpus():
        for method, raw_path, fields in RESPONSE_SHAPE.findall(md.read_text(encoding="utf-8")):
            path = raw_path if raw_path.startswith("/api") else "/api/v1" + raw_path
            op = OPERATIONS.get(_normalize(path), {}).get(method)
            if op is None:
                continue  # test_documented_endpoints_exist already flags it
            actual = _response_fields(op)
            if actual is None:
                continue  # untyped or streaming response; nothing to hold it to
            unknown = {f.strip() for f in fields.split(",")} - actual
            if unknown:
                where = f"{md.relative_to(PRODUCT_SKILLS_DIR.parent)}: {method} {raw_path}"
                complaints.append(f"{where}: fields not in response: {sorted(unknown)}")
    assert not complaints, "\n".join(sorted(complaints))


SCRIPT_REFERENCE = re.compile(r"(?<![\w/.])(scripts/[A-Za-z0-9_./-]+\.(?:py|sh|mjs|js))")


def _skill_directories() -> list[Path]:
    roots = [
        path
        for path in PRODUCT_SKILLS_DIR.iterdir()
        if path.is_dir() and path.name != "_common"
    ]
    if DEMO_SKILLS_DIR.is_dir():
        roots += [
            skill
            for tenant in DEMO_SKILLS_DIR.iterdir()
            if tenant.is_dir()
            for skill in tenant.iterdir()
            if skill.is_dir()
        ]
    return sorted(roots)


def test_every_script_a_skill_names_ships_inside_it() -> None:
    """A tool path in a SKILL is a promise that the bundle keeps it.

    An agent filing an expense called `scripts/upload_attachment.py`, got a
    file-not-found, and fell back to reading the API by hand. The bundle
    carries every file in the skill directory, so the promise is cheap to
    keep — and cheaper still to check, since the alternative is finding out
    from an agent's error transcript.
    """
    missing = []
    checked = 0
    for skill in _skill_directories():
        for document in sorted(skill.rglob("*.md")):
            for reference in SCRIPT_REFERENCE.findall(document.read_text(encoding="utf-8")):
                checked += 1
                if not (skill / reference).is_file():
                    missing.append(
                        f"{document.relative_to(PRODUCT_SKILLS_DIR.parent)}: {reference}"
                    )
    assert checked > 5, f"only {checked} script references found — the scan is not reading the corpus"
    assert not missing, "skills name scripts their bundle does not carry:\n" + "\n".join(missing)


def test_a_document_that_names_a_script_says_where_to_run_it() -> None:
    """`scripts/x.py` is relative to the skill's own directory, and an agent
    whose working directory is the bundle root — or anywhere else — resolves
    it to nothing.

    One document said "in this skill's directory" and three said nothing,
    which is the whole difference between a tool that runs and a tool the
    agent decides is broken. The rule is per document, because an agent reads
    whichever one it opened.
    """
    unanchored = []
    for skill in _skill_directories():
        for document in sorted(skill.rglob("*.md")):
            text = document.read_text(encoding="utf-8")
            if not SCRIPT_REFERENCE.search(text):
                continue
            if "this skill's directory" not in text:
                unanchored.append(str(document.relative_to(PRODUCT_SKILLS_DIR.parent)))
    assert not unanchored, (
        "these name a script without saying the path is relative to the skill "
        "directory:\n" + "\n".join(unanchored)
    )


# --- cross references between skills ---------------------------------------
#
# `$oryh-approve` is how one skill hands work to another, and it is the only
# navigation an agent has: nothing resolves it at runtime, so a name that does
# not exist is a dead end the agent discovers mid-task, in front of a user.
#
# Four approval-flow skills deferred to `$oryh-timesheet-approve`,
# `$oryh-expense-approve`, `$oryh-purchase-approve` and `$oryh-quotation-approve`
# — a per-document-type approve family that has never existed. The authoring
# guide taught the same shape as `$oryh-*-approve`. Five documents agreeing
# with each other and none with the registry, found by the 2026-08-16
# architecture review rather than by anything mechanical.
#
# The glob form is captured deliberately: `$oryh-*-approve` was one of the five
# and reads as a real family. A pattern that names no skill is the same defect
# spelled with a wildcard.
SKILL_REFERENCE = re.compile(r"\$([a-z][a-z0-9*-]*[a-z0-9*])")

# References that are prose, not navigation. Each one needs a reason.
REFERENCE_EXEMPTIONS: dict[str, str] = {}


def _known_skill_names() -> set[str]:
    names = {path.name for path in PRODUCT_SKILLS_DIR.iterdir()
             if path.is_dir() and path.name != "_common"}
    if DEMO_SKILLS_DIR.is_dir():
        names |= {path.name for path in DEMO_SKILLS_DIR.glob("*/*") if path.is_dir()}
    return names


def test_every_skill_cross_reference_names_a_skill_that_exists() -> None:
    known = _known_skill_names()
    assert len(known) > 20, "skill registry did not load; the check below would pass vacuously"

    dangling: dict[str, list[str]] = {}
    for path in _corpus():
        for match in SKILL_REFERENCE.finditer(path.read_text(encoding="utf-8")):
            name = match.group(1)
            if name in known or name in REFERENCE_EXEMPTIONS:
                continue
            dangling.setdefault(name, []).append(str(path.relative_to(PRODUCT_SKILLS_DIR.parent)))

    assert dangling == {}, (
        f"{dangling} are handed to agents as skills to defer to, and no such skill exists. "
        "Point them at the real one, or add an entry to REFERENCE_EXEMPTIONS saying why "
        "this one is prose"
    )


def test_the_skills_that_get_referenced_the_most_are_real() -> None:
    """A guard on the guard. If `_known_skill_names` ever returned an empty or
    wrong-shaped set, the check above would pass with everything dangling —
    so pin a few names the corpus leans on hardest."""
    known = _known_skill_names()
    for name in ("oryh-approve", "oryh-my-work", "oryh-business-object"):
        assert name in known, f"{name} is referenced across the corpus but is not a skill directory"


# --- the connection contract, product and demo alike ------------------------


def test_every_skill_that_calls_the_api_states_where_the_api_is() -> None:
    """A skill documenting `GET /todos` and never naming the API base is a skill
    whose first call goes to the site root.

    `test_bundles.py` already checked that a stated `api_base_url` is complete —
    but it opens with `if "api_base_url:" not in rendered: continue`, so the
    skill that never states one at all is the single case it cannot see. Two
    product skills were in exactly that gap: `oryh-order-approval-flow`
    documented six API paths with no Required Inputs section of any kind, and
    `approval-notifier` had an inputs block about notification payloads and
    nothing about oryh.

    Product and demo skills are held to the one contract here, deliberately.
    The demo tenants are how the product is shown to people, and a demo skill
    on an older contract than the product teaches the older contract.
    """
    offenders = {}
    for path in _corpus():
        if path.name != "SKILL.md":
            continue
        text = path.read_text(encoding="utf-8")
        calls = REQUEST_LINE.findall(text)
        if calls and "api_base_url" not in text:
            offenders[str(path.relative_to(PRODUCT_SKILLS_DIR.parent))] = len(calls)

    assert offenders == {}, (
        f"{offenders} document API paths without stating `api_base_url`, so an agent "
        "following them verbatim sends its first request to the console"
    )


def test_the_attachment_fragment_ships_with_the_script_it_names() -> None:
    """The fragment tells the agent to prefer `scripts/upload_attachment.py`
    "in this skill's own directory". A skill that includes the fragment and
    does not carry the stub sends the agent looking for a file that is not
    there — and the fallback is hand-rolled base64 with no 10 MB pre-check,
    which fails at upload time on exactly the large scans that matter.

    The stub is one `{{include:_common/scripts/upload_attachment.py}}` line, so
    the cost of remembering is a line and the cost of forgetting is a broken
    instruction inside otherwise-correct prose.
    """
    fragment = "_common/attachment-evidence.md"
    including = [
        d for d in sorted(PRODUCT_SKILLS_DIR.iterdir())
        if (d / "SKILL.md").is_file() and fragment in (d / "SKILL.md").read_text(encoding="utf-8")
    ]
    assert including, "nothing includes the attachment fragment — has it been renamed?"
    missing = [d.name for d in including if not (d / "scripts" / "upload_attachment.py").is_file()]
    assert not missing, (
        f"these include {fragment} but ship no scripts/upload_attachment.py: {missing}"
    )


def test_every_money_skill_says_who_its_holder_is() -> None:
    """A real agent refused to pay an approved reimbursement because it had
    decided it was "the employee's agent" and payment "belonged to the payables
    role" — while holding `$oryh-payables` and every capability the route
    needed. Both halves of that sentence were about itself.

    `_common/who-you-are-acting-as.md` answers exactly that, and reached only
    the approval-flow skills: the desks that MOVE money had no copy. A skill
    that writes or settles money must carry it, because that is where a wrong
    self-image stops a real payment.
    """
    fragment = "_common/who-you-are-acting-as.md"
    MOVES_MONEY = (
        "oryh-payables", "oryh-receivables", "oryh-payroll",
        "oryh-billing-account", "oryh-approve",
    )
    missing = [
        name for name in MOVES_MONEY
        if (PRODUCT_SKILLS_DIR / name / "SKILL.md").is_file()
        and fragment not in (PRODUCT_SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    ]
    assert not missing, (
        f"these move money and never say whose desk they are: {missing} — "
        f"include {{{{include:{fragment}}}}}"
    )


def test_the_warehouse_doctrine_is_written_where_the_agent_reads() -> None:
    """The ledger ACCEPTS an undocumented movement — but the agent only records
    one if its instructions say to. The doctrine is the half that turns the
    mechanism into behaviour: record reality first, never fabricate a document,
    resolve later by counter-entry. A refactor that drops the section leaves
    the mechanism intact and the behaviour gone, which no API test can see.
    """
    body = (PRODUCT_SKILLS_DIR / "oryh-inventory" / "SKILL.md").read_text(encoding="utf-8")
    assert "## The Warehouse Records Reality, Not Paperwork" in body
    for sentence in (
        "never a\ndocument",
        "Never fabricate a document",
        "counter-entry",
    ):
        assert sentence in body, f"the doctrine lost: {sentence!r}"


def test_channel_order_translation_is_taught_where_each_agent_reads() -> None:
    """The server holds two mapping tables; the BEHAVIOUR — dedup by the
    platform's order number before creating, translate lines through the map
    instead of guessing, name a movement's external return by a link instead
    of a counter-entry — lives only in skill prose. Each desk gets its half:
    the seller dedups and translates, the catalog admin curates the map, the
    warehouse links returns. Losing any of these sections leaves the tables
    intact and the mess they exist to prevent back in place."""
    seller = (PRODUCT_SKILLS_DIR / "oryh-order-submit" / "SKILL.md").read_text(encoding="utf-8")
    assert "/external-document-links" in seller, "the seller lost the dedup check"
    assert "/external-product-maps" in seller, "the seller lost the line translation"
    assert "Dedup" in seller and "FIRST" in seller, \
        "dedup must be taught as the first step, not an aside"
    assert "at={the ORDER's date}" in seller, \
        "translation without the order's date mistranslates every back-dated " \
        "import after a listing swap — the `at` param is the whole point"

    curator = (PRODUCT_SKILLS_DIR / "oryh-master-data" / "SKILL.md").read_text(encoding="utf-8")
    assert "/external-product-maps" in curator, "the catalog admin lost map curation"
    assert "effective_to" in curator and "Never archive" in curator, \
        "the swap workflow (close the window, keep the row active) lives only " \
        "here — losing it turns every listing swap into a withdrawn history"

    keeper = (PRODUCT_SKILLS_DIR / "oryh-inventory" / "SKILL.md").read_text(encoding="utf-8")
    assert "/external-document-links" in keeper, \
        "the warehouse lost the link that names a frozen row later"


def test_returns_as_order_rows_are_taught_where_each_agent_reads() -> None:
    """The server holds the kind split; the BEHAVIOUR — a return is a row in
    the same collection naming its original, running its own e-commerce
    lifecycle, never charging credit — lives in skill prose. The seller
    records customer returns, procurement records vendor returns, the
    warehouse books the parcel against the return row. Losing any section
    leaves the columns intact and the agents recording returns as free-text
    remarks again."""
    seller = (PRODUCT_SKILLS_DIR / "oryh-order-submit" / "SKILL.md").read_text(encoding="utf-8")
    assert '"order_kind": "return"' in seller, "the seller lost the return-row shape"
    assert "original_order_id" in seller, "the seller lost the original-order linkage"
    assert "many returns" in seller, "one order, many returns is the requirement — say it"

    buyer = (PRODUCT_SKILLS_DIR / "oryh-purchase-order" / "SKILL.md").read_text(encoding="utf-8")
    assert "order_kind" in buyer and "original_order_id" in buyer, \
        "procurement lost the vendor-return shape"

    keeper = (PRODUCT_SKILLS_DIR / "oryh-inventory" / "SKILL.md").read_text(encoding="utf-8")
    assert "RETURN row" in keeper, \
        "the warehouse must know a return receipt names the return row"

    receivables = (PRODUCT_SKILLS_DIR / "oryh-receivables" / "SKILL.md").read_text(encoding="utf-8")
    assert "Refunding a Customer Return" in receivables and "settles no invoice" in receivables, \
        "the refund is the money half of every return and no other desk records " \
        "it — losing this section strands every return one step before refunded"
    payables = (PRODUCT_SKILLS_DIR / "oryh-payables" / "SKILL.md").read_text(encoding="utf-8")
    assert "Purchase Return" in payables and "inbound" in payables, \
        "the vendor's refund coming home is the payables desk's inbound exception"

    keeper_api = (PRODUCT_SKILLS_DIR / "oryh-inventory" / "SKILL.md").read_text(encoding="utf-8")
    assert "/post-stock" in keeper_api and "ONCE" in keeper_api, \
        "the once-only bridge is the rule that stops double-booked goods"
    assert "Never book the same goods twice" in keeper_api, \
        "/receive and shipments both reach the ledger — without this warning " \
        "the same parcel lands twice"
    assert "object_type=sales_return" in keeper_api and "original position" in keeper_api, \
        "where returned goods land is the tenant's sentence in the sales_return " \
        "definition, defaulting to the original position — losing this teaching " \
        "reopens the OFBiz fork as every keeper's private guess"

    flow_md = PRODUCT_SKILLS_DIR / "oryh-order-approval-flow" / "SKILL.md"
    if flow_md.is_file():  # *-approval-flow skills are PRIVATE_SKILLS, absent
        flow = flow_md.read_text(encoding="utf-8")  # from the open-core export
        assert "order_kind" in flow, \
            "the hosted queue serves returns too — a flow admin who cannot tell " \
            "the kinds apart writes order states onto returns and loops on 409s"
        assert "sales_return" in flow, \
            "the return decision reads the sales_return definition and machine"
