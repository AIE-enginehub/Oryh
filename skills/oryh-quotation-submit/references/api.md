# Oryh Quotation Submit API Reference

{{include:_common/api-auth-principal.md}}

## Identity And Reads

{{include:_common/tenant-state-names.md}}

```text
GET /auth/me                                               → linked employee_id + permissions
GET /customers?keyword=&status=active                      → match the customer (read-only)
GET /customers?tax_id=                                     → exact customer match by tax id
GET /products?keyword=&status=active                       → match catalog products (read-only; has_skus flags variant products)
GET /product-skus?product_id={id}&status=active            → the product's variants
GET /sales-quotations?employee_id={me}&status=draft        → reuse before create
GET /sales-quotations?employee_id={me}&status=submitted    → in-flight duplicate check (also ?status=sent)
GET /sales-quotations?quote_number=QT-000123&include_deleted=false → every revision of one number
GET /sales-quotations/{quotation_id}/detail                → quotation + items + adjustments + computed_total + adjustments_total + adjusted_total + unpriced_item_count + revisions + approval trail
GET /approval-records?entity_type=sales_quotation&entity_id={quotation_id} → progress
GET /workflow-definitions?entity_kind=builtin&object_type=sales_quotation  → tenant rules; apply its submission requirements (step 2)
```

## Create Quotation

```json
POST /sales-quotations
{
  "employee_id": "my-employee-id",
  "title": "Huaxin Machinery — annual CNC tooling quotation",
  "customer_id": "customer-id-if-confidently-matched",
  "customer_name_snapshot": "Huaxin Machinery",
  "contact_name": "Engineer Wang",
  "contact_phone": "13800000000",
  "quote_date": "2026-07-21",
  "valid_until": "2026-08-20",
  "currency": "CNY",
  "payment_terms": "payment before shipment; net 30 available",
  "delivery_terms": "freight included; 3 days within East China",
  "remarks": "all unit prices include 13% VAT",
  "source_report_text": "Huaxin wants annual pricing on a batch of tools: mills at 10% off list, two boxes of samples included, net 30.",
  "items": [
    {"line_no": 1, "product_id": "product-id-if-matched", "quantity": 200,
     "unit_price": 85.00, "tax_rate": 13},
    {"line_no": 2, "product_name_snapshot": "Samples, two boxes", "quantity": 2,
     "unit_price": 0, "is_gift": true}
  ]
}
```

`items` rides the create: the whole quotation is ONE call and one
transaction — a bad line rolls everything back, and the response echoes the
lines as they landed (your read-back material). Catalog `list_price_snapshot`
capture works identically inline. Up to 200 lines.

Status starts at `draft`. `POST /sales-quotation-items` (below) remains the way to ADD a line to an existing `draft`/`returned` quotation. `quote_number` omitted → the server allocates the next `QT-NNNNNN` (bring your own only for tenant numbering conventions; duplicates 409). Both customer fields are optional: a matched `customer_id` backfills an empty snapshot; free text alone is the new-prospect case. `total_amount` is usually set later, once the lines exist and a document total is negotiated (rounding it down, for instance) — omit it and
the line sum is the total.

## Items

```json
POST /sales-quotation-items
{
  "quotation_id": "quotation-id",
  "line_no": 1,
  "product_id": "product-id-if-confidently-matched",
  "sku_id": "sku-id-when-the-variant-is-decided",
  "product_name_snapshot": "Four-flute end mill",
  "spec": "D10 carbide",
  "quantity": 200,
  "unit": "each",
  "unit_price": 85.00,
  "tax_rate": 13,
  "lead_time": "in stock",
  "is_gift": false,
  "notes": "10% off list price"
}
```

- `list_price_snapshot` is captured **automatically** from the catalog (SKU price overrides product price) when the line references one — send it explicitly only when applying a special price list. Uncataloged free-text lines carry none; the discount is then not derivable, which approvers will see.
- `amount` is the line total override (normally omit; `quantity × unit_price` is computed at read time).
- Gift lines: `"is_gift": true, "unit_price": 0` — counted as 0 in totals, never as "unpriced" and never as a 100% discount.
- `line_no` is the printed document order; `/detail` returns lines sorted by it.

## Adjustments (document-level and line-level)

Signed amounts that move the total beside the line math — the explicit home
for promotions, tax, freight, handling, surcharges and rounding (OFBiz
QuoteAdjustment shaped):

```json
POST /sales-quotation-adjustments
{
  "quotation_id": "quotation-id",
  "adjustment_type": "promotion",
  "amount": -500.00,
  "description": "opening promotion, less 500",
  "quotation_item_id": "item-id-or-omit-for-header-level",
  "source_percentage": 5
}
```

- `adjustment_type`: the shipped catalog is `discount | promotion | tax | shipping | fee | surcharge | rounding | other`;
  the tenant may have added their own (an invoicing service fee…) or archived
  shipped ones —
  the current vocabulary is `GET /type-options?family=sales_adjustment_type`,
  and an unknown value is a 422 listing the active options. The same
  vocabulary governs order adjustments. A charge that fits none of them
  (an invoicing service fee, an installation charge…) is a new type: propose it, then
  `POST /type-options {"family": "sales_adjustment_type", "name":
  "invoicing_fee", "title": "Invoicing service fee"}` (needs `object_types.manage`; on
  403 ask an admin) — never file it as `other` when it has a real name the
  customer sees on the quote.
