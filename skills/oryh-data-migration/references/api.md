# Oryh Data Migration API Reference

{{include:_common/api-auth-principal.md}}

The credential also needs `tenant.act_for_any_employee` — a migration writes
documents belonging to many salespeople, which ordinary submit credentials are
forbidden to do (403 naming the capability). Admin roles hold it by default.
The purchase-order import is gated on `purchase_order.manage` instead (also
an admin default) — procurement documents are a function, not personal ones.

## Pre-flight Reads

```text
GET /customers?keyword=&size=200      → sample the workbook's customer codes
GET /products?keyword=&size=200       → sample its product codes
GET /employees?status=active&size=200 → every document names a salesperson
GET /sales-quotations?keyword={number}  → did a previous run already land this?
```

## Historical Quotations

```jsonc
POST /sales-quotations/bulk
{"rows": [{
  "quote_number": "QT-2023-000001",      // REQUIRED — the historical number IS the identity
  "employee_code": "E-001",              // or employee_id; never omitted
  "customer_code": "C-001",              // resolved against customer master data
  "customer_name_snapshot": "华欣机械",   // what the document printed
  "contact_name": "王工", "contact_phone": "138…",
  "title": "2023年刀具年度报价",
  "project_code": "PRJ-2023-07",         // optional
  "quote_date": "2023-03-15", "valid_until": "2023-04-15",
  "currency": "CNY",
  "status": "accepted",                  // any state of the tenant's machine
  "total_amount": 1130.00,               // the historical document total
  "payment_terms": "月结30天", "remarks": "…",
  "items": [{
    "line_no": 1,
    "product_code": "P-001", "sku_code": null,
    "product_name_snapshot": "四刃立铣刀", "spec": "D10",
    "quantity": 10, "unit": "支",
    "list_price_snapshot": 120.00, "unit_price": 100.00, "amount": 1000.00,
    "tax_rate": 13, "is_gift": false, "lead_time": "7天", "notes": null
  }],
  "adjustments": [{
    "adjustment_type": "tax", "amount": 130.00, "source_percentage": 13,
    "line_no": null                      // null = 整单级; a line_no pins it to that line
  }]
}],
 "dry_run": true,
 "on_error": "skip",
 "on_missing_reference": "error"}
```

## Historical Orders

Same shape, with the order's own fields:

```jsonc
POST /sales-orders/bulk
{"rows": [{
  "order_no": "SO-2023-000001",            // REQUIRED
  "source_quote_number": "QT-2023-000001", // links the won quotation, by number
  "employee_code": "E-001", "customer_code": "C-001",
  "title": "2023年首批订单", "order_date": "2023-04-01",
  "contract_no": "HT-2023-088", "ship_to_address": "苏州市…",
  "promised_date": "2023-04-20",
  "status": "signed",
  "items": [{"line_no": 1, "product_code": "P-001", "quantity": 10,
             "unit_price": 100.00, "amount": 1000.00,
             "promised_date": "2023-04-20"}],
  "adjustments": [{"adjustment_type": "shipping", "amount": 80.00}]
}], "dry_run": true}
```

## Historical Purchase Orders

Same contract, procurement side. The vendor is REQUIRED per row — a PO
without a counterparty is not a document — so an unmatched `vendor_code` is
always an error, in both reference modes. Lines never carry
`list_price_snapshot`/`is_gift` (purchases have neither).

```jsonc
POST /purchase-orders/bulk
{"rows": [{
  "po_number": "CG-2019-042",              // REQUIRED — the historical number IS the identity
  "vendor_code": "V-DELL",                 // REQUIRED-to-resolve (or vendor_id)
  "vendor_name_snapshot": "戴尔计算机（中国）有限公司",  // what the document printed; kept verbatim
  "employee_code": "E-001",                // the buyer; never omitted
  "title": "2019年显示器框架采购",
  "contract_no": "HT-2019-102",
  "order_date": "2019-03-15", "promised_date": "2019-04-01",
  "currency": "CNY", "payment_terms": "月结30天",
  "status": "closed",                      // any state of the tenant's purchase_order machine
  "total_amount": 28000.00,
  "items": [{"line_no": 1, "product_code": "PRD-MON", "quantity": 10,
             "unit_price": 2800.00, "amount": 28000.00,
             "promised_date": "2019-04-01"}],
  "adjustments": [{"adjustment_type": "shipping", "amount": 200.00}]
}], "dry_run": true}
```

Historical `received_quantity` is not imported — receiving is a live-ledger
fact (`POST /purchase-orders/{po_id}/receive`), and backfilling it would
fabricate inventory history. A closed historical PO simply imports closed.

## Request Options

- `rows` — 1 to 500 documents per call. Chunk longer files yourself, or use
  the bundled script.
- `dry_run` (default `false`) — runs the identical write path and rolls back.
- `on_error` — **`skip` (default here)**: import the good documents and report
  the rest, which is what a 300k-row migration needs. `abort` writes nothing
  and is for the case where a dry run says the column mapping itself is wrong.
- `on_missing_reference` — `error` (default) makes an unmatched
  `customer_code`/`product_code`/`sku_code`/`project_code` a per-document
  error; `snapshot` imports the document anyway with the historical text
  standing alone. An unmatched **`employee_code` is always an error**, and on
  purchase orders so is an unmatched **`vendor_code`**.
- A file-provided `customer_name_snapshot`/`vendor_name_snapshot` is kept
  verbatim even when the code resolves — the snapshot is what the document
  printed, not today's master-data name.

## Response

```json
{"data": {
  "dry_run": false, "applied": true,
  "summary": {"total": 500, "created": 486, "updated": 0, "unchanged": 9, "failed": 5},
  "results": [
    {"index": 0, "number": "QT-2023-000001", "outcome": "created", "id": "…"},
    {"index": 7, "number": "QT-2023-000008", "outcome": "unchanged", "id": "…", "changed": []},
    {"index": 9, "number": "QT-2023-000010", "outcome": "error",
     "error": "unknown customer_code C-0881"}
  ]}}
```

- `number` (not `code`) identifies the row — report failures by document
  number, which is what the person can find in their workbook.
- `applied` is `false` for a dry run AND for an aborted run. Read it before
  reporting success.
- `unchanged` means that document was already imported — the signal that a
  re-run is doing its job.

## Idempotency And Resume

The document number is the upsert key:

- same file twice → every row `unchanged`, nothing written;
- corrected file → `updated`, with lines and adjustments replaced wholesale
  (a historical document is one fact, so a correction is that whole fact);
- interrupted run → **re-run the whole file**; already-imported documents cost
  a fast `unchanged` pass. Do not hand-track a resume offset.

Nothing is server-allocated, so the per-tenant document-number lock is never
taken and the import is not serialized by it (~385 documents/sec measured on
postgres, i.e. ~13 minutes for 300k).

## Chunking Script

```text
python3 scripts/import_documents.py --kind quotations rows.json            (dry run)
python3 scripts/import_documents.py --kind quotations rows.json --apply
python3 scripts/import_documents.py --kind orders rows.json --apply --on-missing-reference snapshot
python3 scripts/import_documents.py --kind purchase-orders rows.json --apply
```

`rows.json` is a JSON array of the row objects above. The script chunks at
500, keeps every reported index global to your file, prints progress per
chunk, and ends with ONE list of problem documents grouped by cause — which
is the report the person actually needs.
