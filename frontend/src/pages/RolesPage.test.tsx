import { zhCN } from "../locales/zh-CN/tests";
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
  title: zhCN.pagesRolesPage.title,
  description: zhCN.pagesRolesPage.description,
  permissions: ["business_object.write:*", "users.manage"],
  is_system: true,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as Role;

const reviewerRole = {
  id: "role-reviewer",
  tenant_id: "tenant-1",
  name: "contract_reviewer",
  title: zhCN.pagesRolesPage.title2,
  description: zhCN.pagesRolesPage.description2,
  permissions: ["business_object.write:contract", "jc.warranty.approve"],
  is_system: false,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: null,
} as Role;

const legacyGlobalRole = {
  ...reviewerRole,
  id: "role-legacy-global",
  name: "legacy_global",
  title: zhCN.pagesRolesPage.title3,
  permissions: ["business_object.write"],
} as Role;

const systemCapabilities = [
  {
    id: "cap-users",
    name: "users.manage",
    kind: "system",
    title: zhCN.pagesRolesPage.title4,
    description: zhCN.pagesRolesPage.description3,
    scopable: false,
    created_at: "2026-07-01T00:00:00Z",
  },
  {
    id: "cap-employees",
    name: "employees.manage",
    kind: "system",
    title: zhCN.pagesRolesPage.title5,
    description: zhCN.pagesRolesPage.description4,
    scopable: false,
    created_at: "2026-07-01T00:00:00Z",
  },
  {
    id: "cap-objects",
    name: "business_object.write",
    kind: "system",
    title: zhCN.pagesRolesPage.title6,
    description: zhCN.pagesRolesPage.description5,
    scopable: true,
    created_at: "2026-07-01T00:00:00Z",
  },
] as Capability[];

