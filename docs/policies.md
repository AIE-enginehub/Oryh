# Company rules: a published rule of the house

One table. `policies` is the document — versioned, published by a named person,
visible to whoever it says, and carrying its own figures.

## What was copied from OFBiz, and what was refused

**The document half** is `Content` + `DataResource` + `ContentRevision` +
`ContentApproval`. Between them they carry a `contentTypeId`, a `statusId`, a
`privilegeEnumId`, a `createdByUserLogin`, a revision sequence with a
`committedByPartyId`, an approval with a `partyId` and an `approvalDate` — and,
on `DataResource`, an `isPublic` flag. That is the entire feature list of "a
policy with a version, a publisher and a visibility."

What was left behind is the CMS around it: `decoratorContentId`,
`instanceOfContentId`, `childLeafCount`, `localeString`, and a `DataResource`
indirection that costs four joins to read one paragraph. `policies` keeps the
shape and puts the body in a column.

`isPublic` became three-valued. An employee handbook (everyone here), a
compensation policy (management only) and a service commitment (customers too)
are three different answers, and
a boolean holds two.

### The term table was built, then removed

OFBiz's other half is `Agreement` + `AgreementTerm`, where every figure gets a
row: `termValue` / `textValue` / `minQuantity` / `maxQuantity`, effective-dated
independently of the agreement. That shape was implemented here as
`policy_rules`, with a key namespace and a `resolve?key=…&on=…` lookup, and then
deleted before it shipped. The reason it went is worth more than the table was.

**A term table exists because traditional software cannot read a policy.** It
has to be told, in fields, that the tier-one city lodging cap is 600, because its consumer
parses columns and not paragraphs. The consumer here is an agent that reads the
paragraph. So the table bought nothing — and cost the one thing that actually
matters: **a second source of truth for the same rule.** The body would say
600, the row would say `travel.hotel.cap.tier1 = 600`, and nothing in the
schema could notice when they stopped agreeing.

Two smaller tells pointed the same way. The key had to carry the dimensions
(`travel.hotel.cap.tier1`) with a rule that `scope_json` "documents but never
disambiguates" — inventing a namespace to hold what prose holds for free. And
the argument that a rule needs dating independent of the document (the
contribution base changes every July while the compensation policy does not)
only bites if the government figure is crammed into the compensation policy,
which it should not be: it has its own
`external_standard` policy row, and a new notice is a new version of that.

So the figures ride the document, in **`rules_json`** — a free-shape object the
server never parses, versioned and published and frozen with the body it
restates, because it IS the body. And what is deliberately not copied from
`Agreement` at all is `partyIdFrom` / `partyIdTo` / `roleTypeId`: an agreement
is negotiated between two parties, a company policy is published by one.

**The cost, stated plainly:** changing one figure now means publishing a new
version of the policy that contains it, rather than closing a single row. That
is how policy documents actually work, and it is what keeps the version history
from lying about what changed.

## This is not `workflow_definitions`

Both are versioned tenant prose read by agents, and merging them would be the
easy mistake. They are different axes:

| | `workflow_definitions` | `policies` |
|---|---|---|
| answers | how does THIS KIND OF DOCUMENT route | what are the company's rules |
| keyed to | an `object_type` | nothing |
| read by | the flow agent | everyone, and every agent |
| gated | no | visibility + capability |

"Who approves an expense over 50,000" is a workflow definition. "What is the
expense standard" is a policy.
They travel together and they are not the same thing.

## Status is a marker; the dates are the truth

`status = 'published'` means "the current version of this code", and a partial
unique index holds one per code. What actually applied in March is answered by
`effective_from` / `effective_thru` across every non-draft version —
`GET /policies?in_force_on=2026-03-15`.

This is the same stance settlement takes, where `paid` is a flow marker and
`outstanding_amount` is the fact. A v1 that reads `superseded` today is still
the document that governed March, and answering "what were the rules then" from
the current version is the error the effective dates exist to prevent.

Publishing performs the handover in one transaction: the previous version's
`effective_thru` lands the day before the new one starts, and the response
returns both. That is the same shape `POST /pay-histories` uses for a raise, for
the same reason — as two calls they eventually drift, and a policy history with
a gap in it cannot answer what applied in March.

One implementation note worth keeping: the supersede is flushed **before** the
new version is promoted. SQLAlchemy's unit of work orders UPDATEs by its own
bookkeeping, not by assignment order, so without the flush the new version can
reach `published` while the old one still is — and the partial unique index
refuses, correctly, in the middle of an entirely legal handover.

## The read gate

The second gated read in this API, after pay, and it has to fail in two
directions at once:

- an **internal** policy is readable by anyone here, with no capability at all.
  A handbook nobody may open is not a handbook, and a gate that got this wrong
  by being cautious would be as broken as one that leaked.
- a **restricted** policy is readable only by holders of the capability the row
  names. It reuses the existing scopable `verb:scope` grammar rather than
  inventing a second permission vocabulary, so a compensation policy can simply say
  `payroll.read`.
- a **draft** is readable only by its authors. This is the one that gets
  forgotten: a draft reorganisation plan says what is coming before anyone has
  decided, and it is more dangerous than the published version.
- a **repealed** policy likewise leaves the handbook. Leaving it visible is how
  somebody follows a rule that no longer applies.

