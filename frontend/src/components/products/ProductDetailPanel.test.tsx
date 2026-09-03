import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Product } from "../../api/client";
import { LanguageProvider } from "../../i18n";
import { ProductDetailPanel } from "./ProductDetailPanel";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    headers: new Headers({ "Content-Type": "application/json" }),
    json: async () => body,
  } as Response;
}

const product: Product = {
  id: "prod-1",
  product_code: "P-1001",
  name: "内窥镜镜头",
  product_type: "finished_good",
  spec: "4mm 30°",
  unit: "个",
  list_price: 1200,
  currency: "CNY",
  status: "active",
  metadata: { 报关编码: "9018.90", 存储条件: { 温度: "2-30℃", 湿度: "<80%" } },
  has_skus: false,
  sku_count: 0,
  created_at: "2026-07-25T10:00:00+08:00",
  updated_at: "2026-07-25T11:00:00+08:00",
};

const prices = [
  { id: "pp-1", product_id: "prod-1", sku_id: null, price_type: "wholesale", price: 980, currency: "CNY",
    tax_in_price: true, tax_percentage: 13, status: "active", metadata: {},
    created_at: "2026-07-25T10:00:00+08:00", updated_at: "2026-07-25T10:00:00+08:00" },
  // a tenant-defined type (via /type-options) has no shipped label — it must
  // render verbatim, never crash the label lookup
  { id: "pp-3", product_id: "prod-1", sku_id: null, price_type: "dealer_tier2", price: 940, currency: "CNY",
    tax_in_price: true, tax_percentage: null, status: "active", metadata: {},
    created_at: "2026-07-25T10:00:00+08:00", updated_at: "2026-07-25T10:00:00+08:00" },
  { id: "pp-2", product_id: "prod-1", sku_id: null, price_type: "promo", price: 899, currency: "CNY",
    tax_in_price: true, tax_percentage: null, status: "archived", metadata: { 活动: "618" },
    created_at: "2026-07-20T10:00:00+08:00", updated_at: "2026-07-21T10:00:00+08:00" },
];

const suppliers = [
  { id: "sp-1", product_id: "prod-1", vendor_id: "v-1", vendor_name: "华东医疗器械有限公司",
    supplier_product_code: "HD-JT-4030", supplier_product_name: "内窥镜物镜4mm", last_price: 760,
    currency: "CNY", lead_time_days: 7, min_order_quantity: 5, order_increment: null, preference: 1,
    status: "active", metadata: {}, created_at: "2026-07-25T10:00:00+08:00", updated_at: "2026-07-25T10:00:00+08:00" },
];

const inventory = [
  { id: "inv-1", product_id: "prod-1", product_code: "P-1001", sku_id: null, facility: "总仓", lot_id: "B2026-07",
    bin_number: "A-03", expire_date: "2027-06-30", received_at: null, quantity_on_hand: 97,
    available_to_promise: 97, unit_cost: 760, currency: "CNY", status: "active", metadata: {},
    created_at: "2026-07-25T10:00:00+08:00", updated_at: "2026-07-25T10:00:00+08:00" },
];

const ledger = [
  { id: "d-2", inventory_item_id: "inv-1", quantity_on_hand_diff: -23.5, available_to_promise_diff: -23.5,
    reason: "import_override", description: "导入覆盖：系统数量 120.5 → 导入数量 97（差异 -23.5）",
    entity_type: null, entity_id: null, unit_cost: null, effective_at: "2026-07-25T10:30:00+08:00",
    created_by: "user:admin", created_at: "2026-07-25T10:30:00+08:00" },
  { id: "d-1", inventory_item_id: "inv-1", quantity_on_hand_diff: 120.5, available_to_promise_diff: 120.5,
    reason: "import_initial", description: "批量导入建账：数量 120.5", entity_type: null, entity_id: null,
    unit_cost: 760, effective_at: "2026-07-25T10:00:00+08:00", created_by: "user:admin",
    created_at: "2026-07-25T10:00:00+08:00" },
];

describe("ProductDetailPanel", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/product-prices")) return jsonResponse({ data: prices, meta: { total: 2 } });
      if (url.includes("/api/v1/supplier-products")) return jsonResponse({ data: suppliers, meta: { total: 1 } });
      if (url.includes("/api/v1/inventory-item-details")) return jsonResponse({ data: ledger, meta: { total: 2 } });
      if (url.includes("/api/v1/inventory-items")) return jsonResponse({ data: inventory, meta: { total: 1 } });
      throw new Error(`unexpected fetch: ${url}`);
    }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  function renderPanel() {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <LanguageProvider defaultLanguage="zh-CN">
          <ProductDetailPanel product={product} onClose={() => undefined} />
        </LanguageProvider>
      </QueryClientProvider>,
    );
  }

  it("shows every product field including nested metadata", async () => {
    renderPanel();
    expect(screen.getByText("P-1001")).toBeInTheDocument();
    expect(screen.getByText("4mm 30°")).toBeInTheDocument();
    expect(screen.getByText("prod-1")).toBeInTheDocument();
    // metadata keys, scalar values, and nested structures all render
    expect(screen.getByText("报关编码")).toBeInTheDocument();
    expect(screen.getByText("9018.90")).toBeInTheDocument();
    expect(screen.getByText("存储条件")).toBeInTheDocument();
    expect(screen.getByText(/2-30℃/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("华东医疗器械有限公司")).toBeInTheDocument());
  });

  it("lists the price book with archived history and the supplier terms", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText("批发价")).toBeInTheDocument());
    expect(screen.getByText("促销价")).toBeInTheDocument();  // archived row still shown
    expect(screen.getByText("dealer_tier2")).toBeInTheDocument();  // custom type, verbatim
    expect(screen.getByText("13%")).toBeInTheDocument();
    expect(screen.getByText("HD-JT-4030")).toBeInTheDocument();
    expect(screen.getByText("内窥镜物镜4mm")).toBeInTheDocument();
  });

  it("expands an inventory position into its movement ledger", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText("总仓")).toBeInTheDocument());
    expect(screen.getByText(/B2026-07/)).toBeInTheDocument();
    expect(screen.getByText("97")).toBeInTheDocument();

    await userEvent.click(screen.getByText("总仓"));
    await waitFor(() => expect(screen.getByText("导入覆盖")).toBeInTheDocument());
    // qoh diff and ATP diff move together on an override — both cells render
    expect(screen.getAllByText("-23.5")).toHaveLength(2);
    expect(screen.getAllByText("+120.5")).toHaveLength(2);
    expect(screen.getByText(/系统数量 120.5 → 导入数量 97/)).toBeInTheDocument();
    expect(screen.getByText("导入建账")).toBeInTheDocument();
  });
});
