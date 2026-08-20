# Payroll API

Every path hangs off `api_base_url` exactly as given — no version prefix to add.

Everything here is behind `payroll.read`. Without that capability a credential
sees only the records of the employee it is linked to, and someone else's
payslip is a **404, not a 403** — 403 would confirm the document exists, which
is most of what the gate protects.

## Pay records

| Call | Purpose |
|---|---|
| `GET /pay-histories` | every term this key may see |
| `GET /pay-histories?employee_id={id}` | one person's terms |
| `GET /pay-histories?component=commission` | everyone on a commission arrangement |
| `GET /pay-histories?in_force_on=2026-07-01` | what was in force on a date |
| `POST /pay-histories` | set or revise pay — closes the previous term and opens the new one |
| `GET /pay-histories/{pay_history_id}` | one record |
| `PATCH /pay-histories/{pay_history_id}` | correct a mistake — refused once a payslip cites it |
| `GET /employees/{employee_id}/pay-history` | one person's whole history, newest first |

### Setting and revising pay

```json
POST /pay-histories
{
  "employee_id": "employee-uuid",
  "component": "base_salary",
  "effective_from": "2026-07-01",
  "amount": 15000.0,
  "period_type": "month",
  "currency": "CNY",
  "notes": "revision on confirmation of employment",
  "custom_fields": {"social_insurance_base": 12000, "housing_fund_base": 12000}
}
```

```json
POST /pay-histories
{
  "employee_id": "employee-uuid",
  "component": "commission",
  "effective_from": "2026-07-01",
  "rate": 0.03,
  "basis": "collections that month on contracts this person owns"
}
```

- The response is `{"current": {...}, "superseded": {...}}`. `superseded` is
  `null` for a person's first record of that component; otherwise its
  `effective_thru` is the day before `effective_from`, set in the same
  transaction. There is no "change the amount" call.
- **Only the same `component` is superseded.** A pay rise does not close a
  commission arrangement.
- A term states an `amount`, a `rate` **with** its `basis`, or a `formula` in
  words. None of the three is a 422; a `rate` without a `basis` is a 422. The
  server never parses `formula`.
- `component` must be an active option:
  `GET /type-options?family=pay_component_type` — ships `base_salary`,
  `allowance`, `commission`, `bonus`, `overtime_rate`, `other`.
- `period_type`: `GET /type-options?family=pay_period_type` — `month`, `hour`,
  `day`, `year`.
- Two records of the same component in force on the same day is a 409, whether
  from an overlapping range or the same `effective_from` twice.
- `effective_thru` is only for closing a term with no successor (someone
  leaving). A raise sets it for you.
- `PATCH` refuses (409) once an `invoice_item` cites the record.

## Payslips

A payslip is an invoice with `direction: "payroll"`. Everything in
`$oryh-receivables`'s invoice reference applies, plus what is below.

| Call | Purpose |
|---|---|
| `GET /invoices?direction=payroll` | every payslip this key may see |
| `GET /invoices?direction=payroll&payee_employee_id={id}` | one person's payslips |
| `GET /invoices?direction=payroll&outstanding=true` | issued but not yet paid out |
| `POST /invoices` | file one, with its lines |
| `POST /attachments` | upload the payslip document; the id goes in `attachment_id` |
| `GET /invoices/{invoice_id}/attachments/{attachment_id}/content` | read it back — only a credential that may see the payslip may see its file |
| `GET /invoices/{invoice_id}/detail` | the lines and `billed_total` (net pay) |
| `PATCH /invoices/{invoice_id}` | correct the header, or move the status |

