# Billing account API

Every path hangs off `api_base_url` exactly as given — no version prefix to add.

## Accounts

| Call | Purpose |
|---|---|
| `GET /billing-accounts?customer_id={id}` | every account one party holds |
| `GET /billing-accounts?unit_type=points` | the loyalty side only |
| `GET /billing-accounts?unit_type=currency&over_limit=true` | drawn past the credit line |
| `GET /billing-accounts?external_account_id=CARD-0001` | find by the card number it came in with |
| `POST /billing-accounts` | open one |
| `GET /billing-accounts/{account_id}` | the header, with `balance` and `available_amount` |
| `GET /billing-accounts/{account_id}/detail` | + recent entries and what is expiring |
| `PATCH /billing-accounts/{account_id}` | name, credit limit, validity, status |
| `DELETE /billing-accounts/{account_id}` | soft delete — refused while a balance stands |
| `POST /billing-accounts/{account_id}/restore` | undo that |

`keyword=` matches name, account_code, owner snapshot and external id. Lists
accept `page`/`size`.

```json
POST /billing-accounts
{
  "name": "市一院预存款",
  "unit_type": "currency",
  "unit": "CNY",
  "customer_id": "customer-uuid",
  "credit_limit": 50000.0,
  "opening_balance": 100000.0,
  "external_account_id": "OLD-SYS-8842"
}
```

- exactly one of `customer_id` / `vendor_id` / `employee_id` (422 otherwise)
- `unit_type` is `currency` or `points` and is **immutable**, as are `unit` and
  the owner — each decides what may be posted here
- `unit`: a 3-letter currency code, or an active
  `GET /type-options?family=billing_account_unit` value for points
- `credit_limit` is how far the balance may go NEGATIVE; 0 means no overdraft
- `opening_balance` becomes the account's first entry (`reason: "initial"`),
  never a stored field
- `account_code` is server-allocated (`BA-`) unless you bring the workspace's own

`status` is `active` / `frozen` / `closed`. A non-active account refuses every
movement, including payment settlement.

## Entries — the ledger the balance is a sum of

| Call | Purpose |
|---|---|
| `POST /billing-accounts/{account_id}/entries` | record movement |
| `GET /billing-account-entries?billing_account_id={id}` | the ledger |
| `GET /billing-account-entries?reason=expired` | one kind of movement |
| `GET /billing-account-entries?entity_type=payment&entity_id={id}` | what a document caused |

```json
POST /billing-accounts/{account_id}/entries
{
  "lines": [
    {"amount": 300.0, "reason": "earned", "description": "消费 3000 元",
     "entity_type": "sales_order", "entity_id": "order-uuid",
     "expires_at": "2027-12-31T00:00:00Z"}
  ],
  "idempotency_key": "grant-so-2026-0031"
}
```

Returns the written entries, the new `balance`, and `available_amount`
(`balance + credit_limit`).

- `amount` is signed; zero is a 422
- `reason` from `GET /type-options?family=billing_account_entry_reason`:
  `deposit`, `charge`, `refund`, `earned`, `redeemed`, `expired`, `adjustment`,
  `transfer`, `initial`, `import_initial`, `other` — the workspace extends it
- `expires_at` is a 422 on a currency account
- a repeat with the same `idempotency_key` returns `replayed: true` and writes
  nothing
- there is no PATCH and no DELETE: a correction is a line with the opposite sign

## Expiry

```text
GET /billing-accounts/{account_id}/expiring?before=2026-12-31T00:00:00Z
```

Returns positive entries whose `expires_at` is before that moment and which no
`expired` entry points at yet, plus `expiring_amount` (their sum) and the
account's current `balance`.

Expire a batch by posting a negative `expired` entry that **names the batch**:

```json
{"lines": [{"amount": -300.0, "reason": "expired",
            "entity_type": "billing_account_entry", "entity_id": "<earn entry id>"}]}
```

That pointer is what makes the sweep idempotent — the next pass excludes the
batch instead of expiring it again.

`expiring_amount` is the batches' total, not the amount to expire: the server
does not track which batch a redemption drew from, because FIFO/LIFO/pool is
the workspace's rule and lives in its workflow definition.

## Settlement against a money account

```json
POST /payments/{payment_id}/apply
{"lines": [{"applied_to_type": "billing_account", "applied_to_id": "account-id",
            "amount_applied": 100000.0}]}
```

An inbound payment **increases** the balance (预存), an outbound one
**decreases** it (refund). The account's ledger records the movement in the same
transaction, so the balance stays the entries' sum however the money arrived.

Unlike an invoice, an account has no ceiling — a deposit is not a claim — so
the response reports `balance` and `available_amount` instead of
`settleable_total` / `outstanding_amount`.

### The guards, and exactly when they fire

| Condition | Answer |
|---|---|
| balance would fall below `-credit_limit` | 409 naming what IS available |
| a payment applied to a `points` account | 409 — money never enters a points balance |
| payment currency ≠ the account's unit | 409 |
| account `frozen` or `closed` | 409 |
| `amount: 0` | 422 |
| `expires_at` on a currency account | 422 |
| unknown `reason` or points `unit` | 422 listing the active options |
| owner not exactly one | 422 |
| lowering `credit_limit` below what is drawn | 409 |
| deleting an account that still holds a balance | 409 |

## Related

- `GET /workflow-definitions?entity_kind=builtin&object_type=invoice` — where a
  workspace states its earning and redemption rules. The server holds none.
- `POST /invoice-items` with `invoice_item_type: "discount"` — the money half of
  a points redemption. The points half is an account entry; they are two facts,
  and nothing converts between them.
