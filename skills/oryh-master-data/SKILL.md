---
name: oryh-master-data
description: Use when a person's AI agent needs to load or maintain the company's master data in oryh — importing products, vendors, or customers from a spreadsheet ("把这个excel里的产品导进系统"), adding or correcting entries by hand, archiving obsolete ones, or auditing what the catalog already holds. Covers reading the file locally, working out which column means what and confirming it with the person, a dry-run preview before anything is written, upsert by the tenant's own code, and per-row reporting. Requires master-data management rights; ordinary submit/approve skills read this catalog but must never write it.
required_capability: master_data.manage
---

# Oryh Master Data

Own the catalog the rest of the company quotes and requisitions against:
**products**, **vendors**, **customers**. All three behave identically here —
same key, same upsert, same preview — so learn it once.

Customers means both kinds. A 零售会员表 and a 经销商名单 go to the same
`/customers` endpoint; what tells them apart is two optional fields on the row
(`customer_kind`, `customer_type`), not a different table. See
[references/api.md](references/api.md#retail-and-b2b-customers-customer_kind--customer_type).

The common job is a spreadsheet: someone has 产品清单.xlsx and wants it in the
system. That job is mostly not about the API. It is about reading a human
artifact correctly, and the two failure modes are silent ones:

- **Guessing a column wrong.** 单价 might be the list price or the last
  purchase price. Guess, and every quote built on it is wrong, with nothing
  to show that anything went astray.
- **Inventing a code.** The code is the identity. Make one up and the next
  import cannot match it, so it lands a second time as a new product.

Both are resolved the same way: **ask the person**. They have the file open.

{{include:_common/answer-the-question.md}}

## The Code Is The Identity

Every row needs the tenant's own code — `product_code`, `vendor_code`, or
`customer_code`. It is what the server upserts on:

- code not in the system → **created**
- code already there → **updated**, and only the fields your row carries
- same import run twice → **unchanged**, nothing duplicated

So re-running a corrected file is always safe, and is the intended fix for a
bad row. Two things follow that you must not work around:

- **A row without a code is an error, not a row to improvise.** Never
  synthesise one from the name, the line number, or a counter. Collect every
  such row and take them back to the person: "这 3 行没有编码，你看一下补哪个值".
- **A code repeated inside one file is an error too.** Do not pick a winner —
  the person needs to know their sheet has two rows claiming one code.

Archived entries keep their code on purpose, so re-importing one revives it
rather than leaving a duplicate beside it.

## Trigger Examples

- "把这个excel里的产品都导进系统"
- "供应商名单更新了，重新导一遍"
- "客户清单在这个csv里，帮我建档"
- "P-1024 这个产品改个名字" (single edit — same endpoints, one row)
- "这批产品停用了" (archive: `status: archived`)

## Required Inputs

```yaml
oryh:
  base_url: "{{ORYH_BASE_URL}}"
  api_base_url: "{{ORYH_API_BASE_URL}}"
  api_key: "{{ORYH_API_KEY}}"
```

The file itself is on the person's machine — read it where it is. Nothing is
uploaded to oryh; the server never sees the spreadsheet, only the rows you
decided to send.

## Steps

```text
1. Read the file locally (.xlsx / .xls / .csv). Find the header row — it is
   not always row 1; real sheets carry a title, a blank line, sometimes a
   merged banner above the header.

2. Work out the column mapping, then SHOW IT AND GET AGREEMENT before
   writing anything. Present it compactly:

     编码  ← "物料号"          name  ← "品名"
     规格  ← "规格型号"        单位  ← "单位"
     单价  ← "含税单价"   → list_price?   ← ask, do not assume

   - The code column is rarely called "product_code". Expect 物料号, 料号,
     编码, 编号, 产品编码, 存货编码, Item Code, SKU, Part No.
   - Say which columns you are IGNORING too. A 库存数量 or 备注 column you
     silently drop is a decision the person did not get to make.
   - Ambiguous or missing → ask. Especially any price column: list_price is
     the catalog reference price others quote against.
   - 采购价/进价/批发价/促销价 now have real homes instead of being dropped:
     a cost tied to a named supplier → that row's `suppliers` entry
     (`vendor_code` + `last_price`); a price of another kind → a `prices`
     entry with its `price_type` (wholesale/promo/cost/...). Supplier columns
     (供应商货号、交期、起订量) ride the same `suppliers` entry. The vendor
     must already exist in master data — import vendors before products that
     reference them, in the same conversation if need be.
   - **A price column that fits NO existing type is a new type, not a
     shoehorn.** 经销价/会员价/一级价 forced into `wholesale` makes every
     later report lie about what that number is. Read the tenant's current
     vocabulary first (`GET /type-options?family=product_price_type` — it
     may already hold exactly what this column means), and when nothing
     fits, say so and offer to define it:
     "表里的「二级经销价」和现有类型都对不上，建议新建一个价格类型
     dealer_tier2「二级经销价」，可以吗？" On yes:
     `POST /type-options {"family": "product_price_type", "name":
     "dealer_tier2", "title": "二级经销价"}` — then import. A 403 means this
     credential lacks `object_types.manage`: say which type is needed and
     ask an admin to add it; do NOT fall back to a wrong existing type.
     The same applies to 报销类别 and 工时类型 in their own families.
   - 客户表还有一个只属于它的问题：**这批人是谁**。一张 会员登记表 和一张
     经销商名单 进的是同一个 `/customers`，但 `customer_kind`（person /
     company）和 `customer_type`（零售/批发/经销/电商/政企，取自
     `GET /type-options?family=customer_type`）要说清楚。表里有 客户类型/
     客户分类/客户性质 这一列就照着映射，映射不上的词按新类型提（同价格类型
     那套做法）。**发的是类型的 name，不是表里的中文**——name 只能是
     `^[a-z][a-z0-9_]{0,49}$`，把"团购"原样塞进 `customer_type` 会整块 422，
     一行都不落地，而且没有分行报告可以拿去跟人对。
     **表里没有这一列就不要替人填**——留空是"没人说过"，猜成 company 是一句
     假话，个体工商户尤其两头都不像。可以直接问：
     "这批是零售会员还是企业客户？我按 person/retail 建档可以吗？"
   - 零售表常常没有编码列，只有手机号。`customer_code` 仍然是必填的身份，
     所以把用什么当编码问清楚并**一次说定**：老系统的会员号，或者手机号加个
     前缀（`M-13800000000`）。定了就整批照办，下次再导才是更新而不是重建。
   - 历史单据表（几万到几十万行的历史报价单/订单）不是这个 skill 的活：
     交给 $oryh-data-migration，它负责单据的批量导入、分块、断点续传和问
     题单据汇总。**但顺序由这里开始**——客户和产品主数据必须先导进去，否
     则每一单都会因引用不到而被跳过。
   - 盘点表（库存数量、仓库、批号、效期）走 `POST /inventory-items/bulk`。
     库存是台账：数量差异会作为一条 `import_override` 明细入账（写明系统数
     与导入数），不是把数值改掉——所以导入前把差异大的行念给人听：
     "P-001 系统 120.5，你们盘到 97，差 23.5，确认按盘点数入账吗？"
   - Columns with no home in the schema can go into `metadata` rather than
     be thrown away — offer it, do not do it silently.

3. Normalise each row:
   - trim whitespace everywhere (spreadsheet cells are full of it)
   - prices: strip ￥/,/、 and blanks → number; a blank price is null, NOT 0
   - `status`: default "active"; only "archived" if the sheet says so
   - keep the person's own text; do not "tidy" 品名 or 规格

4. DRY RUN first, always:
     POST /products/bulk  {"rows": [...], "dry_run": true}
   When you can run Python, prefer the bundled script — write the normalised
   rows to a JSON file and run (from this skill's directory):
     python3 scripts/bulk_import.py --kind products rows.json
   It dry-runs by default, chunks large files, keeps row indexes global to
   your file, and aggregates a changed-fields histogram. Either way, report
   what the response says — 将新建 47 条、更新 12 条、3 条有问题 — and for the
   updates, say WHICH fields move (the response names them). "12 条更新，都
   只动了价格" is the sentence that lets a person catch a bad mapping before
   it lands.

5. Get explicit confirmation, then re-send with dry_run false (script: add
   `--apply`).
   - Errors present? Default is `on_error: "abort"` — nothing is written and
     the person fixes the file. Offer `"skip"` only if they would rather
     import the good rows now and handle the rest after; say plainly how many
     are being left out.

6. Report the result per the response: created / updated / unchanged /
   failed, and for failures the row `index` (map it back to the person's
   spreadsheet line — the server counts your rows array from 0) with its
   reason. Never report success you did not read in the response.
```

Files over 500 rows: send in chunks of 500, in order, and report cumulatively.
Dry-run every chunk first — a mapping error shows up in chunk 1 and should
stop the rest. The bundled script does exactly this (chunking, ordered sends,
stop on the first bad chunk, cumulative report); the manual rule is for when
you call the endpoint yourself.

## Validate Before Writing

- Every row has a non-blank code, or the run does not go out.
- No code appears twice in the batch.
- A row's `suppliers` reference vendors by their `vendor_code` — codes that
  are not in vendor master data yet are that row's error; never invent a
  vendor to make an import pass.
- One price per (`price_type`, currency) per row; a re-imported equal price
  is unchanged, a different one archives the old and records the new — that
  is the intended price history, not a duplicate.
- Prices are numbers ≥ 0; a blank is null, never 0. 0 means "free", and for a
  list price that is a claim, not a gap.
- Names are the person's text, not your improvement of it.
- You showed the mapping and the person agreed to it.
- You showed a dry-run and the person agreed to it.

## What Happens Next (so you can answer the principal)

Imported products, vendors, and customers become immediately matchable by
everyone else's skills — a salesperson quoting tomorrow will find these by
keyword, and a cataloged line carries `list_price` as the reference price the
discount is judged against. That is exactly why a wrong price column is
expensive: it is not a bad cell, it is a wrong discount on every future quote.

Nothing here needs approval — master data is not a submitted document. The
import is recorded in the tenant audit log as one `master_data.imported` event
with its counts.

## What This Skill Never Does

- Invent, derive, or auto-number a missing code.
- Write anything before showing the column mapping AND a dry run.
- Guess which column is the price when more than one could be.
- Force a price column into a type that does not mean it. A missing type is
  something to propose (`POST /type-options`), never something to approximate.
  The same holds for 客户分类 and `customer_type`.
- Decide for the person whether a customer is 自然人 or 组织. If the sheet does
  not say, leave `customer_kind` out and ask — an unstated kind is a gap, and
  a guessed one is a wrong fact that later reports will repeat.
- Silently drop a column, or silently normalise someone's product names.
- Delete master data. Obsolete entries are archived (`status: archived`),
  because quotations and requisitions already reference them by id.
- Touch employees, roles, or business documents. This is catalog data only.

## Reference

- [references/api.md](references/api.md): endpoints, row shapes per family,
  and the full response contract.
- [references/spreadsheets.md](references/spreadsheets.md): reading real
  files — header detection, merged cells, Chinese column-name vocabulary,
  number and price cleanup.
