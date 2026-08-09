# Oryh Master Data API Reference

Use with:

- header: `X-API-Key: <the principal's user-bound key>`
- base path: `api_base_url`, exactly as given — no version prefix to add
- capability: `master_data.manage` (the bundle only carries this skill when
  the principal's role has it)

## Reads

```text
GET /auth/me                                  → permissions; confirm master_data.manage
GET /products?keyword=&status=active&size=200 → what the catalog already holds
GET /vendors?keyword=&tax_id=&status=active
GET /customers?keyword=&customer_kind=&customer_type=&phone=&tax_id=&status=active
GET /products/{id} · /vendors/{id} · /customers/{id}
```

`phone` is an exact match, and it is the lookup a retail counter actually
needs ("这个手机号是不是老客户"), the way `tax_id` is the one an invoicing desk
needs. `keyword` searches the name only.

```text
GET /type-options?family=customer_type       → the tenant's own 客户分类
```

Read before a big import when the person asks "会不会重复" — but you do not
need to: the upsert answers it definitively, and a dry run reports it.

## Bulk Upsert

```text
POST /products/bulk
POST /vendors/bulk
POST /customers/bulk
```

Request:

```json
{
  "rows": [ ... ],
  "dry_run": false,
  "on_error": "abort"
}
```

- `rows` — 1 to 500 entries. Longer files are chunked by the caller — or by
  the bundled `scripts/bulk_import.py`, which chunks, keeps reported indexes
  global to your file, and stops after a bad chunk in abort mode:

  Run from this skill's directory; the path is relative to it.

  ```text
  python3 scripts/bulk_import.py --kind products rows.json            (dry run)
  python3 scripts/bulk_import.py --kind products rows.json --apply
  ```
- `dry_run` (default `false`) — runs the identical write path and rolls back.
  The preview therefore cannot disagree with the real write.
- `on_error` — `"abort"` (default: any bad row and NOTHING is written) or
  `"skip"` (apply the good rows, report the rest).

### Row shapes

Only `*_code` and `name` are required. **Fields you omit are left alone on an
existing record** — a price-only sheet does not blank a curated `spec`. To
clear a field deliberately, send it explicitly as `null` — that works for the
nullable fields (`spec`, `unit`, `list_price`, `tax_id`, `contact`, `email`,
`phone`, `address`); `name`, `status`, `currency` are not nullable (`null` →
422 for the whole chunk), and `metadata` is cleared with `{}`.

```jsonc
// products
{"product_code": "P-001", "name": "内窥镜镜头", "spec": "4mm 30°", "unit": "个",
 "list_price": 1200.00, "currency": "CNY", "status": "active", "metadata": {}}

// vendors
{"vendor_code": "V-001", "name": "华东医疗器械", "tax_id": "91310000MA1K3XXXXX",
 "contact": "王经理", "email": "wang@example.com", "phone": "13800000000",
 "status": "active", "metadata": {}}

// customers — B2B
{"customer_code": "C-001", "name": "市第一医院", "customer_kind": "company",
 "customer_type": "institution", "tax_id": "12310000MB0K1XXXXX",
 "contact": "采购科 李老师", "email": "", "phone": "021-6000000",
 "address": "上海市黄浦区…", "status": "active", "metadata": {}}

// customers — 零售会员. Same table, same endpoint, same upsert. A member has
// no 税号 and often no address; the phone is what identifies them.
{"customer_code": "M-13800000000", "name": "张女士", "customer_kind": "person",
 "customer_type": "retail", "phone": "13800000000", "status": "active",
 "metadata": {"会员等级": "金卡", "开卡门店": "南京西路店"}}
```

`status` is `active` or `archived`. `currency` is a 3-letter code, default
`CNY`. `metadata` is a free-form object for columns with no first-class home.

### Retail and B2B customers (`customer_kind` / `customer_type`)

Both live in `/customers`. There is no separate retail table, because nothing
downstream differs: a member and a 集团客户 quote, order, get invoiced, pay and
run a standing balance through identical machinery.

What differs is the file, and two optional fields carry it:

- `customer_kind` — `person` (自然人：零售、会员、个人客户) or `company`
  (组织：企业、医院、学校、政府). A fixed pair; the server refuses anything else.
  **Omit it when you do not know.** Null means nobody has stated a kind, which
  is a true statement; `company` guessed onto a member is a false one, and
  个体工商户 genuinely sits on the line — ask the person rather than deciding.
- `customer_type` — the tenant's own 客户分类, from the `customer_type`
  vocabulary: shipped values are `retail` 零售客户, `wholesale` 批发客户,
  `distributor` 经销商, `enterprise` 企业客户, `institution` 政企机构,
  `online` 电商客户, `affiliate` 关联方, `other` 其他. Read
  `GET /type-options?family=customer_type` first — the workspace may have
  added its own (团购客户, 加盟商) or archived ones it never uses.

  Send the vocabulary's **name**, never the sheet's word. Names are
  `^[a-z][a-z0-9_]{0,49}$` and the Chinese sits in the title, so a 客户分类
  column mapped straight through fails the request shape and takes the whole
  chunk with it — 422, nothing written, no per-row report to hand back. A
  well-formed name the tenant simply does not have is the gentler failure, and
  that one IS per-row, exactly like an unknown `price_type`:

  ```text
  unknown customer_type 'group_buy' — active options: affiliate, distributor, …
  ```

  Propose the new type and re-run:
  `POST /type-options {"family": "customer_type", "name": "group_buy",
  "title": "团购客户"}`. Never bend the sheet's word into the nearest shipped
  value — 加盟商 filed as `distributor` makes every later report lie about who
  those customers are.

Neither field changes what the system will let anyone do. Pricing, 账期 and
whether a member prepays are judgments for the selling and finance skills, not
gates on the customer record.

For a retail import, tell the person plainly that `customer_code` is still
required and ask what to use — the member number if their old system had one,
otherwise the phone (`M-13800000000`), agreed once and applied to every row so
the next import updates instead of duplicating.

### Response

```json
{
  "data": {
    "dry_run": false,
    "applied": true,
    "summary": {"total": 62, "created": 47, "updated": 12, "unchanged": 2, "failed": 1},
    "results": [
      {"index": 0, "code": "P-001", "outcome": "created", "id": "…"},
      {"index": 1, "code": "P-002", "outcome": "updated", "id": "…", "changed": ["list_price"]},
      {"index": 2, "code": "P-003", "outcome": "unchanged", "id": "…", "changed": []},
      {"index": 3, "code": null, "outcome": "error",
       "error": "product_code is required and cannot be blank"}
    ]
  }
}
```

- `applied` — whether anything was committed. `false` for a dry run, and
  `false` for an aborted run. **Read it before reporting success.**
- `index` — the row's position in YOUR `rows` array. Map it back to the
  spreadsheet line so the person can find it.
- `changed` — which fields an update actually moved (present only on `updated`/
  `unchanged` rows; `created` rows omit the key). Report these; a mapping
  mistake usually shows up here as "every row updated the same odd field".
- `unchanged` — matched, nothing differed. A whole run of these means the
  import already happened.

Errors reported per row (never fatal to the request):

- `{code} is required and cannot be blank` (a whitespace-only code; a
  literally EMPTY code string fails schema validation instead and 422s the
  whole chunk — one more reason to normalise rows before sending)
- `duplicate {code} in this batch (also row N)`

HTTP-level failures:

- `403` — the principal lacks `master_data.manage`.
- `422` — a row failed schema validation (missing `name`, price out of range,
  over 500 rows). The body names the offending row index and field.

### Prices and suppliers on a row

A product row may carry a price book and supply sources; omitted lists leave
existing rows alone, like every omitted field:

```jsonc
{"product_code": "P-001", "name": "内窥镜镜头", "list_price": 1200.00,
 "prices": [
   {"price_type": "wholesale", "price": 980.00, "tax_percentage": 13},
   {"price_type": "cost", "price": 810.00, "tax_in_price": false}
 ],
 "suppliers": [
   {"vendor_code": "V-001", "supplier_product_code": "HD-XX-01",
    "last_price": 810.00, "lead_time_days": 7, "min_order_quantity": 10}
 ]}
```

- `price_type`: the shipped catalog is `list | default | promo | wholesale |
  competitive | minimum | maximum | cost`, but the tenant may have defined
  their own (经销价、会员价…) or archived shipped ones — the current vocabulary
  is `GET /type-options?family=product_price_type`, and an unknown value is a
  422 that lists the active options. A column that matches none of them wants
  a NEW type (`POST /type-options`, see below), not the closest fit. The product's own `list_price` column
  stays the quoting reference; the book holds the other kinds. `cost` is a
  standard cost with no named supplier — a supplier's own price belongs on
  their link's `last_price`.
- `tax_in_price` (default true) and `tax_percentage` record 含税/税率 as the
  person stated them — never derive one from the other.
- Price upsert key: (`price_type`, `currency`). An equal live price is
  unchanged; a different one ARCHIVES the old row and creates the new — that
  is the price history, status instead of date ranges.
- Supplier upsert key: (product, `vendor_code`). Fields update in place
  (`last_price` means "most recent"); re-importing an archived pair revives
  it. `vendor_code` must exist in vendor master data — an unknown code is a
  per-row error, never an invented vendor: import vendors first.
- Two prices for one (`price_type`, `currency`) or two entries for one
  `vendor_code` in a single row: per-row error, the person's conflict.
- Row results report nested movement as `changed: ["prices"]` /
  `["suppliers"]`.

## Type Vocabularies (租户可自定义)

`price_type`, `adjustment_type`, `category` and `work_type` are tenant-owned
vocabularies, not fixed enums. Two calls, and both belong in the agent's
repertoire:

```text
GET  /type-options?family={family}&status=active   → what this tenant accepts NOW
POST /type-options                                 → define a new one (needs object_types.manage)
PATCH /type-options/{type_option_id}               → retitle/describe an existing one (same gate);
                                                     a live E2E run watched an agent deny this exists
     {"family": "product_price_type", "name": "dealer_tier2", "title": "二级经销价"}
```

Families: `product_price_type` · `sales_adjustment_type` (quotation AND order
adjustments) · `expense_category` · `work_type`. `name` is lowercase
`[a-z][a-z0-9_]*`; colliding with a shipped value is a 409; `DELETE` archives
a type (existing records keep their value, new writes stop accepting it).

**When a real-world fact fits none of the active options, defining a new type
is the correct move — approximating it into a near-miss is not.** Propose it
to the person in their own words, create it on a yes, then continue. A 403
means this credential lacks `object_types.manage`: name the type you need and
ask an admin to add it, rather than writing a wrong one.

## Price Book And Supplier Endpoints

Same capability (`master_data.manage`) for writes; any tenant credential reads.

```text
GET    /product-prices?product_id=&sku_id=&price_type=&currency=&status=
POST   /product-prices              → 409 if the (product, sku, type, currency) slot has an active row
PATCH  /product-prices/{price_id}   → price/tax/status/metadata; identity fields are fixed
DELETE /product-prices/{price_id}   → archive (history, never gone)

GET    /supplier-products?product_id=&vendor_id=&status=   → preferred sources first; rows carry vendor_name
POST   /supplier-products           → 409 if the (product, vendor) pair exists — PATCH that row instead
PATCH  /supplier-products/{supplier_product_id}
DELETE /supplier-products/{supplier_product_id}            → archive; re-import or PATCH status revives
```

`POST /product-prices` may carry `sku_id` to price one variant; the SKU must
belong to the product (400 otherwise). Bulk rows write product-level prices
only.

## Inventory (盘点导入)

Stock lives on a LEDGER. An inventory item's `quantity_on_hand` /
`available_to_promise` are running sums of its detail rows — nothing edits
them directly, and the import obeys the same rule:

```text
POST /inventory-items/bulk
{"rows": [
  {"product_code": "P-001", "facility": "总仓", "lot_id": "B2026-07",
   "quantity": 120.5, "expire_date": "2027-06-30"}
 ], "dry_run": true, "on_error": "abort"}
```

- The stock position is (product-or-sku, `facility`, `lot_id`); `sku_code`
  names a variant, empty facility/lot mean "unspecified". One row per
  position per file — a duplicate is a per-row error.
- No item at that position yet → created, opening balance recorded as a
  ledger detail with reason `import_initial`.
- Counted `quantity` equals the system count → `unchanged`, no ledger noise.
- Counted `quantity` DIFFERS → the item is NOT edited: a detail is appended
  with `quantity_on_hand_diff` = (counted − system), reason
  `import_override`, its description naming both numbers（导入覆盖：系统数量
  X → 导入数量 Y）. The row result reports `changed: ["quantity_on_hand"]`.
- `product_code` (and `sku_code`) must already exist — unknown codes are
  per-row errors, never invented records.

Endpoints:

```text
GET    /inventory-items?product_id=&sku_id=&facility=&lot_id=&status=
POST   /inventory-items             → optional initial_quantity lands as the first detail; 409 if the position exists
PATCH  /inventory-items/{item_id}   → identity/dates/cost only — it has NO quantity fields; sending one is a 422
DELETE /inventory-items/{item_id}   → archive (the ledger beneath stays)

GET    /inventory-item-details?inventory_item_id=&reason=&entity_type=&entity_id=
POST   /inventory-item-details      → append one movement; the ONLY way totals move
```

Details are immutable — no update, no delete, no per-row path; a mistake is
corrected by a counter-entry. `reason` catalog: `initial | import_initial |
import_override | received | issued | adjustment | damaged | returned |
transfer | other`. A movement caused by a record in the system carries it in
(`entity_type`, `entity_id`). Posting to an archived item is a 409.

## Single-Record Writes

Same capability; for one-off edits rather than a file.

```text
POST   /products            → create one (409 if the code already exists)
PATCH  /products/{id}       → change fields; only what you send
DELETE /products/{id}       → archive (soft; the row and its code remain)
```

Vendors and customers mirror this exactly. Prefer the bulk endpoint even for a
handful of rows — it gives you the dry run.

## Codes Are Unique Per Tenant

Enforced by the database, per company: two products in one tenant cannot share
a `product_code`. A single `POST` colliding with an existing code returns
`409` naming it. In a bulk upsert the same collision is not an error at all —
it is the update path, which is the entire point.
