import { zhCN } from "../../locales/zh-CN/console";
import { Link } from "react-router-dom";

import type { ObjectDisplayNames, ObjectListRecord } from "../../api/objects";
import { useI18n } from "../../i18n";

// A lookup, not a ternary chain. The chain fell through to "payslip" for
// anything it did not name, so `reimbursement` — added on the server — showed
// as a payslip in the console: a payable to an employee mislabelled as their
// pay. A fifth direction is one line here, and an unknown one shows its own
// key rather than borrowing someone else's meaning.
export function invoiceDirectionLabel(
  direction: string,
  text: (zh: string, en: string) => string,
): string {
  switch (direction) {
    case "sales":
      return text(zhCN.componentsObjectsObjectRecordTable.sales, "Sales");
    case "purchase":
      return text(zhCN.componentsObjectsObjectRecordTable.purchase, "Purchase");
    case "payroll":
      return text(zhCN.componentsObjectsObjectRecordTable.payslip, "Payslip");
    case "reimbursement":
      return text(zhCN.componentsObjectsObjectRecordTable.reimbursement, "Reimbursement");
    default:
      return direction;
  }
}

export function ObjectStatus({ status, translate = true }: { status: string; translate?: boolean }) {
  const { text } = useI18n();
  const token = status.toLocaleLowerCase().replace(/[^a-z0-9_-]/g, "-");
  const labels: Record<string, [string, string]> = {
    active: [zhCN.componentsObjectsObjectRecordTable.active, "Active"],
    inactive: [zhCN.componentsObjectsObjectRecordTable.name16, "Inactive"],
    archived: [zhCN.componentsObjectsObjectRecordTable.archived, "Archived"],
    confirmed: [zhCN.componentsObjectsObjectRecordTable.message4, "Confirmed"],
    cancelled: [zhCN.componentsObjectsObjectRecordTable.message5, "Cancelled"],
    draft: [zhCN.componentsObjectsObjectRecordTable.draft, "Draft"],
    repealed: [zhCN.componentsObjectsObjectRecordTable.repealed, "Repealed"],
    submitted: [zhCN.componentsObjectsObjectRecordTable.submitted2, "Submitted"],
    approved: [zhCN.componentsObjectsObjectRecordTable.message9, "Approved"],
    rejected: [zhCN.componentsObjectsObjectRecordTable.rejected, "Rejected"],
    returned: [zhCN.componentsObjectsObjectRecordTable.returned, "Returned"],
    sent: [zhCN.componentsObjectsObjectRecordTable.message12, "Sent"],
    accepted: [zhCN.componentsObjectsObjectRecordTable.message13, "Accepted"],
    declined: [zhCN.componentsObjectsObjectRecordTable.message14, "Declined"],
    expired: [zhCN.componentsObjectsObjectRecordTable.message15, "Expired"],
    shipped: [zhCN.componentsObjectsObjectRecordTable.message16, "Shipped"],
    signed: [zhCN.componentsObjectsObjectRecordTable.message17, "Signed"],
    in_delivery: [zhCN.componentsObjectsObjectRecordTable.message18, "In delivery"],
    delivered: [zhCN.componentsObjectsObjectRecordTable.message19, "Delivered"],
    open: [zhCN.componentsObjectsObjectRecordTable.running, "Open"],
    completed: [zhCN.componentsObjectsObjectRecordTable.completed, "Completed"],
    pending: [zhCN.componentsObjectsObjectRecordTable.message22, "Pending"],
    published: [zhCN.componentsObjectsObjectRecordTable.published, "Published"],
    superseded: [zhCN.componentsObjectsObjectRecordTable.superseded, "Superseded"],
  };
  return <span className={`object-status ${token}`}>{translate && labels[status] ? text(...labels[status]) : status}</span>;
}

export function formatDate(value: string | null | undefined, locale = "zh-CN"): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

export function formatDateTime(value: string | null | undefined, locale = "zh-CN"): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(date);
}

