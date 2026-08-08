import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type Capability, type Role } from "../api/client";
import { RolesPage } from "./RolesPage";

const api = vi.hoisted(() => ({
  listRoles: vi.fn(),
  createRole: vi.fn(),
  updateRole: vi.fn(),
  deleteRole: vi.fn(),
  listCapabilities: vi.fn(),
  createCapability: vi.fn(),
  deleteCapability: vi.fn(),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, ...api };
});

const adminRole = {
  id: "role-admin",
  tenant_id: "tenant-1",
  name: "admin",
  title: "管理员",
  description: "租户系统管理员",
  permissions: ["business_object.write:*", "users.manage"],
  is_system: true,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as Role;

const reviewerRole = {
  id: "role-reviewer",
  tenant_id: "tenant-1",
  name: "contract_reviewer",
  title: "合同复核员",
  description: "复核合同对象",
  permissions: ["business_object.write:contract", "jc.warranty.approve"],
  is_system: false,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as Role;

const legacyGlobalRole = {
  ...reviewerRole,
  id: "role-legacy-global",
  name: "legacy_global",
  title: "旧全局角色",
  permissions: ["business_object.write"],
} as Role;

const systemCapabilities = [
  {
    id: "cap-users",
    name: "users.manage",
    kind: "system",
    title: "用户与角色管理",
    description: "邀请用户并维护角色",
    scopable: false,
    created_at: "2026-07-01T00:00:00Z",
  },
  {
    id: "cap-employees",
    name: "employees.manage",
    kind: "system",
    title: "员工管理",
    description: "维护员工档案",
    scopable: false,
    created_at: "2026-07-01T00:00:00Z",
  },
  {
    id: "cap-objects",
    name: "business_object.write",
    kind: "system",
    title: "业务对象写入",
    description: "按对象类型创建和编辑业务对象",
    scopable: true,
    created_at: "2026-07-01T00:00:00Z",
  },
] as Capability[];

const customCapability = {
  id: "cap-warranty",
  name: "jc.warranty.approve",
  kind: "custom",
  title: "质保审批资格",
  description: "用于质保审批 Skill",
  scopable: false,
  created_at: "2026-07-01T00:00:00Z",
} as Capability;

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RolesPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listRoles.mockResolvedValue([adminRole, reviewerRole, legacyGlobalRole]);
  api.listCapabilities.mockResolvedValue({
    capabilities: [...systemCapabilities, customCapability],
    object_types: ["contract", "expense"],
  });
  api.createRole.mockResolvedValue(reviewerRole);
  api.updateRole.mockImplementation((_id: string, input: object) => Promise.resolve({
    ...reviewerRole,
    ...input,
  }));
  api.deleteRole.mockResolvedValue(undefined);
  api.createCapability.mockResolvedValue(customCapability);
  api.deleteCapability.mockResolvedValue(undefined);
});

afterEach(cleanup);

