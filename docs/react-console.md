# React tenant console

The tenant administration console is a React single-page application. The
route-by-route migration from server-rendered Jinja pages is complete, and the
tenant-management Jinja handlers and templates have been removed. `/web` is no
longer a tenant console or an application-rollback surface: it contains public
account/device flows plus thin retirement responses for old bookmarks and
forms.

## Deployment boundary

The frontend is a separate build artifact and container, but it shares one
public origin with the FastAPI application:

```text
https://oryh.ai
  Compose nginx gateway
    /console/*  -> React static container
    /api/v1/*   -> FastAPI container
    /web/*      -> public account/device flows + retired tenant URL boundary
    /admin/*    -> platform console
```

For a retired tenant-management URL, `GET` and `HEAD` permanently redirect to
the corresponding `/console` route. Unsafe methods are never replayed and
return `410 Gone`. Public registration, verification, login, invitation/reset,
device authorization and connect-skill pages remain server-rendered. Image
rollback is provided by the versioned API and console deployment workflow, not
by a second tenant UI.

The browser calls `/api/v1` with relative URLs. Production deployments should
not enable cross-origin credentials or expose a tenant API key to browser
code. The frontend container is a deployment boundary, not a tenancy or
authorization boundary; the backend continues to derive `tenant_id` from the
authenticated session and bind the PostgreSQL RLS context.

API and console images have independent repository/tag variables. The
supported release scripts activate the API first, then the console and nginx
gateway, and verify the complete Nginx entry point. Image rollback keeps PostgreSQL forward and
starts the retained API image with startup maintenance disabled so its older
Alembic package never interprets a newer revision. The retained runtime still
must be schema-compatible under the expand/contract policy. See
deployment.md for the exact commands and failure behavior.

## Browser authentication

Agent clients continue to authenticate with `Authorization: Bearer` or
`X-API-Key`. Browser requests use a host-only, HttpOnly session cookie. Unsafe
cookie-authenticated API requests also send the double-submit CSRF token from
the readable CSRF cookie in `X-CSRF-Token`.

Session tokens and API keys must never be stored in browser storage. UI
capability checks are only presentation; every authorization decision remains
enforced by FastAPI.

Successful browser login, invitation acceptance, and password-reset completion
enter `/console`. Email verification is the deliberate bootstrap exception: its
single-use server-rendered confirmation reveals the initial service API key once
before the signed-in user continues to `/console/dashboard`. Passing that secret
through a URL or browser storage just to remove the confirmation page would
weaken the credential boundary.

## Phase one scope

- React, TypeScript, Vite, React Router and TanStack Query foundation.
- Authenticated application shell and permission-aware navigation.
- Browser login/logout, session bootstrap and CSRF protection.
- Console bootstrap and dashboard summary APIs.
- A separately buildable static frontend image with same-origin proxying.
- Public `/web` flows, retired-URL compatibility, and backend/frontend
  regression tests.

## Phase two scope

- Native React CRUD pages for projects, vendors and resources.
- Server-side keyword/status filtering and pagination, with stable ordering.
- Typed create/update/archive operations generated from the OpenAPI contract.
- A focused `master_data.manage` write capability; read access remains available
  to authenticated tenant members for business workflows. Existing tenant admin
  roles that hold `users.manage` remain compatible during capability rollout.
- Shared list, drawer, validation, empty/error, pagination and confirmation UI.
- Direct React routes are permission-aware. The corresponding retired `/web`
  GET URLs now redirect to these React routes.

API clients that opt into pagination send `page` and `size` and receive
`meta.total`, `meta.page`, `meta.page_size` and `meta.pages`. Older clients that
omit `page` continue to receive the complete filtered collection, preserving
the original response contract.

## Phase three scope

- Native React management for products and their optional SKU variants.
- Product-level filtering and pagination plus a selected-product SKU workspace;
  free-form variant attributes are edited as understandable key/value rows.
