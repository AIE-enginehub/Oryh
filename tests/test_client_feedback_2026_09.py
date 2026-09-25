"""What the client team's first end-to-end round asked of the server
(oryh-ai-client docs/50, 2026-09-24), one test per change.

A count that says what the reader cannot list, a submit that refuses an
empty body, a todo that names its person by UUID, a gateway that answers
HTML to a JSON caller — none of these was wrong by any test that existed,
and each cost an agent a round trip or a wrong conclusion. This file is
where they become wrong.
"""
from __future__ import annotations

import base64
import hashlib
import re
import secrets
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.permissions import CAPABILITY_COLLECTIONS, SYSTEM_CAPABILITY_NAMES
from conftest import invite_member, make_client, provision_tenant

MEMBER = ["timesheet.submit_own", "expense.submit_own", "order.submit_own", "todos.complete_own"]


@contextmanager
def _office():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Feedback Co", email="admin@feedback.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def employee(name: str) -> str:
            return client.post("/api/v1/employees", json={"name": name}, headers=admin).json()["data"]["id"]

        yield client, admin, employee


def test_directory_counts_are_what_the_reader_may_list() -> None:
    """1.1 — a vendor account with warranty-card rights was told the company
    had eight sales orders. Counts follow the lists' visibility rule."""
    with _office() as (client, admin, employee):
        alice = invite_member(client, admin, "alice", MEMBER, employee_id=employee("Alice"))
        bob = invite_member(client, admin, "bob", MEMBER, employee_id=employee("Bob"))
        customer = client.post("/api/v1/customers", json={"name": "C"}, headers=admin).json()["data"]["id"]
        alice_emp = client.get("/api/v1/auth/me", headers=alice).json()["data"]["employee_id"]
        for _ in range(2):
            r = client.post("/api/v1/sales-orders", headers=alice, json={
                "employee_id": alice_emp, "customer_id": customer, "title": "alice's",
                "items": [{"product_name_snapshot": "x", "quantity": 1, "unit_price": 10}]})
            assert r.status_code == 201, r.text
        r = client.post("/api/v1/timesheet-headers", headers=alice, json={
            "employee_id": alice_emp, "period_start": "2026-09-14", "period_end": "2026-09-20"})
        assert r.status_code == 201, r.text

        def counts(who: dict) -> dict[str, int]:
            rows = client.get("/api/v1/object-directory", headers=who).json()["data"]
            return {row["object_type"]: row["count"] for row in rows}

        assert counts(admin)["sales_order"] == 2 and counts(admin)["timesheet_header"] == 1
        seen_by_bob = counts(bob)
        assert seen_by_bob["sales_order"] == 0 and seen_by_bob["timesheet_header"] == 0, \
            "the directory told Bob how many orders Alice filed"
        listed = client.get("/api/v1/sales-orders", headers=bob).json()
        assert listed["meta"]["total"] == seen_by_bob["sales_order"], "count and list disagree"


def test_auth_me_carries_a_permissions_fingerprint_that_moves_with_the_grant() -> None:
    """1.2 — a revoked read narrows lists without a word; the fingerprint is
    how a client knows to drop what it cached."""
    with _office() as (client, admin, employee):
        who = invite_member(client, admin, "reader", ["timesheet.submit_own", "timesheet.read_all"])
        before = client.get("/api/v1/auth/me", headers=who).json()["data"]
        assert re.fullmatch(r"[0-9a-f]{16}", before["permissions_fingerprint"])
        role = next(r for r in client.get("/api/v1/roles", headers=admin).json()["data"] if r["name"] == "reader")
        r = client.patch(f"/api/v1/roles/{role['id']}", headers=admin, json={"permissions": ["timesheet.submit_own"]})
        assert r.status_code == 200, r.text
        after = client.get("/api/v1/auth/me", headers=who).json()["data"]
        assert after["permissions_fingerprint"] != before["permissions_fingerprint"]
        again = client.get("/api/v1/auth/me", headers=who).json()["data"]
        assert again["permissions_fingerprint"] == after["permissions_fingerprint"], "stable while nothing moves"


def _rpc(client: TestClient, headers: dict, method: str, params: dict | None = None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers=headers)


