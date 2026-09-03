# Capabilities, Skills, and the API — How They Relate

Three things in oryh sound similar and are constantly confused. This doc
draws the line once.

- **Capability** — a permission string on a role (e.g. `approval.record`,
  `business_object.write:daily_report`).
- **API** — the HTTP endpoints an agent or the console calls.
- **Skill** — a Markdown process contract (`SKILL.md` + references) that an
  agent loads and follows; it calls the API.

The one sentence to remember: **a capability is the real gate on the API;
the same capability string is *also* used, separately, to decide which skills
land in a person's bundle.** Two enforcement paths, one vocabulary.

## The Three Layers

```
 role.permissions_jsonb  ──(require_permission)──▶  core API endpoint    [HARD GATE]
        (capability strings)
        │
        └────────────────────(capability_covers)──▶  skill in bundle?   [SOFT FILTER]
                                                       (required_capability)
```

1. **System capability → API.** Every entry in `SYSTEM_CAPABILITIES`
   (`app/core/permissions.py`) maps to a `require_permission(...)` call inside
   a real endpoint. This is the only gate that actually protects data: it runs
   no matter who calls (browser, script, agent) and cannot be bypassed by
   possessing a skill file.
2. **Capability → skill distribution.** A skill declares one
   `required_capability`. At bundle time (`eligible_skills` /
   `capability_covers` in `app/services/bundles.py`) a skill is included only
   if the person's role covers that capability. This decides *what an agent is
   handed*, not *what it may do*.
