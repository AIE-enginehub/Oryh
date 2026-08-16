---
name: oryh-policy
description: Use when someone needs to write, publish, amend or repeal a company rule — 员工手册, 报销制度, 薪酬管理办法, 采购审批权限 — or to record an external standard the company must follow (社保缴费基数, 最低工资, 税率通知). Also use when an agent needs a figure a policy sets (差旅住宿上限, 提成比例, 缴费基数) and wants the document, version and publisher behind it. Not for routing a document through approval (that is the workflow definition), and not for one person's own salary or commission (that is oryh-payroll).
required_capability: policy.manage
---

# Oryh Policy

Company rules: draft → publish → amend → repeal.

Two ideas run through everything here:

- **A policy is published, not saved.** Drafting and publishing are separate
  calls and separate capabilities, because publishing is an authority act. A
  published policy is never edited in place — it is amended by publishing a new
  version, which closes the old one the day before. What people were told, and
  until when, stays answerable.
- **A figure an agent applies must be traceable to a document, a version and a
  person.** You get that by reading the policy and citing its `code` and
  `version`. There is deliberately no separate table of extracted numbers:
  that shape exists because traditional software cannot read a policy, and it
  would only be a second source of truth free to drift from the prose. **You
  can read the prose.**

{{include:_common/answer-the-question.md}}

{{include:_common/api-auth-principal.md}}

## Trigger Examples

- "Publish the employee handbook"
- "The lodging standard changed — 700 for tier-one cities"
- "What are this year's social-insurance contribution limits in Shanghai?"
  ← read the standard in force, cite it
- "The compensation policy is for directors and above only"
- "Repeal the old expense policy"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # policy.manage to draft; policy.publish to publish,
                                  # repeal, or change who may read a published one
  employee_id: "{{EMPLOYEE_ID}}"  # the officer recorded as a policy's owner, if any
