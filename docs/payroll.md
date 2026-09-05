# Payroll: the payslip is an invoice, and the server computes nothing

Paying your own people is the third settlement path in this codebase, and it is
the one that reuses the most. It adds one new table and one new value on an
existing column; everything else — settlement, ageing, approval, the integrity invariants —
is the machinery already there.

## The server computes nothing

Say this before anything else, because the first person to use it will assume
otherwise: **oryh calculates no part of a payslip.** Not the social-insurance
contribution, not the housing fund, not cumulative-withholding income tax, not the
special additional deductions, not the year-end bonus method.

Those rates are national and municipal policy. They change on their own
schedule, they differ by city, and they are public knowledge that any competent
agent already has. A records layer that quietly applied a rate would be
inventing policy while looking like arithmetic — and its output would be wrong
in exactly the cases nobody checks, because the number would arrive with the
authority of a computed field.

This is the same position taken on cross-currency conversion and on points
redemption rates: **oryh stores facts and state; agents drive the flow.** The
agent works out the figures from what it knows and from the workspace's own
workflow definition, and records the result.

The consequence is that the payslip line is the ONLY surviving record of the
arithmetic — nothing in this database could reconstruct why the pension
deduction was 960.00 rather than 860.00. So every payslip line is required to
show its working: it either cites the pay record its number came from
(`pay_history_id`) or states the calculation in `notes`
(`contribution base 12000.00 × 8% = 960.00`). A line that does neither is a 422. This is
a legality guard, not a style rule — a figure nobody can check is the one thing
a payslip may not contain.

## `pay_histories`: every term of one person's pay

OFBiz's `PayHistory` is a salary with a date range. This one is widened: a row
states **one component** of one person's pay over one range.

| component | shape | example |
|---|---|---|
| `base_salary` | `amount` + `period_type` | 15000 a month |
| `allowance` | `amount` | travel allowance 500/month |
| `commission` | `rate` + `basis` | 3% of collections |
| `bonus` | `formula` | two months' salary on target |
| `overtime_rate` | `amount` or `formula` | 1.5× on ordinary days |

Three shapes, because compensation terms genuinely come in three: a scalar, a
proportion of something, and everything else. `formula` is free text and **the
server never parses it** — it is there for the agent to read, exactly as a
workflow definition is. At least one shape must be stated; a `rate` without a
`basis` is refused, because a proportion with nothing to apply it to is half a
rule.

### Why these terms live here rather than in a business object

A commission rate could have been a tenant-defined business object — that is
what business objects are for, and it would have cost nothing to build.

The reason not to is that **business-object reads are not gated**. Any
credential in the workspace can list them. Somebody's commission rate is as
confidential as their salary, and `pay_histories` already sits behind
`payroll.read`. Putting the rate anywhere else would have quietly published it.

What belongs here is a fact about THIS PERSON. Company-wide rules (a bonus
scheme, a commission policy) are policy and belong in a workflow definition.
National policy belongs in neither — see above. The one borderline case is the
social-insurance and housing-fund contribution base: that IS a fact about the
person and it changes on its own schedule, so
it goes in this table's `custom_fields`, where it inherits the effective dating
for free.

### A pay revision is not editing a number

`POST /pay-histories` from a new date closes the previous record for **that
component** the day before and opens the new one, in a single transaction. As
two calls they would eventually drift, and a compensation history with a hole in
it cannot explain a payslip.

Components are closed independently, which is the whole reason `component` is in
the unique key and in the supersede query. Superseding by employee alone would
have ended somebody's commission arrangement every time they got a pay rise, and
nobody would have noticed until the quarter closed.

A record a payslip has cited is frozen (409). Moving it would change what an
issued document says without touching that document.

## The payslip

A payslip is an `Invoice` with `direction = 'payroll'`, one `InvoiceItem` per
earning or deduction, **earnings positive, deductions negative**.

### Why `direction` gained a third value

`direction` was named for a two-valued field, and this looks like squeezing a
third value into it. It is the opposite. OFBiz has one `invoiceTypeId` ∈
{SALES, PURCHASE, PAYROL}; renaming it `direction` was the narrowing, made when
only two values existed. Adding `payroll` is a return to the original shape.

