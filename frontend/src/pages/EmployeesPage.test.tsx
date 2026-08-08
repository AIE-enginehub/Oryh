import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ConsoleContext } from "../App";
import { ApiError, type Employee, type InvitationUser, type Role } from "../api/client";
import { EmployeesPage } from "./EmployeesPage";

const api = vi.hoisted(() => ({
  listEmployees: vi.fn(),
  createEmployee: vi.fn(),
  updateEmployee: vi.fn(),
  inviteUser: vi.fn(),
  listRoles: vi.fn(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, ...api };
});

const employee = {
  id: "employee-1",
  employee_code: "EMP-001",
  name: "林晓",
  email: "lin@example.com",
  timezone: "Asia/Shanghai",
  status: "active",
  metadata: {},
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as Employee;

const roles = [
  { id: "role-admin", tenant_id: "tenant-1", name: "admin", title: "管理员", description: null, permissions: ["users.manage"], is_system: true, created_at: "2026-01-01T00:00:00Z", updated_at: null },
  { id: "role-member", tenant_id: "tenant-1", name: "member", title: "成员", description: null, permissions: [], is_system: true, created_at: "2026-01-01T00:00:00Z", updated_at: null },
  { id: "role-auditor", tenant_id: "tenant-1", name: "auditor", title: "审计员", description: null, permissions: [], is_system: false, created_at: "2026-01-01T00:00:00Z", updated_at: null },
] as Role[];

const bootstrap = {
  user: { id: "user-admin", email: "admin@example.com", name: "租户管理员" },
  tenant: { id: "tenant-1", name: "示例公司", email_domain: "example.com" },
  role: "admin",
  permissions: ["employees.manage", "users.manage"],
  employee_id: "employee-admin",
};

function renderPage(permissions = bootstrap.permissions) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const context = { bootstrap: { ...bootstrap, permissions } } as ConsoleContext;
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Routes>
          <Route element={<Outlet context={context} />}>
            <Route index element={<EmployeesPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listEmployees.mockResolvedValue({
    data: [employee],
    meta: { total: 21, page: 1, page_size: 20, pages: 2 },
  });
  api.createEmployee.mockResolvedValue(employee);
  api.updateEmployee.mockResolvedValue(employee);
  api.listRoles.mockResolvedValue(roles);
  api.inviteUser.mockResolvedValue({
    id: "user-new",
    tenant_id: "tenant-1",
    email: "zhou@example.com",
    name: "周宁",
    role: "auditor",
    employee_id: "employee-1",
    status: "invited",
    invitation_pending: true,
    email_verified_at: null,
    created_at: "2026-07-12T00:00:00Z",
    updated_at: null,
    invitation_url: "https://console.example/invitations/accept?token=one-time",
  } as InvitationUser);
});

afterEach(cleanup);

describe("employee directory", () => {
  it("loads employees and sends server-side page, keyword, and status filters", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("林晓")).toBeInTheDocument();
    expect(screen.getByText("EMP-001")).toBeInTheDocument();
    expect(screen.getByText("Asia/Shanghai")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listEmployees).toHaveBeenCalledWith(
      expect.objectContaining({ page: 2, size: 20 }),
    ));

    await user.type(screen.getByRole("searchbox"), " 林 ");
    await user.selectOptions(screen.getByLabelText("状态"), "inactive");
    await user.click(screen.getByRole("button", { name: "筛选" }));
    await waitFor(() => expect(api.listEmployees).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, keyword: "林", status: "inactive" }),
    ));
  });

  it("validates fields, creates an employee, and edits all supported fields", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("林晓");

    await user.click(screen.getByRole("button", { name: /新增员工/ }));
    let dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "新增员工" }));
    expect(await within(dialog).findByText("姓名不能为空。")).toBeInTheDocument();
    expect(api.createEmployee).not.toHaveBeenCalled();

    await user.type(within(dialog).getByLabelText("姓名 *"), "周宁");
    await user.type(within(dialog).getByLabelText("工号"), "EMP-002");
    await user.type(within(dialog).getByLabelText("邮箱"), "not-an-email");
    await user.type(within(dialog).getByLabelText("工作时区"), "Shanghai");
    await user.click(within(dialog).getByRole("button", { name: "新增员工" }));
    expect(await within(dialog).findByText("请输入有效的邮箱地址。")).toBeInTheDocument();
    expect(within(dialog).getByText(/Area\/Location 格式/)).toBeInTheDocument();
    expect(api.createEmployee).not.toHaveBeenCalled();

    const email = within(dialog).getByLabelText("邮箱");
    const timezone = within(dialog).getByLabelText("工作时区");
    await user.clear(email);
    await user.type(email, "zhou@example.com");
    await user.clear(timezone);
    await user.type(timezone, "Asia/Shanghai");
    await user.click(within(dialog).getByRole("button", { name: "新增员工" }));

    await waitFor(() => expect(api.createEmployee).toHaveBeenCalledWith({
      name: "周宁",
      employee_code: "EMP-002",
      email: "zhou@example.com",
      timezone: "Asia/Shanghai",
      status: "active",
    }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "编辑" }));
    dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("姓名 *")).toHaveValue("林晓");
    expect(within(dialog).getByLabelText("邮箱")).toHaveValue("lin@example.com");
    await user.selectOptions(within(dialog).getByLabelText("状态"), "inactive");
    await user.clear(within(dialog).getByLabelText("工作时区"));
    await user.type(within(dialog).getByLabelText("工作时区"), "UTC");
    await user.click(within(dialog).getByRole("button", { name: "保存更改" }));

    await waitFor(() => expect(api.updateEmployee).toHaveBeenCalledWith(
      "employee-1",
      expect.objectContaining({
        name: "林晓",
        employee_code: "EMP-001",
        email: "lin@example.com",
        timezone: "UTC",
        status: "inactive",
      }),
    ));
    expect(screen.queryByRole("button", { name: /删除|归档/ })).not.toBeInTheDocument();
  });

  it("can create an employee and an invited, linked user in one flow", async () => {
    const createdEmployee = {
      ...employee,
      id: "employee-new",
      name: "周宁",
      employee_code: "EMP-002",
      email: "zhou@example.com",
    } as Employee;
    api.createEmployee.mockResolvedValueOnce(createdEmployee);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("林晓");

    await user.click(screen.getByRole("button", { name: /新增员工/ }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("姓名 *"), "周宁");
    await user.type(within(dialog).getByLabelText("工号"), "EMP-002");
    await user.click(within(dialog).getByLabelText("同时创建登录用户"));
    await waitFor(() => expect(api.listRoles).toHaveBeenCalledOnce());
    expect(within(dialog).getByLabelText("状态")).toBeDisabled();
    expect(within(dialog).getByLabelText("邮箱 *")).toBeRequired();
    await waitFor(() => expect(within(dialog).getByLabelText("用户角色")).not.toBeDisabled());
    await user.selectOptions(within(dialog).getByLabelText("用户角色"), "auditor");

    await user.click(within(dialog).getByRole("button", { name: "新增员工并邀请" }));
    expect(await within(dialog).findByText("同时创建登录用户时必须填写邮箱。")).toBeInTheDocument();
    expect(api.createEmployee).not.toHaveBeenCalled();

    const email = within(dialog).getByLabelText("邮箱 *");
    await user.type(email, "zhou@.example.com");
    await user.click(within(dialog).getByRole("button", { name: "新增员工并邀请" }));
    expect(await within(dialog).findByText("请输入有效的邮箱地址。")).toBeInTheDocument();
    expect(api.createEmployee).not.toHaveBeenCalled();

    await user.clear(email);
    await user.type(email, "zhou@example.com");
    await user.click(within(dialog).getByRole("button", { name: "新增员工并邀请" }));

    await waitFor(() => expect(api.createEmployee).toHaveBeenCalledWith({
      name: "周宁",
      employee_code: "EMP-002",
      email: "zhou@example.com",
      timezone: null,
      status: "active",
    }));
    await waitFor(() => expect(api.inviteUser).toHaveBeenCalledWith({
      email: "zhou@example.com",
      name: "周宁",
      role: "auditor",
      employee_id: "employee-new",
    }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(await screen.findByText(/员工与登录用户已创建/)).toBeInTheDocument();
    expect(screen.getByLabelText("一次性邀请链接")).toHaveValue(
      "https://console.example/invitations/accept?token=one-time",
    );
    const clipboardWrite = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(screen.getByRole("button", { name: "复制邀请链接" }));
    expect(clipboardWrite).toHaveBeenCalledWith(
      "https://console.example/invitations/accept?token=one-time",
    );
  });

  it("reports the partial result when employee creation succeeds but invitation fails", async () => {
    api.createEmployee.mockResolvedValueOnce({
      ...employee,
      id: "employee-partial",
      name: "顾航",
      email: "gu@example.com",
    });
    api.inviteUser.mockRejectedValueOnce(new ApiError(409, "该邮箱已有登录用户"));
    const user = userEvent.setup();
    const { queryClient } = renderPage();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    await screen.findByText("林晓");

    await user.click(screen.getByRole("button", { name: /新增员工/ }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("姓名 *"), "顾航");
    await user.type(within(dialog).getByLabelText("邮箱"), "gu@example.com");
    await user.click(within(dialog).getByLabelText("同时创建登录用户"));
    await screen.findByLabelText("用户角色");
    await user.click(within(dialog).getByRole("button", { name: "新增员工并邀请" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent("员工「顾航」已创建，用户邀请未完成");
    expect(notice).toHaveTextContent("该邮箱已有登录用户");
    expect(within(notice).getByRole("link", { name: "前往用户管理" })).toHaveAttribute("href", "/users");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["users"] });
  });

  it("treats a transport error as an uncertain invitation outcome", async () => {
    api.createEmployee.mockResolvedValueOnce({
      ...employee,
      id: "employee-uncertain",
      name: "许澄",
      email: "xu@example.com",
    });
    api.inviteUser.mockRejectedValueOnce(new Error("网络连接中断"));
    const user = userEvent.setup();
    const { queryClient } = renderPage();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    await screen.findByText("林晓");

    await user.click(screen.getByRole("button", { name: /新增员工/ }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("姓名 *"), "许澄");
    await user.type(within(dialog).getByLabelText("邮箱"), "xu@example.com");
    await user.click(within(dialog).getByLabelText("同时创建登录用户"));
    await screen.findByLabelText("用户角色");
    await user.click(within(dialog).getByRole("button", { name: "新增员工并邀请" }));

    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent("员工「许澄」已创建，用户邀请结果未能确认");
    expect(notice).toHaveTextContent("请先前往用户管理核对");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["users"] });
  });

  it("does not expose combined user creation without users.manage", async () => {
    const user = userEvent.setup();
    renderPage(["employees.manage"]);
    await screen.findByText("林晓");
    await user.click(screen.getByRole("button", { name: /新增员工/ }));
    expect(within(screen.getByRole("dialog")).queryByLabelText("同时创建登录用户")).not.toBeInTheDocument();
  });

  it("fails closed when the tenant has no role available for the invited user", async () => {
    api.listRoles.mockResolvedValueOnce([]);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("林晓");

    await user.click(screen.getByRole("button", { name: /新增员工/ }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByLabelText("同时创建登录用户"));

    expect(await within(dialog).findByText(/当前工作空间没有可用角色/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "新增员工并邀请" })).toBeDisabled();
    expect(api.createEmployee).not.toHaveBeenCalled();
  });

  it("can recover when the role directory initially fails to load", async () => {
    api.listRoles
      .mockRejectedValueOnce(new Error("角色目录暂时不可用"))
      .mockResolvedValueOnce(roles);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("林晓");

    await user.click(screen.getByRole("button", { name: /新增员工/ }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByLabelText("同时创建登录用户"));
    expect(await within(dialog).findByText(/角色加载失败/)).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "重试加载角色" }));
    await waitFor(() => expect(within(dialog).getByLabelText("用户角色")).not.toBeDisabled());
    expect(api.listRoles).toHaveBeenCalledTimes(2);
  });

  it("shows loading and empty states", async () => {
    api.listEmployees.mockReturnValueOnce(new Promise(() => {}));
    const first = renderPage();
    expect(screen.getByText("正在加载数据…")).toBeInTheDocument();
    first.unmount();

    api.listEmployees.mockResolvedValue({
      data: [],
      meta: { total: 0, page: 1, page_size: 20, pages: 1 },
    });
    renderPage();
    expect(await screen.findByText("还没有员工")).toBeInTheDocument();
  });

  it("shows a recoverable list error", async () => {
    api.listEmployees.mockRejectedValue(new Error("员工目录暂时不可用"));
    renderPage();

    expect(await screen.findByText("数据加载失败")).toBeInTheDocument();
    expect(screen.getByText("员工目录暂时不可用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  });

  it("returns to the last valid page when a paged response shrinks", async () => {
    api.listEmployees.mockImplementation(({ page = 1 }: { page?: number }) => {
      if (page === 2) {
        return Promise.resolve({
          data: [],
          meta: { total: 1, page: 2, page_size: 20, pages: 1 },
        });
      }
      return Promise.resolve({
        data: [employee],
        meta: { total: 21, page: 1, page_size: 20, pages: 2 },
      });
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("林晓");

    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listEmployees).toHaveBeenCalledWith(
      expect.objectContaining({ page: 2 }),
    ));
    await waitFor(() => {
      const pages = api.listEmployees.mock.calls.map(([filters]) => filters.page);
      expect(pages.at(-1)).toBe(1);
    });
  });
});
