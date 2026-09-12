import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { dataCatalog, findResource, nextOrderBy, parseOrderBy } from "../api/dataCatalog";
import { DataBrowserPage } from "./DataBrowserPage";

const api = vi.hoisted(() => ({ apiRequestEnvelope: vi.fn() }));
vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, apiRequestEnvelope: api.apiRequestEnvelope };
});

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/data" element={<DataBrowserPage />} />
          <Route path="/data/:resource" element={<DataBrowserPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the generated catalogue", () => {
  it("names every paged collection with its filters and columns", () => {
    expect(dataCatalog.resources.length).toBeGreaterThan(50);
    const orders = findResource("sales-orders");
    expect(orders?.path).toBe("/api/v1/sales-orders");
    expect(orders?.filters.map((f) => f.name)).toContain("supersedes_order_id");
    expect(orders?.filters.find((f) => f.name === "include_deleted")?.type).toBe("boolean");
    expect(orders?.columns.map((c) => c.name)).toContain("order_no");
    // nested and array fields are not columns
    expect(orders?.columns.map((c) => c.name)).not.toContain("custom_fields");
    // the paging and sort params are the page's own controls, never filters
    for (const resource of dataCatalog.resources) {
      expect(resource.filters.map((f) => f.name)).not.toContain("page");
      expect(resource.filters.map((f) => f.name)).not.toContain("order_by");
    }
  });

  it("toggles a column between ascending and descending", () => {
    expect(nextOrderBy(null, "name")).toBe("name");
    expect(nextOrderBy("name", "name")).toBe("-name");
    expect(nextOrderBy("-name", "name")).toBe("name");
    expect(nextOrderBy("-name", "code")).toBe("code");
    expect(parseOrderBy("-created_at,order_no")).toEqual({ column: "created_at", descending: true });
  });
});

describe("DataBrowserPage", () => {
  it("lists every group in the directory", () => {
    renderAt("/data");
    expect(screen.getByTestId("data-directory")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Sales orders|销售订单/ })).toHaveAttribute("href", "/data/sales-orders");
  });

  it("requests the collection with the URL's filters, sorts from the header and pages", async () => {
    api.apiRequestEnvelope.mockResolvedValue({
      data: [{ id: "o-1", order_no: "SO-000001", status: "confirmed", total_amount: 1200 }],
      meta: { total: 60, page: 2, page_size: 25, pages: 3 },
    });
    renderAt("/data/sales-orders?status=confirmed&order_by=-order_no&page=2");
    await waitFor(() => expect(screen.getByText("SO-000001")).toBeInTheDocument());
    const url = api.apiRequestEnvelope.mock.calls[0][0] as string;
    expect(url.startsWith("/api/v1/sales-orders?")).toBe(true);
    const sent = new URLSearchParams(url.split("?")[1]);
    expect(sent.get("status")).toBe("confirmed");
    expect(sent.get("order_by")).toBe("-order_no");
    expect(sent.get("page")).toBe("2");
    expect(sent.get("size")).toBe("25");
    expect(sent.has("keyword")).toBe(false);
    // the sorted column says so
    expect(screen.getByRole("columnheader", { name: "order_no" })).toHaveAttribute("aria-sort", "descending");
    // the row links to the existing record detail
    expect(screen.getByRole("link", { name: /Trail|轨迹/ })).toHaveAttribute("href", expect.stringContaining("/objects/sales_order/o-1"));

    await userEvent.click(screen.getByRole("button", { name: "status" }));
    await waitFor(() => {
      const last = api.apiRequestEnvelope.mock.calls.at(-1)?.[0] as string;
      const params = new URLSearchParams(last.split("?")[1]);
      expect(params.get("order_by")).toBe("status");
      expect(params.get("page")).toBe("1");
    });
  });

  it("shows the restricted state on 403 instead of an error", async () => {
    api.apiRequestEnvelope.mockRejectedValue(new ApiError(403, "forbidden"));
    renderAt("/data/pay-histories");
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/not visible|无权/));
  });
});

