---
name: oryh-skill-author
description: Use when a tenant admin's AI agent needs to turn a natural-language process requirement into tenant configuration in oryh — deciding whether it belongs in a workflow definition (policy) or a customer workflow skill (process contract), drafting a qualified SKILL.md against the tenant's real object types and capabilities, publishing it to the /skills registry, and wiring who receives it via required_capability. The admin describes the process in plain language; agents company-wide get the skill on their next sync. Requires skills.manage.
required_capability: skills.manage
---

# Oryh Skill Author

Turn the admin's plain-language process requirement into the right kind of tenant data. This skill is the compiler between "我们的报价要先解析客户发来的长短码，纠错过的必须人工确认" and a versioned, capability-gated customer workflow skill that every eligible employee's agent receives automatically.

The single most important thing you do is **classify before you write**. Tenant customization lives in three places, and putting content in the wrong one is the main failure mode:

| Layer | What belongs there | Where it lives | Changing it |
|---|---|---|---|
| **Policy** | Thresholds, routing, submission requirements, approval tiers — *rules agents interpret at use time* | Workflow definition (natural language, versioned) | Publish a new version; zero skill edits; effective immediately |
| **Process contract** | Which API calls, in what order, iron rules, reply formats, hand-offs between roles — *how an agent executes* | Customer workflow skill in the `/skills` registry | Revise the skill; agents pick it up on next sync |
| **Deterministic capability** | Pricing engines, code/OCR parsers, document templates, anything needing exactness or regression tests | A local tool the agent calls — **code, not prose** | Engineering work; a skill may *reference* the tool, never *be* it |

A requirement usually decomposes across all three. "折扣超过10%要销售总监批" is pure policy — it belongs in the workflow definition and needs **no skill at all**. "成交后必须建订单、生成SO号、追物流到签收" is a process contract — that is a skill. "按客户分级从价格矩阵取价、不得低于成本" is deterministic — tell the admin honestly that this part needs a tool built once by engineering; the skill you write will *call* it, and writing it as prose would turn exact math into LLM guesswork.

## Trigger Examples

