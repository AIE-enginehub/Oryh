<!-- generated from the API contract by the api-contract sync (sync_skill_api_contracts) — edit the server, not this file -->

# oryh-contracts: API contract

Every endpoint this skill names, with the parameters the server actually
accepts. Paths hang off `api_base_url`. Responses are `{data, meta}` and
lists page with `page`/`size` (see the conventions in this skill).

## DELETE /contract-documents/{document_id}

Delete Contract Document

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `document_id` | path | string | yes |  |

## DELETE /contract-terms/{term_id}

Delete Contract Term

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `term_id` | path | string | yes |  |

## DELETE /contracts/{contract_id}

Delete Contract

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | path | string | yes |  |

## GET /contract-documents

List Contract Documents

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | query | string | no |  |
| `document_type` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /contract-documents/{document_id}

Get Contract Document

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `document_id` | path | string | yes |  |

## GET /contract-items

List Contract Items

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | query | string | no |  |
| `product_id` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /contract-terms

List Contract Terms

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | query | string | no |  |
| `term_type` | query | string | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /contracts

List Contracts

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `side` | query | string | no |  |
| `contract_type` | query | string | no |  |
| `vendor_id` | query | string | no |  |
| `customer_id` | query | string | no |  |
| `parent_contract_id` | query | string | no |  |
| `status` | query | string | no |  |
| `include_deleted` | query | boolean | no |  |
| `keyword` | query | string | no |  |
| `page` | query | integer (≥1) | no |  |
| `size` | query | integer (≥1) | no | paging — see the conventions in this skill |

## GET /contracts/{contract_id}

Get Contract

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | path | string | yes |  |

## GET /contracts/{contract_id}/attachments/{attachment_id}/content

Get Contract Attachment

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | path | string | yes |  |
| `attachment_id` | path | string | yes |  |

## GET /contracts/{contract_id}/execution

Contract Execution

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | path | string | yes |  |

## GET /type-options

List Type Options

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `family` | query | string | no |  |
| `status` | query | string | no |  |

## PATCH /contract-documents/{document_id}

Update Contract Document

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `document_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `caption` | string (≤200 chars) | optional |  |
| `document_type` | string (≤50 chars) | optional |  |
| `extracted_text` | string (≤2000000 chars) | optional |  |
| `metadata` | object | optional |  |
| `page_no` | integer (≥1.0, ≤99999.0) | optional |  |
| `sort_order` | integer (≥0.0, ≤9999.0) | optional |  |

## PATCH /contract-items/{item_id}

Update Contract Item

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `item_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `currency` | string (≤3 chars) | optional |  |
| `delivery_note` | string (≤500 chars) | optional |  |
| `description` | string (≤500 chars) | optional |  |
| `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
| `metadata` | object | optional |  |
| `product_id` | string | optional |  |
| `quantity` | number (≤99999999.9999) | optional |  |
| `unit` | string (≤50 chars) | optional |  |
| `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |

## PATCH /contract-terms/{term_id}

Update Contract Term

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `term_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `clause_ref` | string (≤50 chars) | optional |  |
| `content` | string (≤20000 chars) | optional |  |
| `document_id` | string | optional |  |
| `metadata` | object | optional |  |
| `page_no` | integer (≥1.0, ≤99999.0) | optional |  |
| `sort_order` | integer (≥0.0, ≤9999.0) | optional |  |
| `summary` | string (≤2000 chars) | optional |  |
| `term_type` | string (≤50 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## PATCH /contracts/{contract_id}

Update Contract

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | path | string | yes |  |

Body:

| field | type | | notes |
|---|---|---|---|
| `contract_type` | string (≤50 chars) | optional |  |
| `counterparty_name_snapshot` | string (≤200 chars) | optional |  |
| `counterparty_signatory` | string (≤100 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `effective_from` | date | optional |  |
| `effective_to` | date | optional |  |
| `employee_id` | string | optional |  |
| `our_signatory` | string (≤100 chars) | optional |  |
| `parent_contract_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `signed_date` | date | optional |  |
| `status` | string (≤50 chars) | optional |  |
| `summary` | string (≤10000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤999999999999.99) | optional |  |

## POST /attachments

Create Attachment

Body:

| field | type | | notes |
|---|---|---|---|
| `content_base64` | string | required |  |
| `content_type` | string (≤100 chars) | required |  |
| `filename` | string (≤255 chars) | required |  |

## POST /contract-documents

Create Contract Document

Body:

| field | type | | notes |
|---|---|---|---|
| `attachment_id` | string | required |  |
| `contract_id` | string | required |  |
| `caption` | string (≤200 chars) | optional |  |
| `document_type` | string (≤50 chars) | optional |  |
| `extracted_text` | string (≤2000000 chars) | optional |  |
| `metadata` | object | optional |  |
| `page_no` | integer (≥1.0, ≤99999.0) | optional |  |
| `sort_order` | integer (≥0.0, ≤9999.0) | optional |  |

