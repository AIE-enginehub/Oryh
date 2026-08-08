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
  project_name: "云端迁移",
  project_code: "PRJ-001",
  client: "示例客户",
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
  name: "海棠会议室",
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
  name: "北辰服务",
  vendor_code: "VEN-001",
  tax_id: "91310000TEST",
  contact: "王经理",
  phone: "13800000000",
  email: "vendor@example.com",
  status: "active",
  metadata: {},
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as Vendor;

const customer = {
  id: "customer-1",
  name: "华欣机械",
  customer_code: "CUS-001",
  tax_id: "91310000CUST",
  contact: "王工",
  phone: "13900000000",
  email: "customer@example.com",
  address: "上海市浦东新区",
  status: "active",
  metadata: {},
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as Customer;

function renderPage(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
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

    expect(await screen.findByText("云端迁移")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listProjects).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));

    await user.type(screen.getByRole("searchbox"), "迁移");
    await user.selectOptions(screen.getByLabelText("状态"), "archived");
    await user.click(screen.getByRole("button", { name: "筛选" }));
    await waitFor(() => expect(api.listProjects).toHaveBeenCalledWith(expect.objectContaining({ page: 1, keyword: "迁移", status: "archived" })));
  });

  it("creates, edits and archives through the accessible drawer and confirmation", async () => {
    const user = userEvent.setup();
    renderPage(<ProjectsPage />);
    await screen.findByText("云端迁移");

    await user.click(screen.getByRole("button", { name: /新建项目/ }));
    await user.type(screen.getByLabelText(/项目名称/), "内部升级");
    await user.click(screen.getByRole("button", { name: "创建项目" }));
    await waitFor(() => expect(api.createProject).toHaveBeenCalledWith(expect.objectContaining({ project_name: "内部升级" })));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "编辑" }));
    const clientInput = screen.getByLabelText("客户");
    await user.clear(clientInput);
    await user.type(clientInput, "新客户");
    await user.click(screen.getByRole("button", { name: "保存更改" }));
    await waitFor(() => expect(api.updateProject).toHaveBeenCalledWith("project-1", expect.objectContaining({ client: "新客户" })));

    await user.click(screen.getByRole("button", { name: "归档" }));
    const confirm = screen.getByRole("alertdialog");
    expect(within(confirm).getByText(/不会删除历史引用/)).toBeInTheDocument();
    await user.click(within(confirm).getByRole("button", { name: "确认归档" }));
    await waitFor(() => expect(api.archiveProject).toHaveBeenCalledWith("project-1"));
  });

  it("returns to the first page after archiving the only row on a later page", async () => {
    api.listProjects.mockImplementation(({ page = 1 }: { page?: number }) => Promise.resolve({
      data: [project],
      meta: { total: 21, page, page_size: 20, pages: 2 },
    }));
    const user = userEvent.setup();
    renderPage(<ProjectsPage />);
    await screen.findByText("云端迁移");
    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listProjects).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));
    await user.click(screen.getByRole("button", { name: "归档" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "确认归档" }));
    await waitFor(() => {
      const calls = api.listProjects.mock.calls.map(([filters]) => filters.page);
      expect(calls.at(-1)).toBe(1);
    });
  });

  it("returns to the first page after creating from a later page", async () => {
    const user = userEvent.setup();
    renderPage(<ProjectsPage />);
    await screen.findByText("云端迁移");
    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listProjects).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));

    await user.click(screen.getByRole("button", { name: /新建项目/ }));
    await user.type(screen.getByLabelText(/项目名称/), "第二页新建");
    await user.click(screen.getByRole("button", { name: "创建项目" }));
    await waitFor(() => {
      const calls = api.listProjects.mock.calls.map(([filters]) => filters.page);
      expect(calls.at(-1)).toBe(1);
    });
  });

  it("shows a recoverable list error", async () => {
    api.listProjects.mockRejectedValue(new Error("数据库暂时不可用"));
    renderPage(<ProjectsPage />);
    expect(await screen.findByText("数据加载失败")).toBeInTheDocument();
    expect(screen.getByText("数据库暂时不可用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  });
});

describe("resource booking mode", () => {
  it("requires max quantity for shared resources and sends the shared rule", async () => {
    const user = userEvent.setup();
    renderPage(<ResourcesPage />);
    await screen.findByText("还没有资源");

    await user.click(screen.getByRole("button", { name: /新建资源/ }));
    await user.type(screen.getByLabelText(/资源名称/), "共享工位");
    await user.click(screen.getByRole("radio", { name: /共享数量/ }));
    await user.click(screen.getByRole("button", { name: "创建资源" }));
    expect(await screen.findByText(/共享资源必须设置/)).toBeInTheDocument();
    expect(api.createResource).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText(/最大可预订数量/), "12");
    await user.click(screen.getByRole("button", { name: "创建资源" }));
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
    expect(await screen.findByText("北辰服务")).toBeInTheDocument();
    expect(screen.getByText("91310000TEST")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /新建供应商/ }));
    expect(screen.queryByRole("option", { name: "停用" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText(/供应商名称/), "新供应商");
    await user.click(screen.getByRole("button", { name: "创建供应商" }));
    await waitFor(() => expect(api.createVendor).toHaveBeenCalledWith(expect.objectContaining({ name: "新供应商" })));
  });
});

describe("customer master data", () => {
  it("renders a customer, edits the address, and creates without an inactive status option", async () => {
    const user = userEvent.setup();
    renderPage(<CustomersPage />);
    expect(await screen.findByText("华欣机械")).toBeInTheDocument();
    expect(screen.getByText("91310000CUST")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "编辑" }));
    expect(screen.getByLabelText("地址")).toHaveValue("上海市浦东新区");
    const address = screen.getByLabelText("地址");
    await user.clear(address);
    await user.type(address, "北京市朝阳区");
    await user.click(screen.getByRole("button", { name: "保存更改" }));
    await waitFor(() => expect(api.updateCustomer).toHaveBeenCalledWith("customer-1", expect.objectContaining({ address: "北京市朝阳区" })));

    await user.click(screen.getByRole("button", { name: /新建客户/ }));
    expect(screen.queryByRole("option", { name: "停用" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText(/客户名称/), "新客户");
    await user.click(screen.getByRole("button", { name: "创建客户" }));
    await waitFor(() => expect(api.createCustomer).toHaveBeenCalledWith(expect.objectContaining({ name: "新客户", address: null })));
  });
});