- `amount` is SIGNED: negative reduces the total (promotion, discount, rounding),
  positive adds (tax, freight, surcharge).
- Omit `quotation_item_id` for a document-level adjustment; set it to pin the
  adjustment to one line (400 if the line belongs to another quotation).
- `source_percentage` records the rate it was derived from, when there was
  one; `amount` stays the recorded fact — never make the server re-derive.
- `PATCH /sales-quotation-adjustments/{id}` / `DELETE` while the quotation is
  editable (409 otherwise — adjustments lock and unlock with the document,
  exactly like items). `GET /sales-quotation-adjustments?quotation_id=` lists.
- `/revise` copies adjustments to the new revision (line-pinned ones follow
  the copied line), so the negotiation continues from the same facts.
- Detail math: `adjusted_total = computed_total + adjustments_total`. Record
  the adjustments, and the declared `total_amount` should then equal
  `adjusted_total`; a residual gap is undocumented and the approval side
  will ask about it.
- A per-line price concession is still `unit_price` vs `list_price_snapshot`
  — that is where a unit-price discount lives. Adjustments are for amounts that sit
  BESIDE the line prices, not a second way to discount a unit price.

`PATCH /sales-quotation-items/{id}` / `DELETE` while the quotation is editable (409 otherwise). Swapping a line's product refreshes `list_price_snapshot` to the new product's catalog price automatically.

Server-enforced limits (validate in conversation before calling):

```text
quantity        > 0                                     → 422 otherwise
item identity   product_id or product_name_snapshot     → 422 otherwise
tax_rate        0..100                                  → 422 otherwise
items           only while quotation is draft/returned  → 409 otherwise
customer_id / product_id / sku_id / attachment_id / project_id must exist here → 404 otherwise
sku_id          must belong to product_id (sku alone derives it) → 400 otherwise
```

## Historical Import (migration only)

A retired system's export, not today's filing. `POST /sales-quotations/bulk`
takes up to 500 documents per call, each carrying its own lines and
adjustments:

```jsonc
{"rows": [{
  "quote_number": "QT-2023-000001",      // REQUIRED — history keeps its number
  "employee_code": "E-001",              // the salesperson; by code (or employee_id)
  "customer_code": "C-001",              // resolved against customer master data
  "customer_name_snapshot": "Huaxin Machinery",   // what the document printed
  "title": "2023 annual tooling quotation", "quote_date": "2023-03-15",
  "status": "accepted",                  // terminal states import AS-IS
  "total_amount": 1130.00,
  "items": [{"line_no": 1, "product_code": "P-001", "quantity": 10,
             "unit_price": 100.00, "amount": 1000.00}],
  "adjustments": [{"adjustment_type": "tax", "amount": 130.00,
                   "source_percentage": 13, "line_no": 1}]
}], "dry_run": true, "on_error": "skip", "on_missing_reference": "error"}
```

- **The number is the identity**, so a re-run is an upsert: the same file
  twice reports `unchanged`, which is how a half-finished migration resumes —
  just run it again. Nothing is server-allocated, so the number allocator's
  per-tenant lock never throttles the import (~385 docs/sec measured).
- **`status` accepts any state of the tenant's machine.** Won and lost documents
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

## Lifecycle (machine-guarded; submit/send/close are retry-idempotent)

```json
POST /sales-quotations/{id}/submit
{}
```

`draft/returned → submitted`; sets `submitted_at`. Internal approval runs from here.

```json
POST /sales-quotations/{id}/send
{}
```

`approved → sent`; sets `sent_at`. Record the fact AFTER the document actually went to the customer.

```json
POST /sales-quotations/{id}/close
{"outcome": "accepted", "outcome_note": "signed on the v2 quotation, contract HT-2026-088"}
```

`sent → accepted | declined | expired`; sets `closed_at`. `outcome_note` is where
the confirmation of a win, or the reason for a loss, lives.

```json
POST /sales-quotations/{id}/revise
{"reason": "customer asked for the mill unit price to come down to 80"}
```

`approved/sent → superseded` on the old revision; returns a fresh `draft` with `revision_no + 1`, same `quote_number`, lines copied, catalog snapshots refreshed to today's truth. Adjust, read back, submit again. Revise is NOT retry-idempotent: retrying after success returns 409 "already superseded" — recover the new draft via `GET /sales-quotations?quote_number={n}` (highest `revision_no`).

## Submitted Fact (recorded by `/submit`; shown for reference only)

Do not post it — `/submit` already did. The shape, for reading the trail:

```json
POST /approval-records
{
  "entity_type": "sales_quotation",
  "entity_id": "quotation-id",
  "round_no": 1,
  "sequence_no": 1,
  "action": "submitted",
  "approver_role": "submitter"
}
```

After a return, a resubmit records the next `round_no` the same way. Each revision is its own record with its own trail.

## Correcting The Quotation Header Before Submitting

```text
PATCH /sales-quotations/{quotation_id}
{"title": "City First Hospital — JC-800 purchase quotation", "valid_until": "2026-08-25", "remarks": "discount rationale: strategic account, third purchase this year"}
```

Editable while the quotation is in an editable state (`draft`/`returned` by
default; 409 otherwise). `remarks` matters here: tenants commonly require the
discount justification in it, so read the document back after writing and
confirm the value landed.

## When the decision happened

{{include:_common/when-the-decision-happened.md}}
