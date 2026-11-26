---
name: oryh-ledger
description: Use to keep a workspace's books in oryh — set up the chart of accounts, post journal entries for invoices, payments, payroll and month-end, reverse a wrong posting, find and post what the book is missing or waive what needs no entry, close a month, and read the trial balance, an account's ledger or who owes what. Applies the workspace's own posting rules; the server only keeps the book balanced and closed months shut. Requires ledger.post (reading needs ledger.read; closing a month needs period.close).
required_capability: ledger.post
---

# Oryh Ledger

The book is the workspace's journal: balanced debits and credits, each
entry naming the document or event it records. You do the accounting; the
server keeps the book honest. It refuses an entry that does not balance,
posts to a summary or archived account, leaves out the party a receivable or
payable account keeps, converts at a rate that does not add up, records the
same source fact twice, or lands in a closed month. It never decides which
account anything goes to.

**Nothing posts by itself.** Issuing an invoice or receiving a payment puts
nothing in the book until you post an entry for it. Balances, the trial
balance and each party's balance are worked out from posted lines on every
read.

{{include:_common/answer-the-question.md}}

{{include:_common/api-auth-principal.md}}

{{include:_common/confirm-before-you-write.md}}

{{include:_common/business-rules.md}}

## Trigger Examples

- "Set up our chart of accounts for a small trading company"
- "Post March's sales invoices to the books"
- "That entry used the wrong account — fix it"
- "Close February"
- "Show me the trial balance for Q1"
- "Who still owes us money according to the books?"

## Required Inputs

```yaml
oryh:
<!-- only: bundle -->
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
<!-- /only -->
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
<!-- only: bundle -->
  api_key: "{{ORYH_API_KEY}}"     # ledger.post
<!-- /only -->
```

## The Workspace's Posting Rules

Which account a document posts to is the workspace's decision, written as a
`policy` rule:

```text
GET /business-rules?kind=policy&category=accounting&in_force_on=<the posting date>
```

(or wherever that workspace filed it). Apply it as written and say which
rule you applied. **If nothing is written, do not invent a mapping.**
Propose one from the table below, get the person's confirmation, and
suggest writing it down as a rule so the next posting does not ask again.

| Event | Usual entry (propose, never assume) |
|---|---|
| Sales invoice issued | Dr receivable (the customer) / Cr revenue, Cr output VAT |
| Purchase invoice received | Dr expense or inventory, Dr input VAT / Cr payable (the vendor) |
| Money received against an invoice | Dr bank / Cr receivable (the customer) |
| Money paid against a bill | Dr payable (the vendor) / Cr bank |
| Payslip | Dr salary expense / Cr salaries payable (the employee), Cr withholdings |
| Expense claim reimbursed | Dr expense / Cr payable to the employee |
| Credit note issued | the original invoice's entry with sides swapped, for the note's amounts |
| Credit note set against an invoice (`invoice_offset`) | Dr receivable (customer) on the note / Cr receivable on the invoice — on a single receivable account, nothing moves and nothing need be posted |

## Setting Up The Books

1. **Currency once**: `PUT /accounting-settings {"functional_currency":
   "CNY"}`. It is fixed once anything has posted.
2. **The chart**: read `GET /ledger-accounts` first. If the workspace has no
   chart, ask which standard it follows and propose the accounts it needs,
   not the whole catalogue. Create them after the person confirms:
   `POST /ledger-accounts {"account_code", "name", "account_type",
   "parent_id"?, "subledger"?}`.
   - `account_type`: `asset`, `liability`, `equity`, `income`, `expense`.
   - `subledger`: `customer` on receivables, `vendor` on payables,
     `employee` on staff advances and salaries payable. Every line on that
     account must then name the party.
   - An account with sub-accounts is a summary and takes no lines. A
     sub-account shares its parent's type.
   - A foreign-currency account (`"currency": "USD"`) takes lines that state
     the foreign amount and the rate.

## Posting A Document

1. **Already in the book?** `GET /journal-entries?source_type=invoice&source_id=<id>`.
   If an entry stands for that event, stop: posting it again is refused.
2. **Build the entry from the posting rule**:

```text
POST /journal-entries
{"posting_date": "<the document's date, if its month is open>",
 "description": "INV-000123 Huaxin, March goods",
 "source_type": "invoice", "source_id": "<id>", "source_event": "issued",
 "status": "posted",
 "lines": [
   {"ledger_account_id": "<1122 receivable>", "debit": 1130, "customer_id": "<Huaxin>"},
   {"ledger_account_id": "<6001 revenue>", "credit": 1000},
   {"ledger_account_id": "<2221 output VAT>", "credit": 130}]}
```

   - `source_event` says which fact of the document this is (`issued`,
     `received`, `paid`, `reimbursed`). One fact posts once.
   - `source_type` is one of `invoice`, `invoice_offset`, `payment`, `payment_application`,
     `expense_claim`, `sales_order`, `purchase_order`, `shipment`,
     `inventory_item_detail`, `fin_account_transaction`,
     `billing_account_entry`, `business_object`. A manual entry (an accrual,
     a correction) names no source.
   - Each line is a debit or a credit, never both. Cost centre and project
     go on the line when the rule asks for them.
   - Send an `Idempotency-Key` header: a retried post must not post twice.