describe("roles and capabilities workspace", () => {
  it("lists and selects system and custom roles with permission counts", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("管理员")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /admin/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "删除角色" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /contract_reviewer/ }));
    expect(await screen.findByText("复核合同对象")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "删除角色" })).toBeInTheDocument();
    expect(screen.getByText("business_object.write:contract")).toBeInTheDocument();
  });

  it("validates and creates a role with simple, scoped, and custom grants", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("管理员");

    await user.click(screen.getByRole("button", { name: /新建角色/ }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(/角色名称/), "Bad-Name");
    await user.click(within(dialog).getByRole("button", { name: "创建角色" }));
    expect(await within(dialog).findByText(/只能包含小写字母/)).toBeInTheDocument();
    expect(api.createRole).not.toHaveBeenCalled();

    const name = within(dialog).getByLabelText(/角色名称/);
    await user.clear(name);
    await user.type(name, "contract_operator");
    await user.type(within(dialog).getByLabelText("显示标题"), "合同操作员");
    await user.type(within(dialog).getByLabelText("角色说明"), "只处理合同对象");
    await user.click(within(dialog).getByRole("checkbox", { name: /employees.manage/ }));
    await user.click(within(dialog).getByRole("checkbox", { name: "contract" }));
    await user.click(within(dialog).getByRole("checkbox", { name: /jc.warranty.approve/ }));
    await user.click(within(dialog).getByRole("button", { name: "创建角色" }));

    await waitFor(() => expect(api.createRole).toHaveBeenCalledWith({
      name: "contract_operator",
      title: "合同操作员",
      description: "只处理合同对象",
      permissions: [
        "business_object.write:contract",
        "employees.manage",
        "jc.warranty.approve",
      ],
    }));
  });

  it("locks users.manage on admin and canonicalizes scoped wildcard grants", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("管理员");

    await user.click(screen.getByRole("button", { name: "编辑角色" }));
    let dialog = screen.getByRole("dialog");
    const usersManage = within(dialog).getByRole("checkbox", { name: /users.manage/ });
    expect(usersManage).toBeChecked();
    expect(usersManage).toBeDisabled();
    expect(within(dialog).getByRole("checkbox", { name: /全部对象类型/ })).toBeChecked();
    await user.click(within(dialog).getByRole("button", { name: "保存角色" }));
    await waitFor(() => expect(api.updateRole).toHaveBeenCalledWith(
      "role-admin",
      expect.objectContaining({ permissions: expect.arrayContaining(["users.manage"]) }),
    ));

    await user.click(screen.getByRole("button", { name: /contract_reviewer/ }));
    await user.click(screen.getByRole("button", { name: "编辑角色" }));
    dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("checkbox", { name: /全部对象类型/ }));
    expect(within(dialog).getByRole("checkbox", { name: "contract" })).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: "保存角色" }));
    await waitFor(() => expect(api.updateRole).toHaveBeenLastCalledWith(
      "role-reviewer",
      expect.objectContaining({
        permissions: ["business_object.write:*", "jc.warranty.approve"],
      }),
    ));
  });

  it("treats a bare scopable verb as global and removes it before a single-scope grant", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("管理员");
    await user.click(screen.getByRole("button", { name: /legacy_global/ }));
    await user.click(screen.getByRole("button", { name: "编辑角色" }));
    const dialog = screen.getByRole("dialog");

    const allScopes = within(dialog).getByRole("checkbox", { name: /全部对象类型/ });
    const contract = within(dialog).getByRole("checkbox", { name: "contract" });
    expect(allScopes).toBeChecked();
    expect(contract).toBeChecked();
    expect(contract).toBeDisabled();
    expect(within(dialog).queryByText("其他既有授权")).not.toBeInTheDocument();

    await user.click(allScopes);
    expect(contract).not.toBeDisabled();
    await user.click(contract);
    await user.click(within(dialog).getByRole("button", { name: "保存角色" }));

    await waitFor(() => expect(api.updateRole).toHaveBeenCalledWith(
      "role-legacy-global",
      expect.objectContaining({ permissions: ["business_object.write:contract"] }),
    ));
  });

  it("confirms custom role deletion and displays assignment conflicts", async () => {
    api.deleteRole.mockRejectedValueOnce(
      new ApiError(409, "role is assigned to users", "role is assigned to users"),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("管理员");
    await user.click(screen.getByRole("button", { name: /contract_reviewer/ }));
    await user.click(screen.getByRole("button", { name: "删除角色" }));

    const confirm = screen.getByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: "确认删除" }));
    expect(await within(confirm).findByText("role is assigned to users")).toBeInTheDocument();
    expect(api.deleteRole).toHaveBeenCalledWith("role-reviewer");
  });

  it("creates custom capabilities and surfaces backend reference conflicts on delete", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("质保审批资格");

    await user.click(screen.getByRole("button", { name: /新建能力/ }));
    let dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(/能力名称/), "Invalid-Name");
    await user.click(within(dialog).getByRole("button", { name: "创建能力" }));
    expect(await within(dialog).findByText(/只能包含小写字母/)).toBeInTheDocument();
    expect(api.createCapability).not.toHaveBeenCalled();

    const name = within(dialog).getByLabelText(/能力名称/);
    await user.clear(name);
    await user.type(name, "jc.invoice.review");
    await user.type(within(dialog).getByLabelText("显示标题"), "票据复核");
    await user.type(within(dialog).getByLabelText("能力说明"), "票据复核流程资格");
    await user.click(within(dialog).getByRole("button", { name: "创建能力" }));
    await waitFor(() => expect(api.createCapability).toHaveBeenCalledWith({
      name: "jc.invoice.review",
      title: "票据复核",
      description: "票据复核流程资格",
    }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    api.deleteCapability.mockRejectedValueOnce(
      new ApiError(409, "capability is required by a skill", "capability is required by a skill"),
    );
    await user.click(screen.getByRole("button", { name: "删除能力" }));
    dialog = screen.getByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "确认删除" }));
    expect(await within(dialog).findByText("capability is required by a skill")).toBeInTheDocument();
    expect(api.deleteCapability).toHaveBeenCalledWith("jc.warranty.approve");
  });

  it("renders loading, error, and empty states", async () => {
    api.listRoles.mockReturnValueOnce(new Promise(() => {}));
    const loading = renderPage();
    expect(screen.getByText("正在加载数据…")).toBeInTheDocument();
    loading.unmount();

    api.listRoles.mockRejectedValueOnce(new Error("角色目录暂时不可用"));
    renderPage();
    expect(await screen.findByText("数据加载失败")).toBeInTheDocument();
    expect(screen.getByText("角色目录暂时不可用")).toBeInTheDocument();
    cleanup();

    api.listRoles.mockResolvedValue([]);
    api.listCapabilities.mockResolvedValue({ capabilities: systemCapabilities, object_types: [] });
    renderPage();
    expect(await screen.findByText("还没有角色")).toBeInTheDocument();
    expect(screen.getByText("还没有自定义能力")).toBeInTheDocument();
  });
});
