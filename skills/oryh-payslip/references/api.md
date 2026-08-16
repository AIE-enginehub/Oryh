# Payslip Read API

Every path hangs off `api_base_url` exactly as given — no version prefix to add.

Read-only. Every call here is a GET; nothing in this reference writes.

## What each key sees

| Path | With `payroll.read` | Without it |
|---|---|---|
| `GET /invoices?direction=payroll` | every payslip | only the linked employee's own |
| `GET /invoices/{id}`, `/detail` | any payslip | own → 200; someone else's → **404** |
| `GET /pay-histories` | every term | own records only |
| `GET /employees/{id}/pay-history` | anyone's | own → 200; another employee → 404 |
| `GET /payments`, `/payments/{id}` | payouts settling any payslip | ones settling someone else's are filtered / 404 |
| `GET /payment-applications` | every row | rows pointing at someone else's payslip filtered out |
| `GET /object-directory` | true payroll count | the payroll count is filtered too |

404 rather than 403 is deliberate throughout: 403 confirms the document exists,
which is most of what the gate protects. Treat a 404 here as "not yours to
read", not as "missing".

A **tenant service key bypasses the permission layer entirely** and reads all
pay. Do not reach for one to answer a question a user-bound key was refused.

## Payslips

| Call | Purpose |
|---|---|
| `GET /invoices?direction=payroll&payee_employee_id={id}` | one person's payslips |
| `GET /invoices?direction=payroll&period_start=2026-07-01` | one period's batch |
| `GET /invoices/{invoice_id}` | the header |
| `GET /invoices/{invoice_id}/detail` | header + lines + `billed_total` / `outstanding_amount` |

`billed_total` IS net pay: a payslip declares no total of its own, so the sum
of its lines is the number. **Earnings positive, deductions negative** — income
tax, social insurance and the housing fund all come
back negative.

Each line carries:

| Field | Meaning |
|---|---|
| `invoice_item_type` | `payroll_salary`, `payroll_commission`, `payroll_iit`, `payroll_pension_ee`, … |
| `product_name_snapshot` | the label as issued (base salary, income tax) |
| `amount` | signed |
| `pay_history_id` | the pay term this line came from, when it came from one |
| `notes` | the working, in words — `contribution base 12000.00 × 8% = 960.00` |

A line states either `pay_history_id` or its working in `notes`; the write path
refuses one that does neither. So "why is this month lower" is always answerable from
the document itself.

The employer's half of social insurance and the housing fund is never on a
payslip — the shipped item types are all `_ee`, meaning withheld from the
person. Total employment cost cannot be read
off a payslip.

## Pay records

| Call | Purpose |
|---|---|
| `GET /employees/{employee_id}/pay-history` | one person's whole history, newest first |
| `GET /pay-histories?employee_id={id}` | the same, as a filterable list |
| `GET /pay-histories?in_force_on=2026-07-01` | what was in force on a date |
| `GET /pay-histories?component=commission` | everyone on a commission arrangement (needs `payroll.read`) |
| `GET /pay-histories/{pay_history_id}` | one record |

| component | shape |
|---|---|
| `base_salary` | `amount` + `period_type` |
| `allowance` | `amount` |
| `commission` | `rate` + `basis` |
| `bonus` | `formula` (words) |
| `overtime_rate` | `amount` or `formula` |

`effective_from` / `effective_thru` bound the term. A raise closes the previous
row the day before and opens a new one, so the history reads as a sequence of
ranges with no gaps and no overlaps for a given component. Components are
independent: a salary change leaves the commission arrangement untouched.

## The payout

| Call | Purpose |
|---|---|
| `GET /payments?payee_employee_id={id}&direction=outbound` | this person's payouts |
| `GET /payments?reference_no=PAYROLL-2026-07` | one bank batch — a payroll batch is just a shared `reference_no` |
| `GET /payments/{payment_id}/detail` | the payout plus what it has been applied to |

`status: paid` means the workspace recorded the payout. Settlement is separate:
a payslip is settled when a payment has been applied to it, and
`outstanding_amount` on the payslip's `/detail` is what remains. An unapplied
payout is a bookkeeping state, not an unpaid wage.

## Checking the figures before approving (reviewer with `payroll.read`)

Reading a batch to check it, without any capability to change it:

```text
GET /invoices?direction=payroll&period_start=2026-07-01   → sum the billed_total values
GET /payments?reference_no=PAYROLL-2026-07                → sum the amounts
```

The two sums must agree. Report the comparison — the batch total, the payout
total, and whether they match — rather than the individual figures behind it.
