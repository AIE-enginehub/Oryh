---
name: oryh-purchase-submit
description: Use when a person's AI agent needs to file, update, query, or submit that person's own purchase request in oryh. Covers natural-language requisition capture, matching products and the target vendor against master data (both optional), handling known and unknown prices, quote attachments, submission, and fixing a returned request. It records the requester's facts only — routing, sourcing, and approval belong to other roles.
required_capability: purchase.submit_own
---

# Oryh Purchase Submit

Record and submit the principal's own purchase request. The credential is the identity: the server only accepts writes for the employee linked to this key, so never ask "for whom" — it is always the principal.

Three things about a requisition are legitimately uncertain, and the record is honest about all of them:

- **Vendor**: the principal may name a target supplier, or not. Match against master data; no match is fine — `vendor_id` stays null and the free-text hint stands.
- **Product**: the item may be in the tenant's catalog, or free text only. Never invent catalog entries.
- **SKU**: tenants define "product" at their own granularity. Some catalogs are flat (product IS the sku — `has_skus: false`, done). Others split product and transaction granularity (服装的款色 → 尺码): when the matched product has SKUs, purchasing wants the SKU — ask for the variant — but "尺码待定，配比后定" is itself a legal fact: file the line at product level with `sku_id` null and say so.
- **Price**: the principal may know it, or not. An unpriced line is a normal fact — sourcing (询价) happens later in the flow, and you must say so at read-back rather than guessing a number.

## Trigger Examples

