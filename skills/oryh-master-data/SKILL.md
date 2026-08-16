---
name: oryh-master-data
description: Use when a person's AI agent needs to load or maintain the company's master data in oryh — importing products, vendors, or customers from a spreadsheet ("import the products in this Excel file"), adding or correcting entries by hand, archiving obsolete ones, or auditing what the catalog already holds. Covers reading the file locally, working out which column means what and confirming it with the person, a dry-run preview before anything is written, upsert by the tenant's own code, and per-row reporting. Requires master-data management rights; ordinary submit/approve skills read this catalog but must never write it.
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
   - Stock-count sheets (quantity, facility, lot, expiry) go to
     `POST /inventory-items/bulk`. Inventory is a ledger: a quantity difference
     is posted as an `import_override` detail row naming both the system figure
     and the counted one, rather than overwriting the number — so read the
     large differences out before importing:
     "P-001 shows 120.5 in the system, you counted 97, a difference of 23.5.
     Post the counted figure?"
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

## What This Skill Never Does

- Invent, derive, or auto-number a missing code.
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
