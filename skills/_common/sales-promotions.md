## Promotions: read the policy, record the result

This method applies to sales quotations and sales orders, not unrelated
approval documents. Promotions are natural-language `business_rules` of `kind=policy`. The agent
reads, judges eligibility and computes; oryh stores the published rule and the
resulting price, adjustment and gift facts. No promotion engine, new fields or
mandatory `rules_json` format is needed. This section defines the method, not
the workspace's discounts, thresholds, stacking order or approval authority.

**Read before pricing or reviewing a promotion.** Use the category or policy
codes the workspace's data rule names; `promotion` is the suggested category
when the workspace has adopted it:

```text
GET /business-rules?kind=policy&category=promotion&in_force_on=<business-date>
GET /business-rules?kind=policy&code=<promotion-code>&in_force_on=<business-date>
GET /business-rules/{rule_id}
```

Read all matching policies, paging to the end when using `page`/`size`; several
schemes may coexist. Read the full `body`, not just its title or summary.
Prose alone is complete. `rules_json` is optional; if present and inconsistent
with the body, ask the rule owner rather than choosing the convenient value.
An exact rule id in the document's basis identifies a version: fetch that row
and check its effective dates, rather than substituting today's version.

The policy's wording decides the qualifying event/date (quotation, order,
payment, etc.). Use `quote_date` or `order_date` when that is the event it
governs; today's date is only the default for a new transaction occurring
today, not for a delayed import or an old document reviewed today. If the
qualifying event or date is unclear and changes entitlement, ask before
granting the benefit. Record the chosen date and why. A future publication,
draft, or policy outside that period does not establish eligibility. No
applicable policy means no policy-backed promotion; agreed or explicitly
negotiated prices remain facts under the normal submission/approval rules.
If a claimed scheme cannot be read or found, say so and seek its published
basis, rather than asserting that it is authorised.

**Judge from facts and the actual clauses.** Match the customer, customer
type, products/SKUs, quantities, channel/store and currency as needed through
the existing read endpoints in this skill's API contract. Names alone do not
establish a named customer's eligibility when the match is ambiguous. Read
customer-product agreements when relevant; for an existing document, distinguish
its recorded agreement/eligibility facts from master data that changed later.
A current agreement is not proof of historical terms. Decide from the policy whether
the discount uses list price or agreed price, whether gifts count toward
thresholds, how tax/freight enter the base, whether tiers repeat or cap, and
whether schemes stack and in what order. Do not encode default commercial
answers in the skill. Missing or conflicting clauses that affect the result
need clarification from the owner; an exception follows the published approval
flow, not the agent's own permission to grant it.

Explain each benefit using its own clause: a customer eligibility condition, an amount threshold and a gift quantity threshold are distinct. Do not invent a quantity minimum for a discount merely because the gift has one. Clearly separate a policy quotation from your calculation or inference.

**Submitter: write the benefit once, through existing fields.**

- A unit-price discount can be reflected in `unit_price`, keeping the honest
  `list_price_snapshot`; explain the base price and calculation in item
  `notes`. Do not change the snapshot to disguise the discount.
- A monetary reduction not already reflected in line prices is a negative
  adjustment (`adjustment_type: promotion`), with its calculation and basis
  in `description`. Include `adjustments` alongside `items` in the existing
  quotation/order create request; use `item_index` only for a line-specific
  adjustment. For draft edits, read its detail and reconcile existing benefits rather than
  append duplicates. If using `/save`, follow its revision check and diff
  contract, preserving all unrelated items and adjustments.
- A giveaway is a separate item with `is_gift: true`, `unit_price: 0`, the
  actual gift product/SKU and quantity, and its basis in `notes`. Resolve the
  gift just as carefully as the purchased product. Do not count it as a 100%
  price discount.
- Keep the policy id, code, version, clause, qualifying date, eligibility
  facts, calculation base, order of benefits, rounding and resulting amount
  or gift quantity in existing `notes`, adjustment `description` and header
  `remarks`. Split the explanation within their documented length limits;
  existing `custom_fields`/adjustment `metadata` may hold additional evidence
  where supported, without requiring a new schema or overwriting other keys.
  Example basis: “PROMO-X v2 (rule id …), quote date …; customer … qualifies
  under clause 2; eligible amount after discount 2400; each full 1000 saves
  100, so adjustment -200.” The numbers are an example, never a default rule.
- Read back all prices, signed adjustments, gifts and the final payable
  amount with the basis before submission, under this skill's confirmation
  rules. `adjusted_total` and any declared `total_amount` must reconcile;
  changing the header total alone does not record a promotion.
- Copy opaque rule ids, codes and versions from the read response rather than
  retyping them into prose. On draft read-back, compare every stored rule id
  with the exact row read, including every UUID character; code/version alone
  must not conceal a mistyped id. Fetch a cited id if it has not been verified.
  A broken reference in your own draft is corrected from the known source
  row before submission, preserving prices and other facts. For a submitted
  document, report the discrepancy through review/rework instead of silently
  rewriting its basis.

**Carry a won quotation forward faithfully.** Read its full detail and copy
the agreed discounted prices, gifts, adjustments and basis when raising the
order; remap line-specific adjustments to the new items, never reuse quotation
item ids as order item ids. Do not apply its discount a second time or silently
replace the won terms with today's campaign. Whether an expired scheme still
honours a valid quote is the policy's sentence, not a skill default. Changed
quantities, goods or qualifying dates require a fresh eligibility check if
the terms call for one; name any resulting drift and obtain the required
authorisation. For channel orders, preserve the platform's recorded paid
prices, reductions and gifts; reconcile their basis without discounting the
already discounted import again. Returns use the original sale and the return
rules, not a new purchase promotion.

**Approver/flow agent: verify, do not reprice.** Read the cited exact policy
versions and the facts supporting eligibility; independently recalculate the
discount, threshold reduction and gift quantity, including interactions with
agreements and other benefits. Check for missing applicable benefits as well
as excess benefits, duplicate reductions, missing gifts, unsupported bases
and unexplained totals. For linked orders compare the quotation's full detail,
including adjustments, gifts and basis. Put the rules and the concrete checks
in the approval `comment` or routing todo `description`; distinguish policy
benefits from separately negotiated exceptions. Clear non-compliance or a
material unresolved basis is rework under the existing calibration/decision
procedure, with what needs clarification stated. Policy eligibility does not
waive an approval node unless the published approval flow says so. Never edit
the submitter's prices, adjustments or gifts while reviewing.
