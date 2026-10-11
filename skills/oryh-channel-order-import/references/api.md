# Channel Order Import API

<!-- only: bundle -->
Every path hangs off `api_base_url` exactly as given — no version prefix to add.
<!-- /only -->

{{include:_common/api-conventions.md}}

## The opening wave

```text
GET /sales-channels                                     → the registered channels; `channel_code` is `source`
GET /stores?source=tmall                                → the channel's stores, each with fulfilment_facilities
GET /external-document-links?source=tmall&external_kind=order&page=1&size=200
                                                        → page to the end once; the numbers already ours
GET /external-document-links?source=tmall&external_kind=order&external_no=TM2026…
                                                        → the same question for one number
```

## Translating the file

```text
POST /external-product-maps/resolve                      → one call per 500 distinct listings:
                                                            {"source","with_candidates":true,"candidate_limit"?,
                                                             "listings":[{"external_product_id"?,"external_name"?,"external_sku_id"?,"at"}]}
                                                            data[i] answers listings[i]: status mapped|unmapped,
                                                            maps[] (product_id, sku_id, quantity — several rows = a bundle),
                                                            candidates[] (product row + match_score, matched_terms, sku_candidates, has_skus)
GET /products?keyword={code token}&status=active        → when the calibration says a token in the title is a product code
GET /product-skus?product_id=                           → the variants behind a product the title did not pin down
```

`at` is the ORDER's date. `external_name` is the title as printed; the
server folds case, width and spacing, not the platform's spec label.

## Creating a draft

```json
POST /sales-orders
{
  "employee_id": "{{EMPLOYEE_ID}}",
  "store_id": "store-id-from-the-opening-wave",
  "title": "Tmall TM202610080010012345",
  "order_date": "2026-10-08",
  "currency": "CNY",
  "customer_name_snapshot": "buyer nickname as exported",
  "ship_to_address": "as exported",
  "custom_fields": {"channel_import": {"source": "tmall", "external_no": "TM202610080010012345", "platform_status": "awaiting shipment, as exported", "placed_at": "2026-10-08T09:12:00+08:00"}},
  "items": [
    {"product_id": "product-id-from-the-map", "quantity": 2, "unit_price": 128.00,
     "custom_fields": {"channel_import": {"decided_by": "map", "external_name": "title as printed", "external_sku_id": "size:11x14"}}},
    {"product_id": "product-id-the-person-confirmed-today", "sku_id": "sku-id-when-one-variant-matched", "quantity": 1, "unit_price": 59.00,
     "custom_fields": {"channel_import": {"decided_by": "confirmed", "match_score": 0.78, "runner_up": "CUP-350", "external_name": "title as printed", "external_sku_id": ""}}},
    {"product_name_snapshot": "title as printed", "quantity": 1, "unit_price": 19.00,
     "custom_fields": {"channel_import": {"decided_by": "none", "external_name": "title as printed", "external_sku_id": ""}}}
  ]
}
```

No `status`, no `/submit`: the 201 is a draft. Send `Idempotency-Key:
tmall:TM202610080010012345` so a retry returns the same draft. The
`channel_import` object is this skill's own shape — the server stores it
and checks nothing in it; `decided_by` is `map`, `confirmed` or `none`.

```json
POST /external-document-links
{
  "source": "tmall",
  "external_kind": "order",
  "external_no": "TM202610080010012345",
  "entity_type": "sales_order",
  "entity_id": "the draft's id",
  "split": false
}
```

A 409 naming another order is a duplicate import that step 2 should have
caught: do not create a second link; report the draft for the person to
delete. `split: true` declares one platform order deliberately landed as
two drafts.

## Remembering a confirmed pairing

```json
POST /external-product-maps
{
  "source": "tmall",
  "external_name": "title as printed",
  "external_sku_id": "",
  "product_id": "the confirmed product id",
  "quantity": 1
}
```

One row per component of a bundle, written together; `external_product_id`
when the export carried a listing id; `sku_id` when the pairing is a
variant. Undated rows only — a window is $oryh-master-data's.

```json
PATCH /sales-order-items/{item_id}
{
  "product_id": "the product the person named for a line left in words",
  "sku_id": null,
  "custom_fields": {"channel_import": {"decided_by": "confirmed", "external_name": "title as printed", "external_sku_id": ""}}
}
```

For a line that landed in words and the person fills in afterwards — a
confirmation like any other, so its map row is written in the same wave.

## Read-back

```text
platform no.      | draft      | lines | map | confirmed today | none
TM2026…12345      | SO-000212  | 3     | 1   | 1               | 1
TM2026…12346      | already imported → SO-000198 (skipped)

confirmed today, map rows written:
  Insulated cup 500ml sakura pink, gift box | → CUP-500 · Insulated cup 500ml (0.78; matched: insulated cup 500ml; runner-up CUP-350 0.41)
unmatched, for the catalog desk:
  Scarf, autumn/winter | grey | no candidate above 0.6
```