| | draft | published `internal` | published `restricted` | repealed |
|---|---|---|---|---|
| `policy.manage` / `policy.publish` | ✓ | ✓ | ✓ | ✓ |
| the row's `required_capability` | — | ✓ | ✓ | — |
| any other credential | — | ✓ | — | — |

Single fetches return **404, not 403**: that a compensation policy exists at all is part
of what it hides.

## What publication freezes, and what it does not

Publication freezes what the rule SAYS. That is what lets the handbook answer
"what were people told in March", and it is why a published policy is amended
by publishing a new version rather than edited in place.

It does not freeze **who may read it**, and for a while it did, which left the
worst case with no remedy at all. A policy published to a wider audience than
intended could not be edited (409), could not be deleted (published policies
never are), and repealing it would retire a rule that is still in force — so
the only way to stop people reading it was to stop applying it. That is not a
choice a workspace should have to make about its own handbook.

```text
POST /policies/{policy_id}/visibility
{"visibility": "restricted", "required_capability": "payroll.read", "note": "published company-wide by mistake"}
```

Any status, including `superseded` and `repealed` — and it matters most there,
since an old version stays readable to whoever could read it, so one that
should never have been broadly visible has to be closable after the fact. It
touches `visibility` and `required_capability` and nothing else: a call that
could move a word of the body would be the in-place edit the freeze exists to
prevent, wearing a different name.

It needs `policy.publish`, not `policy.manage`. Deciding who in the company may
read a published rule is the authority act that drafting is deliberately kept
apart from — the same line publish and repeal already draw. And it is audited
as `policy.visibility_changed`, with the before and after, because a change to
who can read the rules is exactly the kind of decision a trail is for.

Two facts, one date each: what the rule said on a date, and who could read it
at a time. Conflating them cost the second one.

The whole gate is a SQL predicate rather than a post-filter, which matters more
than it looks. Filtering rows after the query would leave `total` counting
documents the caller cannot see — and how many restricted policies a workspace
has is itself worth hiding. Since a row's `required_capability` is decided in
Python (`has_permission` knows about scopes and bypasses) the predicate is built
from the DISTINCT capability strings actually in use — a handful of rows, tested
once, then an `IN` clause. Exact, and paginable.

`rules_json` rides the policy row, so the figures need no gate of their own —
and a restricted compensation policy cannot be read one number at a time, which a
separate rule table would have offered as a side door.

## `rules_json`: the same rules, in a machine shape

```json
{
  "body": "Per Shanghai HR&SS circular 2026 No. X: ceiling 36921, floor 7384.",
  "rules_json": {"social_insurance": {"base": {"cap": 36921, "floor": 7384}}}
}
```

Optional, free in shape, and **never interpreted by the server** — it has no
more standing than `body` does, and no more than a workflow definition or a
`pay_histories.formula`. Nothing validates it, nothing computes from it, and no
endpoint looks a key up inside it.

What it buys is determinism for the agent: reading `{"cap": 36921}` cannot be
misread the way a sentence can. What it costs is that somebody has to keep it in
step with the prose — and that cost is honest, because it is one author writing
one document, not two systems drifting apart.

Three properties come free from living on the policy row rather than in a table:

| | why |
|---|---|
| versioned with the document | a figure change IS a document change; the version history says so |
| frozen with the document | the published-policy guard covers it — no second freeze to forget |
| gated with the document | no way to read a restricted compensation policy one number at a time |

Reading a figure is an ordinary policy read:
`GET /policies?code=FIN-2026-03&in_force_on=2026-07-15`. `in_force_on` reads
across superseded versions, so a date in March returns the document that
governed March — figures included.

## What this changes for payroll — and what it does not

The payroll simulation surfaced the gap this table closes. The agent had to
print:

> ⚠ Not confident: social-insurance contribution base 7384 — 36921. That is the
> 2024 basis, and this is July 2026 payroll. A real agent should stop and ask HR.

and then write "pending HR review against this year's circular" into every
deduction line's `notes`.

Now HR records the year's standard once, as an `external_standard` policy, and
the agent calls:

```text
GET /policies?category=external_standard&in_force_on=2026-07-15
```

which returns the document, its version, its publisher and its figures. The
payslip line's working becomes `contribution base 36921 × 8% = 2953.68 (per FIN-2026-03
v1)` — a figure somebody can audit rather than one the agent remembered.

**The server still computes nothing.** Storing a rule is not applying a rule.
The agent reads, the agent computes, the agent records its working. What changed
is that the input now has a publisher and a date instead of living in the
agent's memory — a change in provenance, not in who does the arithmetic.

Nothing in force on that date is an instruction to ask, not a reason to guess.
That is the whole point of routing the figure through a published document.

## What the integrity audit asserts

- one published version per policy code
- a published policy names who published it and when
- a restricted policy names the capability that may read it
- no policy stops applying before it starts
- a version chain points backwards, at the same code, in the same tenant
- **only the newest version of a code is ever repealed** — repealing a
  superseded one would move an `effective_thru` the handover already set, and
  publish-v2-from-July then repeal-v1-as-of-March leaves April through June
  governed by nothing at all. The gap itself is not checkable portably (SQLite
  reads `'2026-06-30' + 1` as numeric addition), so the audit asserts the cause
  instead of the symptom

There is nothing to assert about `rules_json`. The server does not parse it, so
it cannot meaningfully audit it — which is the same reason it cannot audit a
workflow definition or a `formula`, and the same trade the whole system makes.

Advisory, not a violation: policies drafted long ago and never published.
