---
name: oryh-billing-account
description: Use when someone needs to work with a party's standing account balance — 客户预存款 and 挂账额度 (deposit money, draw against a credit line, check how much a customer may still charge), or 会员积分/储值/券额 (grant points for a purchase, redeem them, run the expiry sweep, answer "我还有多少分"). One account is one balance in one unit; a customer may hold several. Not for invoicing or collecting (oryh-receivables), not for paying suppliers (oryh-payables), and it never converts points into money.
required_capability: billing_account.post
---

# Oryh Billing Account

A billing account is **one party's standing balance in one unit**. Money and
points are the same object here — a balance, a floor, an owner, and an
append-only ledger of movements — which is why one customer can hold a stored
value account, a loyalty account and a coupon quota side by side.

Four facts shape everything:

- **The balance is never set; it is posted to.** Every movement is a ledger
  entry, and the balance is their sum. There is no "correct the balance" call.
- **The floor is `-credit_limit`.** A points account has a limit of 0, so it
  cannot be overdrawn. A credit account may go negative exactly as far as it
  was allowed, and the server refuses the entry that would go further.
- **Money and points never convert.** "500 分抵 5 元" is TWO facts you record
  separately, never one exchange the server performs. See below — this is the
  single most important line in this skill.
- **Corrections are counter-entries.** The ledger has no edit and no delete.

{{include:_common/api-auth-principal.md}}

## Trigger Examples

- "市一院预存了 10 万" / "他们还能赊多少"
- "这单给客户加 300 积分"
- "用积分抵一下这张单"
- "跑一下积分过期" / "去年的积分该清了"
- "把这个会员的账户冻结"

## Required Inputs

```yaml
oryh:
  base_url: "{{ORYH_BASE_URL}}"
  api_key: "{{ORYH_API_KEY}}"     # needs billing_account.post; opening accounts needs billing_account.manage
  employee_id: "{{EMPLOYEE_ID}}"
```

`billing_account.post` may be scoped to one unit type — a workspace can hand
`:points` to 会员运营 and `:currency` to 财务. Granting points is the
fraud-prone action, which is why it is separable from both opening accounts and
moving money. If your key holds only one scope, do that half and say plainly
who owns the other.

## Opening an Account

`POST /billing-accounts` with exactly one owner (`customer_id`, `vendor_id` or
`employee_id`) and the unit:

- money: `unit_type: "currency"`, `unit: "CNY"`
- points: `unit_type: "points"`, `unit` from
  `GET /type-options?family=billing_account_unit` (the workspace extends it —
  油卡额度, 观影券, whatever they actually call it)

`credit_limit` is how far the balance may go **negative**. Leave it 0 for
points and for prepaid money; set it only when the workspace really is
extending credit, and confirm the number with the person rather than assuming.

An `opening_balance` is recorded as the account's first entry, not as a field —
so the balance is the ledger's sum from the very first row.

**The unit, the unit type and the owner cannot be changed afterwards.** Each of
them decides what may be posted and to whom; a wrong account is closed and a
right one opened.

## Recording Movement

```json
POST /billing-accounts/{account_id}/entries
{
  "lines": [{"amount": 300.0, "reason": "earned", "description": "消费 3000 元",
             "expires_at": "2027-12-31T00:00:00Z"}],
  "idempotency_key": "grant-so-2026-0031"
}
```

- The amount is **signed**: positive adds, negative spends or reverses.
- `reason` comes from `GET /type-options?family=billing_account_entry_reason`.
- **Always pass an `idempotency_key`** when granting or spending: this writes a
  balance, and a retry without one posts twice. A repeat with the same key
  returns `replayed: true`.
- `expires_at` only means something on a points account (422 otherwise).
- Every line of one call is judged together, so a request that would breach the
  floor is refused whole — never half-posted.
- Link the movement to what caused it with `entity_type`/`entity_id` (the
  order, the invoice, the entry being reversed). Do it: it is what makes the
  balance explainable a year later.

## 预存 and 挂账 (money accounts)

A customer's prepayment is a payment applied to the account, not an entry you
write by hand — that way the payment is marked as used and the account's ledger
records it in the same breath:

```json
POST /payments/{payment_id}/apply
{"lines": [{"applied_to_type": "billing_account", "applied_to_id": "account-id",
            "amount_applied": 100000.0}]}
```

Drawing the account down for a document IS an entry (`reason: "charge"`,
pointing at the invoice). Refunding money back out is an **outbound** payment
applied to the account, which reduces the balance.

"还能赊多少" is `available_amount` on the account — balance plus whatever credit
remains. Accounts already past their line:
`GET /billing-accounts?unit_type=currency&over_limit=true`.

## Points: earning, redeeming, expiring

**How many points a purchase earns, and what they are worth, are NOT in this
skill and NOT in the server.** Read them from the workspace's own words:

```text
GET /workflow-definitions?entity_kind=builtin&object_type=invoice
```

…or wherever that workspace wrote its membership rules. If nothing states a
rate, ask — do not invent one.

**Redeeming against a document is two facts, never one conversion:**

1. a points entry — `amount: -500`, `reason: "redeemed"`, pointing at the
   document being paid;
2. a `discount` line on that document for the money value (¥5), or a payment
   for it.

The server will not turn 500 points into ¥5 for you. That rate is a business
rule, and a record layer that quietly applied one would be inventing policy —
the same reason cross-currency settlement is refused rather than converted.

**The expiry sweep**:

```text
GET /billing-accounts/{account_id}/expiring?before=2026-12-31T00:00:00Z
```

Returns the earn batches past that date that nothing has expired yet. Then, for
each batch you decide is actually spent, post:

```json
{"lines": [{"amount": -300.0, "reason": "expired",
            "entity_type": "billing_account_entry", "entity_id": "<the earn entry id>"}]}
```

**Pointing at the earn entry is what makes the sweep safe to re-run** — the
next pass sees that batch as handled instead of expiring it twice.

`expiring_amount` is the sum of those batches, **not** the amount to expire.
How much of a batch survived redemption depends on whether the workspace draws
points FIFO, LIFO or from a pool; the server does not track which batch a
redemption came from, and that口径 lives in the workflow definition. Say which
rule you applied when you report.

## Validate Before Writing

- Owner must exist here; exactly one of the three (422 names the rule).
- A points unit must be an active option; a currency unit is a 3-letter code.
- Breaching the floor is a 409 that names what IS available — read it, do not
  retry the same numbers.
- A `frozen` or `closed` account refuses every movement, including settlement.
  Freezing is deliberate; ask before reactivating.
- Lowering a credit limit below what is already drawn is a 409.
- An account still holding a balance cannot be deleted.

## What This Skill Never Does

- Convert points into money, or money into points.
- Decide earning rates, redemption rates, tiers or expiry 口径.
- Set a balance directly, or edit/delete a ledger entry.
- Apply a payment to a points account (409 — and rightly).
- Change an account's unit, unit type or owner.
- Reactivate a frozen account without being asked to.

## Reference

- [references/api.md](references/api.md): every endpoint, the entry contract,
  and the guards with the exact conditions that raise them.
