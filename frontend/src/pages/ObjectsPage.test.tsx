import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BusinessObject, ObjectDetail, ObjectDirectory } from "../api/objects";
import { ObjectDetailPage } from "./ObjectDetailPage";
import { ObjectsPage } from "./ObjectsPage";

const api = vi.hoisted(() => ({
  getObjectDirectory: vi.fn(),
  listObjectRecords: vi.fn(),
  resolveObjectListDisplayNames: vi.fn(),
  getObjectDetail: vi.fn(),
}));

vi.mock("../api/objects", async () => {
  const actual = await vi.importActual<typeof import("../api/objects")>("../api/objects");
  return { ...actual, ...api };
});

const record: BusinessObject = {
  id: "object-1",
  object_type: "contract",
  title: "年度采购合同",
  summary: "华东区框架合同",
  payload: { region: "east", amount: 200000 },
  source_text: null,
  status: "submitted",
  created_by: "user:user-1",
  created_at: "2026-07-01T08:00:00Z",
  updated_at: "2026-07-02T08:00:00Z",
  deleted_at: null,
  deleted_by: null,
  delete_reason: null,
};

const directory: ObjectDirectory = {
  employees: { "employee-1": "王琳" },
  actors: { "user:user-1": "租户管理员" },
  types: [
    { entityKind: "builtin", objectType: "timesheet_header", title: "工时单", description: null, status: "builtin", definitionVersion: 1, hasWorkflow: true, statuses: ["draft", "submitted", "approved"], count: 12 },
    { entityKind: "builtin", objectType: "expense_claim", title: "报销单", description: null, status: "builtin", definitionVersion: 1, hasWorkflow: true, statuses: ["draft", "submitted"], count: 8 },
    { entityKind: "builtin", objectType: "purchase_request", title: "采购申请", description: null, status: "builtin", definitionVersion: 1, hasWorkflow: true, statuses: ["draft", "submitted"], count: 5 },
    { entityKind: "builtin", objectType: "sales_quotation", title: "销售报价", description: null, status: "builtin", definitionVersion: 1, hasWorkflow: true, statuses: ["draft", "submitted", "approved", "sent", "accepted"], count: 7 },
    { entityKind: "builtin", objectType: "sales_order", title: "销售订单", description: null, status: "builtin", definitionVersion: 1, hasWorkflow: true, statuses: ["draft", "submitted", "confirmed", "shipped", "signed"], count: 6 },
    { entityKind: "builtin", objectType: "resource_booking", title: "资源预订", description: null, status: "builtin", definitionVersion: 1, hasWorkflow: false, statuses: ["confirmed", "cancelled"], count: 4 },
    { entityKind: "business_object", objectType: "contract", title: "合同", description: "合同审批对象", status: "active", definitionVersion: 3, hasWorkflow: true, statuses: ["draft", "submitted", "approved"], count: 21 },
  ],
};

function renderRoute(initialEntry: string, element: React.ReactNode, path = "/objects") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes><Route path={path} element={element} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getObjectDirectory.mockResolvedValue(directory);
  api.listObjectRecords.mockImplementation(({ page = 1 }: { page?: number }) => Promise.resolve({
    data: [{ entityType: "business_object", record }],
    meta: { total: 21, page, page_size: 20, pages: 2 },
  }));
  api.resolveObjectListDisplayNames.mockResolvedValue({ employees: directory.employees, actors: directory.actors });
});

afterEach(cleanup);