3. **Draft or posted**: post directly when the rule is clear and the person
   has agreed to the mapping. For month-end entries, accruals or anything
   judged, leave `status` off to file a **draft**, show it, and post it with
   `POST /journal-entries/{id}/post` once confirmed. A draft can be changed
   (`PATCH`, `lines` replaces all of them) or discarded (`DELETE`).

If the document's month is closed, the post is refused. Post it in the open
month and say so, or ask whoever holds `period.close` whether to reopen.

## Correcting A Posting

A posted entry is never edited or deleted.
`POST /journal-entries/{id}/reverse {"posting_date"?, "description"?}`
posts its mirror (debits become credits), on today's date unless you name
another open day. The original stays, marked reversed, and its source fact
can then be posted again correctly. An entry is reversed once; a reversal
is not reversed.

## What The Book Does Not Say Yet

`GET /ledger-coverage?period=<any day of the month>&families=` lists, per
family, how many documents' money counted that month, how many a posted
entry names, and which are **missing**; and the **stale** entries — posted
that month for a document since voided, cancelled or deleted.

- Default families: `invoice` (by direction: sales, purchase, payroll,
  reimbursement), `payment` (by direction), `expense_claim`, and
  `fin_account_transaction` (bank lines not matched to a payment — fees,
  interest). Ask for `payment_application`, `invoice_offset` or
  `billing_account_entry` when the workspace's rule posts them.
- A document counts as recorded when any posted, unreversed entry names it,
  whatever its `source_event`. The read shows no events; if the rule posts
  one document more than once (issued, then received), check those with
  `GET /journal-entries?source_type=&source_id=`.
- The server does not say what must be posted. A missing row is a document
  no entry names — post it by the rule, or, where the rule says it needs
  none, waive it (below).
- A stale entry is the book saying something that no longer happened.
  Propose its reversal; reverse it once agreed.

### Waiving A Document

Some documents need no entry: a pro forma invoice never billed, a
reimbursement invoice that mirrors a claim already posted. A waiver records
that decision so the coverage stops listing it as missing:

`POST /ledger-waivers {"source_type": "invoice", "source_id", "source_event"?, "reason", "decided_by"}`

- **Never waive on your own judgement.** Waive only what the workspace's
  posting rule says needs no entry, or what the person tells you to — and
  name them in `decided_by` ("Ms Li, controller"); it defaults to you. Put
  their reason in their words.
- Without `source_event` the whole document is waived; with one, only that
  event (the rule posts the issue but not the receipt).
- A fact is never both waived and in the book: a waiver for a posted fact
  is refused (reverse the entry first), and posting a waived fact is refused
  with the waiver named — revoke it first if the person changed their mind.
- A waiver is never edited or deleted.
  `POST /ledger-waivers/{id}/revoke {"reason"?}` withdraws it; the document
  is missing again. The coverage lists live waivers under `waived` with the
  reason and who decided.

## Closing A Month

1. Read `GET /ledger-coverage?period=<the month>` with the families the
   rule posts. Post what is missing, waive what the rule or the person says
   needs no entry, propose reversals for what is stale, and read it again.
2. Read the trial balance.
3. `POST /accounting-periods/close {"period": "2026-02-01", "reason"?}` (any
   day in the month). Drafts dated in that month block it: post or discard
   them first. Closing is not refused while documents are missing — that is
   the person's decision. If anything is left, say exactly what, and put it
   in the close reason.

Reopening needs a reason: `POST /accounting-periods/reopen {"period", "reason"}`.

After closing, read the month's result:
`GET /income-statement?date_to=<the month's last day>` and
`GET /balance-sheet?as_of=<the month's last day>` — the `$oryh-financial-statements`
skill explains them. Then report the month in one line the person can check: "Everything issued, paid
and approved in March is in the book; two pro forma invoices waived by Ms
Li" — or the exact list of what is not.

## Reading The Books

- `GET /trial-balance?date_from=&date_to=` — every account's opening,
  debits, credits and closing; summaries carry their sub-accounts.
  `natural_closing` is the closing figure on the account's usual side
  (income reads positive). Totals of debits and credits are equal.
- `GET /ledger-accounts/{id}/ledger?date_from=&date_to=` — an account's
  lines with a running balance.
- `GET /ledger-accounts/{id}/parties?as_of=` — a receivable or payable per
  party.
- `GET /income-statement` and `GET /balance-sheet` — profit and loss and
  what the business owns and owes; see `$oryh-financial-statements`.

Answer in the person's terms: "Receivables stand at 48,200; Huaxin owes
31,000 of it, all from March."

## What This Skill Never Does

- Choose an account mapping nobody stated or confirmed.
- Edit or delete a posted entry — reverse it.
- Post into a closed month, or reopen one without the holder of
  `period.close` and a reason.
- Convert currencies at a rate nobody gave: a converted line states the rate
  and the source of it is the person's or the rule's.
- Treat a document as booked because it exists — check the book.
- Waive a document nobody decided needs no entry, or revoke a waiver
  without saying so.

## Reference

- [references/api.md](references/api.md): request templates.

Chinese request aliases and original example wording are available in
[locale examples](locales/zh-CN/examples.json); preserve user-provided names and text.
