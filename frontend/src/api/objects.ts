import { apiRequest, apiRequestEnvelope, type PaginatedEnvelope, type PaginationMeta } from "./client";

const API_ROOT = "/api/v1";
const DEFAULT_PAGE_SIZE = 20;

export const BUILTIN_OBJECT_TYPES = [
  "timesheet_header",
  "expense_claim",
  "purchase_request",
  "sales_quotation",
  "sales_order",
  "sales_return",
  "invoice",
  "payment",
  "billing_account",
  "resource_booking",
] as const;

export type BuiltinObjectType = (typeof BUILTIN_OBJECT_TYPES)[number];
export type ObjectEntityType = BuiltinObjectType | "business_object";
export type ObjectEntityKind = "builtin" | "business_object";

export type ObjectTypeDefinition = {
  id: string;
  tenant_id: string;
  entity_kind: ObjectEntityKind;
  object_type: string;
  title: string | null;
  description: string | null;
  json_schema: Record<string, unknown>;
  state_machine: Record<string, unknown> | null;
  version: number;
  status: "active" | "archived";
  created_by: string | null;
  created_at: string;
  updated_at: string | null;
};

export type WorkflowDefinition = {
  id: string;
  tenant_id: string;
  entity_kind: ObjectEntityKind;
  object_type: string;
  name: string;
  version: number;
  definition_text: string;
  status: "active" | "superseded";
  created_by: string | null;
  created_at: string;
};

export type ObjectTypeSummary = {
  entityKind: ObjectEntityKind;
  objectType: string;
  title: string;
  description: string | null;
  status: "active" | "archived" | "builtin";
  definitionVersion: number | null;
  hasWorkflow: boolean;
  statuses: string[];
  count: number;
};

export type ObjectDirectoryEntry = {
  entity_kind: ObjectEntityKind;
  object_type: string;
  count: number;
  title: string | null;
  definition_status: "active" | "archived" | null;
};

export type ObjectDisplayNames = {
  employees: Record<string, string>;
  actors: Record<string, string>;
};

export type ObjectDirectory = ObjectDisplayNames & {
  types: ObjectTypeSummary[];
};

export type BusinessObject = {
  id: string;
  object_type: string;
  title: string;
  summary: string | null;
  payload: Record<string, unknown>;
  source_text: string | null;
  status: string;
  created_by: string | null;
  created_at: string;
  updated_at: string | null;
  deleted_at: string | null;
  deleted_by: string | null;
  delete_reason: string | null;
};

