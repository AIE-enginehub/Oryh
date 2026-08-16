# Oryh Business Object Summary API Reference

{{include:_common/api-auth-principal.md}}

## Look Up The Type's Shape (optional but useful)

```text
GET /object-type-definitions?object_type=daily_report&status=active
```

Returns the active `json_schema` (which fields exist) and `state_machine` (if any). Types without a definition are free-form — summarize whatever payload keys the records actually contain.

## Fetch The Records To Summarize

```text
GET /business-objects?object_type=daily_report
GET /business-objects?object_type=daily_report&status=open
GET /business-objects?object_type=daily_report&payload_match={"department":"Engineering"}
```

Notes:

- `payload_match` only matches top-level scalar payload fields (string/number/boolean). It has no range operator — an exact-value filter only.
- No `created_at` range filter exists. `page`/`size` paginate (both omitted → every non-deleted match in one response); `keyword=` matches title/summary/source_text/object_type/id. For "this week's reports" style questions, fetch and filter/sort by `created_at` in the agent; if the set is large, say so rather than quietly summarizing a partial view.
- `include_deleted=true` surfaces soft-deleted objects if a question is specifically about those; omit it otherwise.

## Find Who Has Not Submitted

There is no "missing" query. Compute the gap yourself:

```text
GET /employees?status=active
GET /business-objects?object_type=daily_report&payload_match={...}
```

Match employees against a payload field that records the submitter (how the tenant's daily-report schema captures identity). `created_by` is `user:<user_id>` — resolving user ids to employees needs `users.manage` (`GET /auth/users`), which this credential normally lacks, so a payload identity field is the practical route.

Note on read scoping: reads are tenant-wide — there is no per-object read scoping today; every holder of this skill's capability sees every object of the type. Access control happens at skill distribution, not per record.

## Reading Status And Approval Context (if relevant to the question)

```text
GET /approval-records?entity_type=business_object&entity_id={id}
```

Only needed if the summary is about approval progress, not just content.
