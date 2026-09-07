# ORYH tenant Console redesign

The Console is the tenant administrator's daily workspace: find records, inspect the current state of work, and make small, explicit edits. Agent connection remains available, with business data and to-dos taking priority on the dashboard.

## Changes

- The dashboard shows live tenant-wide counts, a separately scoped recent open to-do queue, common data destinations, and direct create links. A member's queue is always restricted to their linked employee; an unlinked member never makes an unrestricted queue request. Loading, empty and failed requests have distinct states.
- A single permission-aware navigation registry powers the sidebar, the `Cmd/Ctrl + K` page finder, and global creation. Existing route guards and server permissions remain unchanged.
- Customers, vendors, products, projects, resources and employees share URL-backed keyword, status and pagination state. Refresh and browser Back preserve the applied list view. Create links open the relevant form once and consume their URL intent.
- Record names open editing; successful saves and archives are announced inline. Existing archive semantics and validation remain in place. Product detail, SKU variants and batch creation retain their existing operations; the SKU workspace opens only after selecting a product.
- Editing and confirmation share focus trapping, return focus, unique accessible names, and protection against dismissal while a request is pending. To-do completion uses the same confirmation component and refreshes the dashboard afterward.
- Calm green and neutral surfaces, readable table rows, consistent form spacing, a compact sidebar and responsive drawers form a shared visual system. Wide tables scroll inside their panels.
- Management pages load on demand. Session, CSRF handling, backend contracts and deployment configuration are preserved.

## Local preview

```sh
cd frontend
npm run dev:preview
```

Open http://127.0.0.1:5175/console/dashboard.

This runs the actual Console against a **local in-memory sample adapter**. The banner explicitly labels the data as examples. It listens on loopback, makes no backend requests, and writes no authentication cookies. Restarting the server resets samples.

The sample adapter supports master data creation/editing/archiving and to-do completion. Other sections have read-only sample or empty states; credential issuance, invitations, emails, file downloads, configuration writes and advanced SKU batch operations are not simulated. Unsupported API actions return an explicit error. The preview mode cannot be built for production, and sample data is outside the browser bundle.

Normal `npm run dev` and `npm run build` continue to use the real application API.

## Verification

- TypeScript and production build pass. Route splitting removes the oversized Console bundle warning.
- 180 Vitest tests pass, including navigation permissions, keyboard navigation, create-link consumption under StrictMode, URL history, member queue scope, error handling, and modal focus/busy behavior.
- Browser checks at desktop and phone sizes cover dashboard, global finder, mobile navigation, customer creation/search/edit/archive, product/SKU interfaces, and to-do completion with refreshed counts. All browser writes used local samples.
- No cloud deployment or live business-data mutation was performed.
