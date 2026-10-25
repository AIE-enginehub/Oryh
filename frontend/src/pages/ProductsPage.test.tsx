import { zhAttributes } from "../locales/zh-CN/attributes";
import { zhCN } from "../locales/zh-CN/tests";
import { MemoryRouter } from "react-router-dom";
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
  name: zhCN.pagesProductsPage.name,
  spec: zhCN.pagesProductsPage.spec,
  unit: zhCN.pagesProductsPage.unit,
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
    [zhAttributes.color]: zhCN.pagesProductsPage.message,
    [zhAttributes.sizeSequence]: 42,
    [zhAttributes.packaging]: { [zhAttributes.packagingType]: zhCN.pagesProductsPage.message2, [zhAttributes.itemCount]: 1 },
  },
  list_price: 429,
  status: "active",
  metadata: {},
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as ProductSku;

function renderPage(node: ReactNode = <ProductsPage />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
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
    expect(await screen.findByText(zhCN.pagesProductsPage.name)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name2 }));
    await waitFor(() => expect(api.listProducts).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));
    await user.type(screen.getByRole("searchbox"), zhCN.pagesProductsPage.message3);
    await user.selectOptions(screen.getByLabelText(zhCN.pagesProductsPage.state), "archived");
    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name3 }));
    await waitFor(() => expect(api.listProducts).toHaveBeenCalledWith(expect.objectContaining({ page: 1, keyword: zhCN.pagesProductsPage.message3, status: "archived" })));
  });

  it("validates, creates, edits and archives a product while returning to page one", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(zhCN.pagesProductsPage.name);
    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name2 }));
    await waitFor(() => expect(api.listProducts).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));

    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name4() }));
    await user.type(screen.getByLabelText(zhCN.pagesProductsPage.pattern()), zhCN.pagesProductsPage.message5);
    await user.clear(screen.getByLabelText(zhCN.pagesProductsPage.pattern2()));
    await user.type(screen.getByLabelText(zhCN.pagesProductsPage.pattern2()), "US");
    await user.type(screen.getByLabelText(zhCN.pagesProductsPage.referencePrice), "12.345");
    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name5 }));
    expect(await screen.findByText(zhCN.pagesProductsPage.pattern3())).toBeInTheDocument();
    await user.clear(screen.getByLabelText(zhCN.pagesProductsPage.pattern2()));
    await user.type(screen.getByLabelText(zhCN.pagesProductsPage.pattern2()), "USD");
    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name5 }));
    expect(await screen.findByText(zhCN.pagesProductsPage.pattern4())).toBeInTheDocument();
    await user.clear(screen.getByLabelText(zhCN.pagesProductsPage.referencePrice));
    await user.type(screen.getByLabelText(zhCN.pagesProductsPage.referencePrice), "129.90");
    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name5 }));
    await waitFor(() => expect(api.createProduct).toHaveBeenCalledWith(expect.objectContaining({ name: zhCN.pagesProductsPage.message5, currency: "USD", list_price: 129.9 })));
    await waitFor(() => {
      const calls = api.listProducts.mock.calls.map(([filters]) => filters.page);
      expect(calls.at(-1)).toBe(1);
    });

    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name6 }));
    await user.clear(screen.getByLabelText(zhCN.pagesProductsPage.unitOfMeasure));
    await user.type(screen.getByLabelText(zhCN.pagesProductsPage.unitOfMeasure), zhCN.pagesProductsPage.message8);
    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name7 }));
    await waitFor(() => expect(api.updateProduct).toHaveBeenCalledWith("product-1", expect.objectContaining({ unit: zhCN.pagesProductsPage.message8 })));

    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name8 }));
    const confirm = screen.getByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: zhCN.pagesProductsPage.name9 }));
    await waitFor(() => expect(api.archiveProduct).toHaveBeenCalledWith("product-1"));
  });

  it("shows a recoverable product-list error", async () => {
    api.listProducts.mockRejectedValue(new Error(zhCN.pagesProductsPage.message9));
    renderPage();
    expect(await screen.findByText(zhCN.pagesProductsPage.dataCouldNotBeLoaded)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesProductsPage.message9)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: zhCN.pagesProductsPage.name10 })).toBeInTheDocument();
  });

  it("returns to the last valid product page when the result set shrinks", async () => {
    api.listProducts.mockImplementation(({ page = 1 }: { page?: number }) => Promise.resolve(
      page === 2
        ? { data: [], meta: { total: 1, page: 2, page_size: 20, pages: 1 } }
        : { data: [product], meta: { total: 21, page: 1, page_size: 20, pages: 2 } },
    ));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(zhCN.pagesProductsPage.name);
    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name2 }));
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
    await screen.findByText(zhCN.pagesProductsPage.name);
    await user.click(screen.getByRole("button", { name: "SKU · 1" }));
    const workspace = await screen.findByRole("region", { name: zhCN.pagesProductsPage.name11 });
    expect(await within(workspace).findByText("P-100-GRAY-L")).toBeInTheDocument();
    expect(within(workspace).getByText(zhCN.pagesProductsPage.message11)).toBeInTheDocument();

    await user.type(within(workspace).getByLabelText(zhCN.pagesProductsPage.exactSKUCode), "P-100-GRAY-L");
    await user.selectOptions(within(workspace).getByLabelText(zhCN.pagesProductsPage.sKUStatus), "active");
    await user.click(within(workspace).getByRole("button", { name: zhCN.pagesProductsPage.name12 }));
    await waitFor(() => expect(api.listProductSkus).toHaveBeenCalledWith(expect.objectContaining({ product_id: "product-1", sku_code: "P-100-GRAY-L", status: "active" })));

    await user.click(within(workspace).getByRole("button", { name: zhCN.pagesProductsPage.name6 }));
    expect(screen.getByLabelText(zhCN.pagesProductsPage.message14)).toHaveValue("42");
    expect(screen.getByLabelText(zhCN.pagesProductsPage.message15)).toHaveValue(zhCN.pagesProductsPage.message16);
    expect(screen.getAllByText(zhCN.pagesProductsPage.structuredContent)).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name7 }));
    await waitFor(() => expect(api.updateProductSku).toHaveBeenCalledWith("sku-1", expect.objectContaining({
      variant_attrs: {
        [zhAttributes.color]: zhCN.pagesProductsPage.message,
        [zhAttributes.sizeSequence]: 42,
        [zhAttributes.packaging]: { [zhAttributes.packagingType]: zhCN.pagesProductsPage.message2, [zhAttributes.itemCount]: 1 },
      },
    })));
    expect(api.updateProductSku.mock.calls[0][1]).not.toHaveProperty("product_id");

    await user.click(within(workspace).getByRole("button", { name: zhCN.pagesProductsPage.name2 }));
    await waitFor(() => expect(api.listProductSkus).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));
    await user.click(within(workspace).getByRole("button", { name: zhCN.pagesProductsPage.name13() }));
    await user.type(screen.getByLabelText(zhCN.pagesProductsPage.sKUCode), "P-100-BLUE-M");
    await user.type(screen.getByLabelText(zhCN.pagesProductsPage.message19), zhCN.pagesProductsPage.message20);
    await user.type(screen.getByLabelText(zhCN.pagesProductsPage.message21), zhCN.pagesProductsPage.message22);
    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name14() }));
    await user.type(screen.getByLabelText(zhCN.pagesProductsPage.message23), zhCN.pagesProductsPage.size);
    await user.type(screen.getByLabelText(zhCN.pagesProductsPage.message14), "M");
    await user.type(screen.getByLabelText(zhCN.pagesProductsPage.variantPrice), "419.00");
    await user.click(screen.getByRole("button", { name: zhCN.pagesProductsPage.name15 }));
    await waitFor(() => expect(api.createProductSku).toHaveBeenCalledWith(expect.objectContaining({
      product_id: "product-1",
      sku_code: "P-100-BLUE-M",
      variant_attrs: { [zhAttributes.color]: zhCN.pagesProductsPage.message22, [zhAttributes.size]: "M" },
      list_price: 419,
    })));
    await waitFor(() => {
      const calls = api.listProductSkus.mock.calls.map(([filters]) => filters.page);
      expect(calls.at(-1)).toBe(1);
    });

    await user.click(within(workspace).getByRole("button", { name: zhCN.pagesProductsPage.name8 }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: zhCN.pagesProductsPage.name9 }));
    await waitFor(() => expect(api.archiveProductSku).toHaveBeenCalledWith("sku-1"));
    expect(screen.getByRole("button", { name: "SKU · 1" })).toBeInTheDocument();
  });

  it("shows an empty state for a product without SKU variants", async () => {
    api.listProductSkus.mockResolvedValue({ data: [], meta: { total: 0, page: 1, page_size: 20, pages: 1 } });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(zhCN.pagesProductsPage.name);
    await user.click(screen.getByRole("button", { name: "SKU · 1" }));
    expect(await screen.findByText(zhCN.pagesProductsPage.thisProductHasNoSKUsYet)).toBeInTheDocument();
  });

  it("batch-creates a size run and reports both created and skipped values", async () => {
    api.batchCreateProductSkus.mockResolvedValueOnce({
      created: [
        { ...sku, id: "sku-s", sku_code: "P-100-S", variant_attrs: { [zhAttributes.size]: "S" } },
        { ...sku, id: "sku-l", sku_code: null, variant_attrs: { [zhAttributes.size]: "L" } },
      ],
      skipped: ["M", "XL"],
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(zhCN.pagesProductsPage.name);
    await user.click(screen.getByRole("button", { name: "SKU · 1" }));
    const workspace = await screen.findByRole("region", { name: zhCN.pagesProductsPage.name11 });
    await user.click(within(workspace).getByRole("button", { name: zhCN.pagesProductsPage.name16 }));
    const dialog = screen.getByRole("dialog");

    await user.clear(within(dialog).getByLabelText(zhCN.pagesProductsPage.pattern5()));
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesProductsPage.name17 }));
    expect(await within(dialog).findByText(zhCN.pagesProductsPage.enterAtLeastOneVariantValue)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText(zhCN.pagesProductsPage.pattern5()), "S, M，L XL");
    await user.type(within(dialog).getByLabelText(zhCN.pagesProductsPage.sharedVariantPrice), "429.90");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesProductsPage.name17 }));

    await waitFor(() => expect(api.batchCreateProductSkus).toHaveBeenCalledWith("product-1", {
      dimension: zhCN.pagesProductsPage.size,
      values: ["S", "M", "L", "XL"],
      list_price: 429.9,
    }));
    expect(await screen.findByText(zhCN.pagesProductsPage.message29)).toBeInTheDocument();
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
    await screen.findByText(zhCN.pagesProductsPage.name);
    await user.click(screen.getByRole("button", { name: "SKU · 1" }));
    const workspace = await screen.findByRole("region", { name: zhCN.pagesProductsPage.name11 });
    await user.click(within(workspace).getByRole("button", { name: zhCN.pagesProductsPage.name16 }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(zhCN.pagesProductsPage.pattern5()), "S M");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesProductsPage.name17 }));

    expect(within(dialog).getByRole("button", { name: zhCN.pagesProductsPage.name18 })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: zhCN.pagesProductsPage.name19 })).toBeDisabled();
    act(() => rejectBatch(new Error(zhCN.pagesProductsPage.message30)));
    expect(await within(dialog).findByText(zhCN.pagesProductsPage.message30)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: zhCN.pagesProductsPage.name17 })).not.toBeDisabled();
  });

  it("does not create new SKUs under an archived product", async () => {
    api.listProducts.mockResolvedValue({
      data: [{ ...product, status: "archived" }],
      meta: { total: 1, page: 1, page_size: 20, pages: 1 },
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(zhCN.pagesProductsPage.name);
    await user.click(screen.getByRole("button", { name: "SKU · 1" }));

    const createButton = await screen.findByRole("button", { name: zhCN.pagesProductsPage.name13() });
    expect(createButton).toBeDisabled();
    expect(createButton).toHaveAttribute("title", zhCN.pagesProductsPage.restoreTheProductToActiveFirst);
    const batchButton = screen.getByRole("button", { name: zhCN.pagesProductsPage.name16 });
    expect(batchButton).toBeDisabled();
    expect(batchButton).toHaveAttribute("title", zhCN.pagesProductsPage.restoreTheProductToActiveFirst);
  });

  it("returns to the last valid SKU page when variants shrink", async () => {
    api.listProductSkus.mockImplementation(({ page = 1 }: { page?: number }) => Promise.resolve(
      page === 2
        ? { data: [], meta: { total: 1, page: 2, page_size: 20, pages: 1 } }
        : { data: [sku], meta: { total: 21, page: 1, page_size: 20, pages: 2 } },
    ));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(zhCN.pagesProductsPage.name);
    await user.click(screen.getByRole("button", { name: "SKU · 1" }));
    const workspace = await screen.findByRole("region", { name: zhCN.pagesProductsPage.name11 });
    await within(workspace).findByText("P-100-GRAY-L");
    await user.click(within(workspace).getByRole("button", { name: zhCN.pagesProductsPage.name2 }));
    await waitFor(() => expect(api.listProductSkus).toHaveBeenCalledWith(
      expect.objectContaining({ page: 2 }),
    ));

    await waitFor(() => {
      const pages = api.listProductSkus.mock.calls.map(([filters]) => filters.page);
      expect(pages.at(-1)).toBe(1);
    });
  });
});
