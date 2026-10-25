"""Unknown query parameters are refused on reads. `GET /products?product_code=X`
used to answer with the unfiltered list (FastAPI ignores undeclared query
parameters) and an agent took the first row as the product it asked for."""

from __future__ import annotations

from json import loads as _load_locale_json
from pathlib import Path as _LocalePath

# Exact multilingual fixtures; keep formatting and decisions at call sites.
_ZH_TEXT = _load_locale_json((_LocalePath(__file__).resolve().parent / 'locales/zh-CN/test_query_guard.json').read_text(encoding="utf-8"))


from conftest import make_client, provision_tenant


def test_a_list_refuses_a_filter_it_does_not_have_and_names_the_ones_it_does() -> None:
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Guard Co", email="admin@guard-co.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        for code, name in (("P-1", _ZH_TEXT['TEXT_33E3580C093111E1']), ("P-2", _ZH_TEXT['TEXT_71530D4C49F12C48'])):
            created = client.post("/api/v1/products", json={"product_code": code, "name": name}, headers=admin)
            assert created.status_code in (200, 201), created.text

        refused = client.get("/api/v1/products", params={"product_code": "P-2"}, headers=admin)
        assert refused.status_code == 422, refused.text
        [error] = refused.json()["detail"]
        assert error["type"] == "extra_forbidden" and error["loc"] == ["query", "product_code"]
        assert "keyword" in error["msg"] and "page" in error["msg"], "the refusal names the parameters that do exist"

        found = client.get("/api/v1/products", params={"keyword": "P-2"}, headers=admin)
        assert found.status_code == 200 and [row["product_code"] for row in found.json()["data"]] == ["P-2"]

        # declared parameters, aliases and generated range filters still pass
        assert client.get("/api/v1/products", params={"status": "active", "created_at_from": "2020-01-01T00:00:00", "page": 1, "size": 5}, headers=admin).status_code == 200


def test_writes_and_non_api_routes_are_not_checked_by_the_query_guard() -> None:
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Guard Two", email="admin@guard-two.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        created = client.post("/api/v1/customers", params={"utm": "x"}, json={"name": _ZH_TEXT['TEXT_85DED9E803B8D55E']}, headers=admin)
        assert created.status_code in (200, 201), created.text
        assert client.get("/", params={"utm": "x"}, follow_redirects=False).status_code != 422


def test_mcp_request_surfaces_the_refusal_as_a_tool_error() -> None:
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Guard MCP", email="admin@guard-mcp.example")
        bearer = {"Authorization": f"Bearer {t['plain_text_api_key']}"}

        def call(name: str, arguments: dict) -> dict:
            body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
            return client.post("/mcp", json=body, headers=bearer).json()["result"]

        refused = call("oryh_request", {"method": "GET", "path": "/products", "query": {"product_code": "P-1"}})
        assert refused["isError"] and "product_code" in refused["content"][0]["text"]
        listed = call("oryh_list", {"collection": "products", "filters": {"keyword": "P-1", "size": 5}})
        assert not listed.get("isError"), listed
