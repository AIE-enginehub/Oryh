import { Link } from "react-router-dom";

import type { ObjectDisplayNames, ObjectListRecord } from "../../api/objects";
import { useI18n } from "../../i18n";

export function ObjectStatus({ status, translate = true }: { status: string; translate?: boolean }) {
  const { text } = useI18n();
  const token = status.toLocaleLowerCase().replace(/[^a-z0-9_-]/g, "-");
  const labels: Record<string, [string, string]> = {
    active: ["启用", "Active"],
    inactive: ["停用", "Inactive"],
    archived: ["已归档", "Archived"],
    confirmed: ["已确认", "Confirmed"],
    cancelled: ["已取消", "Cancelled"],
    draft: ["草稿", "Draft"],
    submitted: ["已提交", "Submitted"],
    approved: ["已通过", "Approved"],
    rejected: ["已拒绝", "Rejected"],
    returned: ["已退回", "Returned"],
    sent: ["已发送", "Sent"],
    accepted: ["已成交", "Accepted"],
    declined: ["已谢绝", "Declined"],
    expired: ["已过期", "Expired"],
    shipped: ["已发货", "Shipped"],
    signed: ["已签收", "Signed"],
    in_delivery: ["配送中", "In delivery"],
    delivered: ["已送达", "Delivered"],
    open: ["进行中", "Open"],
    completed: ["已完成", "Completed"],
    pending: ["待处理", "Pending"],
    published: ["已发布", "Published"],
    superseded: ["已替代", "Superseded"],
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
          <thead><tr><th>{text("员工", "Employee")}</th><th>{text("周期", "Period")}</th><th>{text("状态", "Status")}</th><th>{text("提交时间", "Submitted")}</th><th>{text("更新时间", "Updated")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong>{person(record.employee_id, employees)}</strong><small className="mono-cell">{record.employee_id}</small></td>
              <td>{formatDate(record.period_start, language)} → {formatDate(record.period_end, language)}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td>{formatDateTime(record.submitted_at, language)}</td>
              <td>{formatDateTime(record.updated_at, language)}</td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text("查看详情", "View details")}</Link></td>
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
          <thead><tr><th>{text("员工", "Employee")}</th><th>{text("事由", "Reason")}</th><th>{text("报销日期", "Claim date")}</th><th>{text("币种", "Currency")}</th><th>{text("状态", "Status")}</th><th>{text("提交时间", "Submitted")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
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
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text("查看详情", "View details")}</Link></td>
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
          <thead><tr><th>{text("申请人", "Requester")}</th><th>{text("事由", "Reason")}</th><th>{text("目标供应商", "Preferred vendor")}</th><th>{text("期望到货", "Needed by")}</th><th>{text("状态", "Status")}</th><th>{text("提交时间", "Submitted")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
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
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text("查看详情", "View details")}</Link></td>
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
          <thead><tr><th>{text("报价单号", "Quote no.")}</th><th>{text("客户", "Customer")}</th><th>{text("事由", "Reason")}</th><th>{text("总额", "Total")}</th><th>{text("有效期至", "Valid until")}</th><th>{text("状态", "Status")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong className="mono-cell">{record.quote_number}</strong>{record.revision_no > 1 && <small>{text(`第 ${record.revision_no} 版`, `Rev ${record.revision_no}`)}</small>}</td>
              <td>{record.customer_name_snapshot || "—"}</td>
              <td><strong>{record.title}</strong></td>
              <td>{formatMoney(record.total_amount, record.currency, language)}</td>
              <td>{formatDate(record.valid_until, language)}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text("查看详情", "View details")}</Link></td>
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
          <thead><tr><th>{text("订单号", "Order no.")}</th><th>{text("客户", "Customer")}</th><th>{text("金额", "Amount")}</th><th>{text("状态", "Status")}</th><th>{text("承诺交期", "Promised")}</th><th>{text("物流单号", "Tracking no.")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong className="mono-cell">{record.order_no}</strong>{record.source_quote_number && <small>{text(`报价 ${record.source_quote_number}`, `Quote ${record.source_quote_number}`)}</small>}</td>
              <td>{record.customer_name_snapshot || "—"}</td>
              <td>{formatMoney(record.total_amount, record.currency, language)}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td>{formatDate(record.promised_date, language)}</td>
              <td className="mono-cell">{record.logistics_tracking_no || "—"}</td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text("查看详情", "View details")}</Link></td>
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
          <thead><tr><th>{text("发票号", "Invoice no.")}</th><th>{text("方向", "Direction")}</th><th>{text("往来单位", "Counterparty")}</th><th>{text("金额", "Amount")}</th><th>{text("已核销", "Applied")}</th><th>{text("到期日 / 期间", "Due / period")}</th><th>{text("状态", "Status")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong className="mono-cell">{record.invoice_no}</strong>{record.tax_invoice_number && <small className="mono-cell">{record.tax_invoice_number}</small>}</td>
              <td>{record.direction === "sales" ? text("销项", "Sales") : record.direction === "purchase" ? text("进项", "Purchase") : text("工资条", "Payslip")}</td>
              <td>{record.counterparty_name_snapshot || "—"}</td>
              {/* a payslip declares no total of its own — 实发 is the sum of its
                  lines, so the header has nothing to show here */}
              <td>{record.direction === "payroll" ? "—" : formatMoney(record.total_amount, record.currency, language)}</td>
              <td>{formatMoney(record.applied_amount, record.currency, language)}</td>
              <td>{record.direction === "payroll" ? formatDate(record.period_end, language) : formatDate(record.due_date, language)}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text("查看详情", "View details")}</Link></td>
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
          <thead><tr><th>{text("单号", "Payment no.")}</th><th>{text("方向", "Direction")}</th><th>{text("往来单位", "Counterparty")}</th><th>{text("金额", "Amount")}</th><th>{text("未核销", "Unapplied")}</th><th>{text("日期", "Date")}</th><th>{text("状态", "Status")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong className="mono-cell">{record.payment_no}</strong>{record.reference_no && <small className="mono-cell">{record.reference_no}</small>}</td>
              <td>{record.direction === "inbound" ? text("收款", "In") : text("付款", "Out")}</td>
              <td>{record.counterparty_name_snapshot || "—"}</td>
              <td>{formatMoney(record.amount, record.currency, language)}</td>
              <td>{formatMoney(record.amount - record.applied_amount, record.currency, language)}</td>
              <td>{formatDate(record.payment_date, language)}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text("查看详情", "View details")}</Link></td>
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
          <thead><tr><th>{text("账户", "Account")}</th><th>{text("归属", "Owner")}</th><th>{text("计量", "Unit")}</th><th>{text("余额", "Balance")}</th><th>{text("可用", "Available")}</th><th>{text("状态", "Status")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            const money = record.unit_type === "currency";
            return <tr key={record.id}>
              <td><strong className="mono-cell">{record.account_code}</strong><small>{record.name}</small></td>
              <td>{record.owner_name_snapshot || "—"}</td>
              <td>{money ? record.unit : `${record.unit} (${text("积分", "points")})`}</td>
              <td>{money ? formatMoney(record.balance, record.unit, language) : record.balance}</td>
              <td>{money ? formatMoney(record.available_amount, record.unit, language) : record.available_amount}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text("查看详情", "View details")}</Link></td>
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
          <thead><tr><th>{text("标题", "Title")}</th><th>{text("预订人", "Booked by")}</th><th>{text("开始", "Start")}</th><th>{text("结束", "End")}</th><th>{text("数量", "Quantity")}</th><th>{text("状态", "Status")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
          <tbody>{records.map((item) => {
            if (item.entityType !== entityType) return null;
            const record = item.record;
            return <tr key={record.id}>
              <td><strong>{record.title}</strong><small>{record.booking_type || text("未分类", "Uncategorized")}</small></td>
              <td><strong>{person(record.booked_by_employee_id, employees)}</strong><small className="mono-cell">{record.booked_by_employee_id}</small></td>
              <td>{formatDateTime(record.start_at, language)}</td>
              <td>{formatDateTime(record.end_at, language)}</td>
              <td>{record.quantity}</td>
              <td><ObjectStatus status={record.status} /></td>
              <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text("查看详情", "View details")}</Link></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="table-scroll">
      <table className="data-table object-record-table">
        <thead><tr><th>{text("标题", "Title")}</th><th>{text("摘要", "Summary")}</th><th>{text("状态", "Status")}</th><th>{text("创建者", "Created by")}</th><th>{text("更新时间", "Updated")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
        <tbody>{records.map((item) => {
          if (item.entityType !== "business_object") return null;
          const record = item.record;
          return <tr key={record.id}>
            <td><strong>{record.title}</strong><small className="mono-cell">{record.id}</small></td>
            <td className="object-summary-cell">{record.summary || "—"}</td>
            <td><ObjectStatus status={record.status} translate={false} />{record.deleted_at && <span className="object-deleted">{text("已删除", "Deleted")}</span>}</td>
            <td className="object-actor-cell">{person(record.created_by, actors)}</td>
            <td className="object-date-cell">{formatDateTime(record.updated_at || record.created_at, language)}</td>
            <td className="row-actions"><Link className="text-action" to={detailUrl(item, objectType)}>{text("查看详情", "View details")}</Link></td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  );
}
