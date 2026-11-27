# Ledger API

<!-- only: bundle -->
Every path hangs off `api_base_url` exactly as given — no version prefix to add.
<!-- /only -->

{{include:_common/api-conventions.md}}

## Settings and the chart

```text
GET    /accounting-settings            → the functional currency (null until set)
PUT    /accounting-settings            → {functional_currency, retained_earnings_account_id?, fiscal_year_start_month?}; the currency is fixed once anything posted
GET    /ledger-accounts?account_type=&parent_id=&subledger=&status=&is_cash=&keyword=   → the chart, code order; `summary` marks accounts with sub-accounts
POST   /ledger-accounts                → {account_code, name, account_type, parent_id?, subledger?, currency?, description?, is_cash?}
PATCH  /ledger-accounts/{id}           → name, description, parent_id, status, is_cash; code, type, subledger, currency only before it has lines
```

## Entries

```text
GET    /journal-entries?status=&source_type=&source_id=&source_event=&ledger_account_id=&posting_date_from=&posting_date_thru=
POST   /journal-entries                → {posting_date, description, status?: draft|posted, source_type?, source_id?, source_event?, entry_no?,
                                          lines: [{ledger_account_id, debit | credit, customer_id?, vendor_id?, employee_id?,
                                                   cost_center_id?, project_id?, currency?, foreign_amount?, exchange_rate?, description?}]}
PATCH  /journal-entries/{id}           → a draft: posting_date, description, lines (replaces all)
DELETE /journal-entries/{id}           → a draft only
POST   /journal-entries/{id}/post      → a draft becomes posted
POST   /journal-entries/{id}/reverse   → {posting_date?, description?}: posts the mirror; once per entry
```

## Waivers

```text
GET    /ledger-waivers?source_type=&source_id=&source_event=&revoked=   → newest first; revoked=false for live only
POST   /ledger-waivers                 → {source_type, source_id, source_event?, reason, decided_by?}; refused while a posted entry records the fact
POST   /ledger-waivers/{id}/revoke     → {reason?}; once; the waiver stays, revoked
```

## Periods

```text
GET    /accounting-periods?status=
POST   /accounting-periods/close       body {"period": any day in the month, "reason"?}; drafts in the month block it
POST   /accounting-periods/reopen      body {"period", "reason"}; the reason is required
```

## Reads

```text
GET    /trial-balance?date_from=&date_to=                 → per account: opening, debit, credit, closing, natural_closing; totals
GET    /income-statement?date_from=&date_to=&compare=&by=&layout_id=  → income and expenses, the result, a layout's lines; see oryh-financial-statements
GET    /balance-sheet?as_of=&compare=&layout_id=                     → assets, liabilities, equity with earnings not yet closed; balanced
GET    /cash-summary?date_from=&date_to=&compare=&layout_id=          → money in and out of the is_cash accounts by the other side; reconciled
GET    /ledger-coverage?period=&families=             → per family counted / recorded / waived / missing (by direction for invoices and payments); missing[] {family, id, number, day, amount, currency, party}; waived[] {…, waiver_id, source_event, reason, decided_by}; stale[] {entry_no, source_type, source_id, why}
GET    /ledger-accounts/{id}/ledger?date_from=&date_to=&page=&size=   → opening, a page of lines with running balance, total_lines, closing
GET    /ledger-accounts/{id}/parties?as_of=               → a subledger account's balance per party
```

## Foreign Currency

```text
GET    /exchange-rates?from_currency=&to_currency=&rate_type=&date_from=&date_to=   → rates, newest day first
GET    /exchange-rates/lookup?from_currency=&to_currency=&rate_type=&on=   → {exchange_rate_id, rate, rate_date, rate_type, source, inverted, stated}; 404 when none
POST   /exchange-rates                 ledger.manage — {from_currency, to_currency, rate, rate_date, rate_type, source}
POST   /exchange-rates/import          ledger.manage — {rates: [...]}: all or nothing; an identical row is skipped
PATCH  /exchange-rates/{id}            ledger.manage — {rate?, source?}; 409 once a line cites it
DELETE /exchange-rates/{id}            ledger.manage — 409 once a line cites it
GET    /fx-revaluation?as_of=&rate_type=   (or &rates=USD:7.82,CNY:1.083)
       → rows[] {account_code, currency, customer_id|vendor_id|employee_id?, foreign_balance, book_balance, rate, revalued, difference, effect, settled, revaluation_entry_no}; rates; missing_rates[]; totals; source_event
```

`rate_type` is the workspace's `exchange_rate_type` vocabulary: `spot`,
`month_end`, `bank_buying`, `bank_selling`, `contract`, and its own. A
journal line converting a foreign amount carries `currency`,
`foreign_amount`, `exchange_rate` and optionally `exchange_rate_id`.

A revaluation entry: `source_type: "ledger_account"`, `source_id` the
account, `source_event: "revalued:2026-06"`; on the foreign account,
`foreign_amount: 0` with the rate used.
