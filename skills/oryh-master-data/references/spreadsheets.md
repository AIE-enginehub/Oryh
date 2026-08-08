# Reading The Person's Spreadsheet

Real files are not clean tables. This is the part of the job the API cannot
help with, and the part where a silent mistake is most expensive.

## Finding The Header

The header is often not row 1. Expect a title row (「2026年产品价格表」), a
blank spacer, an export banner, or a merged cell spanning the sheet.

Find the first row where most cells are short non-numeric labels and the rows
beneath it are consistently populated. If two candidate rows look plausible,
show the person both and ask. Do not silently pick one.

Also watch for:

- **Multiple sheets** — 产品 / 供应商 / 停用 in one workbook. Ask which sheet,
  and say what the others appear to hold. Never merge sheets on your own.
- **Merged cells** in the header, which read as a label plus blanks. The label
  belongs to all the columns it spanned.
- **Trailing junk rows** — 合计, 制表人, 备注 blocks under the data. A row
  whose code cell is empty but which has text elsewhere is usually one of
  these, not a product missing its code. Say so rather than reporting it as a
  missing-code error: "最后 3 行看着是合计和制表人，我跳过了，对吗？"
- **Frozen index columns** — a leading 序号 1,2,3… is a line number, NOT the
  product code. This one is worth being explicit about, because it looks
  exactly like a code and importing it would be a disaster to unwind.

## Column Name Vocabulary

Same field, many names. Recognise, then confirm — recognition is a hypothesis,
not a decision.

| Field | Commonly appears as |
|---|---|
| `product_code` | 物料号 · 料号 · 编码 · 编号 · 产品编码 · 存货编码 · 商品编码 · Item Code · SKU · Part No. |
| `name` | 品名 · 名称 · 产品名称 · 商品名称 · 存货名称 · Description |
| `spec` | 规格 · 型号 · 规格型号 · 规格/型号 · Spec · Model |
| `unit` | 单位 · 计量单位 · 基本单位 · UOM |
| `list_price` | 单价 · 售价 · 标准售价 · 目录价 · 参考价 · 含税单价 · 不含税单价 · List Price |
| `vendor_code` | 供应商编码 · 供应商代码 · Vendor Code |
| `supplier_product_code` | 供应商货号 · 供应商型号 · 厂家型号 · 厂家货号 |
| `last_price` | 采购价 · 进价 · 最近采购价 · 供货价 |
| `lead_time_days` | 交期 · 货期 · 交货天数 · 供货周期 |
| `min_order_quantity` | 起订量 · 最小起订量 · MOQ |
| `customer_code` | 客户编码 · 客户代码 · 往来单位编码 · 会员号 · 会员卡号 · Customer Code |
| `customer_type` | 客户类型 · 客户分类 · 客户性质 · 客户级别 · 渠道类型 |
| `customer_kind` | 单位性质 · 客户属性（只当它真在说"个人/单位"时；见下） |
| `quantity` | 库存数量 · 实盘数量 · 结存数量 · 在库数量 · 账面数量 |
| `facility` | 仓库 · 库房 · 存放仓库 · 仓 |
| `lot_id` | 批号 · 批次 · 生产批号 · Lot No. |
| `expire_date` | 效期 · 有效期 · 有效期至 · 失效日期 |
| `tax_id` | 税号 · 纳税人识别号 · 统一社会信用代码 |
| `contact` | 联系人 · 业务员 · 对接人 |
| `phone` | 电话 · 联系电话 · 手机 |
| `address` | 地址 · 收货地址 · 通讯地址 |

### Price columns deserve a question of their own

`list_price` is the **catalog reference price** — the number future quotes are
compared against to judge a discount. Several columns can look like it:

- 含税单价 vs 不含税单价 — materially different numbers. Ask which one the
  catalog price should be; do not average, convert, or pick the larger. A
  price-book entry records the fact either way (`tax_in_price`, and 税率 in
  `tax_percentage`) — never convert between them yourself.
- 采购价 / 进价 / 成本价 — a cost, **not** a list price. Importing a cost as
  `list_price` makes every future discount calculation nonsense — but it now
  has a real home: when the sheet names the supplier, it is that supplier's
  `last_price` on the row's `suppliers` entry; with no supplier named, a
  `prices` entry with `price_type: "cost"`. Confirm which before writing.
- 最近成交价 / 历史单价 — a past transaction, not a catalog price.
- Multiple tiered prices (一级/二级/经销价) — ask which tier is the catalog
  price. 批发价/经销价 can land as `price_type: "wholesale"` book entries;
  anything the person cannot place goes to `metadata`, kept, not guessed.

Empty price → `null`. Never `0`: zero is a claim that the item is free.

## Cleaning Values

- **Whitespace** everywhere, including inside codes ("P-001 " from a merged
  cell). Trim. The server trims codes too, but trim before comparing rows
  yourself so in-file duplicates are found.
- **Numbers as text** — "￥1,200.00", "1 200", "1200元". Strip currency marks,
  thousands separators, and unit suffixes.
- **Full-width characters** in codes (Ｐ－００１) — normalise to half-width,
  and mention that you did.
- **Excel date/number coercion** — a code like "0012" may arrive as `12`, and
  "2-1" may have become a date. If codes look mangled, say so and ask the
  person to re-export that column as text rather than reconstructing values.
- **Formula cells** — read the computed value, not the formula.
- **Duplicate rows** — genuinely identical rows can be collapsed (tell the
  person); rows sharing a code with DIFFERENT values cannot, and are an error
  for them to resolve.

## Presenting The Mapping

Short, complete, and explicit about what you are not importing:

```text
读到 62 行，表头在第 3 行。字段对应：

  product_code ← 物料号          name  ← 品名
  spec         ← 规格型号        unit  ← 单位
  list_price   ← 含税单价        status← (无，默认 active)

  忽略：库存数量、仓位、备注
  最后 2 行看着是合计和制表人，已跳过

含税单价作为目录价对吗？（另有一列"采购价"我没用）
```

Then dry-run, and report the counts before writing anything for real.