export type TimesheetHeader = {
  id: string;
  employee_id: string;
  period_start: string;
  period_end: string;
  status: string;
  submitted_at: string | null;
  source_report_text: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type ExpenseClaim = {
  id: string;
  employee_id: string;
  title: string;
  claim_date: string | null;
  currency: string;
  status: string;
  submitted_at: string | null;
  source_report_text: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type PurchaseRequest = {
  id: string;
  employee_id: string;
  title: string;
  request_date: string | null;
  needed_by: string | null;
  vendor_id: string | null;
  vendor_name_snapshot: string | null;
  currency: string;
  status: string;
  submitted_at: string | null;
  source_report_text: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type SalesQuotation = {
  id: string;
  employee_id: string;
  title: string;
  quote_number: string;
  revision_no: number;
  revision_of_id: string | null;
  customer_id: string | null;
  customer_name_snapshot: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  quote_date: string | null;
  valid_until: string | null;
  currency: string;
  payment_terms: string | null;
  delivery_terms: string | null;
  remarks: string | null;
  status: string;
  submitted_at: string | null;
  sent_at: string | null;
  closed_at: string | null;
  outcome_note: string | null;
  project_id: string | null;
  source_report_text: string | null;
  total_amount: number | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type SalesOrder = {
  id: string;
  employee_id: string;
  title: string;
  order_no: string;
  order_date: string | null;
  promised_date: string | null;
  customer_id: string | null;
  customer_name_snapshot: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  quotation_id: string | null;
  source_quote_number: string | null;
  contract_no: string | null;
  currency: string;
  payment_terms: string | null;
  delivery_terms: string | null;
  logistics_company: string | null;
  logistics_tracking_no: string | null;
  ship_to_address: string | null;
  remarks: string | null;
  status: string;
  submitted_at: string | null;
  shipped_at: string | null;
  signed_at: string | null;
  project_id: string | null;
  source_report_text: string | null;
  total_amount: number | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type Invoice = {
  id: string;
  invoice_no: string;
  // `payroll` is a payslip: the counterparty is the employee it pays, and
  // reading it needs `payroll.read` — see docs/payroll.md
  direction: "sales" | "purchase" | "payroll" | "reimbursement";
  invoice_type: string | null;
  employee_id: string;
  customer_id: string | null;
  vendor_id: string | null;
  payee_employee_id: string | null;
  counterparty_name_snapshot: string | null;
  title: string;
  period_start: string | null;
  period_end: string | null;
  invoice_date: string | null;
  due_date: string | null;
  currency: string;
  total_amount: number | null;
  tax_amount: number | null;
  applied_amount: number;
  tax_invoice_code: string | null;
  tax_invoice_number: string | null;
  attachment_id: string | null;
  sales_order_id: string | null;
  purchase_order_id: string | null;
  project_id: string | null;
  status: string;
  submitted_at: string | null;
  issued_at: string | null;
  remarks: string | null;
  source_report_text: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type Payment = {
  id: string;
  payment_no: string;
  direction: "inbound" | "outbound";
  payment_method: string | null;
  employee_id: string;
  customer_id: string | null;
  vendor_id: string | null;
  payee_employee_id: string | null;
  counterparty_name_snapshot: string | null;
  payment_date: string | null;
  amount: number;
  currency: string;
  applied_amount: number;
  bank_account: string | null;
  counterparty_account: string | null;
  reference_no: string | null;
  attachment_id: string | null;
  status: string;
  submitted_at: string | null;
  paid_at: string | null;
  remarks: string | null;
  source_report_text: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type BillingAccount = {
  id: string;
  account_code: string;
  name: string;
  unit_type: "currency" | "points";
  unit: string;
  customer_id: string | null;
  vendor_id: string | null;
  employee_id: string | null;
  owner_name_snapshot: string | null;
  credit_limit: number;
  balance: number;
  available_amount: number;
  valid_from: string | null;
  valid_until: string | null;
  status: "active" | "frozen" | "closed";
  external_account_id: string | null;
  description: string | null;
  remarks: string | null;
  source_report_text: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type ResourceBooking = {
  id: string;
  resource_id: string;
  booked_by_employee_id: string;
  booking_type: string | null;
  title: string;
  start_at: string;
  end_at: string;
  quantity: number;
  status: "confirmed" | "cancelled";
  source_text: string | null;
  notes: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
  cancelled_at: string | null;
  cancelled_by: string | null;
  cancel_reason: string | null;
};

export type ObjectListRecord =
  | { entityType: "business_object"; record: BusinessObject }
  | { entityType: "timesheet_header"; record: TimesheetHeader }
  | { entityType: "expense_claim"; record: ExpenseClaim }
  | { entityType: "purchase_request"; record: PurchaseRequest }
  | { entityType: "sales_quotation"; record: SalesQuotation }
  | { entityType: "sales_order"; record: SalesOrder }
  | { entityType: "invoice"; record: Invoice }
  | { entityType: "payment"; record: Payment }
  | { entityType: "billing_account"; record: BillingAccount }
  | { entityType: "resource_booking"; record: ResourceBooking };

export type TimesheetEntry = {
  id: string;
  header_id: string;
  employee_id: string;
  work_date: string;
  project_id: string | null;
  project_name_snapshot: string | null;
  client: string | null;
  task: string | null;
  hours: number;
  work_type: string;
  notes: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type ExpenseItem = {
  id: string;
  claim_id: string;
  employee_id: string;
  expense_date: string;
  category: string;
  amount: number;
  tax_amount: number | null;
  vendor_id: string | null;
  vendor_name?: string | null;
  merchant: string | null;
  invoice_number: string | null;
  invoice_type: string | null;
  project_id: string | null;
  project_name_snapshot: string | null;
  client: string | null;
  attachment_id: string | null;
  extracted_fields: Record<string, unknown>;
  notes: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type PurchaseRequestItem = {
  id: string;
  request_id: string;
  product_id: string | null;
  sku_id: string | null;
  product_name_snapshot: string | null;
  spec: string | null;
  quantity: number;
  unit: string | null;
  unit_price: number | null;
  amount: number | null;
  attachment_id: string | null;
  notes: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
  product?: {
    id: string;
    product_code: string | null;
    name: string;
    spec: string | null;
    unit: string | null;
  } | null;
  sku?: {
    id: string;
    product_id: string;
    sku_code: string | null;
    variant_attrs: Record<string, unknown>;
  } | null;
  sku_pending?: boolean;
};

export type SalesQuotationItem = {
  id: string;
  quotation_id: string;
  line_no: number | null;
  product_id: string | null;
  sku_id: string | null;
  product_name_snapshot: string | null;
  spec: string | null;
  quantity: number;
  unit: string | null;
  unit_price: number | null;
  list_price_snapshot: number | null;
  tax_rate: number | null;
  amount: number | null;
  is_gift: boolean;
  lead_time: string | null;
  attachment_id: string | null;
  notes: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
  product?: {
    id: string;
    product_code: string | null;
    name: string;
    spec: string | null;
    unit: string | null;
    list_price?: number | null;
  } | null;
  sku?: {
    id: string;
    product_id: string;
    sku_code: string | null;
    variant_attrs: Record<string, unknown>;
    list_price?: number | null;
  } | null;
  sku_pending?: boolean;
};

export type SalesOrderItem = {
  id: string;
  order_id: string;
  line_no: number | null;
  product_id: string | null;
  sku_id: string | null;
  product_name_snapshot: string | null;
  spec: string | null;
  quantity: number;
  unit: string | null;
  unit_price: number | null;
  list_price_snapshot: number | null;
  tax_rate: number | null;
  amount: number | null;
  is_gift: boolean;
  promised_date: string | null;
  attachment_id: string | null;
  notes: string | null;
  custom_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
  product?: {
    id: string;
    product_code: string | null;
    name: string;
    spec: string | null;
    unit: string | null;
    list_price?: number | null;
  } | null;
  sku?: {
    id: string;
    product_id: string;
    sku_code: string | null;
    variant_attrs: Record<string, unknown>;
    list_price?: number | null;
  } | null;
  sku_pending?: boolean;
};

export type Attachment = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  uploaded_by: string | null;
  created_at: string;
};

export type ApprovalRecord = {
  id: string;
  entity_type: string;
  entity_id: string;
  round_no: number;
  sequence_no: number;
  action: string;
  approver_id: string | null;
  approver_role: string | null;
  comment: string | null;
  source: string | null;
  metadata: Record<string, unknown>;
  acted_at: string;
  created_at: string;
};

export type Todo = {
  id: string;
  employee_id: string;
  entity_type: string;
  entity_id: string;
  title: string;
  description: string | null;
  todo_type: string | null;
  status: "open" | "completed";
  due_at: string | null;
  created_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
  completed_at: string | null;
  completed_by: string | null;
};

export type AuditLog = {
  id: number;
  action: string;
  entity_type: string;
  entity_id: string;
  actor: string | null;
  detail: Record<string, unknown>;
  created_at: string;
};

export type BusinessObjectLink = {
  id: string;
  source_object_id: string;
  target_object_id: string;
  link_type: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

type TimesheetDetailResponse = {
  header: TimesheetHeader;
  entries: TimesheetEntry[];
  approval_records: ApprovalRecord[];
};

type ExpenseDetailResponse = {
  claim: ExpenseClaim;
  items: ExpenseItem[];
  approval_records: ApprovalRecord[];
  attachments: Attachment[];
  total_amount: number;
  total_tax_amount: number;
};

type PurchaseDetailResponse = {
  request: PurchaseRequest;
  items: PurchaseRequestItem[];
  approval_records: ApprovalRecord[];
  attachments: Attachment[];
  estimated_total: number;
  unpriced_item_count: number;
  pending_sku_count: number;
};

type SalesQuotationDetailResponse = {
  quotation: SalesQuotation;
  items: SalesQuotationItem[];
  approval_records: ApprovalRecord[];
  attachments: Attachment[];
  computed_total: number;
  unpriced_item_count: number;
  pending_sku_count: number;
  revisions: SalesQuotation[];
};

type SalesOrderDetailResponse = {
  order: SalesOrder;
  items: SalesOrderItem[];
  approval_records: ApprovalRecord[];
  attachments: Attachment[];
  computed_total: number;
  unpriced_item_count: number;
  pending_sku_count: number;
  quotation: SalesQuotation | null;
};

type InvoiceDetailResponse = {
  invoice: Invoice;
  approval_records: ApprovalRecord[];
  billed_total: number;
  applied_amount: number;
  outstanding_amount: number;
};

type BillingAccountDetailResponse = {
  account: BillingAccount;
  balance: number;
  credit_limit: number;
  available_amount: number;
  expiring_amount: number;
  expiring_entry_count: number;
};

type PaymentDetailResponse = {
  payment: Payment;
  approval_records: ApprovalRecord[];
  applied_amount: number;
  unapplied_amount: number;
};

type BusinessObjectDetailResponse = {
  business_object: BusinessObject;
  links: BusinessObjectLink[];
  approval_records: ApprovalRecord[];
  todos: Todo[];
  audit_logs: AuditLog[];
  object_type_definition: ObjectTypeDefinition | null;
  workflow_definitions: WorkflowDefinition[];
};

export type ObjectDetailIssue = {
  section: string;
  message: string;
};

export type ObjectDetail = ObjectDisplayNames & {
  entityType: ObjectEntityType;
  entityKind: ObjectEntityKind;
  objectType: string;
  heading: string;
  subject: ObjectListRecord;
  timesheetEntries: TimesheetEntry[];
  expenseItems: ExpenseItem[];
  purchaseItems: PurchaseRequestItem[];
  salesQuotationItems: SalesQuotationItem[];
  salesOrderItems: SalesOrderItem[];
  attachments: Attachment[];
  expenseTotals: { totalAmount: number; totalTaxAmount: number } | null;
  purchaseTotals: { estimatedTotal: number; unpricedItemCount: number; pendingSkuCount: number } | null;
  salesQuotationTotals: { computedTotal: number; unpricedItemCount: number; pendingSkuCount: number } | null;
  salesOrderTotals: { computedTotal: number; unpricedItemCount: number; pendingSkuCount: number } | null;
  revisions: SalesQuotation[];
  quotationLink: SalesQuotation | null;
  links: BusinessObjectLink[];
  workflows: WorkflowDefinition[];
  approvals: ApprovalRecord[];
  todos: Todo[];
  audits: AuditLog[];
  issues: ObjectDetailIssue[];
};

type ObjectLocale = "zh-CN" | "en";

function localText(locale: ObjectLocale, chinese: string, english: string): string {
  return locale === "en" ? english : chinese;
}

const BUILTIN_TITLES: Record<BuiltinObjectType, [string, string]> = {
  timesheet_header: ["工时单", "Timesheet"],
  expense_claim: ["报销单", "Expense claim"],
  purchase_request: ["采购申请", "Purchase request"],
  sales_quotation: ["销售报价", "Sales quotation"],
  sales_order: ["销售订单", "Sales order"],
  sales_return: ["销售退单", "Sales return"],
  invoice: ["发票", "Invoice"],
  payment: ["收付款", "Payment"],
  billing_account: ["往来账户", "Billing account"],
  resource_booking: ["资源预订", "Resource booking"],
};

const BUILTIN_STATUSES: Record<BuiltinObjectType, string[]> = {
  timesheet_header: [],
  expense_claim: [],
  purchase_request: [],
  sales_quotation: [],
  sales_order: [],
  sales_return: [],
  invoice: [],
  payment: [],
  billing_account: ["active", "frozen", "closed"],
  resource_booking: ["confirmed", "cancelled"],
};

const ENTITY_ALIASES: Record<ObjectEntityType, string[]> = {
  timesheet_header: ["timesheet_header"],
  expense_claim: ["expense_claim"],
  purchase_request: ["purchase_request"],
  sales_quotation: ["sales_quotation"],
  sales_order: ["sales_order"],
  // a sales return IS a sales_orders row; its todos/approvals say sales_order
  sales_return: ["sales_order"],
  invoice: ["invoice"],
  payment: ["payment"],
  billing_account: ["billing_account"],
  resource_booking: ["resource_booking"],
  business_object: ["business_object", "approval_target"],
};

export function isObjectEntityType(value: string | undefined): value is ObjectEntityType {
  return value === "business_object" || BUILTIN_OBJECT_TYPES.includes(value as BuiltinObjectType);
}

function apiUrl(path: string, params: Record<string, string | number | boolean | undefined> = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return `${API_ROOT}${path}${query ? `?${query}` : ""}`;
}

function statesFromDefinition(definition: ObjectTypeDefinition | undefined): string[] {
  const states = definition?.state_machine?.states;
  return Array.isArray(states)
    ? states.filter((state): state is string => typeof state === "string")
    : [];
}

export async function getObjectDirectory(locale: ObjectLocale = "zh-CN"): Promise<ObjectDirectory> {
  const [definitions, workflows, entries] = await Promise.all([
    apiRequest<ObjectTypeDefinition[]>(apiUrl("/object-type-definitions")),
    apiRequest<WorkflowDefinition[]>(apiUrl("/workflow-definitions")),
    apiRequest<ObjectDirectoryEntry[]>(apiUrl("/object-directory")),
  ]);
  const workflowKeys = new Set(workflows.map((workflow) => `${workflow.entity_kind}:${workflow.object_type}`));
  const byKey = new Map(definitions.map((definition) => [
    `${definition.entity_kind}:${definition.object_type}`,
    definition,
  ]));
  const entriesByKey = new Map(entries.map((entry) => [
    `${entry.entity_kind}:${entry.object_type}`,
    entry,
  ]));
  const builtins = BUILTIN_OBJECT_TYPES.map<ObjectTypeSummary>((objectType) => {
    const definition = byKey.get(`builtin:${objectType}`);
    return {
      entityKind: "builtin",
      objectType,
      title: definition?.title || localText(locale, ...BUILTIN_TITLES[objectType]),
      description: definition?.description ?? null,
      status: definition?.status ?? "builtin",
      definitionVersion: definition?.version ?? null,
      hasWorkflow: workflowKeys.has(`builtin:${objectType}`),
      statuses: statesFromDefinition(definition).length > 0
        ? statesFromDefinition(definition)
        : BUILTIN_STATUSES[objectType],
      count: entriesByKey.get(`builtin:${objectType}`)?.count ?? 0,
    };
  });
  const customNames = new Set([
    ...definitions.filter((definition) => definition.entity_kind === "business_object").map((definition) => definition.object_type),
    ...entries.filter((entry) => entry.entity_kind === "business_object").map((entry) => entry.object_type),
  ]);
  const custom = Array.from(customNames).sort().map<ObjectTypeSummary>((objectType) => {
    const definition = byKey.get(`business_object:${objectType}`);
    const entry = entriesByKey.get(`business_object:${objectType}`);
    return {
      entityKind: "business_object",
      objectType,
      title: definition?.title || entry?.title || objectType,
      description: definition?.description ?? (definition ? null : localText(locale, "已有数据，尚未设置字段规则。", "Data exists, but no field rules have been defined yet.")),
      status: definition?.status ?? "active",
      definitionVersion: definition?.version ?? null,
      hasWorkflow: workflowKeys.has(`business_object:${objectType}`),
      statuses: statesFromDefinition(definition),
      count: entry?.count ?? 0,
    };
  });
  return { employees: {}, actors: {}, types: [...builtins, ...custom] };
}

export async function resolveObjectDisplayNames(
  employeeIds: string[],
  actorLabels: string[],
): Promise<ObjectDisplayNames> {
  const employees = Array.from(new Set(employeeIds.filter(Boolean))).slice(0, 200);
  const actors = Array.from(new Set(actorLabels.filter(Boolean))).slice(0, 200);
  if (employees.length === 0 && actors.length === 0) return { employees: {}, actors: {} };
  return apiRequest<ObjectDisplayNames>(apiUrl("/directory/display-names/resolve"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ employee_ids: employees, actor_labels: actors }),
  });
}

export function resolveObjectListDisplayNames(records: ObjectListRecord[]): Promise<ObjectDisplayNames> {
  const employeeIds: string[] = [];
  const actorLabels: string[] = [];
  for (const item of records) {
    if (item.entityType === "business_object") {
      if (item.record.created_by) actorLabels.push(item.record.created_by);
      if (item.record.deleted_by) actorLabels.push(item.record.deleted_by);
    } else if (item.entityType === "resource_booking") {
      employeeIds.push(item.record.booked_by_employee_id);
      if (item.record.cancelled_by) actorLabels.push(item.record.cancelled_by);
    } else if (item.entityType === "billing_account") {
      // an account's owner may be a customer or a vendor rather than a person
      if (item.record.employee_id) employeeIds.push(item.record.employee_id);
    } else {
      employeeIds.push(item.record.employee_id);
    }
  }
  return resolveObjectDisplayNames(employeeIds, actorLabels);
}

export type ObjectListFilters = {
  entityType: ObjectEntityType;
  objectType: string;
  page?: number;
  size?: number;
  keyword?: string;
  status?: string;
};

function listEndpoint(filters: ObjectListFilters): string {
  const common = {
    status: filters.status || undefined,
    keyword: filters.keyword?.trim() || undefined,
    page: Math.max(1, filters.page ?? 1),
    size: Math.max(1, filters.size ?? DEFAULT_PAGE_SIZE),
  };
  switch (filters.entityType) {
    case "business_object":
      return apiUrl("/business-objects", {
        ...common,
        object_type: filters.objectType,
        include_deleted: true,
      });
    case "timesheet_header":
      return apiUrl("/timesheet-headers", { ...common, include_deleted: true });
    case "expense_claim":
      return apiUrl("/expense-claims", { ...common, include_deleted: true });
    case "purchase_request":
      return apiUrl("/purchase-requests", { ...common, include_deleted: true });
    case "sales_quotation":
      return apiUrl("/sales-quotations", { ...common, include_deleted: true });
    case "sales_order":
      // orders and returns share the table; each console page shows its kind
      return apiUrl("/sales-orders", { ...common, order_kind: "order", include_deleted: true });
    case "sales_return":
      return apiUrl("/sales-orders", { ...common, order_kind: "return", include_deleted: true });
    case "invoice":
      return apiUrl("/invoices", { ...common, include_deleted: true });
    case "payment":
      return apiUrl("/payments", { ...common, include_deleted: true });
    case "billing_account":
      return apiUrl("/billing-accounts", { ...common, include_deleted: true });
    case "resource_booking":
      return apiUrl("/resource-bookings", common);
  }
}

function normalizeRecords(entityType: ObjectEntityType, records: unknown[]): ObjectListRecord[] {
  switch (entityType) {
    case "business_object":
      return (records as BusinessObject[]).map((record) => ({ entityType, record }));
    case "timesheet_header":
      return (records as TimesheetHeader[]).map((record) => ({ entityType, record }));
    case "expense_claim":
      return (records as ExpenseClaim[]).map((record) => ({ entityType, record }));
    case "purchase_request":
      return (records as PurchaseRequest[]).map((record) => ({ entityType, record }));
    case "sales_quotation":
      return (records as SalesQuotation[]).map((record) => ({ entityType, record }));
    case "sales_order":
      return (records as SalesOrder[]).map((record) => ({ entityType, record }));
    case "sales_return":
      // tagged as sales_order so search, links and the detail page — which
      // render the same row — need no second case anywhere downstream
      return (records as SalesOrder[]).map((record) => ({ entityType: "sales_order" as const, record }));
    case "invoice":
      return (records as Invoice[]).map((record) => ({ entityType, record }));
    case "payment":
      return (records as Payment[]).map((record) => ({ entityType, record }));
    case "billing_account":
      return (records as BillingAccount[]).map((record) => ({ entityType, record }));
    case "resource_booking":
      return (records as ResourceBooking[]).map((record) => ({ entityType, record }));
  }
}

function searchableText(item: ObjectListRecord): string {
  switch (item.entityType) {
    case "business_object":
      {
      const record = item.record;
      return [record.title, record.summary, record.status, record.created_by, JSON.stringify(record.payload)].join(" ");
      }
    case "timesheet_header":
      {
      const record = item.record;
      return [record.employee_id, record.period_start, record.period_end, record.status].join(" ");
      }
    case "expense_claim":
      {
      const record = item.record;
      return [record.employee_id, record.title, record.claim_date, record.currency, record.status].join(" ");
      }
    case "purchase_request":
      {
      const record = item.record;
      return [record.employee_id, record.title, record.vendor_name_snapshot, record.needed_by, record.status].join(" ");
      }
    case "sales_quotation":
      {
      const record = item.record;
      return [record.employee_id, record.title, record.quote_number, record.customer_name_snapshot, record.valid_until, record.status].join(" ");
      }
    case "sales_order":
      {
      const record = item.record;
      return [record.employee_id, record.title, record.order_no, record.customer_name_snapshot, record.source_quote_number, record.logistics_tracking_no, record.status].join(" ");
      }
    case "invoice":
      {
      const record = item.record;
      return [record.invoice_no, record.title, record.counterparty_name_snapshot, record.tax_invoice_number, record.direction, record.status].join(" ");
      }
    case "payment":
      {
      const record = item.record;
      return [record.payment_no, record.counterparty_name_snapshot, record.reference_no, record.direction, record.status].join(" ");
      }
    case "billing_account":
      {
      const record = item.record;
      return [record.account_code, record.name, record.owner_name_snapshot, record.unit, record.status].join(" ");
      }
    case "resource_booking":
      {
      const record = item.record;
      return [record.title, record.booked_by_employee_id, record.resource_id, record.booking_type, record.status].join(" ");
      }
  }
}

export async function listObjectRecords(filters: ObjectListFilters): Promise<PaginatedEnvelope<ObjectListRecord>> {
  const response = await apiRequestEnvelope<unknown[], Partial<PaginationMeta>>(listEndpoint(filters));
  const serverMeta = response.meta;
  const serverPaginated = Number.isInteger(serverMeta.page)
    && Number.isInteger(serverMeta.page_size)
    && Number.isInteger(serverMeta.pages)
    && Number.isInteger(serverMeta.total);
  if (serverPaginated) {
    const pages = Math.max(1, serverMeta.pages!);
    return {
      data: normalizeRecords(filters.entityType, response.data),
      meta: {
        total: serverMeta.total!,
        page: Math.min(Math.max(1, serverMeta.page!), pages),
        page_size: serverMeta.page_size!,
        pages,
      },
    };
  }

  // Compatibility for deployments that have not picked up server-side object
  // pagination yet. Once page metadata is present, no full-list filtering or
  // slicing runs in the browser.
  const keyword = filters.keyword?.trim().toLocaleLowerCase("zh-CN") ?? "";
  const all = normalizeRecords(filters.entityType, response.data).filter((item) =>
    keyword === "" || searchableText(item).toLocaleLowerCase("zh-CN").includes(keyword));
  const pageSize = Math.max(1, filters.size ?? DEFAULT_PAGE_SIZE);
  const pages = Math.max(1, Math.ceil(all.length / pageSize));
  const page = Math.min(Math.max(1, filters.page ?? 1), pages);
  const start = (page - 1) * pageSize;
  const meta: PaginationMeta = { total: all.length, page, page_size: pageSize, pages };
  return { data: all.slice(start, start + pageSize), meta };
}

function errorMessage(error: unknown, locale: ObjectLocale): string {
  return error instanceof Error ? error.message : localText(locale, "请求失败", "Request failed");
}

async function optional<T>(
  section: string,
  promise: Promise<T>,
  fallback: T,
  issues: ObjectDetailIssue[],
  locale: ObjectLocale,
): Promise<T> {
  try {
    return await promise;
  } catch (error) {
    issues.push({ section, message: errorMessage(error, locale) });
    return fallback;
  }
}

async function listForAliases<T>(
  path: string,
  aliases: string[],
  recordId: string,
  extra: Record<string, string | number | boolean | undefined> = {},
): Promise<T[]> {
  const collections = await Promise.all(aliases.map((entityType) =>
    apiRequest<T[]>(apiUrl(path, { entity_type: entityType, entity_id: recordId, ...extra }))));
  return collections.flat();
}

function uniqueBy<T>(items: T[], key: (item: T) => string | number): T[] {
  return Array.from(new Map(items.map((item) => [key(item), item])).values());
}

type PrimaryDetail = {
  subject: ObjectListRecord;
  objectType: string;
  heading: string;
  timesheetEntries: TimesheetEntry[];
  expenseItems: ExpenseItem[];
  purchaseItems: PurchaseRequestItem[];
  salesQuotationItems: SalesQuotationItem[];
  salesOrderItems: SalesOrderItem[];
  attachments: Attachment[];
  approvals: ApprovalRecord[];
  expenseTotals: ObjectDetail["expenseTotals"];
  purchaseTotals: ObjectDetail["purchaseTotals"];
  salesQuotationTotals: ObjectDetail["salesQuotationTotals"];
  salesOrderTotals: ObjectDetail["salesOrderTotals"];
  revisions: SalesQuotation[];
  quotationLink: SalesQuotation | null;
  related?: {
    links: BusinessObjectLink[];
    workflows: WorkflowDefinition[];
    todos: Todo[];
    audits: AuditLog[];
  };
};

async function getPrimaryDetail(entityType: ObjectEntityType, recordId: string, locale: ObjectLocale): Promise<PrimaryDetail> {
  if (entityType === "sales_return") {
    // a sales return IS a sales_orders row; its detail is the order's detail
    return getPrimaryDetail("sales_order", recordId, locale);
  }
  const id = encodeURIComponent(recordId);
  if (entityType === "business_object") {
    const detail = await apiRequest<BusinessObjectDetailResponse>(apiUrl(`/business-objects/${id}/detail`, { include_deleted: true }));
    const record = detail.business_object;
    return {
      subject: { entityType, record },
      objectType: record.object_type,
      heading: record.title,
      timesheetEntries: [], expenseItems: [], purchaseItems: [], salesQuotationItems: [], salesOrderItems: [], attachments: [], approvals: detail.approval_records,
      expenseTotals: null, purchaseTotals: null, salesQuotationTotals: null, salesOrderTotals: null, revisions: [], quotationLink: null,
      related: {
        links: detail.links,
        workflows: detail.workflow_definitions,
        todos: detail.todos,
        audits: detail.audit_logs,
      },
    };
  }
  if (entityType === "timesheet_header") {
    const detail = await apiRequest<TimesheetDetailResponse>(apiUrl(`/timesheet-headers/${id}/detail`, { include_deleted: true }));
    return {
      subject: { entityType, record: detail.header }, objectType: entityType,
      heading: `${localText(locale, "工时单", "Timesheet")} ${detail.header.period_start} → ${detail.header.period_end}`,
      timesheetEntries: detail.entries, expenseItems: [], purchaseItems: [], salesQuotationItems: [], salesOrderItems: [], attachments: [],
      approvals: detail.approval_records, expenseTotals: null, purchaseTotals: null, salesQuotationTotals: null, salesOrderTotals: null, revisions: [], quotationLink: null,
    };
  }
  if (entityType === "expense_claim") {
    const detail = await apiRequest<ExpenseDetailResponse>(apiUrl(`/expense-claims/${id}/detail`, { include_deleted: true }));
    return {
      subject: { entityType, record: detail.claim }, objectType: entityType,
      heading: detail.claim.title,
      timesheetEntries: [], expenseItems: detail.items, purchaseItems: [], salesQuotationItems: [], salesOrderItems: [], attachments: detail.attachments,
      approvals: detail.approval_records,
      expenseTotals: { totalAmount: detail.total_amount, totalTaxAmount: detail.total_tax_amount },
      purchaseTotals: null, salesQuotationTotals: null, salesOrderTotals: null, revisions: [], quotationLink: null,
    };
  }
  if (entityType === "purchase_request") {
    const detail = await apiRequest<PurchaseDetailResponse>(apiUrl(`/purchase-requests/${id}/detail`, { include_deleted: true }));
    return {
      subject: { entityType, record: detail.request }, objectType: entityType,
      heading: detail.request.title,
      timesheetEntries: [], expenseItems: [], purchaseItems: detail.items, salesQuotationItems: [], salesOrderItems: [], attachments: detail.attachments,
      approvals: detail.approval_records, expenseTotals: null,
      purchaseTotals: {
        estimatedTotal: detail.estimated_total,
        unpricedItemCount: detail.unpriced_item_count,
        pendingSkuCount: detail.pending_sku_count,
      },
      salesQuotationTotals: null, salesOrderTotals: null, revisions: [], quotationLink: null,
    };
  }
  if (entityType === "sales_quotation") {
    const detail = await apiRequest<SalesQuotationDetailResponse>(apiUrl(`/sales-quotations/${id}/detail`, { include_deleted: true }));
    return {
      subject: { entityType, record: detail.quotation }, objectType: entityType,
      heading: `${detail.quotation.quote_number} · ${detail.quotation.title}`,
      timesheetEntries: [], expenseItems: [], purchaseItems: [], salesQuotationItems: detail.items, salesOrderItems: [], attachments: detail.attachments,
      approvals: detail.approval_records, expenseTotals: null, purchaseTotals: null,
      salesQuotationTotals: {
        computedTotal: detail.computed_total,
        unpricedItemCount: detail.unpriced_item_count,
        pendingSkuCount: detail.pending_sku_count,
      },
      salesOrderTotals: null, revisions: detail.revisions, quotationLink: null,
    };
  }
  if (entityType === "sales_order") {
    const detail = await apiRequest<SalesOrderDetailResponse>(apiUrl(`/sales-orders/${id}/detail`, { include_deleted: true }));
    return {
      subject: { entityType, record: detail.order }, objectType: entityType,
      heading: `${detail.order.order_no} · ${detail.order.title}`,
      timesheetEntries: [], expenseItems: [], purchaseItems: [], salesQuotationItems: [], salesOrderItems: detail.items, attachments: detail.attachments,
      approvals: detail.approval_records, expenseTotals: null, purchaseTotals: null, salesQuotationTotals: null,
      salesOrderTotals: {
        computedTotal: detail.computed_total,
        unpricedItemCount: detail.unpriced_item_count,
        pendingSkuCount: detail.pending_sku_count,
      },
      revisions: [], quotationLink: detail.quotation ?? null,
    };
  }
  if (entityType === "invoice") {
    const detail = await apiRequest<InvoiceDetailResponse>(apiUrl(`/invoices/${id}/detail`, { include_deleted: true }));
    return {
      subject: { entityType, record: detail.invoice }, objectType: entityType,
      heading: `${detail.invoice.invoice_no} · ${detail.invoice.title}`,
      timesheetEntries: [], expenseItems: [], purchaseItems: [], salesQuotationItems: [], salesOrderItems: [], attachments: [],
      approvals: detail.approval_records, expenseTotals: null, purchaseTotals: null, salesQuotationTotals: null,
      salesOrderTotals: null, revisions: [], quotationLink: null,
    };
  }
  if (entityType === "payment") {
    const detail = await apiRequest<PaymentDetailResponse>(apiUrl(`/payments/${id}/detail`, { include_deleted: true }));
    return {
      subject: { entityType, record: detail.payment }, objectType: entityType,
      heading: detail.payment.payment_no,
      timesheetEntries: [], expenseItems: [], purchaseItems: [], salesQuotationItems: [], salesOrderItems: [], attachments: [],
      approvals: detail.approval_records, expenseTotals: null, purchaseTotals: null, salesQuotationTotals: null,
      salesOrderTotals: null, revisions: [], quotationLink: null,
    };
  }
  if (entityType === "billing_account") {
    const detail = await apiRequest<BillingAccountDetailResponse>(
      apiUrl(`/billing-accounts/${id}/detail`, { include_deleted: true }),
    );
    return {
      subject: { entityType, record: detail.account }, objectType: entityType,
      heading: `${detail.account.account_code} · ${detail.account.name}`,
      timesheetEntries: [], expenseItems: [], purchaseItems: [], salesQuotationItems: [], salesOrderItems: [], attachments: [],
      approvals: [], expenseTotals: null, purchaseTotals: null, salesQuotationTotals: null,
      salesOrderTotals: null, revisions: [], quotationLink: null,
    };
  }
  const record = await apiRequest<ResourceBooking>(apiUrl(`/resource-bookings/${id}`));
  return {
    subject: { entityType, record }, objectType: entityType, heading: record.title,
    timesheetEntries: [], expenseItems: [], purchaseItems: [], salesQuotationItems: [], salesOrderItems: [], attachments: [], approvals: [],
    expenseTotals: null, purchaseTotals: null, salesQuotationTotals: null, salesOrderTotals: null, revisions: [], quotationLink: null,
  };
}

export async function getObjectDetail(entityType: ObjectEntityType, recordId: string, locale: ObjectLocale = "zh-CN"): Promise<ObjectDetail> {
  const primary = await getPrimaryDetail(entityType, recordId, locale);
  const issues: ObjectDetailIssue[] = [];
  const aliases = ENTITY_ALIASES[entityType];
  const entityKind: ObjectEntityKind = entityType === "business_object" ? "business_object" : "builtin";
  const workflowPromise = primary.related
    ? Promise.resolve(primary.related.workflows)
    : apiRequest<WorkflowDefinition[]>(apiUrl("/workflow-definitions", {
      entity_kind: entityKind,
      object_type: primary.objectType,
      history: true,
    }));
  const approvalPromise = primary.related
    ? Promise.resolve(primary.approvals)
    : primary.approvals.length > 0 || entityType !== "business_object" && entityType !== "resource_booking"
    ? Promise.resolve(primary.approvals)
    : listForAliases<ApprovalRecord>("/approval-records", aliases, recordId);
  const linkPromise = primary.related
    ? Promise.resolve(primary.related.links)
    : entityType === "business_object"
    ? Promise.all([
      apiRequest<BusinessObjectLink[]>(apiUrl("/business-object-links", { source_object_id: recordId })),
      apiRequest<BusinessObjectLink[]>(apiUrl("/business-object-links", { target_object_id: recordId })),
    ]).then(([outgoing, incoming]) => uniqueBy([...outgoing, ...incoming], (link) => link.id))
    : Promise.resolve([] as BusinessObjectLink[]);

  const [workflows, approvals, todos, audits, links] = await Promise.all([
    optional(localText(locale, "流程版本", "Workflow versions"), workflowPromise, [], issues, locale),
    optional(localText(locale, "审批记录", "Approval history"), approvalPromise, primary.approvals, issues, locale),
    optional(localText(locale, "待办", "Todos"), primary.related ? Promise.resolve(primary.related.todos) : listForAliases<Todo>("/todos", aliases, recordId), [], issues, locale),
    optional(localText(locale, "审计轨迹", "Audit trail"), primary.related ? Promise.resolve(primary.related.audits) : listForAliases<AuditLog>("/audit-logs", aliases, recordId, { limit: 200 }), [], issues, locale),
    optional(localText(locale, "关联对象", "Related objects"), linkPromise, [], issues, locale),
  ]);
  const employeeIds = [
    ...primary.timesheetEntries.map((entry) => entry.employee_id),
    ...primary.expenseItems.map((item) => item.employee_id),
    ...todos.map((todo) => todo.employee_id),
  ];
  const actorLabels = [
    ...approvals.map((approval) => approval.approver_id),
    ...todos.flatMap((todo) => [todo.created_by, todo.completed_by]),
    ...audits.map((audit) => audit.actor),
    ...workflows.map((workflow) => workflow.created_by),
    ...primary.attachments.map((attachment) => attachment.uploaded_by),
  ].filter((value): value is string => Boolean(value));
  if (primary.subject.entityType === "business_object") {
    if (primary.subject.record.created_by) actorLabels.push(primary.subject.record.created_by);
    if (primary.subject.record.deleted_by) actorLabels.push(primary.subject.record.deleted_by);
  } else if (primary.subject.entityType === "resource_booking") {
    employeeIds.push(primary.subject.record.booked_by_employee_id);
    if (primary.subject.record.cancelled_by) actorLabels.push(primary.subject.record.cancelled_by);
  } else if (primary.subject.entityType === "billing_account") {
    // an account's owner may be a customer or a vendor rather than a person
    if (primary.subject.record.employee_id) employeeIds.push(primary.subject.record.employee_id);
  } else {
    employeeIds.push(primary.subject.record.employee_id);
  }
  const names = await optional(
    localText(locale, "人员名称", "Display names"),
    resolveObjectDisplayNames(employeeIds, actorLabels),
    { employees: {}, actors: {} },
    issues,
    locale,
  );

  return {
    entityType,
    entityKind,
    objectType: primary.objectType,
    heading: primary.heading,
    subject: primary.subject,
    timesheetEntries: primary.timesheetEntries,
    expenseItems: primary.expenseItems,
    purchaseItems: primary.purchaseItems,
    salesQuotationItems: primary.salesQuotationItems,
    salesOrderItems: primary.salesOrderItems,
    attachments: primary.attachments,
    expenseTotals: primary.expenseTotals,
    purchaseTotals: primary.purchaseTotals,
    salesQuotationTotals: primary.salesQuotationTotals,
    salesOrderTotals: primary.salesOrderTotals,
    revisions: primary.revisions,
    quotationLink: primary.quotationLink,
    links,
    workflows: workflows.sort((left, right) => right.version - left.version),
    approvals: uniqueBy(approvals, (approval) => approval.id).sort((left, right) =>
      left.round_no - right.round_no || left.sequence_no - right.sequence_no || left.acted_at.localeCompare(right.acted_at)),
    todos: uniqueBy(todos, (todo) => todo.id),
    audits: uniqueBy(audits, (audit) => audit.id).sort((left, right) => right.id - left.id),
    employees: names.employees,
    actors: names.actors,
    issues,
  };
}

// The document that carries an attachment is what authorises reading it: the
// server checks "may this person see this document" and only then serves the
// bytes. `/attachments/{id}/content` still exists but is the workspace
// administrator's route — an ordinary member gets 403 there, which is why
// every download link below names its document.
const ATTACHMENT_COLLECTIONS: Partial<Record<ObjectEntityType, string>> = {
  expense_claim: "expense-claims",
  purchase_request: "purchase-requests",
  sales_quotation: "sales-quotations",
  sales_order: "sales-orders",
  invoice: "invoices",
  payment: "payments",
  // purchase_order and policy have the same API route but no console detail
  // page, so they are absent from ObjectEntityType. Returning null here is the
  // safe failure: no link rather than a link that 403s.
};

export function attachmentContentUrl(
  entityType: ObjectEntityType,
  documentId: string,
  attachmentId: string,
): string | null {
  const collection = ATTACHMENT_COLLECTIONS[entityType];
  if (!collection) return null;
  return `${API_ROOT}/${collection}/${encodeURIComponent(documentId)}`
    + `/attachments/${encodeURIComponent(attachmentId)}/content`;
}
