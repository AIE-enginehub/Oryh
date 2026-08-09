# Policy API

Every path hangs off `api_base_url` exactly as given — no version prefix to add.

## 制度

| Call | Purpose |
|---|---|
| `GET /policies` | what this credential may see |
| `GET /policies?code=HR-001` | every version of one policy, newest first |
| `GET /policies?category=payroll&status=published` | the live 薪酬类制度 |
| `GET /policies?in_force_on=2026-03-15` | **what applied on a date** — reads across superseded versions |
| `GET /policies?keyword=差旅` | matches code, title and summary |
| `GET /policies?category=external_standard&in_force_on=2026-07-15` | the standard that applied on a date |
| `POST /policies` | draft one (or the next version of one) |
| `GET /policies/{policy_id}` | one version, body included |
| `PATCH /policies/{policy_id}` | correct a **draft** |
| `DELETE /policies/{policy_id}` | drop a **draft** |
| `POST /policies/{policy_id}/publish` | release it, closing the previous version |
| `POST /policies/{policy_id}/repeal` | 废止 |

### Draft

```json
POST /policies
{
  "code": "FIN-002",
  "category": "expense",
  "title": "差旅与报销标准（2026）",
  "body": "# 差旅与报销标准\n\n## 第一条 住宿\n一线城市每晚不超过 600 元……",
  "summary": "2026 年起执行的差旅住宿、交通与餐补标准",
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
{"effective_from": "2026-09-01", "note": "经 2026-08 管理会议通过"}
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
{"effective_thru": "2026-12-31", "note": "由 FIN-003 取代"}
```

`effective_thru` defaults to today and may be backdated — a policy can be
repealed retroactively to the day a law changed, but not to before it started
(422). A repealed policy stops being visible to anyone without `policy.manage`.

## 数字

There is no rule table and no key lookup. A policy's figures are in its `body`,
and optionally restated in **`rules_json`** — a free-shape object on the same
row that the server never parses, never validates and never computes from.

```json
POST /policies
{
  "code": "FIN-2026-03",
  "category": "external_standard",
  "title": "上海市2026年度社保缴费基数标准",
  "body": "依据沪人社规〔2026〕X号：上限 36921 元，下限 7384 元。",
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

- Single fetches return **404, not 403** — that a 薪酬管理办法 exists is part of
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
