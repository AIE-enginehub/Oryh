---
name: oryh-product-matching
description: Use when platform listings (天猫/京东/亚马逊 titles, SKU text, listing ids) must be resolved to oryh products — "这些商品对应我们哪个产品". Map first, candidates second, a person confirms, the map remembers. The workspace's own matching rules live in this skill's calibration.
required_capability: order.submit_own
---

# Oryh Product Matching

A platform export names goods the way the storefront does — a title written
to sell, a spec string written to filter, sometimes a listing id — and the
catalog names them the way the warehouse does. Every channel order, every
return, every stock reconciliation against a platform report crosses that
gap, and this skill is the one crossing. It resolves a batch of platform
lines to `product_id × quantity`, and it is **generic**: the same procedure
serves every workspace, and what differs between workspaces is data, not
prose.

Three pieces of tenant data, three places:

| What | Where | Written by |
|---|---|---|
| Pairings already confirmed ("this title IS product X, ×2") | `/external-product-maps`, dated | this skill, after a person confirms |
| **This workspace's matching rules** — how its titles are built, which words mean nothing, what a bundle looks like, when to refuse | the **Workspace calibration** section rendered at the bottom of this file | whoever holds the `skills.calibrate` grant for this skill (the order desk, typically) or `skills.manage`: `PATCH /skills/{skill_ref}` with `calibration` — `skill_ref` is the skill's REGISTERED name, printed in the code block near the end of this file, not the name your bundle installs it under |
| The catalog itself | `/products` | $oryh-master-data |

The rules are the part this workspace's admin controls without touching the
skill: a calibration is rendered into every copy of this skill on the next
sync and never forks it, so corrections to the procedure keep arriving. If
the section below is missing, this workspace has not written its rules yet —
match by the general procedure, and tell the admin once how to write them
(the block near the end of this file is a starting point).

{{include:_common/answer-the-question.md}}

{{include:_common/confirm-before-you-write.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/fail-fast-on-master-data.md}}

## Trigger Examples

- "Match the products in this Tmall export to ours"
- "Which of our products is 'Insulated cup 500ml sakura pink, gift box'?"
- "The order import stopped on eleven unmapped listings — sort them out"
- "This listing sells the scarf from the 15th; the earlier orders were the hat" — that is a swap: confirm the pairing here, the dated window is $oryh-master-data's write
- "Our platform titles always start with the brand and put the spec in brackets, remember that" — a rule, for the admin to write into the calibration, not for you to memorise

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # order.submit_own writes title-keyed map rows; master_data.manage writes any
  employee_id: "{{EMPLOYEE_ID}}"  # who is confirming