The name stays. Renaming it would touch two live databases, every guard that
branches on it, every skill document and the whole frontend type surface — a
large migration bought for a wording preference.

### What the payslip refuses

| refused | why |
|---|---|
| a second payslip for the same person and `period_start` | double payment is the most expensive mistake here and the least likely to be noticed — so it is a partial unique index, not an agent's care |
| `total_amount` | net pay IS the sum of the lines; a second opinion about what somebody earns can only be wrong |
| a deduction written positive | `payroll_iit` as `+389.4` hands the person nearly twice what they are owed, and nothing downstream would object |
| a line with neither `pay_history_id` nor `notes` | the rates are not stored here, so this line is the only record of the calculation |
| a customer, a vendor, or either order link | a payslip bills nobody and fulfils no order |
| a `pay_history_id` belonging to someone else | that is a different person's salary on this person's payslip |
| a signed line of `0.00` | a line that moves nothing is not a movement — a month with no income tax has no tax line, and the reason belongs in `remarks` |

### The item vocabulary carries a sign

`type_options` gained a nullable `sign` column, and `payroll_item_type` is the
one family that uses it. The shipped catalog maps OFBiz's `PAYROL_*` ids onto
this repository's lowercase naming:

| name | sign | OFBiz |
|---|---|---|
| `payroll_salary` | + | `PAYROL_SALARY` |
| `payroll_hourly_rate` | + | `PAYROL_HRLY_RATE` |
| `payroll_bonus` | + | `PAYROL_BONUS` |
| `payroll_commission` | + | `PAYROL_COMMISSION` |
| `payroll_allowance` | + | `CN_PAYROL_ALLOWANCE` |
| `payroll_iit` | − | `CN_PAYROL_IIT` |
| `payroll_pension_ee` | − | `CN_PAYROL_PENSION_EE` |
| `payroll_medical_ee` | − | `CN_PAYROL_MEDICAL_EE` |
| `payroll_unemploy_ee` | − | `CN_PAYROL_UNEMPLOY_EE` |
| `payroll_housing_ee` | − | `CN_PAYROL_HOUSING_EE` |
| `payroll_other_deduction` | − | — |

A tenant may add its own; an entry in this family without a `sign` is refused on
use, because an unsigned payslip line is exactly the ambiguity the family exists
to remove.

Which vocabulary an invoice line validates against depends on the invoice's
direction — `payroll_item_type` for a payslip, `invoice_item_type` for
everything else. That is the same move billing accounts make when validating
`unit` against one of two families by `unit_type`.

## What the payslip does not carry

Only the employee's half. Every shipped deduction type is `_ee`, so the
employer's own social-insurance and housing-fund contributions appear nowhere on
it, and total employment cost cannot be read off a payslip.

That is not an omission to fix. A payslip states what one person was paid and
what was withheld from them; the employer's contribution is a company expense
that happens to be computed from the same base. It arrives as an ordinary
**purchase** invoice against the collecting authority — the tax authority for
income tax and social insurance, the housing fund centre for the fund — settled
by an outbound payment through the
same ledger as any other payable. Two payables, two payments, no new object.

The identity worth checking at month end:

```
cash out = net pay total + remitted to the tax authority + remitted to the fund centre
         = gross pay total + the employer's own contributions
         = total employment cost
```

## Paying it out

One outbound payment per person, all sharing a `reference_no` as the bank batch
number. That is the whole of a payroll batch — no `PaymentGroup` object, no new schema.
Each payout is applied to that person's payslip through the ordinary settlement
endpoint, so `outstanding_amount`, the reversal-by-counter-entry rule and the
over-application guard all work unchanged.

## Confidentiality: the first gated read

Every other read in this API is tenant-scoped only. That is right for business
documents and unacceptable for pay, so payroll is the first thing here that
belonging to the workspace does not entitle you to see.

`payroll.read` gates six paths, and the gate is only worth what its least
covered path is:

