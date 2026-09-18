"""Which delivery a piece of skill text is for: a bundle or an MCP connection."""

import re

# A skill reaches an agent two ways. A BUNDLE is files on the person's machine:
# a key rendered in, HTTP calls, bundled scripts, a manifest to re-sync. MCP is
# a connection: the client carries the OAuth token, every call is a tool, the
# server serves the current text. Text true of only one carries a marker line
# on each side — `<!-- only: bundle -->` or `<!-- only: mcp -->`, closed by
# `<!-- /only -->`, alone on its line (indented inside a list item, or after `> ` inside a quote, is fine)
# — and rendering keeps the block for its own delivery and drops the other.
# The markers survive provisioning like any text, so the registry holds both
# and neither delivery shows the other's instructions: an MCP agent was being
# told to send `X-API-Key: <the bearer token this MCP session already carries>`.
DELIVERIES = ("bundle", "mcp")
_DELIVERY_OPEN = re.compile(r"^[ \t]*(?:> ?)?<!-- only: (bundle|mcp) -->[ \t]*$")
_DELIVERY_CLOSE = re.compile(r"^[ \t]*(?:> ?)?<!-- /only -->[ \t]*$")


def delivery_blocks_error(content: str) -> str | None:
    """Why the markers in `content` are malformed, or None when they balance."""
    open_line = None
    for number, line in enumerate(content.splitlines(), 1):
        if _DELIVERY_OPEN.match(line):
            if open_line is not None:
                return f"line {number}: `only` block opened inside the one opened on line {open_line}"
            open_line = number
        elif _DELIVERY_CLOSE.match(line):
            if open_line is None:
                return f"line {number}: `/only` with no block open"
            open_line = None
        elif "<!-- only:" in line or "<!-- /only" in line:
            return f"line {number}: a delivery marker must stand alone on its line"
    return None if open_line is None else f"line {open_line}: `only` block never closed"


def for_delivery(content: str, delivery: str) -> str:
    """The text as `delivery` ("bundle" or "mcp") should read it."""
    if delivery not in DELIVERIES:
        raise ValueError(f"unknown delivery {delivery!r}")
    if "<!-- only:" not in content:
        return content
    kept, keeping = [], True
    for line in content.splitlines(keepends=True):
        opened = _DELIVERY_OPEN.match(line.rstrip("\r\n"))
        if opened:
            keeping = opened.group(1) == delivery
            continue
        if _DELIVERY_CLOSE.match(line.rstrip("\r\n")):
            keeping = True
            continue
        if keeping:
            kept.append(line)
    return "".join(kept)
