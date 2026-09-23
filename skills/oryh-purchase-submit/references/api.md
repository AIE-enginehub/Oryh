# Oryh Purchase Submit API Reference

{{include:_common/api-auth-principal.md}}

{{include:_common/api-conventions.md}}

## Identity And Reads

```text
GET /auth/me                                              → linked employee_id + permissions
GET /vendors?keyword=&status=active                       → match the target vendor (read-only)
GET /vendors?tax_id=                                      → exact vendor match by tax id
GET /products?keyword=&status=active                      → match catalog products (read-only; has_skus flags variant products)
GET /product-skus?product_id={id}&status=active           → the product's variants (variant_attrs is free-form: size, colour, configuration…)
GET /purchase-requests?employee_id={me}&status=draft      → reuse before create
GET /purchase-requests?employee_id={me}&status=submitted  → in-flight duplicate check
GET /purchase-requests/{request_id}/detail                → request + items (each with its `sales_order` context when pinned, and the `purchase_order_items` procurement later places against it) + estimated_total + unpriced_item_count + approval trail
GET /approval-records?entity_type=purchase_request&entity_id={request_id}   → progress
GET /workflow-definitions?entity_kind=builtin&object_type=purchase_request → tenant rules; apply its submission requirements (step 2)
```

## Create Request

```json
POST /purchase-requests
{
  "employee_id": "my-employee-id",
  "title": "R&amp;D monitor purchase",
  "request_date": "2026-07-11",
  "needed_by": "2026-07-25",
  "vendor_id": "vendor-id-if-confidently-matched",
  "vendor_name_snapshot": "Dell",
  "currency": "CNY",
  "source_report_text": "R&amp;D needs two 4K monitors and a batch of cabling; monitors from Dell, cabling supplier undecided."
}
```

`items` may ride this create — the document and its lines in one call and one
transaction (bad line = whole document rolls back; response echoes the lines).
The per-line POST below remains for adding to an existing draft.

Status starts at `draft`. Both vendor fields are optional: a matched `vendor_id` backfills an empty snapshot; free text alone is the "not decided yet" case.

## Items

```json
POST /purchase-request-items
{
  "request_id": "request-id",
  "product_id": "product-id-if-confidently-matched",
  "sku_id": "sku-id-when-the-variant-is-decided (null = flat product, or size undecided)",
  "product_name_snapshot": "27-inch monitor",
  "spec": "4K IPS",
  "quantity": 2,
  "unit": "each",
  "unit_price": 2999.00,
  "amount": null,
  "attachment_id": "quote-attachment-id-if-any",
  "notes": "optional"
}
```

Pricing is optional by design: `unit_price` for per-unit quotes, `amount` for lump sums ("a batch of cabling, budget 800"), neither when the price is still to be sourced. A matched `product_id` backfills empty name/unit snapshots. Quote files are uploaded first (base64, 10 MB) and referenced by `attachment_id`.
<!-- only: bundle -->
Upload with `POST /attachments`, or the bundled `scripts/upload_attachment.py` (in this skill's directory), which does the base64, the size pre-check, and reports `already_existed` per file.
<!-- /only -->
<!-- only: mcp -->
Upload with the `upload_attachment` tool; a 200 instead of 201 means the file was already on file.
<!-- /only -->

Purchasing against an order: an item may carry `sales_order_item_id` — the confirmed sales order line it fulfils (from that order's `/detail`, `items[].id`; nonexistent or cross-tenant → 404). Several purchase lines may pin to one order line. In this request's `/detail`, a pinned line resolves a `sales_order` block: `{sales_order_item_id, order_id, order_no, order_status, customer_name_snapshot, quantity}` — the order-side quantity, so a reviewer sees "3 ordered / 4 being purchased" at a glance. PATCH with `null` detaches. Downstream, once procurement places the actual purchase order (`$oryh-purchase-order`), each line's `purchase_order_items` lists `{po_number, po_status, quantity, received_quantity, …}` — how the principal's request is progressing, without leaving this detail call.

`PATCH /purchase-request-items/{id}` / `DELETE` while the request is editable (409 otherwise).

Server-enforced limits (validate in conversation before calling):

```text
quantity        > 0                                     → 422 otherwise
item identity   product_id or product_name_snapshot    → 422 otherwise
items           only while request is draft/returned   → 409 otherwise
vendor_id / product_id / sku_id / attachment_id must exist here → 404 otherwise
sku_id          must belong to product_id (sku alone derives it) → 400 otherwise
```

## Restating The Whole Document

```text
GET  /purchase-requests/{id}/detail                          → revision (a hash of header, live lines, adjustments)
POST /purchase-requests/{id}/save?validate_only=true         → the same run, nothing written
POST /purchase-requests/{id}/save
{"expected_revision": "<detail.revision>",
 "items": [{"id": "<existing line>", ...the fields that change...},   → updated through the PATCH rules
           {...full line without id...}],                → added through the POST rules
 "adjustments": [{"id": "<existing>", "adjustment_type": "discount", "amount": -8},
                 {"adjustment_type": "discount", "amount": -1, "item_index": 1}]}
```

A DIFF, never a delete-and-reinsert: a line kept by id keeps its identity
(and anything pointing at it), a live line not listed is removed with the
same audit a DELETE writes.
Stale `expected_revision` → 409: read `/detail` again and restate. The
header stays with PATCH; the editable-state gate is the same one every
line write passes. One call replaces N PATCH/DELETE round trips when a
person reworks a draft.

## Submit

```json
POST /purchase-requests/{request_id}/submit
{}
```

Guarded by the tenant's lifecycle machine (draft/returned → submitted); idempotent on resubmit; sets `submitted_at`.

## Submitted Fact (only if the role has approval.record)

```json
POST /approval-records
{
  "entity_type": "purchase_request",
  "entity_id": "request-id",
  "round_no": 1,
  "sequence_no": 1,
  "action": "submitted",
  "approver_role": "submitter"
}
```

403 here is expected in tenants whose member role is fact-free — the workflow admin backfills it. After a return, resubmit with `round_no` incremented.

## Correcting The Request Header Before Submitting

```text
PATCH /purchase-requests/{request_id}
{"title": "R&amp;D monitor purchase", "needed_by": "2026-08-15", "vendor_id": null}
```

Editable while the request is in an editable state (`draft`/`returned` by
default; 409 otherwise). Detach a wrongly matched vendor by sending `null`;
the free-text `vendor_name_snapshot` stands on its own.

## When the decision happened

{{include:_common/when-the-decision-happened.md}}
