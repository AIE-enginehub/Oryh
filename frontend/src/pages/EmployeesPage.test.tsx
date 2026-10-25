import { zhCN } from "../locales/zh-CN/tests";
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
  name: zhCN.pagesEmployeesPage.name,
  email: "lin@example.com",
  timezone: "Asia/Shanghai",
  status: "active",
  metadata: {},
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as Employee;

const roles = [
  { id: "role-admin", tenant_id: "tenant-1", name: "admin", title: zhCN.pagesEmployeesPage.title, description: null, permissions: ["users.manage"], is_system: true, created_at: "2026-01-01T00:00:00Z", updated_at: null },
  { id: "role-member", tenant_id: "tenant-1", name: "member", title: zhCN.pagesEmployeesPage.title2, description: null, permissions: [], is_system: true, created_at: "2026-01-01T00:00:00Z", updated_at: null },
  { id: "role-auditor", tenant_id: "tenant-1", name: "auditor", title: zhCN.pagesEmployeesPage.title3, description: null, permissions: [], is_system: false, created_at: "2026-01-01T00:00:00Z", updated_at: null },
] as Role[];

const bootstrap = {
  user: { id: "user-admin", email: "admin@example.com", name: zhCN.pagesEmployeesPage.name2 },
  tenant: { id: "tenant-1", name: zhCN.pagesEmployeesPage.name3, email_domain: "example.com" },
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
    name: zhCN.pagesEmployeesPage.name4,
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

    expect(await screen.findByText(zhCN.pagesEmployeesPage.name)).toBeInTheDocument();
    expect(screen.getByText("EMP-001")).toBeInTheDocument();
    expect(screen.getByText("Asia/Shanghai")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name5 })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name6 }));
    await waitFor(() => expect(api.listEmployees).toHaveBeenCalledWith(
      expect.objectContaining({ page: 2, size: 20 }),
    ));

    await user.type(screen.getByRole("searchbox"), zhCN.pagesEmployeesPage.message);
    await user.selectOptions(screen.getByLabelText(zhCN.pagesEmployeesPage.state), "inactive");
    await user.click(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name7 }));
    await waitFor(() => expect(api.listEmployees).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, keyword: zhCN.pagesEmployeesPage.keyword, status: "inactive" }),
    ));
  });

  it("validates fields, creates an employee, and edits all supported fields", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(zhCN.pagesEmployeesPage.name);

    await user.click(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name8() }));
    let dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesEmployeesPage.name9 }));
    expect(await within(dialog).findByText(zhCN.pagesEmployeesPage.nameIsRequired)).toBeInTheDocument();
    expect(api.createEmployee).not.toHaveBeenCalled();

    await user.type(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.message4), zhCN.pagesEmployeesPage.name4);
    await user.type(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.employeeID), "EMP-002");
    await user.type(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.email), "not-an-email");
    await user.type(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.workingTimeZone), "Shanghai");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesEmployeesPage.name9 }));
    expect(await within(dialog).findByText(zhCN.pagesEmployeesPage.enterAValidEmailAddress)).toBeInTheDocument();
    expect(within(dialog).getByText(zhCN.pagesEmployeesPage.pattern())).toBeInTheDocument();
    expect(api.createEmployee).not.toHaveBeenCalled();

    const email = within(dialog).getByLabelText(zhCN.pagesEmployeesPage.email);
    const timezone = within(dialog).getByLabelText(zhCN.pagesEmployeesPage.workingTimeZone);
    await user.clear(email);
    await user.type(email, "zhou@example.com");
    await user.clear(timezone);
    await user.type(timezone, "Asia/Shanghai");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesEmployeesPage.name9 }));

    await waitFor(() => expect(api.createEmployee).toHaveBeenCalledWith({
      name: zhCN.pagesEmployeesPage.name4,
      employee_code: "EMP-002",
      email: "zhou@example.com",
      timezone: "Asia/Shanghai",
      status: "active",
    }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name10 }));
    dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.message4)).toHaveValue(zhCN.pagesEmployeesPage.name);
    expect(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.email)).toHaveValue("lin@example.com");
    await user.selectOptions(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.state), "inactive");
    await user.clear(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.workingTimeZone));
    await user.type(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.workingTimeZone), "UTC");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesEmployeesPage.name11 }));

    await waitFor(() => expect(api.updateEmployee).toHaveBeenCalledWith(
      "employee-1",
      expect.objectContaining({
        name: zhCN.pagesEmployeesPage.name,
        employee_code: "EMP-001",
        email: "lin@example.com",
        timezone: "UTC",
        status: "inactive",
      }),
    ));
    expect(screen.queryByRole("button", { name: zhCN.pagesEmployeesPage.name12() })).not.toBeInTheDocument();
  });

  it("can create an employee and an invited, linked user in one flow", async () => {
    const createdEmployee = {
      ...employee,
      id: "employee-new",
      name: zhCN.pagesEmployeesPage.name4,
      employee_code: "EMP-002",
      email: "zhou@example.com",
    } as Employee;
    api.createEmployee.mockResolvedValueOnce(createdEmployee);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(zhCN.pagesEmployeesPage.name);

    await user.click(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name8() }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.message4), zhCN.pagesEmployeesPage.name4);
    await user.type(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.employeeID), "EMP-002");
    await user.click(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.createALoginUserAtTheSameTime));
    await waitFor(() => expect(api.listRoles).toHaveBeenCalledOnce());
    expect(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.state)).toBeDisabled();
    expect(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.message10)).toBeRequired();
    await waitFor(() => expect(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.userRole)).not.toBeDisabled());
    await user.selectOptions(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.userRole), "auditor");

    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesEmployeesPage.name13 }));
    expect(await within(dialog).findByText(zhCN.pagesEmployeesPage.emailIsRequiredWhenCreatingALoginUserAt)).toBeInTheDocument();
    expect(api.createEmployee).not.toHaveBeenCalled();

    const email = within(dialog).getByLabelText(zhCN.pagesEmployeesPage.message10);
    await user.type(email, "zhou@.example.com");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesEmployeesPage.name13 }));
    expect(await within(dialog).findByText(zhCN.pagesEmployeesPage.enterAValidEmailAddress)).toBeInTheDocument();
    expect(api.createEmployee).not.toHaveBeenCalled();

    await user.clear(email);
    await user.type(email, "zhou@example.com");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesEmployeesPage.name13 }));

    await waitFor(() => expect(api.createEmployee).toHaveBeenCalledWith({
      name: zhCN.pagesEmployeesPage.name4,
      employee_code: "EMP-002",
      email: "zhou@example.com",
      timezone: null,
      status: "active",
    }));
    await waitFor(() => expect(api.inviteUser).toHaveBeenCalledWith({
      email: "zhou@example.com",
      name: zhCN.pagesEmployeesPage.name4,
      role: "auditor",
      employee_id: "employee-new",
    }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(await screen.findByText(zhCN.pagesEmployeesPage.pattern2())).toBeInTheDocument();
    expect(screen.getByLabelText(zhCN.pagesEmployeesPage.oneTimeInvitationLink)).toHaveValue(
      "https://console.example/invitations/accept?token=one-time",
    );
    const clipboardWrite = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name14 }));
    expect(clipboardWrite).toHaveBeenCalledWith(
      "https://console.example/invitations/accept?token=one-time",
    );
  });

  it("reports the partial result when employee creation succeeds but invitation fails", async () => {
    api.createEmployee.mockResolvedValueOnce({
      ...employee,
      id: "employee-partial",
      name: zhCN.pagesEmployeesPage.name15,
      email: "gu@example.com",
    });
    api.inviteUser.mockRejectedValueOnce(new ApiError(409, zhCN.pagesEmployeesPage.message14));
    const user = userEvent.setup();
    const { queryClient } = renderPage();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    await screen.findByText(zhCN.pagesEmployeesPage.name);

    await user.click(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name8() }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.message4), zhCN.pagesEmployeesPage.name15);
    await user.type(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.email), "gu@example.com");
    await user.click(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.createALoginUserAtTheSameTime));
    await screen.findByLabelText(zhCN.pagesEmployeesPage.userRole);
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesEmployeesPage.name13 }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent(zhCN.pagesEmployeesPage.message15);
    expect(notice).toHaveTextContent(zhCN.pagesEmployeesPage.message14);
    expect(within(notice).getByRole("link", { name: zhCN.pagesEmployeesPage.name16 })).toHaveAttribute("href", "/users");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["users"] });
  });

  it("treats a transport error as an uncertain invitation outcome", async () => {
    api.createEmployee.mockResolvedValueOnce({
      ...employee,
      id: "employee-uncertain",
      name: zhCN.pagesEmployeesPage.name17,
      email: "xu@example.com",
    });
    api.inviteUser.mockRejectedValueOnce(new Error(zhCN.pagesEmployeesPage.message16));
    const user = userEvent.setup();
    const { queryClient } = renderPage();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    await screen.findByText(zhCN.pagesEmployeesPage.name);

    await user.click(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name8() }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.message4), zhCN.pagesEmployeesPage.name17);
    await user.type(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.email), "xu@example.com");
    await user.click(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.createALoginUserAtTheSameTime));
    await screen.findByLabelText(zhCN.pagesEmployeesPage.userRole);
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesEmployeesPage.name13 }));

    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent(zhCN.pagesEmployeesPage.message17);
    expect(notice).toHaveTextContent(zhCN.pagesEmployeesPage.message18);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["users"] });
  });

  it("does not expose combined user creation without users.manage", async () => {
    const user = userEvent.setup();
    renderPage(["employees.manage"]);
    await screen.findByText(zhCN.pagesEmployeesPage.name);
    await user.click(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name8() }));
    expect(within(screen.getByRole("dialog")).queryByLabelText(zhCN.pagesEmployeesPage.createALoginUserAtTheSameTime)).not.toBeInTheDocument();
  });

  it("fails closed when the tenant has no role available for the invited user", async () => {
    api.listRoles.mockResolvedValueOnce([]);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(zhCN.pagesEmployeesPage.name);

    await user.click(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name8() }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.createALoginUserAtTheSameTime));

    expect(await within(dialog).findByText(zhCN.pagesEmployeesPage.pattern3())).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: zhCN.pagesEmployeesPage.name13 })).toBeDisabled();
    expect(api.createEmployee).not.toHaveBeenCalled();
  });

  it("can recover when the role directory initially fails to load", async () => {
    api.listRoles
      .mockRejectedValueOnce(new Error(zhCN.pagesEmployeesPage.message19))
      .mockResolvedValueOnce(roles);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(zhCN.pagesEmployeesPage.name);

    await user.click(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name8() }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.createALoginUserAtTheSameTime));
    expect(await within(dialog).findByText(zhCN.pagesEmployeesPage.pattern4())).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesEmployeesPage.name18 }));
    await waitFor(() => expect(within(dialog).getByLabelText(zhCN.pagesEmployeesPage.userRole)).not.toBeDisabled());
    expect(api.listRoles).toHaveBeenCalledTimes(2);
  });

  it("shows loading and empty states", async () => {
    api.listEmployees.mockReturnValueOnce(new Promise(() => {}));
    const first = renderPage();
    expect(screen.getByText(zhCN.pagesEmployeesPage.loadingData)).toBeInTheDocument();
    first.unmount();

    api.listEmployees.mockResolvedValue({
      data: [],
      meta: { total: 0, page: 1, page_size: 20, pages: 1 },
    });
    renderPage();
    expect(await screen.findByText(zhCN.pagesEmployeesPage.noEmployeesYet)).toBeInTheDocument();
  });

  it("shows a recoverable list error", async () => {
    api.listEmployees.mockRejectedValue(new Error(zhCN.pagesEmployeesPage.message22));
    renderPage();

    expect(await screen.findByText(zhCN.pagesEmployeesPage.dataCouldNotBeLoaded)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesEmployeesPage.message22)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name19 })).toBeInTheDocument();
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
    await screen.findByText(zhCN.pagesEmployeesPage.name);

    await user.click(screen.getByRole("button", { name: zhCN.pagesEmployeesPage.name6 }));
    await waitFor(() => expect(api.listEmployees).toHaveBeenCalledWith(
      expect.objectContaining({ page: 2 }),
    ));
    await waitFor(() => {
      const pages = api.listEmployees.mock.calls.map(([filters]) => filters.page);
      expect(pages.at(-1)).toBe(1);
    });
  });
});