| path | without the capability |
|---|---|
| `GET /invoices` | payroll rows filtered out, except the caller's own |
| `GET /invoices/{id}` and `/detail` | **404**, not 403 — 403 would confirm the payslip exists |
| `GET /payments`, `GET /payments/{id}` | two clauses: a payout **already applied** to someone else's payslip is hidden from everyone below `payroll.read`, and a payout merely **naming another employee** is hidden from anyone who is not a money handler (`payment.record` / `payment.apply`) |
| `GET /payment-applications` | rows pointing at someone else's payslip are filtered, including when named directly |
| `GET /object-directory` | the payroll count is filtered — "how many payslips did this company issue" is worth hiding on its own |
| `GET /pay-histories`, `GET /employees/{id}/pay-history` | own records only |

An employee always sees their own payslip. Somebody who cannot check what they
were paid has no recourse.

The second payment clause exists because the first one had a window in it, found
in the live test environment rather than here. Settlement is what makes a
payout *provably* payroll — but the payout exists long before it is settled:
created, submitted, approved, paid, and only then applied. For that whole
stretch it sat in plain view of every colleague, carrying the payee's name and
their net pay, and became confidential only after the money had already moved.
Gating on the link was gating on the wrong thing; money that names another
employee is that person's business from the moment it is recorded.

Money handlers are exempt from that second clause, and the exemption is the job:
a cashier processing expense reimbursements and salary disbursement has to see
what they are paying. What
they still do not see is a payout already applied to a payslip — at that point
its amount IS somebody's net pay, and the first clause holds for them too.

"Money handler" is `payment.record`, `payment.apply` **or** `payment.advance`.
The third was added after a workspace routed salary disbursement through payment approval
and discovered the step was unreachable: approving a payout you cannot see is
not a weaker version of the job, it is none of it, and the approver's queue came
back empty for human and flow agent alike. The widening is real — whoever may
approve payouts can read an unsettled one's amount — and it is bounded twice:
it reaches the payout only, never the payslip with its line-by-line breakdown,
and it ends the moment the payout is applied.

An approval path therefore needs `payment.advance` and nothing from payroll. A
reviewer who must additionally tie the batch back to the payslips needs
`payroll.read` — but never `payroll.manage`, or they can rewrite the salary they
were asked to check.

**A tenant service key reads everything**, because `Actor.bypasses_permissions`
is what that credential means — the company issued it to itself. The
consequence is real and worth stating rather than discovering: any standing
agent on the tenant key can read every salary. A workspace that cares should run
payroll agents on user-bound keys holding `payroll.read`.

**The hosted flow agent reads payroll too.** Its fixed grant set carries
`payroll.read` (since 2026-09-05) because a payslip is a `direction=payroll`
invoice in the same `submitted` queue as every other invoice, and without the
read the hosted invoice flow could neither list nor advance one — thirteen
payslips once waited a day in a workspace whose run log said "queue 0". The
trade is stated rather than hidden: enrolling in hosted driving means the
platform-run agent can read pay. What bounds it is the skill it runs, which
routes payslips and writes no pay figure anywhere outside them, and the
approver it assigns, who must hold `payroll.read` to open what they are asked
to approve.

`payroll.manage` is separate from `invoice.manage:payroll` because deciding what
somebody earns and producing the monthly document are different jobs, and a
workspace that separates them should be able to.

## What the integrity audit asserts

Every invariant above is restated over the whole database in
`scripts/data_integrity_audit.py`, because the write path only guards what goes
through it:

- no two terms of the same component in force at once, and none ending before it starts
- every term states an amount, a rate with its basis, or a formula
- one payslip per person per period; every payslip names its person and its period
- no payslip declares a total of its own, and none is empty
- every line moves the way its type's sign says, falling back to the shipped
  catalog for a tenant that never customized the family
- every line shows its working
- a salary line cites only that person's own record
- nobody is paid a negative net

## Mapping to OFBiz

| OFBiz | here |
|---|---|
| `PayHistory` | `pay_histories`, widened from the salary to every per-person term |
| `Invoice(invoiceTypeId = PAYROL_INVOICE)` | `invoices.direction = 'payroll'` |
| `InvoiceItem(invoiceItemTypeId = PAYROL_*)` | `invoice_items.invoice_item_type`, family `payroll_item_type` |
| `PayGrade` / `SalaryStep` | not modelled — HR master data; use a tenant business object |
| `PaymentGroup` | a shared `reference_no` |