describe("writes are confirmed with the facts they send", () => {
  it("edits a record: only the changed fields, shown before PATCH", async () => {
    api.apiRequestEnvelope.mockImplementation((path: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "GET") {
        return Promise.resolve({
          data: [{ id: "c-1", name: "Acme", tax_id: "91330100", status: "active", contact: "Li" }],
          meta: { total: 1, page: 1, page_size: 25, pages: 1 },
        });
      }
      return Promise.resolve({ data: { id: "c-1" }, meta: {} });
    });
    renderAt("/data/customers");
    await waitFor(() => expect(screen.getByText("Acme")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /Edit|编辑/ }));
    const name = screen.getByLabelText("name");
    await userEvent.clear(name);
    await userEvent.type(name, "Acme Ltd");
    await userEvent.click(screen.getByRole("button", { name: /Next: confirm|下一步/ }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("PATCH /api/v1/customers/c-1");
    expect(dialog).toHaveTextContent("Acme Ltd");
    // untouched fields are not in the preview and not in the body
    expect(dialog).not.toHaveTextContent("91330100");
    expect(api.apiRequestEnvelope.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === "PATCH")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: /Confirm write|确认写入/ }));
    await waitFor(() => {
      const patch = api.apiRequestEnvelope.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PATCH");
      expect(patch?.[0]).toBe("/api/v1/customers/c-1");
      expect(JSON.parse(String((patch?.[1] as RequestInit).body))).toEqual({ name: "Acme Ltd" });
    });
    expect(await screen.findByRole("status")).toHaveTextContent(/saved|已保存/);
  });

  it("runs a record verb against its own path, and nothing is sent before the confirmation", async () => {
    api.apiRequestEnvelope.mockImplementation((_path: string, init?: RequestInit) =>
      Promise.resolve((init?.method ?? "GET") === "GET"
        ? { data: [{ id: "o-9", order_no: "SO-000009", status: "confirmed" }], meta: { total: 1, page: 1, page_size: 25, pages: 1 } }
        : { data: { id: "o-10" }, meta: {} }),
    );
    renderAt("/data/sales-orders");
    await waitFor(() => expect(screen.getByText("SO-000009")).toBeInTheDocument());
    await userEvent.click(screen.getByText(/Actions|动作/));
    await userEvent.click(screen.getByRole("button", { name: "revise" }));
    await userEvent.type(screen.getByLabelText("reason"), "cannot ship");
    await userEvent.click(screen.getByRole("button", { name: /Next: confirm|下一步/ }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("POST /api/v1/sales-orders/o-9/revise");
    expect(dialog).toHaveTextContent("cannot ship");
    expect(api.apiRequestEnvelope.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "POST")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: /Confirm write|确认写入/ }));
    await waitFor(() => {
      const post = api.apiRequestEnvelope.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST");
      expect(post?.[0]).toBe("/api/v1/sales-orders/o-9/revise");
      expect(JSON.parse(String((post?.[1] as RequestInit).body))).toEqual({ reason: "cannot ship" });
    });
  });

  it("creates a record from the contract's fields and omits what was left blank", async () => {
    api.apiRequestEnvelope.mockImplementation((_path: string, init?: RequestInit) =>
      Promise.resolve((init?.method ?? "GET") === "GET"
        ? { data: [], meta: { total: 0, page: 1, page_size: 25, pages: 0 } }
        : { data: { id: "v-1" }, meta: {} }),
    );
    renderAt("/data/vendors");
    await userEvent.click(await screen.findByRole("button", { name: /Create|新建/ }));
    await userEvent.type(screen.getByLabelText(/^name/), "Probe Supplier");
    await userEvent.click(screen.getByRole("button", { name: /Next: confirm|下一步/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Confirm write|确认写入/ }));
    await waitFor(() => {
      const post = api.apiRequestEnvelope.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST");
      expect(post?.[0]).toBe("/api/v1/vendors");
      expect(JSON.parse(String((post?.[1] as RequestInit).body))).toEqual({ name: "Probe Supplier" });
    });
  });

  it("surfaces the server's refusal inside the confirmation instead of closing it", async () => {
    api.apiRequestEnvelope.mockImplementation((_path: string, init?: RequestInit) =>
      (init?.method ?? "GET") === "GET"
        ? Promise.resolve({ data: [{ id: "c-2", name: "Beta", status: "active" }], meta: { total: 1, page: 1, page_size: 25, pages: 1 } })
        : Promise.reject(new ApiError(409, "a live document still names this customer")),
    );
    renderAt("/data/customers");
    await waitFor(() => expect(screen.getByText("Beta")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /Delete|删除/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Confirm write|确认写入/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("still names this customer");
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });
});

describe("references and related records", () => {
  it("offers a picker for a *_id field, searching the target collection by keyword", async () => {
    api.apiRequestEnvelope.mockImplementation((path: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") !== "GET") return Promise.resolve({ data: { id: "o-new" }, meta: {} });
      if (path.startsWith("/api/v1/customers?")) {
        return Promise.resolve({ data: [{ id: "c-7", customer_code: "C-007", name: "Seven Hospital" }], meta: { total: 1, page: 1, page_size: 8, pages: 1 } });
      }
      if (path.startsWith("/api/v1/customers/c-7")) return Promise.resolve({ data: { id: "c-7", customer_code: "C-007", name: "Seven Hospital" }, meta: {} });
      return Promise.resolve({ data: [], meta: { total: 0, page: 1, page_size: 25, pages: 0 } });
    });
    renderAt("/data/sales-orders");
    await userEvent.click(await screen.findByRole("button", { name: /Create|新建/ }));
    const picker = document.getElementById("data-customer_id") as HTMLInputElement;
    await userEvent.click(picker);
    await userEvent.type(picker, "Seven");
    await userEvent.click(within(await screen.findByRole("option", { name: /Seven Hospital/ })).getByRole("button"));
    // the id landed, and the field now shows the row by its code and name
    expect(await screen.findByText(/C-007 · Seven Hospital/)).toBeInTheDocument();
    const searches = api.apiRequestEnvelope.mock.calls.map(([path]) => String(path)).filter((path) => path.startsWith("/api/v1/customers?"));
    expect(searches.map((path) => new URLSearchParams(path.split("?")[1]).get("keyword"))).toContain("Seven");
    expect(searches.every((path) => new URLSearchParams(path.split("?")[1]).get("size") === "8")).toBe(true);
    await userEvent.type(screen.getByLabelText(/^title/), "Picked");
    await userEvent.click(screen.getByRole("button", { name: /Next: confirm|下一步/ }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("c-7");
  });

  it("links a record's detail to its own sub-collections, already filtered", async () => {
    api.apiRequestEnvelope.mockResolvedValue({
      data: [{ id: "o-3", order_no: "SO-000003", status: "confirmed" }],
      meta: { total: 1, page: 1, page_size: 25, pages: 1 },
    });
    renderAt("/data/sales-orders");
    await waitFor(() => expect(screen.getByText("SO-000003")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /Detail|详情/ }));
    const nav = await screen.findByRole("navigation", { name: /Related|相关/ });
    expect(nav.querySelector('a[href="/data/sales-order-items?order_id=o-3"]')).not.toBeNull();
    expect(nav.querySelector('a[href="/data/sales-orders?supersedes_order_id=o-3"]')).not.toBeNull();
  });
});
