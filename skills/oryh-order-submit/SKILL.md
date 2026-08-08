---
name: oryh-order-submit
description: Use when a salesperson's AI agent needs to record, update, query, or submit that person's own sales order in oryh — typically right after a quotation was accepted ("客户签了，下单吧"), and afterwards to keep fulfilment facts current ("发货了，单号SF…"、"客户签收了"). Records the order (usually from the won quotation's lines), submits it for confirmation, and maintains logistics/delivery FACTS as fields; status transitions belong to the flow admin. Requires order.submit_own.
required_capability: order.submit_own
---

# Oryh Order Submit

Record and maintain the principal's own sales orders. The credential is the identity: the server only accepts writes for the employee linked to this key. An order is the fulfilment side of a won quotation — **you write facts (lines, tracking numbers, dates); the flow agent moves the status** (`confirmed → shipped → signed` by default; service tenants rename the back half).

**Not for historical migration.** A workbook of past orders belongs to
$oryh-data-migration. This skill records ONE order the principal is placing
now.

## Trigger Examples

- "市一那单签了，按报价下单"
- "订单发货了，顺丰 SF3021…"
- "客户签收了" / "货什么时候能到？"

## Required Inputs

```yaml
oryh:
  base_url: "{{ORYH_BASE_URL}}"
  api_key: "{{ORYH_API_KEY}}"     # the principal's user-bound key
```

## Steps

{{include:_common/fewer-round-trips.md}}

1. **Identity**: your employee id is already in this file — `{{EMPLOYEE_ID}}`. No call needed. Blank means no employee record is linked to this principal: say so, do not work around it.
2. **Tenant requirements**: `GET /workflow-definitions?entity_kind=builtin&object_type=sales_order` — what a valid order must carry (合同号、收货地址、发货前审批 and the like), current as of this moment. Never invent requirements.
3. **From the won quotation** (the normal path): `GET /sales-quotations/{id}/detail` of the accepted quotation → `POST /sales-orders` with `quotation_id` (the quote number snapshot backfills automatically), the customer fields, `ship_to_address`, `contract_no`, and `title`. Omit `order_no` for the server's `SO-NNNNNN`, or pass the tenant's own convention. Mirror the quotation's lines **in the same create** — the `items` array rides `POST /sales-orders`, one call and one transaction (prices carry over; `promised_date` per line when承诺了交期). `POST /sales-order-items` remains for adding a line to an existing draft. A quote-less order (直接下单) is also legal — snapshots stand alone.
4. **Reuse before create**: `GET /sales-orders?quotation_id={id}` and `?employee_id={me}&status=draft` — one won quote, one order; retries must not duplicate. A `returned` order is also reused: fix what the rework todo's `description` and the latest `returned` record's `comment` name, resubmit, then complete that rework todo (`PATCH /todos/{todo_id}` `{"status": "completed"}`) — while it stays open, the order is invisible to the flow admin's work queue.
5. **Submit**: `POST /sales-orders/{id}/submit` after an explicit read-back (lines, total vs quotation, ship-to, promised dates). The flow agent calibrates and confirms — tenants without order ceremony get `confirmed` immediately per their definition.
6. **Fulfilment facts, as they happen** (PATCH fields on your own order — never `status`):
   - 发货：`logistics_company` + `logistics_tracking_no`
   - 签收/交付：the flow agent stamps the transition; you report the fact in conversation and keep `remarks` honest
   - 交期变化：`promised_date`（整单）或行上的 `promised_date`
7. **Read back**: `GET /sales-orders/{id}/detail` — items, adjustments, `adjusted_total` vs declared `total_amount`, the linked quotation, approval trail. 税/运费/整单折扣/抹零 record as adjustments (`POST /sales-order-adjustments`, same contract as the quotation side: signed amount, typed, optional `order_item_id`, editable only while the order is) — so the declared total is explained, not asserted.

## What This Skill Never Does

- PATCH `status` (flow admin's write — no self-confirmation, no self-sign-off).
- Invent tracking numbers, dates, amounts, or a `contract_no` the principal never stated — a contract number is a legal fact, and an order can be created without one; ask, or leave it empty. Change prices away from the won quotation only by saying so out loud.
- Create orders for anyone else, or touch the warehouse's fulfilment todos.

## Reference

- [references/api.md](references/api.md): request templates.
