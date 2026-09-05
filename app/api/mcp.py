"""MCP — the second door.

One stateless JSON-RPC endpoint, `POST /mcp` (Streamable HTTP, no session,
no server-initiated stream), behind the same service layer as REST: the
bearer is the OAuth access token (an interactive api key) or an api key,
resolved by the same `get_actor`, so capabilities, RLS and the audit stamp
are exactly what a REST call would get. Tool calls are dispatched IN
PROCESS through the ASGI app, never re-implemented — a tool is a binding
of the REST contract, not a second API.

What stays out of tools: judgement. Skills — the reading before a write,
the read-back, the iron rules — are delivered as MCP prompts and their
reference files as resources, filtered by the caller's role exactly as a
bundle would be. An MCP client gets the same three layers a skills-only
agent gets: mechanics (tools), judgement (prompts), reference (resources).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import Actor, _authenticate
from app.api.oauth import issuer
from app.core.browser_auth import CSRF_COOKIE, SESSION_COOKIE
from app.core.request_context import resolved_api_base_url, resolved_base_url
from app.db.session import get_db
from app.models import Tenant, User
from app.services.bundles import (
    apply_brand,
    eligible_skills,
    service_permissions,
    tenant_slug,
)
from app.services.bundles import render_content

router = APIRouter(include_in_schema=False)

PROTOCOL_VERSIONS = ("2026-07-28", "2025-06-18", "2025-03-26")
SERVER_INFO = {"name": "oryh", "version": "1"}
INSTRUCTIONS = (
    "oryh is an AI-native ERP/CRM. Tools are the mechanics — the REST contract, "
    "bound. The judgement lives in the prompts: read the prompt (skill) for the "
    "desk you are working at BEFORE calling tools, follow its read-back and "
    "never-do rules, and take the reference resources when it points at them. "
    "Answer the person's question first and only what was asked."
)

READ = "GET"
API = "/api/v1"


def _mcp_actor(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Actor:
    """The REST authenticator, with RFC 9728's discovery hint on refusal so
    an MCP client can find the authorization server on its own."""
    try:
        return _authenticate(
            request, db,
            request.headers.get("x-api-key"),
            request.headers.get("authorization"),
            request.cookies.get(SESSION_COOKIE),
            request.cookies.get(CSRF_COOKIE),
            request.headers.get("x-csrf-token"),
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            raise HTTPException(
                status_code=401,
                detail=exc.detail,
                headers={
                    "WWW-Authenticate": (
                        f'Bearer resource_metadata="{issuer()}/.well-known/oauth-protected-resource/mcp"'
                    )
                },
            )
        raise


# --- the tool surface ---------------------------------------------------------


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": properties, "required": required},
    }


TOOLS: list[dict] = [
    _tool(
        "oryh_request",
        "Call any oryh REST operation exactly as the skills document it: method, path under /api/v1 "
        "(e.g. /customers, /sales-orders/{id}/submit), optional query and JSON body. The response is "
        "the API's own envelope; a 4xx is returned as an error with the API's detail — read it, it "
        "names the fix. Paths outside the OpenAPI contract are refused.",
        {
            "method": {"type": "string", "enum": ["GET", "POST", "PATCH", "PUT", "DELETE"]},
            "path": {"type": "string"},
            "query": {"type": "object", "additionalProperties": True},
            "body": {"type": "object", "additionalProperties": True},
        },
        ["method", "path"],
    ),
    _tool(
        "oryh_list",
        "List a collection with filters (status, keyword, ids, page/size) — the everyday answer: "
        "master-data lists return active rows unless status=all is passed.",
        {"collection": {"type": "string"}, "filters": {"type": "object", "additionalProperties": True}},
        ["collection"],
    ),
    _tool("oryh_get", "Read one record by id.", {"collection": {"type": "string"}, "id": {"type": "string"}}, ["collection", "id"]),
    _tool("oryh_detail", "Read a document's /detail — lines, derived totals, drift, execution.", {"collection": {"type": "string"}, "id": {"type": "string"}}, ["collection", "id"]),
    _tool("builtin_object_types", "What oryh ships — before ever proposing a custom object.", {}, []),
    _tool("object_directory", "Every object type this workspace has, builtin and custom, with counts.", {}, []),
    _tool("setup_report", "Where this workspace stands: derived from live data, stored nowhere.", {}, []),
    _tool(
        "upload_attachment",
        "Upload evidence (receipt, contract original, picture) — base64 bytes, 10 MB max, deduplicated by content; returns the attachment id to link from a document.",
        {"filename": {"type": "string"}, "content_type": {"type": "string"}, "content_base64": {"type": "string"}},
        ["filename", "content_type", "content_base64"],
    ),
]


@lru_cache(maxsize=1)
def _contract() -> list[tuple[str, re.Pattern[str]]]:
    """(METHOD, path regex) for every REST operation — the contract a tool
    call must match. Derived from the OpenAPI document, never listed."""
    from app.main import app

    operations = []
    for path, methods in app.openapi()["paths"].items():
        pattern = "^" + re.sub(r"\{[^}]+\}", r"[^/]+", re.escape(path).replace(r"\{", "{").replace(r"\}", "}")) + "$"
        for method in methods:
            if method.upper() in {"GET", "POST", "PATCH", "PUT", "DELETE"}:
                operations.append((method.upper(), re.compile(pattern)))
    return operations


def _in_contract(method: str, path: str) -> bool:
    return any(m == method and rx.match(path) for m, rx in _contract())


def _normalise_path(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    if not path.startswith(API + "/") and path != API:
        path = API + path
    return path


async def _dispatch(request: Request, method: str, path: str, query: dict | None, body: Any) -> dict:
    """Run the REST operation in process, as the same principal: the
    incoming credential headers travel with the call, so the audit stamp
    and every guard are the REST ones."""
    path = _normalise_path(path)
    if not _in_contract(method, path):
        return {"isError": True, "content": [{"type": "text", "text": f"{method} {path} is not an operation of the oryh API — see the skill's api reference"}]}
    headers = {}
    for name in ("authorization", "x-api-key", "cookie", "x-csrf-token"):
        if name in request.headers:
            headers[name] = request.headers[name]
    transport = httpx.ASGITransport(app=request.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://oryh.internal") as client:
        response = await client.request(method, path, params=query or None, json=body if body is not None else None, headers=headers)
    text = response.text
    try:
        structured = response.json() if text else None
    except ValueError:
        structured = None
    result: dict[str, Any] = {"content": [{"type": "text", "text": text or f"HTTP {response.status_code}"}]}
    if isinstance(structured, dict):
        result["structuredContent"] = structured
    if response.status_code >= 400:
        result["isError"] = True
    return result


async def _call_tool(request: Request, name: str, args: dict) -> dict:
    if name == "oryh_request":
        return await _dispatch(request, str(args.get("method", "GET")).upper(), str(args.get("path", "")), args.get("query"), args.get("body"))
    if name == "oryh_list":
        return await _dispatch(request, READ, f"/{str(args.get('collection', '')).strip('/')}", args.get("filters"), None)
    if name == "oryh_get":
        return await _dispatch(request, READ, f"/{str(args.get('collection', '')).strip('/')}/{args.get('id', '')}", None, None)
    if name == "oryh_detail":
        return await _dispatch(request, READ, f"/{str(args.get('collection', '')).strip('/')}/{args.get('id', '')}/detail", None, None)
    if name == "builtin_object_types":
        return await _dispatch(request, READ, "/builtin-object-types", None, None)
    if name == "object_directory":
        return await _dispatch(request, READ, "/object-directory", None, None)
    if name == "setup_report":
        return await _dispatch(request, READ, "/workspace/setup-report", None, None)
    if name == "upload_attachment":
        return await _dispatch(request, "POST", "/attachments", None, {
            "filename": args.get("filename"), "content_type": args.get("content_type"),
            "content_base64": args.get("content_base64"),
        })
    raise KeyError(name)


# --- prompts and resources: the skills, by the caller's reach ------------------


def _skills(db: Session, actor: Actor):
    permissions = service_permissions() if actor.kind == "service" else actor.permissions
    return eligible_skills(
        db, actor.tenant_id, permissions,
        user_id=actor.user_id, role=actor.role, ignore_audience=actor.kind == "service",
    )


def _render_context(db: Session, actor: Actor) -> dict[str, str]:
    tenant = db.get(Tenant, actor.tenant_id)
    user = db.get(User, actor.user_id) if actor.user_id else None
    return {
        "ORYH_BASE_URL": resolved_base_url(),
        "ORYH_API_BASE_URL": resolved_api_base_url(),
        "ORYH_API_KEY": "<the bearer token this MCP session already carries>",
        "EMPLOYEE_ID": actor.employee_id or "",
        "USER_NAME": (user.name or user.email) if user else "service",
        "TENANT_NAME": tenant.name if tenant else "",
        "TENANT_SLUG": tenant_slug(tenant),
        "INSTALL_DIR": "",
    }


def _render(content: str, context: dict[str, str]) -> str:
    return apply_brand(render_content(content, context))


def _prompt_entries(db: Session, actor: Actor) -> list[dict]:
    return [
        {"name": skill.name, "title": skill.title or skill.name, "description": (skill.description or "")[:1000], "arguments": []}
        for skill in _skills(db, actor)
    ]


def _resource_entries(db: Session, actor: Actor) -> list[dict]:
    entries = []
    for skill in _skills(db, actor):
        for path in sorted(skill.files_jsonb):
            if path == "SKILL.md":
                continue
            entries.append({
                "uri": f"oryh://skills/{skill.name}/{path}",
                "name": f"{skill.name}/{path}",
                "mimeType": "text/markdown",
            })
    return entries


# --- JSON-RPC --------------------------------------------------------------------


def _ok(request_id, result) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _err(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


async def _handle(request: Request, db: Session, actor: Actor, message: dict) -> dict | None:
    method = message.get("method")
    params = message.get("params") or {}
    request_id = message.get("id")
    if request_id is None:
        return None  # a notification: acknowledged, nothing to say
    if method == "initialize":
        asked = str(params.get("protocolVersion", ""))
        return _ok(request_id, {
            "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}, "resources": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        })
    if method == "ping":
        return _ok(request_id, {})
    if method == "tools/list":
        return _ok(request_id, {"tools": TOOLS})
    if method == "tools/call":
        name = str(params.get("name", ""))
        try:
            result = await _call_tool(request, name, params.get("arguments") or {})
        except KeyError:
            return _err(request_id, -32602, f"unknown tool {name!r}")
        return _ok(request_id, result)
    if method == "prompts/list":
        return _ok(request_id, {"prompts": _prompt_entries(db, actor)})
    if method == "prompts/get":
        name = str(params.get("name", ""))
        skill = next((s for s in _skills(db, actor) if s.name == name), None)
        if skill is None:
            return _err(request_id, -32602, f"no skill {name!r} reaches this credential")
        text = _render(skill.files_jsonb.get("SKILL.md", ""), _render_context(db, actor))
        return _ok(request_id, {
            "description": skill.description or skill.title or skill.name,
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        })
    if method == "resources/list":
        return _ok(request_id, {"resources": _resource_entries(db, actor)})
    if method == "resources/read":
        uri = str(params.get("uri", ""))
        match = re.match(r"^oryh://skills/([^/]+)/(.+)$", uri)
        skill = next((s for s in _skills(db, actor) if match and s.name == match.group(1)), None)
        if skill is None or match.group(2) not in skill.files_jsonb or match.group(2) == "SKILL.md":
            return _err(request_id, -32602, f"no resource {uri!r} reaches this credential")
        text = _render(skill.files_jsonb[match.group(2)], _render_context(db, actor))
        return _ok(request_id, {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": text}]})
    return _err(request_id, -32601, f"method not found: {method}")


@router.post("/mcp")
async def mcp_endpoint(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(_mcp_actor)],
):
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse(_err(None, -32700, "parse error"), status_code=400)
    messages = payload if isinstance(payload, list) else [payload]
    if not messages or not all(isinstance(m, dict) for m in messages):
        return JSONResponse(_err(None, -32600, "invalid request"), status_code=400)
    replies = [reply for m in messages if (reply := await _handle(request, db, actor, m)) is not None]
    if not replies:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    body = replies if isinstance(payload, list) else replies[0]
    return JSONResponse(body, headers={"MCP-Protocol-Version": PROTOCOL_VERSIONS[0]})


@router.get("/mcp")
def mcp_stream_not_offered():
    """Stateless server: no server-initiated stream to open."""
    return JSONResponse({"error": "this server is stateless; POST JSON-RPC messages"}, status_code=405)