- "申请采购" / "帮我提个采购申请"
- "要买3台显示器，找戴尔，大概3000一台"
- "申请买一批线材，还不知道多少钱"
- "采购申请被退回了，补了报价重新交"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # the principal's user-bound key
```

Everything else comes from conversation: what to buy, how many, for when, from whom (maybe), at what price (maybe).

## Steps

{{include:_common/fewer-round-trips.md}}

{{include:_common/read-before-you-decide.md}}

1. **Identity**: your employee id is already in this file — `{{EMPLOYEE_ID}}`. No call needed. Do not create employees; that is an HR/admin capability. Blank means no employee record is linked to this principal: say so, do not work around it.
2. **Tenant requirements**: `GET /workflow-definitions?entity_kind=builtin&object_type=purchase_request` — the tenant's natural-language rules for this object, current as of this moment. Read what it requires of a submission (报价单要求、用途说明、needed_by and the like) and let it shape the conversation from the first question — see the "Tenant requirements" layer below. No definition, or nothing in it about filing a request → only the universal checks apply; never invent requirements. Routing rules in the same document belong to other roles — ignore them.
3. **Reuse before create**: `GET /purchase-requests?employee_id={me}&status=draft` — reuse an open draft for the same purpose; retries must not duplicate. A `returned` request is also reused: fix it (typically add prices or quotes), don't recreate — and read why it came back first: the rework todo's `description` and the latest `returned` approval record's `comment` list exactly what to fix, usually citing the step-2 requirements. After a successful resubmit, complete that rework todo (`PATCH /todos/{todo_id}` `{"status": "completed"}`; needs `todos.complete_own`, in the default member role) — while it stays open, the request is invisible to the flow admin's work queue.

   **Steps 2 and 3 do not feed each other — send them as one batch.** The tenant's rules and your own open documents are independent lookups; waiting for the first before asking the second doubles the wait for no reason.

4. **In-flight duplicate check**: `GET /purchase-requests?employee_id={me}&status=submitted` — if an open request already covers the same items, tell the principal instead of filing twice. This is a conversation, not a hard stop.
5. **Match master data** (read-only, both optional):
   - Vendor: `GET /vendors?keyword={名称}` or `?tax_id=` when the principal names a supplier. Confident match → header `vendor_id`; otherwise put their words in `vendor_name_snapshot`.
   - Product per line: `GET /products?keyword=`. Confident match → `product_id` (name/unit backfill automatically, and `list_price` gives you the price-sanity reference); otherwise `product_name_snapshot` + `spec` free text.
   - SKU per line, when the matched product has `has_skus: true`: `GET /product-skus?product_id={id}&status=active` and locate the variant from the principal's words against `variant_attrs`（"藏青XL" → 尺码:XL）. Confident match → send `sku_id` (the product derives automatically; SKU-level `list_price` overrides the product's). Ambiguous → ask ONE question listing the variants. Principal says 待定 → `sku_id` null, and flag it at read-back.
   - Never create vendors, products, or SKUs; that is master-data management.
6. **Request**: `POST /purchase-requests` with `employee_id`, `title` (the purpose), `needed_by` if stated, the vendor fields from step 5, and the principal's original words in `source_report_text`.
7. **Items ride the create** — put the complete `items` array on step 6's `POST /purchase-requests`: one call, one transaction, a bad line rolls the whole request back, and the response echoes the lines (your read-back material). `POST /purchase-request-items` remains for adding to an existing draft (`quantity` required; `unit_price` or lump-sum `amount` only if actually known; quote file via `POST /attachments` → `attachment_id`, or the bundled `scripts/upload_attachment.py` (in this skill's directory — the path is relative to it, not to wherever you happen to be) which does the base64 and the 10 MB pre-check). `PATCH`/`DELETE` to correct. Items are editable only while the request is in the tenant's editable states (default `draft`/`returned`) — a 409 means the request has moved on.
   - **按单采购 (零库存)**: when this purchase exists to fulfil a confirmed sales order line, pin the line with `sales_order_item_id` — take the id from `GET /sales-orders/{order_id}/detail` (`items[].id`), never guess it (a wrong id is 404). Several purchase lines may pin to one order line (split vendors/deliveries). The link is what lets the fulfilment side see 采购到位没有 before shipping, and lets approvers review the purchase against the order it serves. Omit it for ordinary stock purchases; PATCH it to `null` to detach.
8. **Submit**: `POST /purchase-requests/{id}/submit` — only after the pre-submit read-back below got an explicit yes. Idempotent — resubmitting a submitted request is a no-op.
9. **The submitted approval fact is not yours to write.** `/submit` records it (`round_no` derived, `sequence_no=1`, `source=system`), so the trail opens with it whether or not this credential carries `approval.record`. Posting it anyway is harmless — the recorded fact comes back — but there is nothing to do here.
10. **Read back — no extra call**: the create response already echoed every line and the submit response carries the new status and `submitted_at`. Tell the principal it is submitted, with the estimated total and how many lines are unpriced, from what you already hold. `GET /purchase-requests/{id}/detail` is for LATER — checking the approval trail — not for confirming what you just wrote.

## Validate Before Writing

Three layers. Hard rules the server enforces — check them yourself first so the principal gets a question, not an error code. Tenant requirements the workflow admin calibrates against — the server records whatever is legal, but a request that ignores them comes straight back. Reasonableness checks are yours alone.

**Hard rules (the server rejects these; catch them in conversation first):**

- `quantity` per item: more than 0.
- Every item needs a `product_id` **or** a free-text `product_name_snapshot`.
- Items only while the request is `draft`/`returned`.
- `vendor_id` / `product_id` / `sku_id` / `attachment_id` must be real records in this tenant — free text goes in the snapshot fields, never a guessed id.
- `sku_id` must belong to the line's `product_id` (400 otherwise); sending `sku_id` alone is fine — the product derives from it.

**Tenant requirements (the workflow admin returns violations; catch them in conversation first):**

- Whatever the step-2 definition requires of a submission, applied line by line. Typical shapes: 超过一定金额必须附报价单；必须写明用途和期望到货时间；指定品类只能从合格供应商采购. The definition's own wording always wins over these examples.
- These are the exact requirements the workflow admin's agent checks before assigning any approver, and its return note cites the ones violated — so a requirement skipped here is a guaranteed rework round. Ask for the missing quote or 用途 while the principal is still talking, not after the return.
- Fixing a returned request? Re-run step 2 first — the requirements may have changed since the original submission, and the current version is what the next calibration uses.

**Reasonableness (pause and ask before writing):**

- A quantity that smells like a mishearing ("300台显示器" — 是不是3台？) → confirm before writing.
- Stated price deviating more than ~20% from the catalog `list_price` → show both, ask which is right. The principal may know about a discount; record what they confirm.
- `needed_by` in the past, or unrealistically soon for the item → typo or genuine urgency? Ask.
- No price at all → fine, but say it out loud: "线材这行没有报价，我按无报价提交，流程可能会先安排询价。"
- A near-identical line already on the request, or an in-flight request covering the same purchase → add, replace, or stop?
- Vague content ("买点东西") → ask what, how many, for what; approvers return vague requests, one question now saves a rework round.

**How to have the conversation:**

- Quote the principal's own words, state what looks off, propose your reading, ask ONE clear question. Don't stack five doubts into one message.
- Never silently "fix" a quantity, price, or spec — a correction the principal didn't see is worse than the error.
- If the principal confirms an unusual fact (the 300 chairs are real — it's a new office), record it exactly as stated and put the clarification in `notes`. Judging necessity is the approver's job; yours is faithful capture plus honest flagging.

**Pre-submit read-back:** before step 8, echo the complete request — each line with quantity/price (or "未报价"), the variant (or "SKU 待定" when the product has variants and none was picked), the target vendor (or "未指定"), the estimated total, and how many lines carry no price — and get an explicit confirmation.

## What Happens Next (so you can answer the principal)

The request now sits in the workflow admin's queue. It is first calibrated against the same submission requirements you applied in step 2 — a non-compliant request comes back as a rework todo without reaching any approver — then approvers are assigned per the tenant's workflow definition: amount tiers key on the estimated total, and definitions commonly send unpriced requests for sourcing first (a `returned` + rework round to fill in prices). Progress is visible any time via `GET /approval-records?entity_type=purchase_request&entity_id={id}` — the status stays `submitted` until the flow finishes, then `approved` and, once procurement places the order, `ordered` (tenant machines may differ). If it is returned, a rework todo appears in the principal's inbox (see `$oryh-my-work`).

## What This Skill Never Does

- Approve, decide routing, pick the winning vendor, or touch the request status (`/submit` is the only transition it makes).
- Create employees, vendors, or products as a side effect.
- File for anyone other than the credential's own employee.
- Invent a price, quantity, or vendor the principal didn't state.
- Submit without the pre-submit read-back.

## Reference

- [references/api.md](references/api.md): request templates.
