import { zhCN } from "../locales/zh-CN/tests";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Customer, Project, Resource, Vendor } from "../api/client";
import { CustomersPage } from "./CustomersPage";
import { ProjectsPage } from "./ProjectsPage";
import { ResourcesPage } from "./ResourcesPage";
import { VendorsPage } from "./VendorsPage";

const api = vi.hoisted(() => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  archiveProject: vi.fn(),
  listVendors: vi.fn(),
  createVendor: vi.fn(),
  updateVendor: vi.fn(),
  archiveVendor: vi.fn(),
  listCustomers: vi.fn(),
  listEmployees: vi.fn(),
  createCustomer: vi.fn(),
  updateCustomer: vi.fn(),
  archiveCustomer: vi.fn(),
  listResources: vi.fn(),
  createResource: vi.fn(),
  updateResource: vi.fn(),
  archiveResource: vi.fn(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, ...api };
});

const project = {
  id: "project-1",
  project_name: zhCN.pagesMasterDataPages.projectName,
  project_code: "PRJ-001",
  client: zhCN.pagesMasterDataPages.client,
  status: "active",
  start_date: "2026-07-01",
  end_date: null,
  metadata: {},
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as Project;

const resource = {
  id: "resource-1",
  resource_type: "meeting_room",
  name: zhCN.pagesMasterDataPages.name,
  code: "ROOM-1",
  location: "3F",
  capacity: 8,
  booking_mode: "exclusive",
  max_quantity: null,
  status: "active",
  metadata: {},
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as Resource;

const vendor = {
  id: "vendor-1",
  name: zhCN.pagesMasterDataPages.name2,
  vendor_code: "VEN-001",
  tax_id: "91310000TEST",
  contact: zhCN.pagesMasterDataPages.contact,
  phone: "13800000000",
  email: "vendor@example.com",
  status: "active",
  metadata: {},
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as Vendor;

const customer = {
  id: "customer-1",
  name: zhCN.pagesMasterDataPages.name3,
  customer_code: "CUS-001",
  tax_id: "91310000CUST",
  contact: zhCN.pagesMasterDataPages.contact2,
  phone: "13900000000",
  email: "customer@example.com",
  address: zhCN.pagesMasterDataPages.address,
  status: "active",
  metadata: {},
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as Customer;

function renderPage(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listProjects.mockResolvedValue({ data: [project], meta: { total: 21, page: 1, page_size: 20, pages: 2 } });
  api.createProject.mockResolvedValue(project);
  api.updateProject.mockResolvedValue(project);
  api.archiveProject.mockResolvedValue(undefined);
  api.listVendors.mockResolvedValue({ data: [vendor], meta: { total: 1, page: 1, page_size: 20, pages: 1 } });
  api.createVendor.mockResolvedValue(vendor);
  api.updateVendor.mockResolvedValue(vendor);
  api.archiveVendor.mockResolvedValue(undefined);
  api.listCustomers.mockResolvedValue({ data: [customer], meta: { total: 1, page: 1, page_size: 20, pages: 1 } });
  api.listEmployees.mockResolvedValue({ data: [], meta: { total: 0, page: 1, page_size: 20, pages: 1 } });
  api.createCustomer.mockResolvedValue(customer);
  api.updateCustomer.mockResolvedValue(customer);
  api.archiveCustomer.mockResolvedValue(undefined);
  api.listResources.mockResolvedValue({ data: [], meta: { total: 0, page: 1, page_size: 20, pages: 1 } });
  api.createResource.mockResolvedValue(resource);
  api.updateResource.mockResolvedValue(resource);
  api.archiveResource.mockResolvedValue(undefined);
});

afterEach(cleanup);

describe("project master data", () => {
  it("loads, filters and pages with server-side query parameters", async () => {
    const user = userEvent.setup();
    renderPage(<ProjectsPage />);

    expect(await screen.findByText(zhCN.pagesMasterDataPages.projectName)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name4 }));
    await waitFor(() => expect(api.listProjects).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));

    await user.type(screen.getByRole("searchbox"), zhCN.pagesMasterDataPages.message);
    await user.selectOptions(screen.getByLabelText(zhCN.pagesMasterDataPages.state), "archived");
    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name5 }));
    await waitFor(() => expect(api.listProjects).toHaveBeenCalledWith(expect.objectContaining({ page: 1, keyword: zhCN.pagesMasterDataPages.message, status: "archived" })));
  });

  it("creates, edits and archives through the accessible drawer and confirmation", async () => {
    const user = userEvent.setup();
    renderPage(<ProjectsPage />);
    await screen.findByText(zhCN.pagesMasterDataPages.projectName);

    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name6() }));
    await user.type(screen.getByLabelText(zhCN.pagesMasterDataPages.pattern()), zhCN.pagesMasterDataPages.message3);
    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name7 }));
    await waitFor(() => expect(api.createProject).toHaveBeenCalledWith(expect.objectContaining({ project_name: zhCN.pagesMasterDataPages.message3 })));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name8 }));
    const clientInput = screen.getByLabelText(zhCN.pagesMasterDataPages.customerNameText);
    await user.clear(clientInput);
    await user.type(clientInput, zhCN.pagesMasterDataPages.message5);
    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name9 }));
    await waitFor(() => expect(api.updateProject).toHaveBeenCalledWith("project-1", expect.objectContaining({ client: zhCN.pagesMasterDataPages.message5 })));

    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name10 }));
    const confirm = screen.getByRole("alertdialog");
    expect(within(confirm).getByText(zhCN.pagesMasterDataPages.pattern2())).toBeInTheDocument();
    await user.click(within(confirm).getByRole("button", { name: zhCN.pagesMasterDataPages.name11 }));
    await waitFor(() => expect(api.archiveProject).toHaveBeenCalledWith("project-1"));
  });

  it("returns to the first page after archiving the only row on a later page", async () => {
    api.listProjects.mockImplementation(({ page = 1 }: { page?: number }) => Promise.resolve({
      data: [project],
      meta: { total: 21, page, page_size: 20, pages: 2 },
    }));
    const user = userEvent.setup();
    renderPage(<ProjectsPage />);
    await screen.findByText(zhCN.pagesMasterDataPages.projectName);
    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name4 }));
    await waitFor(() => expect(api.listProjects).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));
    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name10 }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: zhCN.pagesMasterDataPages.name11 }));
    await waitFor(() => {
      const calls = api.listProjects.mock.calls.map(([filters]) => filters.page);
      expect(calls.at(-1)).toBe(1);
    });
  });

  it("returns to the first page after creating from a later page", async () => {
    const user = userEvent.setup();
    renderPage(<ProjectsPage />);
    await screen.findByText(zhCN.pagesMasterDataPages.projectName);
    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name4 }));
    await waitFor(() => expect(api.listProjects).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));

    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name6() }));
    await user.type(screen.getByLabelText(zhCN.pagesMasterDataPages.pattern()), zhCN.pagesMasterDataPages.message6);
    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name7 }));
    await waitFor(() => {
      const calls = api.listProjects.mock.calls.map(([filters]) => filters.page);
      expect(calls.at(-1)).toBe(1);
    });
  });

  it("shows a recoverable list error", async () => {
    api.listProjects.mockRejectedValue(new Error(zhCN.pagesMasterDataPages.message7));
    renderPage(<ProjectsPage />);
    expect(await screen.findByText(zhCN.pagesMasterDataPages.dataCouldNotBeLoaded)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesMasterDataPages.message7)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name12 })).toBeInTheDocument();
  });
});

