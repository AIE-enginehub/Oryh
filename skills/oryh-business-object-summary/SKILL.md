---
name: oryh-business-object-summary
description: Use when an AI agent needs to summarize a set of business objects of one type for its principal — e.g. a manager asking for this week's daily reports, or who has not submitted one yet. Reads business_objects (optionally scoped by a payload field) and produces a natural-language summary. Read-only; never writes or advances any record.
required_capability: business_object.summarize
---

# Oryh Business Object Summary

Turn a set of business-object records into a briefing. This is the read/aggregate counterpart to `$oryh-business-object`: that skill records one object at a time, this one reads many and summarizes them. It never creates, edits, or advances anything.

{{include:_common/answer-the-question.md}}

## Trigger Examples

- "总结一下这周的日报"
- "研发部还有哪些人没交日报"
- "看看本月的费用申请都是什么情况"
- "汇总一下张三团队最近的保修卡申请"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"        # the manager's own user-bound key
```

`object_type` (e.g. `daily_report`) and the scope of the summary (time window, a payload field like `department`, a specific employee) come from the conversation — never hardcoded, so the same skill works for any object type a tenant defines.

## Steps

1. **Confirm the type and scope** with the principal if either is ambiguous: which `object_type`, what time window, any filter (department, project, a specific person). Do not guess a scope wide enough to include records outside what was asked.
2. **Read the schema, if one exists**: `GET /object-type-definitions?object_type=<type>` — its `json_schema` tells you what fields are worth summarizing (e.g. a daily report's "完成事项" / "问题" / "明日计划" fields) and its `state_machine` (if any) tells you what statuses mean.
3. **Fetch the records**: `GET /business-objects?object_type=<type>&payload_match={"field":"value"}` for a payload-field filter (e.g. `{"department":"研发部"}`). There is no server-side date-range filter; `keyword=` searches title/summary/source_text, and `page`/`size` paginate (omit both to get every non-deleted match in one response). For time-window questions, read the results and filter/sort by `created_at` yourself. Say so if the result set looks too large to have summarized completely, rather than silently truncating.
4. **For "who hasn't submitted" questions**, cross-reference `GET /employees?status=active` against a payload field that records the submitter (`created_by` is `user:<user_id>` — mapping user ids to employees needs `users.manage`, which this credential normally lacks) — oryh has no dedicated "missing submission" query, so the gap is computed by the agent, not the API.
5. **Summarize**, grouped in whatever way answers the question (by person, by status, by day). Call out anything that stands out: overdue or missing entries, a cluster of `rejected`/`returned` statuses, a record whose payload flags a problem.

## What This Skill Never Does

- Create, edit, or soft-delete a business object (`$oryh-business-object` does that).
- Change `status` or otherwise advance a record — a summary is read-only by definition.
- Record approval facts or assign todos.
- Assume it has read access beyond what `business-objects` reads publicly return within the tenant — this skill does not add or remove visibility; it only decides who gets handed the skill (see the note in the reference doc about the current absence of per-object read scoping).

## Reference

- [references/api.md](references/api.md): request templates.