def test_mcp_tools_say_whether_they_read_or_write() -> None:
    """1.3 — a host that treated `oryh_get` as a possible write dragged a
    person's screen to a sales order for asking a question."""
    with _office() as (client, admin, employee):
        bearer = {"Authorization": f"Bearer {admin['X-API-Key']}"}
        tools = {t["name"]: t for t in _rpc(client, bearer, "tools/list").json()["result"]["tools"]}
        for name in ("oryh_list", "oryh_get", "oryh_detail", "builtin_object_types", "object_directory", "setup_report"):
            assert tools[name]["annotations"]["readOnlyHint"] is True, name
            assert tools[name]["annotations"]["destructiveHint"] is False, name
        assert tools["oryh_request"]["annotations"] == {
            "readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False}
        assert tools["upload_attachment"]["annotations"]["readOnlyHint"] is False
        assert tools["upload_attachment"]["annotations"]["idempotentHint"] is True, "deduplicated by content"


def test_action_routes_take_no_body() -> None:
    """2.1 — two employees' first submit each failed with `body: Field
    required` for a schema whose every field is optional."""
    with _office() as (client, admin, employee):
        emp = employee("Filer")
        me = invite_member(client, admin, "filer", MEMBER, employee_id=emp)
        sheet = client.post("/api/v1/timesheet-headers", headers=me, json={
            "employee_id": emp, "period_start": "2026-09-14", "period_end": "2026-09-20",
            "entries": [{"work_date": "2026-09-15", "hours": 8}]}).json()["data"]["id"]
        bare = client.post(f"/api/v1/timesheet-headers/{sheet}/submit", headers=me)
        assert bare.status_code == 200, bare.text
        assert bare.json()["data"]["status"] == "submitted"
        claim = client.post("/api/v1/expense-claims", headers=me, json={
            "employee_id": emp, "title": "taxi", "items": [{"expense_date": "2026-09-10", "category": "travel", "amount": 20}]}
        ).json()["data"]["id"]
        assert client.post(f"/api/v1/expense-claims/{claim}/submit", headers=me).status_code == 200
        # and the contract says so: no action route requires a body whose fields are all optional
        spec = client.get("/openapi.json").json()
        for path, ops in spec["paths"].items():
            for method, op in ops.items():
                body = op.get("requestBody")
                if not body or not body.get("required") or method != "post":
                    continue
                ref = body["content"].get("application/json", {}).get("schema", {}).get("$ref")
                if not ref:
                    continue
                schema = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]
                verb = path.rsplit("/", 1)[-1]
                if verb in {"submit", "restore", "revise", "send", "publish", "repeal", "convert", "quote", "release"}:
                    assert schema.get("required"), f"{path} still demands a body with nothing required in it"


def test_documents_and_todos_name_their_person() -> None:
    """2.2 — an agent confirming who filed a timesheet spent three calls and
    111K tokens on a UUID. The name travels with the record, read live."""
    with _office() as (client, admin, employee):
        emp = employee("王小明")
        me = invite_member(client, admin, "ming", MEMBER, employee_id=emp)
        sheet = client.post("/api/v1/timesheet-headers", headers=me, json={
            "employee_id": emp, "period_start": "2026-09-14", "period_end": "2026-09-20"}).json()["data"]
        assert sheet["employee_name"] == "王小明", "the create's read-back names the person"
        assert client.get(f"/api/v1/timesheet-headers/{sheet['id']}", headers=me).json()["data"]["employee_name"] == "王小明"
        assert client.get("/api/v1/timesheet-headers", headers=me).json()["data"][0]["employee_name"] == "王小明"
        assert client.get(f"/api/v1/timesheet-headers/{sheet['id']}/detail", headers=me).json()["data"]["header"]["employee_name"] == "王小明"
        todo = client.post("/api/v1/todos", headers=admin, json={
            "employee_id": emp, "entity_type": "timesheet_header", "entity_id": sheet["id"], "title": "look"}).json()["data"]
        assert todo["employee_name"] == "王小明"
        assert client.get("/api/v1/todos", headers=me).json()["data"][0]["employee_name"] == "王小明"
        # a renamed person reads under the current name: nothing was stored
        assert client.patch(f"/api/v1/employees/{emp}", headers=admin, json={"name": "王明"}).status_code == 200
        assert client.get(f"/api/v1/todos/{todo['id']}", headers=me).json()["data"]["employee_name"] == "王明"
        claim = client.post("/api/v1/expense-claims", headers=me, json={"employee_id": emp, "title": "taxi"}).json()["data"]
        assert claim["employee_name"] == "王明"
        leave = client.post("/api/v1/employee-leaves", headers=admin, json={
            "employee_id": emp, "leave_type": "annual", "from_date": "2026-10-01", "thru_date": "2026-10-01", "duration_days": 1})
        assert leave.status_code == 201 and leave.json()["data"]["employee_name"] == "王明", leave.text
        request = client.post("/api/v1/purchase-requests", headers=admin, json={"employee_id": emp, "title": "pens"})
        assert request.status_code == 201 and request.json()["data"]["employee_name"] == "王明", request.text


