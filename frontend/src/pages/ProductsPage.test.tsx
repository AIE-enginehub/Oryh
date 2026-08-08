import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Product, ProductSku } from "../api/client";
import { ProductsPage } from "./ProductsPage";

const api = vi.hoisted(() => ({
  listProducts: vi.fn(),
  createProduct: vi.fn(),
  updateProduct: vi.fn(),
  archiveProduct: vi.fn(),
  listProductSkus: vi.fn(),
  createProductSku: vi.fn(),
  batchCreateProductSkus: vi.fn(),
  updateProductSku: vi.fn(),
  archiveProductSku: vi.fn(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, ...api };
});

const product = {
  id: "product-1",
  product_code: "P-100",
  name: "轻量夹克",
  spec: "城市通勤款",
  unit: "件",
  list_price: 399,
  currency: "CNY",
  status: "active",
  metadata: {},
  has_skus: true,
  sku_count: 1,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as Product;

const sku = {
  id: "sku-1",
  product_id: "product-1",
  sku_code: "P-100-GRAY-L",
  variant_attrs: {
    颜色: "深空灰",
    尺码序号: 42,
    包装: { 类型: "礼盒", 件数: 1 },
  },
  list_price: 429,
  status: "active",
  metadata: {},
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as ProductSku;

function renderPage(node: ReactNode = <ProductsPage />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listProducts.mockImplementation(({ page = 1 }: { page?: number }) => Promise.resolve({
    data: [product],
    meta: { total: 21, page, page_size: 20, pages: 2 },
  }));
  api.createProduct.mockResolvedValue(product);
  api.updateProduct.mockResolvedValue(product);
  api.archiveProduct.mockResolvedValue(undefined);
  api.listProductSkus.mockImplementation(({ page = 1 }: { page?: number }) => Promise.resolve({
    data: [sku],
    meta: { total: 21, page, page_size: 20, pages: 2 },
  }));
  api.createProductSku.mockResolvedValue(sku);
  api.batchCreateProductSkus.mockResolvedValue({ created: [], skipped: [] });
  api.updateProductSku.mockResolvedValue(sku);
  api.archiveProductSku.mockResolvedValue(undefined);
});

afterEach(cleanup);

describe("product catalog", () => {
  it("loads products and applies server-side search, status and pagination", async () => {
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText("轻量夹克")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listProducts).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));
    await user.type(screen.getByRole("searchbox"), "夹克");
    await user.selectOptions(screen.getByLabelText("状态"), "archived");
    await user.click(screen.getByRole("button", { name: "筛选" }));
    await waitFor(() => expect(api.listProducts).toHaveBeenCalledWith(expect.objectContaining({ page: 1, keyword: "夹克", status: "archived" })));
  });

  it("validates, creates, edits and archives a product while returning to page one", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("轻量夹克");
    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listProducts).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));

    await user.click(screen.getByRole("button", { name: /新建产品/ }));
    await user.type(screen.getByLabelText(/产品名称/), "旅行风衣");
    await user.clear(screen.getByLabelText(/币种/));
    await user.type(screen.getByLabelText(/币种/), "US");
    await user.type(screen.getByLabelText("参考价格"), "12.345");
    await user.click(screen.getByRole("button", { name: "创建产品" }));
    expect(await screen.findByText(/币种必须是三位/)).toBeInTheDocument();
    await user.clear(screen.getByLabelText(/币种/));
    await user.type(screen.getByLabelText(/币种/), "USD");
    await user.click(screen.getByRole("button", { name: "创建产品" }));
    expect(await screen.findByText(/最多保留两位小数/)).toBeInTheDocument();
    await user.clear(screen.getByLabelText("参考价格"));
    await user.type(screen.getByLabelText("参考价格"), "129.90");
    await user.click(screen.getByRole("button", { name: "创建产品" }));
    await waitFor(() => expect(api.createProduct).toHaveBeenCalledWith(expect.objectContaining({ name: "旅行风衣", currency: "USD", list_price: 129.9 })));
    await waitFor(() => {
      const calls = api.listProducts.mock.calls.map(([filters]) => filters.page);
      expect(calls.at(-1)).toBe(1);
    });

    await user.click(screen.getByRole("button", { name: "编辑" }));
    await user.clear(screen.getByLabelText("计量单位"));
    await user.type(screen.getByLabelText("计量单位"), "套");
    await user.click(screen.getByRole("button", { name: "保存更改" }));
    await waitFor(() => expect(api.updateProduct).toHaveBeenCalledWith("product-1", expect.objectContaining({ unit: "套" })));

    await user.click(screen.getByRole("button", { name: "归档" }));
    const confirm = screen.getByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: "确认归档" }));
    await waitFor(() => expect(api.archiveProduct).toHaveBeenCalledWith("product-1"));
  });

  it("shows a recoverable product-list error", async () => {
    api.listProducts.mockRejectedValue(new Error("目录服务暂时不可用"));
    renderPage();
    expect(await screen.findByText("数据加载失败")).toBeInTheDocument();
    expect(screen.getByText("目录服务暂时不可用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  });

  it("returns to the last valid product page when the result set shrinks", async () => {
    api.listProducts.mockImplementation(({ page = 1 }: { page?: number }) => Promise.resolve(
      page === 2
        ? { data: [], meta: { total: 1, page: 2, page_size: 20, pages: 1 } }
        : { data: [product], meta: { total: 21, page: 1, page_size: 20, pages: 2 } },
    ));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("轻量夹克");
    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listProducts).toHaveBeenCalledWith(
      expect.objectContaining({ page: 2 }),
    ));

    await waitFor(() => {
      const pages = api.listProducts.mock.calls.map(([filters]) => filters.page);
      expect(pages.at(-1)).toBe(1);
    });
  });
});

