import { zhCN } from "../../locales/zh-CN/console";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  attachmentContentUrl,
  type Attachment,
  type ObjectDetail,
} from "../../api/objects";
import { useI18n } from "../../i18n";
import { ruleKindLabel } from "../rules";
import { formatDate, formatDateTime, formatMoney, ObjectStatus } from "./ObjectRecordTable";

type LocalText = (chinese: string, english: string) => string;

const FIELD_LABELS: Record<string, [string, string]> = {
  id: [zhCN.componentsObjectsObjectDetailSections.message, "Record ID"],
  object_type: [zhCN.componentsObjectsObjectDetailSections.objectType, "Object type"],
  title: [zhCN.componentsObjectsObjectDetailSections.title, "Title"],
  summary: [zhCN.componentsObjectsObjectDetailSections.summary, "Summary"],
  status: [zhCN.componentsObjectsObjectDetailSections.status, "Status"],
  employee_id: [zhCN.componentsObjectsObjectDetailSections.employee, "Employee"],
  booked_by_employee_id: [zhCN.componentsObjectsObjectDetailSections.bookedBy, "Booked by"],
  resource_id: [zhCN.componentsObjectsObjectDetailSections.message8, "Resource ID"],
  booking_type: [zhCN.componentsObjectsObjectDetailSections.message9, "Booking type"],
  period_start: [zhCN.componentsObjectsObjectDetailSections.message10, "Period start"],
  period_end: [zhCN.componentsObjectsObjectDetailSections.message11, "Period end"],
  claim_date: [zhCN.componentsObjectsObjectDetailSections.claimDate, "Claim date"],
  request_date: [zhCN.componentsObjectsObjectDetailSections.message13, "Request date"],
  needed_by: [zhCN.componentsObjectsObjectDetailSections.neededBy, "Needed by"],
  vendor_id: [zhCN.componentsObjectsObjectDetailSections.message15, "Vendor ID"],
  vendor_name_snapshot: [zhCN.componentsObjectsObjectDetailSections.vendor, "Vendor"],
  quote_number: [zhCN.componentsObjectsObjectDetailSections.quoteNo, "Quote number"],
  revision_no: [zhCN.componentsObjectsObjectDetailSections.message18, "Revision"],
  revision_of_id: [zhCN.componentsObjectsObjectDetailSections.message19, "Revision of"],
  customer_id: [zhCN.componentsObjectsObjectDetailSections.message20, "Customer ID"],
  customer_name_snapshot: [zhCN.componentsObjectsObjectDetailSections.customer, "Customer"],
  contact_name: [zhCN.componentsObjectsObjectDetailSections.contact, "Contact"],
  contact_phone: [zhCN.componentsObjectsObjectDetailSections.message23, "Contact phone"],
  contact_email: [zhCN.componentsObjectsObjectDetailSections.message24, "Contact email"],
  quote_date: [zhCN.componentsObjectsObjectDetailSections.quoteDate, "Quote date"],
  valid_until: [zhCN.componentsObjectsObjectDetailSections.validUntil, "Valid until"],
  payment_terms: [zhCN.componentsObjectsObjectDetailSections.message27, "Payment terms"],
  delivery_terms: [zhCN.componentsObjectsObjectDetailSections.message28, "Delivery terms"],
  remarks: [zhCN.componentsObjectsObjectDetailSections.comment, "Remarks"],
  sent_at: [zhCN.componentsObjectsObjectDetailSections.message30, "Sent at"],
  closed_at: [zhCN.componentsObjectsObjectDetailSections.message31, "Closed at"],
  outcome_note: [zhCN.componentsObjectsObjectDetailSections.message32, "Outcome note"],
  order_no: [zhCN.componentsObjectsObjectDetailSections.name8, "Order no."],
  order_date: [zhCN.componentsObjectsObjectDetailSections.message34, "Order date"],
  promised_date: [zhCN.componentsObjectsObjectDetailSections.promised, "Promised date"],
  quotation_id: [zhCN.componentsObjectsObjectDetailSections.message36, "Won quotation ID"],
  source_quote_number: [zhCN.componentsObjectsObjectDetailSections.message37, "Won quote no."],
  contract_no: [zhCN.componentsObjectsObjectDetailSections.message38, "Contract no."],
  logistics_company: [zhCN.componentsObjectsObjectDetailSections.message39, "Carrier"],
  logistics_tracking_no: [zhCN.componentsObjectsObjectDetailSections.trackingNo, "Tracking no."],
  ship_to_address: [zhCN.componentsObjectsObjectDetailSections.message41, "Ship-to address"],
  shipped_at: [zhCN.componentsObjectsObjectDetailSections.message42, "Shipped at"],
  signed_at: [zhCN.componentsObjectsObjectDetailSections.message43, "Signed at"],
  project_id: [zhCN.componentsObjectsObjectDetailSections.message44, "Project ID"],
  total_amount: [zhCN.componentsObjectsObjectDetailSections.message45, "Total amount"],
  currency: [zhCN.componentsObjectsObjectDetailSections.currency, "Currency"],
  start_at: [zhCN.componentsObjectsObjectDetailSections.started, "Start time"],
  end_at: [zhCN.componentsObjectsObjectDetailSections.message48, "End time"],
  quantity: [zhCN.componentsObjectsObjectDetailSections.quantity, "Quantity"],
  notes: [zhCN.componentsObjectsObjectDetailSections.comment, "Notes"],
  source_text: [zhCN.componentsObjectsObjectDetailSections.message50, "Source text"],
  source_report_text: [zhCN.componentsObjectsObjectDetailSections.message51, "Source report"],
  submitted_at: [zhCN.componentsObjectsObjectDetailSections.submitted, "Submitted at"],
  created_by: [zhCN.componentsObjectsObjectDetailSections.createdBy, "Created by"],
  created_at: [zhCN.componentsObjectsObjectDetailSections.created, "Created at"],
  updated_at: [zhCN.componentsObjectsObjectDetailSections.updated, "Updated at"],
  deleted_at: [zhCN.componentsObjectsObjectDetailSections.message56, "Deleted at"],
  deleted_by: [zhCN.componentsObjectsObjectDetailSections.message57, "Deleted by"],
  delete_reason: [zhCN.componentsObjectsObjectDetailSections.message58, "Deletion reason"],
  cancelled_at: [zhCN.componentsObjectsObjectDetailSections.message59, "Cancelled at"],
  cancelled_by: [zhCN.componentsObjectsObjectDetailSections.message60, "Cancelled by"],
  cancel_reason: [zhCN.componentsObjectsObjectDetailSections.message61, "Cancellation reason"],
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
  if (typeof value === "boolean") return value ? text(zhCN.componentsObjectsObjectDetailSections.yes, "Yes") : text(zhCN.componentsObjectsObjectDetailSections.no, "No");
  if (typeof value === "object") return <code>{JSON.stringify(value)}</code>;
  return String(value);
}

