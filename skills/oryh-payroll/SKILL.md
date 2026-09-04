---
name: oryh-payroll
description: Use when HR or a compensation specialist needs to set or change someone's pay terms (setting or revising pay, including commission and bonus arrangements), produce payslips (工资条) for a period, and disburse pay (发放工资) with the payout matched to each payslip. Covers the whole payroll arc for one role. Not for approving the payout (that is oryh-payment-approval-flow), not for expense reimbursement (oryh-expense-submit), and not for billing customers or suppliers (oryh-receivables / oryh-payables).
required_capability: payroll.manage
---

# Oryh Payroll

The whole HR arc: set the terms → produce the payslip → pay it → settle it.

**The server computes nothing.** Read that again before the first call. Social
insurance bases and ceilings, housing fund rates, cumulative withholding for
individual income tax, itemised additional deductions, the tax treatment of an
annual bonus — none of it is stored here and none of it is calculated here. Those are national and local
policy, they change, and a records layer that quietly applied a rate would be
inventing policy while looking like arithmetic. **You do the calculation** from
what you know and from the workspace's own workflow definition, and you record
the result together with how you reached it.

The three facts that follow from that:

- **Every payslip line must show its working.** A line either cites the pay
  record it came from (`pay_history_id`) or states the calculation in `notes`
  — `contribution base 12000.00 × 8% = 960.00`. A line that does neither is refused
  (422), because nothing else in this database could reconstruct why the
  number was 960 and not 860.
- **A payslip is an invoice.** `direction: "payroll"`, one `InvoiceItem` per
  earning or deduction, **earnings positive, deductions negative**. So
  settlement, ageing, approval and the audit invariants are the ones you
  already know.
- **Pay is the one read that belonging to the workspace does not entitle you
  to.** Payslips and pay records are gated behind `payroll.read`; without it a
  credential sees only its own. Do not work around this, and do not repeat a
  colleague's figures to someone who asked.

{{include:_common/answer-the-question.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/who-you-are-acting-as.md}}

{{include:_common/read-before-you-decide.md}}

{{include:_common/leave-no-orphan-work.md}}

## Trigger Examples

- "Set the new salesperson's pay: 15000 a month, 3% commission on collections"
- "Raise Zhou to 18000 from July"
- "Produce July's payslips"
- "Payroll went out this month, settle each person's payslip"
- "What did Zhou earn in March last year?"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # needs payroll.manage, payroll.read,
                                  # invoice.manage:payroll, payment.record, payment.apply
  employee_id: "{{EMPLOYEE_ID}}"  # the HR officer recorded on what you file