```

The lines to match come from the conversation or from the calling skill
($oryh-order-submit hands over its unmapped lines; $oryh-inventory a platform
stock report). Each line is `source` (the channel's code, lowercase), the
title **verbatim as the export prints it**, the spec text if the platform
splits it out, the listing id if the export carries one, and the date the
document it belongs to was placed.

## The Procedure

Reads first, the person in the middle, writes last — for the **whole batch**
at once, never one line at a time.

1. **The map answers first, as of the document's date.** For every line, in
   one wave: `GET /external-product-maps?source={source}&external_name={title verbatim}&at={document date}`
   (`&external_sku_id={spec as printed}` when the platform splits the spec
   out — the server folds case, width and spacing on both sides, so
   `size:11X14` finds `size:11x14`, but it does not strip the platform's
   label: write the spec the way the export prints it and look it up the
   same way). When the export carries a listing id, pass **both**
   `external_product_id={id}` and the title: the server answers with the
   id-keyed rows and with the title-keyed rows a desk wrote before anyone
   recorded the id. A hit is a decision a person already made: use it, do
   not ask again. The date matters: listings swap goods while keeping
   their title or id, and an order placed Tuesday must translate against
   what the listing meant on Tuesday.

   **Reading several rows for one title.** Rows that differ in
   `external_sku_id` are spec variants — the lookup WITH the spec returns
   one of them; a title-only lookup that returns three sizes has not
   answered, it has listed the sizes. Rows with the same title and spec
   and different products are a bundle only when they were written
   together on one confirmation (same day, complementary goods, quantities
   that make a set); a lone extra row pointing at an unrelated product is
   a conflict, not a component — do not translate, show the person both
   rows, and withdraw the wrong one (`DELETE`; your grant archives an
   undated row). A bundle row contributes `quantity × line qty` of its
   product, and that IS the translation.
2. **Only the lines the map did not answer go further.** For each of those,
   in the same wave: `GET /product-matches?title={title}&limit=5` — active
   products ranked by the phrases they share with the title, each phrase
   weighed by how rare it is in this catalog: a marketing compound every
   printer carries counts for little, the one word only the ribbon carries
   counts for much. `matched_terms` says which phrases scored, rarest
   first — read it before trusting a number. `sku_candidates` names the
   product's variants whose own code or attributes the title also matches
   (a `14x17` in the title points at the 14x17 SKU); `has_skus` tells you a
   product without such a hit still needs a spec chosen (`GET
   /product-skus?product_id=`). It is a shortlist, not a decision. When
   the calibration names a keyword form for this workspace's titles (a
   model code, a bracketed spec), add `GET /products?keyword={that form}`
   to the same wave; a code match outranks a vocabulary score — but a
   model code in a PART's title names the machine the part fits, and the
   calibration is where that rule lives.
3. **Apply the workspace's rules to the shortlist.** This is where the
   calibration does its work: strip the words it says mean nothing, read
   the spec the way it says the platform writes it, decompose a title it
   calls a bundle into components, prefer the catalog field it says is
   authoritative. The rules **rank and explain**; they never turn a
   shortlist into a silent choice. A line whose best candidate is still
   ambiguous under the rules is simply an unmapped line with a good first
   guess.
4. **Ask the person once, for the whole batch.** One message, every
   unmapped title with its top candidates — code, name, spec, `match_score` — and
   your reading of why: "Insulated cup 500ml sakura pink, gift box → CUP-500 Insulated cup 500ml (0.83)
   ×1 + BOX-01 gift box ×1, because the calibration says gift-box edition adds the gift box?
   or CUP-350?". Never pick a look-alike yourself, and treat "none of these"
   as an answer: that listing waits for the catalog desk, and the line may
   meanwhile be recorded in words (`description`, no `product_id`) if the
   caller prefers that to waiting.
5. **Record what the person confirmed** so the next import skips steps 2–4:
   `POST /external-product-maps` per pairing — `source`, `external_name` as
   printed (never tidied), `external_sku_id` as printed or `""`,
   `external_product_id` when the export carries a listing id (the
   sturdier key: a title gets re-worded, an id does not), `product_id`,
   `sku_id` when the pairing is a variant, `quantity`; a bundle is one row
   per component, all written now. Before writing, look at what the title
   already has (step 1): a row to a different product that is not part of
   this confirmation is the conflict described above. Undated rows are
   yours to write, correct and withdraw; **a dated window — `effective_from`
   / `effective_to`, the record of a listing swap — stays with the catalog
   desk**, $oryh-master-data (the server refuses it on your grant): say so
   and hand over when a person describes a swap rather than a new pairing.
6. **Return the translation** to the person or the calling skill, one row
   per input line:

```text
title (as printed) | spec | → product code · name × qty | decided by
Insulated cup 500ml sakura pink, gift box | — | CUP-500 · Insulated cup 500ml ×1; BOX-01 · gift box ×1 | map (2026-08-20)
Insulated cup 350ml mist blue   | — | CUP-350 · Insulated cup 350ml ×1 | confirmed just now, map written
Scarf, autumn/winter     | grey | UNMAPPED — none of 3 candidates, waiting for the catalog desk | —
```

`decided by` is not decoration: an order desk records a line differently
depending on whether it was the map, a fresh confirmation, or nothing.

## What A Calibration May Say

The section at the bottom of this file, when present, is this workspace's
rules. The kinds of sentence that belong there, so the admin knows what to
write and you know how to read it:

- **Title grammar**: "our Tmall titles are `brand + product name + spec in
  [] + marketing words`; the spec inside [] is the catalog `spec` field".
- **Noise**: "free shipping, official, new arrival, hot carry no meaning — strip them before
  scoring".
- **Codes**: "when a title contains a token like `TX-1234`, that is our
  `product_code`; look it up by keyword and do not score by words at all".
- **Bundles**: "gift-box edition means the product plus one `BOX-01`; two-piece set means ×2 of
  the same product".
- **Refusals**: "never map anything to a product whose code starts with
  `OLD-`; those are discontinued and stay unmapped until the catalog desk
  decides".
- **Reporting**: "when a candidate scores below 0.6, show it as a guess,
  not a recommendation".

A calibration refines HOW you match. It cannot make step 4 optional, let
you write a map row nobody confirmed, or move a swap or deletion off the
catalog desk — the boundary sentence rendered above the section says so,
and the skill wins where they disagree.

Whoever holds `skills.calibrate:oryh-product-matching` — the order desk
that just met an unmapped listing, not only the admin — writes it with one
call (`GET /skills/{skill_ref}` first, append to what is there, never
overwrite another desk's rules), and the next skill sync carries it to
every copy:

```text
PATCH /skills/{skill_ref}          # skill_ref: oryh-product-matching
{"calibration": "Tmall titles: brand + name + spec in [] + marketing words. Strip free-shipping / official / new-arrival. gift-box edition = product ×1 + BOX-01 ×1. Tokens like TX-1234 are product codes: look up by keyword. Never map to codes starting OLD-."}
```

## What This Skill Never Does

- Guess a product from a look-alike name, or let a calibration rule turn a shortlist into a silent choice.
- Write a map row without the person's confirmation, or date a swap (`effective_from` / `effective_to`) — the window is $oryh-master-data's.
- Create products. A listing that matches nothing is a catalog question, not a reason to invent a product.
- Create or change the order, the movement, or any document — the caller does that with the translation you return.
- Store the workspace's rules anywhere but the calibration: not in a map row's metadata, not in a custom object, not in your memory.

## Reference

- [references/api.md](references/api.md): request templates and the fields each lookup returns.