describe("product SKU workspace", () => {
  it("filters and manages SKU attributes without losing numeric or object values", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("轻量夹克");
    await user.click(screen.getByRole("button", { name: "SKU · 1" }));
    const workspace = await screen.findByRole("region", { name: "SKU 管理" });
    expect(await within(workspace).findByText("P-100-GRAY-L")).toBeInTheDocument();
    expect(within(workspace).getByText('包装：{"类型":"礼盒","件数":1}')).toBeInTheDocument();

    await user.type(within(workspace).getByLabelText("精确 SKU 编码"), "P-100-GRAY-L");
    await user.selectOptions(within(workspace).getByLabelText("SKU 状态"), "active");
    await user.click(within(workspace).getByRole("button", { name: "查询" }));
    await waitFor(() => expect(api.listProductSkus).toHaveBeenCalledWith(expect.objectContaining({ product_id: "product-1", sku_code: "P-100-GRAY-L", status: "active" })));

    await user.click(within(workspace).getByRole("button", { name: "编辑" }));
    expect(screen.getByLabelText("属性 2 值")).toHaveValue("42");
    expect(screen.getByLabelText("属性 3 值")).toHaveValue('{"类型":"礼盒","件数":1}');
    expect(screen.getAllByText("结构化内容")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "保存更改" }));
    await waitFor(() => expect(api.updateProductSku).toHaveBeenCalledWith("sku-1", expect.objectContaining({
      variant_attrs: {
        颜色: "深空灰",
        尺码序号: 42,
        包装: { 类型: "礼盒", 件数: 1 },
      },
    })));
    expect(api.updateProductSku.mock.calls[0][1]).not.toHaveProperty("product_id");

    await user.click(within(workspace).getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listProductSkus).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));
    await user.click(within(workspace).getByRole("button", { name: /新建 SKU/ }));
    await user.type(screen.getByLabelText("SKU 编码"), "P-100-BLUE-M");
    await user.type(screen.getByLabelText("属性 1 名称"), "颜色");
    await user.type(screen.getByLabelText("属性 1 值"), "海军蓝");
    await user.click(screen.getByRole("button", { name: /添加属性/ }));
    await user.type(screen.getByLabelText("属性 2 名称"), "尺码");
    await user.type(screen.getByLabelText("属性 2 值"), "M");
    await user.type(screen.getByLabelText("变体价格"), "419.00");
    await user.click(screen.getByRole("button", { name: "创建 SKU" }));
    await waitFor(() => expect(api.createProductSku).toHaveBeenCalledWith(expect.objectContaining({
      product_id: "product-1",
      sku_code: "P-100-BLUE-M",
      variant_attrs: { 颜色: "海军蓝", 尺码: "M" },
      list_price: 419,
    })));
    await waitFor(() => {
      const calls = api.listProductSkus.mock.calls.map(([filters]) => filters.page);
      expect(calls.at(-1)).toBe(1);
    });

    await user.click(within(workspace).getByRole("button", { name: "归档" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "确认归档" }));
    await waitFor(() => expect(api.archiveProductSku).toHaveBeenCalledWith("sku-1"));
    expect(screen.getByRole("button", { name: "SKU · 1" })).toBeInTheDocument();
  });

  it("shows an empty state for a product without SKU variants", async () => {
    api.listProductSkus.mockResolvedValue({ data: [], meta: { total: 0, page: 1, page_size: 20, pages: 1 } });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("轻量夹克");
    await user.click(screen.getByRole("button", { name: "SKU · 1" }));
    expect(await screen.findByText("该产品还没有 SKU")).toBeInTheDocument();
  });

  it("batch-creates a size run and reports both created and skipped values", async () => {
    api.batchCreateProductSkus.mockResolvedValueOnce({
      created: [
        { ...sku, id: "sku-s", sku_code: "P-100-S", variant_attrs: { 尺码: "S" } },
        { ...sku, id: "sku-l", sku_code: null, variant_attrs: { 尺码: "L" } },
      ],
      skipped: ["M", "XL"],
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("轻量夹克");
    await user.click(screen.getByRole("button", { name: "SKU · 1" }));
    const workspace = await screen.findByRole("region", { name: "SKU 管理" });
    await user.click(within(workspace).getByRole("button", { name: "批量配码" }));
    const dialog = screen.getByRole("dialog");

    await user.clear(within(dialog).getByLabelText(/规格值/));
    await user.click(within(dialog).getByRole("button", { name: "批量创建 SKU" }));
    expect(await within(dialog).findByText("请至少填写一个规格值。")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText(/规格值/), "S, M，L XL");
    await user.type(within(dialog).getByLabelText("统一变体价格"), "429.90");
    await user.click(within(dialog).getByRole("button", { name: "批量创建 SKU" }));

    await waitFor(() => expect(api.batchCreateProductSkus).toHaveBeenCalledWith("product-1", {
      dimension: "尺码",
      values: ["S", "M", "L", "XL"],
      list_price: 429.9,
    }));
    expect(await screen.findByText("批量配码完成：已创建 2 个 SKU，跳过 2 个值。")).toBeInTheDocument();
    expect(screen.getByText("P-100-S")).toBeInTheDocument();
    expect(screen.getByText("L")).toBeInTheDocument();
    expect(screen.getByText("M")).toBeInTheDocument();
    expect(screen.getByText("XL")).toBeInTheDocument();
  });

  it("keeps the batch drawer busy and exposes a recoverable API error", async () => {
    let rejectBatch!: (error: Error) => void;
    api.batchCreateProductSkus.mockImplementationOnce(() => new Promise((_resolve, reject) => {
      rejectBatch = reject;
    }));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("轻量夹克");
    await user.click(screen.getByRole("button", { name: "SKU · 1" }));
    const workspace = await screen.findByRole("region", { name: "SKU 管理" });
    await user.click(within(workspace).getByRole("button", { name: "批量配码" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(/规格值/), "S M");
    await user.click(within(dialog).getByRole("button", { name: "批量创建 SKU" }));

    expect(within(dialog).getByRole("button", { name: "正在保存…" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "取消" })).toBeDisabled();
    act(() => rejectBatch(new Error("批量配码服务不可用")));
    expect(await within(dialog).findByText("批量配码服务不可用")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "批量创建 SKU" })).not.toBeDisabled();
  });

  it("does not create new SKUs under an archived product", async () => {
    api.listProducts.mockResolvedValue({
      data: [{ ...product, status: "archived" }],
      meta: { total: 1, page: 1, page_size: 20, pages: 1 },
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("轻量夹克");
    await user.click(screen.getByRole("button", { name: "SKU · 1" }));

    const createButton = await screen.findByRole("button", { name: /新建 SKU/ });
    expect(createButton).toBeDisabled();
    expect(createButton).toHaveAttribute("title", "请先将产品恢复为启用状态");
    const batchButton = screen.getByRole("button", { name: "批量配码" });
    expect(batchButton).toBeDisabled();
    expect(batchButton).toHaveAttribute("title", "请先将产品恢复为启用状态");
  });

  it("returns to the last valid SKU page when variants shrink", async () => {
    api.listProductSkus.mockImplementation(({ page = 1 }: { page?: number }) => Promise.resolve(
      page === 2
        ? { data: [], meta: { total: 1, page: 2, page_size: 20, pages: 1 } }
        : { data: [sku], meta: { total: 21, page: 1, page_size: 20, pages: 2 } },
    ));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("轻量夹克");
    await user.click(screen.getByRole("button", { name: "SKU · 1" }));
    const workspace = await screen.findByRole("region", { name: "SKU 管理" });
    await within(workspace).findByText("P-100-GRAY-L");
    await user.click(within(workspace).getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listProductSkus).toHaveBeenCalledWith(
      expect.objectContaining({ page: 2 }),
    ));

    await waitFor(() => {
      const pages = api.listProductSkus.mock.calls.map(([filters]) => filters.page);
      expect(pages.at(-1)).toBe(1);
    });
  });
});
