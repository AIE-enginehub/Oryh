# Oryh Order Submit API Reference

{{include:_common/api-auth-principal.md}}

## Reads

```text
GET /auth/me                                            → linked employee_id
GET /workflow-definitions?entity_kind=builtin&object_type=sales_order → tenant rules
GET /sales-quotations/{id}/detail                       → the won quotation's lines to mirror
GET /sales-orders?quotation_id={id}                     → dedupe: one won quote, one order
GET /sales-orders?employee_id={me}&status=draft         → reuse before create
GET /sales-orders/{order_id}/detail                     → order + items (each with `purchase_items`: purchase lines behind it, with request status) + adjustments + linked quotation + computed_total + adjustments_total + adjusted_total + trail
```

## Create

```json
POST /sales-orders
{
  "employee_id": "my-employee-id",
  "title": "City First Hospital — JC-800 order",
  "quotation_id": "won-quotation-id",
  "customer_id": "customer-id",
  "contact_name": "Equipment dept, Zhou Min",
  "ship_to_address": "100 West Beijing Road, Huangpu, Shanghai",
  "contract_no": "JC-HT-2026-018",
  "order_date": "2026-07-22",
  "promised_date": "2026-08-05",
  "payment_terms": "payment 30 days after delivery and acceptance"
}
```

`items` may ride this create — the document and its lines in one call and one
transaction (bad line = whole document rolls back; response echoes the lines).
The per-line POST below remains for adding to an existing draft.

`order_no` omitted → server allocates `SO-NNNNNN` (duplicates 409; bring the
tenant's own convention when it has one). `quotation_id` backfills
`source_quote_number` automatically. Status starts at `draft`; create accepts
any declared state when recording an already-agreed fact.

## Items

```json
POST /sales-order-items
{
  "order_id": "order-id",
  "line_no": 1,
  "product_id": "product-id",
  "quantity": 1,
  "unit_price": 121600.0,
  "tax_rate": 13,
  "promised_date": "2026-08-05"
}
```

`list_price_snapshot` auto-captures from the catalog (explicit value — e.g.
carried from the quotation — wins). Items editable only while
`draft`/`returned` (409 otherwise).

## Submit

```json
POST /sales-orders/{order_id}/submit
{}
```

`draft/returned → submitted`; idempotent; sets `submitted_at`. The flow agent
confirms from there.

## Historical Import (migration only)

A retired system's export, not today's filing. `POST /sales-orders/bulk`
takes up to 500 documents per call, each carrying its own lines and
adjustments:

```jsonc
{"rows": [{
  "order_no": "SO-2023-000001",           // REQUIRED — history keeps its number
  "employee_code": "E-001",              // the salesperson; by code (or employee_id)
  "customer_code": "C-001",              // resolved against customer master data
  "customer_name_snapshot": "Huaxin Machinery",   // what the document printed
  "source_quote_number": "QT-2023-000001",  // the won quotation, by number
  "title": "2023 first order", "order_date": "2023-04-01", "contract_no": "HT-2023-088",
  "status": "signed",                    // terminal states import AS-IS
  "total_amount": 1130.00,
  "items": [{"line_no": 1, "product_code": "P-001", "quantity": 10,
             "unit_price": 100.00, "amount": 1000.00, "promised_date": "2023-04-20"}],
  "adjustments": [{"adjustment_type": "tax", "amount": 130.00,
                   "source_percentage": 13, "line_no": 1}]
}], "dry_run": true, "on_error": "skip", "on_missing_reference": "error"}
```

- **The number is the identity**, so a re-run is an upsert: the same file
  twice reports `unchanged`, which is how a half-finished migration resumes —
  just run it again. Nothing is server-allocated, so the number allocator's
  per-tenant lock never throttles the import (~385 docs/sec measured).
- **`status` accepts any state of the tenant's machine.** Shipped and signed-for documents
  are recorded as they ended; they are NOT walked through the lifecycle.
- **Master data is referenced by the tenant's own codes** (`employee_code`,
  `customer_code`, `product_code`, `sku_code`, `project_code`) — import the
  master data FIRST.
