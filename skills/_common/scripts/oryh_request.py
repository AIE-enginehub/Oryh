#!/usr/bin/env python3
"""One oryh API call from the command line — stdlib only, no script to write.

    python3 scripts/oryh_request.py GET /todos employee_id=... status=open
    python3 scripts/oryh_request.py GET /projects keyword="wing phase"
    python3 scripts/oryh_request.py POST /approval-records --json '{"entity_type": "...", ...}'
    python3 scripts/oryh_request.py POST /timesheet-headers --json @body.json validate_only=true

Paths are relative to the API base (`/api/v1` is added when missing); `k=v`
arguments become query parameters; `--json` takes inline JSON or `@file`.
Connection: --base-url/--api-key flags win, then ORYH_BASE_URL/ORYH_API_KEY
environment variables, then the values rendered into this bundle.

Prints the response body as JSON on stdout — `{"data": ..., "meta": ...}` on
success, `{"detail": ...}` on an error — and exits with the HTTP class:
0 for 2xx, 4 for 4xx, 5 for 5xx, 1 for a configuration or connection problem.
Never retries: a 4xx is an answer (see the API conventions), not a hint to
try again with different parameters.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "{{ORYH_BASE_URL}}"
DEFAULT_API_KEY = "{{ORYH_API_KEY}}"


def _configured(flag: str | None, env: str, rendered: str) -> str:
    if flag:
        return flag
    if os.environ.get(env):
        return os.environ[env]
    return "" if rendered.startswith("{{") else rendered


def _api_base(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    return trimmed if trimmed.endswith("/api/v1") else trimmed + "/api/v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("method", choices=["GET", "POST", "PATCH", "PUT", "DELETE"])
    parser.add_argument("path")
    parser.add_argument("params", nargs="*", help="query parameters as key=value")
    parser.add_argument("--json", dest="body", help="request body: inline JSON or @file")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    args = parser.parse_args()

    base_url = _configured(args.base_url, "ORYH_BASE_URL", DEFAULT_BASE_URL)
    api_key = _configured(args.api_key, "ORYH_API_KEY", DEFAULT_API_KEY)
    if not base_url or not api_key:
        print(json.dumps({"detail": "no base URL or API key: pass --base-url/--api-key or set ORYH_BASE_URL/ORYH_API_KEY"}))
        return 1

    query = []
    for item in args.params:
        if "=" not in item:
            print(json.dumps({"detail": f"query parameter must be key=value, got {item!r}"}))
            return 1
        key, _, value = item.partition("=")
        query.append((key, value))
    path = args.path if args.path.startswith("/") else "/" + args.path
    url = _api_base(base_url) + path
    if query:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query)

    data = None
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    if args.body is not None:
        raw = open(args.body[1:], encoding="utf-8").read() if args.body.startswith("@") else args.body
        try:
            data = json.dumps(json.loads(raw)).encode("utf-8")
        except json.JSONDecodeError as exc:
            print(json.dumps({"detail": f"--json is not valid JSON: {exc}"}))
            return 1
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=args.method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, body = exc.code, exc.read()
    except (urllib.error.URLError, OSError) as exc:
        print(json.dumps({"detail": f"connection failed: {exc}"}))
        return 1

    text = body.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text) if text else {}
    except json.JSONDecodeError:
        parsed = {"detail": text[:2000]}
    print(json.dumps(parsed, ensure_ascii=False))
    return 0 if status < 300 else (4 if status < 500 else 5)


if __name__ == "__main__":
    sys.exit(main())
