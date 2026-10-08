# Business rules API

<!-- only: bundle -->
Every path hangs off `api_base_url` exactly as given — no version prefix to add.
<!-- /only -->

{{include:_common/api-conventions.md}}

## Business rules

| Call | Purpose |
|---|---|
| `GET /business-rules` | what this credential may see, every kind |
| `GET /business-rules?kind=approval_flow&entity_kind=builtin&object_type=expense_claim&status=published` | the version in force for one scope |
| `GET /business-rules?kind=data_rule&entity_kind=business_object&object_type=warranty_card` | every version of one scoped rule, newest first |
| `GET /business-rules?kind=policy&code=HR-001` | every version of one policy, newest first |
| `GET /business-rules?kind=policy&category=payroll&status=published` | the live compensation policies |
| `GET /business-rules?in_force_on=2026-03-15` | **what applied on a date** — reads across superseded versions, any kind |
| `GET /business-rules?keyword=travel` | matches code, title, summary, body and object type |
| `GET /business-rules?status=draft&origin=catalog` | the seeded drafts not yet made this workspace's own |
| `POST /business-rules` | draft one (or the next version of one) |
| `POST /business-rules/publish` | draft and publish in one call — the next version of a scoped rule |
| `GET /business-rules/{rule_id}` | one version, body included |
| `PATCH /business-rules/{rule_id}` | correct a **draft** |
| `DELETE /business-rules/{rule_id}` | drop a **draft** |
| `POST /business-rules/{rule_id}/publish` | release it, closing the previous version |
| `POST /business-rules/{rule_id}/visibility` | change who may read it, at any status |
| `POST /business-rules/{rule_id}/repeal` | repeal |
| `GET /business-rules/{rule_id}/attachments/{attachment_id}/content` | the attached document, behind the rule's own read gate |

Every row carries `kind`, `code`, `version`, `status`, the scope columns
(`entity_kind`, `object_type`, `name` — null on a policy), `origin`
(`tenant` or `catalog`), `effective_from` / `effective_thru`, `published_at` /
`published_by`, `supersedes_id`, `visibility` / `required_capability`.

### The kinds

| `kind` | `code` | `category` | scope |
|---|---|---|---|
| `policy` | yours — `HR-001`, `FIN-2026-03` | **required**, from `policy_category` | none |
| `approval_flow` | generated: `approval_flow:{entity_kind}:{object_type}:{name}` | refused | **required** |
| `data_rule` | generated the same way | refused | **required** |
| `linkage` | generated the same way | refused | **required** |

Scope: `entity_kind` is `builtin` (default) or `business_object`;
`object_type` must be a builtin family with a lifecycle, or a custom type the
workspace has defined or holds records of — anything else is a 422 naming the
known types; `name` defaults to `default`. Two scoped rules of one kind on the
same type differ by `name`.

### Draft

```json
POST /business-rules
{
  "kind": "policy",
  "code": "FIN-002",
  "category": "expense",
  "title": "Travel and expense standards (2026)",
  "body": "# Travel and expense standards\n\n## 1. Lodging\nTier-one cities: no more than 600 per night……",
  "summary": "Lodging, travel and meal standards in force from 2026",
  "rules_json": {"travel": {"hotel": {"cap": {"tier1": 600, "tier2": 450}}}},
  "visibility": "internal",
  "effective_from": "2026-09-01",
  "owner_employee_id": "employee-uuid",
  "attachment_id": "attachment-uuid"
}
```

```json
POST /business-rules
{
  "kind": "data_rule",
  "entity_kind": "builtin",
  "object_type": "timesheet_header",
  "body": "Every line names a project task; the week totals exactly 40 hours."
}
```

- Always lands as `status: "draft"`, whatever you send.
- Reusing a `code` — or, for a scoped kind, the same scope — allocates the next
  `version` and wires `supersedes_id` to the previous one. Two drafts of v2
  cannot exist.
- `title` defaults to `{object_type} {kind}` on a scoped kind; a policy names
  its own.
- `category`: `GET /type-options?family=policy_category` — ships `hr`,
  `payroll`, `finance`, `expense`, `procurement`, `compliance`,
  `external_standard`, `other`. `POST /type-options` extends it.
- `visibility` ∈ `internal` / `restricted` / `public`. `restricted` **requires**
  `required_capability` (422 otherwise).
- `effective_from` is when it APPLIES, not when it was published. Both may be
  set at publication instead.
- `rules_json` is optional and free in shape. The server stores it and nothing
  else; keeping it in step with `body` is the author's job.

### Publish

