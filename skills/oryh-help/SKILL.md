---
name: oryh-help
description: Use when someone asks a question ABOUT oryh itself rather than asking for work to be done — "oryh 能不能…"、"这个权限是什么意思"、"给他建客户的权限是不是要给 admin"、"为什么我被 403"、"自定义对象和内置对象有什么区别"、"哪个 skill 负责…". Answers from the shipped documentation in this skill's references — the user manual, the capability-to-API-to-skill map, the FAQ — and only touches the API for a live fact. Needs no capability; everyone's bundle carries it.
---

# Oryh Help

The answer to "how does oryh work" is written down. Read it before doing
anything else, and answer in the person's own words and language.

{{include:_common/answer-the-question.md}}

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  api_key: "{{ORYH_API_KEY}}"            # the person's own key; live-fact reads only
```

{{include:_common/api-auth-principal.md}}

## The One Rule

**Documentation first, API only for live facts, never research the API
surface to answer a conceptual question.** "Does granting customer creation
mean granting admin?" is answered by the capability map in thirty seconds;
walking `/openapi.json` for it wastes the person's afternoon and still
guesses. The references below are the same pages people read, rendered into
this skill, so they cannot disagree with the product.

A live fact is different: *which* roles this workspace has, *who* holds
`master_data.manage` today, *whether* a picklist practice is written into
the sales-order definition. For those, one read each — `GET /roles`,
`GET /capabilities`, `GET /workspace/setup-report`, `GET /builtin-object-types`,
`GET /workflow-definitions?entity_kind=builtin&object_type=…` — and say
which read the answer came from.

When the answer ends in an action ("so add `master_data.manage` to her
role"), name the skill and the desk that does it; do not do it from here.

## Where To Look

| The question is about | Read |
|---|---|
| A word people keep hearing — capability, role, desk, flow agent, workflow definition | `references/manual-index.md` |
| What a permission means, which capability a task needs, whether a role is needed | `references/capabilities-skills-api.md`, then `faq.md` → Permissions |
| Scoped grants (`business_object.write:daily_report`) and self-authored skills | `references/scoped-skill-capabilities.md` |
| Setting up a workspace: people, roles, master data, rules, custom objects | `references/manual-workspace.md` |
| Which skill does what, day to day | `references/manual-daily-use.md` |
| The console screens and what an administrator sees | `references/manual-administration.md` |
| Connecting an agent, keys, bundles, keeping skills current | `references/manual-connect-agent.md` |
| Sign-in, credentials, the first start | `references/manual-first-boot.md` |
| A question that has been asked before | `references/faq.md` |

## What This Skill Never Does

- Write anything. It explains; the owning skill acts.
- Guess a permission answer from route names or status codes — the map is
  the source, and a 403's detail names the capability.
- Invent a configuration switch. When the person asks "can it be set to…",
  the honest answer is usually a sentence in a workflow definition or a
  skill calibration, and the FAQ says so.
- Read payroll or anyone's private records to illustrate an answer.

## Reference

- references/manual-*.md: the user manual, one page per file
- references/capabilities-skills-api.md: capability → API → skill
- references/scoped-skill-capabilities.md: `verb:scope` grants
- references/faq.md: questions people have asked, with the answers
