# Oryh Expense Submit API Reference

{{include:_common/api-auth-principal.md}}

## Identity And Reads

```text
GET /auth/me                                             → linked employee_id + permissions
GET /projects?keyword=&status=active                     → match a real project (read-only)
GET /vendors?tax_id={销售方税号}                          → exact vendor match by tax id (read-only)
GET /vendors?keyword={销售方名称}&status=active           → fuzzy vendor match by name (read-only)
GET /expense-claims?employee_id={me}&status=draft        → reuse before create
GET /expense-items?invoice_number={n}                    → duplicate check before filing
GET /expense-claims/{claim_id}/detail                    → claim + items + totals + attachments + approval trail
GET /approval-records?entity_type=expense_claim&entity_id={claim_id}   → progress
GET /workflow-definitions?entity_kind=builtin&object_type=expense_claim → tenant rules; apply its 提交要求 (step 2)
```

## Create Claim

```json
POST /expense-claims
{
  "employee_id": "my-employee-id",
  "title": "6月上海出差",
  "claim_date": "2026-07-10",
  "currency": "CNY",
  "source_report_text": "6月底去上海出差三天，餐费和高铁票一起报，发票都在附件里。",
  "items": [
    {"expense_date": "2026-06-28", "amount": 386.0, "category": "meal",
     "merchant": "上海楼外楼餐饮有限公司", "invoice_number": "25317000000123456789",
     "attachment_id": "<from the upload>"}
  ]
}
```

`items` rides the same transaction: a duplicated invoice anywhere in the
batch rolls the whole claim back, `claim_id`/`employee_id` per row are
implied, and the response carries the claim AND every item as stored — it is
the read-back. Standalone `POST /expense-items` remains for corrections.

Status starts at `draft`. `currency` is claim-level; a foreign-currency receipt is a conversation (convert or ask), with the original figures kept in the item's `extracted_fields`.

## Upload Evidence

```json
POST /attachments
{
  "filename": "receipt-0708.pdf",
  "content_type": "application/pdf",
  "content_base64": "<base64 of the file>"
}
```

Response carries `id` + `sha256`. Idempotent per (tenant, file content): **201** stored these bytes for the first time, **200** returned the attachment the server already held — a 200 means this exact file was uploaded before, which is the duplicate-evidence signal. Limit 10 MB per file (413 above).

Prefer the bundled script when you can run Python — same contract, with the base64, the size pre-check, and the duplicate signal computed for you:

```text
python3 scripts/upload_attachment.py 发票1.pdf 高铁票.jpg    (in this skill's directory)
```

One JSON entry per file: `id`, `sha256`, `size_bytes`, `created_at`, `already_existed` — `already_existed: true` is the duplicate signal above, taken from the server's response code (200 reused / 201 stored), not guessed from a timestamp. The raw endpoint stays the fallback when Python is unavailable.

## Items

```json
POST /expense-items
{
  "claim_id": "claim-id",
  "employee_id": "my-employee-id",
  "expense_date": "2026-07-08",
  "category": "meal",
  "amount": 186.50,
  "tax_amount": 11.06,
  "vendor_id": "vendor-id-if-confidently-matched",
  "merchant": "上海某餐饮有限公司",
  "invoice_number": "032001900311",
  "invoice_type": "vat_electronic",
  "attachment_id": "attachment-id",
  "extracted_fields": {"发票代码": "032001900311", "购买方名称": "客户公司全称", "税率": "6%"},
  "project_id": "project-id-if-confidently-matched",
  "project_name_snapshot": "ERP Upgrade",
  "notes": "optional"
}
```

`category`: the shipped catalog is travel | lodging | meal | transport | office | entertainment | communication | other;
the tenant may have defined their own (培训费…) or archived shipped ones — the
current vocabulary is `GET /type-options?family=expense_category`, and an
unknown value is a 422 listing the active options. A receipt that belongs to
no active category is a new category worth proposing —
`POST /type-options {"family": "expense_category", "name": "training",
"title": "培训费"}` (needs `object_types.manage`; on 403 tell the principal
which category is missing and file under `other` only with their agreement).
`invoice_type`: vat_special | vat_general | vat_electronic | receipt | other.

`PATCH /expense-items/{id}` / `DELETE` while the claim is editable (409 otherwise). Omit `project_id` and keep the free-text fields when master data is uncertain.

Server-enforced limits (validate in conversation before calling):

```text
amount          > 0                                → 422 otherwise
invoice_number  unclaimed among live items         → 409 otherwise (duplicate reimbursement)
employee_id     must match the claim               → 400 otherwise
items           only while claim is editable       → 409 otherwise
attachment_id   must be an uploaded file (tenant)  → 404 otherwise
project_id      must exist in this tenant          → 404 otherwise
vendor_id       must exist in this tenant          → 404 otherwise (null is fine — merchant free text stands alone)
```

## Submit

```json
POST /expense-claims/{claim_id}/submit
{}
```

Guarded by the tenant's lifecycle machine (draft/returned → submitted); idempotent on resubmit; sets `submitted_at`.

## Submitted Fact (only if the role has approval.record)

```json
POST /approval-records
{
  "entity_type": "expense_claim",
  "entity_id": "claim-id",
  "round_no": 1,
  "sequence_no": 1,
  "action": "submitted",
  "approver_role": "submitter"
}
```

403 here is expected in tenants whose member role is fact-free — the workflow admin backfills it. After a return, resubmit with `round_no` incremented.

## Correcting The Claim Header Before Submitting

```text
PATCH /expense-claims/{claim_id}
{"title": "7月苏州宏达项目出差", "claim_date": "2026-07-26", "project_id": null}
```

Editable while the claim is in an editable state (`draft`/`returned` by
default; 409 otherwise). Fix a wrong title, date, or project here rather
than deleting the claim and starting over — the items and their attachments
stay attached.

## When the decision happened

{{include:_common/when-the-decision-happened.md}}
