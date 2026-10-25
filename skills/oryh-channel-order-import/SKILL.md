---
name: oryh-channel-order-import
description: Use when a seller's agent lands a file of e-commerce platform orders (Tmall/JD.com/Douyin/Amazon exports — "e-commerce order import", "import this batch of platform orders", "today's Tmall orders") in oryh as DRAFTS — dedup by the platform's number, translate every line through the product map, propose the likeliest catalog product for the rest, have the person confirm every proposal in one message, then create the drafts and link the numbers. Requires order.submit_own. Matching rules are oryh-product-matching's calibration; one listing to sort out by hand is oryh-product-matching; an order filed today in conversation, or submitting a draft, is oryh-order-submit.
required_capability: order.submit_own
---

# Oryh Channel Order Import

A platform export is a spreadsheet of platform order numbers and product
TITLES, and the company wants it in oryh as orders — today, all of it, not
after a conversation about every line. The desk skill ($oryh-order-submit)
puts the person in the middle of each unmapped line, which is right for one
order and wrong for three hundred. This skill lands the batch as **drafts**,
and does the person's reading for them in bulk: it proposes a catalog
product for every unmapped line, then puts all the proposals in front of
the person at once — one message, one answer — and only what they confirm
becomes a product on a line. A proposal nobody confirmed lands nowhere:
the line is recorded in words. Every line records how it was decided — by
the map, by a confirmation given today, or not at all — and the drafts
start no approval flow, reserve nothing and tell the warehouse nothing
until a person submits them.

{{include:_common/answer-the-question.md}}

{{include:_common/confirm-before-you-write.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/stay-current.md}}

{{include:_common/fewer-round-trips.md}}

{{include:_common/read-before-you-decide.md}}

{{include:_common/fail-fast-on-master-data.md}}

## Trigger Examples

- "Import today's Tmall orders"
- "Here is the JD export for last week, three hundred orders"
- "Land these Douyin orders as drafts; we will check the products afterwards"
- "The Amazon file again — some of these we already imported" (dedup is the first step)
- "Which of the imported lines are still in words, with no product?"

## Required Inputs

```yaml
oryh:
<!-- only: bundle -->
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
<!-- /only -->
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
<!-- only: bundle -->
  api_key: "{{ORYH_API_KEY}}"     # order.submit_own — creates the seller's own orders and writes undated map rows
<!-- /only -->
  employee_id: "{{EMPLOYEE_ID}}"  # the salesperson the drafts belong to
```

Plus the export file(s), on the person's machine — read them where they are —
and the channel they came from (`source`: the channel's registered code,
lowercase — `tmall`, `jd`, `douyin`, `amazon`; `GET /sales-channels` lists
them). The file's own columns are the facts: platform order number, order
time with its time zone, buyer, listing title as printed, spec text, listing
id when the platform exports one, quantity, unit price, currency, platform
status. Keep them as printed; never tidy a title.

## The Loop

Reads first — all of them, together — one confirmation for the batch,
writes last. For a file of N orders this is a handful of calls, not N
conversations.

1. **Open with one wave of reads.** The channel's stores
   (`GET /stores?source={source}` — several stores under one channel is
   normal; the export says which, or the person does; each store row lists
   its `fulfilment_facilities`, not yours to override), the manifest
   check above, and the **Workspace calibration** section at the bottom of
   your copy of $oryh-product-matching — the workspace's own matching
   rules (title grammar, noise words, bundle forms, refusals, a score
   below which a candidate is not worth proposing). No calibration means the general
   procedure applies and the default bar below.
2. **Dedup by the platform number FIRST.** For a few orders,
   `GET /external-document-links?source={source}&external_kind=order&external_no={theirs}`
   per number; for a file, page
   `GET /external-document-links?source={source}&external_kind=order` to
   the end once and diff the numbers locally. A hit is an order already
   ours — report it under "already imported" and skip it; the export came
   twice, the order must not. (The server also refuses to link a number
   already on another order, 409 naming it — but by then a duplicate draft
   exists, so this read comes first.)
3. **Translate every line through the map, as of each order's date.**
   Collect the distinct listings of the whole file and send them in one
   call: `POST /external-product-maps/resolve`
   `{"source", "with_candidates": true, "listings": [{"external_product_id"?, "external_name"? (title verbatim), "external_sku_id"? (spec as printed), "at": {that order's date}}, …]}`
   (up to 500 per call; a file of 300 lines usually names 40 listings).
   `data[i]` answers `listings[i]`: `status: mapped` with the `maps` rows —
   a decision a person already made, use it without asking; several rows
   are a bundle, each contributing `quantity × line qty` of its product —
   or `unmapped` with the shortlist in `candidates`. The order's date,
   not today's: listings swap goods while keeping their title.
