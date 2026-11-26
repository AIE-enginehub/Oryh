# Financial Statements API

<!-- only: bundle -->
Every path hangs off `api_base_url` exactly as given — no version prefix to add.
<!-- /only -->

{{include:_common/api-conventions.md}}

## Statements

```text
GET    /income-statement?date_from=&date_to=&compare=&by=   → sections[] income, expense {total, rows[] {account_code, name, depth, summary, amount, compare?, change?, change_ratio?, amounts?}}; result {amount, …}; columns[] with `by`; period_status, drafts, coverage[]
GET    /balance-sheet?as_of=&compare=                       → sections[] asset, liability, equity (equity.earnings_not_yet_closed); totals {assets, liabilities_and_equity}; balanced; period_status, drafts, coverage[]
```

`date_from` is `YYYY-MM-DD` or `year_start`; `compare` is `previous_period`
(default), `previous_year` or `none`; `by` is one of `project`,
`cost_center`, `customer`, `vendor`, `employee`, `month`.

## Behind A Figure

```text
GET    /accounting-settings                              → functional_currency, fiscal_year_start_month, retained_earnings_account_id
GET    /ledger-accounts?account_type=&parent_id=          → the chart
GET    /ledger-accounts/{id}/ledger?date_from=&date_to=   → an account's lines with a running balance
GET    /ledger-accounts/{id}/parties?as_of=               → a receivable or payable per party
GET    /ledger-coverage?period=                           → which documents a month's counts name
```