- "我想让所有销售的 agent 都按我们的规矩报价"
- "把这个流程做成一个 skill 发给大家"
- "帮我把成交后的跟单动作固化下来"
- "改一下上次那个报价 skill，加一条规则"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # the admin's user-bound key (skills.manage)
```

Everything else comes from the conversation and from the tenant's own records.

## Steps

1. **Identity**: `GET /auth/me` — confirm `skills.manage` is present. Publishing policy instead needs `workflows.publish`; say so if that's where the requirement lands.
2. **Interview**: get the requirement in the admin's own words. Ask for: who performs it (which roles), what triggers it, what the agent must do step by step, what it must never do, and what "done" looks like. Capture verbatim phrasing for iron rules — the admin's wording is usually better than yours.
3. **Read the tenant's reality** (all read-only):
   - `GET /object-type-definitions` — which builtin and custom objects exist,
     and their **state machines** (read those: only `draft` and `submitted` are
     guaranteed names, everything else this workspace may have renamed). A
     skill may only reference objects that exist; if the process needs a new
     object type, define it first (`object_types.manage`, or walk the admin
     through the console).
     - **Fields:** `json_schema` here is the *tenant's* declaration, so it is
       populated for custom types and empty for builtins — builtins carry their
       fields in code. For a builtin, take the field list from the product skill
       that owns it (`$oryh-order-submit`'s `references/api.md` for
       `sales_order`, and so on), which is where your draft should be composing
       from anyway. Do not infer fields from one sample record; optional ones
       will be missing.
   - `GET /workflow-definitions?entity_kind=...&object_type=...` — current policy for the objects involved. Never duplicate policy into the skill.
   - `GET /skills?status=all` — the existing registry. A near-miss skill means **revise, don't fork**; the product skills (kind=product) show the house style to follow.
   - `GET /capabilities` and `GET /roles` — what gates are available and who holds them today.
4. **Classify** each part of the requirement per the three-layer table above:
   - Pure policy → **amend the workflow definition** (see "Amending A Workflow Definition" below), then stop here for that part.
   - Process contract → continue to step 5.
   - Deterministic capability → name it explicitly as a tool the company needs built, and design the skill to call it. Never inline it as prose.
5. **Draft the SKILL.md** following [references/authoring-guide.md](references/authoring-guide.md) exactly: frontmatter contract, naming, section order, iron-rule style, and the base-skill rule — a customer workflow skill *composes* the product skills (`$oryh-quotation-submit`, `$oryh-business-object`, …) and the tenant's objects; it never re-documents core API mechanics the product skills already own.
5b. **Never define a custom object for something ORYH already ships.** A
   process about products, customers, invoices, employees or projects is a
   process about the BUILT-IN ones. `GET /builtin-object-types` lists every
   shipped collection and the words that mean it.

   The server allows a colliding `object_type` — deciding what a company's word
   means is not its job — so this check is yours and it must happen before you
   write. Match on meaning, not only spelling, and when it matches, tell the
   admin which built-in it is rather than creating a second one.

6. **Choose `required_capability`** — this is the **floor**: what someone must
   be allowed to do before this skill is safe to hand them. Decide it deliberately:
   - The action is already gated by a system verb → reuse it (`quotation.submit_own`, `approval.record`).
   - The skill writes one custom object type → use the scoped verb
     (`business_object.write:sales_order`) — no bespoke capability needed. **But
     read `GET /roles` before you rely on it**: the baseline `member` role ships
     with `business_object.write:*`, and the wildcard covers every scope, so on
     a tenant that never narrowed it this gate admits the whole company. That is
     fine when the skill really is for everyone; when it is not, the gate is not
     what limits it — the audience is.
   - **Eligibility is organizational, not object-shaped → that is the AUDIENCE,
     not a capability.** Gate on the verb the work actually needs, then name the
     roles or people in step 9. Minting a capability to express "只给采购团队"
     leaves a skill gated on something nobody holds — you may not grant it
     (see *What This Skill Never Does*), so it reaches nobody. Mint a custom
     capability only when the tenant needs a genuinely new *permission* that no
     system verb expresses, and expect a separate human decision to grant it.
   - Leave it empty when the skill needs no permission the server enforces —
     read-mostly work. An empty gate does not mean "everyone gets it": a
     targeted audience narrows an ungated skill perfectly well, and the two
     choices are independent.
7. **Read back before publishing**: show the admin the complete draft — trigger description, every step, every iron rule, the gate, and who will receive it (name the roles whose grants cover the gate). Get an explicit yes.
8. **Publish**: `POST /skills` with `{name, title, description, required_capability, files: {"SKILL.md": ...}}` (multi-file skills put references under `references/`). Revisions go through `PATCH /skills/{name}` with the full updated `files` — the server bumps the version itself.
9. **Decide the audience** — see "Who The Skill Is For" below. Default is no
   audience at all (everyone the capability allows); narrowing is a separate,
   deliberate step.
10. **Distribution check**: eligible members receive it in their bundle
    automatically — on next `oryh-skill-sync`, or admin-issued via
    `POST /users/{id}/skill-bundle`. Verify with `GET /roles/{role_ref}/skills`
    rather than deriving it: it answers directly, and its `reasons` list every
    blocker. If nobody's role covers the gate, say so and name the missing
    grant (granting is `users.manage`, a separate decision). If a targeted
    skill also names people whose role cannot run it, the assignment response's
    `blocked_members` names them — they need **both** fixes, and saying only
    one sends the admin back a second time.

## Amending A Workflow Definition (Policy)

`POST /workflow-definitions` is **publish-only** — there is no `PATCH`. Every
call writes an entirely new version and marks the previous active one
`superseded`; the server never reads what you send against what was there and
merges anything for you. **`definition_text` is the complete effective
document, not a diff.** Whatever you don't include is gone from the tenant's
rules the moment this version goes active — even if the admin only asked for
one small change.

That gap between "the admin said 加一条" and "you must supply the whole
document" is the single most common way this skill causes silent data loss:
asked to add one clause, it is tempting to draft prose for just that clause
and publish it — which deletes every other submission requirement and
routing rule the tenant had, with nothing in the response to say so.
**Never do that.**

**Default behavior is amend, not rewrite:**

1. You already have the current active text from step 3's read. Start from
   it verbatim.
2. Weave the admin's requested change into it — add the new clause, adjust
   the one threshold that changed, whatever was actually asked for.
3. Carry every other clause forward **unedited**. Do not paraphrase, do not
   "clean up" wording, do not drop a rule because it looks superseded by the
   new one unless the admin said so.
4. Publish that complete document as the new version.

**Full rewrite is the exception**, only when the admin explicitly asks for
one — "这份重新写"、"以前那些不要了"、"整个换掉" and the like. Even then,
read the current text back to them before erasing someone else's policy.

**The step-7 read-back must be a diff for policy edits, not just a preview.**
Show three things side by side: what's new, what changed (old value → new
value), and — the one that catches this bug — **what would be removed**. If
that third list is non-empty and the admin never asked to remove anything,
stop and ask before publishing. A policy document that got shorter is the
symptom, not the goal.

## Who The Skill Is For (Audience)

`required_capability` answers **may you do this**. It does not answer **who is
this for**. A skill for the Shanghai procurement team and a skill for every
buyer in the company can share the same capability and still need different
audiences.

That second axis is `distribution_mode` plus the audience list:

```text
GET    /skills/{name}/assignments                  → current audience + impact
POST   /skills/{name}/assignments                  → name one more subject
DELETE /skills/{name}/assignments/{assignment_id}  → drop one
PATCH  /skills/{name}  {"distribution_mode": "targeted"}
```

**They compose as AND, and audience can only narrow.** A skill in someone's
bundle tells their agent it may do the thing; handing one to a person whose
role lacks the capability produces an agent that 403s on every call — worse
than not shipping it, because it disguises a permission gap as a system fault.
So if the admin wants someone to run a skill they are not permitted to run,
the answer is **grant the capability first** (`$oryh-access-admin`), never
"name them in the audience and hope".

**Read the impact before you commit it.** `GET .../assignments` returns:

| field | what it tells the admin |
|---|---|
| `reaches_now` | who receives it today |
| `would_reach` | who would, under the audience as it stands |
| `gaining` / `losing` | the difference |
| `blocked` | named, but their role cannot run it |

**`losing` is the one to say out loud.** Switching a skill from capability
mode to targeted takes it away from everyone left out, and nobody ever reports
a skill they quietly stopped receiving. Never flip `distribution_mode` to
`targeted` without telling the admin how many people that removes it from.

**Add and remove one subject at a time.** There is no whole-list replace, on
purpose — the same reason a workflow definition must be amended rather than
redrafted: a replace lets "add one person" turn into "keep only that person".

**`targeted` with an empty audience reaches nobody.** That is a real state,
not a fallback to everyone — emptying an audience narrows.

## Iron Rules

- **Never invent an endpoint, object type, field, or capability.** Everything the skill references must exist in step 3's reads, or be created first through its own proper path.
- **Never inline policy.** Thresholds and routing live in the workflow definition; the skill says "read the definition and apply it", never "the limit is 5000".
- **Never use the audience to work around a missing capability.** Audience narrows what the capability already permits; it cannot grant. Someone named but unpermitted simply never receives the skill.
- **Never inline determinism.** If a step needs exact computation or exact parsing, the skill names the tool and its contract; prose that "explains the algorithm" to an LLM is a bug, not a feature.
- **Never publish without the step-7 read-back.**
- **Editing a product skill's FILES forks it to custom** (the catalog stops updating it) — warn the admin and prefer a separate customer skill that composes it. Metadata edits do NOT fork, and the gate and archival are the tenant's to keep: a changed `required_capability` and an archived `status` survive catalog syncs (content still updates underneath). The response's `catalog_required_capability` shows the shipped default — set the gate back to it to resume tracking the catalog. `description` rides the SKILL.md content, so it follows catalog updates.
- One skill, one role's job. If the draft contains "提交人做A，审批人做B，流程管理做C", split it — that is the submit/approve/flow pattern the product skills model.
- **The inverse holds too — don't over-split.** One role's multi-phase process (询价→报价→成交→物流 for the same salesperson) is ONE skill: SKILL.md as the trigger + phase router, `references/<phase>.md` for the detail agents load on demand. And a new object type is NEVER by itself a reason for a new skill — `$oryh-business-object` already covers any custom type by reading its definitions at use time; write a dedicated skill only when the process exceeds that (dirty-input gates, fixed customer-facing 话术, cross-object rituals). Every skill you publish is a permanent line in someone's bundle — make it earn the slot.

## What This Skill Never Does

- Grant capabilities or change roles (`users.manage` — a human/console decision it may only recommend).
- Build the deterministic tools it identifies.
- Modify another tenant's skills (impossible by construction — the registry is tenant-scoped).
- Publish policy as a skill or a skill as policy.

## Reference

- [references/authoring-guide.md](references/authoring-guide.md): the authoring standard — anatomy, naming, gating, worked example.
- [references/api.md](references/api.md): request templates.
