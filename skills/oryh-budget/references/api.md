# Budget API

<!-- only: bundle -->
Every path hangs off `api_base_url` exactly as given — no version prefix to add.
<!-- /only -->

{{include:_common/api-conventions.md}}

## Budgets

```text
GET    /budgets?direction=&budget_type=&status=&keyword=
POST   /budgets                      → {name, direction?, budget_type?, currency?, period_start, period_end, owner_employee_id?, cost_center_id? (spend only), description?, lines?: [{line_code, name, category, owner_employee_id?, sort_order?}]}
GET    /budgets/{id}                 → the header and its lines
PATCH  /budgets/{id}                 → name, owner, notes at any time; type, currency, period while draft; status (draft → active ⇄ frozen → closed)
GET    /budgets/{id}/execution?by_month=   → per line (and month): every figure; unbudgeted spend; a line's sub_targets and splits
POST   /budgets/{id}/close           → closes; reads back each spend line's unspent amount
POST   /budgets/{id}/import          → {employee_id, reason, rows: [{line_code, name?, category?, period_month, amount}], post?, dry_run?}
DELETE /budgets/{id}                 → a draft with no posted figures only; POST /budgets/{id}/restore undoes
```

## Lines

```text
GET    /budget-lines?budget_id=&category=&status=   → the directory: codes, names, categories, no amounts
POST   /budget-lines                 → {budget_id, line_code, name, category, owner_employee_id?, status?, sort_order?}
                                         a sub-target: + parent_line_id (the sales line) and one of employee_id | territory_id | customer_id | product_category_id
PATCH  /budget-lines/{id}            → name, category, owner_employee_id, status (closed), sort_order, description
GET    /budget-lines/{id}/documents?stage=   → the documents behind a figure (labour: payroll.read)
GET    /budget-lines/{id}/availability?amount=   → available now and after this amount
```

## Changes and the ledger

```text
GET    /budget-changes?budget_id=&change_type=&status=
POST   /budget-changes               → {budget_id, employee_id, change_type, reason, status?: "posted", source_budget_id?, lines: [{budget_line_id | line_code, period_month, amount, note?}]}
GET    /budget-changes/{id}          → with its lines and revision
PATCH  /budget-changes/{id}          → reason, change_type while editable; status (posted from draft: budget.manage; approve/return/reject: budget.advance)
POST   /budget-changes/{id}/save     → {expected_revision, items: [...]} the lines restated as a diff
POST   /budget-changes/{id}/submit   → into a workspace's approval flow
GET    /budget-entries?budget_id=&budget_line_id=&change_id=&period_month=   → the plan ledger, read-only
```

## The cash budget

Alerts are the agent's: compare execution's `percent_consumed` /
`percent_achieved` with the workspace's rule and raise a todo (`POST /todos`).

```text
GET    /budget-cash?income_budget_id=&spend_budget_id=   → per month: income_planned, received, spend_planned, paid, unbudgeted_paid, net and cumulative net
```

## Impact and vocabularies

```text
GET    /budget-impact?entity_type=&entity_id=   → expense_claim | purchase_request | purchase_order | invoice: lines drawn on, available before and after
GET    /type-options?family=budget_category
GET    /type-options?family=budget_type
GET    /type-options?family=budget_change_type
```
