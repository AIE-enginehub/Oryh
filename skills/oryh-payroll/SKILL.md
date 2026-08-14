---
name: oryh-payroll
description: Use when HR or 薪酬专员 needs to set or change someone's pay terms (定薪/调薪, including commission and bonus arrangements), 生成工资条 for a period, and 发放工资 with the payout matched to each payslip. Covers the whole payroll arc for one role. Not for approving the payout (that is oryh-payment-approval-flow), not for expense reimbursement (oryh-expense-submit), and not for billing customers or suppliers (oryh-receivables / oryh-payables).
required_capability: payroll.manage
---

# Oryh Payroll

HR 的一条龙: 定薪 → 出工资条 → 发放 → 核销.

**The server computes nothing.** Read that again before the first call. 社保
基数与封顶、公积金比例、个税累计预扣、专项附加扣除、年终奖计税方式 — none of it
is stored here and none of it is calculated here. Those are national and local
policy, they change, and a records layer that quietly applied a rate would be
inventing policy while looking like arithmetic. **You do the calculation** from
what you know and from the workspace's own workflow definition, and you record
the result together with how you reached it.

The three facts that follow from that:

- **Every payslip line must show its working.** A line either cites the pay
  record it came from (`pay_history_id`) or states the calculation in `notes`
  — `缴费基数 12000.00 × 8% = 960.00`. A line that does neither is refused
  (422), because nothing else in this database could reconstruct why the
  number was 960 and not 860.
- **A payslip is an invoice.** `direction: "payroll"`, one `InvoiceItem` per
  earning or deduction, **增项为正、扣减为负**. So 核销, 账龄, 审批 and the
  audit invariants are the ones you already know.
- **Pay is the one read that belonging to the workspace does not entitle you
  to.** Payslips and pay records are gated behind `payroll.read`; without it a
  credential sees only its own. Do not work around this, and do not repeat a
  colleague's figures to someone who asked.

{{include:_common/answer-the-question.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/read-before-you-decide.md}}

{{include:_common/leave-no-orphan-work.md}}

## Trigger Examples

- "给新来的销售定薪，月薪 15000，提成按回款 3%"
- "小周 7 月起调薪到 18000"
- "生成 7 月份的工资条"
- "这个月工资发了，把每个人的核销一下"
- "小周去年 3 月拿多少"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # needs payroll.manage, payroll.read,
                                  # invoice.manage:payroll, payment.record, payment.apply
  employee_id: "{{EMPLOYEE_ID}}"  # the HR 经办人 recorded on what you file
```

定薪 (`payroll.manage`) and 出工资条 (`invoice.manage:payroll`) are separate on
purpose — deciding what someone earns and producing the monthly document are
different jobs. If your key holds only one, do that half and say plainly which
step someone else must take.

发放 needs `payment.record`, which is what lets you **create and submit** the
payout — and deliberately not approve it: moving it past submitted needs
`payment.advance`, which belongs to whoever the workflow definition names. A
403 on `POST /payments` means this key files pay but does not disburse it; hand
the batch over rather than looking for another credential.

**只读的人不需要这个技能.** 本人查自己的工资条、审批人核对一批工资条合计，都走
`$oryh-payslip` — it is ungated, so everyone already has it. This skill is the
write half.

## 定薪与调薪

A `pay_history` row is **one term of one person's pay, over one date range**.
`component` says which term:

| component | shape | example |
|---|---|---|
| `base_salary` | `amount` + `period_type` | 月薪 15000 |
| `allowance` | `amount` | 交通补贴 500/月 |
| `commission` | `rate` + `basis` | 回款额的 3% |
| `bonus` | `formula` (words) | 达标发 2 个月工资 |
| `overtime_rate` | `amount` or `formula` | 平时 1.5 倍 |

State the term in whichever of the three shapes fits — a scalar `amount`, a
proportional `rate` with the `basis` it applies to, or a `formula` in words for
what fits neither (阶梯提成, 绩效系数). At least one is required; a `rate`
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
  "basis": "本人负责合同的当月回款额",
  "notes": "季度结算，随次月工资发放"
}
```

- **调薪 is not editing a number.** Post a new record from the new date; the
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
  commission rate, their bonus arrangement, and their 社保/公积金缴费基数 (in
  `custom_fields`, where it inherits the same effective dating). What does not:
  company-wide rules (a workflow definition), and national policy (nowhere —
  you already know it).

Reading: `GET /employees/{employee_id}/pay-history` is one person's whole
history; `GET /pay-histories?component=commission&in_force_on=2026-07-01` is
everyone on a rate today.

