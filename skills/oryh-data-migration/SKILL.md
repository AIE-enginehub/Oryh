---
name: oryh-data-migration
description: Use when a company is moving HISTORICAL business data into oryh in bulk — 把老系统/旧ERP的历史报价单、历史销售订单导进来, "这是我们2021到2024年的报价单，几十万条", a migration workbook with thousands of rows, or backfilling past documents that already ended. Covers the mandatory order (master data first, then documents), reading the workbook, a dry run before anything lands, chunked imports that resume after an interruption, and reporting the documents whose customer or product no longer exists. Not for filing today's quotation or order — those are the submit skills.
required_capability: tenant.act_for_any_employee
---

# Oryh Data Migration

Historical documents are **facts that already happened**, and importing them
is a different job from filing today's work. They carry their own numbers,
they ended long ago in states nobody is going to walk them through, and they
belong to many salespeople — several of whom may have left. This skill exists
because the submit skills would do all three wrong.

The volume is the other reason. A migration is tens of thousands to hundreds
of thousands of documents; at that size a mistake found on row 200,000 must
not mean starting over, and one departed customer must not stop the run.

## Trigger Examples

- "把老系统的历史报价单导进来"
- "这是我们 2021-2024 的销售订单，大概三十万条"
- "历史数据迁移，先导哪个？"
- "上次导到一半断了，怎么接着导？"

## Required Inputs

```yaml
oryh:
  api_base_url: "{{ORYH_API_BASE_URL}}"  # every API path below hangs off THIS — already complete
  base_url: "{{ORYH_BASE_URL}}"          # the console address, for links a person opens
  api_key: "{{ORYH_API_KEY}}"     # needs tenant.act_for_any_employee
```

Plus the workbook(s), on the person's machine — read them where they are.

## The Order Is Not Optional

```text
1. 客户 (customers)   ← $oryh-master-data
2. 产品 (products)     ← $oryh-master-data
3. 供应商 (vendors)    ← $oryh-master-data; only if importing采购单
4. 员工 (employees)    ← whoever owns HR data; every document names a salesperson
5. 历史报价单          ← POST /sales-quotations/bulk
6. 历史订单            ← POST /sales-orders/bulk      (can link back by quote number)
7. 历史采购单          ← POST /purchase-orders/bulk   (needs purchase_order.manage; vendor REQUIRED per row)
8. 期初应收应付         ← POST /invoices/bulk          (needs invoice.manage for each direction present)
9. 历史收付款          ← POST /payments/bulk          (needs payment.record)
```

Documents reference master data **by the tenant's own codes**. Import them in
the wrong order and every single document fails the same way — unmatched
`customer_code`, unmatched `product_code` — which looks like a broken import
but is only a sequencing mistake. Say this out loud before starting: "先导客
户和产品，再导单据，否则每一单都会因为找不到引用被跳过。"

## Steps

1. **Survey before promising anything.** Open the workbook and report what
   you found: how many documents, which columns, what date range, how many
   distinct customers/products/salespeople. Numbers now prevent surprises at
   row 200,000.
2. **Map the columns and get agreement**, exactly as $oryh-master-data does —
   the same 单号/客户/金额 ambiguities apply. Say which columns you are
   ignoring. A historical total that disagrees with the line sum is normal
   (that is what `total_amount` beside the lines is for); do not "fix" it.
3. **Check the master data is in place**: sample 20-30 codes from the
   workbook against `GET /customers?keyword=`/`GET /products?keyword=`. If the
   sample already misses codes, stop and do step 1-2 of the order above first
   — finding it now costs minutes, finding it after a full run costs a rerun.
4. **Dry run one chunk** (500 rows) with `dry_run: true`. Report the summary
   and every failing document by its number. This is the moment to decide the
   reference policy below.
5. **Import in chunks of 500**, in order, reporting cumulative progress.
   Prefer the bundled `scripts/import_documents.py` when you can run Python
   (in this skill's directory — the path is relative to it) —
   it chunks, keeps a running summary, and collects every problem document
   into one list instead of drowning the person in per-chunk output.
6. **Report the problem documents** at the end: their numbers, grouped by
   cause (unknown customer / unknown product / missing salesperson). That
   list is the person's work item, not a failure of the import.
7. **Spot-check** a handful of imported documents with
   `GET /sales-quotations/{id}/detail` — lines, adjustments, the total — and
   show one to the person.

## 期初余额: Import the Facts, Then Match Them

Opening balances are the step that actually decides whether a company can
switch, and they are two imports plus a matching pass — never one column.

An imported invoice arrives **fully outstanding**, and an imported payment
arrives **fully unapplied**. There is deliberately no "already paid" column on
either row: writing settlement straight into the ledger would bypass the
over-application, direction and currency guards that are the only reason the
ledger can be trusted, and a wrong opening balance is the one migration error
nobody catches for months.

So the sequence for a half-paid historical invoice is:

1. import the invoice at its **full** original amount, with its own `due_date`;
2. import the payment that was already received, at its own amount;
3. match them with `POST /payments/{payment_id}/apply` — the same guarded call
   the finance agents use every day.

For a company that only wants the open balance and not the history, importing
the invoice at its **remaining** amount is a legitimate simplification — but it
is the person's decision, not yours. Say what it costs: the original amount and
the collection history are gone, and any later reconciliation against the old
system will not tie out. Ask before choosing it.

Reconcile before declaring done: the sum of `outstanding_amount` per customer
should equal the old system's 应收账款明细. Report the comparison; a migration
that imported cleanly and still disagrees with the old trial balance has not
succeeded.

## Two Decisions Only The Person Can Make

**An unmatched customer or product.** Default (`on_missing_reference:
"error"`) reports those documents and imports the rest. The alternative
(`"snapshot"`) imports them anyway, keeping the historical text with no link
to master data. Put it to them plainly:

> "有 1,240 单的客户编码在系统里找不到（共 43 个客户，比如 C-0881）。两个
> 选择：先把这 43 个客户补进主数据再导，单据就能关联上；或者按历史文本导
> 进去，单子留着客户名但不关联客户档案。你选哪个？"

Never choose silently. A snapshot-imported document can never be found by
"这个客户历年买过什么" — that is a real loss, and it is theirs to accept.

**A departed salesperson** is always an error, in both modes: a document
cannot exist without an owner. The fix is to create the employee record
(archived is fine — they are history too), then re-run. **A purchase order's
vendor** works the same way: the counterparty is not optional, so an
unmatched `vendor_code` is always an error — create the vendor first
(archived is fine), never snapshot around it.

## Resuming, And Why Re-running Is Safe

The document number is the identity and the upsert key. Re-importing the same
file reports `unchanged` and writes nothing. So:

- interrupted at row 180,000 → **just run the whole file again**; the first
  180,000 land as `unchanged` in seconds and the rest import normally.
- a corrected file → re-run it; changed documents report `updated`, their
  lines and adjustments replaced wholesale.
- never "resume from row N" by hand. Re-running the whole file is both
  cheaper and safer than trusting your own bookkeeping about where it stopped.

## What This Skill Never Does

- Import documents before master data, or invent a customer/product/employee
  to make a row pass.
- Change a historical document's status to walk it through the lifecycle. It
  ended as it ended; `accepted`/`declined`/`signed` import as-is.
- Let the server allocate a number over a historical one — the original
  number IS the record's identity, and losing it breaks every reference the
  person still has on paper.
- Decide the unmatched-reference policy without asking.
- File today's quotation or order — that is $oryh-quotation-submit and
  $oryh-order-submit.

## Reference

- [references/api.md](references/api.md): both bulk endpoints, the row shape,
  the report contract, and the chunking script.
