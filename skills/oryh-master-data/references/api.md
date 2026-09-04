# Oryh Master Data API Reference

Use with:

- header: `X-API-Key: <the principal's user-bound key>`
- base path: `api_base_url`, exactly as given — no version prefix to add
- capability: `master_data.manage` (the bundle only carries this skill when
  the principal's role has it)

## Reads

Every list here answers with ACTIVE rows by default; `status=archived` asks
for the history, `status=all` for both. An archived row is never a quieter
kind of live row.

```text
GET /auth/me                                  → permissions; confirm master_data.manage
GET /products?keyword=&status=active&size=200 → what the catalog already holds
GET /vendors?keyword=&tax_id=&status=active
GET /customers?keyword=&customer_kind=&customer_type=&phone=&tax_id=&status=active
GET /products/{id} · /vendors/{id} · /customers/{id}
```

`phone` is an exact match, and it is the lookup a retail counter actually
needs ("is this mobile number an existing customer"), the way `tax_id` is the one an invoicing desk
needs. `keyword` searches the name only.

```text
GET /type-options?family=customer_type       → the tenant's own customer categories
```

Read before a big import when the person asks whether it will duplicate anything — but you do not
need to: the upsert answers it definitively, and a dry run reports it.

## Product Pictures

```text
POST   /attachments                 → {filename, content_type: image/* or application/pdf, content_base64}; 10 MB max; returns the attachment id
GET    /product-images?product_id=&image_type=  → primary first, then sort_order; rows carry filename/content_type/size
POST   /product-images              → {product_id, attachment_id, image_type, is_primary?, sort_order?, caption?}; not image/* or PDF → 422; unknown image_type → 422 with the options; same pair twice → 409
PATCH  /product-images/{image_id}   → image_type, is_primary (demotes the old), sort_order, caption
GET    /type-options?family=product_image_type   → the tenant's picture kinds
DELETE /product-images/{image_id}   → removes the link; the bytes stay in the store
GET    /products/{product_id}/attachments/{attachment_id}/content   → the bytes, member-readable
```

## Bills Of Materials

```text
GET    /products?product_type=raw_material|semi_finished|finished_good|service
GET    /bills-of-materials?product_id=&status=&keyword=
POST   /bills-of-materials      → {product_id, version?, output_quantity?, status?, items: [{component_product_id, quantity, unit?, scrap_rate?}]}
GET    /bills-of-materials/{bom_id}            → with items
PATCH  /bills-of-materials/{bom_id}            → status active demotes the old active; output_quantity only while draft
DELETE /bills-of-materials/{bom_id}            → archive
GET    /bills-of-materials/{bom_id}/explode?quantity=&with_stock=   → lines by level + leaf_requirements (ATP, shortage)
POST   /bom-items · PATCH /bom-items/{item_id} · DELETE /bom-items/{item_id}   → draft recipes only (409 otherwise)
```

A parent that is a raw material or a service → 422; a component that is a
service, the parent, or anything made from the parent → 422 naming the path.

## Stores And Facilities

```text
GET    /facilities?facility_type=&status=&keyword=
POST   /facilities               → {name, facility_type, facility_code?, address?}; type from the facility_type vocabulary; duplicate active name → 409
PATCH  /facilities/{facility_id} · DELETE → archive (frees the name)

GET    /sales-channels?channel_kind=&status=&keyword=
POST   /sales-channels           → {channel_code, name, channel_kind, remarks?}; code lowercased and
                                   immutable; same code again → 409 naming the row (revive it)
PATCH  /sales-channels/{id} · DELETE → archive; stores and maps keep their pointer
GET    /stores?channel=&source=&status=&keyword=   → source= lists every store under that channel
POST   /stores                   → {name, channel: offline|online, sales_channel_id? | source?, store_code?, address?}
                                   an unregistered source → 422 "register it first"; reads carry
                                   sales_channel_id, sales_channel_name and source (the code)
GET    /stores/{store_id}        → includes fulfilment_facilities, preferred first
PATCH  /stores/{store_id} · DELETE → archive; orders keep their pointer

GET    /store-facilities?store_id=&facility_id=&status=
POST   /store-facilities         → {store_id, facility_id, priority?}; 409 if the pair exists — PATCH it (archived revives)
PATCH  /store-facilities/{link_id} · DELETE → archive
```

Sales orders may carry `store_id` (nullable); an archived store refuses new
orders with the fix and keeps the old ones.

## Product Categories (the shelving)

```text
GET    /product-categories?parent_id=&root_only=&status=&keyword=   → rows carry parent_name
POST   /product-categories       → {name, category_code?, parent_id?, description?}; duplicate active sibling name → 409
PATCH  /product-categories/{category_id}   → rename/move/revive; self or descendant parent → 422, archived parent → 409
DELETE /product-categories/{category_id}   → archive; children and products keep their pointers
```

Products point at the tree: `category_id` on POST/PATCH `/products` (an
archived category → 409 naming the fix), `GET /products?category_id=` filters
one shelf, and a bulk product row may carry `category_code` — resolved
against existing categories, never auto-created; explicit `null` takes the
product off its shelf.

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
{"product_code": "P-001", "name": "Endoscope lens", "spec": "4mm 30°", "unit": "each",
 "list_price": 1200.00, "currency": "CNY", "status": "active", "metadata": {}}

// vendors
{"vendor_code": "V-001", "name": "East China Medical Devices", "tax_id": "91310000MA1K3XXXXX",
 "contact": "Manager Wang", "email": "wang@example.com", "phone": "13800000000",
 "status": "active", "metadata": {}}

// customers — B2B
{"customer_code": "C-001", "name": "City First Hospital", "customer_kind": "company",
 "customer_type": "institution", "tax_id": "12310000MB0K1XXXXX",
 "contact": "Procurement, Ms Li", "email": "", "phone": "021-6000000",
 "address": "Huangpu District, Shanghai…", "status": "active", "metadata": {}}

// customers — a retail member. Same table, same endpoint, same upsert. A member
// has no tax id and often no address; the phone is what identifies them.
{"customer_code": "M-13800000000", "name": "Ms Zhang", "customer_kind": "person",
 "customer_type": "retail", "phone": "13800000000", "status": "active",
 "metadata": {"membership_tier": "gold", "issuing_store": "Nanjing West Road"}}
```

`status` is `active` or `archived`. `currency` is a 3-letter code, default
`CNY`. `metadata` is a free-form object for columns with no first-class home.

### Retail and B2B customers (`customer_kind` / `customer_type`)

Both live in `/customers`. There is no separate retail table, because nothing
downstream differs: a member and a group account quote, order, get invoiced, pay and
run a standing balance through identical machinery.

What differs is the file, and two optional fields carry it:

- `customer_kind` — `person` (an individual: retail, member, private customer)
  or `company` (an organisation: business, hospital, school, government). A
  fixed pair; the server refuses anything else.
  **Omit it when you do not know.** Null means nobody has stated a kind, which
  is a true statement; `company` guessed onto a member is a false one. A sole proprietor genuinely sits on the line, so ask
  rather than deciding.
- `customer_type` — the tenant's own customer category, from the
  `customer_type` vocabulary: shipped values are `retail`, `wholesale`,
  `distributor`, `enterprise`, `institution` (government and public bodies),
  `online`, `affiliate` and `other`. Read
  `GET /type-options?family=customer_type` first — the workspace may have
  added its own (group buyers, franchisees) or archived ones it never uses.

  Send the vocabulary's **name**, never the sheet's word. Names are
  `^[a-z][a-z0-9_]{0,49}$` and the display wording sits in the title, so a category
  column mapped straight through fails the request shape and takes the whole
  chunk with it — 422, nothing written, no per-row report to hand back. A
  well-formed name the tenant simply does not have is the gentler failure, and
  that one IS per-row, exactly like an unknown `price_type`:

  ```text
  unknown customer_type 'group_buy' — active options: affiliate, distributor, …
  ```

  Propose the new type and re-run:
  `POST /type-options {"family": "customer_type", "name": "group_buy",
  "title": "Group buyer"}`. Never bend the sheet's word into the nearest shipped
  value — a franchisee filed as `distributor` makes every later report lie about who
  those customers are.

Neither field changes what the system will let anyone do. Pricing, payment terms and
whether a member prepays are judgments for the selling and finance skills, not
gates on the customer record.

`customer_code` is required for retail rows too — SKILL.md says how to
settle one for the whole batch.

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
{"product_code": "P-001", "name": "Endoscope lens", "list_price": 1200.00,
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
  their own (dealer, member…) or archived shipped ones — the current vocabulary
  is `GET /type-options?family=product_price_type`, and an unknown value is a
  422 that lists the active options. A column that matches none of them wants
  a NEW type (`POST /type-options`, see below), not the closest fit. The product's own `list_price` column
  stays the quoting reference; the book holds the other kinds. `cost` is a
  standard cost with no named supplier — a supplier's own price belongs on
  their link's `last_price`.
- `tax_in_price` (default true) and `tax_percentage` record tax inclusion and rate as the
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

## Type Vocabularies (the tenant may extend these)

The type families below are tenant-owned vocabularies, not fixed enums.
Two calls, and both belong in the agent's repertoire:

```text
GET  /type-options?family={family}&status=active   → what this tenant accepts NOW
POST /type-options                                 → define a new one (needs object_types.manage)
PATCH /type-options/{type_option_id}               → retitle/describe an existing one (same gate)
     {"family": "product_price_type", "name": "dealer_tier2", "title": "Tier-2 dealer price"}
```

Families: `product_price_type` · `sales_adjustment_type` (quotation AND order
adjustments) · `expense_category` · `work_type` · `customer_type` ·
`product_image_type` · `facility_type` · `sales_channel_kind`. `name` is lowercase
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

GET    /customer-products?product_id=&customer_id=&customer_product_code=&status=   → rows carry customer_name
POST   /customer-products           → 409 if the (product, customer) pair exists — PATCH that row (revives archived)
PATCH  /customer-products/{customer_product_id}   → agreed_price/code/name/MOQ; the pair itself is fixed
DELETE /customer-products/{customer_product_id}   → archive; the agreement lapses, the pair stays claimed
```

`POST /product-prices` may carry `sku_id` to price one variant; the SKU must
belong to the product (400 otherwise). Bulk rows write product-level prices
only.

## Customer Contacts (the rolodex)

```text
GET    /customer-contacts?customer_id=&phone=&status=&keyword=   → primary lists first
POST   /customer-contacts        → 404 if the customer is not here; phone dup at the same customer → 409
PATCH  /customer-contacts/{contact_id}   → fields incl. is_primary (new primary demotes the old)
DELETE /customer-contacts/{contact_id}   → archive; frees the phone slot and the primary slot
```

```json
POST /customer-contacts
{
  "customer_id": "customer-id",
  "name": "Zhang Jie",
  "title": "Finance",
  "phone": "13800000003",
  "is_primary": true
}
```

## The External Product Map (channel listings → catalog)

What a platform's product id means in this catalog: Tmall listing 6543… IS
product X, or IS 2× cup and 1× lid (a bundle = several rows with
quantities). The channel mirror of supplier-products — that table maps a
vendor's code for what the tenant buys; this one maps Tmall/JD/Amazon/a
mini-program's id — or its TITLE, since most exports carry no id — for what
it sells. Order-recording agents READ this map to translate channel orders,
and order desks may POST title-keyed map rows after a person confirms the candidate; id-keyed rows, edits, effective-date swaps and deletion stay with $oryh-master-data.

```text
GET    /external-product-maps?source=&external_product_id=&external_sku_id=&product_id=&status=
GET    /external-product-maps?source=&external_product_id=&at=2026-08-10
                                    → the map AS OF that date (live rows whose window covers it)
GET    /external-product-maps?source=&external_name=&at=   → the same by title (matching form:
                                    fullwidth spacing, case and doubled spaces forgiven)
GET    /external-product-maps?source=&keyword=             → loose search over titles, for curation
POST   /external-product-maps       → 409 only if an OPEN-ended live row already pairs this
                                      (source, listing, product); closed windows never block;
                                      omit external_product_id and the TITLE is the identity;
                                      a row naming neither id nor title is a 422
PATCH  /external-product-maps/{map_id}   → external_name/sku_id/quantity/effective_from/
                                           effective_to/status; identity fields are fixed, and
                                           the title is editable only on id-keyed rows (a
                                           snapshot there) — a title-keyed row swaps via effective_to
GET    /product-matches?title=&limit=      → active products ranked against a platform title
                                           (CJK bigrams + words): candidates for a person to
                                           confirm, never a decision
DELETE /external-product-maps/{map_id}   → archive = WITHDRAWN (a mistaken pairing);
                                           never how a superseded pairing is recorded
```

```json
POST /external-product-maps
{
  "source": "tmall",
  "external_product_id": "654321987",
  "external_sku_id": "4890",
  "external_name": "Two-cup set with lid",
  "product_id": "product-id",
  "quantity": 2
}
```

- `source` is the platform, lowercased by the server — "Tmall" and "tmall"
  must not split the mapping space — and it must be a registered
  `/sales-channels` code (422 otherwise: register the channel first).
- `quantity` is the bundle multiplier: one unit of the listing = N of this
  product. A bundle is SEVERAL rows for the same (source, listing), one per
  component. A wrong pairing is deleted and re-created — identity fields
  never bend.
- `sku_id` (optional) must belong to `product_id` (422 otherwise);
  `external_sku_id` holds the PLATFORM's sku when it distinguishes one.
- `effective_from` / `effective_to` bound WHEN the pairing described the
  listing — half-open `[from, to)`, null bounds open, both omitted =
  "always". **A listing swap is: PATCH the old row's `effective_to`, POST
  the new row with the same date as `effective_from`.** The old row stays
  active (it still translates back-dated orders); the swap day belongs to
  the new meaning. Swapping back later is allowed — only a second
  open-ended row for the same pairing is a 409. Recording a purely
  historical pairing (both bounds set) is also legal, e.g. when onboarding
  mid-year and importing last month's orders.

The external ORDER number is not master data: it lands in
`/external-document-links` when the order is recorded ($oryh-order-submit).

## Inventory

The stock ledger is not master data. `/inventory-items`,
`/inventory-item-details` and the stock-count import (`POST
/inventory-items/bulk`) moved to `$oryh-inventory`, under their own capability
`inventory.manage` — held by the warehouse, not by default by a catalog
administrator. Products, SKUs, vendors and customers stay here; a stock sheet
goes there.

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
