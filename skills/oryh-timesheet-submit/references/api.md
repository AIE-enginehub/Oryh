# Oryh Timesheet Submit API Reference

{{include:_common/api-auth-principal.md}}

## Identity And Reads

```text
GET /auth/me                                              → linked employee_id + permissions
GET /projects?keyword=&status=active                      → match a real project (read-only)
GET /timesheet-headers?employee_id={me}&status=draft      → reuse before create
GET /timesheet-headers/{header_id}/detail                 → header + entries + approval trail
GET /approval-records?entity_type=timesheet_header&entity_id={header_id}   → progress
GET /workflow-definitions?entity_kind=builtin&object_type=timesheet_header → tenant rules; apply its 提交要求 (step 2)
```

## Create Header

```json
POST /timesheet-headers
{
  "employee_id": "my-employee-id",
  "period_start": "2026-06-29",
  "period_end": "2026-07-05",
  "source_report_text": "这周我主要在 ERP Upgrade 上做 API 设计，还处理了联调问题。",
  "entries": [
    {"work_date": "2026-06-29", "hours": 8, "task": "API 设计"},
    {"work_date": "2026-06-30", "hours": 6.5, "task": "联调排查"}
  ]
}
```

`entries` rides the same transaction: one bad line rolls the whole document
back (nothing half-filled survives), `header_id`/`employee_id` per row are
implied, and the response carries the header AND every entry as stored — it
is the read-back. Standalone `POST /timesheet-entries` remains for
corrections afterwards.

One header per employee per exact (`period_start`, `period_end`) pair — a duplicate create returns 409 carrying the existing header's id and period; reuse that header. A soft-deleted header still holds its period slot, and the 409 then tells you to `POST /timesheet-headers/{header_id}/restore` instead of recreating. Pre-check the period across all statuses (the draft-only reuse query cannot see a `submitted`/`approved` header). Status starts at `draft`.

## Entries

```json
POST /timesheet-entries
{
  "header_id": "header-id",
  "employee_id": "my-employee-id",
  "work_date": "2026-06-29",
  "hours": 8,
  "task": "API design",
  "project_id": "project-id-if-confidently-matched",
  "project_name_snapshot": "ERP Upgrade",
  "client": "Globex",
  "work_type": "regular",
  "notes": "optional"
}
```

`work_type` (default `regular`) is a tenant-owned vocabulary: the shipped
catalog is regular | overtime | holiday | travel | other, and the tenant may
have added their own (值班、培训…) or archived shipped ones. Read the current
list with `GET /type-options?family=work_type&status=active`; an unknown value
is a 422 listing the active ones. Hours that genuinely are a kind of their own
deserve a new type rather than being filed as `other` —
`POST /type-options {"family": "work_type", "name": "on_call", "title": "值班"}`
(needs `object_types.manage`; on 403 name the missing type and ask an admin).

`PATCH /timesheet-entries/{id}` / `DELETE` while the header is editable (409 otherwise). `work_date` is not a PATCH field — sending it (or any unknown field, on any endpoint) is a 422 naming the field; correct a wrong date by DELETE + re-POST. Omit `project_id` and keep the free-text fields when master data is uncertain.

Server-enforced limits (validate in conversation before calling):

```text
hours       > 0 and ≤ 24 per entry          → 422 otherwise
work_date   within period_start..period_end → 400 otherwise
employee_id must match the header           → 400 otherwise
entries     only while header is editable   → 409 otherwise
project_id  must exist in this tenant       → 404 otherwise
```

## Submit

```json
POST /timesheet-headers/{header_id}/submit
{}
```

Guarded by the tenant's lifecycle machine (draft/returned → submitted); idempotent on resubmit; sets `submitted_at`.

## Submitted Fact (only if the role has approval.record)

```json
POST /approval-records
{
  "entity_type": "timesheet_header",
  "entity_id": "header-id",
  "round_no": 1,
  "sequence_no": 1,
  "action": "submitted",
  "approver_role": "submitter",
  "acted_at": "2026-07-06T09:00:00Z"
}
```

403 here is expected in tenants whose member role is fact-free — the workflow admin backfills it. After a return, resubmit with `round_no` incremented.

## Correcting The Header Before Submitting

```text
PATCH /timesheet-headers/{header_id}
{"period_start": "2026-07-06", "period_end": "2026-07-10", "remarks": "补充说明"}
```

Editable while the header is in an editable state (`draft`/`returned` by
default; 409 otherwise). This is how a wrong period or title is fixed — do
not delete and recreate, and do not leave a wrong value standing because the
document is already filled in.
