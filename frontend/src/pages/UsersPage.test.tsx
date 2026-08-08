import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ConsoleContext } from "../App";
import { ApiError, type Employee, type InvitationUser, type Role, type User } from "../api/client";
import { UsersPage } from "./UsersPage";

const api = vi.hoisted(() => ({
  listUsers: vi.fn(),
  inviteUser: vi.fn(),
  updateUser: vi.fn(),
  resendInvitation: vi.fn(),
  sendPasswordResetEmail: vi.fn(),
  generateUserSkillBundle: vi.fn(),
  listRoles: vi.fn(),
  listEmployees: vi.fn(),
  getEmployee: vi.fn(),
}));

const createObjectURL = vi.fn(() => "blob:skill-bundle");
const revokeObjectURL = vi.fn();
Object.defineProperties(URL, {
  createObjectURL: { configurable: true, value: createObjectURL },
  revokeObjectURL: { configurable: true, value: revokeObjectURL },
});

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, ...api };
});

const selfUser = {
  id: "user-self",
  tenant_id: "tenant-1",
  email: "admin@acme.example",
  name: "当前管理员",
  role: "admin",
  employee_id: "employee-1",
  status: "active",
  invitation_pending: false,
  email_verified_at: "2026-01-01T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
} as User;

const invitedUser = {
  id: "user-invited",
  tenant_id: "tenant-1",
  email: "guest@example.com",
  name: "待加入用户",
  role: "member",
  employee_id: null,
  status: "invited",
  invitation_pending: true,
  email_verified_at: null,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as User;

const roles = [
  { id: "role-admin", tenant_id: "tenant-1", name: "admin", title: "管理员", description: null, permissions: ["users.manage"], is_system: true, created_at: "2026-01-01T00:00:00Z", updated_at: null },
  { id: "role-member", tenant_id: "tenant-1", name: "member", title: "成员", description: null, permissions: [], is_system: true, created_at: "2026-01-01T00:00:00Z", updated_at: null },
  { id: "role-auditor", tenant_id: "tenant-1", name: "auditor", title: "审计员", description: null, permissions: [], is_system: false, created_at: "2026-01-01T00:00:00Z", updated_at: null },
] as Role[];

const employees = [
  { id: "employee-1", employee_code: "E-001", name: "当前管理员", email: "admin@acme.example", timezone: "Asia/Shanghai", status: "active", metadata: {}, created_at: "2026-01-01T00:00:00Z", updated_at: null },
  { id: "employee-2", employee_code: "E-002", name: "受邀员工", email: "new@example.com", timezone: "Asia/Shanghai", status: "active", metadata: {}, created_at: "2026-01-01T00:00:00Z", updated_at: null },
] as Employee[];

const bootstrap = {
  user: { id: selfUser.id, email: selfUser.email, name: selfUser.name },
  tenant: { id: "tenant-1", name: "Acme", email_domain: "acme.example" },
  role: "admin",
  permissions: ["users.manage", "keys.manage"],
  employee_id: "employee-1",
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const context = { bootstrap } as ConsoleContext;
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Routes>
          <Route element={<Outlet context={context} />}>
            <Route index element={<UsersPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listUsers.mockImplementation(({ page = 1 }: { page?: number }) => Promise.resolve({
    data: [selfUser, invitedUser],
    meta: { total: 22, page, page_size: 20, pages: 2 },
  }));
  api.listRoles.mockResolvedValue(roles);
  api.listEmployees.mockImplementation(({ keyword }: { keyword?: string }) => Promise.resolve({
    data: keyword ? [employees[1]] : employees,
    meta: { total: keyword ? 1 : 2, page: 1, page_size: 50, pages: 1 },
  }));
  api.getEmployee.mockResolvedValue(employees[0]);
  api.inviteUser.mockResolvedValue({
    ...invitedUser,
    id: "user-new",
    email: "new@example.com",
    invitation_url: "https://app.example/invite/one-time",
  } as InvitationUser);
  api.updateUser.mockImplementation((_id: string, input: Record<string, unknown>) => Promise.resolve({ ...invitedUser, ...input }));
  api.resendInvitation.mockResolvedValue({
    ...invitedUser,
    invitation_url: "https://app.example/invite/reissued",
  } as InvitationUser);
  api.sendPasswordResetEmail.mockResolvedValue({
    user: selfUser,
    email_sent: true,
  });
  api.generateUserSkillBundle.mockResolvedValue({
    blob: new Blob(["bundle"], { type: "application/zip" }),
    filename: "oryh-skills-admin.zip",
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("tenant users workspace", () => {
  it("loads bounded employee options and sends server-side user and employee searches", async () => {
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText(/admin@acme\.example/)).toBeInTheDocument();
    expect(screen.getByText("待加入用户")).toBeInTheDocument();
    await waitFor(() => expect(api.listEmployees).toHaveBeenCalledWith({
      page: 1,
      size: 50,
      keyword: undefined,
    }));
    expect(api.listEmployees.mock.calls.some(([filters]) => filters.page > 1)).toBe(false);

    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listUsers).toHaveBeenCalledWith(expect.objectContaining({ page: 2, size: 20 })));
    await user.type(screen.getByRole("searchbox"), " guest ");
    await user.selectOptions(screen.getByLabelText("用户状态"), "invited");
    await user.selectOptions(screen.getByLabelText("用户角色"), "auditor");
    await user.click(screen.getByRole("button", { name: "筛选" }));
    await waitFor(() => expect(api.listUsers).toHaveBeenCalledWith(expect.objectContaining({
      page: 1,
      keyword: "guest",
      status: "invited",
      role: "auditor",
    })));

    await user.click(screen.getByRole("button", { name: /邀请用户/ }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("查找员工"), " 受邀 ");
    await user.click(within(dialog).getByRole("button", { name: "搜索员工" }));
    await waitFor(() => expect(api.listEmployees).toHaveBeenCalledWith({
      page: 1,
      size: 50,
      keyword: "受邀",
    }));
  });

  it("validates and sends an invitation, then exposes and copies its one-time URL", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("待加入用户");
    await user.click(screen.getByRole("button", { name: /邀请用户/ }));
    let dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "发送邀请" }));
    expect(await within(dialog).findByText("邮箱不能为空。")).toBeInTheDocument();
    expect(api.inviteUser).not.toHaveBeenCalled();

    await user.type(within(dialog).getByLabelText(/邮箱/), "new@example.com");
    await user.type(within(dialog).getByLabelText("姓名"), "新用户");
    await user.selectOptions(within(dialog).getByLabelText(/角色/), "auditor");
    await user.selectOptions(within(dialog).getByLabelText("关联员工"), "employee-2");
    await user.click(within(dialog).getByRole("button", { name: "发送邀请" }));
    await waitFor(() => expect(api.inviteUser).toHaveBeenCalledWith({
      email: "new@example.com",
      name: "新用户",
      role: "auditor",
      employee_id: "employee-2",
    }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const link = await screen.findByLabelText("一次性邀请链接");
    expect(link).toHaveValue("https://app.example/invite/one-time");
    expect(screen.getByText(/仅在本次响应中显示/)).toBeInTheDocument();
    const clipboardWrite = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(screen.getByRole("button", { name: "复制链接" }));
    expect(clipboardWrite).toHaveBeenCalledWith("https://app.example/invite/one-time");
    expect(screen.getByRole("button", { name: "已复制" })).toBeInTheDocument();
  });

  it("protects the current user's role/status while allowing safe profile updates", async () => {
    const user = userEvent.setup();
    renderPage();
    const selfEmail = await screen.findByText(/admin@acme\.example/);
    const selfRow = selfEmail.closest("tr");
    expect(selfRow).not.toBeNull();
    await user.click(within(selfRow!).getByRole("button", { name: "编辑" }));
    let dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("正在编辑当前登录用户")).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/角色/)).toBeDisabled();
    expect(within(dialog).getByLabelText("状态")).toBeDisabled();
    await user.clear(within(dialog).getByLabelText("姓名"));
    await user.type(within(dialog).getByLabelText("姓名"), "管理员新名");
    await user.click(within(dialog).getByRole("button", { name: "保存更改" }));
    await waitFor(() => expect(api.updateUser).toHaveBeenCalledWith("user-self", expect.objectContaining({ name: "管理员新名" })));
    const selfPayload = api.updateUser.mock.calls[0][1];
    expect(selfPayload).not.toHaveProperty("role");
    expect(selfPayload).not.toHaveProperty("status");

    const invitedRow = screen.getByText("待加入用户").closest("tr");
    expect(invitedRow).not.toBeNull();
    await user.click(within(invitedRow!).getByRole("button", { name: "编辑" }));
    dialog = screen.getByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText(/角色/), "auditor");
    expect(within(dialog).queryByRole("option", { name: "已启用" })).not.toBeInTheDocument();
    await user.selectOptions(within(dialog).getByLabelText("状态"), "disabled");
    await user.selectOptions(within(dialog).getByLabelText("关联员工"), "employee-2");
    await user.click(within(dialog).getByRole("button", { name: "保存更改" }));
    await waitFor(() => expect(api.updateUser).toHaveBeenCalledWith("user-invited", expect.objectContaining({
      role: "auditor",
      status: "disabled",
      employee_id: "employee-2",
    })));
    expect(screen.queryByRole("button", { name: /删除|归档/ })).not.toBeInTheDocument();
  });

  it("reissues an invited user's link without inventing a delete action", async () => {
    const user = userEvent.setup();
    renderPage();
    const invitedRow = (await screen.findByText("待加入用户")).closest("tr");
    expect(invitedRow).not.toBeNull();
    await user.click(within(invitedRow!).getByRole("button", { name: "重发邀请" }));
    await waitFor(() => expect(api.resendInvitation).toHaveBeenCalledWith("user-invited"));
    expect(await screen.findByDisplayValue("https://app.example/invite/reissued")).toBeInTheDocument();
    expect(screen.getByText(/邀请已重新发送/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /删除|归档/ })).not.toBeInTheDocument();
  });

  it("confirms and sends a one-time password reset email for an active user", async () => {
    let completeReset!: (value: {
      user: User;
      email_sent: boolean;
    }) => void;
    api.sendPasswordResetEmail.mockImplementationOnce(() => new Promise((resolve) => {
      completeReset = resolve;
    }));
    const user = userEvent.setup();
    renderPage();
    const selfRow = (await screen.findByText(/admin@acme\.example/)).closest("tr");
    const invitedRow = screen.getByText("待加入用户").closest("tr");
    expect(selfRow).not.toBeNull();
    expect(invitedRow).not.toBeNull();
    expect(within(invitedRow!).queryByRole("button", { name: "发送重置邮件" })).not.toBeInTheDocument();

    await user.click(within(selfRow!).getByRole("button", { name: "发送重置邮件" }));
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("这是当前登录账号");
    expect(dialog).toHaveTextContent("当前密码和会话仍有效");
    expect(api.sendPasswordResetEmail).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "发送重置邮件" }));
    expect(api.sendPasswordResetEmail).toHaveBeenCalledWith("user-self");
    expect(within(dialog).getByRole("button", { name: "正在发送…" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "取消" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "＋ 邀请用户" })).toBeDisabled();

    completeReset({
      user: selfUser,
      email_sent: true,
    });
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(await screen.findByText(/重置密码邮件已发送/)).toBeInTheDocument();
    expect(screen.queryByLabelText("一次性重置链接")).not.toBeInTheDocument();
  });

  it("shows password reset only for active users and reports email delivery failure", async () => {
    const disabledUser = {
      ...invitedUser,
      id: "user-disabled",
      email: "disabled@example.com",
      name: "停用用户",
      status: "disabled",
      invitation_pending: false,
      email_verified_at: "2026-01-02T00:00:00Z",
    } as User;
    api.listUsers.mockResolvedValue({
      data: [selfUser, invitedUser, disabledUser],
      meta: { total: 3, page: 1, page_size: 20, pages: 1 },
    });
    api.sendPasswordResetEmail.mockResolvedValueOnce({
      user: selfUser,
      email_sent: false,
    });
    const user = userEvent.setup();
    renderPage();

    const selfRow = (await screen.findByText(/admin@acme\.example/)).closest("tr");
    const invitedRow = screen.getByText("待加入用户").closest("tr");
    const disabledRow = screen.getByText("停用用户").closest("tr");
    expect(within(selfRow!).getByRole("button", { name: "发送重置邮件" })).toBeInTheDocument();
    expect(within(invitedRow!).queryByRole("button", { name: "发送重置邮件" })).not.toBeInTheDocument();
    expect(within(disabledRow!).queryByRole("button", { name: "发送重置邮件" })).not.toBeInTheDocument();

    await user.click(within(selfRow!).getByRole("button", { name: "发送重置邮件" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "发送重置邮件" }));
    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent("重置链接已生成，但邮件未送达");
    expect(notice).toHaveTextContent("当前密码和会话仍然有效");
    expect(screen.queryByLabelText("一次性重置链接")).not.toBeInTheDocument();
  });

  it("distinguishes a rejected reset request from an uncertain delivery result", async () => {
    api.sendPasswordResetEmail.mockRejectedValueOnce(
      new ApiError(409, "only active users with a usable login can reset their password"),
    );
    const user = userEvent.setup();
    renderPage();
    const selfRow = (await screen.findByText(/admin@acme\.example/)).closest("tr");
    const invitedRow = screen.getByText("待加入用户").closest("tr");

    await user.click(within(invitedRow!).getByRole("button", { name: "重发邀请" }));
    expect(await screen.findByLabelText("一次性邀请链接")).toHaveValue(
      "https://app.example/invite/reissued",
    );

    await user.click(within(selfRow!).getByRole("button", { name: "发送重置邮件" }));
    let dialog = screen.getByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "发送重置邮件" }));
    expect(await within(dialog).findByText(/无法发送重置邮件/)).toBeInTheDocument();
    expect(within(dialog).getByText(/only active users/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(screen.getByLabelText("一次性邀请链接")).toHaveValue(
      "https://app.example/invite/reissued",
    );

    api.sendPasswordResetEmail.mockRejectedValueOnce(new Error("connection closed"));
    await user.click(within(selfRow!).getByRole("button", { name: "发送重置邮件" }));
    dialog = screen.getByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "发送重置邮件" }));
    expect(await within(dialog).findByText(/无法确认重置邮件是否送达/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "取消" }));

    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent("重置邮件结果未能确认");
    expect(notice).toHaveTextContent("系统可能已生成并发送链接");
  });

  it("serializes one-time invitation and password-reset email actions", async () => {
    let completeResend!: (value: InvitationUser) => void;
    api.resendInvitation.mockImplementationOnce(() => new Promise((resolve) => {
      completeResend = resolve;
    }));
    const user = userEvent.setup();
    renderPage();
    const selfRow = (await screen.findByText(/admin@acme\.example/)).closest("tr");
    const invitedRow = screen.getByText("待加入用户").closest("tr");

    await user.click(within(invitedRow!).getByRole("button", { name: "重发邀请" }));
    expect(within(invitedRow!).getByRole("button", { name: "发送中…" })).toBeDisabled();
    expect(within(selfRow!).getByRole("button", { name: "发送重置邮件" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "＋ 邀请用户" })).toBeDisabled();

    completeResend({
      ...invitedUser,
      invitation_url: "https://app.example/invite/reissued",
    } as InvitationUser);
    expect(await screen.findByLabelText("一次性邀请链接")).toHaveValue(
      "https://app.example/invite/reissued",
    );
    await waitFor(() => {
      expect(within(selfRow!).getByRole("button", { name: "发送重置邮件" })).not.toBeDisabled();
    });
  });

  it("keeps a pre-opened reset confirmation behind the synchronous credential mutex", async () => {
    let completeResend!: (value: InvitationUser) => void;
    api.resendInvitation.mockImplementationOnce(() => new Promise((resolve) => {
      completeResend = resolve;
    }));
    const user = userEvent.setup();
    renderPage();
    const selfRow = (await screen.findByText(/admin@acme\.example/)).closest("tr");
    const invitedRow = screen.getByText("待加入用户").closest("tr");

    await user.click(within(selfRow!).getByRole("button", { name: "发送重置邮件" }));
    const dialog = screen.getByRole("alertdialog");
    const confirmReset = within(dialog).getByRole("button", { name: "发送重置邮件" });
    const backgroundResend = within(invitedRow!).getByRole("button", { name: "重发邀请" });

    act(() => {
      backgroundResend.click();
      confirmReset.click();
    });
    await waitFor(() => expect(api.resendInvitation).toHaveBeenCalledWith("user-invited"));
    expect(api.sendPasswordResetEmail).not.toHaveBeenCalled();
    expect(confirmReset).toBeDisabled();

    act(() => completeResend({
      ...invitedUser,
      invitation_url: "https://app.example/invite/reissued",
    } as InvitationUser));
    await waitFor(() => expect(confirmReset).not.toBeDisabled());
    await user.click(confirmReset);
    await waitFor(() => expect(api.sendPasswordResetEmail).toHaveBeenCalledWith("user-self"));
  });

  it("keeps a pre-opened invitation drawer behind the synchronous credential mutex", async () => {
    let completeResend!: (value: InvitationUser) => void;
    api.resendInvitation.mockImplementationOnce(() => new Promise((resolve) => {
      completeResend = resolve;
    }));
    const user = userEvent.setup();
    renderPage();
    const invitedRow = (await screen.findByText("待加入用户")).closest("tr");
    await user.click(screen.getByRole("button", { name: /邀请用户/ }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(/邮箱/), "new@example.com");
    const submitInvite = within(dialog).getByRole("button", { name: "发送邀请" });
    const backgroundResend = within(invitedRow!).getByRole("button", { name: "重发邀请" });

    act(() => {
      backgroundResend.click();
      submitInvite.click();
    });
    await waitFor(() => expect(api.resendInvitation).toHaveBeenCalledWith("user-invited"));
    expect(api.inviteUser).not.toHaveBeenCalled();
    expect(submitInvite).toBeDisabled();

    act(() => completeResend({
      ...invitedUser,
      invitation_url: "https://app.example/invite/reissued",
    } as InvitationUser));
    await waitFor(() => expect(submitInvite).not.toBeDisabled());
    await user.click(submitInvite);
    await waitFor(() => expect(api.inviteUser).toHaveBeenCalledWith(expect.objectContaining({
      email: "new@example.com",
    })));
  });

  it("confirms credential rotation before downloading an active user's Skill bundle", async () => {
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const user = userEvent.setup();
    renderPage();
    const selfRow = (await screen.findByText(/admin@acme\.example/)).closest("tr");
    expect(selfRow).not.toBeNull();

    await user.click(within(selfRow!).getByRole("button", { name: "生成 Skill 包" }));
    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText(/旧 Skill 包和旧凭证失效/)).toBeInTheDocument();
    expect(api.generateUserSkillBundle).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "更新凭证并下载" }));
    await waitFor(() => expect(api.generateUserSkillBundle).toHaveBeenCalledWith("user-self"));
    expect(await screen.findByText(/此前的访问凭证已失效/)).toBeInTheDocument();
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(anchorClick).toHaveBeenCalledOnce();
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:skill-bundle"));
  });

  it("hides Skill bundle issuance without the backend's explicit keys.manage grant", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const context = {
      bootstrap: { ...bootstrap, permissions: ["users.manage"] },
    } as ConsoleContext;
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Routes>
            <Route element={<Outlet context={context} />}>
              <Route index element={<UsersPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const selfRow = (await screen.findByText(/admin@acme\.example/)).closest("tr");
    expect(selfRow).not.toBeNull();
    expect(within(selfRow!).queryByRole("button", { name: "生成 Skill 包" })).not.toBeInTheDocument();
  });

  it("warns that rotation may have happened when bundle delivery is uncertain", async () => {
    api.generateUserSkillBundle.mockRejectedValueOnce(new Error("connection closed"));
    const user = userEvent.setup();
    renderPage();
    const selfRow = (await screen.findByText(/admin@acme\.example/)).closest("tr");
    await user.click(within(selfRow!).getByRole("button", { name: "生成 Skill 包" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "更新凭证并下载" }));

    const dialog = screen.getByRole("alertdialog");
    expect(await within(dialog).findByText(/系统可能已经更新访问凭证/)).toBeInTheDocument();
    expect(dialog).toHaveTextContent("connection closed");
    await user.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("系统可能已经更新访问凭证");
  });

  it("recovers a disabled unverified account through invitation instead of direct activation", async () => {
    const disabledPending = { ...invitedUser, status: "disabled" } as User;
    api.listUsers.mockResolvedValue({
      data: [disabledPending],
      meta: { total: 1, page: 1, page_size: 20, pages: 1 },
    });
    const user = userEvent.setup();
    renderPage();

    const row = (await screen.findByText("待加入用户")).closest("tr");
    expect(row).not.toBeNull();
    expect(within(row!).getByRole("button", { name: "恢复邀请" })).toBeInTheDocument();
    await user.click(within(row!).getByRole("button", { name: "编辑" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("状态")).toBeDisabled();
    expect(within(dialog).queryByRole("option", { name: "已启用" })).not.toBeInTheDocument();
    expect(within(dialog).getByText(/恢复邀请后再激活/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "取消" }));

    await user.click(within(row!).getByRole("button", { name: "恢复邀请" }));
    await waitFor(() => expect(api.resendInvitation).toHaveBeenCalledWith("user-invited"));
  });

  it("shows loading, empty, and recoverable error states", async () => {
    api.listUsers.mockReturnValueOnce(new Promise(() => {}));
    const pending = renderPage();
    expect(screen.getByText("正在加载数据…")).toBeInTheDocument();
    pending.unmount();

    api.listUsers.mockResolvedValueOnce({ data: [], meta: { total: 0, page: 1, page_size: 20, pages: 1 } });
    const empty = renderPage();
    expect(await screen.findByText("还没有用户")).toBeInTheDocument();
    empty.unmount();

    api.listUsers.mockRejectedValueOnce(new Error("用户目录暂时不可用"));
    renderPage();
    expect(await screen.findByText("数据加载失败")).toBeInTheDocument();
    expect(screen.getByText("用户目录暂时不可用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  });

  it("returns to the last valid page when the user directory shrinks", async () => {
    api.listUsers.mockImplementation(({ page = 1 }: { page?: number }) => page === 2
      ? Promise.resolve({ data: [], meta: { total: 1, page: 2, page_size: 20, pages: 1 } })
      : Promise.resolve({ data: [selfUser], meta: { total: 21, page: 1, page_size: 20, pages: 2 } }));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/admin@acme\.example/);
    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => {
      const pages = api.listUsers.mock.calls.map(([filters]) => filters.page);
      expect(pages.at(-1)).toBe(1);
    });
  });
});