```

Drafting and publishing are separate grants on purpose. If your key holds only
`policy.manage`, prepare the draft and say plainly that somebody with
`policy.publish` has to release it — do not describe an unpublished draft as if
it were in force.

## Drafting and publishing

```json
POST /policies
{
  "code": "FIN-002",
  "category": "expense",
  "title": "Travel and expense standards (2026)",
  "body": "# Travel and expense standards\n\n## 1. Lodging\nTier-one cities: no more than 600 per night……",
  "summary": "Lodging, travel and meal standards in force from 2026",
  "effective_from": "2026-09-01",
  "owner_employee_id": "..."
}
```

- Always lands as a **draft**, and a draft is invisible to everybody without
  `policy.manage`. That is deliberate: a draft reorganisation plan says what is
  coming before anyone has decided.
- **Reusing a `code` opens the next version** of that policy. The version number
  is the server's to allocate, so two people cannot both be drafting v2, and
  `supersedes_id` is wired to the previous version for you.
- `category` must be an active option:
  `GET /type-options?family=policy_category`. `external_standard` is the one
  worth knowing — see "Recording an external standard" below.
- `body` is Markdown and **the server never parses it**, exactly as it never
  parses a workflow definition.

```json
POST /policies/{policy_id}/publish
{"effective_from": "2026-09-01", "note": "approved at the August 2026 management meeting"}
```

The response is `{"current": ..., "superseded": ...}`. Publishing closes the
previous version's `effective_thru` at the day before this one starts, in one
transaction — read `superseded.effective_thru` to confirm the handover landed
where you meant. A policy approved today and applying next month is the
ordinary case, not an exception.

**Status is a marker; the dates are the truth.** `published` means "the current
version of this code". What applied in March is
`GET /policies?in_force_on=2026-03-15`, which reads across superseded versions
too. Never answer "what were the rules then" from the current version.

## Amending and repealing

- **Amending** = draft a new version of the same `code`, then publish it. Never
  `PATCH` a published policy — that is a 409, and it would change what people
  were told without leaving a trace that they were told something else.
- **`PATCH`** is for fixing a draft before it goes out.
- **Changing who can see it** = `POST /policies/{id}/visibility` with the new `visibility`
  and, for `restricted`, the `required_capability` that may read it. This is
  the one thing about a published policy that is NOT frozen, and deliberately:
  what the rule says was stated on a date, but who may read it is a standing
  decision that changes when the company does — a rule announced to management that
  later goes company-wide, or one published wider than intended.

  **Do not publish a new version to fix an audience.** A v2 whose only
  difference is who can read it puts a second document in the history that says
  the same thing, and the over-visible v1 stays readable as the superseded
  version anyway — so it does not even work. Re-scope the version itself; it
  works on `superseded` and `repealed` ones too, which is where it matters most.

  Needs `policy.publish`, and it is audited with the before and after. It
  changes visibility only — the body, the figures and the dates are untouched.
- **Repealing** = `POST /policies/{id}/repeal` with the date it stops applying. It is
  not deleted — people acted on it. A repealed policy also drops out of view for
  everyone but `policy.manage` holders, because a repealed rule left in the
  handbook is how somebody follows a rule that no longer exists.
- `DELETE` only works on drafts, and is for a draft that should never have
  existed.

## Who can see it

| visibility | who reads it |
|---|---|
| `internal` (default) | anyone in the workspace, no capability needed |
| `restricted` | only holders of the `required_capability` named on the row |
| `public` | intended for people outside the workspace too |

A `restricted` policy **must** name its capability (422 otherwise) — one that
names none is readable by everyone, which is the opposite of what it says. Reuse
an existing capability rather than inventing one: `payroll.read` for
a compensation policy is exactly right.

Someone else's restricted policy is a **404, not a 403** — that a compensation policy
exists at all is part of what it hides. If a person asks about a policy you
cannot see, say you cannot see it; do not speculate about its contents.

## Figures: read the body, or read `rules_json`

A policy's figures live in the policy. There is no rule table and no key
lookup — the body says tier-one cities are capped at 600 a night and you read it.

When a workspace would rather hand agents a machine shape than a paragraph, it
puts the same figures in **`rules_json`** on the policy row, in whatever
structure suits:

```json
POST /policies
{
  "code": "FIN-2026-03",
  "category": "external_standard",
  "title": "Shanghai 2026 social-insurance contribution base standards",
  "body": "Per Shanghai HR&SS circular 2026 No. X: contribution base ceiling 36921, floor 7384, in force from 2026-07-01.",
  "rules_json": {
    "social_insurance": {"base": {"cap": 36921, "floor": 7384}},
    "housing_fund": {"base": {"cap": 36921, "floor": 2690}}
  },
  "effective_from": "2026-07-01"
}
```

- **The server never parses it.** `rules_json` has no more standing than `body`
  — any shape is accepted, nothing is validated, nothing is computed from it.
- **It rides the document.** It versions, publishes and freezes with the policy,
  because it IS the policy. There is no second freeze to forget and no way for
  the numbers to disagree with the prose without somebody having written both.
- **It is optional.** A policy with only prose is complete.
- **Keep the two in step.** If you set `rules_json`, the body must say the same
  thing. You are the only thing checking that — the server cannot, and will
  not pretend to.

Getting a figure is one call:

```text
GET /policies?category=external_standard&in_force_on=2026-07-15
GET /policies?code=FIN-2026-03&in_force_on=2026-07-15
```

`in_force_on` reads across superseded versions, so asking for a date in March
returns the document that governed March — not the one on the intranet today.

**Cite what you used.** `contribution base ceiling 36921 (per FIN-2026-03 v1)` is working
shown; a number you remembered is not, and on a payslip line the difference is
the difference between a 422 and a document somebody can audit.

**Nothing in force means ask, not assume.** If no policy covers the date, say
so and ask whoever owns it to publish one. That is what this table is for.

## Recording an external standard

Social-insurance contribution limits, the minimum wage, itemised additional
tax deductions — none of these are the
company's rules, and none of them belong in the employee handbook. They still
have to be recorded, because payroll is wrong without them and because
"whose number is this, as of when" has to be answerable.

File them as a policy of `category: "external_standard"`, with the government
document's own reference in the body and the figures in `rules_json`:

```json
POST /policies
{
  "code": "FIN-2026-03",
  "category": "external_standard",
  "title": "Shanghai 2026 social-insurance contribution base standards",
  "body": "Per Shanghai HR&SS circular 2026 No. X: contribution base ceiling 36921, floor 7384, in force from 2026-07-01.",
  "rules_json": {"social_insurance": {"base": {"cap": 36921, "floor": 7384}}},
  "effective_from": "2026-07-01"
}
```

A number with no published source is exactly what the payslip guard refuses on a
deduction line. Recording the notice is how the figure gets one.

## What This Skill Never Does

- **Describe a draft as if it were in force**, or answer "what are the rules" from
  an unpublished version.
- Edit a published policy. Amend by publishing a new version; that is the only
  route, and the 409 says so.
- Delete a policy people acted on. Repeal it.
- Invent a figure no published policy states. Nothing in force on that date is
  an instruction to ask, not a licence to guess.
- Let `rules_json` and the body disagree. If you write one, write the other.
- Put company-wide **routing** here. "who approves an expense over 50,000" is a
  workflow definition; "what is the expense standard" is a policy. Both are versioned tenant text and
  they are not the same axis.
- Put **one person's** pay terms here. A salary, a commission rate or a bonus
  arrangement is a fact about that person and lives in `pay-histories`
  (`$oryh-payroll`), behind `payroll.read`.
- Apply a rule on the server's behalf. Nothing here computes; you read the
  number, you do the arithmetic, and you record how you reached it.

## Reference

- [references/api.md](references/api.md): every endpoint, the visibility matrix,
  and the guards with the exact conditions that raise them.