```json
POST /invoices
{
  "direction": "payroll",
  "employee_id": "{{EMPLOYEE_ID}}",
  "payee_employee_id": "employee-uuid",
  "title": "July 2026 salary",
  "period_start": "2026-07-01",
  "period_end": "2026-07-31",
  "currency": "CNY",
  "items": [
    {"invoice_item_type": "payroll_salary", "product_name_snapshot": "Base salary",
     "amount": 15000.0, "pay_history_id": "pay-history-uuid",
     "notes": "15000.00 a month (from 2026-07-01)"},
    {"invoice_item_type": "payroll_commission", "product_name_snapshot": "Sales commission",
     "amount": 2400.0, "pay_history_id": "pay-history-uuid",
     "notes": "collections 80000.00 × 3% = 2400.00"},
    {"invoice_item_type": "payroll_allowance", "product_name_snapshot": "Travel allowance",
     "amount": 500.0, "notes": "role travel allowance 500.00/month"},
    {"invoice_item_type": "payroll_pension_ee", "product_name_snapshot": "Pension (employee)",
     "amount": -960.0, "notes": "contribution base 12000.00 × 8% = 960.00"},
    {"invoice_item_type": "payroll_iit", "product_name_snapshot": "Individual income tax",
     "amount": -389.4, "notes": "cumulative withholding: taxable income 12989.00 × 3%"}
  ]
}
```

- `payee_employee_id`, `period_start` and `period_end` are all required for a
  payroll invoice (422 otherwise). `employee_id` stays the HR officer.
- **One payslip per person per `period_start`** — a second is a 409. This is a
  database constraint, not a convention.
- **No `total_amount`** — a 422. Net pay is the sum of the lines, reported as
  `billed_total` on `/detail`.
- A payslip names no customer, no vendor, and no order; all four are 422s.
- `direction` is not correctable. A payslip filed against the wrong person is
  voided and refiled.

### Payslip lines

`invoice_item_type` comes from a different vocabulary than an ordinary invoice:
`GET /type-options?family=payroll_item_type`. Each entry carries a `sign`, and
a line whose amount contradicts it is a 422.

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

`POST /type-options` extends the family; an entry added here **must** declare
its `sign`, and one without it is refused on use.

- **Every line shows its working**: either `pay_history_id` (the record the
  number came from) or a non-empty `notes` stating the calculation. Neither is
  a 422. The rates behind social insurance, the housing fund and income tax are
  not stored anywhere in this
  database, so the line is the only record of how the figure was reached.
- `pay_history_id` may only cite a record belonging to `payee_employee_id`
  (422 otherwise).
- An amount of `0` is refused for a signed type — a line that moves nothing is
  not a line.
- `sales_order_item_id` and `purchase_order_item_id` are both 422s on a
  payslip line.

## Paying it out

Ordinary outbound payments — `$oryh-payables`'s reference covers the shape.
Payroll specifics:

```json
POST /payments
{
  "direction": "outbound",
  "employee_id": "{{EMPLOYEE_ID}}",
  "payee_employee_id": "employee-uuid",
  "amount": 16550.6,
  "currency": "CNY",
  "payment_method": "bank_transfer",
  "reference_no": "PAYROLL-2026-07",
  "status": "paid"
}
```

```json
POST /payments/{payment_id}/apply
{
  "lines": [
    {"applied_to_type": "invoice", "applied_to_id": "payslip-uuid", "amount_applied": 16550.6}
  ],
  "idempotency_key": "payroll-2026-07-zhou"
}
```

- One payment per person; the shared `reference_no` IS the batch. There is no
  batch object.
- `payee_employee_id` names the person paid; `employee_id` stays the officer.
- Over-applying is a 409 naming what is left on whichever side ran out.
- A wrong match is reversed with a negative `amount_applied`, never deleted.
- The payout and the payslip must share a currency (409 otherwise).

## Read gate

| Path | Without `payroll.read` |
|---|---|
| `GET /invoices` | payroll rows filtered out, except the key's own employee's |
| `GET /invoices/{id}`, `/detail` | 404 for someone else's payslip |
| `GET /payments`, `GET /payments/{id}` | payouts settling someone else's payslip filtered / 404 |
| `GET /payment-applications` | rows pointing at someone else's payslip filtered |
| `GET /object-directory` | the payroll count is filtered too |
| `GET /pay-histories`, `GET /employees/{id}/pay-history` | own records only; 404 for another employee |

A **tenant service key bypasses the permission layer entirely** and therefore
reads all pay. That is what that credential means — the company issued it to
itself — but the consequence is real: run payroll agents on a user-bound key
holding `payroll.read` if the workspace cares who can read salaries.
