---
name: oryh-budget
description: Use to plan and follow a workspace's budget in oryh — set the year's plan (a marketing pot, labour cost, a sales target), change it with a reason, read where it stands — building the plan, posting changes with their reasons, reading planned against requested, committed, actual, paid and the sales gap. Requires budget.manage (reading needs budget.read_all; labour actuals also payroll.read).
required_capability: budget.manage
---

# Oryh Budget

A budget is what the business planned for the year and the running answer
to "where do we stand against it". It has two halves, and you only ever
write one of them:

- **The plan** — each line's amount, month by month. It moves only through
  a **budget change** with its reason; a posted change is history and is
  corrected by another change, never edited.
- **What was used** — derived by the server from the documents, on every
  read. You never enter spend into a budget: a marketing invoice, a payslip,
  a sales invoice reaches its line by itself.

The server reports and never refuses spending for being over budget. Whether
going over needs the owner's sign-off is the workspace's approval flow,
which reads `GET /budget-impact`.

{{include:_common/answer-the-question.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/confirm-before-you-write.md}}

## Trigger Examples

- "This year: marketing 300,000 for the year, labour 80,000 a month, sales target 5 million"
- "How much is left in marketing?"
- "Move 2,000 from office to marketing"
- "Close the year and carry what marketing did not spend into next year"
- "Split the sales target by salesperson: Ana 3 million, Ben 2 million"
- "Tell me when marketing passes 80%, and show this year's cash plan"

## Required Inputs

```yaml
oryh:
<!-- only: bundle -->
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
<!-- /only -->
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
<!-- only: bundle -->
  api_key: "{{ORYH_API_KEY}}"     # budget.manage
<!-- /only -->
  employee_id: "{{EMPLOYEE_ID}}"  # who files the changes
```

## How Lines Collect

Three line categories gather their documents with nobody tagging anything;
say which when you set a line up:

| Category | Budget | Collects |
|---|---|---|
| `labour` | spend | payslips' **gross** pay (never the net total), plus remittance-invoice lines typed `employer_social_insurance` / `employer_housing_fund`; `withheld_remittance` lines are already inside gross and count nowhere |
| `marketing` | spend | expense items with category `marketing`, purchase-invoice lines typed `marketing` |
| `sales` | income | issued sales invoices (tax lines excluded); confirmed orders as *ordered*; open deals as the *pipeline* forecast |

Any other category (`office`, `travel`, `rent`, …) receives only spend tagged
to it with `budget_line_id`. A budget has one live line per collecting
category, and two overlapping budgets may not both collect the same one.

## Setting Up The Year

1. **Read first**: `GET /budgets?status=active` — one live budget per
   direction and year is the usual shape; a second one collecting marketing
   for the same months is refused.
2. **Vocabularies once**: `GET /type-options?family=budget_category`,
   `family=budget_type`, `family=budget_change_type`.
3. **Spend budget with its lines**: `POST /budgets {"name", "direction":
   "spend", "period_start": "2026-01-01", "period_end": "2026-12-31",
   "currency", "lines": [{"line_code": "LAB", "name", "category": "labour"},
   {"line_code": "MKT", "category": "marketing", …}]}`. An income budget is
   the same with `"direction": "income"` and one `sales` line.
