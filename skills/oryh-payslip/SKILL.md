---
name: oryh-payslip
description: Use when someone wants to READ pay — "我这个月发了多少"、"我的工资条"、"我的社保扣了多少"、"我去年的调薪记录", or, for a reviewer holding payroll.read, 核对某批工资条与发放金额是否一致 before approving a payout. Everyone can read their OWN pay with this skill and needs no special permission for it. Read-only: it never sets pay, never issues a payslip, and never moves money — that is oryh-payroll (定薪/出工资条/发放) and oryh-payment-approval-flow (审批).
---

# Oryh Payslip (只读)

Pay is the one thing in this workspace that belonging to it does not entitle
you to read. That gate has an important exception, and this skill exists
because the exception had no instructions: **anyone can always read their own
pay.** An employee who cannot check what they were paid has no recourse.

So this skill serves two readers with the same calls:

| Reader | Sees |
|---|---|
| anyone, no capability | their OWN payslips and their OWN pay records |
| a key holding `payroll.read` | everyone's — for review, audit, or 核对 before an approval |

Nothing here writes. If the person wants a raise recorded, a payslip issued, or
a payout made, that is `$oryh-payroll` and it needs `payroll.manage` /
`invoice.manage:payroll`; say so plainly rather than reaching for another tool.

{{include:_common/answer-the-question.md}}

{{include:_common/api-auth-principal.md}}

## Trigger Examples

- "我这个月工资发了多少？"
- "我的工资条发我看看"
- "上个月个税扣了多少？为什么比上上个月多"
- "我今年调过几次薪？"
- "这批工资条合计和发放单对得上吗？" — a reviewer with `payroll.read`
- "小周 7 月拿多少" — needs `payroll.read`; without it this is a 404, and that
  is the gate working, not a fault

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # no payroll capability required to read your own
  employee_id: "{{EMPLOYEE_ID}}"  # who "我的" means
```

## 查工资条

```text
GET /invoices?direction=payroll&payee_employee_id={{EMPLOYEE_ID}}
GET /invoices/{invoice_id}/detail
```

The list is already filtered to what this key may see, so it needs no
permission check of your own — send it and read what comes back.

`/detail` is the one to quote from: it reports `billed_total`, which IS 实发工资
(a payslip declares no total of its own — the sum of the lines is the number),
plus one line per earning and deduction. **增项为正、扣减为负**, so 个税 and
社保 come back negative; report them as deductions rather than reading the minus
sign out loud as if the person were charged twice.

Each line carries its own working in `notes` —
`缴费基数 12000.00 × 8% = 960.00` — because whoever issued it was required to
show it. When someone asks "为什么这个月少了", that field is the answer, and it
is a better answer than any arithmetic you do yourself.

## 查薪资档案

```text
GET /employees/{employee_id}/pay-history            # whole history, newest first
GET /pay-histories?employee_id={{EMPLOYEE_ID}}&in_force_on=2026-07-01
```

`{employee_id}` is `{{EMPLOYEE_ID}}` when the question is 我的 — which it
usually is. Another employee's id there is a 404 without `payroll.read`.

One row is **one term of one person's pay over one date range** —
`base_salary`, `allowance`, `commission`, `bonus`, `overtime_rate`. A raise is
not an edit: it closes the old row (`effective_thru`) and opens a new one, so
"调过几次薪" is answered by the rows, in order, and each one's date range is
the answer to "从什么时候起".

A term may be a scalar `amount`, a `rate` on a stated `basis`, or a `formula`
in words. The server never parses `formula` — read it out as written; do not
compute from it and present the result as a fact.

## 发放到账了吗

```text
GET /payments?payee_employee_id={{EMPLOYEE_ID}}&direction=outbound
GET /payments/{payment_id}/detail
```

`status: paid` means the workspace recorded the payout, and the payslip is
settled when the payment has been applied to it — `outstanding_amount` on the
payslip's `/detail` is what remains. 核销未完成 is a bookkeeping state, not an
unpaid wage; do not tell someone they were not paid on the strength of it.

## What A 404 Means Here

**A payslip you may not read is a 404, never a 403.** That is deliberate: 403
would confirm the document exists, which is most of what the gate protects.

So when a read comes back 404 or an empty list:

- Say the pay is not yours to read, and who to ask (HR, or whoever holds
  `payroll.read`).
- Do **not** retry with a service key, another person's key, or the tenant
  root credential to get around it.
- Do **not** conclude the payroll API is missing and record the figures
  somewhere else. Creating a `business_object` — a custom "工资" object, a note,
  a spreadsheet row — puts real salary data outside the gate that was just
  applied to you, in a place with no read control at all. This is the one
  fallback that turns a refused read into a data leak, and it has happened; it
  is never the right recovery.

## What This Skill Never Does

- Set or change pay, issue a payslip, create or approve a payout — `$oryh-payroll`
  for the first three, `$oryh-payment-approval-flow` for the last.
- Repeat one person's pay to another person, in any summary, total or aside.
  A reviewer holding `payroll.read` reads figures **to check them**, not to
  circulate them.
- Recompute 社保/公积金/个税 and present the result as what the person is owed.
  Those numbers come from the payslip's own lines and their stated working.

## Reference

- [references/api.md](references/api.md): every read path, what each returns
  with and without `payroll.read`, and the exact shape of a payslip line.
