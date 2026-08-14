---
name: oryh-purchase-order
description: Use when a procurement agent needs to place, maintain, or receive against purchase orders in oryh — 下采购单/向供应商订货 from approved purchase requests (按单采购 keeps the request-line link), recording goods arrival (收货) with or without a warehouse, and closing or cancelling the order. The vendor is required — a PO is a commitment to a specific supplier. Not for filing the requisition (that is oryh-purchase-submit), approving it (oryh-purchase-approve), or routing the flow (oryh-purchase-approval-flow).
required_capability: purchase_order.manage
---

# Oryh Purchase Order

The purchase order is the **commitment to a vendor** — the document that
leaves the building. Everything upstream (requisition, sourcing, approval) is
internal deliberation; this skill records what was actually ordered, from
whom, at what price, and what has actually arrived.

Two facts shape every step:

- **The vendor is required.** A requisition may say "还没定找谁"; a PO cannot.
  If the supplier is not decided, the work still belongs upstream.
- **One capability drives everything.** `purchase_order.manage` files, edits,
  advances, and receives — procurement is a function, not "my own documents",
  so there is no submit/approve split and no built-in second approval. Tenants
  wanting PO审批 add it via workflow definitions and the flow agent.

{{include:_common/answer-the-question.md}}

## Trigger Examples

- "给戴尔下采购单" / "按上周批的采购申请下单"
- "PO-2026-00012 到货了，入上海仓"
- "显示器到了6台，剩下的直发客户了"
- "把这张采购单关了" / "供应商没货，取消"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # needs purchase_order.manage (admin default; NOT in the member default)
```

## Lifecycle

Default machine: `draft → submitted → confirmed → received → closed`, with
`cancelled` reachable until `received`. Items and adjustments are editable
**only in `draft`** (409 afterwards). Tenants rename and rewire states
(`GET /object-type-definitions?entity_kind=builtin&object_type=purchase_order`),
so read the machine rather than
assuming these names. Status never moves by itself — receiving goods records
facts, and **you** move the status when the facts support it (all lines
arrived → `received`; invoiced/settled per tenant practice → `closed`).

## Steps

1. **Find the work.** Ordering usually starts from an approved requisition:
   `GET /purchase-requests?status=approved` (or the ordering todo the flow
   agent assigned — see `$oryh-my-work`). Read the request's `/detail` for
   lines, quantities, target vendor, and quotes.
2. **Reuse before create**: `GET /purchase-orders?vendor_id={id}&status=draft`
   — an open draft to the same vendor takes more lines; retries must not
   duplicate. `?keyword=` also matches po_number/title/vendor snapshot.
3. **Create the order** with `vendor_id` (required — match via
   `GET /vendors?keyword=`) and `employee_id` (the buyer). Omit `po_number`
   for a server-allocated `PO-` number; pass one to keep a tenant's own
   numbering (409 = that number exists).
4. **Add items** — send them inline on the create (`items` on `POST
   /purchase-orders`, one call and one transaction, a bad line rolls the order
   back), or afterwards with `POST /purchase-order-items`. Catalog lines carry
   `product_id`/`sku_id` (name and unit backfill; SKU-level granularity works as
   everywhere); free-text lines carry `product_name_snapshot`. 按单采购: pin each line to the requisition
   line it fulfils with `purchase_request_item_id` — the chain then shows in
   both details, and through the requisition's own `sales_order_item_id` link
   it reaches the customer order that triggered the buy.
5. **Adjustments** (运费/税/整单折扣) work exactly as on quotations and
   orders: signed amounts, header- or line-pinned, and the type must be an
   active `sales_adjustment_type` option (`GET /type-options?family=sales_adjustment_type`;
   tenants extend via `POST /type-options`).
6. **Read back before advancing.** `GET /purchase-orders/{po_id}/detail` gives
   lines, adjustments, `computed_total`/`adjusted_total`, and
   ordered-vs-received quantities. Confirm with the principal, then
   `PATCH {"status": "submitted"}` → (vendor confirms) → `"confirmed"`.
7. **Receive** with `POST /purchase-orders/{po_id}/receive` as goods arrive —
   partial deliveries are many calls, each accumulating `received_quantity`:
   - a line with `facility` lands in the inventory ledger (position found or
     created; ledger reason `received`, pinned to the PO line);
   - a line **without** `facility` is a 直发/零库存 receipt — recorded on the
     PO, never touching stock;
   - free-text lines (no product) can only be received without a facility.
8. **Advance on facts.** All lines received (over-receipt 超收 is legal and
   recorded as stated — flag it, don't block it) → `"received"`, then
   `"closed"` per tenant practice. If the order came from a requisition, tell
   the flow agent's queue by completing the ordering todo; the request's
   `ordered` status is the flow agent's move, not yours.

## Validate Before Writing

- `vendor_id` and `employee_id` must exist here (404 otherwise); quantity > 0;
  items need `product_id` or `product_name_snapshot` (422).
- Unit price far off the vendor's history (`GET /supplier-products?vendor_id=`
  shows `last_price`) → show both, ask. Receiving quietly updates that
  `last_price` when the (product, vendor) link exists — it never invents one.
- Receiving more than ordered, or into an unexpected warehouse → confirm in
  conversation first; the server records what you state.
- A cancel after goods were received → the inventory entries stand; reversing
  stock is an explicit inventory adjustment, not a side effect. Say so.

## What This Skill Never Does

- Order without a decided vendor, or invent vendors/products to make a line pass.
- Approve its own purchase — tenants wanting PO审批 route it through workflow
  definitions and the flow agent before `submitted → confirmed`.
- Move `received`/`closed` ahead of the recorded facts, or walk a status
  backwards to "fix" history.
- Touch the requisition's status (`ordered` belongs to the flow agent) or the
  sales order it chains to.
- Import historical POs — that is `$oryh-data-migration`
  (`POST /purchase-orders/bulk`).

## Reference

- [references/api.md](references/api.md): all endpoints, the receive
  contract, and the 按单采购 chain.
