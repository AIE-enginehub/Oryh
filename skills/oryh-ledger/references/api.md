# Ledger API

<!-- only: bundle -->
Every path hangs off `api_base_url` exactly as given — no version prefix to add.
<!-- /only -->

{{include:_common/api-conventions.md}}

## Settings and the chart

```text
GET    /accounting-settings            → the functional currency (null until set)
PUT    /accounting-settings            → {functional_currency, retained_earnings_account_id?}; fixed once anything posted
GET    /ledger-accounts?account_type=&parent_id=&subledger=&status=&keyword=   → the chart, code order; `summary` marks accounts with sub-accounts
POST   /ledger-accounts                → {account_code, name, account_type, parent_id?, subledger?, currency?, description?}
PATCH  /ledger-accounts/{id}           → name, description, parent_id, status; code, type, subledger, currency only before it has lines
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

## Periods

```text
GET    /accounting-periods?status=
POST   /accounting-periods/close       body {"period": any day in the month, "reason"?}; drafts in the month block it
POST   /accounting-periods/reopen      body {"period", "reason"}; the reason is required
```

## Reads

```text
GET    /trial-balance?date_from=&date_to=                 → per account: opening, debit, credit, closing, natural_closing; totals
GET    /ledger-accounts/{id}/ledger?date_from=&date_to=&page=&size=   → opening, a page of lines with running balance, total_lines, closing
GET    /ledger-accounts/{id}/parties?as_of=               → a subledger account's balance per party
```
