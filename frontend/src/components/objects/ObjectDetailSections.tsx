import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  attachmentContentUrl,
  type Attachment,
  type ObjectDetail,
} from "../../api/objects";
import { useI18n } from "../../i18n";
import { formatDate, formatDateTime, formatMoney, ObjectStatus } from "./ObjectRecordTable";

type LocalText = (chinese: string, english: string) => string;

const FIELD_LABELS: Record<string, [string, string]> = {
  id: ["记录 ID", "Record ID"],
  object_type: ["对象类型", "Object type"],
  title: ["标题", "Title"],
  summary: ["摘要", "Summary"],
  status: ["状态", "Status"],
  employee_id: ["员工", "Employee"],
  booked_by_employee_id: ["预订人", "Booked by"],
  resource_id: ["资源 ID", "Resource ID"],
  booking_type: ["预订类型", "Booking type"],
  period_start: ["周期开始", "Period start"],
  period_end: ["周期结束", "Period end"],
  claim_date: ["报销日期", "Claim date"],
  request_date: ["申请日期", "Request date"],
  needed_by: ["期望到货", "Needed by"],
  vendor_id: ["供应商 ID", "Vendor ID"],
  vendor_name_snapshot: ["供应商", "Vendor"],
  quote_number: ["报价单号", "Quote number"],
  revision_no: ["修订版本", "Revision"],
  revision_of_id: ["修订自", "Revision of"],
  customer_id: ["客户 ID", "Customer ID"],
  customer_name_snapshot: ["客户", "Customer"],
  contact_name: ["联系人", "Contact"],
  contact_phone: ["联系电话", "Contact phone"],
  contact_email: ["联系邮箱", "Contact email"],
  quote_date: ["报价日期", "Quote date"],
  valid_until: ["有效期至", "Valid until"],
  payment_terms: ["付款条款", "Payment terms"],
  delivery_terms: ["交付条款", "Delivery terms"],
  remarks: ["备注", "Remarks"],
  sent_at: ["发送时间", "Sent at"],
  closed_at: ["关闭时间", "Closed at"],
  outcome_note: ["成交/流失说明", "Outcome note"],
  order_no: ["订单号", "Order no."],
  order_date: ["下单日期", "Order date"],
  promised_date: ["承诺交期", "Promised date"],
  quotation_id: ["成交报价 ID", "Won quotation ID"],
  source_quote_number: ["成交报价单号", "Won quote no."],
  contract_no: ["合同号", "Contract no."],
  logistics_company: ["物流公司", "Carrier"],
  logistics_tracking_no: ["物流单号", "Tracking no."],
  ship_to_address: ["收货地址", "Ship-to address"],
  shipped_at: ["发货时间", "Shipped at"],
  signed_at: ["签收时间", "Signed at"],
  project_id: ["项目 ID", "Project ID"],
  total_amount: ["单据总额", "Total amount"],
  currency: ["币种", "Currency"],
  start_at: ["开始时间", "Start time"],
  end_at: ["结束时间", "End time"],
  quantity: ["数量", "Quantity"],
  notes: ["备注", "Notes"],
  source_text: ["来源文本", "Source text"],
  source_report_text: ["来源报告", "Source report"],
  submitted_at: ["提交时间", "Submitted at"],
  created_by: ["创建者", "Created by"],
  created_at: ["创建时间", "Created at"],
  updated_at: ["更新时间", "Updated at"],
  deleted_at: ["删除时间", "Deleted at"],
  deleted_by: ["删除者", "Deleted by"],
  delete_reason: ["删除原因", "Deletion reason"],
  cancelled_at: ["取消时间", "Cancelled at"],
  cancelled_by: ["取消者", "Cancelled by"],
  cancel_reason: ["取消原因", "Cancellation reason"],
};

const JSON_FIELDS = new Set(["payload", "custom_fields", "metadata"]);

function Section({ title, count, description, children, className = "" }: {
  title: string;
  count?: number;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`data-panel object-detail-section ${className}`}>
      <header className="object-section-header">
        <div><h3>{title}{count !== undefined && <span>{count}</span>}</h3>{description && <p>{description}</p>}</div>
      </header>
      {children}
    </section>
  );
}

function EmptySection({ children }: { children: ReactNode }) {
  return <div className="object-section-empty"><span aria-hidden="true">∅</span><p>{children}</p></div>;
}

