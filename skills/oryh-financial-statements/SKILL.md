---
name: oryh-financial-statements
description: Use when someone asks how the business did or where it stands according to the books in oryh — the profit and loss (income statement) for a month, quarter or year to date, compared with the period before or last year, split by project, cost centre, customer or month; the balance sheet, what the business owns and owes at a day; the cash summary, where the money came from and went; and the workspace's own statement layout (gross profit, a statutory format), set up only once the person confirms it. Every figure is a sum of posted journal entries; you read and explain, you post nothing. Requires ledger.read; writing a layout needs ledger.manage.
required_capability: ledger.read
---

# Oryh Financial Statements

The statements are the book, summed. Every figure is worked out from posted
journal entries each time it is read; nothing is stored, and draft entries
are never counted. You read the statement, say whether it is final, and
explain what moved — in the person's terms, from what the book shows.

You post nothing here. Keeping the book is `oryh-ledger`'s, and a figure
that looks wrong is reported to whoever keeps it, never patched by you.

{{include:_common/answer-the-question.md}}

{{include:_common/confirm-before-you-write.md}}

{{include:_common/api-auth-principal.md}}

## Trigger Examples

- "How did we do in March?"
- "Profit and loss for the year so far, against last year"
- "Which project made money this quarter?"
- "What do we own and owe at the end of June?"
- "Why are expenses up this month?"
- "Set up our income statement in the small-enterprise format"
- "Where did our cash go this quarter?"

## Required Inputs

```yaml
oryh:
<!-- only: bundle -->
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
<!-- /only -->
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
<!-- only: bundle -->
  api_key: "{{ORYH_API_KEY}}"     # ledger.read
<!-- /only -->
```

## First: Are These Figures Final?

Every statement carries what makes it provisional. Read these before the
figures, and say them first:

- `period_status.open_months` — months not closed yet; their figures can
  still move.
- `drafts` — draft entries dated in the span, which the figures leave out.
- `coverage[]` — per month, `missing` (documents whose money counts but no
  entry records) and `stale` (entries for documents since voided).

"These figures are not final: March is still open and 3 invoices are not
in the book yet." Then the figures. Point the person to whoever keeps the
book (`oryh-ledger`) for the gaps; do not post them yourself.

## The Income Statement

`GET /income-statement?date_from=&date_to=&compare=&by=`

- The span: `date_from` and `date_to` (`YYYY-MM-DD`). Only `date_to` reads
  its month; neither reads this month. `date_from=year_start` starts at the
  financial year `date_to` falls in (the workspace's
  `fiscal_year_start_month`).