export function ObjectRecordDetail({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  const record = detail.subject.record as unknown as Record<string, unknown>;
  const fields = Object.entries(record).filter(([key]) => !JSON_FIELDS.has(key));
  const jsonFields = Object.entries(record).filter(([key]) => JSON_FIELDS.has(key));
  return (
    <Section title={text(zhCN.componentsObjectsObjectDetailSections.recordInformation, "Record information")} className="object-record-detail">
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
  return <a className="text-action" href={href}>{text(zhCN.componentsObjectsObjectDetailSections.download, "Download")}</a>;
}

function AttachmentTable({ detail, attachments }: { detail: ObjectDetail; attachments: Attachment[] }) {
  const { language, text } = useI18n();
  if (attachments.length === 0) return <EmptySection>{text(zhCN.componentsObjectsObjectDetailSections.noRelatedAttachments, "No related attachments.")}</EmptySection>;
  return (
    <div className="table-scroll"><table className="data-table object-detail-table">
      <thead><tr><th>{text(zhCN.componentsObjectsObjectDetailSections.fileName, "File name")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.type, "Type")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.size, "Size")}</th><th>SHA-256</th><th>{text(zhCN.componentsObjectsObjectDetailSections.uploaded, "Uploaded")}</th><th><span className="sr-only">{text(zhCN.componentsObjectsObjectDetailSections.actions, "Actions")}</span></th></tr></thead>
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
  return <Section title={text(zhCN.componentsObjectsObjectDetailSections.timesheetEntries, "Timesheet entries")} count={detail.timesheetEntries.length}>
    {detail.timesheetEntries.length === 0 ? <EmptySection>{text(zhCN.componentsObjectsObjectDetailSections.thisTimesheetHasNoEntriesYet, "This timesheet has no entries yet.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text(zhCN.componentsObjectsObjectDetailSections.date, "Date")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.project, "Project")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.customer, "Customer")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.task, "Task")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.hours, "Hours")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.type, "Type")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.comment, "Notes")}</th></tr></thead>
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
    <Section title={text(zhCN.componentsObjectsObjectDetailSections.expenseItems, "Expense items")} count={detail.expenseItems.length}>
      {detail.expenseItems.length === 0 ? <EmptySection>{text(zhCN.componentsObjectsObjectDetailSections.thisExpenseClaimHasNoExpenseItemsYet, "This expense claim has no expense items yet.")}</EmptySection> :
        <div className="table-scroll"><table className="data-table object-detail-table">
          <thead><tr><th>{text(zhCN.componentsObjectsObjectDetailSections.date, "Date")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.category, "Category")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.merchant, "Merchant")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.vendor, "Vendor")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.amount, "Amount")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.tax, "Tax")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.invoiceNo, "Invoice no.")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.project, "Project")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.receipt, "Receipt")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.comment, "Notes")}</th></tr></thead>
          <tbody>{detail.expenseItems.map((item) => <tr key={item.id}>
            <td>{formatDate(item.expense_date, language)}</td><td>{item.category}</td><td>{item.merchant || "—"}</td>
            <td>{item.vendor_name || item.vendor_id || "—"}</td>
            <td><strong>{formatMoney(item.amount, currency, language)}</strong></td><td>{formatMoney(item.tax_amount, currency, language)}</td>
            <td className="mono-cell">{item.invoice_number || "—"}</td><td>{item.project_name_snapshot || item.project_id || "—"}</td>
            <td>{item.attachment_id ? <AttachmentDownload detail={detail} attachmentId={item.attachment_id} /> : "—"}</td>
            <td>{item.notes || "—"}</td>
          </tr>)}</tbody>
          {detail.expenseTotals && <tfoot><tr><td colSpan={4}>{text(zhCN.componentsObjectsObjectDetailSections.total, "Total")}</td><td><strong>{formatMoney(detail.expenseTotals.totalAmount, currency, language)}</strong></td><td>{formatMoney(detail.expenseTotals.totalTaxAmount, currency, language)}</td><td colSpan={4} /></tr></tfoot>}
        </table></div>}
    </Section>
    <Section title={text(zhCN.componentsObjectsObjectDetailSections.receiptAttachments, "Receipt attachments")} count={detail.attachments.length}><AttachmentTable detail={detail} attachments={detail.attachments} /></Section>
  </>;
}

