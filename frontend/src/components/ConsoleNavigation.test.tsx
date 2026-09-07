import { StrictMode, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  render,
  screen,
  waitFor,
  cleanup,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { AppShell } from "./AppShell";
import { ListToolbar } from "./master-data/ListToolbar";
import { useListFilters } from "./master-data/useListFilters";
import { LanguageProvider } from "../i18n";
import type { BootstrapData } from "../api/client";

const admin: BootstrapData = {
  user: { id: "u-1", name: "Admin", email: "admin@example.com" },
  tenant: { id: "t-1", name: "Example", email_domain: "example.com" },
  role: "admin",
  permissions: ["users.manage", "employees.manage"],
  employee_id: "e-1",
};
function ListProbe() {
  const filters = useListFilters(["active", "archived"]);
  const [created, setCreated] = useState(0);
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <output data-testid="location">
        {location.pathname}
        {location.search}
      </output>
      <output data-testid="filters">
        {JSON.stringify({
          keyword: filters.keyword,
          status: filters.status,
          page: filters.page,
        })}
      </output>
      <output data-testid="created">{created}</output>
      <ListToolbar
        {...filters}
        placeholder="Find a customer"
        createLabel="New customer"
        statusOptions={[
          { value: "active", label: "Active" },
          { value: "archived", label: "Archived" },
        ]}
        onApply={filters.applyFilters}
        onCreate={() => setCreated((value) => value + 1)}
      />
      <button onClick={() => filters.setPage(2)}>Page two</button>
      <button onClick={() => navigate(-1)}>Back</button>
    </>
  );
}
function renderConsole(path = "/dashboard", bootstrap = admin) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <LanguageProvider>
          <MemoryRouter initialEntries={[path]}>
            <AppShell bootstrap={bootstrap}>
              <ListProbe />
            </AppShell>
          </MemoryRouter>
        </LanguageProvider>
      </QueryClientProvider>
    </StrictMode>,
  );
}
beforeEach(() => {
  localStorage.setItem("oryh.console.language", "en");
});
afterEach(cleanup);

describe("Console navigation and list continuity", () => {
  it("opens the finder by keyboard and navigates to a selected result", async () => {
    const user = userEvent.setup();
    renderConsole();
    await user.keyboard("{Control>}k{/Control}");
    const input = screen.getByRole("combobox", {
      name: "Search pages or actions",
    });
    expect(input).toHaveFocus();
    await user.type(input, "products");
    await user.keyboard("{Enter}");
    expect(screen.getByTestId("location")).toHaveTextContent("/products");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("keeps forbidden destinations out of the finder and hides global creation", async () => {
    const user = userEvent.setup();
    renderConsole("/dashboard", { ...admin, role: "member", permissions: [] });
    expect(
      screen.queryByRole("button", { name: "Create" }),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Find pages and actions" }),
    );
    await user.type(
      screen.getByRole("combobox", { name: "Search pages or actions" }),
      "customers",
    );
    expect(
      within(screen.getByRole("dialog")).queryByRole("option"),
    ).not.toBeInTheDocument();
    expect(
      within(screen.getByRole("dialog")).getByRole("status"),
    ).toHaveTextContent("No matches");
    await user.keyboard("{Escape}");
    expect(
      screen.getByRole("button", { name: "Find pages and actions" }),
    ).toHaveFocus();
  });
  it("consumes a create link once under StrictMode without losing list filters", async () => {
    renderConsole("/customers?keyword=Acme&status=active&page=2&create=1");
    await waitFor(() =>
      expect(screen.getByTestId("created")).toHaveTextContent("1"),
    );
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/customers?keyword=Acme&status=active&page=2",
    );
    expect(screen.getByTestId("location")).not.toHaveTextContent("create=");
    expect(screen.getByRole("searchbox")).toHaveValue("Acme");
  });
  it("restores search and pagination when navigating Back", async () => {
    const user = userEvent.setup();
    renderConsole("/customers?keyword=Acme&status=active&page=4");
    await user.clear(screen.getByRole("searchbox"));
    await user.type(screen.getByRole("searchbox"), "  North  ");
    await user.click(screen.getByRole("button", { name: "Filter" }));
    expect(screen.getByTestId("filters")).toHaveTextContent(
      '"keyword":"North","status":"active","page":1',
    );
    await user.click(screen.getByRole("button", { name: "Page two" }));
    expect(screen.getByTestId("filters")).toHaveTextContent('"page":2');
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByTestId("filters")).toHaveTextContent('"page":1');
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("searchbox")).toHaveValue("Acme");
    expect(screen.getByTestId("filters")).toHaveTextContent('"page":4');
  });
  it("normalizes malformed filters and page numbers", () => {
    renderConsole("/customers?status=deleted&page=-12");
    expect(screen.getByTestId("filters")).toHaveTextContent(
      '"status":"","page":1',
    );
  });
});
