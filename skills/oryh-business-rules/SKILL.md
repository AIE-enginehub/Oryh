---
name: oryh-business-rules
description: Use to write, publish, amend, re-scope or repeal any of the workspace's own rules — a company policy (员工手册、报销制度、薪酬管理办法) or an external standard (社保缴费基数、最低工资), who approves what (an approval flow), what a document must carry when filed (a data rule), what happens elsewhere when it reaches a state (a linkage) — and to split a pre-2026-10 workflow definition into its kinds. Also when an agent needs a figure a policy sets, with its version and publisher. Not for one person's pay (oryh-payroll) or for writing a skill (oryh-skill-author).
required_capability: policy.manage
---

# Oryh Business Rules

The workspace's own rules: draft → publish → amend → repeal, four kinds in
one table.

| `kind` | answers | keyed by | who drafts / publishes |
|---|---|---|---|
| `policy` | what are the company's rules — handbook, expense standard, a government figure | its own `code` (`HR-001`) and a `category` | `policy.manage` / `policy.publish` |
| `approval_flow` | who looks at a submitted document next, and when it is final | `entity_kind` + `object_type` (+ `name`) | `workflows.publish` does both |
| `data_rule` | what a document must carry to be filed at all | the same scope | `workflows.publish` |
| `linkage` | what happens elsewhere when a document reaches a state | the same scope | `workflows.publish` |

Three ideas run through everything here:

- **A rule is published, not saved.** Drafting and publishing are separate
  calls, because publishing is an authority act. A published rule is never
  edited in place — it is amended by publishing the next version, which closes
  the previous one the day before. What people were told, and until when, stays
  answerable.
- **A figure an agent applies must be traceable to a document, a version and a
  person.** You get that by reading the rule and citing its `code` and
  `version`. There is deliberately no separate table of extracted numbers:
  that shape exists because traditional software cannot read a policy, and it
  would only be a second source of truth free to drift from the prose. **You
  can read the prose.**
- **A rule is one question's answer.** Who approves is not what a document must
  carry, and neither is what happens next door when it is approved. One
  document that answered all three is how a submit agent came to read routing
  it had no business seeing, and how "add one requirement" replaced a whole
  routing map. Each kind is its own row, with its own history.

{{include:_common/answer-the-question.md}}

{{include:_common/confirm-before-you-write.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/business-rules.md}}

## Trigger Examples

- "Publish the employee handbook"
- "The lodging standard changed — 700 for tier-one cities"
- "What are this year's social-insurance contribution limits in Shanghai?"
  ← read the standard in force, cite it
- "The compensation policy is for directors and above only"
- "Repeal the old expense policy"
- "claims over 5000 also go to finance" ← the next version of the expense `approval_flow`
- "every timesheet line names a project code" ← the timesheet `data_rule`
- "a confirmed order is picked before it ships" ← the sales-order `linkage`
- "Split our old expense workflow definition into its parts"

## Required Inputs

```yaml
oryh:
<!-- only: bundle -->
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
<!-- /only -->
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
<!-- only: bundle -->
  api_key: "{{ORYH_API_KEY}}"     # policy.manage to draft a policy; policy.publish to publish,
<!-- /only -->
                                  # repeal, or change who may read one; workflows.publish for
                                  # the three scoped kinds (draft and publish alike)
  employee_id: "{{EMPLOYEE_ID}}"  # the officer recorded as a rule's owner, if any
```

Drafting and publishing a policy are separate grants on purpose. If your key
holds only `policy.manage`, prepare the draft and say plainly that somebody
with `policy.publish` has to release it — do not describe an unpublished draft
as if it were in force. The three scoped kinds take `workflows.publish` for
both acts: publishing a routing rule is the same decision as writing one.
Without it, say so and hand off to the administrator; do not try the policy
grants on an approval flow.

## The scoped kinds: approval flows, data rules, linkages

One call drafts and publishes the next version, closing the previous one in
the same transaction:

```json
POST /business-rules/publish
{
  "kind": "approval_flow",
  "entity_kind": "builtin",
  "object_type": "expense_claim",
  "body": "The line manager approves; over 5000 finance reviews as well; approved once finance passes it.",
  "note": "finance review above 5000, per the October management meeting"
}
```

- `code` is generated from the scope — `approval_flow:builtin:expense_claim:default`
  — and is the identity every version of this rule shares. Never send one;
  a `category` is refused too, since the kind is the classification.