function PurchaseLines({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  if (detail.entityType !== "purchase_request") return null;
  const record = detail.subject.entityType === "purchase_request" ? detail.subject.record : null;
  const currency = record?.currency || "CNY";
  return <>
    <Section title={text(zhCN.componentsObjectsObjectDetailSections.purchaseItems, "Purchase items")} count={detail.purchaseItems.length}>
      {detail.purchaseItems.length === 0 ? <EmptySection>{text(zhCN.componentsObjectsObjectDetailSections.thisPurchaseRequestHasNoItemsYet, "This purchase request has no items yet.")}</EmptySection> :
        <div className="table-scroll"><table className="data-table object-detail-table">
          <thead><tr><th>{text(zhCN.componentsObjectsObjectDetailSections.product, "Product")}</th><th>SKU</th><th>{text(zhCN.componentsObjectsObjectDetailSections.specification, "Specification")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.quantity, "Quantity")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.unit, "Unit")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.unitPrice, "Unit price")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.amount, "Amount")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.quote, "Quote")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.comment, "Notes")}</th></tr></thead>
          <tbody>{detail.purchaseItems.map((item) => {
            const estimated = item.amount ?? (item.unit_price == null ? null : item.unit_price * item.quantity);
            return <tr key={item.id}>
              <td><strong>{item.product?.name || item.product_name_snapshot || "—"}</strong>{item.product?.product_code && <small>{item.product.product_code}</small>}{item.product_id && <small className="object-inline-id">{item.product_id}</small>}</td>
              <td>{item.sku ? <><strong className="mono-cell">{item.sku.sku_code || item.sku.id}</strong>{Object.keys(item.sku.variant_attrs).length > 0 && <small className="object-variant-list">{variantSummary(item.sku.variant_attrs)}</small>}</> : !item.sku_id && item.sku_pending ? <span className="object-pending-sku">{text(zhCN.componentsObjectsObjectDetailSections.sKUPending, "SKU pending")}</span> : item.sku_id ? <><span className="mono-cell">{item.sku_id}</span><small>{text(zhCN.componentsObjectsObjectDetailSections.sKUCatalogInformationUnavailable, "SKU catalog information unavailable")}</small></> : "—"}</td><td>{item.spec || item.product?.spec || "—"}</td><td>{item.quantity}</td><td>{item.unit || item.product?.unit || "—"}</td>
              <td>{formatMoney(item.unit_price, currency, language)}</td><td><strong>{formatMoney(estimated, currency, language)}</strong></td>
              <td>{item.attachment_id ? <AttachmentDownload detail={detail} attachmentId={item.attachment_id} /> : "—"}</td>
              <td>{item.notes || "—"}</td>
            </tr>;
          })}</tbody>
          {detail.purchaseTotals && <tfoot><tr><td colSpan={6}>{text(zhCN.componentsObjectsObjectDetailSections.estimatedTotal, "Estimated total")}</td><td><strong>{formatMoney(detail.purchaseTotals.estimatedTotal, currency, language)}</strong><small>{detail.purchaseTotals.unpricedItemCount > 0 && text(zhCN.componentsObjectsObjectDetailSections.unpricedLines(`${detail.purchaseTotals.unpricedItemCount}`), `${detail.purchaseTotals.unpricedItemCount} additional unpriced items`)}{detail.purchaseTotals.pendingSkuCount > 0 && text(zhCN.componentsObjectsObjectDetailSections.sKUsPending(`${detail.purchaseTotals.pendingSkuCount}`), ` · ${detail.purchaseTotals.pendingSkuCount} SKUs pending`)}</small></td><td colSpan={2} /></tr></tfoot>}
        </table></div>}
    </Section>
    <Section title={text(zhCN.componentsObjectsObjectDetailSections.quoteAttachments, "Quote attachments")} count={detail.attachments.length}><AttachmentTable detail={detail} attachments={detail.attachments} /></Section>
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
    <Section title={text(zhCN.componentsObjectsObjectDetailSections.quotationLines, "Quotation lines")} count={detail.salesQuotationItems.length}>
      {detail.salesQuotationItems.length === 0 ? <EmptySection>{text(zhCN.componentsObjectsObjectDetailSections.thisQuotationHasNoLinesYet, "This quotation has no lines yet.")}</EmptySection> :
        <div className="table-scroll"><table className="data-table object-detail-table">
          <thead><tr><th>{text(zhCN.componentsObjectsObjectDetailSections.product, "Product")}</th><th>SKU</th><th>{text(zhCN.componentsObjectsObjectDetailSections.specification, "Specification")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.quantity, "Quantity")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.unit, "Unit")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.listPrice, "List price")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.unitPrice, "Unit price")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.taxRate, "Tax rate")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.amount, "Amount")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.leadTime, "Lead time")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.comment, "Notes")}</th></tr></thead>
          <tbody>{detail.salesQuotationItems.map((item) => {
            const lineTotal = item.is_gift ? 0 : (item.amount ?? (item.unit_price == null ? null : item.unit_price * item.quantity));
            return <tr key={item.id}>
              <td><strong>{item.product?.name || item.product_name_snapshot || "—"}</strong>{item.is_gift && <small className="object-gift-tag">{text(zhCN.componentsObjectsObjectDetailSections.gift, "Gift")}</small>}{item.product?.product_code && <small>{item.product.product_code}</small>}{item.product_id && <small className="object-inline-id">{item.product_id}</small>}</td>
              <td>{item.sku ? <><strong className="mono-cell">{item.sku.sku_code || item.sku.id}</strong>{Object.keys(item.sku.variant_attrs).length > 0 && <small className="object-variant-list">{variantSummary(item.sku.variant_attrs)}</small>}</> : !item.sku_id && item.sku_pending ? <span className="object-pending-sku">{text(zhCN.componentsObjectsObjectDetailSections.sKUPending, "SKU pending")}</span> : item.sku_id ? <><span className="mono-cell">{item.sku_id}</span><small>{text(zhCN.componentsObjectsObjectDetailSections.sKUCatalogInformationUnavailable, "SKU catalog information unavailable")}</small></> : "—"}</td><td>{item.spec || item.product?.spec || "—"}</td><td>{item.quantity}</td><td>{item.unit || item.product?.unit || "—"}</td>
              <td>{formatMoney(item.list_price_snapshot, currency, language)}</td><td>{item.is_gift ? text(zhCN.componentsObjectsObjectDetailSections.gift, "Gift") : formatMoney(item.unit_price, currency, language)}</td><td>{item.tax_rate == null ? "—" : `${item.tax_rate}%`}</td><td><strong>{formatMoney(lineTotal, currency, language)}</strong></td>
              <td>{item.lead_time || "—"}</td>
              <td>{item.notes || "—"}</td>
            </tr>;
          })}</tbody>
          {totals && <tfoot>
            <tr><td colSpan={8}>{text(zhCN.componentsObjectsObjectDetailSections.lineTotal, "Line total")}</td><td><strong>{formatMoney(totals.computedTotal, currency, language)}</strong>{(totals.unpricedItemCount > 0 || totals.pendingSkuCount > 0) && <small>{totals.unpricedItemCount > 0 && text(zhCN.componentsObjectsObjectDetailSections.unpricedLines(`${totals.unpricedItemCount}`), `${totals.unpricedItemCount} unpriced lines`)}{totals.pendingSkuCount > 0 && text(zhCN.componentsObjectsObjectDetailSections.sKUsPending(`${totals.pendingSkuCount}`), ` · ${totals.pendingSkuCount} SKUs pending`)}</small>}</td><td colSpan={2} /></tr>
            {documentTotal != null && <tr><td colSpan={8}>{text(zhCN.componentsObjectsObjectDetailSections.documentTotal, "Document total")}</td><td><strong>{formatMoney(documentTotal, currency, language)}</strong>{Math.abs(documentTotal - totals.computedTotal) > 0.005 && <small>{text(zhCN.componentsObjectsObjectDetailSections.differsFromLineTotalRoundingNegotiated, "Differs from line total (rounding / negotiated)")}</small>}</td><td colSpan={2} /></tr>}
          </tfoot>}
        </table></div>}
    </Section>
    <Section title={text(zhCN.componentsObjectsObjectDetailSections.quoteAttachments, "Quotation attachments")} count={detail.attachments.length}><AttachmentTable detail={detail} attachments={detail.attachments} /></Section>
  </>;
}