- Native React employee records with name, employee code, email, timezone and
  active/inactive lifecycle management.
- Product/SKU writes continue to use `master_data.manage`; employee writes and
  the direct employee route require `employees.manage`.
- Products, SKUs and employees adopt the same typed envelope and opt-in
  pagination contract while preserving unpaged API clients.

## Phase four scope

- Native React user invitation and account management, including role,
  lifecycle and optional employee linkage.
- Employee linkage uses bounded server-side search instead of loading the
  tenant's entire employee directory into the browser.
- Server-side user keyword/status/role filtering and pagination, while an
  omitted `page` keeps the legacy complete-list contract.
- Invitation resend and the console-email development link remain one-time
  server responses; invitation tokens are never persisted in browser storage.
- Active users can receive a one-time personal Skill bundle from React after an
  explicit credential-rotation confirmation; issuing it invalidates their
  previous user-bound keys and refreshes the API-key workspace cache.
- Native React role and capability management, including object-type-scoped
  grants, custom capabilities and the system-admin lockout guard.
- User and role mutations enforce a backend invariant that every tenant keeps
  at least one active human identity with `users.manage`; an unverified,
  disabled invite can only be recovered by issuing a fresh invitation.
- Direct identity-management routes and navigation require `users.manage` in
  the UI, while FastAPI remains the authorization boundary for every write.
- Retired `/web/users` and `/web/roles` GET bookmarks redirect to their React
  workspaces; their old form endpoints return `410 Gone`.

## Final migration scope

- Native React todo queue with employee scoping, a bounded administrator
  employee picker, tenant-scoped owner/creator/completer names,
  capability-aware completion, server-side filters and paginated ordering.
- Immutable approval-record browser with action, entity and keyword filters.
- Business-object directory and multi-resource detail views for custom objects,
  timesheets, expense claims, purchase requests and resource bookings. Detail
  views retain line items, attachments, links, approvals, todos, workflows and
  audit history, including supplier labels and product/SKU variant context. A
  bounded directory projection discovers schema-less legacy
  object types and resolves only the employee/actor names visible on the
  current page instead of downloading tenant-wide identity lists.
- Object-type and workflow workspaces for JSON Schema, optional state machines,
  lifecycle management, immutable workflow publishing and version history.
- Tenant skill package management, including multi-file editing, product-skill
  forking, capability-based distribution, SKILL.md frontmatter fallback and
  archive/restore lifecycle.
- API-key lifecycle management with service/user-bound identity selection,
  a `keys.manage`-scoped paginated owner search, the user's current effective
  role and owner availability, one-time secret display and immediate
  deactivate/reactivate controls.
- All tenant navigation now remains inside `/console`; `/admin` and public
  registration, invitation, device and bootstrap flows remain server-rendered.

The activity, configuration and automation lists use the same opt-in pagination
contract as earlier phases. Omitting both `page` and `size` preserves complete
collection responses for existing agent clients.

Workflow publication accepts only built-in types with an active definition, or
custom types backed by an active definition or existing tenant data. This keeps
append-only workflow history from accumulating unusable typo-only subjects.

## API compatibility

Frontend and backend images may be built independently, but deployments use an
expand/contract policy:

1. Deploy additive, backward-compatible API changes.
2. Deploy the frontend that consumes them.
3. Remove superseded API behavior only after the previous frontend release is
   outside the supported rollback window.

The generated frontend API types and contract tests are the compatibility
gate. At minimum, the current and immediately preceding frontend builds must
remain usable during a rolling deployment and rollback.

The production-entry Playwright gate runs against the Compose nginx gateway,
not Vite or mocked fetch. It covers direct deep links, the authenticated 404
surface, static-asset 404 behavior, same-origin cookie login, CSRF/logout, and
a representative project create/archive lifecycle. Run it with
`scripts/run_compose_e2e.sh`; it uses a dedicated tenant and isolated database
instead of deleting or depending on demo data.
