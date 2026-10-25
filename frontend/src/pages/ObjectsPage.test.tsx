import { zhAttributes } from "../locales/zh-CN/attributes";
import { zhCN } from "../locales/zh-CN/tests";
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
  title: zhCN.pagesObjectsPage.title,
  summary: zhCN.pagesObjectsPage.summary,
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
  employees: { "employee-1": zhCN.pagesObjectsPage.employee1 },
  actors: { "user:user-1": zhCN.pagesObjectsPage.userUser1 },
  types: [
    { entityKind: "builtin", objectType: "timesheet_header", title: zhCN.pagesObjectsPage.title2, description: null, status: "builtin", definitionVersion: 1, hasWorkflow: true, statuses: ["draft", "submitted", "approved"], count: 12 },
    { entityKind: "builtin", objectType: "expense_claim", title: zhCN.pagesObjectsPage.title3, description: null, status: "builtin", definitionVersion: 1, hasWorkflow: true, statuses: ["draft", "submitted"], count: 8 },
    { entityKind: "builtin", objectType: "purchase_request", title: zhCN.pagesObjectsPage.title4, description: null, status: "builtin", definitionVersion: 1, hasWorkflow: true, statuses: ["draft", "submitted"], count: 5 },
    { entityKind: "builtin", objectType: "sales_quotation", title: zhCN.pagesObjectsPage.title5, description: null, status: "builtin", definitionVersion: 1, hasWorkflow: true, statuses: ["draft", "submitted", "approved", "sent", "accepted"], count: 7 },
    { entityKind: "builtin", objectType: "sales_order", title: zhCN.pagesObjectsPage.title6, description: null, status: "builtin", definitionVersion: 1, hasWorkflow: true, statuses: ["draft", "submitted", "confirmed", "shipped", "signed"], count: 6 },
    { entityKind: "builtin", objectType: "resource_booking", title: zhCN.pagesObjectsPage.title7, description: null, status: "builtin", definitionVersion: 1, hasWorkflow: false, statuses: ["confirmed", "cancelled"], count: 4 },
    { entityKind: "business_object", objectType: "contract", title: zhCN.pagesObjectsPage.title8, description: zhCN.pagesObjectsPage.description, status: "active", definitionVersion: 3, hasWorkflow: true, statuses: ["draft", "submitted", "approved"], count: 21 },
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

    expect(await screen.findByText(zhCN.pagesObjectsPage.title)).toBeInTheDocument();
    expect(screen.getAllByText(zhCN.pagesObjectsPage.userUser1).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: zhCN.pagesObjectsPage.name })).toHaveAttribute("href", expect.stringContaining("/objects/business_object/object-1"));

    await user.type(screen.getByRole("searchbox", { name: zhCN.pagesObjectsPage.name2 }), zhCN.pagesObjectsPage.message);
    await user.selectOptions(screen.getByLabelText(zhCN.pagesObjectsPage.state), "submitted");
    await user.click(screen.getByRole("button", { name: zhCN.pagesObjectsPage.name3 }));
    await waitFor(() => expect(api.listObjectRecords).toHaveBeenCalledWith(expect.objectContaining({
      entityType: "business_object", objectType: "contract", keyword: zhCN.pagesObjectsPage.message, status: "submitted", page: 1,
    })));

    await user.click(screen.getByRole("button", { name: zhCN.pagesObjectsPage.name4 }));
    await waitFor(() => expect(api.listObjectRecords).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));

    await user.click(screen.getByRole("button", { name: zhCN.pagesObjectsPage.name5() }));
    await waitFor(() => expect(api.listObjectRecords).toHaveBeenCalledWith(expect.objectContaining({
      entityType: "expense_claim", objectType: "expense_claim", page: 1,
    })));
  });

  it("shows a recoverable record error without losing the type directory", async () => {
    api.listObjectRecords.mockRejectedValue(new Error(zhCN.pagesObjectsPage.message3));
    renderRoute("/objects?kind=business_object&object_type=contract", <ObjectsPage />);
    expect(await screen.findByText(zhCN.pagesObjectsPage.dataCouldNotBeLoaded)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.message3)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: zhCN.pagesObjectsPage.name6() })).toBeInTheDocument();
  });

  it("lists sales quotations with quote number, customer and total columns", async () => {
    const quotation = {
      id: "quotation-2", employee_id: "employee-1", title: zhCN.pagesObjectsPage.title9, quote_number: "QT-000123",
      revision_no: 2, revision_of_id: "quotation-1", customer_id: "customer-1", customer_name_snapshot: zhCN.pagesObjectsPage.customerNameSnapshot,
      contact_name: zhCN.pagesObjectsPage.contactName, contact_phone: null, contact_email: null, quote_date: "2026-07-21", valid_until: "2026-08-20",
      currency: "CNY", payment_terms: null, delivery_terms: null, remarks: null, status: "sent",
      submitted_at: "2026-07-21T09:00:00Z", sent_at: "2026-07-22T09:00:00Z", closed_at: null, outcome_note: null,
      project_id: null, source_report_text: null, total_amount: 16800, custom_fields: {},
      created_at: "2026-07-21T08:00:00Z", updated_at: null,
    };
    api.listObjectRecords.mockResolvedValue({
      data: [{ entityType: "sales_quotation", record: quotation }],
      meta: { total: 1, page: 1, page_size: 20, pages: 1 },
    });
    api.resolveObjectListDisplayNames.mockResolvedValue({ employees: { "employee-1": zhCN.pagesObjectsPage.employee1 }, actors: {} });
    renderRoute("/objects?kind=builtin&object_type=sales_quotation&page=1", <ObjectsPage />);

    expect(await screen.findByText("QT-000123")).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.customerNameSnapshot)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.message5)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: zhCN.pagesObjectsPage.name7 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: zhCN.pagesObjectsPage.name })).toHaveAttribute("href", expect.stringContaining("/objects/sales_quotation/quotation-2"));
    await waitFor(() => expect(api.listObjectRecords).toHaveBeenCalledWith(expect.objectContaining({
      entityType: "sales_quotation", objectType: "sales_quotation", page: 1,
    })));
  });

  it("lists sales orders with order no, customer, amount and tracking columns", async () => {
    const order = {
      id: "order-2", employee_id: "employee-1", title: zhCN.pagesObjectsPage.title10, order_no: "SO-000042",
      order_date: "2026-07-22", promised_date: "2026-08-05", customer_id: "customer-1", customer_name_snapshot: zhCN.pagesObjectsPage.customerNameSnapshot,
      contact_name: zhCN.pagesObjectsPage.contactName, contact_phone: null, quotation_id: "quotation-2", source_quote_number: "QT-000123",
      contract_no: null, currency: "CNY", payment_terms: null, delivery_terms: null,
      logistics_company: zhCN.pagesObjectsPage.logisticsCompany, logistics_tracking_no: "SF1234567890", ship_to_address: null,
      remarks: null, status: "confirmed", submitted_at: "2026-07-22T09:00:00Z", shipped_at: null, signed_at: null,
      project_id: null, source_report_text: null, total_amount: 16800, custom_fields: {},
      created_at: "2026-07-22T08:00:00Z", updated_at: null,
    };
    api.listObjectRecords.mockResolvedValue({
      data: [{ entityType: "sales_order", record: order }],
      meta: { total: 1, page: 1, page_size: 20, pages: 1 },
    });
    api.resolveObjectListDisplayNames.mockResolvedValue({ employees: { "employee-1": zhCN.pagesObjectsPage.employee1 }, actors: {} });
    renderRoute("/objects?kind=builtin&object_type=sales_order&page=1", <ObjectsPage />);

    expect(await screen.findByText("SO-000042")).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.customerNameSnapshot)).toBeInTheDocument();
    expect(screen.getByText("SF1234567890")).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.message6)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: zhCN.pagesObjectsPage.name8 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: zhCN.pagesObjectsPage.name })).toHaveAttribute("href", expect.stringContaining("/objects/sales_order/order-2"));
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
      heading: zhCN.pagesObjectsPage.title,
      subject: { entityType: "business_object", record },
      timesheetEntries: [], expenseItems: [], purchaseItems: [], salesQuotationItems: [], salesOrderItems: [], attachments: [],
      expenseTotals: null, purchaseTotals: null, salesQuotationTotals: null, salesOrderTotals: null, revisions: [], quotationLink: null,
      links: [{ id: "link-1", source_object_id: "object-1", target_object_id: "object-2", link_type: "amends", metadata: {}, created_at: "2026-07-03T08:00:00Z" }],
      rules: [{ id: "rule-1", kind: "approval_flow", code: "approval_flow:business_object:contract:approval", version: 2, entity_kind: "business_object", object_type: "contract", name: "approval", origin: "tenant", category: null, title: zhCN.pagesObjectsPage.title11, summary: null, body: "steps: []", rules_json: null, visibility: "internal", required_capability: null, status: "published", effective_from: "2026-07-03", effective_thru: null, published_at: "2026-07-03T08:00:00Z", published_by: "user:user-1", supersedes_id: null, attachment_id: null, owner_employee_id: null, created_by: "user:user-1", custom_fields: {}, created_at: "2026-07-03T08:00:00Z", updated_at: "2026-07-03T08:00:00Z" }],
      approvals: [{ id: "approval-1", entity_type: "business_object", entity_id: "object-1", round_no: 1, sequence_no: 1, action: "approved", approver_id: "user:user-1", approver_role: "admin", comment: zhCN.pagesObjectsPage.comment, source: "web", metadata: {}, acted_at: "2026-07-04T08:00:00Z", created_at: "2026-07-04T08:00:00Z" }],
      todos: [{ id: "todo-1", employee_id: "employee-1", entity_type: "business_object", entity_id: "object-1", title: zhCN.pagesObjectsPage.title12, description: null, todo_type: "review", status: "open", due_at: null, created_by: "user:user-1", metadata: {}, created_at: "2026-07-04T08:00:00Z", updated_at: null, completed_at: null, completed_by: null }],
      audits: [],
      employees: directory.employees,
      actors: directory.actors,
      issues: [{ section: zhCN.pagesObjectsPage.section, message: "audit service unavailable" }],
    };
    api.getObjectDetail.mockResolvedValue(detail);
    renderRoute(
      "/objects/business_object/object-1?kind=business_object&object_type=contract",
      <ObjectDetailPage />,
      "/objects/:entityType/:recordId",
    );

    expect(await screen.findByRole("heading", { name: zhCN.pagesObjectsPage.title })).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.someRelatedInformationCouldNotBeLoaded)).toBeInTheDocument();
    expect(screen.getByText("amends")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.comment)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.title12)).toBeInTheDocument();
    expect(screen.getAllByText(zhCN.pagesObjectsPage.userUser1).length).toBeGreaterThan(0);
  });

  it("shows the tenant-scoped supplier name on expense lines", async () => {
    const detail: ObjectDetail = {
      entityType: "expense_claim", entityKind: "builtin", objectType: "expense_claim", heading: zhCN.pagesObjectsPage.heading,
      subject: { entityType: "expense_claim", record: {
        id: "claim-1", employee_id: "employee-1", title: zhCN.pagesObjectsPage.heading, claim_date: "2026-07-10",
        currency: "CNY", status: "submitted", submitted_at: "2026-07-11T08:00:00Z", source_report_text: null,
        custom_fields: {}, created_at: "2026-07-10T08:00:00Z", updated_at: null,
      } },
      timesheetEntries: [], purchaseItems: [], salesQuotationItems: [], salesOrderItems: [], attachments: [],
      expenseItems: [{
        id: "expense-1", claim_id: "claim-1", employee_id: "employee-1", expense_date: "2026-07-08",
        category: "meal", amount: 186.5, tax_amount: 11.06, vendor_id: "vendor-1", vendor_name: zhCN.pagesObjectsPage.vendorName,
        merchant: zhCN.pagesObjectsPage.merchant, invoice_number: "INV-001", invoice_type: "vat_electronic", project_id: null,
        project_name_snapshot: null, client: null, attachment_id: null, extracted_fields: {}, notes: null,
        custom_fields: {}, created_at: "2026-07-10T08:00:00Z", updated_at: null,
      }],
      expenseTotals: { totalAmount: 186.5, totalTaxAmount: 11.06 }, purchaseTotals: null, salesQuotationTotals: null, salesOrderTotals: null, revisions: [], quotationLink: null,
      links: [], rules: [], approvals: [], todos: [], audits: [], employees: directory.employees, actors: directory.actors, issues: [],
    };
    api.getObjectDetail.mockResolvedValue(detail);
    renderRoute("/objects/expense_claim/claim-1", <ObjectDetailPage />, "/objects/:entityType/:recordId");

    expect(await screen.findByText(zhCN.pagesObjectsPage.vendorName)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.merchant)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: zhCN.pagesObjectsPage.name9 })).toBeInTheDocument();
  });

  it("renders purchase SKU code, catalog product and variant attributes instead of a raw id", async () => {
    const detail: ObjectDetail = {
      entityType: "purchase_request", entityKind: "builtin", objectType: "purchase_request", heading: zhCN.pagesObjectsPage.heading2,
      subject: { entityType: "purchase_request", record: {
        id: "request-1", employee_id: "employee-1", title: zhCN.pagesObjectsPage.heading2, request_date: "2026-07-11", needed_by: null,
        vendor_id: null, vendor_name_snapshot: null, currency: "CNY", status: "submitted", submitted_at: null,
        source_report_text: null, custom_fields: {}, created_at: "2026-07-11T08:00:00Z", updated_at: null,
      } },
      timesheetEntries: [], expenseItems: [], salesQuotationItems: [], salesOrderItems: [], attachments: [],
      purchaseItems: [{
        id: "line-1", request_id: "request-1", product_id: "product-1", sku_id: "sku-raw-id",
        product_name_snapshot: zhCN.pagesObjectsPage.productNameSnapshot, spec: null, quantity: 30, unit: null, unit_price: 95, amount: null,
        attachment_id: null, notes: null, custom_fields: {}, created_at: "2026-07-11T08:00:00Z", updated_at: null,
        product: { id: "product-1", product_code: "STYLE-001", name: zhCN.pagesObjectsPage.name10, spec: zhCN.pagesObjectsPage.spec, unit: zhCN.pagesObjectsPage.unit },
        sku: { id: "sku-raw-id", product_id: "product-1", sku_code: "001-NV-XL", variant_attrs: { [zhAttributes.size]: "XL", [zhAttributes.packaging]: { [zhAttributes.itemCount]: 1 } } },
        sku_pending: false,
      }, {
        id: "line-2", request_id: "request-1", product_id: "product-1", sku_id: null,
        product_name_snapshot: zhCN.pagesObjectsPage.name10, spec: null, quantity: 100, unit: zhCN.pagesObjectsPage.unit, unit_price: null, amount: null,
        attachment_id: null, notes: null, custom_fields: {}, created_at: "2026-07-11T08:01:00Z", updated_at: null,
        product: { id: "product-1", product_code: "STYLE-001", name: zhCN.pagesObjectsPage.name10, spec: zhCN.pagesObjectsPage.spec, unit: zhCN.pagesObjectsPage.unit },
        sku: null,
        sku_pending: true,
      }],
      expenseTotals: null, purchaseTotals: { estimatedTotal: 2850, unpricedItemCount: 1, pendingSkuCount: 1 }, salesQuotationTotals: null, salesOrderTotals: null, revisions: [], quotationLink: null,
      links: [], rules: [], approvals: [], todos: [], audits: [], employees: directory.employees, actors: directory.actors, issues: [],
    };
    api.getObjectDetail.mockResolvedValue(detail);
    renderRoute("/objects/purchase_request/request-1", <ObjectDetailPage />, "/objects/:entityType/:recordId");

    expect(await screen.findByText("001-NV-XL")).toBeInTheDocument();
    expect(screen.getAllByText(zhCN.pagesObjectsPage.name10)).toHaveLength(2);
    expect(screen.getByText(zhCN.pagesObjectsPage.message8)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.sKUPending)).toBeInTheDocument();
    expect(screen.queryByText("sku-raw-id")).not.toBeInTheDocument();
  });

  it("renders quotation lines, list price, gift, tax rate, computed-vs-document total, and the revision chain", async () => {
    const quotationRecord = {
      id: "quotation-2", employee_id: "employee-1", title: zhCN.pagesObjectsPage.title9, quote_number: "QT-000123",
      revision_no: 2, revision_of_id: "quotation-1", customer_id: "customer-1", customer_name_snapshot: zhCN.pagesObjectsPage.customerNameSnapshot,
      contact_name: zhCN.pagesObjectsPage.contactName, contact_phone: "13800000000", contact_email: null, quote_date: "2026-07-21",
      valid_until: "2026-08-20", currency: "CNY", payment_terms: zhCN.pagesObjectsPage.paymentTerms, delivery_terms: zhCN.pagesObjectsPage.deliveryTerms,
      remarks: zhCN.pagesObjectsPage.remarks, status: "sent", submitted_at: "2026-07-21T09:00:00Z", sent_at: "2026-07-22T09:00:00Z",
      closed_at: null, outcome_note: null, project_id: null, source_report_text: null, total_amount: 16800,
      custom_fields: {}, created_at: "2026-07-21T08:00:00Z", updated_at: null,
    };
    const detail: ObjectDetail = {
      entityType: "sales_quotation", entityKind: "builtin", objectType: "sales_quotation",
      heading: zhCN.pagesObjectsPage.heading3,
      subject: { entityType: "sales_quotation", record: quotationRecord },
      timesheetEntries: [], expenseItems: [], purchaseItems: [],
      salesQuotationItems: [{
        id: "qline-1", quotation_id: "quotation-2", line_no: 1, product_id: "product-1", sku_id: "sku-1",
        product_name_snapshot: zhCN.pagesObjectsPage.productNameSnapshot2, spec: null, quantity: 200, unit: zhCN.pagesObjectsPage.unit2, unit_price: 85,
        list_price_snapshot: 94.44, tax_rate: 13, amount: null, is_gift: false, lead_time: zhCN.pagesObjectsPage.leadTime,
        attachment_id: null, notes: zhCN.pagesObjectsPage.notes, custom_fields: {}, created_at: "2026-07-21T08:00:00Z", updated_at: null,
        product: { id: "product-1", product_code: "MILL-001", name: zhCN.pagesObjectsPage.productNameSnapshot2, spec: zhCN.pagesObjectsPage.spec2, unit: zhCN.pagesObjectsPage.unit2, list_price: 94.44 },
        sku: { id: "sku-1", product_id: "product-1", sku_code: "MILL-001-D10", variant_attrs: { [zhAttributes.diameter]: "D10" }, list_price: 94.44 },
        sku_pending: false,
      }, {
        id: "qline-2", quotation_id: "quotation-2", line_no: 2, product_id: null, sku_id: null,
        product_name_snapshot: zhCN.pagesObjectsPage.productNameSnapshot3, spec: null, quantity: 2, unit: zhCN.pagesObjectsPage.unit3, unit_price: 0,
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
      links: [], rules: [], approvals: [], todos: [], audits: [], employees: directory.employees, actors: directory.actors, issues: [],
    };
    api.getObjectDetail.mockResolvedValue(detail);
    renderRoute("/objects/sales_quotation/quotation-2", <ObjectDetailPage />, "/objects/:entityType/:recordId");

    expect(await screen.findByRole("heading", { name: zhCN.pagesObjectsPage.heading3 })).toBeInTheDocument();
    expect(screen.getByText("MILL-001-D10")).toBeInTheDocument();
    expect(screen.getByText("13%")).toBeInTheDocument();
    expect(screen.getAllByText(zhCN.pagesObjectsPage.gift).length).toBeGreaterThan(0);
    // computed line total vs a rounded-down document total are both shown and reconciled
    expect(screen.getByText(zhCN.pagesObjectsPage.lineTotal)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.documentTotal)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.pattern())).toBeInTheDocument();
    // revision chain lists both revisions with the current one marked
    expect(screen.getByText(zhCN.pagesObjectsPage.message13)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.viewing)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: zhCN.pagesObjectsPage.name11 })).toHaveAttribute("href", expect.stringContaining("/objects/sales_quotation/quotation-1"));
  });

  it("renders order lines, promised date, computed-vs-document total, and the won-quotation card", async () => {
    const quotation = {
      id: "quotation-2", employee_id: "employee-1", title: zhCN.pagesObjectsPage.title9, quote_number: "QT-000123",
      revision_no: 1, revision_of_id: null, customer_id: "customer-1", customer_name_snapshot: zhCN.pagesObjectsPage.customerNameSnapshot,
      contact_name: zhCN.pagesObjectsPage.contactName, contact_phone: null, contact_email: null, quote_date: "2026-07-18", valid_until: "2026-08-20",
      currency: "CNY", payment_terms: null, delivery_terms: null, remarks: null, status: "accepted",
      submitted_at: null, sent_at: null, closed_at: null, outcome_note: null,
      project_id: null, source_report_text: null, total_amount: 16800, custom_fields: {},
      created_at: "2026-07-18T08:00:00Z", updated_at: null,
    };
    const orderRecord = {
      id: "order-2", employee_id: "employee-1", title: zhCN.pagesObjectsPage.title10, order_no: "SO-000042",
      order_date: "2026-07-22", promised_date: "2026-08-05", customer_id: "customer-1", customer_name_snapshot: zhCN.pagesObjectsPage.customerNameSnapshot,
      contact_name: zhCN.pagesObjectsPage.contactName, contact_phone: "13800000000", quotation_id: "quotation-2", source_quote_number: "QT-000123",
      contract_no: null, currency: "CNY", payment_terms: zhCN.pagesObjectsPage.paymentTerms, delivery_terms: zhCN.pagesObjectsPage.deliveryTerms,
      logistics_company: zhCN.pagesObjectsPage.logisticsCompany, logistics_tracking_no: "SF1234567890", ship_to_address: zhCN.pagesObjectsPage.shipToAddress,
      remarks: null, status: "confirmed", submitted_at: "2026-07-22T09:00:00Z", shipped_at: null, signed_at: null,
      project_id: null, source_report_text: null, total_amount: 16800, custom_fields: {},
      created_at: "2026-07-22T08:00:00Z", updated_at: null,
    };
    const detail: ObjectDetail = {
      entityType: "sales_order", entityKind: "builtin", objectType: "sales_order",
      heading: zhCN.pagesObjectsPage.heading4,
      subject: { entityType: "sales_order", record: orderRecord },
      timesheetEntries: [], expenseItems: [], purchaseItems: [], salesQuotationItems: [],
      salesOrderItems: [{
        id: "oline-1", order_id: "order-2", line_no: 1, product_id: "product-1", sku_id: "sku-1",
        product_name_snapshot: zhCN.pagesObjectsPage.productNameSnapshot2, spec: null, quantity: 200, unit: zhCN.pagesObjectsPage.unit2, unit_price: 85,
        list_price_snapshot: 94.44, tax_rate: 13, amount: null, is_gift: false, promised_date: "2026-08-05",
        attachment_id: null, notes: zhCN.pagesObjectsPage.notes, custom_fields: {}, created_at: "2026-07-22T08:00:00Z", updated_at: null,
        product: { id: "product-1", product_code: "MILL-001", name: zhCN.pagesObjectsPage.productNameSnapshot2, spec: zhCN.pagesObjectsPage.spec2, unit: zhCN.pagesObjectsPage.unit2, list_price: 94.44 },
        sku: { id: "sku-1", product_id: "product-1", sku_code: "MILL-001-D10", variant_attrs: { [zhAttributes.diameter]: "D10" }, list_price: 94.44 },
        sku_pending: false,
      }, {
        id: "oline-2", order_id: "order-2", line_no: 2, product_id: null, sku_id: null,
        product_name_snapshot: zhCN.pagesObjectsPage.productNameSnapshot3, spec: null, quantity: 2, unit: zhCN.pagesObjectsPage.unit3, unit_price: 0,
        list_price_snapshot: null, tax_rate: null, amount: null, is_gift: true, promised_date: null,
        attachment_id: null, notes: null, custom_fields: {}, created_at: "2026-07-22T08:01:00Z", updated_at: null,
        product: null, sku: null, sku_pending: false,
      }],
      attachments: [],
      expenseTotals: null, purchaseTotals: null, salesQuotationTotals: null,
      salesOrderTotals: { computedTotal: 17000, unpricedItemCount: 0, pendingSkuCount: 0 },
      revisions: [], quotationLink: quotation,
      links: [], rules: [], approvals: [], todos: [], audits: [], employees: directory.employees, actors: directory.actors, issues: [],
    };
    api.getObjectDetail.mockResolvedValue(detail);
    renderRoute("/objects/sales_order/order-2", <ObjectDetailPage />, "/objects/:entityType/:recordId");

    expect(await screen.findByRole("heading", { name: zhCN.pagesObjectsPage.heading4 })).toBeInTheDocument();
    expect(screen.getByText("MILL-001-D10")).toBeInTheDocument();
    expect(screen.getByText("13%")).toBeInTheDocument();
    expect(screen.getAllByText(zhCN.pagesObjectsPage.gift).length).toBeGreaterThan(0);
    expect(screen.getByRole("columnheader", { name: zhCN.pagesObjectsPage.name12 })).toBeInTheDocument();
    // computed line total vs a rounded-down document total are both shown and reconciled
    expect(screen.getByText(zhCN.pagesObjectsPage.lineTotal2)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.documentTotal)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesObjectsPage.pattern())).toBeInTheDocument();
    // won-quotation back-link card links to the source quotation
    expect(screen.getByText(zhCN.pagesObjectsPage.wonQuotation)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "QT-000123" })).toHaveAttribute("href", expect.stringContaining("/objects/sales_quotation/quotation-2"));
  });
});
