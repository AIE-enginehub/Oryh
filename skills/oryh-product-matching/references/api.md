# Product Matching API

Every path hangs off `api_base_url` exactly as given — no version prefix to add.

{{include:_common/api-conventions.md}}

## The map: pairings a person already confirmed

```text
GET /external-product-maps?source=tmall&external_name={title verbatim}&at={document date}
GET /external-product-maps?source=tmall&external_name={title verbatim}&external_sku_id={spec as printed}&at={document date}
GET /external-product-maps?source=tmall&external_product_id={listing id}&external_name={title verbatim}&at={document date}
```

- `external_name` and `external_sku_id` match their normalised form (NFKC,
  case-folded, spacing forgiven) — pass them as printed and let the server
  normalise. The platform's label inside the spec (`size:`) is kept: write
  and look up the same string.
- id and title together: the answer is the id-keyed rows plus the
  title-keyed rows written before the id was recorded — one listing, both
  keys.
- `at` resolves the map **as of that date**: rows whose
  `[effective_from, effective_to)` window covers it, null bounds open. A
  swap boundary belongs to the newer meaning.
- Several rows for one title are a bundle. Each row's `quantity` is the
  multiplier for its `product_id`.

Each row: `id`, `source`, `external_product_id`, `external_sku_id`,
`external_name`, `product_id`, `sku_id`, `quantity`, `effective_from`,
`effective_to`, `status`.

## Candidates: when the map is silent

```text
GET /product-matches?title={title as printed}&limit=5
```

Active products ranked by the phrases their name, code, spec and SKU
codes/attributes share with the title, each phrase weighed by its rarity
in this catalog. Each candidate is the product row (`id`, `product_code`,
`name`, `spec`, `has_skus`, `sku_count`, …) plus `match_score` in `[0, 1]`
(the share of the title's catalog-known weight this product covers),
`matched_terms` (the phrases, rarest first) and `sku_candidates` — `[{id,
sku_code, variant_attrs, matched_terms}]` for the variants the title's own
tokens name. `limit` is at most 20. A shortlist, never a decision.

```text
GET /products?keyword={code or phrase}&status=active
```

Every word of `keyword` must appear (in code, name or spec). Use it when the
calibration says a token in the title is this workspace's product code.

## Remembering a confirmation

```text
POST /external-product-maps
{
  "source": "tmall",
  "external_name": "Insulated cup 500ml sakura pink, gift box",
  "external_sku_id": "",
  "product_id": "{catalog product id}",
  "quantity": 1
}
```

One row per component of a bundle, same `external_name`, each with its own
`product_id` and `quantity`; add `external_product_id` when the export
carries a listing id and `sku_id` when the pairing is a variant. `source`
must name a registered sales channel (`GET /sales-channels`).
`order.submit_own` writes, corrects (`PATCH`) and withdraws (`DELETE`,
an archive) undated rows; `effective_from` / `effective_to` — the dated
window of a listing swap — need `master_data.manage` ($oryh-master-data)
and so does any row that carries one. A second open row for the same
listing and product is a 409 naming the first: PATCH that one.

## The workspace's rules

```text
GET /skills/{skill_ref}             # skill_ref: oryh-product-matching — the registered name, whatever your bundle installed it as
PATCH /skills/{skill_ref}
{"calibration": "Tmall titles: brand + name + spec in [] + marketing words. Strip free-shipping / official / new-arrival. gift-box edition = product ×1 + BOX-01 ×1."}
```

`calibration` is rendered into this skill as its **Workspace calibration**
section on the next sync and does not fork the skill. `PATCH` with only
`calibration` in the body needs `skills.calibrate` (scopable:
`skills.calibrate:oryh-product-matching`) or `skills.manage`; `GET` needs
the same. Read first and append: the field holds every desk's rules.
