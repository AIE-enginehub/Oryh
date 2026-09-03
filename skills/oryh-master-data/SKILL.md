---
name: oryh-master-data
description: Use when a person's AI agent needs to load or maintain the company's master data in oryh — importing products, vendors, or customers from a spreadsheet ("import the products in this Excel file"), adding or correcting entries by hand, archiving obsolete ones, or auditing what the catalog already holds. Also curates the external product map ("天猫这个商品对应我们哪个货"、"京东商品id映射"): which platform listing means which catalog product, bundles included. Covers reading the file locally, working out which column means what and confirming it with the person, a dry-run preview before anything is written, upsert by the tenant's own code, and per-row reporting. Requires master-data management rights; ordinary submit/approve skills read this catalog but must never write it.
required_capability: master_data.manage
---

# Oryh Master Data

Own the catalog the rest of the company quotes and requisitions against:
**products**, **vendors**, **customers**. All three behave identically here —
same key, same upsert, same preview — so learn it once.

Customers means both kinds. A retail membership list and a dealer list go to
the same `/customers` endpoint; what tells them apart is two optional fields on the row
(`customer_kind`, `customer_type`), not a different table. See
[references/api.md](references/api.md#retail-and-b2b-customers-customer_kind--customer_type).

The common job is a spreadsheet: someone has a product list in .xlsx and wants
it in the system. That job is mostly not about the API. It is about reading a human
artifact correctly, and the two failure modes are silent ones:

- **Guessing a column wrong.** A "unit price" column might be the list price or
  the last purchase price. Guess, and every quote built on it is wrong, with nothing
  to show that anything went astray.
- **Inventing a code.** The code is the identity. Make one up and the next
  import cannot match it, so it lands a second time as a new product.

Both are resolved the same way: **ask the person**. They have the file open.

{{include:_common/answer-the-question.md}}

## The Code Is The Identity

Every row needs the tenant's own code — `product_code`, `vendor_code`, or
`customer_code`. It is what the server upserts on:

- code not in the system → **created**
- code already there → **updated**, and only the fields your row carries
- same import run twice → **unchanged**, nothing duplicated

So re-running a corrected file is always safe, and is the intended fix for a
bad row. Two things follow that you must not work around:

- **A row without a code is an error, not a row to improvise.** Never
  synthesise one from the name, the line number, or a counter. Collect every
  such row and take them back to the person: "these 3 rows have no code — which
  value should fill it?"
- **A code repeated inside one file is an error too.** Do not pick a winner —
  the person needs to know their sheet has two rows claiming one code.

Archived entries keep their code on purpose, so re-importing one revives it
rather than leaving a duplicate beside it.

## Trigger Examples

- "Import all the products in this Excel file"
- "The vendor list has been updated, import it again"
- "The customer list is in this CSV, please create the records"
- "Rename product P-1024" (single edit — same endpoints, one row)
- "These products are discontinued" (archive: `status: archived`)

## Required Inputs

```yaml
oryh:
  base_url: "{{ORYH_BASE_URL}}"
  api_base_url: "{{ORYH_API_BASE_URL}}"
  api_key: "{{ORYH_API_KEY}}"
```

The file itself is on the person's machine — read it where it is. Nothing is
uploaded to oryh; the server never sees the spreadsheet, only the rows you
decided to send.

## Steps

```text
1. Read the file locally (.xlsx / .xls / .csv). Find the header row — it is
   not always row 1; real sheets carry a title, a blank line, sometimes a
   merged banner above the header.

2. Work out the column mapping, then SHOW IT AND GET AGREEMENT before
   writing anything. Present it compactly:

     code  ← "Material No."     name  ← "Product name"
     spec  ← "Specification"   unit  ← "Unit"
     price ← "Tax-inclusive unit price"  → list_price?  ← ask, do not assume

   - The code column is rarely called "product_code". Expect Material No.,
     Part No., Code, Item No., Product Code, Stock Code, Item Code, SKU — and
     their Chinese equivalents, which is what most real sheets carry.
   - Say which columns you are IGNORING too. A stock-quantity or remarks column
     you silently drop is a decision the person did not get to make.
   - Ambiguous or missing → ask. Especially any price column: list_price is
     the catalog reference price others quote against.
   - Purchase price, cost, wholesale and promotional prices now have real homes
     instead of being dropped:
     a cost tied to a named supplier → that row's `suppliers` entry
     (`vendor_code` + `last_price`); a price of another kind → a `prices`
     entry with its `price_type` (wholesale/promo/cost/...). Supplier columns
     (their part number, lead time, minimum order quantity) ride the same
     `suppliers` entry. The vendor
     must already exist in master data — import vendors before products that
     reference them, in the same conversation if need be.
   - **A price column that fits NO existing type is a new type, not a
     shoehorn.** A dealer, member or tier-one price forced into `wholesale`
     makes every later report lie about what that number is. Read the tenant's current
     vocabulary first (`GET /type-options?family=product_price_type` — it
     may already hold exactly what this column means), and when nothing
     fits, say so and offer to define it:
     "the sheet's tier-two dealer price matches none of the existing types.
     Shall I define a new price type dealer_tier2 for it?" On yes:
     `POST /type-options {"family": "product_price_type", "name":
     "dealer_tier2", "title": "Tier-2 dealer price"}` — then import. A 403 means this
     credential lacks `object_types.manage`: say which type is needed and
     ask an admin to add it; do NOT fall back to a wrong existing type.
     The same applies to expense categories and work types in their own
     families.
   - Customer sheets carry one question of their own: **who are these people**.
     A membership sign-up sheet and a dealer list both go to `/customers`, but
     `customer_kind` (person / company) and `customer_type` (retail, wholesale,
     dealer, e-commerce, government/enterprise — taken from
     `GET /type-options?family=customer_type`) have to be stated. If the sheet
     has a customer-type or customer-category column, map from it; propose a new
     type for words that map to nothing, exactly as with price types. **Send the
     type's `name`, not the sheet's own wording** — `name` must match
     `^[a-z][a-z0-9_]{0,49}$`, and putting the raw label into `customer_type`
     fails the WHOLE batch with a 422, landing not one row and leaving no
     per-row report to go through with the person.
     **If the sheet has no such column, do not fill it in for them** — leaving it
     out says "nobody stated this", while guessing `company` is a false
     statement, and a sole proprietor looks like neither. Just ask:
     "are these retail members or business customers? Shall I file them as
     person/retail?"
   - Retail sheets often have no code column at all, only a mobile number.
     `customer_code` is still the required identity, so settle **once** what
     serves as the code: the membership number from the old system, or the
     mobile number with a prefix (`M-13800000000`). Apply that decision to the
     whole batch, so the next import updates rather than rebuilds.
   - Historical document sheets (tens or hundreds of thousands of past
     quotations and orders) are not this skill's job: hand them to
     $oryh-data-migration, which owns bulk document import, chunking, resume
     and problem-document summaries. **But the order starts here** — customer
     and product master data must be imported first, or every document is
     skipped for an unresolvable reference.
   - Stock-count sheets (quantity, facility, lot, expiry) are not master
     data: they are the stock ledger, and `$oryh-inventory` owns it — a
     different capability (`inventory.manage`) held by the warehouse, not
     the catalog administrator. Hand the sheet over rather than posting it.
   - Columns with no home in the schema can go into `metadata` rather than
     be thrown away — offer it, do not do it silently.

3. Normalise each row:
   - trim whitespace everywhere (spreadsheet cells are full of it)
   - prices: strip currency symbols, thousands separators and blanks → number;
     a blank price is null, NOT 0
   - `status`: default "active"; only "archived" if the sheet says so
   - keep the person's own text; do not "tidy" a product name or specification

4. DRY RUN first, always:
     POST /products/bulk  {"rows": [...], "dry_run": true}
   When you can run Python, prefer the bundled script — write the normalised
   rows to a JSON file and run (from this skill's directory):
     python3 scripts/bulk_import.py --kind products rows.json
   It dry-runs by default, chunks large files, keeps row indexes global to
   your file, and aggregates a changed-fields histogram. Either way, report
   what the response says — 47 to create, 12 to update, 3 with problems — and
   for the updates, say WHICH fields move (the response names them). "12
   updates, all of them price-only" is the sentence that lets a person catch a
   bad mapping before it lands.

5. Get explicit confirmation, then re-send with dry_run false (script: add
   `--apply`).
   - Errors present? Default is `on_error: "abort"` — nothing is written and
     the person fixes the file. Offer `"skip"` only if they would rather
     import the good rows now and handle the rest after; say plainly how many
     are being left out.

6. Report the result per the response: created / updated / unchanged /
   failed, and for failures the row `index` (map it back to the person's
   spreadsheet line — the server counts your rows array from 0) with its
   reason. Never report success you did not read in the response.
```

Files over 500 rows: send in chunks of 500, in order, and report cumulatively.
Dry-run every chunk first — a mapping error shows up in chunk 1 and should
stop the rest. The bundled script does exactly this (chunking, ordered sends,
stop on the first bad chunk, cumulative report); the manual rule is for when
you call the endpoint yourself.

## Validate Before Writing

- Every row has a non-blank code, or the run does not go out.
- No code appears twice in the batch.
- A row's `suppliers` reference vendors by their `vendor_code` — codes that
  are not in vendor master data yet are that row's error; never invent a
  vendor to make an import pass.
- One price per (`price_type`, currency) per row; a re-imported equal price
  is unchanged, a different one archives the old and records the new — that
  is the intended price history, not a duplicate.
- Prices are numbers ≥ 0; a blank is null, never 0. 0 means "free", and for a
  list price that is a claim, not a gap.
- Names are the person's text, not your improvement of it.
- You showed the mapping and the person agreed to it.
- You showed a dry-run and the person agreed to it.

## What Happens Next (so you can answer the principal)

Imported products, vendors, and customers become immediately matchable by
everyone else's skills — a salesperson quoting tomorrow will find these by
keyword, and a cataloged line carries `list_price` as the reference price the
discount is judged against. That is exactly why a wrong price column is
expensive: it is not a bad cell, it is a wrong discount on every future quote.

Nothing here needs approval — master data is not a submitted document. The
import is recorded in the tenant audit log as one `master_data.imported` event
with its counts.

## The Shelving: Product Categories

`/product-categories` is a TREE the products hang off — one parent per
category, `category_id` on the product row. It is master data like the
products themselves: everyone reads it, this desk writes it.

- **A sheet's category column is a tree to propose, not strings to file.**
  Collect the distinct values, show the tree you would create ("Valves →
  ball/gate — two levels, five shelves?"), get agreement, create the
  categories FIRST, then import products with each row's `category_code`.
  An unknown code in a bulk row is that row's error — the server never
  invents a shelf, exactly as it never invents a vendor.
- **Same name, two parents: fine. Same name, one parent: 409.** Two live
  "Parts" folders at one level is a filing error; archiving frees the name.
- **Archiving a shelf strands nothing.** Children and products keep their
  pointers (history, not a cascade) — but NEW filing onto an archived
  shelf is refused with "revive it first". Moving a category under its
  own descendant is refused too; the tree cannot fold into itself.
- A product needing two homes is a judgment call for the person — pick
  the primary shelf; the other axis is usually a `customer_type`-style
  vocabulary or a metadata tag, not a second tree.

## Product Pictures

A picture is an attachment (the receipts' own store — tenant-scoped, 10 MB
per file, deduplicated by content) linked to a product through
`/product-images`. Upload first, link second: `POST /attachments` with the
file's base64 and its real content type — `image/*`, or `application/pdf`
for a design draft; anything else (a spreadsheet, a CAD source) is refused
as a picture (422) and belongs on a document. This desk's grant covers
filing attachments. Then `POST /product-images {"product_id",
"attachment_id", "image_type", "is_primary"?, "sort_order"?, "caption"?}`.

- **Say what KIND each picture is.** `image_type` is the tenant's
  `product_image_type` vocabulary (shipped: `main` (the hero shot),
  `detail` (detail-page shots), `design` (a design draft), `packaging`,
  `dimension` (a dimension drawing), `other`;
  `GET /type-options?family=product_image_type` for the current
  set, and a kind the workspace lacks is a new type option, never a
  shoehorn). The kind is orthogonal to the primary: the primary says which
  picture REPRESENTS the product, the kind says what it is — a design
  draft is rarely the primary. A folder of files usually names the kind
  (main / detail / design, or their local-language equivalents); confirm
  the mapping before writing, and
  never file everything as `other` because it was quicker.
- **Ask by kind**: `GET /product-images?product_id=&image_type=detail`
  hands the platform sync every detail shot at once.

- **One primary per product**, and setting a new one demotes the old in
  the same write — never the two-step. The primary is what lists, quotes
  and platform listings show; the rest follow `sort_order`.
- **Everyone reads the pictures** through the product that carries them:
  `GET /products/{id}/attachments/{attachment_id}/content` (the same shape
  every document uses for its evidence); product reads carry
  `primary_image_id` so a list shows thumbnails without a query per row.
- **Removing a picture removes the link, not the bytes** — a blob two
  products share is one blob. A folder of images imports as one upload
  and one link per file, the first (or the one named "main") as
  primary — confirm which before writing.

## Materials And Bills Of Materials

There is no materials table. A raw material is a product with
`product_type: raw_material` — one catalog, because everything that HAPPENS
to a material (stock ledger, supplier links, purchase lines, receipts,
picks, categories) already keys on the product. The closed roles:
`finished_good` (default), `semi_finished` (a sub-assembly you make and
use), `raw_material`, `service`. Classification (materials / auxiliaries /
packaging) is the category tree, not the role. Bought-or-made is derived:
supplier links say bought, an active recipe says made — never a flag.

A bill of materials (`/bills-of-materials`) says what a finished or
semi-finished good is made of: a header with a `version`, an
`output_quantity` (components are PER that many units — per 1 or per 100,
however the factory writes it) and lines of component + quantity +
`scrap_rate` (percent lost making it).

- **One active recipe per product.** Activating a new version archives
  the old in the same write. An active recipe's lines are frozen — the
  floor builds to it — so a change is a NEW version (draft, edit,
  activate), never an edit.
- **Made of goods, never of itself.** A service line, the parent as its
  own component, or a component that is made (at any depth) from the
  parent — all refused, with the path.
- **A materials sheet imports like every sheet** — but ask which rows are
  materials, which are sub-assemblies, and map the column to
  `product_type` before the import; a BOM sheet is then one recipe per
  parent, created draft, read back line by line, activated on agreement.
- **Requirements are a READ, never a plan.**
  `GET /bills-of-materials/{id}/explode?quantity=&with_stock=true` walks
  every sub-assembly's active recipe, folds in output ratios and scrap,
  and hands back the leaf requirements with ATP and the shortage. What to
  buy is the person's decision — say the gap, then hand off to
  $oryh-purchase-submit; oryh stores no plan.

## Stores And Facilities: Where You Sell, Where You Ship From

`/stores` are selling fronts (`channel`: offline door or online storefront)
and `/facilities` are physical places (shop/warehouse/office — the tenant's
`facility_type` vocabulary, extensible like every family). Both are this
desk's to curate.

- **The facility NAME is a join key.** The stock ledger and freight legs
  carry facility as free text — register the facility FIRST and use its
  exact name there, which is why two live facilities cannot share one.
- **An online store's `source` is the channel key** external orders arrive
  under (tmall/jd/…, lowercased) — the same key the external product map
  uses, so "which store did this order belong to" is answerable.
- **Fulfilment is a standing answer, not a router.** `/store-facilities`
  rows say which facilities MAY ship for a store (priority ranks them, one
  row per pair, archived pairs revive); which facility a given order
  actually ships from stays the warehouse's call on the shipment.

## The Rolodex: People At A Customer

A B2B customer is several PEOPLE — procurement, the equipment engineer, the
finance desk — and `/customer-contacts` is where they live: name, title,
phone, wechat, email, one row each, under the customer. The parent row's
single `contact` column stays as the printed-document default; the rolodex
answers "who receives the invoice" and "who signs the acceptance".

- **One primary per customer**, and setting a new one demotes the old in
  the same write — never do the two-step yourself.
- **Same phone twice under one customer is a duplicate person** (409);
  archive the stale row to free the number. The same person at TWO
  customers is two rows — that is normal.
- A contact sheet from the person imports as a loop of creates today; map
  columns conversationally like every sheet (job title→title, mobile→phone), and
  never invent a person a row does not name.
- Documents keep their free-text contact snapshots on purpose — this table
  is what agents CONSULT when writing them, not a FK they must resolve.

## Customer Price Agreements

`/customer-products` is the sell-side mirror of `/supplier-products`: one
customer's standing terms for one product — THEIR item code and name for it
(their purchase order says "item no. KH-3301", and this table is what makes
that resolvable), the agreed price, minimum quantity, pack multiple. One
row per (product, customer).

- **The agreed price is the exception; the price book is the rule.** A
  quote or order for a customer with an agreement uses `agreed_price`,
  everyone else gets the price book — that is the whole reason this table
  is separate from `/product-prices`.
- **A lapsed agreement REVIVES, never forks.** POST on an existing pair —
  active or archived — is a 409 pointing at the row: PATCH it. Price
  changes update `agreed_price` in place; the paper trail is the
  quotations and orders that carried each price, not this row.
- A price agreement sheet imports like every sheet: map columns
  conversationally (customer item no.→customer_product_code, agreed price→agreed_price),
  and each row needs a customer and a product that already exist.

## The External Product Map

**Most platform exports carry titles, not listing ids.** A Tmall order
download names each line by title + spec, and the merchant may never see
a listing id. So a map row may be keyed by its TITLE: omit
`external_product_id` and give `external_name` (the platform's exact
title) with the spec text in `external_sku_id` when the platform splits
it. Matching forgives fullwidth spacing, case and doubled spaces
(`external_name_norm` is the matching form), so copy the title as the
export prints it and never "tidy" it. A renamed listing is a SWAP exactly
like a swapped id: close the old row's window and add a row for the new
title — the title cannot be edited on a title-keyed row. Bundles work the
same by title (several rows, one title). When an export DOES carry ids,
key by id and keep the title as the snapshot; both kinds answer the same
`external_name` lookup, so one table serves whichever export arrives.

Tenants selling through Tmall, JD, Amazon or a mini-program keep this
translation table: which platform listing means which catalog product,
with a quantity per row so a bundle listing is several rows ("two-cup set
with lid" = 2× cup + 1× lid). Curating it is catalog work — the same
authority as products themselves — with one shared act: Order desks may POST title-keyed map rows after a person confirms the candidate; id-keyed rows, edits, effective-date swaps and deletion stay with $oryh-master-data
— the order desk's row is exactly what a curator would write, and it keeps
the import a one-desk job. When a salesperson reports an unmapped listing,
this is the desk that fixes it: `POST /external-product-maps` with
`source`, the platform's ids or title, the catalog `product_id`, and the
multiplier. Never map by name similarity without the person confirming — a
wrong mapping ships the wrong goods silently.

**A listing's meaning changes over time, and the map records WHEN.**
Platforms rank the listing, not its contents, so a merchant who fought for a
good promotion slot keeps the same platform id and swaps the goods behind
it. When the person says a listing changed ("from Aug 15 this listing sells
the scarf instead"):

1. `PATCH` the current row with `effective_to: <the swap date>` — it stays
   `active`, because it is still the truth about its window, and orders
   synced late still translate against it. **Never archive it**: archived
   means withdrawn-as-a-mistake, and an archived row stops translating the
   old orders it correctly describes.
2. `POST` the new pairing with `effective_from: <the same date>`. The swap
   day belongs to the NEW meaning (`[from, to)`).

Swapping back later to a product the listing sold before is normal and
allowed — only two OPEN-ended rows for one (source, listing, product) are
refused. If the person cannot name the exact day, record their best date and
say out loud that orders ON the boundary day may need a hand check.

## What This Skill Never Does

- Invent, derive, or auto-number a missing code.
- Map an external listing to a product by name similarity alone — the person
  confirms every pairing; a wrong map row ships wrong goods with no error
  anywhere.
- Write anything before showing the column mapping AND a dry run.
- Guess which column is the price when more than one could be.
- Force a price column into a type that does not mean it. A missing type is
  something to propose (`POST /type-options`), never something to approximate.
  The same holds for customer categories and `customer_type`.
- Decide for the person whether a customer is an individual or an organisation.
  If the sheet does
  not say, leave `customer_kind` out and ask — an unstated kind is a gap, and
  a guessed one is a wrong fact that later reports will repeat.
- Silently drop a column, or silently normalise someone's product names.
- Delete master data. Obsolete entries are archived (`status: archived`),
  because quotations and requisitions already reference them by id.
- Touch employees, roles, or business documents. This is catalog data only.

## Reference

- [references/api.md](references/api.md): endpoints, row shapes per family,
  and the full response contract.
- [references/spreadsheets.md](references/spreadsheets.md): reading real
  files — header detection, merged cells, the Chinese column-name vocabulary
  real sheets use, number and price cleanup.
