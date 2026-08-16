# Customer Workflow Skill Authoring Guide

The standard a drafted skill must meet before publishing. The product skills in the registry (kind=product) are the reference implementations of this style — read one before writing.

## Anatomy

A skill is a `files` map. Minimum: one `SKILL.md`. Larger skills add `references/*.md` (request templates, worked examples) — keep SKILL.md the contract and references the detail.

```markdown
---
name: <kebab-case, tenant-conventional prefix, e.g. jc-quote>
description: Use when <whose agent> needs to <do what> — <trigger phrases>. <What it records/produces>. Requires <capability>; <what belongs to other roles>.
required_capability: <gate or omit>
---

# <Title>

<2-5 sentences: the job, and the one design idea that makes this skill safe.>

## Trigger Examples
- "<the admin's own phrasing>" (3-5 items)

## Required Inputs
```yaml
oryh:
  base_url: "{{ORYH_BASE_URL}}"
  api_key: "{{ORYH_API_KEY}}"
```

## Steps
1. numbered, each step naming its exact API call or the base skill it defers to

## <Domain rules section — iron rules in the admin's wording>

## What This Skill Never Does
- the negative space: role boundaries, forbidden writes
```

## The description is the trigger contract

Agents choose skills by name + description alone. The description must open with "Use when …", name the acting role, contain the natural trigger phrases users actually say (Chinese phrases verbatim if that's how they talk), and close with the capability + what belongs to other roles. One long sentence-paragraph, not bullets.

## Naming

- `<tenant-prefix>-<domain>-<action>`: `jc-quote`, `sb-quote`. Prefix is the tenant's own convention — never `oryh-` (reserved for the product catalog).
- Bundles render tenant scoping automatically; keep registry names canonical.

## Composing, not re-documenting

A customer workflow skill sits **on top of** the product skills:

- Creating/submitting builtin objects → defer to `$oryh-quotation-submit`, `$oryh-purchase-submit`, … ("create and submit per the $oryh-quotation-submit contract; this skill only states the house rules").
- Custom objects → defer to `$oryh-business-object` for mechanics (full-payload PATCH, no status advancing) and state only your object's fields and rules.
- Approval facts → `$oryh-approve` (one skill, every document type) / `approval.record` conventions; one fact + own todo, never status writes.
- Check-in/queues → `$oryh-my-work`.

Re-explaining core API mechanics inside a customer skill is a defect: it drifts when the product updates.

## required_capability selection

| Situation | Gate |
|---|---|
| Skill drives a builtin family's own-record lifecycle | that family's system verb (`quotation.submit_own`) |
| Skill writes one custom object type | scoped verb: `business_object.write:<type>` |
| Skill records approval facts | `approval.record` |
| Eligibility is organizational (outside vendors, back-office staff) | custom capability (create via `POST /capabilities`, grant via roles) |
| Read-mostly, everyone | omit |

The gate is also the **distribution rule**: holding the skill always implies permission to execute it. Check `GET /roles` to see who will actually receive it, and say so at read-back.

## Policy stays out

Any number, threshold, named approver, or routing rule belongs in the workflow definition. The skill's job is to *point* at it:

> **Wrong (in a skill):** "a discount below 80% needs the general manager to countersign"
> **Right (in a skill):** "before submitting, read `GET /workflow-definitions?entity_kind=builtin&object_type=sales_quotation` and apply its submission requirements to the conversation"
> **Right (in the workflow definition):** "for a discount below 80%, the sales manager approves and the general manager countersigns"

This is why tenants can retune the process without touching any skill.

## Determinism stays out

If a step needs exact results — price lookups, model-code parsing with correction guarantees, document rendering — the skill declares a **tool contract** and stops there:

> "call the local pricing tool `price(customer, sku, qty)` for the tax-inclusive and list prices; this skill never works a price out in its head, and stops and says so plainly when the tool is unavailable."

Signs you are inlining determinism (stop and extract a tool): tables of prices, regex-like format rules the agent must "apply carefully", multi-step arithmetic, anything with a regression test in its history.

## Granularity: split by role, merge by arc, never by object

The unit of a skill is **one role's coherent job**, not a phase and not an object type:

- **Split across roles** (the submit / approve / flow pattern): if the process has an approval loop, model it as up to three skills, mirroring the product families —
  - **submit**: the actor's own facts, own lifecycle endpoints only
  - **approve**: one approval fact + complete own todo, never status
  - **flow**: the service-credential loop — queue → trail → workflow definition → next todo or final status

  Small processes may only need submit (the flow agent's generic loop covers the rest).
- **Merge within a role**: the same person's consecutive phases (parsing an enquiry → quoting → winning → tracking logistics) belong in ONE skill. Keep SKILL.md a trigger + phase-router (a "which reference do I load" table), and put each phase's detail in `references/<phase>.md` — agents hold one bundle line and load only the phase the conversation is in.
- **Never one-skill-per-object-type**: `$oryh-business-object` already handles any custom type by reading the tenant's object-type definition and workflow definition at use time. Ten new object types should add zero new skills. A dedicated customer skill is earned only by process that exceeds those definitions — correction-confirm gates, fixed customer-facing wording, cross-object rituals.

Bundle-size sanity check before publishing: an ordinary member should end up holding **well under ten** skills. If your draft pushes past that, you are splitting by phase or by object — merge.

## Revision protocol

- `PATCH /skills/{name}` with the **complete** `files` map (it replaces wholesale); the server bumps `version` when content changed.
- Never revise by publishing `-v2` names; one name, versioned.
- Archive (`DELETE /skills/{name}`) only when a skill is superseded by a different decomposition; say which skill replaces it in the survivor's description.

## Worked example (condensed)

Requirement (admin's words): "model numbers customers send over chat are often mistyped. The agent must resolve them against the product catalog first, and anything it corrected must be confirmed by the salesperson before a quotation goes out; quoting itself follows the standard flow."

Classification: parsing exactness → **tool** (catalog matcher); confirmation before a quotation goes out → **process contract** (skill); discount authority → already in the sales_quotation workflow definition → **policy, untouched**.

Resulting skill (skeleton — note the granularity rule in action: this is the salesperson's ONE deal skill; intake is a reference, not its own skill, leaving room for follow-up phases later):

```markdown
---
name: acme-quote
description: Use when a salesperson's AI agent works a customer deal at any stage — an enquiry pasted from chat or a screenshot, quoting, following up — 询价、报价、跟进, "帮XX报价", "这个型号多少钱". Resolves codes read-only with a correction-confirm gate, then quotes via oryh-quotation-submit. Requires quotation.submit_own.
required_capability: quotation.submit_own
---
# Acme Quote

| Where the conversation is | Which reference to load |
|---|---|
| An enquiry arrives; codes need resolving and a quotation producing | references/intake.md |

## What This Skill Never Does
- Quote a corrected line without confirmation; invent codes; touch prices by hand.
```

`references/intake.md` carries the detail:

```markdown
1. `GET /products?keyword=` / `GET /product-skus?...` — read-only resolve; uncertain → ask, never guess.
2. Any line whose code needed correction → list the original against the correction side by side, wait for explicit confirmation. No confirmation, no quote.
3. Hand the clean lines to `$oryh-quotation-submit` (it owns pricing snapshots, read-back, submission).
```

Publish with `POST /skills`; sales roles holding `quotation.submit_own` receive it on next sync. When the admin later adds deal-close and logistics rules, they become `references/follow-up.md` inside this same skill — the bundle line count stays at one.
