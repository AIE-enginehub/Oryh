#!/usr/bin/env python3
"""Send normalised master-data rows through the bulk upsert.

The mechanical half of an import, done deterministically: chunking at the
server's 500-row cap, keeping every reported index global to YOUR file, and
honest reporting when a run stops halfway. The judgment half — reading the
spreadsheet, mapping columns, confirming with the person — happened before
this script and stays in the conversation. Stdlib only.

Usage (from this skill's directory):

    python3 scripts/bulk_import.py --kind products rows.json             # dry run
    python3 scripts/bulk_import.py --kind products rows.json --apply
    python3 scripts/bulk_import.py --kind vendors rows.json --apply --on-error skip

rows.json is a JSON array of row objects exactly as references/api.md gives
for the family. Connection: --base-url/--api-key flags, then
ORYH_BASE_URL/ORYH_API_KEY environment variables, then the bundle's values.

Prints one JSON report on stdout:

    {"dry_run", "kind", "total_rows", "chunks_sent", "chunks_applied",
     "summary": {"total", "created", "updated", "unchanged", "failed"},
     "changed_fields": {"list_price": 12, ...},
     "failures": [{"index", "code", "error"}, ...],
     "stopped_at_row": N | null}

- `failures[].index` and `stopped_at_row` are positions in rows.json — map
  them back to spreadsheet lines for the person.
- `changed_fields` counts which fields updates actually moved; every row
  moving the same odd field is the classic bad-mapping smell.
- Chunks go in order. In abort mode (the default) the first chunk with a bad
  row stops the run: with --apply, EARLIER chunks are already committed — the
  report says how many — and rows from `stopped_at_row` on were never sent.

Exit 0: clean. Exit 1: configuration or input problem (bad flags, missing
credentials, unreadable rows file). Exit 2: some rows failed or the run
stopped early — including a transport failure mid-run; the report has the
details.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import urllib.error
import urllib.request

# Rendered per person at bundle download; the repo copy keeps the literal
# placeholder, which _configured() treats as "not set".
DEFAULT_BASE_URL = "{{ORYH_BASE_URL}}"
DEFAULT_API_KEY = "{{ORYH_API_KEY}}"

SERVER_MAX_ROWS = 500
KINDS = ("products", "vendors", "customers")


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


def _post_chunk(base_url: str, api_key: str, kind: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{_site_origin(base_url)}/api/v1/{kind}/bulk",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))["data"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("rows_file", help="JSON array of normalised row objects")
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("--apply", action="store_true", help="write for real (default is a dry run)")
    parser.add_argument("--on-error", choices=("abort", "skip"), default="abort")
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
        rows = json.loads(open(args.rows_file, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError) as error:
        print(f"cannot read {args.rows_file}: {error}", file=sys.stderr)
        return 1
    if not isinstance(rows, list) or not rows:
        print(f"{args.rows_file} must be a non-empty JSON array of row objects", file=sys.stderr)
        return 1

    summary = collections.Counter()
    changed_fields = collections.Counter()
    failures: list[dict] = []
    chunks_sent = chunks_applied = 0
    stopped_at_row = None

    for offset in range(0, len(rows), args.chunk_size):
        chunk = rows[offset : offset + args.chunk_size]
        try:
            data = _post_chunk(
                base_url, api_key, args.kind,
                {"rows": chunk, "dry_run": not args.apply, "on_error": args.on_error},
            )
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
                failures.append({
                    "index": offset + result["index"],
                    "code": result.get("code"),
                    "error": result.get("error"),
                })
            else:
                changed_fields.update(result.get("changed") or [])

        # A bad row under abort semantics: this chunk wrote nothing, and a
        # mapping error found in chunk 1 should not be repeated over the rest.
        if data["summary"].get("failed") and args.on_error == "abort":
            after = offset + len(chunk)
            stopped_at_row = after if after < len(rows) else None
            break

    report = {
        "dry_run": not args.apply,
        "kind": args.kind,
        "total_rows": len(rows),
        "chunks_sent": chunks_sent,
        "chunks_applied": chunks_applied,
        "summary": dict(summary),
        "changed_fields": dict(changed_fields.most_common()),
        "failures": failures,
        "stopped_at_row": stopped_at_row,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if failures or stopped_at_row is not None else 0


if __name__ == "__main__":
    sys.exit(main())