## POST /contract-items

Create Contract Item

Body:

| field | type | | notes |
|---|---|---|---|
| `contract_id` | string | required |  |
| `currency` | string (≤3 chars) | optional |  |
| `delivery_note` | string (≤500 chars) | optional |  |
| `description` | string (≤500 chars) | optional |  |
| `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
| `metadata` | object | optional |  |
| `product_id` | string | optional |  |
| `quantity` | number (≤99999999.9999) | optional |  |
| `unit` | string (≤50 chars) | optional |  |
| `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |

## POST /contract-terms

Create Contract Term

Body:

| field | type | | notes |
|---|---|---|---|
| `content` | string (≤20000 chars) | required |  |
| `contract_id` | string | required |  |
| `term_type` | string (≤50 chars) | required |  |
| `clause_ref` | string (≤50 chars) | optional |  |
| `document_id` | string | optional |  |
| `metadata` | object | optional |  |
| `page_no` | integer (≥1.0, ≤99999.0) | optional |  |
| `sort_order` | integer (≥0.0, ≤9999.0) | optional |  |
| `summary` | string (≤2000 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |

## POST /contracts

Create Contract

Body:

| field | type | | notes |
|---|---|---|---|
| `title` | string (≤200 chars) | required |  |
| `contract_no` | string (≤64 chars) | optional |  |
| `contract_type` | string (≤50 chars) | optional |  |
| `counterparty_name_snapshot` | string (≤200 chars) | optional |  |
| `counterparty_signatory` | string (≤100 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `customer_id` | string | optional |  |
| `effective_from` | date | optional |  |
| `effective_to` | date | optional |  |
| `employee_id` | string | optional |  |
| `items` | array of objects (fields below) | optional |  |
| ↳ each `items[]` item: | | | |
  | `currency` | string (≤3 chars) | optional |  |
  | `delivery_note` | string (≤500 chars) | optional |  |
  | `description` | string (≤500 chars) | optional |  |
  | `line_no` | integer (≥1.0, ≤9999.0) | optional |  |
  | `metadata` | object | optional |  |
  | `product_id` | string | optional |  |
  | `quantity` | number (≤99999999.9999) | optional |  |
  | `unit` | string (≤50 chars) | optional |  |
  | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `our_signatory` | string (≤100 chars) | optional |  |
| `parent_contract_id` | string | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `signed_date` | date | optional |  |
| `status` | string (≤50 chars) | optional |  |
| `summary` | string (≤10000 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤999999999999.99) | optional |  |
| `vendor_id` | string | optional |  |

## POST /contracts/{contract_id}/restore

Restore Contract

| parameter | in | type | required | notes |
|---|---|---|---|---|
| `contract_id` | path | string | yes |  |

## POST /purchase-orders

Create Purchase Order

Body:

| field | type | | notes |
|---|---|---|---|
| `employee_id` | string | required |  |
| `vendor_id` | string | required |  |
| `billing_account_id` | string | optional |  |
| `contract_id` | string | optional |  |
| `contract_no` | string (≤64 chars) | optional |  |
| `currency` | string (≤3 chars) | optional |  |
| `custom_fields` | object | optional |  |
| `delivery_terms` | string (≤2000 chars) | optional |  |
| `items` | array of objects (fields below) | optional |  |
| ↳ each `items[]` item: | | | |
  | `amount` | number (≥0.0, ≤9999999.99) | optional |  |
  | `attachment_id` | string | optional |  |
  | `custom_fields` | object | optional |  |
  | `line_no` | integer (≥1.0) | optional |  |
  | `notes` | string (≤2000 chars) | optional |  |
  | `po_id` | string | optional |  |
  | `product_id` | string | optional |  |
  | `product_name_snapshot` | string (≤200 chars) | optional |  |
  | `promised_date` | date | optional |  |
  | `purchase_request_item_id` | string | optional |  |
  | `quantity` | number (≤9999999.99) | optional |  |
  | `sku_id` | string | optional |  |
  | `spec` | string (≤200 chars) | optional |  |
  | `tax_rate` | number (≥0.0, ≤100.0) | optional |  |
  | `unit` | string (≤50 chars) | optional |  |
  | `unit_price` | number (≥0.0, ≤9999999.99) | optional |  |
| `order_date` | date | optional |  |
| `order_kind` | `order` | `return` | optional |  |
| `original_order_id` | string | optional |  |
| `payment_terms` | string (≤2000 chars) | optional |  |
| `po_number` | string (≤64 chars) | optional |  |
| `promised_date` | date | optional |  |
| `remarks` | string (≤2000 chars) | optional |  |
| `source_report_text` | string (≤10000 chars) | optional |  |
| `status` | string (≤30 chars) | optional |  |
| `title` | string (≤200 chars) | optional |  |
| `total_amount` | number (≥0.0, ≤9999999999.99) | optional |  |
| `vendor_name_snapshot` | string (≤200 chars) | optional |  |