export function formatMoney(value: number | null | undefined, currency: string, locale = "zh-CN"): string {
  if (value == null) return "—";
  try {
    return new Intl.NumberFormat(locale, { style: "currency", currency }).format(value);
  } catch {
    return `${currency} ${value.toFixed(2)}`;
  }
}

function detailUrl(item: ObjectListRecord, objectType: string): string {
  const search = new URLSearchParams({
    kind: item.entityType === "business_object" ? "business_object" : "builtin",
    object_type: objectType,
  });
  return `/objects/${item.entityType}/${encodeURIComponent(item.record.id)}?${search.toString()}`;
}

function person(id: string | null | undefined, names: Record<string, string>): string {
  if (!id) return "—";
  return names[id] || id;
}

type ObjectRecordTableProps = ObjectDisplayNames & {
  records: ObjectListRecord[];
  objectType: string;
};

export function ObjectRecordTable({ records, objectType, employees, actors }: ObjectRecordTableProps) {
  const { language, text } = useI18n();
  const entityType = records[0]?.entityType;
  if (!entityType) return null;

  if (entityType === "timesheet_header") {
    return (
      <div className="table-scroll">
        <table className="data-table object-record-table">
          <thead><tr><th>{text(zhCN.componentsObjectsObjectRecordTable.employee, "Employee")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.period, "Period")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.status, "Status")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.submitted, "Submitted")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.updated, "Updated")}</th><th><span className="sr-only">{text(zhCN.componentsObjectsObjectRecordTable.actions, "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong>{person(record.employee_id, employees)}</strong><small className="mono-cell">{record.employee_id}</small></td>
              <td>{formatDate(record.period_start, language)} → {formatDate(record.period_end, language)}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td>{formatDateTime(record.submitted_at, language)}</td>
              <td>{formatDateTime(record.updated_at, language)}</td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text(zhCN.componentsObjectsObjectRecordTable.viewDetails, "View details")}</Link></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    );
  }

  if (entityType === "expense_claim") {
    return (
      <div className="table-scroll">
        <table className="data-table object-record-table">
          <thead><tr><th>{text(zhCN.componentsObjectsObjectRecordTable.employee, "Employee")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.reason, "Reason")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.claimDate, "Claim date")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.currency, "Currency")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.status, "Status")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.submitted, "Submitted")}</th><th><span className="sr-only">{text(zhCN.componentsObjectsObjectRecordTable.actions, "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong>{person(record.employee_id, employees)}</strong><small className="mono-cell">{record.employee_id}</small></td>
              <td><strong>{record.title}</strong></td>
              <td>{formatDate(record.claim_date, language)}</td>
              <td className="mono-cell">{record.currency}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td>{formatDateTime(record.submitted_at, language)}</td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text(zhCN.componentsObjectsObjectRecordTable.viewDetails, "View details")}</Link></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    );
  }

  if (entityType === "purchase_request") {
    return (
      <div className="table-scroll">
        <table className="data-table object-record-table">
          <thead><tr><th>{text(zhCN.componentsObjectsObjectRecordTable.requester, "Requester")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.reason, "Reason")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.preferredVendor, "Preferred vendor")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.neededBy, "Needed by")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.status, "Status")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.submitted, "Submitted")}</th><th><span className="sr-only">{text(zhCN.componentsObjectsObjectRecordTable.actions, "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong>{person(record.employee_id, employees)}</strong><small className="mono-cell">{record.employee_id}</small></td>
              <td><strong>{record.title}</strong></td>
              <td>{record.vendor_name_snapshot || "—"}</td>
              <td>{formatDate(record.needed_by, language)}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td>{formatDateTime(record.submitted_at, language)}</td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text(zhCN.componentsObjectsObjectRecordTable.viewDetails, "View details")}</Link></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    );
  }

  if (entityType === "sales_quotation") {
    return (
      <div className="table-scroll">
        <table className="data-table object-record-table">
          <thead><tr><th>{text(zhCN.componentsObjectsObjectRecordTable.quoteNo, "Quote no.")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.customer, "Customer")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.reason, "Reason")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.total, "Total")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.validUntil, "Valid until")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.status, "Status")}</th><th><span className="sr-only">{text(zhCN.componentsObjectsObjectRecordTable.actions, "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong className="mono-cell">{record.quote_number}</strong>{record.revision_no > 1 && <small>{text(zhCN.componentsObjectsObjectRecordTable.rev(`${record.revision_no}`), `Rev ${record.revision_no}`)}</small>}</td>
              <td>{record.customer_name_snapshot || "—"}</td>
              <td><strong>{record.title}</strong></td>
              <td>{formatMoney(record.total_amount, record.currency, language)}</td>
              <td>{formatDate(record.valid_until, language)}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text(zhCN.componentsObjectsObjectRecordTable.viewDetails, "View details")}</Link></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    );
  }

  if (entityType === "sales_order") {
    return (
      <div className="table-scroll">
        <table className="data-table object-record-table">
          <thead><tr><th>{text(zhCN.componentsObjectsObjectRecordTable.orderNo, "Order no.")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.customer, "Customer")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.amount, "Amount")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.status, "Status")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.promised, "Promised")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.trackingNo, "Tracking no.")}</th><th><span className="sr-only">{text(zhCN.componentsObjectsObjectRecordTable.actions, "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong className="mono-cell">{record.order_no}</strong>{record.source_quote_number && <small>{text(zhCN.componentsObjectsObjectRecordTable.quote(`${record.source_quote_number}`), `Quote ${record.source_quote_number}`)}</small>}</td>
              <td>{record.customer_name_snapshot || "—"}</td>
              <td>{formatMoney(record.total_amount, record.currency, language)}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td>{formatDate(record.promised_date, language)}</td>
              <td className="mono-cell">{record.logistics_tracking_no || "—"}</td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text(zhCN.componentsObjectsObjectRecordTable.viewDetails, "View details")}</Link></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    );
  }

  if (entityType === "invoice") {
    return (
      <div className="table-scroll">
        <table className="data-table object-record-table">
          <thead><tr><th>{text(zhCN.componentsObjectsObjectRecordTable.invoiceNo, "Invoice no.")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.direction, "Direction")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.counterparty, "Counterparty")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.amount, "Amount")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.applied, "Applied")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.duePeriod, "Due / period")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.status, "Status")}</th><th><span className="sr-only">{text(zhCN.componentsObjectsObjectRecordTable.actions, "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong className="mono-cell">{record.invoice_no}</strong>{record.tax_invoice_number && <small className="mono-cell">{record.tax_invoice_number}</small>}</td>
              <td>{invoiceDirectionLabel(record.direction, text)}</td>
              <td>{record.counterparty_name_snapshot || "—"}</td>
              {/* a payslip declares no total of its own — net pay is the sum of its
                  lines, so the header has nothing to show here */}
              <td>{record.direction === "payroll" ? "—" : formatMoney(record.total_amount, record.currency, language)}</td>
              <td>{formatMoney(record.applied_amount, record.currency, language)}</td>
              <td>{record.direction === "payroll" ? formatDate(record.period_end, language) : formatDate(record.due_date, language)}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text(zhCN.componentsObjectsObjectRecordTable.viewDetails, "View details")}</Link></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    );
  }

  if (entityType === "payment") {
    return (
      <div className="table-scroll">
        <table className="data-table object-record-table">
          <thead><tr><th>{text(zhCN.componentsObjectsObjectRecordTable.paymentNo, "Payment no.")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.direction, "Direction")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.counterparty, "Counterparty")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.amount, "Amount")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.unapplied, "Unapplied")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.date, "Date")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.status, "Status")}</th><th><span className="sr-only">{text(zhCN.componentsObjectsObjectRecordTable.actions, "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong className="mono-cell">{record.payment_no}</strong>{record.reference_no && <small className="mono-cell">{record.reference_no}</small>}</td>
              <td>{record.direction === "inbound" ? text(zhCN.componentsObjectsObjectRecordTable.in, "In") : text(zhCN.componentsObjectsObjectRecordTable.out, "Out")}</td>
              <td>{record.counterparty_name_snapshot || "—"}</td>
              <td>{formatMoney(record.amount, record.currency, language)}</td>
              <td>{formatMoney(record.amount - record.applied_amount, record.currency, language)}</td>
              <td>{formatDate(record.payment_date, language)}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text(zhCN.componentsObjectsObjectRecordTable.viewDetails, "View details")}</Link></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    );
  }

  if (entityType === "billing_account") {
    return (
      <div className="table-scroll">
        <table className="data-table object-record-table">
          <thead><tr><th>{text(zhCN.componentsObjectsObjectRecordTable.account, "Account")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.owner, "Owner")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.unit, "Unit")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.balance, "Balance")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.available, "Available")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.status, "Status")}</th><th><span className="sr-only">{text(zhCN.componentsObjectsObjectRecordTable.actions, "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            const money = record.unit_type === "currency";
            return <tr key={record.id}>
              <td><strong className="mono-cell">{record.account_code}</strong><small>{record.name}</small></td>
              <td>{record.owner_name_snapshot || "—"}</td>
              <td>{money ? record.unit : zhCN.componentsObjectsObjectRecordTable.template3(`${record.unit}`, `${text(zhCN.componentsObjectsObjectRecordTable.points, "points")}`)}</td>
              <td>{money ? formatMoney(record.balance, record.unit, language) : record.balance}</td>
              <td>{money ? formatMoney(record.available_amount, record.unit, language) : record.available_amount}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text(zhCN.componentsObjectsObjectRecordTable.viewDetails, "View details")}</Link></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    );
  }

  if (entityType === "resource_booking") {
    return (
      <div className="table-scroll">
        <table className="data-table object-record-table">
          <thead><tr><th>{text(zhCN.componentsObjectsObjectRecordTable.title, "Title")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.bookedBy, "Booked by")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.start, "Start")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.end, "End")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.quantity, "Quantity")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.status, "Status")}</th><th><span className="sr-only">{text(zhCN.componentsObjectsObjectRecordTable.actions, "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong>{record.title}</strong><small>{record.booking_type || text(zhCN.componentsObjectsObjectRecordTable.uncategorized, "Uncategorized")}</small></td>
              <td><strong>{person(record.booked_by_employee_id, employees)}</strong><small className="mono-cell">{record.booked_by_employee_id}</small></td>
              <td>{formatDateTime(record.start_at, language)}</td>
              <td>{formatDateTime(record.end_at, language)}</td>
              <td>{record.quantity}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text(zhCN.componentsObjectsObjectRecordTable.viewDetails, "View details")}</Link></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="table-scroll">
      <table className="data-table object-record-table">
        <thead><tr><th>{text(zhCN.componentsObjectsObjectRecordTable.title, "Title")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.summary, "Summary")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.status, "Status")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.createdBy, "Created by")}</th><th>{text(zhCN.componentsObjectsObjectRecordTable.updated, "Updated")}</th><th><span className="sr-only">{text(zhCN.componentsObjectsObjectRecordTable.actions, "Actions")}</span></th></tr></thead>
        <tbody>{records.map((item) => {
          if (item.entityType !== "business_object") return null;
          const record = item.record;
          return <tr key={record.id}>
            <td><strong>{record.title}</strong><small className="mono-cell">{record.id}</small></td>
            <td className="object-summary-cell">{record.summary || "—"}</td>
            <td><ObjectStatus status={record.status} translate={false} />{record.deleted_at && <span className="object-deleted">{text(zhCN.componentsObjectsObjectRecordTable.deleted, "Deleted")}</span>}</td>
            <td className="object-actor-cell">{person(record.created_by, actors)}</td>
            <td className="object-date-cell">{formatDateTime(record.updated_at || record.created_at, language)}</td>
            <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text(zhCN.componentsObjectsObjectRecordTable.viewDetails, "View details")}</Link></td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  );
}