- `entity_kind` is `builtin` for a shipped family and `business_object` for a
  type the workspace defined; the server refuses a type it has never seen
  (422 naming what it knows). `name` is `default` unless the workspace keeps a
  second rule for the same type (a fast lane for small amounts).
- The response is `{"current": ..., "superseded": ...}`; read
  `superseded.effective_thru` to confirm the handover landed where you meant.
- Two calls when the text needs a reviewer first: `POST /business-rules` with
  the same fields lands a **draft** that only `workflows.publish` holders can
  see; `POST /business-rules/{rule_id}/publish` releases it. A draft that
  should never have existed is `DELETE`d; a published rule never is.
- Publishing an `approval_flow` is the one thing the server does with a rule:
  it lifts a parked hosted-driving subscription for that family. It still reads
  no sentence of it — what the words mean is the flow agent's work.

**Write each kind for its reader.** An `approval_flow` is read by the flow
agent only — nodes, thresholds, who is final, whether to notify. A `data_rule`
is read by the submitter's agent while filling and by the flow agent once
before the first assignment — conditions a document must meet, in words that
can be checked against the record's fields. A `linkage` is read when a state
is reached — "picked before shipping once confirmed", "a payment todo for finance
once approved", "invoiced once signed" — one sentence per consequence, naming the state it hangs on.
A sentence in the wrong kind is read by the wrong agent or by nobody.

### Amending is amend, not rewrite

Every publish replaces the whole text of that rule. Asked to "add one more", start
from the version in force — `GET
/business-rules?kind=approval_flow&entity_kind=builtin&object_type=expense_claim&status=published`
— weave the change into it, carry every other sentence forward unedited, and
publish the complete text. Before publishing, read back **what is new, what
changed, and what would be removed**; if the third list is not empty and the
person did not ask to remove anything, stop and ask. A rule that got shorter is
the symptom, not the goal. A full rewrite is the exception, only when asked for
in those words — and even then read the current text back first.

### Splitting a definition published before the kinds existed