- `on_missing_reference` decides what an unmatched code costs: `error`
  (default) reports that document and imports the rest; `snapshot` imports it
  anyway with the historical text standing alone (`customer_id` null, the
  printed name kept). A missing SALESPERSON is always an error — the document
  cannot exist without one.
- `on_error` defaults to **`skip`** here (unlike master data): one document
  referencing a departed customer must not stop a 300k-row migration. Use
  `abort` when a dry run suggests the column mapping itself is wrong.
- Lines and adjustments are **replaced wholesale** on re-import: a historical
  document is one fact, and a corrected file is that whole fact again.
  Adjustments pin to a line by that line's `line_no` within the same row.
- Row results carry `number` (not `code`): report failures by document number
  so the person finds them in their spreadsheet.

## Fulfilment Facts (fields, never status)

```json
PATCH /sales-orders/{order_id}
{"logistics_company": "SF Express", "logistics_tracking_no": "SF3021188299"}
```

The flow agent advances `confirmed → shipped → signed` from these facts;
`shipped_at`/`signed_at` stamp automatically on those transitions.

## Channel Orders: External Numbers and the Product Map

```text
GET /external-document-links?source=tmall&external_kind=order&external_no=TM2026…
                                                        → dedup BEFORE creating the order
GET /external-document-links?entity_type=sales_order&entity_id={order_id}
                                                        → which platform orders became this one
GET /external-product-maps?source=tmall&external_product_id={platform id}&at={order date}
                                                        → the map AS OF that date. Listings swap
                                                          goods while keeping their id, so pass the
                                                          ORDER's date, not today. Rows: each
                                                          contributes quantity × line qty of
                                                          product_id; several rows = a bundle
GET /external-product-maps?source=tmall&external_name={title verbatim}&at={order date}
                                                        → the same, keyed by the listing's TITLE
                                                          (the common export); spec in external_sku_id
GET /product-matches?title={title}&limit=5              → candidates when the map is silent — a
                                                          shortlist for the person, never a decision
POST /external-product-maps {source, external_name, external_sku_id?, product_id, quantity?}
                                                        → what the person confirmed; title-keyed only
```

```json
POST /external-document-links
{
  "source": "tmall",
  "external_kind": "order",
  "external_no": "TM202608280010012345",
  "entity_type": "sales_order",
  "entity_id": "oryh-order-id"
}
```

One row per (platform number, oryh document) pair — splits and merges are
extra rows. Exact duplicate → 409 naming the existing link: a retry, not a
new fact. The same `POST` with `external_kind: "return"` ties a platform
return number to whatever recorded the return (`entity_type` also accepts
`payment`, `business_object`, `inventory_item_detail`, `purchase_order`,
`invoice` — the capability that governs writing that document governs its
links). `DELETE /external-document-links/{id}` undoes a mislink; the tuple
reopens. Order desks may POST title-keyed map rows after a person confirms the candidate; id-keyed rows, edits, effective-date swaps and deletion stay with $oryh-master-data.

## Returns

```text
GET  /sales-orders?order_kind=return&status=received      → returns, by their own machine's states
GET  /sales-orders?original_order_id={order_id}           → every return of one order — many returns = many rows
POST /sales-orders  {"order_kind": "return", "original_order_id": "...", ...}
                                                          → SR-NNNNNN beside the orders' SO-
PATCH /sales-orders/{id}  {"original_order_id": "..."}    → an orphan return matched later
```

Create accepts any state of the RETURN machine (`draft → submitted → approved
→ in_transit → received → inspected → refunded`; rejected/cancelled as
exits) — a platform-synced return arrives mid-flow as a fact. 422s that
teach: `original_order_id` on an order, an original that is itself a return,
a `billing_account_id` or `quotation_id` on a return (the refund is a
payment document; a return fulfils no quotation). An unscoped `?status=` is
checked against the UNION of both machines; add `order_kind=` to scope the
vocabulary to one.
