# Reading The Person's Spreadsheet

Real files are not clean tables. This is the part of the job the API cannot
help with, and the part where a silent mistake is most expensive.

## Finding The Header

The header is often not row 1. Expect a title row ("2026 Product Price List"),
a blank spacer, an export banner, or a merged cell spanning the sheet.

Find the first row where most cells are short non-numeric labels and the rows
beneath it are consistently populated. If two candidate rows look plausible,
show the person both and ask. Do not silently pick one.

Also watch for:

- **Multiple sheets** — products, vendors and discontinued items in one
  workbook. Ask which sheet, and say what the others appear to hold. Never
  merge sheets on your own.
- **Merged cells** in the header, which read as a label plus blanks. The label
  belongs to all the columns it spanned.
- **Trailing junk rows** — totals, a "prepared by" line, remarks blocks under
  the data. A row whose code cell is empty but which has text elsewhere is
  usually one of these, not a product missing its code. Say so rather than
  reporting it as a missing-code error: "the last 3 rows look like a total and
  a prepared-by line; I skipped them — is that right?"
- **Frozen index columns** — a leading sequence column of 1,2,3… is a line
  number, NOT the product code. This one is worth being explicit about, because it looks
  exactly like a code and importing it would be a disaster to unwind.

## Column Name Vocabulary

Same field, many names. Recognise, then confirm — recognition is a hypothesis,
not a decision.

The right-hand column below is **data, not prose**: these are the literal
strings to match a sheet's header cells against, and most real files in this
market are written in Chinese. Translating them would leave the skill unable to
do its one job. Everything else on this page is English.

| Field | Commonly appears as |
|---|---|
| `product_code` | Product code, item code, material code, SKU |
| `name` | Product or customer/vendor name |
| `spec` | Specification, model |
| `unit` | Unit |
| `list_price` | List price, sales price |
| `vendor_code` | Supplier code |
| `supplier_product_code` | Supplier Product Code |
| `last_price` | Last Price |
| `lead_time_days` | Lead Time Days |
| `min_order_quantity` | Min Order Quantity |
| `customer_code` | Customer code |
| `customer_type` | Customer Type |
| `customer_kind` | Customer Kind |
| `quantity` | Quantity |
| `facility` | Facility |
| `lot_id` | Lot Id |
| `expire_date` | Expire Date |
| `tax_id` | Tax identifier, registration number |
| `contact` | Contact person, account representative |
| `phone` | Phone, mobile |
| `address` | Address, shipping address |

### Price columns deserve a question of their own

`list_price` is the **catalog reference price** — the number future quotes are
compared against to judge a discount. Several columns can look like it:

- Tax-inclusive versus tax-exclusive unit price — materially different
  numbers. Ask which one the catalog price should be; do not average, convert,
  or pick the larger. A price-book entry records the fact either way
  (`tax_in_price`, with the rate in `tax_percentage`) — never convert between
  them yourself.
- A purchase, buying-in or cost price — a cost, **not** a list price. Importing a cost as
  `list_price` makes every future discount calculation nonsense — but it now
  has a real home: when the sheet names the supplier, it is that supplier's
  `last_price` on the row's `suppliers` entry; with no supplier named, a
  `prices` entry with `price_type: "cost"`. Confirm which before writing.
- A last-transaction or historical unit price — a past transaction, not a
  catalog price.
- Multiple tiered prices (tier one, tier two, dealer) — ask which tier is the
  catalog price. Wholesale and dealer prices can land as
  `price_type: "wholesale"` book entries; anything the person cannot place goes
  to `metadata`, kept, not guessed.

Empty price → `null`. Never `0`: zero is a claim that the item is free.

## Cleaning Values

- **Whitespace** everywhere, including inside codes ("P-001 " from a merged
  cell). Trim. The server trims codes too, but trim before comparing rows
  yourself so in-file duplicates are found.
- **Numbers as text** — a currency symbol, a thousands separator, or a unit
  suffix attached to the figure. Strip all three.
- **Full-width characters** in codes — normalise to half-width, and mention
  that you did.
- **Excel date/number coercion** — a code like "0012" may arrive as `12`, and
  "2-1" may have become a date. If codes look mangled, say so and ask the
  person to re-export that column as text rather than reconstructing values.
- **Formula cells** — read the computed value, not the formula.
- **Duplicate rows** — genuinely identical rows can be collapsed (tell the
  person); rows sharing a code with DIFFERENT values cannot, and are an error
  for them to resolve.

## Presenting The Mapping

Short, complete, and explicit about what you are not importing:

```text
Read 62 rows; the header is on row 3. Field mapping:

  product_code ← "Material No."      name   ← "Product name"
  spec         ← "Specification"     unit   ← "Unit"
  list_price   ← "Tax-incl. price"   status ← (absent, defaulting to active)

  Ignoring: stock quantity, bin, remarks
  The last 2 rows look like a total and a prepared-by line; skipped

Is the tax-inclusive price the right catalog price? (There is also a
"purchase price" column I have not used.)
```

Then dry-run, and report the counts before writing anything for real.

For Chinese source columns, read the [localized header aliases](../locales/zh-CN/spreadsheet-headers.json)
before proposing a column map. These are recognition examples, not permission to guess missing fields.
