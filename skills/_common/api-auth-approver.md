Use with:

- header: `X-API-Key: <the approver's own user-bound key>`
- api_base_url: `<base_url>/api/v1` — EVERY path below hangs off THIS, never
  bare `<base_url>` and never `<base_url>/api`; a wrong prefix does not 404,
  it returns the website
