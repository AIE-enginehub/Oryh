---
name: oryh-workspace-setup
description: Use when a tenant administrator's AI agent should introduce a NEW workspace and guide its initialization ("刚开通,从哪开始？"、"帮我初始化"、"系统怎么用起来"、"我们要启用哪些模块"、"给我做个开通向导"), or audit where setup stands later ("我们还缺什么配置"). Reads the derived setup report, interviews the admin about what the company does, then orchestrates the real work through the owning skills — people and roles, master data import, workflow definitions, state vocabulary — verifying every step by re-reading the report. Requires users.manage.
required_capability: users.manage
---

# Oryh Workspace Setup

The new administrator's wizard — as a conversation, not a form. One read
tells you where the workspace stands; everything else is interviewing the
person, handing each piece of real work to the skill that owns it, and
verifying afterwards. There is no wizard state anywhere: **the workspace is
the state**, the report derives it fresh on every call, and work done
outside this conversation — by anyone, in any order — shows as done.

## Trigger Examples

- "We just got this workspace — where do we start?"
- "Walk me through setting up oryh for our company"
- "What's still missing before the team can use this?"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"            # the administrator's key
```

## Steps

{{include:_common/answer-the-question.md}}

{{include:_common/read-before-you-decide.md}}

1. **Read before you speak**: `GET /workspace/setup-report` — every area
   with its status, facts and next act — plus `GET /tenant` (the room's
   name) and `GET /capabilities` (the vocabulary you will explain things
   in). Introduce the workspace from THESE facts, in the person's language:
   what is already alive, what is untouched, what the numbers say. Never
   recite a feature list; a workspace with three products and no people has
   a different first sentence than an empty one.
2. **Interview, then prioritize**: ask what the company actually does —
   trade, manufacture, services, e-commerce, some mix — and how money and
   goods move. Map their answers onto the report's areas and propose an
   order. **Whether an area is "not used" is the administrator's judgment
   and it lives in YOUR context, nowhere else**: oryh deliberately stores no
   module switches and no declared-off registry, so remember what they told
   you, stop proposing what they declined, and expect `untouched` in the
   report to keep meaning only "no data yet".
3. **The natural order** (each step is a HANDOFF to the owning skill — this
   one orchestrates and verifies, it never re-teaches):
   1. *People and access*: invite users, create employees and link them,
      shape roles around real desks — $oryh-access-admin. The report's
      `organization.facts` show the gaps, including
      `capabilities_reaching_nobody` — a feature only the admin can touch is
      a feature nobody has.
   2. *Master data*: products / customers / vendors from their spreadsheets
      — $oryh-master-data. Selling through platforms? The external product
      map lives there too.
   3. *Workflow definitions*: for each family the company will run, publish
      the tenant's own rules in their own words —
      `POST /workflow-definitions` with plain natural-language
      `definition_text` ("expenses: direct manager approves; above 5000 add finance"). This is the map
      every flow agent reads; a family without one stalls at "todo for the
      admin".
   4. *State vocabulary*, only where their words differ from the defaults:
      one sentence renames any machine's states
      (`GET /object-type-definitions` → PATCH the `state_machine` with a
      `roles` map). E-commerce order states, return flows, invoice wording —
      all the same mechanism.
   5. *The standing one-sentence policies*, mentioned so the admin knows
      they exist: reimbursement mode (invoice or direct settle), where
      returned goods land, calibration lines on any skill. Each is a
      sentence in a definition or a calibration — never a config screen.
4. **Verify every step by re-reading the report** — never by memory, never
   by assuming a handoff finished. `partial` with facts tells you exactly
   what is still missing; read it back to the person as progress, not as
   nagging.
5. **Offer a walkthrough at the end** (the admin decides): one clearly
   marked sample document through one activated flow — submit, watch the
   flow agent route it, approve, archive it after. Proof beats assertion;
   but it writes into the real workspace, so offer, never assume.
6. **Leaving is fine**: any later session starts at step 1 and continues
   from wherever reality stands. Nothing depends on this conversation
   surviving.

## What This Skill Never Does

- Store setup progress, module decisions, or "done" marks anywhere in oryh —
  the report derives, your context remembers, and that is the whole design.
- Invent master data, guess vocabulary, or publish a workflow definition the
  admin did not phrase — the definitions are THEIR words.
- Grant a capability without naming who gets it and why, or touch role
  grants itself — that is $oryh-access-admin's work with its own guardrails.
- Mark an area complete by assertion. The report says, or it is not so.

## Reference

- [references/api.md](references/api.md): the report's shape and the reads
  this skill makes; all writes belong to the skills it hands off to.
