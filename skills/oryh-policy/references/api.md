# Policy API

Every path hangs off `api_base_url` exactly as given — no version prefix to add.

## Policies

| Call | Purpose |
|---|---|
| `GET /policies` | what this credential may see |
| `GET /policies?code=HR-001` | every version of one policy, newest first |
| `GET /policies?category=payroll&status=published` | the live compensation policies |
| `GET /policies?in_force_on=2026-03-15` | **what applied on a date** — reads across superseded versions |
| `GET /policies?keyword=travel` | matches code, title and summary |
| `GET /policies?category=external_standard&in_force_on=2026-07-15` | the standard that applied on a date |
| `POST /policies` | draft one (or the next version of one) |
| `GET /policies/{policy_id}` | one version, body included |
| `PATCH /policies/{policy_id}` | correct a **draft** |
| `DELETE /policies/{policy_id}` | drop a **draft** |
| `POST /policies/{policy_id}/publish` | release it, closing the previous version |
| `POST /policies/{policy_id}/repeal` | repeal |

### Draft

```json
POST /policies
{
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

- Always lands as `status: "draft"`, whatever you send.
- Reusing a `code` allocates the next `version` and wires `supersedes_id` to the
  previous one. Two drafts of v2 cannot exist.
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
POST /policies/{policy_id}/publish
{"effective_from": "2026-09-01", "note": "approved at the August 2026 management meeting"}
```

Returns `{"current": {...}, "superseded": {...}}`. In one transaction it:

1. sets the previous published version of the same `code` to `superseded` and
   its `effective_thru` to the day before `effective_from`;
2. sets this one to `published` with `published_at` / `published_by`.

`superseded` is `null` for a first version. Publishing anything that is not a
draft is a 409. **One published version per `code`** is a partial unique index,
not a convention.

### Repeal

```json
POST /policies/{policy_id}/repeal
{"effective_thru": "2026-12-31", "note": "superseded by FIN-003"}
```

`effective_thru` defaults to today and may be backdated — a policy can be
repealed retroactively to the day a law changed, but not to before it started
(422). A repealed policy stops being visible to anyone without `policy.manage`.

## Figures

There is no rule table and no key lookup. A policy's figures are in its `body`,
and optionally restated in **`rules_json`** — a free-shape object on the same
row that the server never parses, never validates and never computes from.

```json
POST /policies
{
  "code": "FIN-2026-03",
  "category": "external_standard",
  "title": "Shanghai 2026 social-insurance contribution base standards",
  "body": "Per Shanghai HR&SS circular 2026 No. X: ceiling 36921, floor 7384.",
  "rules_json": {"social_insurance": {"base": {"cap": 36921, "floor": 7384}}}
}
```

It versions, publishes and freezes with the document — a published policy's
`rules_json` is a 409 to `PATCH`, by the same guard that refuses its `body`.

Reading a figure is an ordinary policy read:

```text
GET /policies?code=FIN-2026-03&in_force_on=2026-07-15
GET /policies?category=external_standard&in_force_on=2026-07-15
```

`in_force_on` reads across superseded versions, so a date in March returns the
document that governed March. Cite `code` and `version` with whatever you use.

## Read gate

| | draft | published `internal` | published `restricted` | repealed |
|---|---|---|---|---|
| holds `policy.manage` or `policy.publish` | ✓ | ✓ | ✓ | ✓ |
| holds the row's `required_capability` | — | ✓ | ✓ | — |
| any other credential in the tenant | — | ✓ | — | — |

- Single fetches return **404, not 403** — that a compensation policy exists is part of
  what it hides.
- List `total` is filtered too, not just the rows: how many restricted policies
  a workspace has is worth hiding on its own.
- `rules_json` rides the policy row, so the figures are gated by the same rule
  as the document — there is no second surface, and no way to read a restricted
  policy one number at a time.
- A **tenant service key bypasses the permission layer entirely** and therefore
  reads drafts. That is what that credential means; run policy agents on
  user-bound keys if the workspace cares.

## Capabilities

| capability | what it allows |
|---|---|
| *(none)* | reading published `internal` / `public` policies |
| the row's `required_capability` | reading that `restricted` policy |
| `policy.manage` | drafting, correcting and deleting drafts; seeing drafts and repealed policies |
| `policy.publish` | `publish` and `repeal` |
