"""Every internal link must point at something the STANDALONE build serves.

The published repository shipped three links to pages that are not part of the
open core: the login page offered `/home` and `/web/register`, and the connect
page — the one whose entire job is getting a new self-hoster's agent attached —
sent them to `/docs`. All three are 404 in a standalone build. The marketing
site is not exported and `app.saas` is not exported, so the pages exist only in
the hosted assembly, while the templates and console source that link to them
travelled unchanged.

That is the same shape as the build breaks `check_build_inputs` now catches —
the export withholds something and the referencing file does not follow — but
one a build check cannot see, because a link is not a build input. It fails at
run time, for a reader, on the first page they are shown.

The question is asked here in the PRIVATE tree, where the defect is introduced,
rather than only in the export where it is discovered. So this does not ask
"does this assembly serve it" — in the private tree the answer is yes to all
three and the test would sit green while the export shipped broken. It asks
what a standalone build would serve, from three facts this tree already holds:

  * routes whose endpoint is not under `app.saas` — the open core's own,
  * `nginx.standalone.conf`, whose catch-all is `return 404` where the hosted
    gateway proxies to the site,
  * the export's own REDACTIONS, so a link removed on the way out does not
    count against the private file that legitimately carries it.
"""

from __future__ import annotations

import pathlib
import re

from app.core.config import settings
from app.main import app

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "web" / "templates"
CONSOLE = ROOT / "frontend" / "src"
EXPORT_SCRIPT = ROOT / "scripts" / "export_open_core.py"

HREF = re.compile(r'href="(/[^"#?]*)')
# Branches a standalone assembly never renders, so links inside them are not
# reachable and must not be reported: an explicit `edition == "cloud"` guard,
# and the `platform_admin` block, whose variable only the hosted layer supplies
# — that is where base.html's operator nav lives.
HOSTED_ONLY_BLOCK = re.compile(
    r'\{%-?\s*(?:el)?if (?:edition == "cloud"|platform_admin)\s*-?%\}'
    r".*?\{%-?\s*(?:else|elif|endif)\s*-?%\}",
    re.S,
)


def _gateway_locations() -> tuple[set[str], set[str]]:
    """What the standalone gateway answers at all, as (exact, prefix).

    A FastAPI route is not enough to make a link live: the gateway proxies only
    an allowlist to the app, and `/docs` is the case that proves it — a real
    route on the app object, and 404 through the gateway, because `docs` is not
    in `location ~ ^/(?:api/v1|web|redoc|healthz|livez|readyz)(?:/|$)`. A guard
    that models the app rather than the deployment calls that link live and
    misses the defect; this one asked the config.
    """
    nginx = ROOT / "nginx"
    config = next(
        (c for c in (nginx / "nginx.standalone.conf", nginx / "nginx.conf") if c.exists()),
        None,
    )
    exact: set[str] = set()
    prefixes: set[str] = set()
    if config is None:
        return exact, prefixes
    text = config.read_text(encoding="utf-8")
    for match in re.finditer(r"^\s*location\s+(=\s*)?(\S+)\s*\{", text, re.M):
        is_exact, target = match.group(1), match.group(2)
        if target.startswith("~"):
            continue
        (exact if is_exact else prefixes).add(target.rstrip("/") or "/")
    # `location ~ ^/(?:api/v1|web|redoc|…)(?:/|$)` — the proxied allowlist.
    for match in re.finditer(r"location\s+~\s+\^/\(\?:([^)]+)\)", text):
        prefixes.update("/" + alternative for alternative in match.group(1).split("|"))
    return exact, prefixes


def _redactions() -> list[tuple[str, str, str]]:
    """What the export removes on the way out.

    Absent in the export itself — the script is a private tool — and that is
    correct: by then the removals have already happened.
    """
    if not EXPORT_SCRIPT.exists():
        return []
    namespace: dict = {}
    source = EXPORT_SCRIPT.read_text(encoding="utf-8")
    start = source.index("REDACTIONS = (")
    end = source.index("\n)\n", start) + 3
    exec(compile(source[start:end], str(EXPORT_SCRIPT), "exec"), namespace)
    return [(entry[0], entry[1], entry[2]) for entry in namespace["REDACTIONS"]]


def _withheld_from_the_export() -> set[str]:
    """Files the export does not ship, so the standalone build never has them.

    Read from the export's own EXCLUDE_WITHIN rather than restated here — a
    second list would drift from the first, and the drift would show up as this
    test quietly checking a file nobody publishes.
    """
    if not EXPORT_SCRIPT.exists():
        return set()
    namespace: dict = {}
    source = EXPORT_SCRIPT.read_text(encoding="utf-8")
    start = source.index("EXCLUDE_WITHIN = {")
    end = source.index("\n}\n", start) + 3
    exec(compile(source[start:end], str(EXPORT_SCRIPT), "exec"), namespace)
    return set(namespace["EXCLUDE_WITHIN"])


