#!/usr/bin/env python3
"""Import historical quotations, orders, or purchase orders in chunks.

The mechanical half of a migration, done deterministically: chunking at the
server's 500-document cap, keeping every reported index global to YOUR file,
progress you can watch for twenty minutes, and ONE list of problem documents
at the end grouped by cause. The judgment half — which column meant what,
whether an unmatched customer should be created first or accepted as
historical text — happened in the conversation. Stdlib only.

Usage (from this skill's directory):

    python3 scripts/import_documents.py --kind quotations rows.json           # dry run
    python3 scripts/import_documents.py --kind quotations rows.json --apply
    python3 scripts/import_documents.py --kind orders rows.json --apply \
        --on-missing-reference snapshot

rows.json is a JSON array of document rows exactly as references/api.md
gives. Connection: --base-url/--api-key flags, then ORYH_BASE_URL/
ORYH_API_KEY environment variables, then the bundle's values.

Prints progress per chunk to stderr and one JSON report on stdout:

    {"dry_run", "kind", "total_documents", "chunks_sent", "chunks_applied",
     "summary": {"total", "created", "updated", "unchanged", "failed"},
     "problems": {"unknown customer_code": ["QT-…", …], …},
     "stopped_at_row": N | null}

Re-running the same file is safe and is how an interrupted migration
resumes: already-imported documents come back `unchanged` in seconds.

Exit 0: every document imported. Exit 1: configuration or input problem.
Exit 2: some documents failed or the run stopped early — the report says
which, by document number.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import urllib.error
import urllib.request

# Rendered per person at bundle download; the repo copy keeps the literal
# placeholder, which _configured() treats as "not set".
DEFAULT_BASE_URL = "{{ORYH_BASE_URL}}"
DEFAULT_API_KEY = "{{ORYH_API_KEY}}"

SERVER_MAX_ROWS = 500
KINDS = {
    "quotations": "sales-quotations",
    "orders": "sales-orders",
    "purchase-orders": "purchase-orders",
}


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


def _post_chunk(base_url: str, api_key: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{_site_origin(base_url)}/api/v1/{path}/bulk",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))["data"]


def _cause(error: str) -> str:
    """Group problems by what the person must DO about them, not by the exact
    code that was missing — 1,240 documents citing 43 customers is one work
    item, and listing it 1,240 times helps nobody."""
    for pattern, cause in (
        (r"unknown customer_code", "unknown customer_code"),
        (r"unknown product_code", "unknown product_code"),
        (r"unknown sku_code", "unknown sku_code"),
        (r"unknown project_code", "unknown project_code"),
        (r"employee_code", "missing salesperson"),
        (r"vendor_code", "missing vendor"),
        (r"duplicate", "duplicate document number in the file"),
        (r"not a state", "status not in the tenant's state machine"),
        (r"adjustment pinned", "adjustment pinned to a line the document lacks"),
    ):
        if re.search(pattern, error):
            return cause
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("rows_file", help="JSON array of document rows")
    parser.add_argument("--kind", required=True, choices=sorted(KINDS))
    parser.add_argument("--apply", action="store_true", help="write for real (default is a dry run)")
    parser.add_argument("--on-error", choices=("skip", "abort"), default="skip")
    parser.add_argument(
        "--on-missing-reference", choices=("error", "snapshot"), default="error",
        help="error: report documents whose codes match nothing; snapshot: import them as text",
    )
    parser.add_argument("--chunk-size", type=int, default=SERVER_MAX_ROWS)
    parser.add_argument("--base-url", help="server base URL; the API root is accepted too (default: env ORYH_BASE_URL, then bundle)")
    parser.add_argument("--api-key", help="user-bound API key (default: env ORYH_API_KEY, then bundle)")
    args = parser.parse_args()

    base_url = _configured(args.base_url, "ORYH_BASE_URL", DEFAULT_BASE_URL)
    api_key = _configured(args.api_key, "ORYH_API_KEY", DEFAULT_API_KEY)
    if not base_url or not api_key:
        print("no base URL / API key: pass --base-url/--api-key or set ORYH_BASE_URL/ORYH_API_KEY", file=sys.stderr)
        return 1
    if not 1 <= args.chunk_size <= SERVER_MAX_ROWS:
        print(f"--chunk-size must be 1..{SERVER_MAX_ROWS}", file=sys.stderr)
        return 1

    try:
        with open(args.rows_file, encoding="utf-8") as handle:
            rows = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        print(f"cannot read {args.rows_file}: {error}", file=sys.stderr)
        return 1
    if not isinstance(rows, list) or not rows:
        print(f"{args.rows_file} must be a non-empty JSON array of document rows", file=sys.stderr)
        return 1

    path = KINDS[args.kind]
    summary = collections.Counter()
    problems: dict[str, list[str]] = collections.defaultdict(list)
    chunks_sent = chunks_applied = 0
    stopped_at_row = None
    total_chunks = (len(rows) + args.chunk_size - 1) // args.chunk_size

    for offset in range(0, len(rows), args.chunk_size):
        chunk = rows[offset : offset + args.chunk_size]
        try:
            data = _post_chunk(base_url, api_key, path, {
                "rows": chunk,
                "dry_run": not args.apply,
                "on_error": args.on_error,
                "on_missing_reference": args.on_missing_reference,
            })
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", "replace")
            try:
                detail = json.loads(body).get("detail", body)
            except json.JSONDecodeError:
                detail = body
            print(f"HTTP {error.code} on rows {offset}..{offset + len(chunk) - 1}: {detail}", file=sys.stderr)
            stopped_at_row = offset
            break
        except (urllib.error.URLError, TimeoutError) as error:
            print(f"connection failed on rows {offset}..{offset + len(chunk) - 1}: {error}", file=sys.stderr)
            stopped_at_row = offset
            break

        chunks_sent += 1
        chunks_applied += bool(data.get("applied"))
        summary.update(data["summary"])
        for result in data["results"]:
            if result.get("outcome") == "error":
                problems[_cause(result.get("error") or "")].append(result.get("number") or f"row {offset + result['index']}")
        print(
            f"chunk {chunks_sent}/{total_chunks} "
            f"(rows {offset}..{offset + len(chunk) - 1}): {dict(data['summary'])}",
            file=sys.stderr,
        )

        if data["summary"].get("failed") and args.on_error == "abort":
            after = offset + len(chunk)
            stopped_at_row = after if after < len(rows) else None
            break

    report = {
        "dry_run": not args.apply,
        "kind": args.kind,
        "total_documents": len(rows),
        "chunks_sent": chunks_sent,
        "chunks_applied": chunks_applied,
        "summary": dict(summary),
        "problems": {cause: numbers for cause, numbers in sorted(problems.items())},
        "stopped_at_row": stopped_at_row,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if problems or stopped_at_row is not None else 0


if __name__ == "__main__":
    sys.exit(main())
