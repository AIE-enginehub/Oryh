import { zhCN } from "../locales/zh-CN/tests";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getObjectDetail, getObjectDirectory, listObjectRecords, type BusinessObject } from "./objects";

function jsonResponse(data: unknown, meta: Record<string, unknown> = {}): Response {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    headers: new Headers({ "Content-Type": "application/json" }),
    json: async () => ({ data, meta }),
  } as Response;
}

const businessObject: BusinessObject = {
  id: "object-1",
  object_type: "contract",
  title: zhCN.apiObjects.title,
  summary: zhCN.apiObjects.summary,
  payload: { region: "east" },
  source_text: null,
  status: "submitted",
  created_by: "user:user-1",
  created_at: "2026-07-01T08:00:00Z",
  updated_at: "2026-07-02T08:00:00Z",
  deleted_at: null,
  deleted_by: null,
  delete_reason: null,
};

afterEach(() => vi.unstubAllGlobals());

describe("object API", () => {
  it("uses server-side pagination and forwards object filters", async () => {
    const meta = { total: 41, page: 2, page_size: 20, pages: 3 };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([businessObject], meta));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listObjectRecords({
      entityType: "business_object",
      objectType: "contract",
      page: 2,
      size: 20,
      keyword: zhCN.apiObjects.keyword,
      status: "submitted",
    })).resolves.toEqual({ data: [{ entityType: "business_object", record: businessObject }], meta });

    const request = new URL(String(fetchMock.mock.calls[0][0]), "https://console.example");
    expect(request.pathname).toBe("/api/v1/business-objects");
    expect(Object.fromEntries(request.searchParams)).toMatchObject({
      page: "2",
      size: "20",
      keyword: zhCN.apiObjects.keyword,
      status: "submitted",
      object_type: "contract",
      include_deleted: "true",
    });
  });

  it("keeps a bounded local fallback for old servers without page metadata", async () => {
    const second = { ...businessObject, id: "object-2", title: zhCN.apiObjects.title2, summary: null };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([businessObject, second], { total: 2 })));

    await expect(listObjectRecords({
      entityType: "business_object",
      objectType: "contract",
      page: 1,
      size: 1,
      keyword: zhCN.apiObjects.keyword2,
    })).resolves.toEqual({
      data: [{ entityType: "business_object", record: businessObject }],
      meta: { total: 1, page: 1, page_size: 1, pages: 1 },
    });
  });

  it("uses the aggregate business-object detail contract and resolves display names", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string) => {
      const url = new URL(input, "https://console.example");
      if (url.pathname === "/api/v1/business-objects/object-1/detail") return Promise.resolve(jsonResponse({
        business_object: businessObject,
        links: [{ id: "link-1", source_object_id: "object-1", target_object_id: "object-2", link_type: "amends", metadata: {}, created_at: "2026-07-03T08:00:00Z" }],
        approval_records: [{ id: "approval-1", entity_type: "business_object", entity_id: "object-1", round_no: 1, sequence_no: 1, action: "approved", approver_id: "user:user-1", approver_role: "admin", comment: null, source: "web", metadata: {}, acted_at: "2026-07-04T08:00:00Z", created_at: "2026-07-04T08:00:00Z" }],
        todos: [],
        audit_logs: [],
        object_type_definition: null,
        rules: [{ id: "rule-1", kind: "approval_flow", code: "approval_flow:business_object:contract:approval", version: 2, entity_kind: "business_object", object_type: "contract", name: "approval", origin: "tenant", category: null, title: zhCN.apiObjects.title3, summary: null, body: "steps: []", rules_json: null, visibility: "internal", required_capability: null, status: "published", effective_from: "2026-07-03", effective_thru: null, published_at: "2026-07-03T08:00:00Z", published_by: "user:user-1", supersedes_id: null, attachment_id: null, owner_employee_id: null, created_by: "user:user-1", custom_fields: {}, created_at: "2026-07-03T08:00:00Z", updated_at: "2026-07-03T08:00:00Z" }],
      }));
      if (url.pathname === "/api/v1/directory/display-names/resolve") return Promise.resolve(jsonResponse({ employees: { "employee-1": zhCN.apiObjects.employee1 }, actors: { "user:user-1": zhCN.apiObjects.userUser1 } }));
      throw new Error(`Unexpected URL ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const detail = await getObjectDetail("business_object", "object-1");
    expect(detail.objectType).toBe("contract");
    expect(detail.links).toHaveLength(1);
    expect(detail.approvals).toHaveLength(1);
    expect(detail.rules[0]).toMatchObject({ kind: "approval_flow", version: 2, status: "published" });
    expect(detail.actors["user:user-1"]).toBe(zhCN.apiObjects.userUser1);
    expect(detail.issues).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toContain("/business-objects/object-1/detail?include_deleted=true");
  });

  it("maps the sales-quotation detail contract into items, totals and the revision chain", async () => {
    const quotation = {
      id: "quotation-2", employee_id: "employee-1", title: zhCN.apiObjects.title4, quote_number: "QT-000123",
      revision_no: 2, revision_of_id: "quotation-1", customer_id: "customer-1", customer_name_snapshot: zhCN.apiObjects.customerNameSnapshot,
      contact_name: zhCN.apiObjects.contactName, contact_phone: null, contact_email: null, quote_date: "2026-07-21", valid_until: "2026-08-20",
      currency: "CNY", payment_terms: null, delivery_terms: null, remarks: null, status: "sent",
      submitted_at: "2026-07-21T09:00:00Z", sent_at: "2026-07-22T09:00:00Z", closed_at: null, outcome_note: null,
      project_id: null, source_report_text: null, total_amount: 16800, custom_fields: {},
      created_at: "2026-07-21T08:00:00Z", updated_at: null,
    };
    const fetchMock = vi.fn().mockImplementation((input: string) => {
      const url = new URL(input, "https://console.example");
      if (url.pathname === "/api/v1/sales-quotations/quotation-2/detail") return Promise.resolve(jsonResponse({
        quotation,
        items: [{
          id: "qline-1", quotation_id: "quotation-2", line_no: 1, product_id: "product-1", sku_id: "sku-1",
          product_name_snapshot: zhCN.apiObjects.productNameSnapshot, spec: null, quantity: 200, unit: zhCN.apiObjects.unit, unit_price: 85,
          list_price_snapshot: 94.44, tax_rate: 13, amount: null, is_gift: false, lead_time: zhCN.apiObjects.leadTime,
          attachment_id: null, notes: null, custom_fields: {}, created_at: "2026-07-21T08:00:00Z", updated_at: null,
          product: { id: "product-1", product_code: "MILL-001", name: zhCN.apiObjects.productNameSnapshot, spec: "D10", unit: zhCN.apiObjects.unit, list_price: 94.44 },
          sku: { id: "sku-1", product_id: "product-1", sku_code: "MILL-001-D10", variant_attrs: {}, list_price: 94.44 },
          sku_pending: false,
        }],
        approval_records: [{ id: "approval-1", entity_type: "sales_quotation", entity_id: "quotation-2", round_no: 1, sequence_no: 1, action: "approved", approver_id: "user:user-1", approver_role: "manager", comment: null, source: "web", metadata: {}, acted_at: "2026-07-21T10:00:00Z", created_at: "2026-07-21T10:00:00Z" }],
        attachments: [],
        computed_total: 17000,
        unpriced_item_count: 0,
        pending_sku_count: 0,
        revisions: [quotation, { ...quotation, id: "quotation-1", revision_no: 1, revision_of_id: null, status: "superseded" }],
      }));
      if (url.pathname === "/api/v1/business-rules") return Promise.resolve(jsonResponse([]));
      if (url.pathname === "/api/v1/todos") return Promise.resolve(jsonResponse([]));
      if (url.pathname === "/api/v1/audit-logs") return Promise.resolve(jsonResponse([]));
      if (url.pathname === "/api/v1/directory/display-names/resolve") return Promise.resolve(jsonResponse({ employees: { "employee-1": zhCN.apiObjects.employee1 }, actors: { "user:user-1": zhCN.apiObjects.userUser12 } }));
      throw new Error(`Unexpected URL ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const detail = await getObjectDetail("sales_quotation", "quotation-2");
    expect(detail.entityType).toBe("sales_quotation");
    expect(detail.subject.record.id).toBe("quotation-2");
    expect(detail.salesQuotationItems).toHaveLength(1);
    expect(detail.salesQuotationItems[0].list_price_snapshot).toBe(94.44);
    expect(detail.salesQuotationTotals).toEqual({ computedTotal: 17000, unpricedItemCount: 0, pendingSkuCount: 0 });
    expect(detail.revisions).toHaveLength(2);
    expect(detail.approvals).toHaveLength(1);
    expect(detail.employees["employee-1"]).toBe(zhCN.apiObjects.employee1);
    expect(detail.actors["user:user-1"]).toBe(zhCN.apiObjects.userUser12);
    expect(detail.issues).toEqual([]);
    expect(fetchMock.mock.calls[0][0]).toContain("/sales-quotations/quotation-2/detail?include_deleted=true");
  });

  it("maps the sales-order detail contract into items, totals and the won quotation", async () => {
    const order = {
      id: "order-2", employee_id: "employee-1", title: zhCN.apiObjects.title5, order_no: "SO-000042",
      order_date: "2026-07-22", promised_date: "2026-08-05", customer_id: "customer-1", customer_name_snapshot: zhCN.apiObjects.customerNameSnapshot,
      contact_name: zhCN.apiObjects.contactName, contact_phone: null, quotation_id: "quotation-2", source_quote_number: "QT-000123",
      contract_no: null, currency: "CNY", payment_terms: null, delivery_terms: null,
      logistics_company: zhCN.apiObjects.logisticsCompany, logistics_tracking_no: "SF1234567890", ship_to_address: null,
      remarks: null, status: "confirmed", submitted_at: "2026-07-22T09:00:00Z", shipped_at: null, signed_at: null,
      project_id: null, source_report_text: null, total_amount: 16800, custom_fields: {},
      created_at: "2026-07-22T08:00:00Z", updated_at: null,
    };
    const quotation = {
      id: "quotation-2", employee_id: "employee-1", title: zhCN.apiObjects.title4, quote_number: "QT-000123",
      revision_no: 1, revision_of_id: null, customer_id: "customer-1", customer_name_snapshot: zhCN.apiObjects.customerNameSnapshot,
      contact_name: zhCN.apiObjects.contactName, contact_phone: null, contact_email: null, quote_date: "2026-07-18", valid_until: "2026-08-20",
      currency: "CNY", payment_terms: null, delivery_terms: null, remarks: null, status: "accepted",
      submitted_at: null, sent_at: null, closed_at: null, outcome_note: null,
      project_id: null, source_report_text: null, total_amount: 16800, custom_fields: {},
      created_at: "2026-07-18T08:00:00Z", updated_at: null,
    };
    const fetchMock = vi.fn().mockImplementation((input: string) => {
      const url = new URL(input, "https://console.example");
      if (url.pathname === "/api/v1/sales-orders/order-2/detail") return Promise.resolve(jsonResponse({
        order,
        items: [{
          id: "oline-1", order_id: "order-2", line_no: 1, product_id: "product-1", sku_id: "sku-1",
          product_name_snapshot: zhCN.apiObjects.productNameSnapshot, spec: null, quantity: 200, unit: zhCN.apiObjects.unit, unit_price: 85,
          list_price_snapshot: 94.44, tax_rate: 13, amount: null, is_gift: false, promised_date: "2026-08-05",
          attachment_id: null, notes: null, custom_fields: {}, created_at: "2026-07-22T08:00:00Z", updated_at: null,
          product: { id: "product-1", product_code: "MILL-001", name: zhCN.apiObjects.productNameSnapshot, spec: "D10", unit: zhCN.apiObjects.unit, list_price: 94.44 },
          sku: { id: "sku-1", product_id: "product-1", sku_code: "MILL-001-D10", variant_attrs: {}, list_price: 94.44 },
          sku_pending: false,
        }],
        approval_records: [{ id: "approval-1", entity_type: "sales_order", entity_id: "order-2", round_no: 1, sequence_no: 1, action: "approved", approver_id: "user:user-1", approver_role: "manager", comment: null, source: "web", metadata: {}, acted_at: "2026-07-22T10:00:00Z", created_at: "2026-07-22T10:00:00Z" }],
        attachments: [],
        computed_total: 17000,
        unpriced_item_count: 0,
        pending_sku_count: 0,
        quotation,
      }));
      if (url.pathname === "/api/v1/business-rules") return Promise.resolve(jsonResponse([]));
      if (url.pathname === "/api/v1/todos") return Promise.resolve(jsonResponse([]));
      if (url.pathname === "/api/v1/audit-logs") return Promise.resolve(jsonResponse([]));
      if (url.pathname === "/api/v1/directory/display-names/resolve") return Promise.resolve(jsonResponse({ employees: { "employee-1": zhCN.apiObjects.employee1 }, actors: { "user:user-1": zhCN.apiObjects.userUser12 } }));
      throw new Error(`Unexpected URL ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const detail = await getObjectDetail("sales_order", "order-2");
    expect(detail.entityType).toBe("sales_order");
    expect(detail.subject.record.id).toBe("order-2");
    expect(detail.salesOrderItems).toHaveLength(1);
    expect(detail.salesOrderItems[0].list_price_snapshot).toBe(94.44);
    expect(detail.salesOrderTotals).toEqual({ computedTotal: 17000, unpricedItemCount: 0, pendingSkuCount: 0 });
    expect(detail.quotationLink?.quote_number).toBe("QT-000123");
    expect(detail.revisions).toHaveLength(0);
    expect(detail.approvals).toHaveLength(1);
    expect(detail.employees["employee-1"]).toBe(zhCN.apiObjects.employee1);
    expect(detail.actors["user:user-1"]).toBe(zhCN.apiObjects.userUser12);
    expect(detail.issues).toEqual([]);
    expect(fetchMock.mock.calls[0][0]).toContain("/sales-orders/order-2/detail?include_deleted=true");
  });

  it("discovers data-only custom object types from the bounded directory projection", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string) => {
      const url = new URL(input, "https://console.example");
      if (url.pathname === "/api/v1/object-type-definitions") return Promise.resolve(jsonResponse([]));
      if (url.pathname === "/api/v1/business-rules") return Promise.resolve(jsonResponse([]));
      if (url.pathname === "/api/v1/object-directory") return Promise.resolve(jsonResponse([
        { entity_kind: "business_object", object_type: "legacy_contract", count: 17, title: null, definition_status: null },
      ]));
      throw new Error(`Unexpected URL ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const directory = await getObjectDirectory();

    expect(directory.types).toContainEqual(expect.objectContaining({
      entityKind: "business_object",
      objectType: "legacy_contract",
      count: 17,
      definitionVersion: null,
    }));
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