function isDateKey(key: string): boolean {
  return key.endsWith("_at") || key.endsWith("_date") || key === "period_start" || key === "period_end" || key === "needed_by" || key === "valid_until";
}

function fieldLabel(key: string, text: LocalText): string {
  return FIELD_LABELS[key] ? text(...FIELD_LABELS[key]) : key;
}

function displayValue(key: string, value: unknown, detail: ObjectDetail, text: LocalText, locale: string): ReactNode {
  if (value == null || value === "") return <span className="muted-value">—</span>;
  if (key === "status" && typeof value === "string") return <ObjectStatus status={value} translate={detail.entityKind === "builtin"} />;
  if (typeof value === "string") {
    if (key === "employee_id" || key === "booked_by_employee_id") {
      return <><strong>{detail.employees[value] || value}</strong>{detail.employees[value] && <small className="object-inline-id">{value}</small>}</>;
    }
    if (key === "created_by" || key === "deleted_by" || key === "cancelled_by") {
      return detail.actors[value] || value;
    }
    if (isDateKey(key)) return key.endsWith("_at") ? formatDateTime(value, locale) : formatDate(value, locale);
    return value;
  }
  if (typeof value === "boolean") return value ? text("是", "Yes") : text("否", "No");
  if (typeof value === "object") return <code>{JSON.stringify(value)}</code>;
  return String(value);
}

