"""Unknown query parameters are refused, not ignored.

FastAPI drops query parameters an operation does not declare, so
`GET /products?product_code=X` answered with the unfiltered list — and an
agent taking the first row picked the wrong product. Body fields already
refuse extras (`extra="forbid"`); this is the same rule for the query string
of read operations: a 422 naming the parameter and the ones the operation
does accept, so the caller corrects itself instead of trusting a list that
was never filtered."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.core.config import API_PREFIX

READ_METHODS = frozenset({"GET", "HEAD"})


def _query_param_aliases(dependant) -> set[str]:
    """Every query parameter the operation and its dependencies declare.

    Walks `Dependant.query_params` / `.dependencies` itself rather than calling
    `fastapi.dependencies.utils.get_flat_dependant`: that helper is internal,
    and FastAPI 0.141 removed it — the API then failed to import at startup
    wherever the dependency set was resolved fresh instead of from uv.lock."""
    aliases = {field.alias for field in dependant.query_params}
    for sub in dependant.dependencies:
        aliases |= _query_param_aliases(sub)
    return aliases


def accepted_query_params(route: APIRoute) -> frozenset[str]:
    # APIRoute is unhashable; the answer is cached on the route itself
    accepted = getattr(route, "_oryh_accepted_query_params", None)
    if accepted is None:
        accepted = frozenset(_query_param_aliases(route.dependant))
        route._oryh_accepted_query_params = accepted
    return accepted


def reject_unknown_query_params(request: Request) -> None:
    if request.method not in READ_METHODS or not request.url.path.startswith(f"{API_PREFIX}/"):
        return
    route = request.scope.get("route")
    if not isinstance(route, APIRoute):
        return
    accepted = accepted_query_params(route)
    unknown = [name for name in dict.fromkeys(request.query_params.keys()) if name not in accepted]
    if not unknown:
        return
    accepted_text = ", ".join(sorted(accepted)) or "none"
    raise RequestValidationError([
        {
            "type": "extra_forbidden",
            "loc": ["query", name],
            "msg": f"Unknown query parameter '{name}' — this operation accepts: {accepted_text}",
            "input": request.query_params.get(name),
        }
        for name in unknown
    ])
