---
name: oryh-leave-submit
description: Use when a person's AI agent needs to check their own leave balance or file, amend, withdraw or submit their own 请假 in oryh — 年假/病假/事假/婚假/产假/陪产假/丧假/调休. Answers "我还有几天年假"、"下周三请一天假"、"上午请半天"、"我今年休了多少天", computing the balance from the workspace's published leave policy rather than reading a stored number. Records the requester's own facts only; approving and routing belong to other roles.
required_capability: leave.submit_own
---

# Oryh Leave Submit

File the principal's own leave, and answer what they have left. The credential
is the identity: the server only accepts writes for the employee linked to this
key, so never ask "for whom" — it is always the principal.

**这个系统里没有「余额」这个字段。** 余额是按公司制度算出来的，每次都算。这是
整个设计的核心，不是实现细节——公司改了休假制度，所有人的余额当场就对，不需要
迁移任何数据。

{{include:_common/answer-the-question.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/leave-balance.md}}

{{include:_common/read-before-you-decide.md}}

{{include:_common/leave-no-orphan-work.md}}

## Trigger Examples

- "我还有几天年假？"
- "下周三请一天假" / "明天上午请半天"
- "3 月 2 号到 6 号休年假"
- "我今年病假休了多少天"
- "上次那个请假单撤回吧，日期不对"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # the principal's user-bound key
  employee_id: "{{EMPLOYEE_ID}}"  # who 我 means; the only employee this key may file for
```

## Steps

1. **Read the rules and the facts together** — the balance section above says
   which three calls, and they do not feed each other, so send them as one
   batch. The tenant's 请假制度 shapes the whole conversation: how far ahead a
   请假 must be filed, whether 病假 over N days needs a certificate, whether
   half days are allowed at all.

2. **Work out the length in days, and say how you got it.** The unit is days
   with halves — `0.5`, `1`, `3.5`. A calendar range is not the answer:
   whether the Saturday inside 周五到周一 counts is the policy's call, and so
   is whether a public holiday inside the range does. Compute it, then state
   it: 「3 月 2 日到 3 月 6 日，扣掉周末 2 天，计 3 天」. The person confirms
   the number before it is filed.

3. **Check the balance and say the arithmetic** — see above. If the request
   exceeds what is available, say so plainly with the shortfall, and ask rather
   than refusing: filing it is legal, and whether to grant it is the approver's
   decision informed by the same numbers.

4. **File the whole request in one call**:

```json
POST /employee-leaves
{
  "employee_id": "{{EMPLOYEE_ID}}",
  "leave_type": "annual",
  "from_date": "2026-03-02",
  "thru_date": "2026-03-06",
  "duration_days": 3,
  "reason": "回老家",
  "source_report_text": "3月2号到6号休年假，回老家"
}
```

   - `leave_type` must be a value from the tenant's `leave_type` vocabulary
     (`GET /type-options?family=leave_type`) — a 422 means this workspace calls
     it something else, not that the type is invalid.
   - `duration_days` is **frozen at approval**, like a quotation's price
     snapshot: it records what the approver agreed to under the rules of that
     day, so a later policy revision does not silently restate a past absence.
   - The response is your read-back.

5. **Submit**: `POST /employee-leaves/{id}/submit`, only after the person has
   confirmed the dates, the length and the balance arithmetic. Idempotent.
   `/submit` records the `submitted` approval fact itself — do not post one.

6. **Amending**: while the request is `draft` or `returned`, `PATCH` it.
   A returned request carries the reason in the rework todo's `description` and
   the latest `returned` approval record's `comment`: read both, fix, resubmit,
   then close your own rework todo. Once approved, the dates are settled — see
   below.

## 撤销与销假

- **撤回一个还没批的**: `PATCH` status to `cancelled`. Nothing is refunded
  because nothing was ever deducted — the row simply stops counting toward
  已批/在途 the moment it leaves those states. That is the quiet benefit of a
  computed balance.
- **批了但没休**: also `cancelled`, and it needs the same honesty — an approver
  agreed to this, so say who is being told. Never delete it: what was approved
  is part of the record.
- **改期一个已批准的**: cancel it and file a new one, referencing the original
  in `reason`. Do not edit an approved request's dates — that would change what
  was agreed without leaving a trace that something else was agreed first.
- **销假**: if the workspace records that leave was actually taken, that is the
  `taken` state, and it is the flow side's write, not yours.

## What This Skill Never Does

- **Store a balance anywhere.** Not in a custom object, not in a billing
  account, not in `custom_fields`. The number is a conclusion drawn from rules
  that change; writing it down is how it becomes wrong.
- Approve, reject or return a request — including the principal's own.
- File for anybody but the credential's own employee.
- Invent an entitlement when no leave policy is published. Say it is unwritten.
- Quote statutory minimums as if they were the company's rule.
- Touch timesheets. 请假 and 工时 are separate records; a day off is not a
  timesheet row with zero hours.

## Reference

- [references/api.md](references/api.md): every call, the filters that make the
  balance one query, and the states.
