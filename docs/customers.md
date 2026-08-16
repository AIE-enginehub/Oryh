# Customers: one table for retail and B2B, and why not Party

A company's book routinely holds both a retail member and a group account. `customers` is
one table, and the question this document answers is why — because the two
obvious alternatives (a second table, or an OFBiz Party layer) were both on the
table and both refused.

## Why one table

The test is the one `Invoice` passes and the orders fail.

`PurchaseOrder` and `SalesOrder` are separate entities where OFBiz shares one
`OrderHeader`, because their counterparty, direction and closure all differ.
`Invoice` is one entity carrying both directions, because its closure mechanic
is identical on both sides and splitting would have duplicated the settlement
machinery — the expensive half.

Customers fail the splitting test the same way an invoice does. A member and a
hospital go through identical machinery end to end:

| | Retail member | B2B customer |
|---|---|---|
| quotation → order → invoice | same | same |
| `applied_amount` settlement | same | same |
| aging, outstanding | same | same |
| standing balance | `billing_accounts`, `unit_type: points` | `billing_accounts`, `unit_type: currency` |
| exactly-one-counterparty guard | same | same |

What genuinely differs is the FILE — a member has a phone and no tax id, a
hospital has a tax id, invoicing details and a procurement contact — and a
file's differences are
what nullable columns and `metadata_jsonb` are for.

Splitting would have cost more than the duplication. `customer_id` appears on
six tables, and the exactly-one-counterparty CHECK on `payments`,
`invoices` and `billing_accounts` would have gone from three branches to four.
That is the real hazard: **a fourth counterparty type is how a Party layer
arrives by the back door**, without anyone deciding to build one.

## Two axes, deliberately different in kind

```
customer_kind   person | company        closed   column + CHECK
customer_type   retail | wholesale | …  open     type_options vocabulary
```

`customer_kind` is OFBiz's Person/PartyGroup distinction with the Party table
not built. It is a constrained column and not vocabulary because the
distinction is universal rather than the tenant's to extend — no workspace
should be able to add a third kind or archive one of the two. That closure buys
two things that outlive today: a constraint may branch on it later (a phone
unique per person is the obvious candidate, and a tenant-extensible vocabulary
could never support one), and if a Party layer is ever built this is exactly
the discriminator it needs, unchanged.

Null is a first-class answer on that axis. Nobody stated a kind is a true
statement; `company` guessed onto ten thousand imported members is a false one
repeated by every later report, and a sole proprietor sits genuinely on the line. The
0048 migration backfills `company` only where `tax_id is not null` — a
A unified social credit code on the record means the tenant already files that customer as an
organization, which is what the number IS rather than an inference from it.

`customer_type` is the tenant's own segmentation (retail, wholesale, dealer,
e-commerce, government and public bodies, related parties),
so it is a `type_options` family like every other `*_type`. A workspace adds
a group buyer or a franchisee without waiting for a release.

**Neither field gates anything**, and that is load-bearing rather than an
omission. What a dealer may be sold at, whether a member prepays, who gets payment terms
— those are judgments, and judgments live in agents and workflow definitions.
The moment the server branches on `customer_type`, the tenant can no longer
extend it safely, which is the same argument that keeps `Invoice.direction` and
`BillingAccount.unit_type` OUT of the vocabulary and in a CHECK.

## Retail's one real structural difference

Not the schema — the scale and the natural key. A retail book is orders of
magnitude longer than a vendor list, and the lookup is by phone, so
`customers_tenant_phone_idx` exists. It is deliberately **not** unique: a shared
household number is an ordinary fact, and a duplicate member record costs a
merge rather than money — the bar every constraint in this codebase has to
clear.

`customer_code` remains required for bulk import, retail included. The skill's
instruction is to settle the convention with the person once (the old system's
member number, else `M-<phone>`) and apply it to the whole file, because that
choice is what makes the next import an update instead of a second copy.

## Why not Party (and when to revisit)

OFBiz's `Party` collapses customer/vendor/employee into one identity with roles,
which would replace `customer_id` / `vendor_id` / `payee_employee_id` with a
single `party_id`. It was considered and deferred:

- OFBiz's own `Payment` does not carry one `partyId` — it carries `partyIdFrom`,
  `partyIdTo` and `roleTypeIdTo`. "One pointer" is really a pointer plus a role
  plus a role vocabulary; here, the role is encoded in the column NAME, free.
- The counterparty set is stable at three (seller, buyer, our own people). Tax
  authorities, banks, landlords and contractors are all counterparties —
  vendors — which is how OFBiz files
  them too (a tax authority is a PartyGroup with a `TAX_AUTHORITY` role).
- Database guarantees would weaken. `invoices_direction_counterparty_ck` today
  proves in the DB that `direction='sales'` implies a customer and no vendor.
  Against a `party_id` that becomes a cross-table join — an application check at
  best.
- The API's consumer is an agent reading skill docs. `customer_id` is
  self-describing; `party_id` adds a dereference ("who is this, in what role?")
  to every read and write.

Revisit when any of these is actually true — not before:

1. A fourth or fifth counterparty type appears that genuinely needs its own
   master-data lifecycle, and is not a vendor wearing a hat. (Shareholders —
   dividends and shareholder loans — are the plausible one.)
2. Something needs "any party" as data: a unified contact-method or bank-account
   table (OFBiz's `ContactMech`), or cross-role netting that must be stored
   rather than computed by an agent.
3. A CRM-shaped module arrives where the person-to-organization relationship is
   itself the content.

And when that day comes, grow it from the edge: add `parties`, hang a
`party_id` off `customers` / `vendors` / `employees`, and let new features join
through it — leaving every document FK and every agent-visible field alone. The
uuid-primary-key convention is not an obstacle either way (OFBiz's shared-PK
one-to-one maps onto it directly); the migration surface is, which is precisely
why it should be paid for by a feature that needs it.