A workspace that published before 2026-10 has one `approval_flow` per family
whose text also carries a "submission requirements" section (its heading
may be in the workspace's own language), and
sometimes a sentence about what happens after approval. Until it is split, the
submit agents read only that section and the flow agent reads the rest, which
works but leaves one document answering three questions. To split it:

1. Read the published `approval_flow` and read it back to the person, sorted
   into the three questions. Nothing moves without their yes.
2. Publish the `data_rule` with the submission-requirements sentences, verbatim.
3. Publish the `linkage` with the after-state sentences, if any.
4. Publish the next version of the `approval_flow` **without** those sentences
   — the routing only. Read back the removal list: it must equal exactly what
   steps 2 and 3 published.

That order matters: a submit agent that reads the data rule before it exists
falls back to the old section, and one that reads it after step 4 finds it.

### Seeded drafts

Provisioning seeds a DRAFT of each kind for every shipped family (`origin:
"catalog"`), so an administrator starts from a text and not from nothing:

```text
GET /business-rules?status=draft&origin=catalog
```

Read it back, change the sentences that are not this workspace's, and publish
— never publish a seeded draft unread, and never draft from a blank page while
one exists. A seeded draft the workspace has not touched follows the catalog
on the next deploy; one that was edited or published is the workspace's own
and is never touched again.

## Policies: drafting and publishing

```json
POST /business-rules
{
  "kind": "policy",
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
  parses an approval flow.

```json
POST /business-rules/{rule_id}/publish
{"effective_from": "2026-09-01", "note": "approved at the August 2026 management meeting"}
```

The response is `{"current": ..., "superseded": ...}`. Publishing closes the
previous version's `effective_thru` at the day before this one starts, in one
transaction — read `superseded.effective_thru` to confirm the handover landed
where you meant. A policy approved today and applying next month is the
ordinary case, not an exception.

**Status is a marker; the dates are the truth.** `published` means "the current
version of this code". What applied in March is
`GET /business-rules?kind=policy&in_force_on=2026-03-15`, which reads across
superseded versions too. Never answer "what were the rules then" from the
current version.

## Amending, re-scoping and repealing — every kind

- **Amending** = draft a new version of the same `code` (a policy) or publish
  the next version of the same scope (the other kinds), then publish. Never
  `PATCH` a published rule — that is a 409, and it would change what people
  were told without leaving a trace that they were told something else.
- **`PATCH`** is for fixing a draft before it goes out.
- **Changing who can see it** = `POST /business-rules/{rule_id}/visibility`
  with the new `visibility` and, for `restricted`, the `required_capability`
  that may read it. This is the one thing about a published rule that is NOT
  frozen, and deliberately: what the rule says was stated on a date, but who
  may read it is a standing decision that changes when the company does — a
  rule announced to management that later goes company-wide, or one published
  wider than intended. An `approval_flow` that names individual approvers may
  be `restricted` the same way.

  **Do not publish a new version to fix an audience.** A v2 whose only
  difference is who can read it puts a second document in the history that says
  the same thing, and the over-visible v1 stays readable as the superseded
  version anyway — so it does not even work. Re-scope the version itself; it
  works on `superseded` and `repealed` ones too, which is where it matters most.

  Needs the kind's publishing grant, and it is audited with the before and
  after. It changes visibility only — the body, the figures and the dates are
  untouched.
- **Repealing** = `POST /business-rules/{rule_id}/repeal` with the date it stops
  applying. It is not deleted — people acted on it. A repealed rule leaves the
  default list (a repealed rule left in the handbook is how somebody follows a
  rule that no longer exists) but stays readable by id and by `in_force_on`, to
  whoever could read it when it governed. Repealing an `approval_flow` stops
  the hosted driver for that family at the next run: say so before doing it.
- `DELETE` only works on drafts, and is for a draft that should never have
  existed.

## Who can see it

| visibility | who reads it |
|---|---|
| `internal` (default) | anyone in the workspace, no capability needed |
| `restricted` | only holders of the `required_capability` named on the row |
| `public` | intended for people outside the workspace too |

A `restricted` rule **must** name its capability (422 otherwise) — one that
names none is readable by everyone, which is the opposite of what it says. Reuse
an existing capability rather than inventing one: `payroll.read` for
a compensation policy is exactly right.

Someone else's restricted rule is a **404, not a 403** — that a compensation policy
exists at all is part of what it hides. If a person asks about a rule you
cannot see, say you cannot see it; do not speculate about its contents.

## Figures: read the body, or read `rules_json`

A policy's figures live in the policy. There is no rule table and no key
lookup — the body says tier-one cities are capped at 600 a night and you read it.

When a workspace would rather hand agents a machine shape than a paragraph, it
puts the same figures in **`rules_json`** on the row, in whatever structure
suits:

```json
POST /business-rules
{
  "kind": "policy",
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
- **It rides the document.** It versions, publishes and freezes with the rule,
  because it IS the rule. There is no second freeze to forget and no way for
  the numbers to disagree with the prose without somebody having written both.
- **It is optional.** A rule with only prose is complete.
- **Keep the two in step.** If you set `rules_json`, the body must say the same
  thing. You are the only thing checking that — the server cannot, and will
  not pretend to.

Getting a figure is one call:

```text
GET /business-rules?kind=policy&category=external_standard&in_force_on=2026-07-15
GET /business-rules?code=FIN-2026-03&in_force_on=2026-07-15
```

`in_force_on` reads across superseded versions, so asking for a date in March
returns the document that governed March — not the one on the intranet today.

**Cite what you used.** `contribution base ceiling 36921 (per FIN-2026-03 v1)` is working
shown; a number you remembered is not, and on a payslip line the difference is
the difference between a 422 and a document somebody can audit.

**Nothing in force means ask, not assume.** If no rule covers the date, say
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
POST /business-rules
{
  "kind": "policy",
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
  an unpublished version — a seeded draft included.
- Edit a published rule. Amend by publishing a new version; that is the only
  route, and the 409 says so.
- Delete a rule people acted on. Repeal it.
- Publish a shorter version of a rule without reading back what it removes.
- Put a sentence in the wrong kind: routing in a data rule, a filing condition
  in an approval flow, a consequence in a policy. The reader of each kind is
  fixed; the sentence goes where its reader looks.
- Invent a figure no published policy states. Nothing in force on that date is
  an instruction to ask, not a licence to guess.
- Let `rules_json` and the body disagree. If you write one, write the other.
- Put **one person's** pay terms here. A salary, a commission rate or a bonus
  arrangement is a fact about that person and lives in `pay-histories`
  (`$oryh-payroll`), behind `payroll.read`.
- Write a skill. "Our quotes must first resolve the customer's codes" is a
  process contract — `$oryh-skill-author`; the threshold inside it is a rule
  here.
- Apply a rule on the server's behalf. Nothing here computes; you read the
  number, you do the arithmetic, and you record how you reached it.

## Reference

- [references/api.md](references/api.md): every endpoint, the kinds and their
  filters, the visibility matrix, and the guards with the exact conditions that
  raise them.
