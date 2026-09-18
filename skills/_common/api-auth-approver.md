<!-- only: bundle -->
Use with:

- header: `X-API-Key: <the approver's own user-bound key>`
- api_base_url: the value given in Required Inputs — EVERY path below hangs
  off THIS, exactly as handed to you. Do not append a version, do not trim one,
  do not substitute the bare site address: a wrong prefix does not 404, it
  returns the website, so the mistake reads as a puzzling reply rather than an
  error

- **Expiry.** Personal device keys expire (service keys do not). A 401 whose
  detail says **expired** — not "invalid" — is renewed in one call, no browser:
  `POST /auth/token/refresh` with `{"refresh_token": "<from your credentials
  file — never stored in a skill file>"}` → `{api_key, refresh_token,
  expires_at}`. Use the new key from here on and overwrite the saved refresh
  token — each is spent by the exchange that uses it; the key rendered in
  these files goes stale, so re-sync `GET /my/skill-bundle` when convenient.
  A 401 saying **invalid**, or a refresh answering "already used", means the
  credential is gone — reconnect with `$oryh-connect`; do not retry around it.
<!-- /only -->
<!-- only: mcp -->
Use with the connected Oryh MCP server:

- every call below is the `oryh_request` tool — `{"method", "path", "query",
  "body"}` — with `path` exactly as written here and query parameters in
  `query`. Never send a host, a key or a tenant id: the connection is the
  approver's own OAuth sign-in, and the server records the approval fact
  against it.
- **A 401** means the connection's sign-in lapsed or was revoked: ask the
  approver to reconnect Oryh in their client; do not retry around it.
<!-- /only -->
