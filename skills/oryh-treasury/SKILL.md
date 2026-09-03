---
name: oryh-treasury
description: Use when the cashier/treasury person's AI agent manages where the company's money actually sits and moves — opening fin accounts (银行户/现金/微信支付宝 PayPal 商户), importing bank or platform statements ("把招行这个月流水导进来"、"微信账单对一下"), recording fees/interest/transfers by hand, and reconciling register lines against paid payments ("这笔打款到账了吗"、"对账"). The register is the bank's truth: rows append and never change; balances derive. Requires fin_account.manage.
required_capability: fin_account.manage
---

# Oryh Treasury

The cash side of the house, split from the accounting side on purpose
(cash and ledger split): payments are documents the finance desks write; THIS desk holds
the accounts money actually sits in and the register of how it moved — as
the bank saw it. The two meet only at reconciliation, and the meeting is a
LINK, never an edit.

Three rules carry everything here:

- **The register is the bank's fact.** Rows append; nothing edits or
  deletes one; a wrong row is corrected by a counter-entry. The only
  writable part of a landed row is its reconciliation links.
- **Balances derive.** An account's `current_balance` is the running sum of
  its register — there is no balance field to set, anywhere, ever. The
  opening balance is the register's first row.
- **Reconciliation state derives too.** "Unmatched" means the links are
  null; nothing stores "reconciled". Read `?unlinked=true`, never memory.

## Trigger Examples

- "Open an account: CMB primary account, opening balance 120,000"
- "Here is August's bank statement spreadsheet — import it"
- "Pull the WeChat merchant bill and reconcile it"
- "The 80,000 to the landlord went out — match it in the register"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"            # the treasury principal's key
```

## Steps

{{include:_common/answer-the-question.md}}

{{include:_common/read-before-you-decide.md}}

1. **Accounts**: one row per place money sits — a bank account, the cash
   box, each third-party payment balance. `account_type` comes from the
   tenant's `fin_account_type` vocabulary (`GET /type-options?family=fin_account_type`);
   `institution` is the bank or the platform (WeChat Pay/Alipay/PayPal). A
   PayPal holding several currencies is several accounts, one per currency.
   Opening balance rides the create and lands as the register's first row —
   never ask to "correct the balance" later; post the movement that explains
   the difference.
   **Before opening, ask how far back the statements will ever go.** The
   opening is a balance AS OF a date, and every line before that date is
   already inside it — so `opening_date` must be the start of the EARLIEST
   period this account will ever import, and `opening_balance` the bank's
   balance at that moment. An account opened at 8/1 because August's
   statement was the one at hand cannot take January later without the
   restatement below; one question now saves it.
2. **Statement import** (the usual work): read the bank's file locally —
   the master-data discipline applies verbatim: find the header row, show
   the column mapping and get agreement, say which columns you IGNORE, dry
   run before writing. Then `POST /fin-account-transactions/bulk`. The
   bank's own line id goes in `reference_no` — that is what makes
   re-importing the same statement report `unchanged` instead of doubling
   money. A reference that comes back with a DIFFERENT amount is an error
   row: take it to the person, never overwrite.
3. **Platform statements** (WeChat/Alipay/PayPal): fetch the bill with the
   TENANT'S own tools and credentials — oryh stores no platform secrets and
   pulls nothing. Their lines carry three numbers: map the gross
   transaction amount → `gross_amount`, the fee → `fee_amount`, the settled
   amount → `amount`; the server
   holds `amount = gross − fee`. Platform ids (payment numbers, buyer ids) go in
   `custom_fields`; the platform's line id is still `reference_no`.
4. **Hand entries**: fees, interest, cash drawer movements — one POST each,
   type stated (`fee`, `interest`, `adjustment`, `refund`); omitted type
   derives from the sign (in = deposit, out = withdrawal). Signs are held by
   the database itself: money in is positive, out is negative.
5. **Transfers between own accounts** — a payout from the WeChat merchant balance to the bank,
   moving cash between banks, currency conversion: TWO rows, `transfer_out`
   on the source (negative) and `transfer_in` on the destination
   (positive). In a conversion the two amounts differ — that difference IS
   the exchange rate, not an error. The bank side of a platform payout
   usually prints Tenpay/Alipay as the counterparty; that is your matching
   clue.
6. **Reconciliation, the loop**:
   - `GET /fin-account-transactions?unlinked=true` — bank facts nothing of
     ours explains yet. For each, find the paid payment it settles (the
     amount signs must agree; amounts may differ by fees — say the
     difference out loud) and `PATCH {"payment_id": ...}`.
   - Retail platform lines have NO payment document — that is normal, not a
     gap. Their reconciliation is the daily aggregate: sum the day's lines
     against the platform's settlement summary and against order totals;
     investigate differences, don't force per-line links. When a line IS
     matched to one order or a refund to its RETURN row, use the entity
     pair (`entity_type: "sales_order"`, `entity_id`).
   - The reverse queue: payments marked `paid` with no register line yet —
     money the books claim moved and the bank hasn't shown. Chase these;
     they are the whole point of keeping two sources.
7. **Never "fix" the register to match the books.** When they disagree, one
   of them is wrong about the world; find out which, and correct the books
   or counter-enter the register — with the story in the description.
8. **Restating the opening** (statements older than the opening date must
   be imported): do NOT rebuild the account — the rows and links already
   landed would be lost — and do NOT split one bank account into a
   "history" account. The register's own rule answers it, in three writes,
   with the earlier balance B0 as of the new start date D0 and the
   original opening O as of its date D1:
   1. import the older statements as usual (`/bulk`, `reference_no` dedup);
   2. `POST /fin-account-transactions` `{"trans_type": "adjustment",
      "amount": B0, "trans_date": D0, "description": "opening restated: balance at D0"}`;
   3. `POST /fin-account-transactions` `{"trans_type": "adjustment",
      "amount": -O, "trans_date": D1, "description": "opening restated: reverses the D1 opening, which already contained D0..D1"}`.
   The total is unchanged (B0 + older net = O), the balance as of any date
   between D0 and D1 now reads correctly (the original opening and its
   reversal cancel on D1), and the original `opening` row stays as the
   history it is. Read the account back and say the number before and
   after — they must be equal.

## What This Skill Never Does

- Edit or delete a register row, set a balance, or post a second `opening`
  — an earlier start is a restatement (step 8), never a rebuild.
- Write payment documents — recording who we owe and paying it is the
  finance desks' work ($oryh-payables, $oryh-receivables); this desk
  records what the bank did and links it.
- Hold or ask for platform credentials on oryh's behalf — bills are fetched
  with the tenant's own tools.
- Invent a matching: a link you are not sure of is a question for the
  person, with the candidates and amounts laid out.

## Reference

- [references/api.md](references/api.md): endpoints, the import contract,
  the sign rules.
