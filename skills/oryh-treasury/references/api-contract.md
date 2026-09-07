<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-treasury: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /fin-accounts/{account_id}

Delete Fin Account

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |

## GET /fin-account-transactions

List Fin Account Transactions

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `fin_account_id` | query | string | no |  |
| `trans_type` | query | string | no |  |
| `payment_id` | query | string | no |  |
| `reference_no` | query | string | no |  |
| `unlinked` | query | boolean | no |  |
| `include_archived_accounts` | query | boolean | no |  |
| `date_from` | query | date | no |  |
| `date_to` | query | date | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /fin-accounts

List Fin Accounts

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_type` | query | string | no |  |
| `status` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /fin-accounts/{account_id}

Get Fin Account

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |

## GET /payments

List Payments

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `direction` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `vendor_id` | query | string | no |  |
| `payee_employee_id` | query | string | no |  |
| `employee_id` | query | string | no |  |
| `payment_no` | query | string | no |  |
| `reference_no` | query | string | no |  |
| `status` | query | string | no |  |
| `unapplied` | query | boolean | no |  |
| `without_open_todo` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /type-options

List Type Options

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `family` | query | string | no |  |
| `status` | query | string | no |  |

## PATCH /fin-account-transactions/{trans_id}

Link Fin Account Trans

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `trans_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `entity_id` | string | optional |  |
| `entity_type` | string (≤50 chars) | optional |  |
| `payment_id` | string | optional |  |
| `payment_reference_no` | string (≤100 chars) | optional |  |

## PATCH /fin-accounts/{account_id}

Update Fin Account

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `account_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `account_number` | string (≤64 chars) | optional |  |
| `account_type` | string (≤50 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `institution` | string (≤200 chars) | optional |  |
| `name` | string (≤200 chars) | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |

## POST /fin-account-transactions

Create Fin Account Trans

Body:

| field | type | | notes |
|---|---|---|---|
| `amount` | number (≥-9999999999.99, ≤9999999999.99) | required |  |
| `fin_account_id` | string | required |  |
| `counterparty` | string (≤200 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `description` | string (≤2000 chars) | optional |  |
| `entity_id` | string | optional |  |
| `entity_type` | string (≤50 chars) | optional |  |
| `fee_amount` | number (≥-9999999999.99, ≤9999999999.99) | optional |  |
| `gross_amount` | number (≥-9999999999.99, ≤9999999999.99) | optional |  |
| `payment_id` | string | optional |  |
| `reference_no` | string (≤128 chars) | optional |  |
| `trans_date` | date | optional |  |
| `trans_type` | `adjustment` | `deposit` | `fee` | `interest` | `opening` | `refund` | `transfer_in` | `transfer_out` | `withdrawal` | optional |  |

## POST /fin-account-transactions/bulk

Bulk Import Fin Account Trans

Body:

| field | type | | notes |
|---|---|---|---|
| `fin_account_id` | string | required |  |
| `rows` | array of objects (fields below) | required |  |
| ↳ each `rows[]` item: | | | |
  | `amount` | number (≥-9999999999.99, ≤9999999999.99) | required |  |
  | `counterparty` | string (≤200 chars) | optional |  |
  | `custom_fields` | object | optional |  |
  | `description` | string (≤2000 chars) | optional |  |
  | `fee_amount` | number (≥-9999999999.99, ≤9999999999.99) | optional |  |
  | `gross_amount` | number (≥-9999999999.99, ≤9999999999.99) | optional |  |
  | `reference_no` | string (≤128 chars) | optional |  |
  | `trans_date` | date | optional |  |
  | `trans_type` | `adjustment` | `deposit` | `fee` | `interest` | `opening` | `refund` | `transfer_in` | `transfer_out` | `withdrawal` | optional |  |
| `dry_run` | boolean | optional |  |
| `on_error` | `abort` | `skip` | optional |  |

## POST /fin-accounts

Create Fin Account

Body:

| field | type | | notes |
|---|---|---|---|
| `name` | string (≤200 chars) | required |  |
| `account_number` | string (≤64 chars) | optional |  |
| `account_type` | string (≤50 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `institution` | string (≤200 chars) | optional |  |
| `opening_balance` | number (≥-9999999999.99, ≤9999999999.99) | optional |  |
| `opening_date` | date | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `status` | `active` | `archived` | optional |  |