describe("object browser", () => {
  it("selects a type and applies keyword, status and pagination through URL-backed filters", async () => {
    const user = userEvent.setup();
    renderRoute("/objects?kind=business_object&object_type=contract&page=1", <ObjectsPage />);

    expect(await screen.findByText("年度采购合同")).toBeInTheDocument();
    expect(screen.getAllByText("租户管理员").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "查看详情" })).toHaveAttribute("href", expect.stringContaining("/objects/business_object/object-1"));

    await user.type(screen.getByRole("searchbox", { name: "搜索记录" }), "框架合同");
    await user.selectOptions(screen.getByLabelText("状态"), "submitted");
    await user.click(screen.getByRole("button", { name: "筛选" }));
    await waitFor(() => expect(api.listObjectRecords).toHaveBeenCalledWith(expect.objectContaining({
      entityType: "business_object", objectType: "contract", keyword: "框架合同", status: "submitted", page: 1,
    })));

    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listObjectRecords).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));

    await user.click(screen.getByRole("button", { name: /报销单/ }));
    await waitFor(() => expect(api.listObjectRecords).toHaveBeenCalledWith(expect.objectContaining({
      entityType: "expense_claim", objectType: "expense_claim", page: 1,
    })));
  });

  it("shows a recoverable record error without losing the type directory", async () => {
    api.listObjectRecords.mockRejectedValue(new Error("对象查询服务暂时不可用"));
    renderRoute("/objects?kind=business_object&object_type=contract", <ObjectsPage />);
    expect(await screen.findByText("数据加载失败")).toBeInTheDocument();
    expect(screen.getByText("对象查询服务暂时不可用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /合同/ })).toBeInTheDocument();
  });

  it("lists sales quotations with quote number, customer and total columns", async () => {
    const quotation = {
      id: "quotation-2", employee_id: "employee-1", title: "年度刀具报价", quote_number: "QT-000123",
      revision_no: 2, revision_of_id: "quotation-1", customer_id: "customer-1", customer_name_snapshot: "华欣机械",
      contact_name: "王工", contact_phone: null, contact_email: null, quote_date: "2026-07-21", valid_until: "2026-08-20",
      currency: "CNY", payment_terms: null, delivery_terms: null, remarks: null, status: "sent",
      submitted_at: "2026-07-21T09:00:00Z", sent_at: "2026-07-22T09:00:00Z", closed_at: null, outcome_note: null,
      project_id: null, source_report_text: null, total_amount: 16800, custom_fields: {},
      created_at: "2026-07-21T08:00:00Z", updated_at: null,
    };
    api.listObjectRecords.mockResolvedValue({
      data: [{ entityType: "sales_quotation", record: quotation }],
      meta: { total: 1, page: 1, page_size: 20, pages: 1 },
    });
    api.resolveObjectListDisplayNames.mockResolvedValue({ employees: { "employee-1": "王琳" }, actors: {} });
    renderRoute("/objects?kind=builtin&object_type=sales_quotation&page=1", <ObjectsPage />);

    expect(await screen.findByText("QT-000123")).toBeInTheDocument();
    expect(screen.getByText("华欣机械")).toBeInTheDocument();
    expect(screen.getByText("第 2 版")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "报价单号" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看详情" })).toHaveAttribute("href", expect.stringContaining("/objects/sales_quotation/quotation-2"));
    await waitFor(() => expect(api.listObjectRecords).toHaveBeenCalledWith(expect.objectContaining({
      entityType: "sales_quotation", objectType: "sales_quotation", page: 1,
    })));
  });

  it("lists sales orders with order no, customer, amount and tracking columns", async () => {
    const order = {
      id: "order-2", employee_id: "employee-1", title: "年度刀具首单", order_no: "SO-000042",
      order_date: "2026-07-22", promised_date: "2026-08-05", customer_id: "customer-1", customer_name_snapshot: "华欣机械",
      contact_name: "王工", contact_phone: null, quotation_id: "quotation-2", source_quote_number: "QT-000123",
      contract_no: null, currency: "CNY", payment_terms: null, delivery_terms: null,
      logistics_company: "顺丰", logistics_tracking_no: "SF1234567890", ship_to_address: null,
      remarks: null, status: "confirmed", submitted_at: "2026-07-22T09:00:00Z", shipped_at: null, signed_at: null,
      project_id: null, source_report_text: null, total_amount: 16800, custom_fields: {},
      created_at: "2026-07-22T08:00:00Z", updated_at: null,
    };
    api.listObjectRecords.mockResolvedValue({
      data: [{ entityType: "sales_order", record: order }],
      meta: { total: 1, page: 1, page_size: 20, pages: 1 },
    });
    api.resolveObjectListDisplayNames.mockResolvedValue({ employees: { "employee-1": "王琳" }, actors: {} });
    renderRoute("/objects?kind=builtin&object_type=sales_order&page=1", <ObjectsPage />);

    expect(await screen.findByText("SO-000042")).toBeInTheDocument();
    expect(screen.getByText("华欣机械")).toBeInTheDocument();
    expect(screen.getByText("SF1234567890")).toBeInTheDocument();
    expect(screen.getByText("报价 QT-000123")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "订单号" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看详情" })).toHaveAttribute("href", expect.stringContaining("/objects/sales_order/order-2"));
    await waitFor(() => expect(api.listObjectRecords).toHaveBeenCalledWith(expect.objectContaining({
      entityType: "sales_order", objectType: "sales_order", page: 1,
    })));
  });
});

describe("object detail", () => {
  it("renders links, workflow versions, approvals, todos and partial-load warnings", async () => {
    const detail: ObjectDetail = {
      entityType: "business_object",
      entityKind: "business_object",
      objectType: "contract",
      heading: "年度采购合同",
      subject: { entityType: "business_object", record },
      timesheetEntries: [], expenseItems: [], purchaseItems: [], salesQuotationItems: [], salesOrderItems: [], attachments: [],
      expenseTotals: null, purchaseTotals: null, salesQuotationTotals: null, salesOrderTotals: null, revisions: [], quotationLink: null,
      links: [{ id: "link-1", source_object_id: "object-1", target_object_id: "object-2", link_type: "amends", metadata: {}, created_at: "2026-07-03T08:00:00Z" }],
      workflows: [{ id: "workflow-1", tenant_id: "tenant-1", entity_kind: "business_object", object_type: "contract", name: "approval", version: 2, definition_text: "steps: []", status: "active", created_by: "user:user-1", created_at: "2026-07-03T08:00:00Z" }],
      approvals: [{ id: "approval-1", entity_type: "business_object", entity_id: "object-1", round_no: 1, sequence_no: 1, action: "approved", approver_id: "user:user-1", approver_role: "admin", comment: "同意", source: "web", metadata: {}, acted_at: "2026-07-04T08:00:00Z", created_at: "2026-07-04T08:00:00Z" }],
      todos: [{ id: "todo-1", employee_id: "employee-1", entity_type: "business_object", entity_id: "object-1", title: "复核合同条款", description: null, todo_type: "review", status: "open", due_at: null, created_by: "user:user-1", metadata: {}, created_at: "2026-07-04T08:00:00Z", updated_at: null, completed_at: null, completed_by: null }],
      audits: [],
      employees: directory.employees,
      actors: directory.actors,
      issues: [{ section: "审计轨迹", message: "audit service unavailable" }],
    };
    api.getObjectDetail.mockResolvedValue(detail);
    renderRoute(
      "/objects/business_object/object-1?kind=business_object&object_type=contract",
      <ObjectDetailPage />,
      "/objects/:entityType/:recordId",
    );

    expect(await screen.findByRole("heading", { name: "年度采购合同" })).toBeInTheDocument();
    expect(screen.getByText("部分关联信息未能加载")).toBeInTheDocument();
    expect(screen.getByText("amends")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText("同意")).toBeInTheDocument();
    expect(screen.getByText("复核合同条款")).toBeInTheDocument();
    expect(screen.getAllByText("租户管理员").length).toBeGreaterThan(0);
  });

  it("shows the tenant-scoped supplier name on expense lines", async () => {
    const detail: ObjectDetail = {
      entityType: "expense_claim", entityKind: "builtin", objectType: "expense_claim", heading: "上海出差报销",
      subject: { entityType: "expense_claim", record: {
        id: "claim-1", employee_id: "employee-1", title: "上海出差报销", claim_date: "2026-07-10",
        currency: "CNY", status: "submitted", submitted_at: "2026-07-11T08:00:00Z", source_report_text: null,
        custom_fields: {}, created_at: "2026-07-10T08:00:00Z", updated_at: null,
      } },
      timesheetEntries: [], purchaseItems: [], salesQuotationItems: [], salesOrderItems: [], attachments: [],
      expenseItems: [{
        id: "expense-1", claim_id: "claim-1", employee_id: "employee-1", expense_date: "2026-07-08",
        category: "meal", amount: 186.5, tax_amount: 11.06, vendor_id: "vendor-1", vendor_name: "上海餐饮供应商",
        merchant: "上海某餐饮有限公司", invoice_number: "INV-001", invoice_type: "vat_electronic", project_id: null,
        project_name_snapshot: null, client: null, attachment_id: null, extracted_fields: {}, notes: null,
        custom_fields: {}, created_at: "2026-07-10T08:00:00Z", updated_at: null,
      }],
      expenseTotals: { totalAmount: 186.5, totalTaxAmount: 11.06 }, purchaseTotals: null, salesQuotationTotals: null, salesOrderTotals: null, revisions: [], quotationLink: null,
      links: [], workflows: [], approvals: [], todos: [], audits: [], employees: directory.employees, actors: directory.actors, issues: [],
    };
    api.getObjectDetail.mockResolvedValue(detail);
    renderRoute("/objects/expense_claim/claim-1", <ObjectDetailPage />, "/objects/:entityType/:recordId");

    expect(await screen.findByText("上海餐饮供应商")).toBeInTheDocument();
    expect(screen.getByText("上海某餐饮有限公司")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "供应商" })).toBeInTheDocument();
  });

  it("renders purchase SKU code, catalog product and variant attributes instead of a raw id", async () => {
    const detail: ObjectDetail = {
      entityType: "purchase_request", entityKind: "builtin", objectType: "purchase_request", heading: "文化衫采购",
      subject: { entityType: "purchase_request", record: {
        id: "request-1", employee_id: "employee-1", title: "文化衫采购", request_date: "2026-07-11", needed_by: null,
        vendor_id: null, vendor_name_snapshot: null, currency: "CNY", status: "submitted", submitted_at: null,
        source_report_text: null, custom_fields: {}, created_at: "2026-07-11T08:00:00Z", updated_at: null,
      } },
      timesheetEntries: [], expenseItems: [], salesQuotationItems: [], salesOrderItems: [], attachments: [],
      purchaseItems: [{
        id: "line-1", request_id: "request-1", product_id: "product-1", sku_id: "sku-raw-id",
        product_name_snapshot: "旧快照名称", spec: null, quantity: 30, unit: null, unit_price: 95, amount: null,
        attachment_id: null, notes: null, custom_fields: {}, created_at: "2026-07-11T08:00:00Z", updated_at: null,
        product: { id: "product-1", product_code: "STYLE-001", name: "圆领T恤·藏青", spec: "纯棉", unit: "件" },
        sku: { id: "sku-raw-id", product_id: "product-1", sku_code: "001-NV-XL", variant_attrs: { 尺码: "XL", 包装: { 件数: 1 } } },
        sku_pending: false,
      }, {
        id: "line-2", request_id: "request-1", product_id: "product-1", sku_id: null,
        product_name_snapshot: "圆领T恤·藏青", spec: null, quantity: 100, unit: "件", unit_price: null, amount: null,
        attachment_id: null, notes: null, custom_fields: {}, created_at: "2026-07-11T08:01:00Z", updated_at: null,
        product: { id: "product-1", product_code: "STYLE-001", name: "圆领T恤·藏青", spec: "纯棉", unit: "件" },
        sku: null,
        sku_pending: true,
      }],
      expenseTotals: null, purchaseTotals: { estimatedTotal: 2850, unpricedItemCount: 1, pendingSkuCount: 1 }, salesQuotationTotals: null, salesOrderTotals: null, revisions: [], quotationLink: null,
      links: [], workflows: [], approvals: [], todos: [], audits: [], employees: directory.employees, actors: directory.actors, issues: [],
    };
    api.getObjectDetail.mockResolvedValue(detail);
    renderRoute("/objects/purchase_request/request-1", <ObjectDetailPage />, "/objects/:entityType/:recordId");

    expect(await screen.findByText("001-NV-XL")).toBeInTheDocument();
    expect(screen.getAllByText("圆领T恤·藏青")).toHaveLength(2);
    expect(screen.getByText('尺码：XL · 包装：{"件数":1}')).toBeInTheDocument();
    expect(screen.getByText("SKU 待定")).toBeInTheDocument();
    expect(screen.queryByText("sku-raw-id")).not.toBeInTheDocument();
  });

  it("renders quotation lines, list price, gift, tax rate, computed-vs-document total, and the revision chain", async () => {
    const quotationRecord = {
      id: "quotation-2", employee_id: "employee-1", title: "年度刀具报价", quote_number: "QT-000123",
      revision_no: 2, revision_of_id: "quotation-1", customer_id: "customer-1", customer_name_snapshot: "华欣机械",
      contact_name: "王工", contact_phone: "13800000000", contact_email: null, quote_date: "2026-07-21",
      valid_until: "2026-08-20", currency: "CNY", payment_terms: "月结30天", delivery_terms: "含运费",
      remarks: "含13%增值税", status: "sent", submitted_at: "2026-07-21T09:00:00Z", sent_at: "2026-07-22T09:00:00Z",
      closed_at: null, outcome_note: null, project_id: null, source_report_text: null, total_amount: 16800,
      custom_fields: {}, created_at: "2026-07-21T08:00:00Z", updated_at: null,
    };
    const detail: ObjectDetail = {
      entityType: "sales_quotation", entityKind: "builtin", objectType: "sales_quotation",
      heading: "QT-000123 · 年度刀具报价",
      subject: { entityType: "sales_quotation", record: quotationRecord },
      timesheetEntries: [], expenseItems: [], purchaseItems: [],
      salesQuotationItems: [{
        id: "qline-1", quotation_id: "quotation-2", line_no: 1, product_id: "product-1", sku_id: "sku-1",
        product_name_snapshot: "四刃立铣刀", spec: null, quantity: 200, unit: "支", unit_price: 85,
        list_price_snapshot: 94.44, tax_rate: 13, amount: null, is_gift: false, lead_time: "现货",
        attachment_id: null, notes: "目录价九折", custom_fields: {}, created_at: "2026-07-21T08:00:00Z", updated_at: null,
        product: { id: "product-1", product_code: "MILL-001", name: "四刃立铣刀", spec: "D10 硬质合金", unit: "支", list_price: 94.44 },
        sku: { id: "sku-1", product_id: "product-1", sku_code: "MILL-001-D10", variant_attrs: { 直径: "D10" }, list_price: 94.44 },
        sku_pending: false,
      }, {
        id: "qline-2", quotation_id: "quotation-2", line_no: 2, product_id: null, sku_id: null,
        product_name_snapshot: "样品盒", spec: null, quantity: 2, unit: "盒", unit_price: 0,
        list_price_snapshot: null, tax_rate: null, amount: null, is_gift: true, lead_time: null,
        attachment_id: null, notes: null, custom_fields: {}, created_at: "2026-07-21T08:01:00Z", updated_at: null,
        product: null, sku: null, sku_pending: false,
      }],
      attachments: [],
      expenseTotals: null, purchaseTotals: null,
      salesQuotationTotals: { computedTotal: 17000, unpricedItemCount: 0, pendingSkuCount: 0 },
      salesOrderItems: [], salesOrderTotals: null, quotationLink: null,
      revisions: [
        { ...quotationRecord },
        {
          ...quotationRecord, id: "quotation-1", revision_no: 1, revision_of_id: null, status: "superseded",
          total_amount: 18000, valid_until: "2026-08-10", quote_date: "2026-07-18",
        },
      ],
      links: [], workflows: [], approvals: [], todos: [], audits: [], employees: directory.employees, actors: directory.actors, issues: [],
    };
    api.getObjectDetail.mockResolvedValue(detail);
    renderRoute("/objects/sales_quotation/quotation-2", <ObjectDetailPage />, "/objects/:entityType/:recordId");

    expect(await screen.findByRole("heading", { name: "QT-000123 · 年度刀具报价" })).toBeInTheDocument();
    expect(screen.getByText("MILL-001-D10")).toBeInTheDocument();
    expect(screen.getByText("13%")).toBeInTheDocument();
    expect(screen.getAllByText("赠品").length).toBeGreaterThan(0);
    // computed line total vs a rounded-down document total are both shown and reconciled
    expect(screen.getByText("报价合计")).toBeInTheDocument();
    expect(screen.getByText("文档总额")).toBeInTheDocument();
    expect(screen.getByText(/与行合计不一致/)).toBeInTheDocument();
    // revision chain lists both revisions with the current one marked
    expect(screen.getByText("第 1 版")).toBeInTheDocument();
    expect(screen.getByText("当前查看")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看" })).toHaveAttribute("href", expect.stringContaining("/objects/sales_quotation/quotation-1"));
  });

  it("renders order lines, promised date, computed-vs-document total, and the won-quotation card", async () => {
    const quotation = {
      id: "quotation-2", employee_id: "employee-1", title: "年度刀具报价", quote_number: "QT-000123",
      revision_no: 1, revision_of_id: null, customer_id: "customer-1", customer_name_snapshot: "华欣机械",
      contact_name: "王工", contact_phone: null, contact_email: null, quote_date: "2026-07-18", valid_until: "2026-08-20",
      currency: "CNY", payment_terms: null, delivery_terms: null, remarks: null, status: "accepted",
      submitted_at: null, sent_at: null, closed_at: null, outcome_note: null,
      project_id: null, source_report_text: null, total_amount: 16800, custom_fields: {},
      created_at: "2026-07-18T08:00:00Z", updated_at: null,
    };
    const orderRecord = {
      id: "order-2", employee_id: "employee-1", title: "年度刀具首单", order_no: "SO-000042",
      order_date: "2026-07-22", promised_date: "2026-08-05", customer_id: "customer-1", customer_name_snapshot: "华欣机械",
      contact_name: "王工", contact_phone: "13800000000", quotation_id: "quotation-2", source_quote_number: "QT-000123",
      contract_no: null, currency: "CNY", payment_terms: "月结30天", delivery_terms: "含运费",
      logistics_company: "顺丰", logistics_tracking_no: "SF1234567890", ship_to_address: "上海市宝山区某路 1 号",
      remarks: null, status: "confirmed", submitted_at: "2026-07-22T09:00:00Z", shipped_at: null, signed_at: null,
      project_id: null, source_report_text: null, total_amount: 16800, custom_fields: {},
      created_at: "2026-07-22T08:00:00Z", updated_at: null,
    };
    const detail: ObjectDetail = {
      entityType: "sales_order", entityKind: "builtin", objectType: "sales_order",
      heading: "SO-000042 · 年度刀具首单",
      subject: { entityType: "sales_order", record: orderRecord },
      timesheetEntries: [], expenseItems: [], purchaseItems: [], salesQuotationItems: [],
      salesOrderItems: [{
        id: "oline-1", order_id: "order-2", line_no: 1, product_id: "product-1", sku_id: "sku-1",
        product_name_snapshot: "四刃立铣刀", spec: null, quantity: 200, unit: "支", unit_price: 85,
        list_price_snapshot: 94.44, tax_rate: 13, amount: null, is_gift: false, promised_date: "2026-08-05",
        attachment_id: null, notes: "目录价九折", custom_fields: {}, created_at: "2026-07-22T08:00:00Z", updated_at: null,
        product: { id: "product-1", product_code: "MILL-001", name: "四刃立铣刀", spec: "D10 硬质合金", unit: "支", list_price: 94.44 },
        sku: { id: "sku-1", product_id: "product-1", sku_code: "MILL-001-D10", variant_attrs: { 直径: "D10" }, list_price: 94.44 },
        sku_pending: false,
      }, {
        id: "oline-2", order_id: "order-2", line_no: 2, product_id: null, sku_id: null,
        product_name_snapshot: "样品盒", spec: null, quantity: 2, unit: "盒", unit_price: 0,
        list_price_snapshot: null, tax_rate: null, amount: null, is_gift: true, promised_date: null,
        attachment_id: null, notes: null, custom_fields: {}, created_at: "2026-07-22T08:01:00Z", updated_at: null,
        product: null, sku: null, sku_pending: false,
      }],
      attachments: [],
      expenseTotals: null, purchaseTotals: null, salesQuotationTotals: null,
      salesOrderTotals: { computedTotal: 17000, unpricedItemCount: 0, pendingSkuCount: 0 },
      revisions: [], quotationLink: quotation,
      links: [], workflows: [], approvals: [], todos: [], audits: [], employees: directory.employees, actors: directory.actors, issues: [],
    };
    api.getObjectDetail.mockResolvedValue(detail);
    renderRoute("/objects/sales_order/order-2", <ObjectDetailPage />, "/objects/:entityType/:recordId");

    expect(await screen.findByRole("heading", { name: "SO-000042 · 年度刀具首单" })).toBeInTheDocument();
    expect(screen.getByText("MILL-001-D10")).toBeInTheDocument();
    expect(screen.getByText("13%")).toBeInTheDocument();
    expect(screen.getAllByText("赠品").length).toBeGreaterThan(0);
    expect(screen.getByRole("columnheader", { name: "承诺交期" })).toBeInTheDocument();
    // computed line total vs a rounded-down document total are both shown and reconciled
    expect(screen.getByText("订单合计")).toBeInTheDocument();
    expect(screen.getByText("文档总额")).toBeInTheDocument();
    expect(screen.getByText(/与行合计不一致/)).toBeInTheDocument();
    // won-quotation back-link card links to the source quotation
    expect(screen.getByText("成交报价")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "QT-000123" })).toHaveAttribute("href", expect.stringContaining("/objects/sales_quotation/quotation-2"));
  });
});
