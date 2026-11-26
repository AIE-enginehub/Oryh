---
name: oryh-financial-statements
description: Use when someone asks how the business did or where it stands according to the books in oryh — the profit and loss (income statement) for a month, quarter or year to date, compared with the period before or last year, split by project, cost centre, customer or month; and the balance sheet, what the business owns and owes at a day. Every figure is a sum of posted journal entries; you read and explain, you post nothing. Requires ledger.read.
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

{{include:_common/api-auth-principal.md}}

## Trigger Examples

- "How did we do in March?"
- "Profit and loss for the year so far, against last year"
- "Which project made money this quarter?"
- "What do we own and owe at the end of June?"
- "Why are expenses up this month?"

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
- Mix in documents the book does not record: a budget's actuals come from
  documents and may differ; say which one you are quoting.

## Reference

- [references/api.md](references/api.md): request templates.
