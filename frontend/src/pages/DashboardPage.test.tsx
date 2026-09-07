import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { DashboardPage } from "./DashboardPage";
import { LanguageProvider } from "../i18n";
import { ApiError, type BootstrapData } from "../api/client";
const api = vi.hoisted(() => ({ getDashboard: vi.fn(), listTodos: vi.fn() }));
vi.mock("../api/client", async () => ({
  ...(await vi.importActual<typeof import("../api/client")>("../api/client")),
  getDashboard: api.getDashboard,
}));
vi.mock("../api/activity", async () => ({
  ...(await vi.importActual<typeof import("../api/activity")>(
    "../api/activity",
  )),
  listTodos: api.listTodos,
}));
const bootstrap: BootstrapData = {
  user: { id: "u-1", name: "Sam", email: "sam@example.com" },
  tenant: { id: "t-1", name: "Example", email_domain: "example.com" },
  role: "admin",
  permissions: ["users.manage"],
  employee_id: "e-1",
};
function renderDashboard(overrides: Partial<BootstrapData> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider defaultLanguage="en">
        <MemoryRouter>
          <Routes>
            <Route
              element={
                <Outlet
                  context={{ bootstrap: { ...bootstrap, ...overrides } }}
                />
              }
            >
              <Route index element={<DashboardPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </LanguageProvider>
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  vi.resetAllMocks();
  localStorage.setItem("oryh.console.language", "en");
  api.getDashboard.mockResolvedValue({
    counts: {
      users: 12,
      todos_open: 8,
      todos_overdue: 2,
      objects: 42,
      skills: 3,
    },
  });
  api.listTodos.mockResolvedValue({
    data: [],
    meta: { total: 0, page: 1, page_size: 5, pages: 1 },
  });
});
afterEach(cleanup);
describe("workspace dashboard", () => {
  it("labels tenant-wide metrics and scopes a member's queue to their employee", async () => {
    renderDashboard({ role: "member", permissions: [] });
    await waitFor(() =>
      expect(api.listTodos).toHaveBeenCalledWith({
        status: "open",
        size: 5,
        employee_id: "e-1",
      }),
    );
    expect(await screen.findByTestId("metric-todos_open")).toHaveTextContent(
      "8",
    );
    expect(screen.getByText("Scope: entire workspace")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "My open to-dos" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Business records 42/ }),
    ).not.toBeInTheDocument();
  });
  it("does not issue a broad queue query for a member without an employee", async () => {
    renderDashboard({ role: "member", permissions: [], employee_id: null });
    expect(
      await screen.findByText("Link an employee profile to see your to-dos"),
    ).toBeInTheDocument();
    expect(api.listTodos).not.toHaveBeenCalled();
  });
  it("links a queue item to its open to-do search with special characters encoded", async () => {
    api.listTodos.mockResolvedValue({
      data: [
        {
          id: "t-1",
          title: "Confirm A & B / Q4",
          entity_type: "sales_quotation",
          entity_id: "q-1",
          employee_id: "e-1",
          status: "open",
          created_at: "2026-09-01T00:00:00Z",
        },
      ],
      meta: { total: 1, page: 1, page_size: 5, pages: 1 },
    });
    renderDashboard();
    const link = await screen.findByRole("link", { name: /Confirm A & B/ });
    expect(link).toHaveAttribute(
      "href",
      "/todos?status=open&keyword=Confirm%20A%20%26%20B%20%2F%20Q4",
    );
    expect(api.listTodos).toHaveBeenCalledWith({
      status: "open",
      size: 5,
      employee_id: undefined,
    });
  });
  it("keeps errors distinct from a successful zero count or empty queue", async () => {
    api.getDashboard.mockRejectedValue(new ApiError(403, "Unavailable"));
    api.listTodos.mockRejectedValue(new Error("Queue unavailable"));
    renderDashboard();
    await waitFor(() => expect(screen.getAllByRole("alert")).toHaveLength(2));
    expect(screen.queryByTestId("metric-users")).not.toBeInTheDocument();
    expect(screen.queryByText("No open to-dos")).not.toBeInTheDocument();
  });
});
