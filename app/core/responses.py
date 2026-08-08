from __future__ import annotations

_BARE_JSON = b"application/json"
_JSON_UTF8 = b"application/json; charset=utf-8"


class JSONCharsetMiddleware:
    """Pure-ASGI middleware that stamps `charset=utf-8` onto bare
    `application/json` content types.

    FastAPI serializes JSON with ensure_ascii=False (raw UTF-8 bytes) but
    declares no charset. Spec-compliant clients assume UTF-8 anyway, but
    several common ones (PowerShell 5, older Java HttpClients, requests'
    `.text` fallback, Excel/Power Query imports) guess Latin-1 or the local
    code page instead and render CJK payloads as mojibake. Rewriting the
    header at the outermost layer covers every router and exception handler
    in one place. Content types that already carry parameters are left
    untouched.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_charset(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (name, _JSON_UTF8)
                    if name.lower() == b"content-type"
                    and value.strip().lower() == _BARE_JSON
                    else (name, value)
                    for name, value in message.get("headers") or []
                ]
            await send(message)

        await self.app(scope, receive, send_with_charset)