export function ObjectRecordDetail({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  const record = detail.subject.record as unknown as Record<string, unknown>;
  const fields = Object.entries(record).filter(([key]) => !JSON_FIELDS.has(key));
  const jsonFields = Object.entries(record).filter(([key]) => JSON_FIELDS.has(key));
  return (
    <Section title={text("记录信息", "Record information")} className="object-record-detail">
      <dl className="object-kv-grid">
        {fields.map(([key, value]) => <div key={key}>
          <dt>{fieldLabel(key, text)}</dt>
          <dd>{displayValue(key, value, detail, text, language)}</dd>
        </div>)}
      </dl>
      {jsonFields.map(([key, value]) => (
        <details className="object-json-block" key={key} open={Boolean(value && Object.keys(value as object).length)}>
          <summary>{fieldLabel(key, text)}</summary>
          <pre>{JSON.stringify(value, null, 2)}</pre>
        </details>
      ))}
    </Section>
  );
}

function variantSummary(attributes: Record<string, unknown>): string {
  return Object.entries(attributes)
    .map(([key, value]) => `${key}：${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(" · ");
}

function AttachmentDownload(
  { detail, attachmentId }: { detail: ObjectDetail; attachmentId: string | null | undefined },
) {
  const { text } = useI18n();
  if (!attachmentId) return <>—</>;
  const href = attachmentContentUrl(detail.entityType, detail.subject.record.id, attachmentId);
  if (!href) return <>—</>;
  return <a className="text-action" href={href}>{text("下载", "Download")}</a>;
}

function AttachmentTable({ detail, attachments }: { detail: ObjectDetail; attachments: Attachment[] }) {
  const { language, text } = useI18n();
  if (attachments.length === 0) return <EmptySection>{text("没有关联附件。", "No related attachments.")}</EmptySection>;
  return (
    <div className="table-scroll"><table className="data-table object-detail-table">
      <thead><tr><th>{text("文件名", "File name")}</th><th>{text("类型", "Type")}</th><th>{text("大小", "Size")}</th><th>SHA-256</th><th>{text("上传时间", "Uploaded")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
      <tbody>{attachments.map((attachment) => <tr key={attachment.id}>
        <td><strong>{attachment.filename}</strong></td>
        <td>{attachment.content_type}</td>
        <td>{(attachment.size_bytes / 1024).toFixed(1)} KB</td>
        <td className="mono-cell">{attachment.sha256.slice(0, 12)}…</td>
        <td>{formatDateTime(attachment.created_at, language)}</td>
        <td className="row-actions"><AttachmentDownload detail={detail} attachmentId={attachment.id} /></td>
      </tr>)}</tbody>
    </table></div>
  );
}

function TimesheetLines({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  if (detail.entityType !== "timesheet_header") return null;
  return <Section title={text("工时行", "Timesheet entries")} count={detail.timesheetEntries.length}>
    {detail.timesheetEntries.length === 0 ? <EmptySection>{text("这张工时单还没有工时行。", "This timesheet has no entries yet.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text("日期", "Date")}</th><th>{text("项目", "Project")}</th><th>{text("客户", "Customer")}</th><th>{text("任务", "Task")}</th><th>{text("工时", "Hours")}</th><th>{text("类型", "Type")}</th><th>{text("备注", "Notes")}</th></tr></thead>
        <tbody>{detail.timesheetEntries.map((entry) => <tr key={entry.id}>
          <td>{formatDate(entry.work_date, language)}</td><td>{entry.project_name_snapshot || entry.project_id || "—"}</td>
          <td>{entry.client || "—"}</td><td>{entry.task || "—"}</td><td><strong>{entry.hours}</strong></td>
          <td>{entry.work_type}</td><td>{entry.notes || "—"}</td>
        </tr>)}</tbody>
      </table></div>}
  </Section>;
}

function ExpenseLines({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  if (detail.entityType !== "expense_claim") return null;
  const record = detail.subject.entityType === "expense_claim" ? detail.subject.record : null;
  const currency = record?.currency || "CNY";
  return <>
    <Section title={text("报销行", "Expense items")} count={detail.expenseItems.length}>
      {detail.expenseItems.length === 0 ? <EmptySection>{text("这张报销单还没有费用行。", "This expense claim has no expense items yet.")}</EmptySection> :
        <div className="table-scroll"><table className="data-table object-detail-table">
          <thead><tr><th>{text("日期", "Date")}</th><th>{text("类别", "Category")}</th><th>{text("商户", "Merchant")}</th><th>{text("供应商", "Vendor")}</th><th>{text("金额", "Amount")}</th><th>{text("税额", "Tax")}</th><th>{text("发票号", "Invoice no.")}</th><th>{text("项目", "Project")}</th><th>{text("票据", "Receipt")}</th><th>{text("备注", "Notes")}</th></tr></thead>
          <tbody>{detail.expenseItems.map((item) => <tr key={item.id}>
            <td>{formatDate(item.expense_date, language)}</td><td>{item.category}</td><td>{item.merchant || "—"}</td>
            <td>{item.vendor_name || item.vendor_id || "—"}</td>
            <td><strong>{formatMoney(item.amount, currency, language)}</strong></td><td>{formatMoney(item.tax_amount, currency, language)}</td>
            <td className="mono-cell">{item.invoice_number || "—"}</td><td>{item.project_name_snapshot || item.project_id || "—"}</td>
            <td>{item.attachment_id ? <AttachmentDownload detail={detail} attachmentId={item.attachment_id} /> : "—"}</td>
            <td>{item.notes || "—"}</td>
          </tr>)}</tbody>
          {detail.expenseTotals && <tfoot><tr><td colSpan={4}>{text("合计", "Total")}</td><td><strong>{formatMoney(detail.expenseTotals.totalAmount, currency, language)}</strong></td><td>{formatMoney(detail.expenseTotals.totalTaxAmount, currency, language)}</td><td colSpan={4} /></tr></tfoot>}
        </table></div>}
    </Section>
    <Section title={text("票据附件", "Receipt attachments")} count={detail.attachments.length}><AttachmentTable detail={detail} attachments={detail.attachments} /></Section>
  </>;
}

function PurchaseLines({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  if (detail.entityType !== "purchase_request") return null;
  const record = detail.subject.entityType === "purchase_request" ? detail.subject.record : null;
  const currency = record?.currency || "CNY";
  return <>
    <Section title={text("采购行", "Purchase items")} count={detail.purchaseItems.length}>
      {detail.purchaseItems.length === 0 ? <EmptySection>{text("这张采购申请还没有采购行。", "This purchase request has no items yet.")}</EmptySection> :
        <div className="table-scroll"><table className="data-table object-detail-table">
          <thead><tr><th>{text("产品", "Product")}</th><th>SKU</th><th>{text("规格", "Specification")}</th><th>{text("数量", "Quantity")}</th><th>{text("单位", "Unit")}</th><th>{text("单价", "Unit price")}</th><th>{text("金额", "Amount")}</th><th>{text("报价单", "Quote")}</th><th>{text("备注", "Notes")}</th></tr></thead>
          <tbody>{detail.purchaseItems.map((item) => {
            const estimated = item.amount ?? (item.unit_price == null ? null : item.unit_price * item.quantity);
            return <tr key={item.id}>
              <td><strong>{item.product?.name || item.product_name_snapshot || "—"}</strong>{item.product?.product_code && <small>{item.product.product_code}</small>}{item.product_id && <small className="object-inline-id">{item.product_id}</small>}</td>
              <td>{item.sku ? <><strong className="mono-cell">{item.sku.sku_code || item.sku.id}</strong>{Object.keys(item.sku.variant_attrs).length > 0 && <small className="object-variant-list">{variantSummary(item.sku.variant_attrs)}</small>}</> : !item.sku_id && item.sku_pending ? <span className="object-pending-sku">{text("SKU 待定", "SKU pending")}</span> : item.sku_id ? <><span className="mono-cell">{item.sku_id}</span><small>{text("SKU 目录信息不可用", "SKU catalog information unavailable")}</small></> : "—"}</td><td>{item.spec || item.product?.spec || "—"}</td><td>{item.quantity}</td><td>{item.unit || item.product?.unit || "—"}</td>
              <td>{formatMoney(item.unit_price, currency, language)}</td><td><strong>{formatMoney(estimated, currency, language)}</strong></td>
              <td>{item.attachment_id ? <AttachmentDownload detail={detail} attachmentId={item.attachment_id} /> : "—"}</td>
              <td>{item.notes || "—"}</td>
            </tr>;
          })}</tbody>
          {detail.purchaseTotals && <tfoot><tr><td colSpan={6}>{text("预估合计", "Estimated total")}</td><td><strong>{formatMoney(detail.purchaseTotals.estimatedTotal, currency, language)}</strong><small>{detail.purchaseTotals.unpricedItemCount > 0 && text(`另有 ${detail.purchaseTotals.unpricedItemCount} 行未报价`, `${detail.purchaseTotals.unpricedItemCount} additional unpriced items`)}{detail.purchaseTotals.pendingSkuCount > 0 && text(` · ${detail.purchaseTotals.pendingSkuCount} 行 SKU 待定`, ` · ${detail.purchaseTotals.pendingSkuCount} SKUs pending`)}</small></td><td colSpan={2} /></tr></tfoot>}
        </table></div>}
    </Section>
    <Section title={text("报价单附件", "Quote attachments")} count={detail.attachments.length}><AttachmentTable detail={detail} attachments={detail.attachments} /></Section>
  </>;
}

function SalesQuotationLines({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  if (detail.entityType !== "sales_quotation") return null;
  const record = detail.subject.entityType === "sales_quotation" ? detail.subject.record : null;
  const currency = record?.currency || "CNY";
  const documentTotal = record?.total_amount ?? null;
  const totals = detail.salesQuotationTotals;
  return <>
    <Section title={text("报价行", "Quotation lines")} count={detail.salesQuotationItems.length}>
      {detail.salesQuotationItems.length === 0 ? <EmptySection>{text("这张报价单还没有报价行。", "This quotation has no lines yet.")}</EmptySection> :
        <div className="table-scroll"><table className="data-table object-detail-table">
          <thead><tr><th>{text("产品", "Product")}</th><th>SKU</th><th>{text("规格", "Specification")}</th><th>{text("数量", "Quantity")}</th><th>{text("单位", "Unit")}</th><th>{text("目录价", "List price")}</th><th>{text("单价", "Unit price")}</th><th>{text("税率", "Tax rate")}</th><th>{text("金额", "Amount")}</th><th>{text("交期", "Lead time")}</th><th>{text("备注", "Notes")}</th></tr></thead>
          <tbody>{detail.salesQuotationItems.map((item) => {
            const lineTotal = item.is_gift ? 0 : (item.amount ?? (item.unit_price == null ? null : item.unit_price * item.quantity));
            return <tr key={item.id}>
              <td><strong>{item.product?.name || item.product_name_snapshot || "—"}</strong>{item.is_gift && <small className="object-gift-tag">{text("赠品", "Gift")}</small>}{item.product?.product_code && <small>{item.product.product_code}</small>}{item.product_id && <small className="object-inline-id">{item.product_id}</small>}</td>
              <td>{item.sku ? <><strong className="mono-cell">{item.sku.sku_code || item.sku.id}</strong>{Object.keys(item.sku.variant_attrs).length > 0 && <small className="object-variant-list">{variantSummary(item.sku.variant_attrs)}</small>}</> : !item.sku_id && item.sku_pending ? <span className="object-pending-sku">{text("SKU 待定", "SKU pending")}</span> : item.sku_id ? <><span className="mono-cell">{item.sku_id}</span><small>{text("SKU 目录信息不可用", "SKU catalog information unavailable")}</small></> : "—"}</td><td>{item.spec || item.product?.spec || "—"}</td><td>{item.quantity}</td><td>{item.unit || item.product?.unit || "—"}</td>
              <td>{formatMoney(item.list_price_snapshot, currency, language)}</td><td>{item.is_gift ? text("赠品", "Gift") : formatMoney(item.unit_price, currency, language)}</td><td>{item.tax_rate == null ? "—" : `${item.tax_rate}%`}</td><td><strong>{formatMoney(lineTotal, currency, language)}</strong></td>
              <td>{item.lead_time || "—"}</td>
              <td>{item.notes || "—"}</td>
            </tr>;
          })}</tbody>
          {totals && <tfoot>
            <tr><td colSpan={8}>{text("报价合计", "Line total")}</td><td><strong>{formatMoney(totals.computedTotal, currency, language)}</strong>{(totals.unpricedItemCount > 0 || totals.pendingSkuCount > 0) && <small>{totals.unpricedItemCount > 0 && text(`另有 ${totals.unpricedItemCount} 行未报价`, `${totals.unpricedItemCount} unpriced lines`)}{totals.pendingSkuCount > 0 && text(` · ${totals.pendingSkuCount} 行 SKU 待定`, ` · ${totals.pendingSkuCount} SKUs pending`)}</small>}</td><td colSpan={2} /></tr>
            {documentTotal != null && <tr><td colSpan={8}>{text("文档总额", "Document total")}</td><td><strong>{formatMoney(documentTotal, currency, language)}</strong>{Math.abs(documentTotal - totals.computedTotal) > 0.005 && <small>{text("与行合计不一致（抹零 / 整单议价）", "Differs from line total (rounding / negotiated)")}</small>}</td><td colSpan={2} /></tr>}
          </tfoot>}
        </table></div>}
    </Section>
    <Section title={text("报价单附件", "Quotation attachments")} count={detail.attachments.length}><AttachmentTable detail={detail} attachments={detail.attachments} /></Section>
  </>;
}

function SalesQuotationRevisions({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  if (detail.entityType !== "sales_quotation") return null;
  const currentId = detail.subject.record.id;
  const revisions = [...detail.revisions].sort((left, right) => right.revision_no - left.revision_no);
  return <Section title={text("修订链", "Revision chain")} count={revisions.length} description={text("同一报价单号下的所有修订版本，最新在前；被替代版本作为不可变事实保留。", "All revisions under the same quote number, newest first; superseded revisions remain as immutable facts.")}>
    {revisions.length === 0 ? <EmptySection>{text("这张报价单还没有其他修订版本。", "This quotation has no other revisions yet.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text("版本", "Revision")}</th><th>{text("状态", "Status")}</th><th>{text("报价日期", "Quote date")}</th><th>{text("有效期至", "Valid until")}</th><th>{text("总额", "Total")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
        <tbody>{revisions.map((revision) => <tr key={revision.id}>
          <td><strong>{text(`第 ${revision.revision_no} 版`, `Rev ${revision.revision_no}`)}</strong>{revision.id === currentId && <small>{text("当前查看", "Viewing")}</small>}</td>
          <td><ObjectStatus status={revision.status} /></td>
          <td>{formatDate(revision.quote_date, language)}</td>
          <td>{formatDate(revision.valid_until, language)}</td>
          <td>{formatMoney(revision.total_amount, revision.currency, language)}</td>
          <td className="row-actions">{revision.id === currentId ? <span className="muted-value">{text("本版", "This one")}</span> : <Link className="text-action" to={`/objects/sales_quotation/${encodeURIComponent(revision.id)}?kind=builtin&object_type=sales_quotation`}>{text("查看", "View")}</Link>}</td>
        </tr>)}</tbody>
      </table></div>}
  </Section>;
}

function SalesOrderLines({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  if (detail.entityType !== "sales_order") return null;
  const record = detail.subject.entityType === "sales_order" ? detail.subject.record : null;
  const currency = record?.currency || "CNY";
  const documentTotal = record?.total_amount ?? null;
  const totals = detail.salesOrderTotals;
  return <>
    <Section title={text("订单行", "Order lines")} count={detail.salesOrderItems.length}>
      {detail.salesOrderItems.length === 0 ? <EmptySection>{text("这张销售订单还没有订单行。", "This order has no lines yet.")}</EmptySection> :
        <div className="table-scroll"><table className="data-table object-detail-table">
          <thead><tr><th>{text("产品", "Product")}</th><th>SKU</th><th>{text("规格", "Specification")}</th><th>{text("数量", "Quantity")}</th><th>{text("单位", "Unit")}</th><th>{text("目录价", "List price")}</th><th>{text("单价", "Unit price")}</th><th>{text("税率", "Tax rate")}</th><th>{text("金额", "Amount")}</th><th>{text("承诺交期", "Promised")}</th><th>{text("备注", "Notes")}</th></tr></thead>
          <tbody>{detail.salesOrderItems.map((item) => {
            const lineTotal = item.is_gift ? 0 : (item.amount ?? (item.unit_price == null ? null : item.unit_price * item.quantity));
            return <tr key={item.id}>
              <td><strong>{item.product?.name || item.product_name_snapshot || "—"}</strong>{item.is_gift && <small className="object-gift-tag">{text("赠品", "Gift")}</small>}{item.product?.product_code && <small>{item.product.product_code}</small>}{item.product_id && <small className="object-inline-id">{item.product_id}</small>}</td>
              <td>{item.sku ? <><strong className="mono-cell">{item.sku.sku_code || item.sku.id}</strong>{Object.keys(item.sku.variant_attrs).length > 0 && <small className="object-variant-list">{variantSummary(item.sku.variant_attrs)}</small>}</> : !item.sku_id && item.sku_pending ? <span className="object-pending-sku">{text("SKU 待定", "SKU pending")}</span> : item.sku_id ? <><span className="mono-cell">{item.sku_id}</span><small>{text("SKU 目录信息不可用", "SKU catalog information unavailable")}</small></> : "—"}</td><td>{item.spec || item.product?.spec || "—"}</td><td>{item.quantity}</td><td>{item.unit || item.product?.unit || "—"}</td>
              <td>{formatMoney(item.list_price_snapshot, currency, language)}</td><td>{item.is_gift ? text("赠品", "Gift") : formatMoney(item.unit_price, currency, language)}</td><td>{item.tax_rate == null ? "—" : `${item.tax_rate}%`}</td><td><strong>{formatMoney(lineTotal, currency, language)}</strong></td>
              <td>{formatDate(item.promised_date, language)}</td>
              <td>{item.notes || "—"}</td>
            </tr>;
          })}</tbody>
          {totals && <tfoot>
            <tr><td colSpan={8}>{text("订单合计", "Line total")}</td><td><strong>{formatMoney(totals.computedTotal, currency, language)}</strong>{(totals.unpricedItemCount > 0 || totals.pendingSkuCount > 0) && <small>{totals.unpricedItemCount > 0 && text(`另有 ${totals.unpricedItemCount} 行未报价`, `${totals.unpricedItemCount} unpriced lines`)}{totals.pendingSkuCount > 0 && text(` · ${totals.pendingSkuCount} 行 SKU 待定`, ` · ${totals.pendingSkuCount} SKUs pending`)}</small>}</td><td colSpan={2} /></tr>
            {documentTotal != null && <tr><td colSpan={8}>{text("文档总额", "Document total")}</td><td><strong>{formatMoney(documentTotal, currency, language)}</strong>{Math.abs(documentTotal - totals.computedTotal) > 0.005 && <small>{text("与行合计不一致（抹零 / 整单议价）", "Differs from line total (rounding / negotiated)")}</small>}</td><td colSpan={2} /></tr>}
          </tfoot>}
        </table></div>}
    </Section>
    <Section title={text("订单附件", "Order attachments")} count={detail.attachments.length}><AttachmentTable detail={detail} attachments={detail.attachments} /></Section>
  </>;
}

function SalesOrderQuotationLink({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  if (detail.entityType !== "sales_order") return null;
  const order = detail.subject.entityType === "sales_order" ? detail.subject.record : null;
  const quotation = detail.quotationLink;
  return <Section
    title={text("成交报价", "Won quotation")}
    description={text("订单回链的中标报价，是报价到订单转化的不可变来源事实。", "The won quotation this order was converted from — the immutable source fact of the quote-to-order handoff.")}
  >
    {!quotation
      ? <EmptySection>{order?.source_quote_number
          ? text(`订单记录了成交报价单号 ${order.source_quote_number}，但没有回链到具体报价记录。`, `The order records won quote no. ${order.source_quote_number}, but no linked quotation record is available.`)
          : text("这张订单没有回链的成交报价（可能是直接下单）。", "This order has no linked won quotation (it may have been created directly).")}</EmptySection>
      : <dl className="object-kv-grid">
          <div><dt>{text("报价单号", "Quote no.")}</dt><dd><Link className="text-action mono-cell" to={`/objects/sales_quotation/${encodeURIComponent(quotation.id)}?kind=builtin&object_type=sales_quotation`}>{quotation.quote_number}</Link>{quotation.revision_no > 1 && <small className="object-inline-id">{text(`第 ${quotation.revision_no} 版`, `Rev ${quotation.revision_no}`)}</small>}</dd></div>
          <div><dt>{text("事由", "Reason")}</dt><dd>{quotation.title}</dd></div>
          <div><dt>{text("客户", "Customer")}</dt><dd>{quotation.customer_name_snapshot || "—"}</dd></div>
          <div><dt>{text("状态", "Status")}</dt><dd><ObjectStatus status={quotation.status} /></dd></div>
          <div><dt>{text("报价总额", "Quote total")}</dt><dd>{formatMoney(quotation.total_amount, quotation.currency, language)}</dd></div>
          <div><dt>{text("有效期至", "Valid until")}</dt><dd>{formatDate(quotation.valid_until, language)}</dd></div>
        </dl>}
  </Section>;
}

function BusinessObjectLinks({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  if (detail.entityType !== "business_object") return null;
  return <Section title={text("关联对象", "Related objects")} count={detail.links.length} description={text("同时汇总以本对象为源和目标的关联，重复关联按 ID 去重。", "Includes relationships where this object is either the source or target, deduplicated by ID.")}>
    {detail.links.length === 0 ? <EmptySection>{text("这条业务对象还没有建立关联。", "This business object has no relationships yet.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text("关联类型", "Relationship type")}</th><th>{text("源对象", "Source object")}</th><th>{text("目标对象", "Target object")}</th><th>{text("元数据", "Metadata")}</th><th>{text("创建时间", "Created")}</th></tr></thead>
        <tbody>{detail.links.map((link) => <tr key={link.id}>
          <td><code>{link.link_type}</code></td>
          <td>{link.source_object_id === detail.subject.record.id ? <span className="muted-value">{text("本对象", "This object")}</span> : <Link className="text-action mono-cell" to={`/objects/business_object/${encodeURIComponent(link.source_object_id)}`}>{link.source_object_id}</Link>}</td>
          <td>{link.target_object_id === detail.subject.record.id ? <span className="muted-value">{text("本对象", "This object")}</span> : <Link className="text-action mono-cell" to={`/objects/business_object/${encodeURIComponent(link.target_object_id)}`}>{link.target_object_id}</Link>}</td>
          <td>{Object.keys(link.metadata).length ? <details><summary>{text("查看", "View")}</summary><pre>{JSON.stringify(link.metadata, null, 2)}</pre></details> : "—"}</td>
          <td>{formatDateTime(link.created_at, language)}</td>
        </tr>)}</tbody>
      </table></div>}
  </Section>;
}

function WorkflowHistory({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  return <Section title={text(`${detail.objectType} 流程版本`, `${detail.objectType} workflow versions`)} count={detail.workflows.length} description={text("启用版本供当前流程使用；被替代版本继续保留，便于追溯历史决策。", "The active version is used by the current workflow; superseded versions remain available for historical traceability.")}>
    {detail.workflows.length === 0 ? <EmptySection>{text("该类型还没有发布流程定义。", "No workflow definition has been published for this type.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text("名称", "Name")}</th><th>{text("版本", "Version")}</th><th>{text("状态", "Status")}</th><th>{text("定义", "Definition")}</th><th>{text("发布者", "Published by")}</th><th>{text("发布时间", "Published")}</th></tr></thead>
        <tbody>{detail.workflows.map((workflow) => <tr key={workflow.id}>
          <td><strong>{workflow.name}</strong></td><td><span className="object-version">v{workflow.version}</span></td>
          <td><ObjectStatus status={workflow.status} /></td>
          <td><details><summary>{text("查看定义", "View definition")}</summary><pre className="object-definition">{workflow.definition_text}</pre></details></td>
          <td>{workflow.created_by ? detail.actors[workflow.created_by] || workflow.created_by : "—"}</td><td>{formatDateTime(workflow.created_at, language)}</td>
        </tr>)}</tbody>
      </table></div>}
  </Section>;
}

function ApprovalHistory({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  return <Section title={text("审批记录", "Approval history")} count={detail.approvals.length} description={text("按轮次、步骤和操作时间排列。", "Ordered by round, step, and action time.")}>
    {detail.approvals.length === 0 ? <EmptySection>{text("还没有审批活动。", "No approval activity yet.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text("轮次", "Round")}</th><th>{text("步骤", "Step")}</th><th>{text("动作", "Action")}</th><th>{text("操作者", "Actor")}</th><th>{text("角色", "Role")}</th><th>{text("备注", "Comment")}</th><th>{text("时间", "Time")}</th></tr></thead>
        <tbody>{detail.approvals.map((approval) => <tr key={approval.id}>
          <td>{approval.round_no}</td><td>{approval.sequence_no}</td><td><ObjectStatus status={approval.action} /></td>
          <td>{approval.approver_id ? detail.actors[approval.approver_id] || approval.approver_id : "—"}</td>
          <td>{approval.approver_role || "—"}</td><td>{approval.comment || "—"}</td><td>{formatDateTime(approval.acted_at, language)}</td>
        </tr>)}</tbody>
      </table></div>}
  </Section>;
}

function TodoHistory({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  return <Section title={text("待办", "Todos")} count={detail.todos.length}>
    {detail.todos.length === 0 ? <EmptySection>{text("没有待办引用这条记录。", "No todos reference this record.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text("标题", "Title")}</th><th>{text("负责人", "Assignee")}</th><th>{text("类型", "Type")}</th><th>{text("状态", "Status")}</th><th>{text("截止时间", "Due")}</th><th>{text("完成信息", "Completion")}</th></tr></thead>
        <tbody>{detail.todos.map((todo) => <tr key={todo.id}>
          <td><strong>{todo.title}</strong>{todo.description && <small>{todo.description}</small>}</td>
          <td>{detail.employees[todo.employee_id] || todo.employee_id}</td><td>{todo.todo_type || "—"}</td>
          <td><ObjectStatus status={todo.status} /></td><td>{formatDateTime(todo.due_at, language)}</td>
          <td>{todo.completed_at ? <>{formatDateTime(todo.completed_at, language)}{todo.completed_by && <small>{detail.actors[todo.completed_by] || todo.completed_by}</small>}</> : "—"}</td>
        </tr>)}</tbody>
      </table></div>}
  </Section>;
}

function AuditHistory({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  return <Section title={text("审计轨迹", "Audit trail")} count={detail.audits.length}>
    {detail.audits.length === 0 ? <EmptySection>{text("没有可用的审计记录。", "No audit records are available.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text("时间", "Time")}</th><th>{text("动作", "Action")}</th><th>{text("操作者", "Actor")}</th><th>{text("详情", "Details")}</th></tr></thead>
        <tbody>{detail.audits.map((audit) => <tr key={audit.id}>
          <td>{formatDateTime(audit.created_at, language)}</td><td><code>{audit.action}</code></td>
          <td>{audit.actor ? detail.actors[audit.actor] || audit.actor : "—"}</td>
          <td>{Object.keys(audit.detail || {}).length ? <details><summary>{text("查看", "View")}</summary><pre>{JSON.stringify(audit.detail, null, 2)}</pre></details> : "—"}</td>
        </tr>)}</tbody>
      </table></div>}
  </Section>;
}

export function ObjectDetailSections({ detail }: { detail: ObjectDetail }) {
  return <>
    <TimesheetLines detail={detail} />
    <ExpenseLines detail={detail} />
    <PurchaseLines detail={detail} />
    <SalesQuotationLines detail={detail} />
    <SalesQuotationRevisions detail={detail} />
    <SalesOrderLines detail={detail} />
    <SalesOrderQuotationLink detail={detail} />
    <BusinessObjectLinks detail={detail} />
    <WorkflowHistory detail={detail} />
    <ApprovalHistory detail={detail} />
    <TodoHistory detail={detail} />
    <AuditHistory detail={detail} />
  </>;
}