def test_order_lines_carry_the_order_number_and_movements_their_product() -> None:
    """2.2 — a list of order lines showed the order as a UUID; the ledger
    showed positions as UUIDs. Numbers and names travel with the line."""
    with _office() as (client, admin, employee):
        customer = client.post("/api/v1/customers", json={"name": "C"}, headers=admin).json()["data"]["id"]
        product = client.post("/api/v1/products", json={"name": "Kettle", "product_code": "KT-1"}, headers=admin).json()["data"]["id"]
        created = client.post("/api/v1/sales-orders", headers=admin, json={
            "employee_id": employee("Seller"), "customer_id": customer, "title": "one kettle", "order_no": "SO-2026-0042",
            "items": [{"product_id": product, "quantity": 1, "unit_price": 10}]})
        assert created.status_code == 201, created.text
        order = created.json()["data"]
        assert order["items"][0]["order_no"] == "SO-2026-0042", "the create's read-back"
        line = order["items"][0]["id"]
        assert client.get(f"/api/v1/sales-order-items/{line}", headers=admin).json()["data"]["order_no"] == "SO-2026-0042"
        listed = client.get("/api/v1/sales-order-items", headers=admin, params={"order_id": order["id"]}).json()["data"]
        assert listed[0]["order_no"] == "SO-2026-0042"
        detail = client.get(f"/api/v1/sales-orders/{order['id']}/detail", headers=admin).json()["data"]
        assert detail["items"][0]["order_no"] == "SO-2026-0042"

        position = client.post("/api/v1/inventory-items", headers=admin, json={
            "product_id": product, "facility": "main", "initial_quantity": 5}).json()["data"]
        moves = client.get("/api/v1/inventory-item-details", headers=admin,
                           params={"inventory_item_id": position["id"]}).json()["data"]
        assert moves and all(m["product_id"] == product and m["product_name"] == "Kettle" for m in moves), moves


def test_the_capability_catalog_says_what_each_capability_governs() -> None:
    """2.3 — a console building its menu from permissions kept a hand-written
    table of capability → collection. Now it reads one, and every collection
    named is a real path."""
    with _office() as (client, admin, employee):
        assert set(CAPABILITY_COLLECTIONS) == set(SYSTEM_CAPABILITY_NAMES), "every system capability maps, even to nothing"
        spec = client.get("/openapi.json").json()
        listable = {p[len("/api/v1/"):] for p, ops in spec["paths"].items()
                    if re.fullmatch(r"/api/v1/[a-z][a-z0-9/-]*", p) and "get" in ops}
        for name, collections in CAPABILITY_COLLECTIONS.items():
            missing = set(collections) - listable
            assert not missing, f"{name} names collections that are not listable paths: {sorted(missing)}"
        catalog = client.get("/api/v1/capabilities", headers=admin).json()["data"]
        by_name = {c["name"]: c for c in catalog["capabilities"]}
        assert by_name["timesheet.submit_own"]["collections"] == ["timesheet-headers", "timesheet-entries"]
        assert by_name["timesheet.submit_own"]["title"], "the Chinese title was always there"
        assert by_name["business_object.write"]["collections"] == [] and by_name["business_object.write"]["scopable"]