describe("resource booking mode", () => {
  it("requires max quantity for shared resources and sends the shared rule", async () => {
    const user = userEvent.setup();
    renderPage(<ResourcesPage />);
    await screen.findByText(zhCN.pagesMasterDataPages.noResourcesYet);

    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name13() }));
    await user.type(screen.getByLabelText(zhCN.pagesMasterDataPages.pattern3()), zhCN.pagesMasterDataPages.message10);
    await user.click(screen.getByRole("radio", { name: zhCN.pagesMasterDataPages.name14() }));
    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name15 }));
    expect(await screen.findByText(zhCN.pagesMasterDataPages.pattern4())).toBeInTheDocument();
    expect(api.createResource).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText(zhCN.pagesMasterDataPages.pattern5()), "12");
    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name15 }));
    await waitFor(() => expect(api.createResource).toHaveBeenCalledWith(expect.objectContaining({
      booking_mode: "shared",
      max_quantity: 12,
    })));
  });
});

describe("vendor master data", () => {
  it("renders a vendor and keeps unsupported inactive status out of the form", async () => {
    const user = userEvent.setup();
    renderPage(<VendorsPage />);
    expect(await screen.findByText(zhCN.pagesMasterDataPages.name2)).toBeInTheDocument();
    expect(screen.getByText("91310000TEST")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name16() }));
    expect(screen.queryByRole("option", { name: zhCN.pagesMasterDataPages.name17 })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText(zhCN.pagesMasterDataPages.pattern6()), zhCN.pagesMasterDataPages.message11);
    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name18 }));
    await waitFor(() => expect(api.createVendor).toHaveBeenCalledWith(expect.objectContaining({ name: zhCN.pagesMasterDataPages.message11 })));
  });
});

describe("customer master data", () => {
  it("renders a customer, edits the address, and creates without an inactive status option", async () => {
    const user = userEvent.setup();
    renderPage(<CustomersPage />);
    expect(await screen.findByText(zhCN.pagesMasterDataPages.name3)).toBeInTheDocument();
    expect(screen.getByText("91310000CUST")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name8 }));
    expect(screen.getByLabelText(zhCN.pagesMasterDataPages.address2)).toHaveValue(zhCN.pagesMasterDataPages.address);
    const address = screen.getByLabelText(zhCN.pagesMasterDataPages.address2);
    await user.clear(address);
    await user.type(address, zhCN.pagesMasterDataPages.message13);
    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name9 }));
    await waitFor(() => expect(api.updateCustomer).toHaveBeenCalledWith("customer-1", expect.objectContaining({ address: zhCN.pagesMasterDataPages.message13 })));

    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name19() }));
    expect(screen.queryByRole("option", { name: zhCN.pagesMasterDataPages.name17 })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText(zhCN.pagesMasterDataPages.pattern7()), zhCN.pagesMasterDataPages.message5);
    await user.click(screen.getByRole("button", { name: zhCN.pagesMasterDataPages.name20 }));
    await waitFor(() => expect(api.createCustomer).toHaveBeenCalledWith(expect.objectContaining({ name: zhCN.pagesMasterDataPages.message5, address: null })));
  });
});
