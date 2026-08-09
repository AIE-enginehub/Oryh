#!/usr/bin/env python3
"""Upload evidence files as oryh attachments.

The mechanical half of "upload the receipt", done deterministically: base64,
the 10 MB pre-check, the content-type guess, and the duplicate signal the
skill asks you to watch for. Stdlib only.

Usage (from this skill's directory):

    python3 scripts/upload_attachment.py 发票1.pdf 高铁票.jpg

Connection: --base-url/--api-key flags win, then ORYH_BASE_URL/ORYH_API_KEY
environment variables, then the values rendered into this bundle.

Prints a JSON array on stdout, one entry per file, in input order:

    {"file", "id", "sha256", "size_bytes", "created_at", "already_existed"}
                                 — or {"file", "error"} when that file failed.

`already_existed: true` means the server already held these exact bytes and
reused the stored row (HTTP 200); `false` means it stored them for the first
time (HTTP 201). The upload is idempotent per file content, so this is the
duplicate-receipt signal — tell the principal before filing an item against a
reused attachment. It comes from the server's own response code, so it is
right regardless of how recently the original was uploaded.

Exit 0: every file uploaded. Exit 1: configuration problem (no base URL or
API key). Exit 2: at least one file failed — including connection failures,
which are reported per file; the JSON names each failure.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request

# Rendered per person at bundle download; the repo copy keeps the literal
# placeholder, which _configured() treats as "not set".
DEFAULT_BASE_URL = "{{ORYH_BASE_URL}}"
DEFAULT_API_KEY = "{{ORYH_API_KEY}}"

MAX_BYTES = 10 * 1024 * 1024  # server limit; checked here so the principal
# hears "this file is 14 MB" instead of an HTTP 413


def _configured(flag: str | None, env: str, rendered: str) -> str:
    if flag:
        return flag
    if os.environ.get(env):
        return os.environ[env]
    return "" if rendered.startswith("{{") else rendered


def _site_origin(base_url: str) -> str:
    """The site origin, whichever address was handed in. Bundles now surface
    `api_base_url` (…/api/v1) more prominently than the bare site URL, so a
    caller passing that to --base-url is the likely mistake, not an exotic one —
    and it would build …/api/v1/api/v1/… , a 404 blamed on the server. Trimming
    a trailing API prefix costs nothing and cannot misfire: no site origin ends
    in /api/v1."""
    trimmed = base_url.rstrip("/")
    return trimmed[: -len("/api/v1")] if trimmed.endswith("/api/v1") else trimmed


def _post(base_url: str, api_key: str, payload: dict) -> tuple[int, dict]:
    """(status, data). 201 = these bytes are new to the server; 200 = it
    already held them. That is the server's own statement, not a guess."""
    request = urllib.request.Request(
        _site_origin(base_url) + "/api/v1/attachments",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.status, json.loads(response.read().decode("utf-8"))["data"]


def _upload_one(path: str, content_type: str | None, base_url: str, api_key: str) -> dict:
    if not os.path.isfile(path):
        return {"file": path, "error": "file not found"}
    with open(path, "rb") as handle:
        content = handle.read()
    if not content:
        return {"file": path, "error": "file is empty"}
    if len(content) > MAX_BYTES:
        return {"file": path, "error": f"file is {len(content) / 1024 / 1024:.1f} MB; the server accepts at most 10 MB"}
    local_sha = hashlib.sha256(content).hexdigest()
    payload = {
        "filename": os.path.basename(path),
        "content_type": content_type or mimetypes.guess_type(path)[0] or "application/octet-stream",
        "content_base64": base64.b64encode(content).decode("ascii"),
    }
    try:
        http_status, data = _post(base_url, api_key, payload)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        try:
            detail = json.loads(body).get("detail", body)
        except json.JSONDecodeError:
            detail = body
        return {"file": path, "error": f"HTTP {error.code}: {detail}"}
    except (urllib.error.URLError, TimeoutError) as error:
        return {"file": path, "error": f"connection failed: {error}"}
    if data.get("sha256") != local_sha:
        return {"file": path, "error": "server sha256 does not match the local file; do not use this attachment id"}
    return {
        "file": path,
        "id": data["id"],
        "sha256": data["sha256"],
        "size_bytes": data["size_bytes"],
        "created_at": data["created_at"],
        "already_existed": http_status == 200,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", help="receipt/evidence files to upload")
    parser.add_argument("--content-type", help="override the guessed MIME type for every file")
    parser.add_argument("--base-url", help="server base URL; the API root is accepted too (default: env ORYH_BASE_URL, then bundle)")
    parser.add_argument("--api-key", help="user-bound API key (default: env ORYH_API_KEY, then bundle)")
    args = parser.parse_args()

    base_url = _configured(args.base_url, "ORYH_BASE_URL", DEFAULT_BASE_URL)
    api_key = _configured(args.api_key, "ORYH_API_KEY", DEFAULT_API_KEY)
    if not base_url or not api_key:
        print("no base URL / API key: pass --base-url/--api-key or set ORYH_BASE_URL/ORYH_API_KEY", file=sys.stderr)
        return 1

    results = [_upload_one(path, args.content_type, base_url, api_key) for path in args.files]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 2 if any("error" in entry for entry in results) else 0


if __name__ == "__main__":
    sys.exit(main())
