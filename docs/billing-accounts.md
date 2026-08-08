# Billing accounts: one shape for money and for points

A billing account is **one party's standing balance in one unit**. OFBiz has
the money half of this; the rest is an extension it does not model.

## Why one table

OFBiz's `BillingAccount` is a customer's credit/house account: `accountLimit` is
the ceiling, and the balance comes from the invoices charged to it. Strip that
to its shape and it is *a balance in some unit, with a floor, owned by one
party, moved by a ledger*.

Loyalty points, stored value and coupon quotas are the same object. They have
the same questions (what is the balance, may this movement happen, what expires
when) and the same answers. Splitting them into a second table would have
duplicated the balance, the floor, the owner rule, the ledger, the idempotency
and the expiry — every part except the word "unit".

So `unit_type` sits beside the money case:

| | `unit_type: currency` | `unit_type: points` |
|---|---|---|
| `unit` | a currency code (`CNY`) | a tenant vocabulary entry (`point`, 油卡额度…) |
| typical `credit_limit` | the credit line (挂账额度) | 0 — points cannot be overdrawn |
| settled by payments | yes | **never** |
| `expires_at` on entries | refused | the point of the field |

One party may hold several accounts, which is exactly what "各种积分或 credit"
means in practice: a customer with stored value, loyalty points and a coupon
quota is three accounts, not three columns on `customers`.

`unit_type` is a constrained column rather than a `type_options` vocabulary for
the same reason `Invoice.direction` is: every guard in the settlement path
branches on it, and a value the tenant could add would leave those guards
undecidable. Money reaching a points balance has to be unrepresentable, not
merely discouraged.

## The balance is a running sum

`billing_accounts.balance` is materialized, and `billing_account_entries` is
the append-only ledger it sums. This is the third instance of a shape already in
the codebase:

| running total | its ledger |
|---|---|
| `inventory_items.quantity_on_hand` | `inventory_item_details` |
| `invoices.applied_amount` | `payment_applications` |
| `billing_accounts.balance` | `billing_account_entries` |

Everything follows from it. An opening balance is the account's first *entry*,
never a field. Every write path — the entries endpoint and the settlement
endpoint alike — funnels through one function, so the floor cannot be reached
around. The integrity audit asserts `balance = sum(entries)` because it is an
identity, and it breaks the same silent way the other two do.

Entry provenance uses the generic `(entity_type, entity_id)` pair, deliberately
*unlike* `payment_applications`' explicit foreign keys. The two references mean
different things: a payment application names the document it settles — a closed
set, on which money correctness depends — while an entry names whatever caused
it, which is open-ended (a payment, an invoice, an order, a birthday grant, a
manual adjustment, or another entry when this one expires it).

## Where it meets settlement

A customer's prepayment is a payment **applied to the account** (OFBiz's
`PaymentApplication.billingAccountId`), which both marks the payment as used and
appends the account's ledger in one transaction. An invoice may be charged to an
account (`invoices.billing_account_id`); drawing the account down is an explicit
entry, not a side effect of issuing the invoice.

This is the one target that does not fit the settlement guard's original shape,
which is why `SettlementTarget` carries a running column and two bounds:

| target | running column | floor | ceiling |
|---|---|---|---|
| invoice | `applied_amount` | 0 | billed total |
| expense claim | `applied_amount` | 0 | items total |
| payment (netting) | `applied_amount` | 0 | its amount |
| **billing account** | `balance` | `-credit_limit` | **none** |

A deposit is not a claim, so there is nothing to over-settle; what it can do is
go too far negative, which is the credit line. And the direction rule inverts:
every other target is settled from exactly one side, while an account takes
deposits in and pays refunds out — so `settling_direction` returns `None` and
the sign of the effect comes from the payment's direction instead.

## The server converts nothing

"用 500 积分抵 5 元" is **two facts**, recorded separately:

1. a points entry — `-500`, `reason: redeemed`, pointing at the document;
2. a `discount` line on that document for ¥5.

The server will not turn points into money. The rate is a business rule that
belongs in the tenant's workflow definition, and a record layer that quietly
applied one would be inventing policy — the same position that makes
cross-currency settlement a 409 rather than a conversion.

The same line holds for earning rules, tiers, birthday multipliers and which
products earn at all. None of them are here.

## Expiry: facts, and a queue

Entries carry `expires_at` (points only). Expiry itself is a negative `expired`
entry a flow agent writes, and it **names the earn batch it expired** through
the provenance pair. That pointer is what makes
`GET /billing-accounts/{id}/expiring` answerable and the sweep idempotent: the
next pass excludes batches something already expired instead of expiring them
twice.

`expiring_amount` is the batches' sum, **not** the amount that should expire.
How much of a batch survived redemption depends on whether the workspace draws
FIFO, LIFO or from a pool — and the server does not track which batch a
redemption came from.

That gap is deliberate. Batch-level consumption tracking would answer the
question exactly, at the price of a consumption table and of writing FIFO into
the server, where a business rule does not belong. The honest arrangement is
that the server reports the batches and the agent applies the workspace's rule.

## Capabilities

| capability | scopable | holder |
|---|---|---|
| `billing_account.manage` | no | opening accounts, credit limits, freezing, closing |
| `billing_account.post` | `:currency` / `:points` | writing movements |

The split is not ceremony: granting points is the fraud-prone action in this
family, and the scope lets 会员运营 hold `:points` while 财务 holds
`:currency` — neither of them able to open an account or change a credit line.
`billing_account.post:*` is in the hosted flow agent's fixed grant set so it can
run the expiry sweep. Neither capability is in the `member` default.

## Deliberately out of scope

- **Multi-party accounts.** OFBiz's `BillingAccountRole` lets several parties
  share one account (集团授信). Collapsed to a single owner, as `payments` is.
- **`BillingAccountTerm`.** Payment terms live on the documents, not the account.
- **Points-to-money conversion, in any direction.** See above.
- **Batch-level consumption tracking.** See above.
- **Tiers and membership levels.** Tenant-defined objects, not a fixed schema.
