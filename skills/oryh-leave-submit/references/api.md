# Leave API

Every path hangs off `api_base_url` exactly as given — no version prefix to add.

There is no balance endpoint. That is deliberate and permanent: see the balance
section in SKILL.md. The three reads below are what a balance is computed from.

## The three reads a balance needs

| Call | Gives |
|---|---|
| `GET /policies?category=hr&status=published&in_force_on=2026-06-15` | the rules that applied on that date — `body` in prose, `rules_json` if the workspace put the tiers in structure |
| `GET /employees/{employee_id}` | `hire_date`, which 工龄 is measured from. Null means nobody recorded it — ask, do not assume |
| `GET /employee-leaves?employee_id={id}&leave_type=annual&overlapping_from=2026-01-01&overlapping_thru=2026-12-31` | every request touching the period, whatever its status |

`overlapping_from` / `overlapping_thru` match any request whose range
**intersects** the window, so one straddling New Year appears in both years.
Filtering on `from_date` alone would drop it from one side without saying so.
How to split it is the policy's call.

## Filing

| Call | Purpose |
|---|---|
| `POST /employee-leaves` | file one absence |
| `GET /employee-leaves/{id}` | read one back |
| `PATCH /employee-leaves/{id}` | amend, while `draft` or `returned` |
| `POST /employee-leaves/{id}/submit` | send for approval; idempotent; records the `submitted` fact |
| `DELETE /employee-leaves/{id}` | only a draft mistake. An approved request is `cancelled`, never deleted |
| `POST /employee-leaves/{id}/restore` | undo a soft delete |

```json
POST /employee-leaves
{
  "employee_id": "…",
  "leave_type": "annual",
  "from_date": "2026-03-02",
  "thru_date": "2026-03-06",
  "duration_days": 3,
  "reason": "回老家",
  "source_report_text": "<the person's own words>"
}
```

| Field | Note |
|---|---|
| `leave_type` | from `GET /type-options?family=leave_type`; a 422 means this workspace names it differently |
| `from_date` / `thru_date` | inclusive; `thru_date < from_date` is a 422 |
| `duration_days` | days with halves, `> 0`. YOUR figure, per the tenant's weekend/holiday rule — the server never derives it from the dates |
| `reason` | free text. OFBiz has a reason-code tree; this does not, because nobody queries one |
| `custom_fields` | anything else the workspace tracks |

## States

`draft → submitted → approved | rejected | returned`, plus `cancelled` from
anywhere before completion and `taken` after `approved`.

| State | Means |
|---|---|
| `submitted` | awaiting a decision — **counts against the balance as 在途** |
| `approved` | granted; counts as 已批 |
| `returned` | sent back to fix; a rework todo says why |
| `cancelled` | withdrawn or not taken. Counts toward nothing — which is the whole refund, since nothing was deducted |
| `taken` | the absence actually happened, where the workspace records it |

The tenant may edit this machine
(`GET /workflow-definitions?entity_kind=builtin&object_type=employee_leave`);
read it rather than assuming these names.

## What the filer may not do

`PATCH` with a status the machine does not allow from here is a 409, and
advancing past `submitted` needs `leave.advance`, which a member does not hold.
A 403 there is the separation working, not a configuration error.
