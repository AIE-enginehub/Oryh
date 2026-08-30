# Oryh Treasury API Reference

{{include:_common/api-auth-principal.md}}

Capability: `fin_account.manage` — reads included (the register is
payroll-grade sensitive; the member surface never sees it).

## Accounts

```text
GET    /fin-accounts?account_type=&status=&keyword=
GET    /fin-accounts/{account_id}                 → current_balance is DERIVED, read-only
POST   /fin-accounts                              → opening_balance lands as the register's first row
PATCH  /fin-accounts/{account_id}                 → identity fields; there is NO balance field
DELETE /fin-accounts/{account_id}                 → archive; an archived account refuses postings (409)
```

```json
POST /fin-accounts
{
  "name": "CMB primary account",
  "institution": "China Merchants Bank",
  "account_number": "110908765",
  "account_type": "bank",
  "opening_balance": 120000.0,
  "opening_date": "2026-08-01"
}
```

`account_type` is the tenant's `fin_account_type` vocabulary (shipped:
`bank | cash | wallet | other`; `GET /type-options?family=fin_account_type`
for the current set). Duplicate name → 409.

## The Register

```text
GET  /fin-account-transactions?fin_account_id=&trans_type=&payment_id=&reference_no=&unlinked=true&date_from=&date_to=&keyword=
POST /fin-account-transactions                    → append one movement; the ONLY way balances move
PATCH /fin-account-transactions/{trans_id}        → reconciliation links ONLY (payment_id, entity_type, entity_id);
                                                    any bank-fact field is a 422 naming it — rows are frozen
POST /fin-account-transactions/bulk               → statement import; reference_no is the idempotence key
```

```json
POST /fin-account-transactions
{
  "fin_account_id": "account-id",
  "amount": -80.0,
  "trans_date": "2026-08-25",
  "counterparty": "Landlord Co",
  "description": "September rent",
  "reference_no": "B20260825-0002"
}
```

- `amount` is SIGNED (net effect on the balance); type omitted derives from
  the sign (`deposit`/`withdrawal`). The closed type catalog: `opening |
  deposit | withdrawal | transfer_in | transfer_out | fee | interest |
  refund | adjustment`. The database itself refuses a negative deposit, a
  positive fee, and any zero.
- Platform lines: `gross_amount` − `fee_amount` = `amount`, held by the
  server; the platform's raw ids ride `custom_fields`.
- `opening` belongs to account creation only — a later one is a 422; the
  fix for a wrong past is a counter-entry with the story in `description`.
- Duplicate `reference_no` on one account → 409 (single POST) or
  `unchanged` (bulk, when the amount matches — a changed amount is an error
  row for a person).

## Statement Import

```json
POST /fin-account-transactions/bulk
{
  "fin_account_id": "account-id",
  "rows": [
    {"trans_date": "2026-08-25", "amount": 300.0, "reference_no": "B-001",
     "counterparty": "Customer A", "description": "goods payment"},
    {"trans_date": "2026-08-26", "amount": -1.5, "trans_type": "fee",
     "reference_no": "B-003", "description": "bank fee"}
  ],
  "dry_run": true,
  "on_error": "abort"
}
```

Same contract as every import here: `dry_run` runs the identical write path
and rolls back; `on_error` `abort` (default) or `skip`; results report per
row (`created | unchanged | error`) with your row index. 1–500 rows per
call; chunk longer statements.

## Reconciliation Links

```json
PATCH /fin-account-transactions/{trans_id}
{"payment_id": "payment-id"}
```

The linked payment must move money the same WAY: outbound documents land as
negative lines, inbound as positive — a backwards link is a 422. Amounts
may differ (fees); say the difference to the person. `{"payment_id": null}`
unlinks. The entity pair (`entity_type` + uuid `entity_id`) points a retail
line at its order or a refund at the RETURN row; an external number in
`entity_id` is a 422 pointing you to `custom_fields`.