def test_a_targeted_skill_with_no_audience_is_reported_not_skipped() -> None:
    """2.4 — the flow skills ship targeted; an admin holding the capability
    but not named to the skill saw it vanish from sync without a word."""
    with _office() as (client, admin, employee):
        r = client.post("/api/v1/skills", headers=admin, json={
            "name": "acme-flow", "title": "Acme flow", "description": "Use when acme flows.",
            "required_capability": "timesheet.advance", "distribution_mode": "targeted",
            "files": {"SKILL.md": "---\nname: acme-flow\n---\n\n# acme\n\nsteps\n"}})
        assert r.status_code == 201, r.text
        r = client.post("/api/v1/skills", headers=admin, json={
            "name": "acme-gated", "title": "Acme gated", "description": "Use when acme is gated.",
            "required_capability": "payroll.manage",
            "files": {"SKILL.md": "---\nname: acme-gated\n---\n\n# acme\n\nsteps\n"}})
        assert r.status_code == 201, r.text
        driver = invite_member(client, admin, "driver", ["timesheet.advance", "todos.complete_own"])
        manifest = client.get("/api/v1/my/skills/manifest", headers=driver).json()
        assert "acme-flow" not in {s["name"] for s in manifest["data"]}
        withheld = {w["name"]: w for w in manifest["meta"]["withheld"]}
        assert withheld["acme-flow"]["reasons"] == ["not_in_audience"], manifest["meta"]
        assert "acme-gated" not in withheld, "a skill the caller lacks the capability for is the reach endpoint's story"

        report = client.get("/api/v1/workspace/setup-report", headers=admin).json()["data"]["areas"]["flow_driving"]
        assert "acme-flow" in report["facts"]["targeted_skills_without_audience"]
        assert "acme-flow" in report["next"]
        driver_id = client.get("/api/v1/auth/me", headers=driver).json()["data"]["id"]
        assert client.post("/api/v1/skills/acme-flow/assignments", headers=admin,
                           json={"subject_type": "user", "subject_id": driver_id}).status_code in (200, 201)
        manifest = client.get("/api/v1/my/skills/manifest", headers=driver).json()
        assert "acme-flow" in {s["name"] for s in manifest["data"]}
        assert not [w for w in manifest["meta"]["withheld"] if w["name"] == "acme-flow"]
        report = client.get("/api/v1/workspace/setup-report", headers=admin).json()["data"]["areas"]["flow_driving"]
        assert "acme-flow" not in report["facts"]["targeted_skills_without_audience"]


def test_the_gateways_answer_json_when_the_api_is_away() -> None:
    """3.1 — an HTML 502 read as JSON told agents the tool was broken. Every
    nginx edge sends API and MCP upstream failures to one JSON answer."""
    root = Path(__file__).resolve().parents[1]
    # the open-core export renames nginx.standalone.conf to nginx.conf and ships that one alone
    shipped = [rel for rel in ("nginx/nginx.conf", "nginx/nginx.standalone.conf", "deploy/k8s/configmaps.yaml")
               if (root / rel).exists()]
    # every deployment environment's configmap too, where the tree carries them
    environments = sorted(str(p.relative_to(root)) for p in root.glob("ops/environments/*/k8s/configmaps.yaml"))
    for rel in shipped + environments:
        text = (root / rel).read_text()
        assert "location @api_unavailable {" in text, rel
        assert 'default_type application/json;' in text, rel
        assert '"detail":"oryh API is temporarily unavailable' in text, rel
        api_locations = [m.start() for m in re.finditer(r"location ~ \^/(?:\(\?:api/v1|mcp)", text)]
        assert api_locations, rel
        for start in api_locations:
            block = text[start:text.index("}", start)]
            assert "error_page 502 503 504 = @api_unavailable;" in block, f"{rel}: an API/MCP location without the error page"


def test_an_expired_consent_is_a_page_with_the_way_back() -> None:
    """3.2 — the person saw a raw JSON body and had to find their own way
    back to the client."""
    with make_client([]) as client:
        provision_tenant(client, company_name="OAuth Co", email="admin@oauth-co.example", password="admin-pass1")
        r = client.post("/web/login", data={"email": "admin@oauth-co.example", "password": "admin-pass1"}, follow_redirects=False)
        assert r.status_code == 303, r.text
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        params = {"response_type": "code", "client_id": "https://agent.example.com/client",
                  "redirect_uri": "http://127.0.0.1:53421/callback", "code_challenge": challenge,
                  "code_challenge_method": "S256", "state": "s1"}
        page = client.get("/oauth/authorize", params=params)
        consent = re.search(r'name="consent" value="([^"]+)"', page.text).group(1)
        ok = client.post("/oauth/authorize", data={**params, "decision": "approve", "consent": consent}, follow_redirects=False)
        assert ok.status_code == 303
        again = client.post("/oauth/authorize", data={**params, "decision": "approve", "consent": consent}, follow_redirects=False)
        assert again.status_code == 403
        assert again.headers["content-type"].startswith("text/html"), "a page, not a JSON body"
        assert "expired" in again.text and "agent.example.com" in again.text
        assert 'href="/oauth/authorize?' in again.text, "the way to open the authorization again"
        assert "error=access_denied" in again.text and "state=s1" in again.text, "the way back to the client"
