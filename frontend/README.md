# Oryh tenant console

The authenticated tenant console: a React and TypeScript single-page
application built with base `/console/` (`npm run build` → `dist`,
`Dockerfile`). It ships as its own container and carries no marketing code —
the public website is a separate project at [`../site`](../site).

The Compose nginx gateway keeps browser traffic on one origin:

- `/console/*` serves this application.
- `/api/v1/*` proxies to FastAPI.
- `/web/*` serves public account/device flows plus permanent GET aliases for
  retired tenant URLs; unsafe requests to those retired URLs return `410 Gone`.
- `/admin/*` remains the separately scoped platform-operator console.
- `/`, `/docs`, and the rest of the public surface are served by the **site**
  container built from [`../site`](../site).
- `/redoc` and `/openapi.json` proxy the backend technical API reference.

The browser session and CSRF cookies remain the authentication boundary. Do
not add API keys, session tokens, or tenant identifiers to browser storage.

The React routes cover the complete tenant administration surface: dashboard;
project, vendor, product/SKU and resource master data; employees, users, roles
and capabilities; business objects and multi-resource details; todos and
approval history; object types and workflow versions; skills; and API keys.
Platform operations and public authentication/bootstrap pages intentionally
remain outside this application. There is no server-rendered tenant-management
fallback: application rollback uses retained API, console, and site images.

## Language

The console supports Simplified Chinese and English. It chooses Simplified
Chinese for a Chinese browser locale and English otherwise; users can switch
language from the selector on the login screen or in the console header. The
choice is retained in that browser's local storage and does not affect other
users or the tenant's data.

## Local development

Start FastAPI on port `8000`, then run:

```bash
npm ci
npm run dev
```

Open <http://127.0.0.1:5173/console/> for the tenant console. The Vite
development server proxies backend paths to port `8000`, so cookie
authentication behaves like production.

Useful checks:

```bash
npm run typecheck
npm test
npm run build        # console bundle -> dist
```

Vitest excludes `e2e/`; production-entry browser tests are a separate
Playwright suite. From the repository root, the supported repeatable run is:

```bash
scripts/run_compose_e2e.sh
```

It starts an isolated Compose project and database, seeds a reserved test-only
tenant, and exercises the built console image through the nginx gateway and
same-origin FastAPI proxy.

Regenerate the checked-in API snapshot and TypeScript types after an
intentional contract change, from the repository root:

```bash
uv run python scripts/export_openapi.py
npm --prefix frontend run api:generate
```

Both files are build inputs — the console image compiles against the committed
`schema.d.ts`, never against a live API — so forgetting this leaves the console
typed against an API the server no longer serves.
`tests/test_frontend_contract.py` fails when either file falls behind.

## Container

A multi-stage image (`Dockerfile`) compiles the build with Node and serves only
the static output from unprivileged Nginx on internal port `8080`. It serves
Vite's hashed assets with immutable caching, keeps the entry document uncached
for safe rollouts, and falls back to the SPA entry point for client-side
routes. The top-level Compose nginx service owns the public port and routes
`/console/*` here; the website container is documented in
[`../site/README.md`](../site/README.md).

From the repository root:

```bash
docker compose up --build nginx
```

Open <http://127.0.0.1:8080/console/> for the tenant console. The gateway and
the internal static container both expose `/_health`; only the gateway is
published to the host.
Versioned image deployment, external verification, and forward-only rollback
are documented in [docs/deployment.md](../docs/deployment.md).