function SalesQuotationRevisions({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  if (detail.entityType !== "sales_quotation") return null;
  const currentId = detail.subject.record.id;
  const revisions = [...detail.revisions].sort((left, right) => right.revision_no - left.revision_no);
  return <Section title={text(zhCN.componentsObjectsObjectDetailSections.revisionChain, "Revision chain")} count={revisions.length} description={text(zhCN.componentsObjectsObjectDetailSections.allRevisionsUnderTheSameQuoteNumberNewestFirst, "All revisions under the same quote number, newest first; superseded revisions remain as immutable facts.")}>
    {revisions.length === 0 ? <EmptySection>{text(zhCN.componentsObjectsObjectDetailSections.thisQuotationHasNoOtherRevisionsYet, "This quotation has no other revisions yet.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text(zhCN.componentsObjectsObjectDetailSections.revision, "Revision")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.status, "Status")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.quoteDate, "Quote date")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.validUntil, "Valid until")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.total2, "Total")}</th><th><span className="sr-only">{text(zhCN.componentsObjectsObjectDetailSections.actions, "Actions")}</span></th></tr></thead>
        <tbody>{revisions.map((revision) => <tr key={revision.id}>
          <td><strong>{text(zhCN.componentsObjectsObjectDetailSections.rev(`${revision.revision_no}`), `Rev ${revision.revision_no}`)}</strong>{revision.id === currentId && <small>{text(zhCN.componentsObjectsObjectDetailSections.viewing, "Viewing")}</small>}</td>
          <td><ObjectStatus status={revision.status} /></td>
          <td>{formatDate(revision.quote_date, language)}</td>
          <td>{formatDate(revision.valid_until, language)}</td>
          <td>{formatMoney(revision.total_amount, revision.currency, language)}</td>
          <td className="row-actions">{revision.id === currentId ? <span className="muted-value">{text(zhCN.componentsObjectsObjectDetailSections.thisOne, "This one")}</span> : <Link className="text-action" to={`/objects/sales_quotation/${encodeURIComponent(revision.id)}?kind=builtin&object_type=sales_quotation`}>{text(zhCN.componentsObjectsObjectDetailSections.view, "View")}</Link>}</td>
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
    <Section title={text(zhCN.componentsObjectsObjectDetailSections.orderLines, "Order lines")} count={detail.salesOrderItems.length}>
      {detail.salesOrderItems.length === 0 ? <EmptySection>{text(zhCN.componentsObjectsObjectDetailSections.thisOrderHasNoLinesYet, "This order has no lines yet.")}</EmptySection> :
        <div className="table-scroll"><table className="data-table object-detail-table">
          <thead><tr><th>{text(zhCN.componentsObjectsObjectDetailSections.product, "Product")}</th><th>SKU</th><th>{text(zhCN.componentsObjectsObjectDetailSections.specification, "Specification")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.quantity, "Quantity")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.unit, "Unit")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.listPrice, "List price")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.unitPrice, "Unit price")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.taxRate, "Tax rate")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.amount, "Amount")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.promised, "Promised")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.comment, "Notes")}</th></tr></thead>
          <tbody>{detail.salesOrderItems.map((item) => {
            const lineTotal = item.is_gift ? 0 : (item.amount ?? (item.unit_price == null ? null : item.unit_price * item.quantity));
            return <tr key={item.id}>
              <td><strong>{item.product?.name || item.product_name_snapshot || "—"}</strong>{item.is_gift && <small className="object-gift-tag">{text(zhCN.componentsObjectsObjectDetailSections.gift, "Gift")}</small>}{item.product?.product_code && <small>{item.product.product_code}</small>}{item.product_id && <small className="object-inline-id">{item.product_id}</small>}</td>
              <td>{item.sku ? <><strong className="mono-cell">{item.sku.sku_code || item.sku.id}</strong>{Object.keys(item.sku.variant_attrs).length > 0 && <small className="object-variant-list">{variantSummary(item.sku.variant_attrs)}</small>}</> : !item.sku_id && item.sku_pending ? <span className="object-pending-sku">{text(zhCN.componentsObjectsObjectDetailSections.sKUPending, "SKU pending")}</span> : item.sku_id ? <><span className="mono-cell">{item.sku_id}</span><small>{text(zhCN.componentsObjectsObjectDetailSections.sKUCatalogInformationUnavailable, "SKU catalog information unavailable")}</small></> : "—"}</td><td>{item.spec || item.product?.spec || "—"}</td><td>{item.quantity}</td><td>{item.unit || item.product?.unit || "—"}</td>
              <td>{formatMoney(item.list_price_snapshot, currency, language)}</td><td>{item.is_gift ? text(zhCN.componentsObjectsObjectDetailSections.gift, "Gift") : formatMoney(item.unit_price, currency, language)}</td><td>{item.tax_rate == null ? "—" : `${item.tax_rate}%`}</td><td><strong>{formatMoney(lineTotal, currency, language)}</strong></td>
              <td>{formatDate(item.promised_date, language)}</td>
              <td>{item.notes || "—"}</td>
            </tr>;
          })}</tbody>
          {totals && <tfoot>
            <tr><td colSpan={8}>{text(zhCN.componentsObjectsObjectDetailSections.lineTotal2, "Line total")}</td><td><strong>{formatMoney(totals.computedTotal, currency, language)}</strong>{(totals.unpricedItemCount > 0 || totals.pendingSkuCount > 0) && <small>{totals.unpricedItemCount > 0 && text(zhCN.componentsObjectsObjectDetailSections.unpricedLines(`${totals.unpricedItemCount}`), `${totals.unpricedItemCount} unpriced lines`)}{totals.pendingSkuCount > 0 && text(zhCN.componentsObjectsObjectDetailSections.sKUsPending(`${totals.pendingSkuCount}`), ` · ${totals.pendingSkuCount} SKUs pending`)}</small>}</td><td colSpan={2} /></tr>
            {documentTotal != null && <tr><td colSpan={8}>{text(zhCN.componentsObjectsObjectDetailSections.documentTotal, "Document total")}</td><td><strong>{formatMoney(documentTotal, currency, language)}</strong>{Math.abs(documentTotal - totals.computedTotal) > 0.005 && <small>{text(zhCN.componentsObjectsObjectDetailSections.differsFromLineTotalRoundingNegotiated, "Differs from line total (rounding / negotiated)")}</small>}</td><td colSpan={2} /></tr>}
          </tfoot>}
        </table></div>}
    </Section>
    <Section title={text(zhCN.componentsObjectsObjectDetailSections.orderAttachments, "Order attachments")} count={detail.attachments.length}><AttachmentTable detail={detail} attachments={detail.attachments} /></Section>
  </>;
}