```json
POST /business-rules/{rule_id}/publish
{"effective_from": "2026-09-01", "note": "approved at the August 2026 management meeting"}
```

Returns `{"current": {...}, "superseded": {...}}`. In one transaction it:

1. sets the previous published version of the same `code` to `superseded` and
   its `effective_thru` to the day before `effective_from` — or to its own
   first day, when both were published the same day;
2. sets this one to `published` with `published_at` / `published_by`;
3. for an `approval_flow`, lifts a parked hosted-driving subscription for the
   family.

`superseded` is `null` for a first version. Publishing anything that is not a
draft is a 409. **One published version per `code`** is a partial unique index,
not a convention.

### Publish in one call

```json
POST /business-rules/publish
{
  "kind": "approval_flow",
  "entity_kind": "builtin",
  "object_type": "expense_claim",
  "name": "default",
  "body": "The line manager approves; over 5000 finance reviews as well.",
  "effective_from": "2026-10-07",
  "note": "finance review above 5000"
}
```

The same fields as a draft plus `note`; drafts and publishes the next version
in one transaction, `effective_from` defaulting to today. Returns the same
`{"current", "superseded"}` shape — the handover a workflow definition always
had, for any kind.

### Visibility

```json
POST /business-rules/{rule_id}/visibility
{"visibility": "restricted", "required_capability": "payroll.read", "note": "published company-wide by mistake"}
```

Any status; changes `visibility` and `required_capability` and nothing else.
Needs the kind's publishing grant; audited as `{kind}.visibility_changed`
with the before and after.

### Repeal

```json
POST /business-rules/{rule_id}/repeal
{"effective_thru": "2026-12-31", "note": "superseded by FIN-003"}
```

`effective_thru` defaults to today and may be backdated — a rule can be
repealed retroactively to the day a law changed, but not to before it started
(422). Only the newest version of a code may be repealed. A repealed rule
leaves the default list but stays readable by id and by `in_force_on` to
whoever could read it when it governed.

## Figures

There is no rule table and no key lookup. A policy's figures are in its `body`,
and optionally restated in **`rules_json`** — a free-shape object on the same
row that the server never parses, never validates and never computes from.

```json
POST /business-rules
{
  "kind": "policy",
  "code": "FIN-2026-03",
  "category": "external_standard",
  "title": "Shanghai 2026 social-insurance contribution base standards",
  "body": "Per Shanghai HR&SS circular 2026 No. X: ceiling 36921, floor 7384.",
  "rules_json": {"social_insurance": {"base": {"cap": 36921, "floor": 7384}}}
}
```

It versions, publishes and freezes with the document — a published rule's
`rules_json` is a 409 to `PATCH`, by the same guard that refuses its `body`.

Reading a figure is an ordinary read:

```text
GET /business-rules?code=FIN-2026-03&in_force_on=2026-07-15
GET /business-rules?kind=policy&category=external_standard&in_force_on=2026-07-15
```

`in_force_on` reads across superseded versions, so a date in March returns the
document that governed March. Cite `code` and `version` with whatever you use.

## Read gate

| | draft | published `internal` | published `restricted` | superseded / repealed |
|---|---|---|---|---|
| the kind's authors — `policy.manage` / `policy.publish` for policies, `workflows.publish` for the scoped kinds | ✓ | ✓ | ✓ | ✓ |
| holds the row's `required_capability` | — | ✓ | ✓ | ✓ by id or `in_force_on` |
| any other credential in the tenant | — | ✓ | — | ✓ by id or `in_force_on` |

- Single fetches return **404, not 403** — that a compensation policy exists is part of
  what it hides.
- List `total` is filtered too, not just the rows: how many restricted rules
  a workspace has is worth hiding on its own.
- `rules_json` rides the row, so the figures are gated by the same rule
  as the document — there is no second surface, and no way to read a restricted
  policy one number at a time.
- A **tenant service key bypasses the permission layer entirely** and therefore
  reads drafts. That is what that credential means — the flow agent must add
  `status=published` to every read; run policy agents on user-bound keys if the
  workspace cares.

## Capabilities

| capability | what it allows |
|---|---|
| *(none)* | reading published `internal` / `public` rules of every kind |
| the row's `required_capability` | reading that `restricted` rule |
| `policy.manage` | drafting, correcting and deleting policy drafts; seeing policy drafts, and repealed policies in the default list |
| `policy.publish` | `publish`, `visibility` and `repeal` on a policy |
| `workflows.publish` | everything above for `approval_flow`, `data_rule` and `linkage` — draft, publish-in-one-call, publish, visibility, repeal |