## 生成工资条

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
  "title": "2026年7月工资",
  "period_start": "2026-07-01",
  "period_end": "2026-07-31",
  "items": [
    {"invoice_item_type": "payroll_salary", "product_name_snapshot": "基本工资",
     "amount": 15000.0, "pay_history_id": "...", "notes": "月薪 15000.00（2026-07-01 起）"},
    {"invoice_item_type": "payroll_commission", "product_name_snapshot": "销售提成",
     "amount": 2400.0, "pay_history_id": "...", "notes": "回款 80000.00 × 3% = 2400.00"},
    {"invoice_item_type": "payroll_pension_ee", "product_name_snapshot": "养老保险（个人）",
     "amount": -960.0, "notes": "缴费基数 12000.00 × 8% = 960.00"},
    {"invoice_item_type": "payroll_iit", "product_name_snapshot": "个人所得税",
     "amount": -389.4, "notes": "累计预扣法：应纳税所得额 12989.00 × 3%"}
  ]
}
```

- **The whole payslip is one call.** Lines come with it; a bad line rolls the
  payslip back rather than leaving half a document.
- **A payslip declares no total of its own.** 实发工资 IS the sum of the lines —
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
- **A deduction that computes to zero is not a line.** Somebody whose 累计应纳
  税所得额 is negative owes no 个税 this month; a `0.00` 个税 row is refused
  (422), because a line that moves nothing is not a movement. Do not fake it as
  `-0.01`, and do not silently drop the reasoning either — put it in the
  payslip's `remarks`: "本月个税 0：累计应税 −7243.11，为负数，无需预扣". The
  employee needs to see it was considered, not omitted.

The employer's contributions and the remittance to 税务局/公积金中心 are the
next step, not part of the payslip: file them as an ordinary **purchase**
invoice against the collecting authority as vendor, with one line per
contribution type, and settle it with an outbound payment. 社保费 is collected
by the tax authority; 公积金 by the housing fund centre — two payables, two
payments.

**Per person, in order**: read the terms in force
(`GET /employees/{id}/pay-history?in_force_on=2026-07-01`), work out each
figure, then file. When the workspace has 考勤 or 提成 numbers you need, get
them from the timesheets and the settlement ledger — never assume a full month.

## 发放

One payment per person, all sharing a `reference_no` as the bank batch number.
That is the whole of "发薪批次" — a group of payments with the same reference,
no extra object.

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

**Always pass an `idempotency_key`** — this endpoint writes money, and a retry
without one applies twice. A repeat with the same key returns `replayed: true`
and writes nothing.

Whether the batch needs approval before the bank sees it is the workspace's
decision, in its workflow definition — `$oryh-payment-approval-flow` runs it.
Do not create the payout in a terminal state to skip a queue you were told
about.

## 被退回之后

A payslip or a payout that comes back `returned` leaves a rework todo on you,
and the todo's `description` plus the latest `returned` approval record's
`comment` say exactly what to fix. Read both before touching anything —
`GET /approval-records?entity_type=invoice&entity_id={id}`.

**修原单，不要作废重做.** The 一人一期一张 constraint only counts live payslips,
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

## What This Skill Never Does

- **Calculate 五险一金 or 个税 as if the server had a table.** You compute; you
  record what you computed and how. If you are unsure of a current rate or
  ceiling, **look it up before guessing**:
  `GET /policies?category=external_standard&in_force_on=2026-07-15` returns the
  standard the workspace has recorded for that date, with its `code`, `version`
  and publisher — so the line's working can read
  `缴费基数 36921 × 8%（依据 FIN-2026-03 v1）`. Nothing in force means ask: a
  confidently wrong deduction is worse than a question, and `$oryh-policy` is
  where the answer gets recorded so next month is cheaper.
- **Put the employer's half on the payslip.** The shipped types are all `_ee`:
  a payslip carries only what is withheld from the person. 单位承担的社保和
  公积金 never appear on it, and computing 用工总成本 from a payslip alone gives
  the wrong number.
- Store policy rates in `pay_histories`. Only facts about a person go there.
- Repeat one employee's pay to another person, or work around the read gate.
- Issue a second payslip for a period, or restate a payslip's total.
- Edit a pay record a payslip has cited — that is a correction to the payslip,
  or a new record from a new date.
- Decide the raise, the bonus, or the write-off. Those are the principal's
  decisions; you record them.
- Approve the payout, or move it to paid on your own reading — that is
  `$oryh-payment-approval-flow`.
- Import history — that is `$oryh-data-migration`.
- Answer "我这个月发了多少" — that is `$oryh-payslip`, which every employee
  holds and which needs no payroll capability to read one's own pay.

## Reference

- [references/api.md](references/api.md): every endpoint, the pay-term shapes,
  the payslip item vocabulary with its signs, and the guards with the exact
  conditions that raise them.
