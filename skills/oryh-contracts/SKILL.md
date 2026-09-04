---
name: oryh-contracts
description: Use when a person's AI agent files or consults contracts in oryh — recording a signed contract with a factory, supplier or customer ("把这份代工合同录进去"、"这是签好的扫描件"), locating its key clauses (付款条件、首付款、交货节奏、验收、违约责任) so questions are answered from the clause itself ("这个合同的付款节奏怎样?"、"首付多少?"、"什么时候交货?"), recording supplements and renewals, and linking purchase orders, invoices and payments to the contract they execute. Requires contract.manage (scoped :purchase or :sales).
required_capability: contract.manage
---

# Oryh Contracts

{{include:_common/answer-the-question.md}}

A contract in oryh is a natural-language file plus the clauses located
inside it. The originals — PDF, scanned pages, Word — live in the
attachment store, linked to the contract with the text you extracted from
each; the located clauses are the contract's OWN WORDS, verbatim, tagged
by type, pointing at the file and page they came from. That is the whole
design: a question about payment is one lookup by type, never a re-read
of forty pages, and never your memory of them.

## Three rules

- **Verbatim in `content`, your reading in `summary`.** A term's `content`
  is copied from the contract exactly — punctuation, clause number,
  percentages. What it means ("30% deposit on signing, 60% before
  shipment, 10% after acceptance") goes in `summary`. A scalar you are sure of (a deposit percentage, a lead time
  in days) may ride `metadata`; never invent one.
- **What the contract does not say, say it does not say.** Asked about a
  clause type with no term, answer that the contract has no such clause
  — then offer to search the extracted text, and only then the original.
  Never answer a contract question from recollection.
- **The original is never edited.** A supplement, a renewal, a changed
  price is a NEW contract with `parent_contract_id` pointing at the one
  it modifies, with its own originals and terms. A signed contract's own
  fields are frozen; the desk's notes (`summary`, `remarks`) are not.

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  api_key: "{{ORYH_API_KEY}}"            # the contract desk's key (contract.manage:purchase / :sales)
```

## Filing a contract

1. **Header**: `POST /contracts` with `title`, `contract_type` (the
   tenant's `contract_type` vocabulary: purchase / oem / sales /
   framework / service / nda / …), ONE counterparty (`vendor_id` for the
   purchase side, `customer_id` for the sales side — the side is derived
   and is what your scope is checked against), dates, `total_amount`,
   signatories, and `items` where the contract lists what is contracted
   (product, quantity, unit price, delivery note). Omit `contract_no` for
   `CT-NNNNNN`.
2. **Originals**: for every file the person hands you, `POST /attachments`
   (any format — a PDF, each scanned page, the Word draft) then
   `POST /contract-documents` with `document_type` (signed / draft / annex
   / scan_page / amendment / translation), `page_no` for scanned pages,
   and **`extracted_text`: the text YOU read out of that file** with your
   own tools (OCR for images, the text layer for PDFs). oryh runs no OCR;
   this is where the text lives so nobody reads pictures twice. Files over
   10 MB are split by page.
3. **Locate the clauses**: read the text once and for each core type
   present — payment_terms, deposit, payment_method, delivery_schedule,
   delivery_terms, acceptance, quality, warranty, price, penalty,
   term_period, termination, dispute — `POST /contract-terms` with the
   verbatim passage, `clause_ref`, your `summary`, and `document_id` +
   `page_no`. Several clauses of one type are several rows. A type the
   contract lacks gets no row. A kind of clause the vocabulary lacks is a
   new type option, not `other`.
4. **Sign**: `PATCH /contracts/{id} {"status": "signed"}` when it is —
   `signed_at` stamps itself; then `active` when it governs. Review
   before signing, where the workspace wants it, is todos and approval
   facts against the contract; the server records the signing, never the
   verdict.

## Answering questions

`GET /contract-terms?contract_id=&term_type=payment_terms` → quote the
`content`, give the `summary`, name the clause and page. Then stop; the
person asked one question. A question the types do not cover →
`GET /contract-documents?contract_id=&keyword=` searches the extracted
text and returns the passages. Across contracts: `GET /contracts?
vendor_id=&status=active` first, then the terms.

## Executing under a contract

Orders, invoices and payments name the contract they execute
(`contract_id` on `POST /purchase-orders`, `/sales-orders`, `/invoices`,
`/payments`) — on the contract's own side, which the server checks. A
deposit is an outbound payment with `contract_id` and no invoice to apply
to ($oryh-payables); `GET /contracts/{id}/execution` derives what has
happened — ordered, invoiced, paid, contracted vs ordered by product —
and stores nothing.

## What This Skill Never Does

- Paraphrase into `content`, or answer a clause question from memory.
- Edit a signed contract's agreement fields, or "update" a contract for a
  supplement — that is a new contract pointing at its parent.
- Write a term type the vocabulary lacks as `other` because it was quicker.
- Read a contract it is not scoped to: a buyer's key sees purchase
  contracts; the seller's desk sees its own.

## Reference

- [references/api.md](references/api.md): endpoints and shapes.
