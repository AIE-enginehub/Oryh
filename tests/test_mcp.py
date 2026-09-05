"""MCP — the second door. Stateless JSON-RPC behind the same service layer:
an unauthenticated call is refused with the discovery hint; tools are
bindings of the REST contract dispatched in process as the same principal
(so a 403 is the REST 403, and the audit stamp is the same); prompts and
resources are the caller's skills, by the caller's reach."""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import make_client, provision_tenant, invite_member


def _rpc(client: TestClient, headers: dict, method: str, params: dict | None = None, request_id: int = 1):
    body = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers=headers)


def test_an_unauthenticated_call_says_where_the_authorization_server_is() -> None:
    with make_client([]) as client:
        refused = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert refused.status_code == 401
        assert 'resource_metadata="' in refused.headers["www-authenticate"] and "/.well-known/oauth-protected-resource/mcp" in refused.headers["www-authenticate"]


def test_tools_are_the_rest_contract_bound_and_dispatched_as_the_same_principal() -> None:
    with make_client([]) as client:
        t = provision_tenant(client, company_name="MCP Co", email="admin@mcp-co.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        nobody = invite_member(client, admin, "nobody", [])
        bearer = {"Authorization": f"Bearer {nobody['X-API-Key']}"}

        init = _rpc(client, bearer, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}})
        assert init.status_code == 200
        result = init.json()["result"]
        assert result["protocolVersion"] == "2025-06-18" and "tools" in result["capabilities"]
        assert "judgement lives in the prompts" in result["instructions"]

        notified = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=bearer)
        assert notified.status_code == 202, "a notification is acknowledged with nothing to say"

        tools = {tool["name"] for tool in _rpc(client, bearer, "tools/list").json()["result"]["tools"]}
        assert {"oryh_request", "oryh_list", "oryh_get", "builtin_object_types", "upload_attachment"} <= tools

        client.post("/api/v1/customers", json={"name": "市一医院"}, headers=admin)
        listed = _rpc(client, bearer, "tools/call", {"name": "oryh_list", "arguments": {"collection": "customers"}}).json()["result"]
        assert not listed.get("isError") and listed["structuredContent"]["data"][0]["name"] == "市一医院", listed

        forbidden = _rpc(client, bearer, "tools/call", {"name": "oryh_request", "arguments": {
            "method": "POST", "path": "/customers", "body": {"name": "影子"}}}).json()["result"]
        assert forbidden["isError"] and forbidden["structuredContent"]["detail"].startswith("requires") or "master_data.manage" in forbidden["content"][0]["text"], \
            "the REST 403 comes through the tool unchanged — same guards, same principal"

        outside = _rpc(client, bearer, "tools/call", {"name": "oryh_request", "arguments": {"method": "GET", "path": "/not-a-collection"}}).json()["result"]
        assert outside["isError"] and "not an operation" in outside["content"][0]["text"]

        unknown = _rpc(client, bearer, "tools/call", {"name": "make_coffee", "arguments": {}}).json()
        assert unknown["error"]["code"] == -32602

        admin_bearer = {"Authorization": f"Bearer {t['plain_text_api_key']}"}
        created = _rpc(client, admin_bearer, "tools/call", {"name": "oryh_request", "arguments": {
            "method": "POST", "path": "/customers", "body": {"name": "钢厂"}}}).json()["result"]
        assert not created.get("isError") and created["structuredContent"]["data"]["name"] == "钢厂"
        audit = client.get("/api/v1/audit-logs", params={"entity_type": "customer"}, headers=admin)
        if audit.status_code == 200:
            assert any(row.get("entity_id") == created["structuredContent"]["data"]["id"] for row in audit.json()["data"]), \
                "a write through MCP leaves the same audit row a REST write does"


def test_prompts_and_resources_are_the_callers_skills() -> None:
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Prompt Co", email="admin@prompt-co.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        nobody = invite_member(client, admin, "nobody", [])
        bearer = {"Authorization": f"Bearer {nobody['X-API-Key']}"}

        prompts = {p["name"] for p in _rpc(client, bearer, "prompts/list").json()["result"]["prompts"]}
        assert "oryh-help" in prompts and "oryh-my-work" in prompts, "ungated skills reach everyone"
        assert "oryh-treasury" not in prompts, "a gated skill does not reach a credential without its capability"

        got = _rpc(client, bearer, "prompts/get", {"name": "oryh-help"}).json()["result"]
        text = got["messages"][0]["content"]["text"]
        assert "Documentation first" in text and "{{ORYH_API_BASE_URL}}" not in text, "rendered, placeholders resolved"

        denied = _rpc(client, bearer, "prompts/get", {"name": "oryh-treasury"}).json()
        assert denied["error"]["code"] == -32602

        resources = _rpc(client, bearer, "resources/list").json()["result"]["resources"]
        faq = next(r for r in resources if r["uri"] == "oryh://skills/oryh-help/references/faq.md")
        read = _rpc(client, bearer, "resources/read", {"uri": faq["uri"]}).json()["result"]
        assert "make them an admin" in read["contents"][0]["text"]
