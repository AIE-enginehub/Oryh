---
name: oryh-crm
description: Use when a salesperson's AI agent works that person's own sales pipeline in oryh — capturing leads ("展会上加了个微信,记一下"、"有人咨询报价"), advancing them (contacted/qualified/disqualified and revival), converting a qualified lead into a customer and an opportunity ("这家定了,建档开单"), and driving opportunities to won or lost ("这单赢了"、"预算砍了,丢了"). The pipeline has no approvals — your grant files AND advances your own records; quoting and ordering hand off to $oryh-quotation-submit and $oryh-order-submit. Requires crm.own.
required_capability: crm.own
---

# Oryh CRM

Work the principal's own sales pipeline: leads in, opportunities through,
deals won or lost. The credential is the identity — the server only accepts
writes for the employee linked to this key — and there is no approval half:
qualification is the principal's judgment and a deal is won by the
customer's signature, so YOU advance the states as the facts happen.

{{include:_common/answer-the-question.md}}

## Trigger Examples

- "Met someone at the fair, added them on WeChat — note it down"
- "Somebody asked for a quote — log the inquiry"
- "This one signed: open the customer and the deal"
- "We won this one" / "Budget was cut, we lost it"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  api_key: "{{ORYH_API_KEY}}"            # the salesperson's personal key
  employee_id: "{{EMPLOYEE_ID}}"         # whose pipeline this is
```

## The three rules

- **Capture fast, qualify slowly.** A lead needs only a company OR a person
  (server refuses a lead that names nobody) — record the scrap of contact
  the moment it exists, enrich later. Whether it is worth pursuing is
  judgment, not data entry: `qualified` is you saying so.
- **Convert through the bridge, never by hand.** `POST /leads/{id}/convert`
  is the ONE way a lead becomes a customer: it creates (or names) the
  Customer, carries the lead's person into the contact rolodex, optionally
  opens the Opportunity — one transaction, and the lead lands in
  `converted` holding `converted_customer_id`. A bare status write to
  `converted` is refused because it would lose WHICH customer. You do not
  need master-data authority for this; the bridge is the promotion.
- **Estimates are not money.** An opportunity's `expected_amount` is your
  guess for pipeline reading; real amounts live in the quotations and orders
  the deal produces. When the deal reaches quoting, hand off to
  $oryh-quotation-submit with the opportunity's customer — and record the
  outcome back here (`won`/`lost`), which stamps `closed_at`. A lost deal
  that comes back later is a NEW opportunity; a disqualified lead that
  comes back revives (`disqualified → contacted`).

## Working the pipeline

1. **Requirements**: `GET /workflow-definitions?entity_kind=builtin&object_type=lead`
   (and `=opportunity`) — the machine is the tenant's vocabulary; read it
   before assuming state names. Default lead life:
   `new → contacted → qualified → converted / disqualified`; default
   opportunity life: `open → quoting → negotiating → won / lost`. `won`
   and `lost` are literal — `closed_at` stamps on those two names whatever
   else the tenant renames.
2. **Dedup before create**: `GET /leads?keyword={phone or company}` — the
   same inquiry arriving twice is one lead worked twice, not two. Also
   check `GET /customers?keyword=` — somebody already in master data is
   not a lead; open an opportunity for them directly.
3. **Capture**: `POST /leads {"employee_id": "{{EMPLOYEE_ID}}", "company_name"/"contact_name", "phone", "source": "trade-fair"}`.
   Keep `source` values consistent within the workspace — the vocabulary
   is habit, not a table, and "fair"/"trade fair"/"trade-show" splitting
   one channel three ways ruins the question "where do our leads come
   from".
4. **Advance**: `PATCH /leads/{id} {"status": ...}` as facts happen. Field
   edits obey the machine's editable states; terminal states freeze the
   record (a revival is a status move, not an edit).
5. **Convert** (from `qualified`): `POST /leads/{id}/convert` with either
   `customer_id` (they were in master data all along) or nothing/`customer_name`
   (create). Add `opportunity_title` (+`expected_amount`,
   `expected_close_date`) to open the deal in the same call.
6. **Drive the deal**: `PATCH /opportunities/{id}` — stage moves, estimate
   updates, `remarks` for why. On `won`/`lost`, say the why in `remarks`
   out loud before writing it; `closed_at` stamps itself.

## What This Skill Never Does

- Write `converted` by hand, or create the customer through master data —
  the bridge is the promotion.
- Work anyone else's pipeline, or quote and order from here — those are
  $oryh-quotation-submit and $oryh-order-submit.
- Treat `expected_amount` as money owed or earned.

## Reference

- [references/api.md](references/api.md): request templates.