function SalesOrderQuotationLink({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  if (detail.entityType !== "sales_order") return null;
  const order = detail.subject.entityType === "sales_order" ? detail.subject.record : null;
  const quotation = detail.quotationLink;
  return <Section
    title={text(zhCN.componentsObjectsObjectDetailSections.wonQuotation, "Won quotation")}
    description={text(zhCN.componentsObjectsObjectDetailSections.theWonQuotationThisOrderWasConvertedFromThe, "The won quotation this order was converted from — the immutable source fact of the quote-to-order handoff.")}
  >
    {!quotation
      ? <EmptySection>{order?.source_quote_number
          ? text(zhCN.componentsObjectsObjectDetailSections.theOrderRecordsWonQuoteNoButNoLinked(`${order.source_quote_number}`), `The order records won quote no. ${order.source_quote_number}, but no linked quotation record is available.`)
          : text(zhCN.componentsObjectsObjectDetailSections.thisOrderHasNoLinkedWonQuotationItMay, "This order has no linked won quotation (it may have been created directly).")}</EmptySection>
      : <dl className="object-kv-grid">
          <div><dt>{text(zhCN.componentsObjectsObjectDetailSections.quoteNo, "Quote no.")}</dt><dd><Link className="text-action mono-cell" to={`/objects/sales_quotation/${encodeURIComponent(quotation.id)}?kind=builtin&object_type=sales_quotation`}>{quotation.quote_number}</Link>{quotation.revision_no > 1 && <small className="object-inline-id">{text(zhCN.componentsObjectsObjectDetailSections.rev(`${quotation.revision_no}`), `Rev ${quotation.revision_no}`)}</small>}</dd></div>
          <div><dt>{text(zhCN.componentsObjectsObjectDetailSections.reason, "Reason")}</dt><dd>{quotation.title}</dd></div>
          <div><dt>{text(zhCN.componentsObjectsObjectDetailSections.customer, "Customer")}</dt><dd>{quotation.customer_name_snapshot || "—"}</dd></div>
          <div><dt>{text(zhCN.componentsObjectsObjectDetailSections.status, "Status")}</dt><dd><ObjectStatus status={quotation.status} /></dd></div>
          <div><dt>{text(zhCN.componentsObjectsObjectDetailSections.quoteTotal, "Quote total")}</dt><dd>{formatMoney(quotation.total_amount, quotation.currency, language)}</dd></div>
          <div><dt>{text(zhCN.componentsObjectsObjectDetailSections.validUntil, "Valid until")}</dt><dd>{formatDate(quotation.valid_until, language)}</dd></div>
        </dl>}
  </Section>;
}

function BusinessObjectLinks({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  if (detail.entityType !== "business_object") return null;
  return <Section title={text(zhCN.componentsObjectsObjectDetailSections.relatedObjects, "Related objects")} count={detail.links.length} description={text(zhCN.componentsObjectsObjectDetailSections.includesRelationshipsWhereThisObjectIsEitherTheSource, "Includes relationships where this object is either the source or target, deduplicated by ID.")}>
    {detail.links.length === 0 ? <EmptySection>{text(zhCN.componentsObjectsObjectDetailSections.thisBusinessObjectHasNoRelationshipsYet, "This business object has no relationships yet.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text(zhCN.componentsObjectsObjectDetailSections.relationshipType, "Relationship type")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.sourceObject, "Source object")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.targetObject, "Target object")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.metadata, "Metadata")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.created, "Created")}</th></tr></thead>
        <tbody>{detail.links.map((link) => <tr key={link.id}>
          <td><code>{link.link_type}</code></td>
          <td>{link.source_object_id === detail.subject.record.id ? <span className="muted-value">{text(zhCN.componentsObjectsObjectDetailSections.thisObject, "This object")}</span> : <Link className="text-action mono-cell" to={`/objects/business_object/${encodeURIComponent(link.source_object_id)}`}>{link.source_object_id}</Link>}</td>
          <td>{link.target_object_id === detail.subject.record.id ? <span className="muted-value">{text(zhCN.componentsObjectsObjectDetailSections.thisObject, "This object")}</span> : <Link className="text-action mono-cell" to={`/objects/business_object/${encodeURIComponent(link.target_object_id)}`}>{link.target_object_id}</Link>}</td>
          <td>{Object.keys(link.metadata).length ? <details><summary>{text(zhCN.componentsObjectsObjectDetailSections.view, "View")}</summary><pre>{JSON.stringify(link.metadata, null, 2)}</pre></details> : "—"}</td>
          <td>{formatDateTime(link.created_at, language)}</td>
        </tr>)}</tbody>
      </table></div>}
  </Section>;
}

function RuleHistory({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  return <Section title={text(zhCN.componentsObjectsObjectDetailSections.businessRules(`${detail.objectType}`), `${detail.objectType} business rules`)} count={detail.rules.length} description={text(zhCN.componentsObjectsObjectDetailSections.agentsReadTheVersionInForceSupersededVersionsRemain, "Agents read the version in force; superseded versions remain so past decisions stay traceable.")}>
    {detail.rules.length === 0 ? <EmptySection>{text(zhCN.componentsObjectsObjectDetailSections.noBusinessRuleHasBeenPublishedForThisType, "No business rule has been published for this type.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text(zhCN.componentsObjectsObjectDetailSections.kind, "Kind")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.name, "Name")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.revision, "Version")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.status, "Status")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.inForce, "In force")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.rule, "Rule")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.publishedBy, "Published by")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.published, "Published")}</th></tr></thead>
        <tbody>{detail.rules.map((rule) => {
          const publisher = rule.published_by ?? rule.created_by;
          return <tr key={rule.id}>
            <td><strong>{ruleKindLabel(rule.kind, text)}</strong></td><td>{rule.name ?? rule.code}</td><td><span className="object-version">v{rule.version}</span></td>
            <td><ObjectStatus status={rule.status} /></td>
            <td>{rule.effective_from ? formatDate(rule.effective_from, language) : "—"}{rule.effective_thru ? zhCN.componentsObjectsObjectDetailSections.template6(`${text(zhCN.componentsObjectsObjectDetailSections.to, "to")}`, `${formatDate(rule.effective_thru, language)}`) : ""}</td>
            <td><details><summary>{text(zhCN.componentsObjectsObjectDetailSections.viewRule, "View rule")}</summary><pre className="object-definition">{rule.body}</pre></details></td>
            <td>{publisher ? detail.actors[publisher] || publisher : "—"}</td><td>{formatDateTime(rule.published_at ?? rule.created_at, language)}</td>
          </tr>;
        })}</tbody>
      </table></div>}
  </Section>;
}

function ApprovalHistory({ detail }: { detail: ObjectDetail }) {
  const { language, text } = useI18n();
  return <Section title={text(zhCN.componentsObjectsObjectDetailSections.approvalHistory, "Approval history")} count={detail.approvals.length} description={text(zhCN.componentsObjectsObjectDetailSections.orderedByRoundStepAndActionTime, "Ordered by round, step, and action time.")}>
    {detail.approvals.length === 0 ? <EmptySection>{text(zhCN.componentsObjectsObjectDetailSections.noApprovalActivityYet, "No approval activity yet.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text(zhCN.componentsObjectsObjectDetailSections.round, "Round")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.step, "Step")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.action, "Action")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.actor, "Actor")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.role, "Role")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.comment, "Comment")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.time, "Time")}</th></tr></thead>
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
  return <Section title={text(zhCN.componentsObjectsObjectDetailSections.todos, "Todos")} count={detail.todos.length}>
    {detail.todos.length === 0 ? <EmptySection>{text(zhCN.componentsObjectsObjectDetailSections.noTodosReferenceThisRecord, "No todos reference this record.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text(zhCN.componentsObjectsObjectDetailSections.title, "Title")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.assignee, "Assignee")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.type, "Type")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.status, "Status")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.due, "Due")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.completion, "Completion")}</th></tr></thead>
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
  return <Section title={text(zhCN.componentsObjectsObjectDetailSections.auditTrail, "Audit trail")} count={detail.audits.length}>
    {detail.audits.length === 0 ? <EmptySection>{text(zhCN.componentsObjectsObjectDetailSections.noAuditRecordsAreAvailable, "No audit records are available.")}</EmptySection> :
      <div className="table-scroll"><table className="data-table object-detail-table">
        <thead><tr><th>{text(zhCN.componentsObjectsObjectDetailSections.time, "Time")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.action, "Action")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.actor, "Actor")}</th><th>{text(zhCN.componentsObjectsObjectDetailSections.details, "Details")}</th></tr></thead>
        <tbody>{detail.audits.map((audit) => <tr key={audit.id}>
          <td>{formatDateTime(audit.created_at, language)}</td><td><code>{audit.action}</code></td>
          <td>{audit.actor ? detail.actors[audit.actor] || audit.actor : "—"}</td>
          <td>{Object.keys(audit.detail || {}).length ? <details><summary>{text(zhCN.componentsObjectsObjectDetailSections.view, "View")}</summary><pre>{JSON.stringify(audit.detail, null, 2)}</pre></details> : "—"}</td>
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
    <RuleHistory detail={detail} />
    <ApprovalHistory detail={detail} />
    <TodoHistory detail={detail} />
    <AuditHistory detail={detail} />
  </>;
}