def _standalone_paths() -> set[str]:
    """Routes an assembly without `app.saas` would serve."""
    paths: set[str] = set()

    def walk(routes, prefix: str = "") -> None:
        for route in routes:
            nested = getattr(route, "original_router", None)
            if nested is not None:
                # This FastAPI keeps an included router NESTED rather than
                # flattening it onto the app, so a non-recursive walk sees 34
                # routes and misses every mounted path — `/web/connect` among
                # them, which is plainly served. And it is the INCLUDE-time
                # prefix that matters: a router declaring `APIRouter(prefix=
                # "/web")` already carries it in each child path, while
                # `include_router(..., prefix="/api/v1")` records it only here.
                context = getattr(route, "include_context", None)
                walk(nested.routes, prefix + getattr(context, "prefix", ""))
                continue
            endpoint = getattr(route, "endpoint", None)
            if endpoint is not None and getattr(endpoint, "__module__", "").startswith("app.saas"):
                continue
            path = getattr(route, "path", None)
            if path is not None:
                paths.add(prefix + path)
            if getattr(route, "routes", None):
                walk(route.routes, prefix + (path or ""))

    walk(app.routes)
    return paths


def _standalone_gateway_serves_the_site() -> bool:
    """Both gateways state this outright in their catch-all.

    The hosted one is `location / { proxy_pass $site_upstream; }`; the
    standalone one is `location / { return 404; }`. Reading it beats keeping a
    list of site paths, which would be one more thing to forget to update.
    """
    nginx = ROOT / "nginx"
    # The export renames `nginx.standalone.conf` to `nginx.conf` and ships one
    # file — the same trap that made an earlier gateway test fail in the export
    # by naming a file the export renames. Prefer the explicit name, fall back.
    for config in (nginx / "nginx.standalone.conf", nginx / "nginx.conf"):
        if config.exists():
            return "proxy_pass $site_upstream" in config.read_text(encoding="utf-8")
    return False


def _served(path: str, paths: set[str], gateway: tuple[set[str], set[str]]) -> bool:
    exact, prefixes = gateway
    # First hurdle: does the gateway answer this path at all?
    reachable = path in exact or any(
        path == prefix or path.startswith(prefix + "/") for prefix in prefixes
    )
    if not reachable:
        return False
    # The console is an SPA — the gateway serves its index for any deep link,
    # so `/console/anything` is live without a route behind it.
    if path == "/console" or path.startswith("/console/"):
        return True
    if path in exact and path not in paths:
        # An exact location that answers on its own (a redirect, a health stub).
        return True
    if path in paths:
        return True
    for candidate in paths:  # /users/{user_id}/skill-bundle matches /users/abc/…
        if "{" in candidate and re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", candidate), path):
            return True
    return False


def _links() -> list[tuple[str, str]]:
    redactions = _redactions()

    def as_published(relative: str, text: str) -> str:
        for target, old, new in redactions:
            if target == relative:
                text = text.replace(old, new)
        return text

    withheld = _withheld_from_the_export()
    found = []
    for template in sorted(TEMPLATES.glob("*.html")):
        relative = template.relative_to(ROOT).as_posix()
        if relative in withheld:
            continue
        text = HOSTED_ONLY_BLOCK.sub("", as_published(relative, template.read_text(encoding="utf-8")))
        for href in HREF.findall(text):
            # `/admin/tenants/{{ t.id }}` is one link with a value in it; the
            # prefix is what decides whether the page exists.
            found.append((template.name, href.split("{{")[0].rstrip("/") or "/"))
    if CONSOLE.is_dir():
        for source in sorted(CONSOLE.rglob("*.tsx")):
            relative = source.relative_to(ROOT).as_posix()
            text = as_published(relative, source.read_text(encoding="utf-8"))
            for href in HREF.findall(text):
                found.append((relative, href))
    return found


def test_there_are_internal_links_to_check() -> None:
    # Guard the guard: a regex that stops matching, or a templates directory
    # that moves, would make the assertion below pass by finding nothing.
    links = _links()
    assert len(links) > 5, f"only found {links} — the scan is broken, not the tree clean"


def test_the_standalone_route_set_excludes_the_hosted_layer() -> None:
    # And guard the exclusion: if `app.saas` stopped being detectable, every
    # hosted-only path would count as served and the test above could not fail.
    paths = _standalone_paths()
    assert "/web/connect" in paths, "the open core's own routes are missing"
    if settings.resolved_edition == "cloud":
        assert "/web/register" not in paths, "hosted-only routes leaked into the standalone set"


def test_no_dead_links_in_the_standalone_build() -> None:
    assert not _standalone_gateway_serves_the_site(), (
        "nginx.standalone.conf now proxies unmatched paths to a site — "
        "this test's premise changed"
    )
    paths = _standalone_paths()
    gateway = _gateway_locations()
    dead = [
        f"{where} → {href}" for where, href in _links() if not _served(href, paths, gateway)
    ]
    assert not dead, f"links to paths a standalone build does not serve: {dead}"