- `sections[]` — `income` then `expense`, each with `total` and `rows[]`
  (accounts in the chart's order, `depth` for indentation, `summary` for an
  account whose figure is its sub-accounts'). Figures are on their natural
  side: income and expenses both read positive.
- `result.amount` — income − expenses. Negative is a loss.
- `compare` — `previous_period` (default: whole months compare with the
  same number of months before; other spans with the same number of days),
  `previous_year`, or `none`. Each figure then has `compare`, `change` and
  `change_ratio` (null when there was nothing to compare with — say "new",
  not "infinitely up").
- `by` — one of `project`, `cost_center`, `customer`, `vendor`, `employee`,
  `month`. `columns[]` names them; each row has `amounts` per column, and
  entries without that tag fall under `unassigned`. The columns always add
  up to the total. One dimension at a time: read twice for a cross.

## The Balance Sheet

`GET /balance-sheet?as_of=&compare=`

- `sections[]` — `asset`, `liability`, `equity`, natural side, each with
  `total` and `rows[]`.
- Equity carries `earnings_not_yet_closed`: every income and expense
  balance to the day that has not been closed into retained earnings. Before
  the year-end close it is all profit to date; after it, only the current
  year's. Explain it that way; it is not a mistake.
- `balanced` — assets = liabilities + equity. It always holds for a book of
  balanced entries. `false` is a defect in the book: say so plainly and hand
  it to whoever keeps the book. Never explain it away.
- `compare` — `previous_period` (default: the end of the month before),
  `previous_year`, or `none`.
- Who owes what: `GET /ledger-accounts/{id}/parties?as_of=` on a receivable
  or payable account.
- Foreign-currency accounts (a USD bank, a USD receivable) stand at the
  rates they were posted at until the month is revalued. If the workspace
  has them and the month has no revaluation entry (`GET
  /fx-revaluation?as_of=&rate_type=` shows no `revaluation_entry_no` and a
  non-zero `difference`), say the balance sheet holds them at booked rates
  and by how much the read says they differ. Revaluing is `oryh-ledger`'s.

## The Cash Summary

`GET /cash-summary?date_from=&date_to=&compare=`

Money into and out of the **cash accounts** — the ledger accounts marked
`is_cash` (bank and cash on hand; a sub-account of one is cash too).

- `cash_accounts[]` — each with `opening`, `change`, `closing`; `opening`,
  `net_change`, `closing` are their totals.
- `sections[]` — by the type of the account on the other side of the
  money (`income`, `expense`, `asset` such as receivables, `liability`,
  `equity`), each row with `received`, `paid` and `net`. "Of the 52,000
  that came in, 48,000 was customers paying invoices (receivables)."
- `transfers` — moves between cash accounts: no money in or out.
- `basis` states the rule: each entry's cash is attributed to its other
  lines by their own amounts. Quote it when someone asks how a figure was
  split; it is the book's arithmetic, not a judgement about the business.
- `reconciled` — opening + net change = closing. `false` is a defect in
  the book, like an unbalanced balance sheet.
- This is a direct-method view from the book, not a statutory cash flow
  statement; say so if the person needs the statutory one. A
  `cash_summary` layout groups it into the workspace's operating,
  investing and financing lines.

If `cash_accounts` is empty, no account is marked yet. Read the chart, say
which accounts look like bank or cash accounts, and once the person
confirms, mark them: `PATCH /ledger-accounts/{id} {"is_cash": true}`
(`ledger.manage`; only an asset account).

## The Workspace's Layout

The default statements group accounts by type, so they cannot say gross
profit, and the cash summary cannot say operating or financing. A **layout** is the workspace's format — a statutory one, a
management pack — as rows: each sums accounts, sums other rows, or is a
heading. Every statement read applies its default layout when there is one;
`layout_id=` names another, `layout_id=none` reads without.

With a layout the read adds `layout`:

- `lines[]` — the rows in order: `label`, `amount` (null for a heading),
  `compare`/`change` and `amounts` like every figure, and for an accounts
  row the `accounts[]` that fed it. Quote these lines, in their wording.
- `unplaced[]` — accounts with movement that no row takes (on a balance
  sheet, possibly the earnings not yet closed). Their money is still in
  `result`, `totals` and `balanced`, which are always the book's whole. A
  non-empty `unplaced` means the layout and the chart have drifted apart:
  say which accounts and how much, and propose the row they belong on. Do
  not fold them into a line yourself.
- `clashes[]` — an account added since the layout was written that falls
  into two rows; the first row took it. Say so and propose the fix.

### Setting Up A Layout

Which account is cost of sales and which is overhead changes gross profit,
the figure owners and lenders read first. It is the person's decision.

1. Ask which format they report in (the standard, or their accountant's
   management pack). Read the chart: `GET /ledger-accounts`.
2. Propose the rows, mapping the chart by code ranges
   (`{"code_from": "6401", "code_to": "6499"}`) so sub-accounts added later
   still land; a single account by `ledger_account_id` takes its
   sub-accounts too. Totals are `formula` terms with a `sign`. On a balance
   sheet, put `{"earnings_not_yet_closed": true}` on the undistributed
   profit row.
3. Show the proposal as a page — line, label, accounts — with today's
   figures from a read with it applied if you can, and ask the person to
   confirm it. Only then write it, naming them in `confirmed_by`:
   `POST /statement-layouts` (`ledger.manage`).
4. The server refuses (422, naming the row) a formula naming a row that is
   not there or going in a circle, an account of a type the statement does
   not take, and an account feeding two rows. Fix the proposal and ask
   again if the fix changes what the person saw.
5. A change to the rows is `PUT /statement-layouts/{id}/rows` with the
   whole new set and who confirmed it; making it the default is
   `PATCH {"is_default": true}`.

## Explaining A Movement

1. Name the largest changes first, with the figures: "Expenses rose 18,400,
   most of it rent (12,000, new this month)."
2. When the cause is not obvious from the account, read the entries behind
   it: `GET /ledger-accounts/{id}/ledger?date_from=&date_to=` lists each
   line with its entry and description.
3. Say only what the book shows. If the entries do not say why, say that
   and suggest who would know. Never invent a cause.

## What This Skill Never Does

- Post, reverse, waive or close anything — that is `oryh-ledger`'s.
- Present figures as final while months are open or documents are missing.
- Add up accounts by hand when a statement read answers the question.
- Write or change a layout the person has not confirmed, or hide an
  unplaced account inside a line.
- Mix in documents the book does not record: a budget's actuals come from
  documents and may differ; say which one you are quoting.

## Reference

- [references/api.md](references/api.md): request templates.