const customCapability = {
  id: "cap-warranty",
  name: "jc.warranty.approve",
  kind: "custom",
  title: zhCN.pagesRolesPage.title7,
  description: zhCN.pagesRolesPage.description6,
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

    expect(await screen.findByText(zhCN.pagesRolesPage.title)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /admin/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: zhCN.pagesRolesPage.name })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /contract_reviewer/ }));
    expect(await screen.findByText(zhCN.pagesRolesPage.description2)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: zhCN.pagesRolesPage.name })).toBeInTheDocument();
    expect(screen.getByText("business_object.write:contract")).toBeInTheDocument();
  });

  it("validates and creates a role with simple, scoped, and custom grants", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(zhCN.pagesRolesPage.title);

    await user.click(screen.getByRole("button", { name: zhCN.pagesRolesPage.name2() }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(zhCN.pagesRolesPage.pattern()), "Bad-Name");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesRolesPage.name3 }));
    expect(await within(dialog).findByText(zhCN.pagesRolesPage.pattern2())).toBeInTheDocument();
    expect(api.createRole).not.toHaveBeenCalled();

    const name = within(dialog).getByLabelText(zhCN.pagesRolesPage.pattern());
    await user.clear(name);
    await user.type(name, "contract_operator");
    await user.type(within(dialog).getByLabelText(zhCN.pagesRolesPage.displayTitle), zhCN.pagesRolesPage.message2);
    await user.type(within(dialog).getByLabelText(zhCN.pagesRolesPage.roleDescription), zhCN.pagesRolesPage.message4);
    await user.click(within(dialog).getByRole("checkbox", { name: /employees.manage/ }));
    await user.click(within(dialog).getByRole("checkbox", { name: "contract" }));
    await user.click(within(dialog).getByRole("checkbox", { name: /jc.warranty.approve/ }));
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesRolesPage.name3 }));

    await waitFor(() => expect(api.createRole).toHaveBeenCalledWith({
      name: "contract_operator",
      title: zhCN.pagesRolesPage.message2,
      description: zhCN.pagesRolesPage.message4,
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
    await screen.findByText(zhCN.pagesRolesPage.title);

    await user.click(screen.getByRole("button", { name: zhCN.pagesRolesPage.name4 }));
    let dialog = screen.getByRole("dialog");
    const usersManage = within(dialog).getByRole("checkbox", { name: /users.manage/ });
    expect(usersManage).toBeChecked();
    expect(usersManage).toBeDisabled();
    expect(within(dialog).getByRole("checkbox", { name: zhCN.pagesRolesPage.name5() })).toBeChecked();
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesRolesPage.name6 }));
    await waitFor(() => expect(api.updateRole).toHaveBeenCalledWith(
      "role-admin",
      expect.objectContaining({ permissions: expect.arrayContaining(["users.manage"]) }),
    ));

    await user.click(screen.getByRole("button", { name: /contract_reviewer/ }));
    await user.click(screen.getByRole("button", { name: zhCN.pagesRolesPage.name4 }));
    dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("checkbox", { name: zhCN.pagesRolesPage.name5() }));
    expect(within(dialog).getByRole("checkbox", { name: "contract" })).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesRolesPage.name6 }));
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
    await screen.findByText(zhCN.pagesRolesPage.title);
    await user.click(screen.getByRole("button", { name: /legacy_global/ }));
    await user.click(screen.getByRole("button", { name: zhCN.pagesRolesPage.name4 }));
    const dialog = screen.getByRole("dialog");

    const allScopes = within(dialog).getByRole("checkbox", { name: zhCN.pagesRolesPage.name5() });
    const contract = within(dialog).getByRole("checkbox", { name: "contract" });
    expect(allScopes).toBeChecked();
    expect(contract).toBeChecked();
    expect(contract).toBeDisabled();
    expect(within(dialog).queryByText(zhCN.pagesRolesPage.otherExistingGrants)).not.toBeInTheDocument();

    await user.click(allScopes);
    expect(contract).not.toBeDisabled();
    await user.click(contract);
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesRolesPage.name6 }));

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
    await screen.findByText(zhCN.pagesRolesPage.title);
    await user.click(screen.getByRole("button", { name: /contract_reviewer/ }));
    await user.click(screen.getByRole("button", { name: zhCN.pagesRolesPage.name }));

    const confirm = screen.getByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: zhCN.pagesRolesPage.name7 }));
    expect(await within(confirm).findByText("role is assigned to users")).toBeInTheDocument();
    expect(api.deleteRole).toHaveBeenCalledWith("role-reviewer");
  });

  it("creates custom capabilities and surfaces backend reference conflicts on delete", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(zhCN.pagesRolesPage.title7);

    await user.click(screen.getByRole("button", { name: zhCN.pagesRolesPage.name8() }));
    let dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(zhCN.pagesRolesPage.pattern3()), "Invalid-Name");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesRolesPage.name9 }));
    expect(await within(dialog).findByText(zhCN.pagesRolesPage.pattern2())).toBeInTheDocument();
    expect(api.createCapability).not.toHaveBeenCalled();

    const name = within(dialog).getByLabelText(zhCN.pagesRolesPage.pattern3());
    await user.clear(name);
    await user.type(name, "jc.invoice.review");
    await user.type(within(dialog).getByLabelText(zhCN.pagesRolesPage.displayTitle), zhCN.pagesRolesPage.message6);
    await user.type(within(dialog).getByLabelText(zhCN.pagesRolesPage.capabilityDescription), zhCN.pagesRolesPage.message8);
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesRolesPage.name9 }));
    await waitFor(() => expect(api.createCapability).toHaveBeenCalledWith({
      name: "jc.invoice.review",
      title: zhCN.pagesRolesPage.message6,
      description: zhCN.pagesRolesPage.message8,
    }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    api.deleteCapability.mockRejectedValueOnce(
      new ApiError(409, "capability is required by a skill", "capability is required by a skill"),
    );
    await user.click(screen.getByRole("button", { name: zhCN.pagesRolesPage.name10 }));
    dialog = screen.getByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesRolesPage.name7 }));
    expect(await within(dialog).findByText("capability is required by a skill")).toBeInTheDocument();
    expect(api.deleteCapability).toHaveBeenCalledWith("jc.warranty.approve");
  });

  it("renders loading, error, and empty states", async () => {
    api.listRoles.mockReturnValueOnce(new Promise(() => {}));
    const loading = renderPage();
    expect(screen.getByText(zhCN.pagesRolesPage.loadingData)).toBeInTheDocument();
    loading.unmount();

    api.listRoles.mockRejectedValueOnce(new Error(zhCN.pagesRolesPage.message10));
    renderPage();
    expect(await screen.findByText(zhCN.pagesRolesPage.dataCouldNotBeLoaded)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesRolesPage.message10)).toBeInTheDocument();
    cleanup();

    api.listRoles.mockResolvedValue([]);
    api.listCapabilities.mockResolvedValue({ capabilities: systemCapabilities, object_types: [] });
    renderPage();
    expect(await screen.findByText(zhCN.pagesRolesPage.noRolesYet)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesRolesPage.noCustomCapabilitiesYet)).toBeInTheDocument();
  });
});