```

Setting pay (`payroll.manage`) and producing payslips
(`invoice.manage:payroll`) are separate on purpose — deciding what someone earns and producing the monthly document are
different jobs. If your key holds only one, do that half and say plainly which
step someone else must take.

Disbursing needs `payment.record`, which is what lets you **create and submit** the
payout — and deliberately not approve it: moving it past submitted needs
`payment.advance`, which belongs to whoever the workflow definition names. A
403 on `POST /payments` means this key files pay but does not disburse it; hand
the batch over rather than looking for another credential.

**Read-only users do not need this skill.** Somebody checking their own
payslip, or an approver totalling a batch, goes to `$oryh-payslip` — it is
ungated, so everyone already has it. This skill is the
write half.

## Setting and revising pay

A `pay_history` row is **one term of one person's pay, over one date range**.
`component` says which term:

| component | shape | example |
|---|---|---|
| `base_salary` | `amount` + `period_type` | 15000 a month |
| `allowance` | `amount` | travel allowance 500/month |
| `commission` | `rate` + `basis` | 3% of collections |
| `bonus` | `formula` (words) | two months' salary on target |
| `overtime_rate` | `amount` or `formula` | 1.5× on ordinary days |

State the term in whichever of the three shapes fits — a scalar `amount`, a
proportional `rate` with the `basis` it applies to, or a `formula` in words for
what fits neither (tiered commission, a performance multiplier). At least one
is required; a `rate`
without a `basis` is refused, because a proportion with nothing to apply it to
is half a rule. **The server never parses `formula`** — it is there for you to
read, exactly like a workflow definition.

```json
POST /pay-histories
{
  "employee_id": "...",
  "component": "commission",
  "effective_from": "2026-07-01",
  "rate": 0.03,
  "basis": "collections that month on contracts this person owns",
  "notes": "settled quarterly, paid with the following month's salary"
}
```

- **A pay revision is not editing a number.** Post a new record from the new date; the
  same call closes the previous one for **that component** the day before and
  opens the new one, in one transaction. The response returns both
  (`current`, `superseded`) — read `superseded.effective_thru` to confirm the
  handover landed where you meant.
- Components are independent: a pay rise closes the previous salary and leaves
  the commission arrangement alone. That is deliberate — never post a
  `base_salary` change expecting it to end anything else.
- Two records of the same component may not be in force on the same day (409).
  Backdating into a period that is already closed is refused for the same
  reason; correct the closed record instead, if it is still correctable.
- `PATCH /pay-histories/{id}` is for **fixing a mistake**, not recording a
  change. Once a payslip has cited a record it is frozen (409) — moving it
  would change what an issued document says without touching that document.
- **What belongs here** is a fact about THIS PERSON: their salary, their
  commission rate, their bonus arrangement, and their social-insurance and
  housing-fund contribution bases (in `custom_fields`, where they inherit the
  same effective dating). What does not:
  company-wide rules (a workflow definition), and national policy (nowhere —
  you already know it).

Reading: `GET /employees/{employee_id}/pay-history` is one person's whole
history; `GET /pay-histories?component=commission&in_force_on=2026-07-01` is
everyone on a rate today.

## Producing payslips

One payslip per person per period, and the database enforces it — a second one
for the same person and `period_start` is a 409. That check exists because
double payment is the most expensive mistake on this path and the least likely
to be noticed.

```json
POST /invoices
{
  "direction": "payroll",
  "employee_id": "{{EMPLOYEE_ID}}",
  "payee_employee_id": "...",
  "title": "July 2026 salary",
  "period_start": "2026-07-01",
  "period_end": "2026-07-31",
  "items": [
    {"invoice_item_type": "payroll_salary", "product_name_snapshot": "Base salary",
     "amount": 15000.0, "pay_history_id": "...", "notes": "15000.00 a month (from 2026-07-01)"},
    {"invoice_item_type": "payroll_commission", "product_name_snapshot": "Sales commission",
     "amount": 2400.0, "pay_history_id": "...", "notes": "collections 80000.00 × 3% = 2400.00"},
    {"invoice_item_type": "payroll_pension_ee", "product_name_snapshot": "Pension (employee)",
     "amount": -960.0, "notes": "contribution base 12000.00 × 8% = 960.00"},
    {"invoice_item_type": "payroll_iit", "product_name_snapshot": "Individual income tax",
     "amount": -389.4, "notes": "cumulative withholding: taxable income 12989.00 × 3%"}
  ]
}
```

- **The whole payslip is one call.** Lines come with it; a bad line rolls the
  payslip back rather than leaving half a document.
- **A payslip declares no total of its own.** Net pay IS the sum of the lines —
  passing `total_amount` is a 422, because a second opinion about what someone
  earns can only be wrong. `GET /invoices/{id}/detail` reports `billed_total`,
  which is that sum; read it back and check it against your own arithmetic
  before telling anyone a number.
- **Signs are checked.** `payroll_iit` written as `+389.4` rather than `-389.4`
  hands the person nearly twice what they are owed, and nothing downstream
  would object — so the vocabulary declares the direction and the write path
  refuses the other one (422). See
  `GET /type-options?family=payroll_item_type` for this workspace's list and
  each entry's `sign`.
- A workspace may add its own item types; one in this family without a `sign`
  is refused on use, since an unsigned payslip line is exactly the ambiguity
  the family exists to remove.
- **A deduction that computes to zero is not a line.** Somebody whose cumulative
  taxable income is negative owes no tax this month; a `0.00` tax row is refused
  (422), because a line that moves nothing is not a movement. Do not fake it as
  `-0.01`, and do not silently drop the reasoning either — put it in the
  payslip's `remarks`: "no tax this month: cumulative taxable income −7243.11,
  negative, nothing to withhold". The
  employee needs to see it was considered, not omitted.

The employer's contributions and the remittance to the collecting authorities
are the next step, not part of the payslip: file them as an ordinary
**purchase** invoice against the authority as vendor, with one line per
contribution type, and settle it with an outbound payment. Social insurance is
collected by the tax authority and the housing fund by the fund centre — two
payables, two payments.

**Per person, in order**: read the terms in force
(`GET /employees/{id}/pay-history?in_force_on=2026-07-01`), work out each
figure, then file. When you need attendance or commission figures, get them from
the timesheets and the settlement ledger — never assume a full month.

If the workspace also produces a payslip **document** — a PDF handed to the
person, a signed acknowledgement they return — attach it (`attachment_id` on
the payslip) rather than keeping it outside the system; see "Keeping the
original" below. Read it back with
`GET /invoices/{invoice_id}/attachments/{attachment_id}/content`, and note
that this is the one attachment family where the document route matters for
more than tidiness: a payslip's file is somebody's net pay, so only a
credential that may see the payslip may see it. Reaching it by id alone does
not work for anyone but the workspace administrator, by design.

## Disbursing

One payment per person, all sharing a `reference_no` as the bank batch number.
That is the whole of a "payroll batch" — a group of payments sharing one
reference, with no extra object. Use the bank's own batch number from the
bank disbursement receipt: the treasury desk links the single bank debit to the batch by
that reference (`payment_reference_no` on the register line), and the
server checks the members sum to the debit — so the number must be the one
the bank prints, spelled the same on every payment.

**The person never has to know this field exists.** Ask once, in their
words: "does the bank's disbursement receipt carry a batch number?" If it
does, use it verbatim. If there is none yet — the payout is being filed
before the bank run — derive one from the period, `PAYROLL-2026-08`, use it
on every payment of the batch, and say it in the read-back: "this batch is
PAYROLL-2026-08; the cashier matches the bank debit to it". Never let two
payments of one run carry two spellings, and never reuse a batch number
across periods.

```json
POST /payments
{
  "direction": "outbound",
  "employee_id": "{{EMPLOYEE_ID}}",
  "payee_employee_id": "...",
  "amount": 16150.6,
  "payment_method": "bank_transfer",
  "reference_no": "PAYROLL-2026-07",
  "status": "paid"
}
```

Then match each payout to that person's payslip:

```json
POST /payments/{payment_id}/apply
{
  "lines": [{"applied_to_type": "invoice", "applied_to_id": "...", "amount_applied": 16150.6}],
  "idempotency_key": "payroll-2026-07-zhou"
}
```

**Each payout settles its OWN payslip** — the payment's `payee_employee_id` and
the payslip's must be the same person, or the application is refused (409). In
a batch of forty this is the mistake that hides: the amounts are plausible, the
totals reconcile, and two people's pay is recorded against each other's payslip.

**Always pass an `idempotency_key`** — this endpoint writes money, and a retry
without one applies twice. A repeat with the same key returns `replayed: true`
and writes nothing.

Whether the batch needs approval before the bank sees it is the workspace's
decision, in its workflow definition — `the hosted workflow admin agent` runs it.
Do not create the payout in a terminal state to skip a queue you were told
about.

## After it comes back returned

A payslip or a payout that comes back `returned` leaves a rework todo on you,
and the todo's `description` plus the latest `returned` approval record's
`comment` say exactly what to fix. Read both before touching anything —
`GET /approval-records?entity_type=invoice&entity_id={id}`.

**Correct the original; do not void and redo.** The one-payslip-per-person-per-period
constraint only counts live payslips,
so voiding and re-issuing does work — and it is the more expensive answer every
time. It breaks the link between what was rejected and what replaced it, it
puts two documents in the period's history where the reviewer expects one, and
the approval trail restarts with no record that a previous round happened.
Correct the lines on the original and resubmit; the round number advances and
the whole exchange stays readable.

After a successful resubmit, close your own rework todo
(`PATCH /todos/{todo_id}` `{"status": "completed"}`). While it stays open the
document is invisible to the flow admin's queue, so nobody picks it up.

If voiding really is right — the whole batch was computed against the wrong
month, say — then it is a void, and the rules in "Leave No Orphan Work" above
apply: the todos are yours to close, and the two documents should name each
other.

{{include:_common/attachment-evidence.md}}

## What This Skill Never Does

- **Calculate social insurance, the housing fund or income tax as if the server
  had a table.** You compute; you
  record what you computed and how. If you are unsure of a current rate or
  ceiling, **look it up before guessing**:
  `GET /policies?category=external_standard&in_force_on=2026-07-15` returns the
  standard the workspace has recorded for that date, with its `code`, `version`
  and publisher — so the line's working can read
  `contribution base 36921 × 8% (per FIN-2026-03 v1)`. Nothing in force means ask: a
  confidently wrong deduction is worse than a question, and `$oryh-policy` is
  where the answer gets recorded so next month is cheaper.
- **Put the employer's half on the payslip.** The shipped types are all `_ee`:
  a payslip carries only what is withheld from the person. The employer's own
  social-insurance and housing-fund contributions never appear on it, and
  computing total employment cost from a payslip alone gives the wrong number.
- Store policy rates in `pay_histories`. Only facts about a person go there.
- Repeat one employee's pay to another person, or work around the read gate.
- Issue a second payslip for a period, or restate a payslip's total.
- Edit a pay record a payslip has cited — that is a correction to the payslip,
  or a new record from a new date.
- Decide the raise, the bonus, or the write-off. Those are the principal's
  decisions; you record them.
- Approve the payout, or move it to paid on your own reading — that is
  `the hosted workflow admin agent`.
- Import history — that is `$oryh-data-migration`.
- Answer "what did I get paid this month" — that is `$oryh-payslip`, which every employee
  holds and which needs no payroll capability to read one's own pay.

## Reference

- [references/api.md](references/api.md): every endpoint, the pay-term shapes,
  the payslip item vocabulary with its signs, and the guards with the exact
  conditions that raise them.
