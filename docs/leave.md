# Leave: the absence is the record, the balance is a question

One table, `employee_leaves`, and one column added to `employees`. What is
interesting about this design is what is **not** in it: there is no
entitlement, no allowance, no accrual and no balance, anywhere, and there is
not going to be one.

## Why no balance

"You have four days left" is not a fact anybody recorded. It is what the
company's rules imply about this person today, and companies revise the rules.
A workspace that changes annual leave in June, or backdates a time-off-in-lieu ratio to January,
changes every balance retroactively — and if those balances had been written
down, they are now a pile of numbers that were true under text nobody follows,
correctable only by reconciling entries against a document.

Computed, the same revision needs nothing. Publish the new policy and every
answer is right, including about the past: `policies` is versioned, so
`GET /policies?in_force_on=2026-03-15` returns the rule that applied **in
March** and the March answer stays reproducible. A ledger cannot do that
without rewriting itself.

This is the third time this codebase takes that position. Payroll stores no tax
table and makes the agent show its arithmetic. A sales order's drift from its
quotation is computed on read, never stored. Leave is the same shape: **facts
are recorded, conclusions are derived**.

It also explains an absence in the model this was built from. Apache OFBiz has
`EmplLeave`, `EmplLeaveType` and `EmplLeaveReasonType` — and, twenty years on,
no accrual whatsoever: no balance, no entitlement, not even a service that
computes one. That looks like an omission and reads better as restraint. Leave
rules are too local to fix in a schema. Ours live in a document somebody can
revise, and the arithmetic lives in a skill.

## What is stored

```text
employee_leaves: employee, leave_type, from_date, thru_date, duration_days,
                 reason, status
employees.hire_date: what length of service is measured from
```

`duration_days` is days with halves — half a day off in the morning is `0.5` —
and it is **the agent's figure, not a date subtraction**. Whether the Saturday
inside a Friday-to-Monday span
counts is the policy's call, so the server records what was agreed rather than
recomputing it and quietly overruling the rule.

It is also the one number that freezes. Like a quotation's
`list_price_snapshot`, it records what the approver agreed to under the rules of
that day; the *entitlement* is recomputed forever, but what this particular
absence cost is settled.

## What was taken from OFBiz, and what was left

| OFBiz | Here | Why |
|---|---|---|
| `leaveTypeId` classification | `leave_type` type-option family | Right call: paternity and bereavement leave exist in some workspaces and not others |
| type separate from reason | type is a vocabulary; reason is free text | The split is right, the second tree is not — nobody queries a taxonomy of "why" |
| `approverPartyId` + `leaveStatus` on the row | `approval_records` + todos | Two columns give one approver and one state. The family plumbing gives levels, returns with reasons, and a trail |
| key `(partyId, leaveTypeId, fromDate)` | an id | Changing the dates should write a record, not delete one. Under OFBiz's key a reschedule erases the history |
| no accrual | no accrual, deliberately | See above |

## How a balance is computed

```text
available = entitled(policy, length of service, period) − approved − in flight
```

Three reads, none of them a balance endpoint:

```text
GET /policies?category=hr&status=published&in_force_on={date}
GET /employees/{id}                       → hire_date
GET /employee-leaves?employee_id={id}&overlapping_from=…&overlapping_thru=…
```

`overlapping_from`/`overlapping_thru` matches any request whose range
*intersects* the window, so a leave request straddling New Year appears in both years and
the policy decides how to split it. Filtering on `from_date` alone would drop it
from one side silently.

**In-flight leave is not optional.** There is no server-side hold on leave, so subtracting
`submitted` rows is the entire protection against somebody spending the same
three days twice by filing two requests before either is decided. The
calibration step of the flow agent recomputes it at assignment time, and the
one-decision-per-node index means each request is settled once.

Agents are required to show the arithmetic and cite the policy `code` and
`version` — see `skills/_common/leave-balance.md`. That is not politeness: the
number came from a revisable document, and a person told a bare figure cannot
tell a rule change from a mistake. When two agents disagree, the comparison
lands on the policy text, **which is the thing to fix**.

## Over-entitlement is not the server's business

Filing a request for more days than the balance allows is a legal record — it is
a request. The server has no allowance to check it against, and inventing one
would make it the arbiter of a rule that belongs in a document. The agent says
plainly that it exceeds the balance and by how much; the approver decides,
because granting it anyway (unpaid, or borrowed against next year) is a normal
thing for a company to do and its policy usually says so.

## Cancellation refunds nothing

Because nothing was deducted. A cancelled request stops matching the query that
counts approved and in-flight rows, and that is the whole of it — no reversing entry, no hold to
release. The row itself survives: an approver said yes to it, and that is part
of the record.

## What leave does not touch

**Timesheets.** A day off is not a timesheet row with zero hours; a timesheet
says what was worked and a leave record says what was not. **Payroll.** Unpaid leave affects pay, and
the deduction is HR's arithmetic at payslip time — the agent reads approved
leave and writes a line that shows its working, exactly as it does for social
insurance and income tax. Nothing deducts automatically, for the same reason nothing computes a tax
rate automatically.
