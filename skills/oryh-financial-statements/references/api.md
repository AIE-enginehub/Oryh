# Financial Statements API

<!-- only: bundle -->
Every path hangs off `api_base_url` exactly as given — no version prefix to add.
<!-- /only -->

{{include:_common/api-conventions.md}}

## Statements

```text
GET    /income-statement?date_from=&date_to=&compare=&by=&layout_id=   → sections[] income, expense {total, rows[] {account_code, name, depth, summary, amount, compare?, change?, change_ratio?, amounts?}}; result {amount, …}; columns[] with `by`; period_status, drafts, coverage[]
GET    /balance-sheet?as_of=&compare=&layout_id=                       → sections[] asset, liability, equity (equity.earnings_not_yet_closed); totals {assets, liabilities_and_equity}; balanced; period_status, drafts, coverage[]
```

```text
GET    /cash-summary?date_from=&date_to=&compare=&layout_id=   → cash_accounts[] {opening, change, closing}; opening, net_change, closing; sections[] income, expense, asset, liability, equity {net, rows[] {account_code, name, received, paid, net}}; transfers {count, amount}; basis; reconciled; period_status, drafts, coverage[]
PATCH  /ledger-accounts/{id}   {"is_cash": true}       ledger.manage — mark a bank or cash account (asset only)
GET    /ledger-accounts?is_cash=true                   → the cash accounts
```

`date_from` is `YYYY-MM-DD` or `year_start`; `compare` is `previous_period`
(default), `previous_year` or `none`; `by` is one of `project`,
`cost_center`, `customer`, `vendor`, `employee`, `month`. `layout_id`
defaults to the statement's default layout; `none` reads without. With a
layout, `layout` is `{id, name, confirmed_by, lines[] {row_no, code, label,
kind, amount, compare?, change?, amounts?, accounts[]?}, unplaced[],
clashes[]}`.

## Layouts

```text
GET    /statement-layouts?statement=&status=        → layouts with rows[]
GET    /statement-layouts/{id}
POST   /statement-layouts                           ledger.manage — {statement, name, is_default?, confirmed_by, rows[]}
PATCH  /statement-layouts/{id}                      ledger.manage — {name?, is_default?, status?: active|archived}
PUT    /statement-layouts/{id}/rows                 ledger.manage — {rows[], confirmed_by}: replaces every row
```

`statement` is `income_statement`, `balance_sheet` or `cash_summary` (its
rows group the accounts on the other side of the money). A row:

```json
{"row_no": 20, "code": "cost_of_sales", "label": "Cost of sales", "kind": "accounts",
 "accounts": [{"code_from": "6401", "code_to": "6499"}], "sign": 1}
{"row_no": 30, "code": "gross_profit", "label": "Gross profit", "kind": "total",
 "formula": [{"code": "revenue"}, {"code": "cost_of_sales", "sign": -1}]}
{"row_no": 5, "code": "operating_heading", "label": "Operating", "kind": "heading"}
```

An account reference is one of `{"ledger_account_id"}` (with its
sub-accounts), `{"code_from", "code_to"}` (inclusive, by code order, with
sub-accounts), or `{"earnings_not_yet_closed": true}` (balance sheet only).
`sign: -1` subtracts the row (a contra line). Refused with 422: a formula
naming a code not in the layout, a heading, or itself in a circle; an
account of a type the statement does not take; an account feeding two rows.

## Behind A Figure

```text
GET    /accounting-settings                              → functional_currency, fiscal_year_start_month, retained_earnings_account_id
GET    /ledger-accounts?account_type=&parent_id=          → the chart
GET    /ledger-accounts/{id}/ledger?date_from=&date_to=   → an account's lines with a running balance
GET    /ledger-accounts/{id}/parties?as_of=               → a receivable or payable per party
GET    /ledger-coverage?period=                           → which documents a month's counts name
```