3. **Custom capability → skills/flow only.** Tenant-defined capabilities
   (the tenant's own custom capabilities on the Roles page) are matched *only* in layer 2 and in
   workflow-routing text. They never guard a core endpoint — inventing one
   adds a skill/flow label, never an API permission.

Because layers 1 and 2 read the *same* string off the *same* role, the
platform holds an invariant: **holding a skill implies permission to run it.**
You can never be handed a skill whose API calls you'd be 403'd on, and
stripping a capability removes both the API access and the skill together.

### The one principal that carries grants without a role

A tenant-level service key bypasses layer 1 outright (`has_permission` returns
True for it) and takes `ALL_PERMISSIONS` as its stand-in at layer 2. That is not
a hole: the tenant issued that key to itself, and it is the recovery credential
of last resort.

The exception is the **hosted flow agent** — the principal ORYH operates inside
a customer's tenant when the customer would rather not run their own flow agent.
It is held by someone other than the tenant, so it goes through both layers like
any other actor, on a grant set fixed in `HOSTED_FLOW_AGENT_PERMISSIONS` rather
than read from a tenant `Role` row (it is the contract with the customer, not one
of their tuning knobs). Two consequences worth knowing:

- its bundle is filtered by that set, so it receives the `*-approval-flow` skills
  and not, say, `oryh-access-admin` — the invariant above holds for it too;
- `attributed()` refuses to let it name anyone else, so every `*_by` field and
  audit row it writes reads `key:<id>`, which the display-name resolver renders
  from a platform constant ("ORYH hosted flow agent"), never from the key's label.

The predicate that separates the two is `Actor.bypasses_permissions`
(`app/api/deps.py`). `Actor.kind` still answers "is a person behind this
credential"; `principal_kind` answers "whose machine holds it".

## System Capability → API → Skill Map

Every system capability, the endpoints it guards, and the skill(s) that gate
on it. (Management capabilities at the bottom guard the console/REST only and
intentionally back no agent skill.)

| Capability | Guards these API endpoints | Skill(s) gated on it |
|---|---|---|
| `timesheet.submit_own` | `POST /timesheet-headers`, `POST /timesheet-headers/{id}/submit`, `POST /timesheet-entries`, `PATCH`/`DELETE /timesheet-entries/{id}` | `oryh-timesheet-submit` |
| `timesheet.advance` | `PATCH /timesheet-headers/{id}` (only when `status` changes) | `oryh-timesheet-approval-flow` |
| `expense.submit_own` | `POST /expense-claims`, `POST /expense-claims/{id}/submit`, `POST /expense-items`, `PATCH`/`DELETE /expense-items/{id}` | `oryh-expense-submit` |
| `expense.advance` | `PATCH /expense-claims/{id}` (only when `status` changes) | `oryh-expense-approval-flow` |
| `purchase.submit_own` | `POST /purchase-requests`, `POST /purchase-requests/{id}/submit`, `POST /purchase-request-items`, `PATCH`/`DELETE /purchase-request-items/{id}` | `oryh-purchase-submit` |
| `purchase.advance` | `PATCH /purchase-requests/{id}` (only when `status` changes) | `oryh-purchase-approval-flow` |
| `quotation.submit_own` | `POST /sales-quotations`, `POST /sales-quotations/{id}/submit`+`/send`+`/close`+`/revise`, `POST /sales-quotation-items`, `PATCH`/`DELETE /sales-quotation-items/{id}` | `oryh-quotation-submit` |
| `quotation.advance` | `PATCH /sales-quotations/{id}` (only when `status` changes — approval finalization and the expiry sweep) | `oryh-quotation-approval-flow` |
| `order.submit_own` | `POST /sales-orders`, `POST /sales-orders/{id}/submit`, `POST /sales-order-items`, `PATCH`/`DELETE /sales-order-items/{id}`, field-level `PATCH /sales-orders/{id}` (logistics facts). Customer RETURNS are rows in the same collection (`order_kind=return`, `original_order_id` → the order reversed, SR- numbers, own `sales_return` machine) | `oryh-order-submit` |
| `order.advance` | `PATCH /sales-orders/{id}` (only when `status` changes — confirmation and fact-driven fulfilment advancement) | `oryh-order-approval-flow` |
| `invoice.manage` *(scopable `:sales` / `:purchase` / `:payroll`)* | `POST`/`PATCH`/`DELETE`/`restore` `/invoices*`, `POST /invoices/bulk`, `POST /invoices/{id}/submit`, `POST`/`PATCH`/`DELETE /invoice-items*` | `oryh-receivables` (`:sales`), `oryh-payables` (`:purchase`), `oryh-payroll` (`:payroll`) |
| `invoice.advance` | `PATCH /invoices/{id}` (only when `status` changes) | `oryh-invoice-approval-flow` |
| `payment.record` | `POST`/`PATCH`/`DELETE`/`restore` `/payments*`, `POST /payments/bulk` | `oryh-receivables`, `oryh-payables`, `oryh-payroll` |
| `payment.advance` | `PATCH /payments/{id}` (only when `status` changes) | `oryh-payment-approval-flow` |
| `payment.apply` | `POST /payments/{id}/apply` | `oryh-receivables`, `oryh-payables`, `oryh-payroll` |
| *(`payment.record` / `payment.apply` also **widen a read**)* | a payout naming another employee as payee is hidden from credentials holding neither — a cashier must see what they are paying, an ordinary employee has no such reason | — |
| `billing_account.manage` | `POST`/`PATCH`/`DELETE`/`restore` `/billing-accounts*` | `oryh-billing-account` |
| `billing_account.post` *(scopable `:currency` / `:points`)* | `POST /billing-accounts/{id}/entries` | `oryh-billing-account` |
| `payroll.manage` | `POST`/`PATCH /pay-histories*` | `oryh-payroll` |
| `policy.manage` | `POST`/`PATCH`/`DELETE /policies*` (drafts only); also **widens reads** — drafts and repealed policies are visible only to holders | `oryh-policy` |
| `policy.publish` | `POST /policies/{id}/publish`, `POST /policies/{id}/repeal` | `oryh-policy` |
| *(`users.manage` also **reads the machinery**)* | `GET /roles` (the access topology), `GET /attachments/{id}` and its `/content` (by bare id; everyone else reads attachments through the owning document) — pinned by `tests/test_member_api_surface.py` | — |
| *(**`POST /attachments`** is granted by ANY of these ten)* | `expense.submit_own`, `purchase.submit_own`, `purchase_order.manage`, `quotation.submit_own`, `order.submit_own`, `invoice.manage` (any scope), `payment.record`, `policy.manage`, `master_data.manage` (product pictures), `contract.manage` (contract originals) — one per model carrying `attachment_id`, because whoever files the record must be able to attach its evidence. Pinned to the code by `tests/test_attachment_upload_gate.py`. **Reading** the bytes is a different question: `GET /attachments/{id}/content` needs `users.manage`, and everyone else goes through the document — `GET /invoices/{id}/attachments/{attachment_id}/content` and its nine siblings (products included — pictures are read by everyone through the product; contracts included — originals are read by the contract desk through the contract), where the document's own visibility answers first (`tests/test_attachment_reach.py`) | — |
| `payroll.read` | **a read gate, not a write gate** — filters `GET /invoices*`, `GET /payments*`, `GET /payment-applications`, `GET /object-directory`, and gates `GET /pay-histories*`, `GET /employees/{id}/pay-history` | `oryh-payroll` |
| `business_object.write` *(scopable `:type`)* | `POST`/`PATCH /business-objects`, `POST`/`PATCH /approval-targets` | `oryh-business-object` (bare); a tenant skill may gate on `business_object.write:daily_report` etc. |
| `business_object.advance` *(scopable)* | same `PATCH` endpoints, only on `status` change | *(none shipped — flow-admin/service credential)* |
| `business_object.summarize` *(scopable)* | *(none — no API gate)* | `oryh-business-object-summary` |
| `approval.record` | `POST /approval-records` | `oryh-approve` (all document types) |
| `flow_run.record` | `POST /flow-runs`, `PATCH /flow-runs/{id}` | *(none — held by the hosted flow agent so the runner needs no second, wider credential)* |
| `todos.assign` | `POST /todos`, `POST /todos/bulk` | `approval-notifier` |
| `todos.complete_own` | `PATCH /todos/{id}` | *(used within `oryh-my-work`, which is ungated)* |
| `booking.own` | `POST`/`PATCH`/`DELETE /resource-bookings` | `oryh-resource-booking` |
| `crm.own` | `POST`/`PATCH`/`DELETE /leads*`, `POST /leads/{id}/convert`, `POST`/`PATCH`/`DELETE /opportunities*` — the salesperson's own pipeline: one approval-free grant files AND advances; the conversion bridge creates the Customer (and rolodex entry) without master-data authority, because promotion IS the conversion's meaning. Reads are member-visible | `oryh-crm` |
| `master_data.manage` | `POST`/`PATCH`/`DELETE /projects`, `/vendors`, `/customers`, `/products`, `/product-skus`, `/resources`, `/external-product-maps` (which platform listing means which catalog product AT A GIVEN TIME — bundles as rows, listing swaps as effective windows, `?at=` resolves by date), plus `POST /products/bulk`, `/vendors/bulk`, `/customers/bulk` | `oryh-master-data` |
| *(**`POST`/`DELETE /external-document-links`** is granted per linked document)* | `sales_order` → `order.submit_own`, `purchase_order` → `purchase_order.manage`, `invoice` → `invoice.manage:{direction}`, `payment` → `payment.record`, `business_object` → `business_object.write:{object_type}`, `inventory_item_detail` → `inventory.manage` — a link is an annotation on the document, so whoever may record the document may say where it came from. Hard-unique per (source, kind, number, document); splits/merges are extra rows. Pinned by `tests/test_external_mapping.py` | `oryh-order-submit`, `oryh-inventory` |
| `inventory.manage` | `POST`/`PATCH`/`DELETE /inventory-items*`, `POST /inventory-items/bulk`, `POST /inventory-item-details`; also the freight legs — `POST`/`PATCH`/`DELETE /shipments*`, `/shipment-items*`, and `POST /shipments/{id}/post-stock` (the one once-only bridge from a shipment to the ledger) — split out of `master_data.manage` so a warehouse keeper holds the stock ledger without holding the catalog; receiving against a PO stays with `purchase_order.manage` | `oryh-inventory` |
| `fin_account.manage` | `GET`/`POST`/`PATCH`/`DELETE /fin-accounts*`, `GET`/`POST`/`PATCH /fin-account-transactions*`, `POST /fin-account-transactions/bulk` — the treasury desk, reads included (cash and ledger split: cash position and payout lines are payroll-grade; the accountant's `payment.record` never reaches the register, and this capability never reaches payment documents). Deliberately granted to no shipped role — naming the cashier is the tenant's first treasury decision, and the setup report shows the gap | `oryh-treasury` |
| `employees.manage` | `POST`/`PATCH /employees` | *(console only)* |
| `users.manage` | `POST /auth/invitations`, `GET`/`PATCH /auth/users*`, `POST`/`PATCH`/`DELETE /roles`, `POST`/`DELETE /capabilities`, `POST /users/{id}/skill-bundle`, `GET /workspace/setup-report` (the derived where-does-this-workspace-stand read behind the setup wizard) | `oryh-access-admin`, `oryh-workspace-setup` |
| `keys.manage` | `GET`/`POST`/`PATCH /tenant/api-keys*`, `POST /users/{id}/skill-bundle`; also reads flow machinery — `GET /flow-runs`, `GET /flow-subscriptions` (or `flow_run.record`) | *(console only)* |
| `object_types.manage` | `POST`/`PATCH`/`DELETE /object-type-definitions*` | *(console only)* |
| `workflows.publish` | `POST /workflow-definitions` | *(console only)* |
| `skills.manage` | `GET`/`POST`/`PATCH`/`DELETE /skills*` — the registry, reads included: every skill's text, files, audience and calibration. A member's own surface is `GET /my/skill-bundle` + `/my/skills/*` | *(console only)* |
| `tenant.act_for_any_employee` | not a standalone gate — the bypass in `enforce_member_employee` that lets a role act on any employee's timesheets/bookings/todos | *(none)* |

`users.manage` is also accepted temporarily at master-data write endpoints so
existing tenant admin roles remain functional when `master_data.manage` first
appears in the system capability catalog. Newly provisioned admin roles receive
the focused capability directly.

Three deliberate asymmetries worth noting:

- `business_object.advance` has an API gate but no shipped skill — flow
  advancement is done by an admin/service credential, not handed out as an
  agent skill.
- `business_object.summarize` has a skill but no API gate — reading business
  objects isn't restricted; the capability exists only to decide who gets the
  summary skill.
- A published `internal` policy is readable with **no capability at all**, and
  that is deliberate rather than an oversight: an employee handbook nobody may
  open is not a handbook. A policy that wants an audience names the capability
  itself in `required_capability`, reusing this same catalog — a compensation policy
  simply says `payroll.read`. See [policies.md](policies.md).
- `payroll.read` is the only capability in this catalog that gates a **read**.
  Every other list here is tenant-scoped and nothing more, which is right for
  business documents and unacceptable for pay. Without it a credential still
  sees its own payslip — an employee who cannot check what they were paid has
  no recourse — and someone else's is a 404 rather than a 403, because 403
  would confirm the document exists. Note that a tenant service key bypasses
  the permission layer entirely and therefore reads all pay; see
  [payroll.md](payroll.md).

## The `verb:scope` Grammar

Scopable verbs (`business_object.write`, `.advance`, `.summarize`) take an
object-type scope, and it extends automatically as a tenant defines new object
types — no code change. The same three forms satisfy both the API check and
skill distribution:

| Grant on the role | Covers |
|---|---|
| `business_object.write` (bare) | every object type |
| `business_object.write:*` | every object type |
| `business_object.write:daily_report` | only `daily_report` |

A skill's `required_capability` may use the scoped form too
(`business_object.write:daily_report`), and it matches a role grant by the
same rule (exact type, `:*`, or bare verb). This is what lets a tenant give a
self-defined object type its own skill without inventing a custom capability —
see [scoped-skill-capabilities.md](scoped-skill-capabilities.md). Non-scopable
verbs reject a scope; custom capabilities are exact scope-less strings.

Note: the scope is *not* validated against the object-type registry (a grant
of `business_object.write:not_yet_defined` is accepted), exactly as role
grants behave — scopable verbs are meant to extend ahead of the types.

## Authoring a Skill

Skills are tenant data. Three ways in, all landing in the same registry:

- **Console** (`/console/skills`, `skills.manage`): a React workspace with a capability picker
  (system verbs, per-object-type scopes, custom capabilities) and a file
  editor seeded with a `SKILL.md` starter template. Editing a product skill
  forks it to `custom` so platform syncs stop overwriting it.
- **API**: `POST`/`PATCH /api/v1/skills` with `required_capability` as a JSON
  field. Validated by the same grammar a role grant uses.
- **`scripts/import_skill.py`**: reads `name`, `description`, and
  `required_capability` straight from the `SKILL.md` frontmatter — copy a
  template file, fill it in, import.

The console form and `import_skill.py` both treat the `SKILL.md` frontmatter's
`required_capability` as a fallback, so a complete pasted/imported skill works
without re-specifying it; the console dropdown, when set, is the explicit
override.

## Where Each Piece Lives

- `app/core/permissions.py` — `SYSTEM_CAPABILITIES` catalog, the `verb:scope`
  grammar (`validate_permission_grammar`, `permissions_cover`).
- `app/api/*.py` — `require_permission(...)` calls: the hard API gates.
- `app/services/bundles.py` — `capability_covers` / `eligible_skills`: the
  soft skill-distribution filter.
- `app/api/skills.py` — skill CRUD + `validate_required_capability`.
- `frontend/src/pages/SkillsPage.tsx` — the React console skill editor.

## Related Docs

- [scoped-skill-capabilities.md](scoped-skill-capabilities.md) — walkthrough:
  a tenant-defined `daily_report` object type with its own scoped skill.
- [ai-native-platform.md](ai-native-platform.md) — the platform boundary
  (records + rules-as-data vs. agents that read and drive them).