4. **The figures are a change**: `POST /budget-changes {"budget_id",
   "employee_id", "change_type": "original", "reason", "status": "posted",
   "lines": [{"line_code": "MKT", "period_month": "2026-01-01", "amount":
   300000}]}` — an annual pot is one line in its first month; a monthly
   figure is twelve lines. `status: "posted"` files and posts in one call
   (the owner's path); leave it off to keep a draft. A spreadsheet goes
   through `POST /budgets/{id}/import` with `dry_run` first.
5. **Activate**: `PATCH /budgets/{id} {"status": "active"}`. A draft collects
   too; activation is where the overlap rule is checked.

## Changing The Plan

Every change states its reason; the owner's words go in `reason`.

- More or less for a line: `change_type` `increase` (positive lines) or
  `decrease` (negative lines).
- Between lines: `transfer`, lines that net to exactly zero — `-2000` on
  `OFF`, `+2000` on `MKT`.
- Year end: `POST /budgets/{id}/close` reads back what each spend line left
  unspent; a `carry_forward` change on next year's budget with
  `source_budget_id` moves it — negative lines on the old budget's lines,
  positive on the new, netting to zero. Nothing carries forward by itself.

In a workspace that approves budget changes, file without `status`, submit
with `POST /budget-changes/{id}/submit`, and the holder of `budget.advance`
approves and posts. A posted change is never deleted.

## A Cost Centre's Budget

A larger business plans a spend budget per cost centre as well:
`POST /budgets {…, "cost_center_id": "<Operations>"}`. It collects by the
same rules as the company budget but reads only documents booked to that
centre or one under it — beside the company budget, never added to it, so
the company figure stays the whole. One live budget per scope (the company,
or one centre) collects a category in a period. A tag names one budget's
line; the company budget collects a centre-tagged line by its rules (or
reports it unbudgeted), and a centre line can only be tagged on a document
booked to that centre. A document is booked to the centre its writer names,
never one the server infers — when you file a claim, request, order or bill,
name the centre by the workspace's rule (see $oryh-master-data). Centres
themselves are master data. Income stays on the company budget.

## Splitting The Sales Target

A sales target split by salesperson, territory, customer or product category
is a set of **sub-targets** under the `sales` line. Each takes the part of
the line's documents that match it and is read beside the line — its plan
never adds to the budget's total, so a split by salesperson and a split by
territory can both stand.

1. `POST /budget-lines {"budget_id", "line_code": "S-ANA", "name": "Ana",
   "parent_line_id": "<the sales line>", "employee_id": "<Ana>"}` — exactly
   one of `employee_id`, `territory_id`, `customer_id`,
   `product_category_id`. One live sub-target per person (or territory, …)
   under a line.
2. Plan it like any line, with a change (`original` / `increase` /
   `decrease`). A `transfer` moves money between sub-targets of one line, or
   between top-level lines — never from one to the other.

What matches: the salesperson is the sales order's owner, else the
customer's account owner; the territory is the customer's (a territory takes
everything under it); the product category is each invoice line's product's
(a shelf takes its sub-shelves); a deal's pipeline is shared over its
product lines. The execution read gives each line's `sub_targets` and its
`splits`: per dimension, how far the sub-targets' plans fall short of the
line's own (`unplanned`) and what the line took that none of them matches
(`outside_invoiced`) — say both, a split that leaves money out is a plan
question for the owner.

## Alerts

The server raises no alerts: when a line's progress warrants telling someone,
and whom, is the workspace's rule. Read it first:
`GET /business-rules?kind=policy&in_force_on=<today>&keyword=budget` (or
wherever that workspace filed it). If nothing is written, ask the owner what
they want to hear about — a common answer is spend at 80% and 100%, income at
100% — and suggest writing it down as a rule.

Then read `GET /budgets/{id}/execution` and compare each line's figure to the
rule: spend `percent_consumed` (requested + committed + actual over plan),
income `percent_achieved` (invoiced over target). For a line that has crossed
a percent, tell the line's owner (else the budget's) with `POST /todos`,
`entity_type: budget`, `entity_id` the budget. Keep one open todo per person
per budget: if one is open, update it (`PATCH /todos/{id}`) rather than add a
second. Assigning to someone else needs `todos.assign`; without it, report
the crossing to the person you are working for. In the todo's words, give
the percent, never an amount: a labour
line's amounts are pay. Say which rule you applied. Run this when the owner
asks to be told, or as part of a regular check; nothing runs on a clock.

## Reading Where It Stands

`GET /budgets/{id}/execution` per line and month:

- spend — `planned`, `requested` (approved purchase requests not yet
  ordered), `committed` (confirmed orders not yet invoiced), `actual`,
  `available` = planned − requested − committed − actual (negative is said
  out loud, not hidden), `percent_used` (actual over plan) and
  `percent_consumed` (requested + committed + actual over plan), `paid`
  (cash out), and `unbudgeted` spend no line
  took — name it, it is money nobody planned;
- income — `planned`, `ordered`, `invoiced`, `gap` = planned − invoiced,
  `received`, and the `pipeline` beside it in full and `pipeline_weighted`;
  a pipeline is a forecast, never "achieved".

Answer in the owner's words: "marketing is 62% spent with five months left;
labour is on plan; sales are 8% behind, with 140k weighted pipeline due this
quarter". `GET /budget-lines/{id}/documents?stage=actual` names what is
behind a figure.

The year's cash plan: `GET /budget-cash?income_budget_id=&spend_budget_id=`
— per month, planned income less planned spend, cash received less cash
paid (with `unbudgeted_paid`, cash out no line took), and both running
totals. Say where the cumulative net goes lowest; that month is the one the
owner needs to see.

A labour line's figures beyond its plan are pay. Without `payroll.read` they
come back `null` with `redacted: true` and the budget's totals say
`totals_exclude_labour` (the cash read, `paid_excludes_labour`) — say that
you could not see them, never guess them.

## What This Skill Never Does

- Enter spend or income into a budget — documents carry it; a figure that
  looks wrong is a document to correct ($oryh-payables, $oryh-receivables,
  $oryh-payroll), or a line to tag.
- Edit or delete a posted change — correct it with another change.
- Refuse or hold up spending because a line is over — report it; the
  workspace's approval flow decides.
- Add currencies together — one budget, one currency.

## Reference

- [references/api.md](references/api.md): request templates.

Chinese request aliases and original example wording are available in
[locale examples](locales/zh-CN/examples.json); preserve user-provided names and text.
