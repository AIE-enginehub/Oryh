---
name: oryh-expense-submit
description: Use when a person's AI agent needs to file, update, query, or submit that person's own expense claim in oryh. Covers reading invoice/receipt images and PDFs, extracting the structured fields, confirming them with the principal, uploading the evidence, duplicate-invoice checks, line items, submission, and fixing a returned claim. It records the submitter's facts only — routing and approval belong to other roles.
required_capability: expense.submit_own
---

# Oryh Expense Submit

Record and submit the principal's own expense claim. The credential is the identity: the server only accepts writes for the employee linked to this key, so never ask "for whom" — it is always the principal.

You are the OCR. oryh stores facts and evidence; it does not read receipts. Read the invoice or receipt file the principal provides (image or PDF), extract the fields yourself, confirm them, and write three things: the original file (attachment), the structured extraction (item fields + `extracted_fields`), and the principal's own words (`source_report_text`).

## Trigger Examples

- "File an expense claim" / "Claim these receipts for me"
- "Submit a travel claim, the receipts are here"
- "The claim came back — fix it and resubmit"
- "Where has my expense claim got to?"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # the principal's user-bound key
```

Everything else comes from conversation: the receipts, the purpose, the amounts.

## Steps

{{include:_common/answer-the-question.md}}

{{include:_common/fewer-round-trips.md}}

{{include:_common/read-before-you-decide.md}}

{{include:_common/leave-no-orphan-work.md}}

{{include:_common/stay-current.md}}

1. **Identity**: your employee id is already in this file — `{{EMPLOYEE_ID}}`. No call needed. Do not create employees; that is an HR/admin capability. Blank means no employee record is linked to this principal: say so, do not work around it.
2. **Tenant requirements**: `GET /workflow-definitions?entity_kind=builtin&object_type=expense_claim` — the tenant's natural-language rules for this object, current as of this moment. Read what it requires of a submission (how old a receipt may be, whose name must be on it, per-category limits, and the like) and let it shape the conversation from the first receipt — see the "Tenant requirements" layer below. No definition, or nothing in it about filing a claim → only the universal checks apply; never invent requirements. Routing rules in the same document belong to other roles — ignore them.
3. **Reuse before create**: `GET /expense-claims?employee_id={me}&status=draft` — reuse an open draft for the same trip/purpose; retries must not duplicate. A `returned` claim is also reused: fix it, don't recreate — and read why it came back first: the rework todo's `description` and the latest `returned` approval record's `comment` list exactly what to fix, usually citing the step-2 requirements. After a successful resubmit, complete that rework todo (`PATCH /todos/{todo_id}` `{"status": "completed"}`; needs `todos.complete_own`, in the default member role) — while it stays open, the claim is invisible to the flow admin's work queue.

   **Steps 2 and 3 do not feed each other — send them as one batch.** The tenant's rules and your own open documents are independent lookups; waiting for the first before asking the second doubles the wait for no reason.

4. **Read each receipt** the principal provides. Extract: invoice number, invoice date, seller, total including tax, tax amount, buyer name, invoice type. Anything you cannot read confidently is a question for the principal, never a guess.
5. **Validate every receipt BEFORE writing** — see "Validate before writing" below. Check duplicates first: `GET /expense-items?invoice_number={n}` — a hit means this invoice was already claimed; stop and tell the principal.
6. **Upload evidence first**: `POST /attachments` per receipt file (base64),
   **all files in one batch** — uploads do not depend on each other.
   Idempotent per file content, and the response code says which happened:
   **201 = these bytes are new, 200 = the server already held them**. A 200
   means this exact file was uploaded before — say so before filing an item
   against it. When you can run Python, prefer the bundled
   `scripts/upload_attachment.py` (in this skill's directory): it does the
   base64, the 10 MB pre-check, and reports `already_existed` per file.
7. **The whole claim, one call**: `POST /expense-claims` with `employee_id`,
   `title` (the purpose, such as "Shanghai trip, June"), `claim_date`, the principal's
   original words in `source_report_text`, and **every receipt inline in
   `items`** (`expense_date` = the date on the receipt, `amount`, `category`,
   `merchant`, `invoice_number`, `invoice_type`, `attachment_id` from step 6,
   full extraction in `extracted_fields`; `claim_id`/`employee_id` are
   implied — do not repeat them). One bad item — a duplicated invoice
   included — rolls the whole claim back; a 409 on `invoice_number` means
   the server caught a duplicate you missed: surface it, don't work around
   it.
   - **The response is your read-back**: header and every item as stored.
   - Corrections after the fact: `POST /expense-items` to add,
     `PATCH`/`DELETE` per item to fix. Items are editable only while the
     claim is in the tenant's editable states (default `draft`/`returned`) —
     a 409 means the claim has moved on.
   - Project: send `project_id` only when a real project record is confidently matched (`GET /projects?keyword=`); otherwise keep `project_name_snapshot` + `client` as free text. Never invent projects.
   - Vendor: match the receipt's seller against vendor master data — `GET /vendors?tax_id={seller_tax_id}` (exact key, best) or `GET /vendors?keyword={seller_name}`. Send `vendor_id` only on a confident match; `merchant` always keeps the seller name exactly as printed. No match is normal — leave `vendor_id` null. Never create vendors; that is master-data management.
8. **Submit**: `POST /expense-claims/{id}/submit` — only after the pre-submit read-back below got an explicit yes. Idempotent — resubmitting a submitted claim is a no-op. The response's `status`/`submitted_at` is the confirmation; tell the principal it is submitted, with the total you already hold from step 7.
9. **The submitted approval fact is not yours to write.** `/submit` records it (`round_no` derived, `sequence_no=1`, `source=system`), so the trail opens with it whether or not this credential carries `approval.record`. Posting it anyway is harmless — the recorded fact comes back — but there is nothing to do here.

## Validate Before Writing

Three layers. Hard rules the server enforces — check them yourself first so the principal gets a question, not an error code. Tenant requirements the workflow admin calibrates against — the server records whatever is legal, but a claim that ignores them comes straight back. Reasonableness checks are yours alone: you are the only gate between a blurry photo and a wrong claim.

**Hard rules (the server rejects these; catch them in conversation first):**

- `amount` per item: more than 0.
- One invoice number, one claim: a live item with the same `invoice_number` anywhere in the tenant → 409.
- Items only while the claim is `draft`/`returned`.
- `attachment_id` must be a previously uploaded file; `project_id` must be a real record — free text goes in `project_name_snapshot`, never a guessed id.
- Attachments: 10 MB per file.

**Tenant requirements (the workflow admin returns violations; catch them in conversation first):**

- Whatever the step-2 definition requires of a claim, applied receipt by receipt. Typical shapes: the invoice may not be more than 90 days old; it must be made out to the company's full legal name; meals have a per-item limit; travel must be linked to a project. The definition's own wording always wins over these examples.
- Several reasonableness questions below (how old a receipt may be, whose name is on it, large meal amounts) are exactly what tenants write into their definition — when the definition answers one, apply its answer instead of guessing or asking.
- These are the exact requirements the workflow admin's agent checks before assigning any approver, and its return note cites the ones violated — so a requirement skipped here is a guaranteed rework round.
- Fixing a returned claim? Re-run step 2 first — the requirements may have changed since the original submission, and the current version is what the next calibration uses.

**Reasonableness (pause and ask before writing):**

- Extracted amount ≠ what the principal said → show both, ask which is right. The receipt usually wins, but say so out loud.
- The buyer name on a VAT invoice is not the company → likely a personal-title invoice; confirm the tenant accepts it.
- Invoice date older than ~90 days → many tenants refuse stale receipts; confirm before filing.
- Receipt date is a weekend/holiday for a workday-type expense (client lunch on a Sunday) → confirm it was business.
- A receipt with no invoice number (taxi slip, quota invoice) → file with `invoice_type: "receipt"` and no number; tell the principal duplicate protection won't apply to it.
- Unreadable or partially readable fields → ask for a clearer photo or the missing value; never fabricate a number.
- The same file uploaded twice, or two receipts with identical amount + date + merchant → probably the same expense; ask.
- An amount that is unusually large for the category (a ¥3,000 lunch) → confirm before writing.

**How to have the conversation:**

- Show your extraction next to the receipt: "I read this invoice as: number 032001900311, 8 July, a Shanghai restaurant, 186.50 including tax — is that right?" One receipt, one confirmation.
- Never silently "fix" an amount, date, or merchant — a correction the principal didn't see is worse than the error.
- If the principal confirms an unusual fact (the ¥3,000 dinner was a client banquet), record it exactly as stated and put the clarification in `notes`. Judging reasonableness is the approver's job; yours is faithful capture plus honest flagging.

**Pre-submit read-back:** before step 9, `GET /expense-claims/{id}/detail` and echo the complete claim **from that response** — each receipt's line and the total — then get an explicit confirmation. Submission hands the record to the approval flow; changing it afterwards costs a return round.

Echoing it from memory is what this step exists to prevent, and doing so has already cost a live session: an agent listed two lines to a person whose draft held three, and refused the submission they then confirmed. The count you read out must be the count that just came back.

## What Happens Next (so you can answer the principal)

The claim now sits in the workflow admin's queue. It is first calibrated against the same submission requirements you applied in step 2 — a non-compliant claim comes back as a rework todo without reaching any approver — then approvers are assigned per the tenant's workflow definition. Progress is visible any time via the approval trail (`GET /approval-records?entity_type=expense_claim&entity_id={id}`) — the status stays `submitted` until the flow finishes, then moves to `approved` and, once finance pays out, `paid` (tenant machines may differ). If it is returned, a rework todo appears in the principal's inbox (see `$oryh-my-work`); fix the items and submit again.

## What This Skill Never Does

- Approve, decide routing, or touch the claim status (`/submit` is the only transition it makes).
- Create employees, projects, or vendors as a side effect.
- Submit for anyone other than the credential's own employee.
- Fabricate, round, or "correct" receipt fields without showing the change and getting agreement.
- File an invoice it knows is already claimed, or submit without the pre-submit read-back.

## Reference

- [references/api.md](references/api.md): request templates.