4. **For the unmapped lines, propose the likeliest product.** This is
   where this skill differs from the desk: it does the sorting for the
   whole batch before asking, so the person answers once. Apply the calibration to the
   `candidates` (strip the words it calls noise, read the spec the way it
   says the platform writes it, decompose what it calls a bundle, honour
   its refusals — a listing it says never to map stays unmatched), then:
   - the best candidate's `match_score` clears the bar — the calibration's
     figure, else **0.6** — and leads the runner-up clearly: propose it.
     Read `matched_terms` before trusting the number: a score made of
     words every product in the catalog carries is not a match. When the
     calibration names a code form (a token like `TX-1234`), a code hit from
     `GET /products?keyword=` outranks any score.
   - the product `has_skus`: exactly one `sku_candidates` entry → propose
     that `sku_id`; none or several → propose the product and say the spec
     is still open.
   - nothing clears the bar, or the calibration refuses: no proposal — the
     line will be recorded in words (`product_name_snapshot` as printed,
     no `product_id`) so the draft still carries the order whole.
   A proposal is a question for the person, not a decision: it is never
   written to the map, never put on a line, never submitted, never reserved
   against stock until they confirm it.
5. **The person confirms every proposal — one message, one answer.** List
   the orders to create (count, store, currency, date range), the orders
   skipped as already imported, and **every proposed pairing** — title as
   printed → candidate code · name · spec, score, the matched terms, and the
   runner-up — and every title with no proposal. Wait for an explicit yes;
   "all of them" is a yes to each, a corrected line is a yes to the
   correction, and a pairing the person does not confirm is not a pairing:
   that line is recorded in words. No draft is created before this answer,
   and no proposal lands on a line without it.
6. **Create the drafts.** One `POST /sales-orders` per order — no `status`,
   no `/submit`: `employee_id` yours, `store_id` from step 1, the buyer in
   `customer_name_snapshot` (a buyer who is a known account —
   `GET /customers?keyword=` — gets `customer_id` too), the platform's
   `currency` with unit prices in it, `order_date` the platform's, the
   platform's own facts (buyer nickname, platform status, platform line ids,
   the timestamp with its time zone) in `custom_fields`, and the lines
   translated — each line's `custom_fields.channel_import` recording
   `decided_by` (`map` / `confirmed` / `none`), the title and spec as printed,
   and for a confirmed pairing its `match_score` and the runner-up by code. Send
   `Idempotency-Key: {source}:{platform number}` so a retry after a timeout
   returns the same draft instead of a second one. Then **link the number**:
   `POST /external-document-links` `{source, external_kind: "order",
   external_no, entity_type: "sales_order", entity_id}` — one platform order
   split across two drafts is two links, the second with `split: true`.
7. **Remember what the person confirmed** so the next import skips step 4
   for those listings: for each confirmed pairing, `POST /external-product-maps`
   `{source, external_name as printed, external_sku_id as printed or "",
   external_product_id when the export carried one, product_id, sku_id when
   a variant, quantity}` — a bundle is one row per component, written
   together. Same wave as the drafts; the confirmation in step 5 covered
   both writes. A line the person fills in later on the draft
   (`PATCH /sales-order-items/{id}` with `product_id`, `sku_id`) is a
   confirmation too: write its map row then.
8. **Read back what the server holds**, not what you sent: draft number
   and id per platform number, then lines by how they were decided — from
   the map, confirmed today, unmatched (these wait for the catalog desk,
   $oryh-master-data, who can create the product or write the dated
   pairing; your grant cannot hand them a todo, so name the listings
   plainly). The draft is open in the console at
   `{base_url}/sales-orders/{id}`. Submitting the drafts is
   $oryh-order-submit's `POST /sales-orders/{id}/submit`, when the person
   asks: never an order with a line that has no `product_id`.

## Iron Rules

- **Every matched product is confirmed by the person before it lands.**
  The map's hits were confirmed once before; everything else this skill
  proposes is confirmed now, in the batch message, or it does not become a
  product on a line. A proposal never reaches a line, the map, a
  submission, a stock hold or a shipment on a score alone.
- **Dedup before you create.** The platform number is the identity; the
  file arriving twice is normal, the order existing twice is not.
- **Translate as of the order's date,** with the title verbatim. A tidied
  title finds nothing and a wrong date finds the wrong goods.
- **The map is written only from a confirmation** — a person's yes on a
  specific pairing — never from a score, however high.
- **Label every line.** `decided_by` is what lets the person see which
  lines were decided today and which the map decided long ago.

## What This Skill Never Does

- Submit, reserve or ship anything — the drafts are left for a person; submission is $oryh-order-submit's.
- Put a proposed product on a line, or write it to the map, before the person confirmed it; date a listing swap or withdraw another desk's row — windows are $oryh-master-data's.
- Create a product, a store or a channel — an unmatched listing is a catalog question, a missing store is a setup question.
- Record a return or a historical migration — returns are $oryh-order-submit's own rows, a retired system's history is $oryh-data-migration's.
- Store matching rules anywhere but $oryh-product-matching's calibration.

## Reference

- [references/api.md](references/api.md): the calls, the line's `custom_fields` shape, and the read-back table.

Chinese request aliases and original example wording are available in
[locale examples](locales/zh-CN/examples.json); preserve user-provided names and text.
