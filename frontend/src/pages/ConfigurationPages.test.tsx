import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiKeysPage } from "./ApiKeysPage";
import { ObjectTypesPage } from "./ObjectTypesPage";
import {
  SkillsPage,
  parseSkillRequiredCapability,
  resolveSkillRequiredCapability,
} from "./SkillsPage";
import type { BootstrapData } from "../api/client";

const configuration = vi.hoisted(() => ({
  listObjectTypes: vi.fn(),
  listObjectDirectory: vi.fn(),
  createObjectType: vi.fn(),
  updateObjectType: vi.fn(),
  listWorkflows: vi.fn(),
  publishWorkflow: vi.fn(),
  listSkills: vi.fn(),
  getSkill: vi.fn(),
  createSkill: vi.fn(),
  updateSkill: vi.fn(),
  setSkillStatus: vi.fn(),
  listApiKeys: vi.fn(),
  listApiKeyOwners: vi.fn(),
  createApiKey: vi.fn(),
  updateApiKey: vi.fn(),
}));

const client = vi.hoisted(() => ({ listCapabilities: vi.fn(), listUsers: vi.fn() }));

vi.mock("../api/configuration", () => configuration);
vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, ...client };
});

const meta = { total: 1, page: 1, page_size: 20, pages: 1 };
const objectType = {
  id: "type-1", tenant_id: "tenant-1", entity_kind: "business_object", object_type: "contract",
  title: "合同", description: "合同记录", json_schema: { type: "object" }, state_machine: null,
  version: 2, status: "active", created_by: "user:1", created_at: "2026-07-01T00:00:00Z", updated_at: null,
};
const workflow = {
  id: "workflow-1", tenant_id: "tenant-1", entity_kind: "business_object", object_type: "contract",
  name: "default", version: 3, definition_text: "提交后由法务审批", status: "active",
  created_by: "user:1", created_at: "2026-07-01T00:00:00Z",
};
const skill = {
  id: "skill-1", tenant_id: "tenant-1", name: "contract-review", kind: "custom", title: "合同复核",
  description: "复核合同", required_capability: "business_object.write:contract", files: { "SKILL.md": "# Review" },
  version: 1, status: "active", created_by: "user:1", created_at: "2026-07-01T00:00:00Z", updated_at: null,
};
const apiKey = {
  id: "key-12345678", tenant_id: "tenant-1", label: "agent", user_id: "user-1", role: "member",
  effective_role: "finance_reviewer", effective_active: true, user_name: "管理员", user_email: "admin@example.com", user_status: "active",
  is_active: true, created_at: "2026-07-01T00:00:00Z", updated_at: null,
};

function renderPage(
  node: React.ReactNode,
  access: { role?: string; permissions?: string[] } = {
    role: "admin",
    permissions: ["object_types.manage", "workflows.publish", "skills.manage", "keys.manage"],
  },
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const bootstrap = {
    user: { id: "user-1", email: "admin@example.com", name: "管理员" },
    tenant: { id: "tenant-1", name: "测试租户", email_domain: "example.com" },
    role: access.role ?? "admin",
    permissions: access.permissions ?? [],
    employee_id: null,
  } as BootstrapData;
  return render(<QueryClientProvider client={queryClient}><MemoryRouter><Routes>
    <Route element={<Outlet context={{ bootstrap }} />}><Route index element={node} /></Route>
  </Routes></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  configuration.listObjectTypes.mockResolvedValue({ data: [objectType], meta });
  configuration.listObjectDirectory.mockResolvedValue([
    { entity_kind: "builtin", object_type: "timesheet_header", count: 3, title: "工时单", definition_status: "active" },
    { entity_kind: "business_object", object_type: "contract", count: 8, title: "合同", definition_status: "active" },
  ]);
  configuration.listWorkflows.mockResolvedValue({ data: [workflow], meta });
  configuration.createObjectType.mockResolvedValue(objectType);
  configuration.updateObjectType.mockResolvedValue(objectType);
  configuration.publishWorkflow.mockResolvedValue(workflow);
  configuration.listSkills.mockResolvedValue({ data: [skill], meta });
  configuration.getSkill.mockResolvedValue(skill);
  configuration.createSkill.mockResolvedValue(skill);
  configuration.updateSkill.mockResolvedValue(skill);
  configuration.setSkillStatus.mockResolvedValue(skill);
  configuration.listApiKeys.mockResolvedValue({ data: [apiKey], meta });
  configuration.listApiKeyOwners.mockResolvedValue({ data: [{ id: "user-1", email: "admin@example.com", name: "管理员", role: "finance_reviewer", status: "active" }], meta });
  configuration.createApiKey.mockResolvedValue({ api_key: apiKey, plain_text_api_key: "oryh_secret_once" });
  configuration.updateApiKey.mockResolvedValue({ ...apiKey, is_active: false });
  client.listCapabilities.mockResolvedValue({
    capabilities: [{ id: "cap-1", name: "business_object.write", kind: "system", title: "业务对象写入", description: null, scopable: true, created_at: "2026-07-01T00:00:00Z" }],
    object_types: ["contract"],
  });
  client.listUsers.mockResolvedValue({ data: [{ id: "user-1", email: "admin@example.com", name: "管理员", role: "admin", status: "active" }], meta });
});

afterEach(cleanup);

describe("skill capability frontmatter", () => {
  const skillMd = `---
name: contract-review
required_capability: business_object.write:contract
---

# Contract review`;

  it("reads required_capability only from SKILL.md frontmatter", () => {
    expect(parseSkillRequiredCapability(skillMd)).toBe("business_object.write:contract");
    expect(parseSkillRequiredCapability("# No frontmatter\nrequired_capability: users.manage")).toBeNull();
  });

  it("uses frontmatter only until the capability selection is explicit", () => {
    expect(resolveSkillRequiredCapability("", false, skillMd)).toBe("business_object.write:contract");
    expect(resolveSkillRequiredCapability("skills.manage", false, skillMd)).toBe("skills.manage");
    expect(resolveSkillRequiredCapability("", true, skillMd)).toBeNull();
  });
});

describe("remaining configuration workspaces", () => {
  it("renders object types and workflows and validates field rules before creating", async () => {
    const user = userEvent.setup();
    renderPage(<ObjectTypesPage />);
    expect(await screen.findByText("合同")).toBeInTheDocument();
    expect(screen.getByText("提交后由法务审批")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "定义类型" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(/对象类型/), "warranty_card");
    const schema = within(dialog).getByLabelText(/字段规则/);
    await user.clear(schema);
    await user.type(schema, "not json");
    await user.click(within(dialog).getByRole("button", { name: "创建定义" }));
    expect(await within(dialog).findByText(/字段规则格式不正确/)).toBeInTheDocument();
    expect(configuration.createObjectType).not.toHaveBeenCalled();

    fireEvent.change(schema, { target: { value: '{"type":"object"}' } });
    await user.click(within(dialog).getByRole("button", { name: "创建定义" }));
    await waitFor(() => expect(configuration.createObjectType).toHaveBeenCalledWith(expect.objectContaining({ object_type: "warranty_card" })));
  });

  it("keeps object-type editing and workflow publishing independently capability-gated", async () => {
    const user = userEvent.setup();
    const first = renderPage(<ObjectTypesPage />, { role: "schema_editor", permissions: ["object_types.manage"] });
    expect(await screen.findByRole("button", { name: "定义类型" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "发布流程" })).not.toBeInTheDocument();
    first.unmount();

    renderPage(<ObjectTypesPage />, { role: "flow_publisher", permissions: ["workflows.publish"] });
    const publishButton = await screen.findByRole("button", { name: "发布流程" });
    expect(screen.queryByRole("button", { name: "定义类型" })).not.toBeInTheDocument();
    await user.click(publishButton);
    const dialog = screen.getByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText(/对象类型/), "business_object:contract");
    const definition = within(dialog).getByLabelText(/自然语言流程/);
    expect(definition).toHaveAttribute("placeholder", expect.stringContaining("提交要求"));
    expect(within(dialog).getByText(/「提交要求」由员工侧 agent 填写时核对/)).toBeInTheDocument();
    await user.type(definition, "提交后由法务审批");
    await user.click(within(dialog).getByRole("button", { name: "发布新版本" }));
    await waitFor(() => expect(configuration.publishWorkflow).toHaveBeenCalledWith(expect.objectContaining({
      entity_kind: "business_object", object_type: "contract",
    })));
  });

  it("creates a skill with SKILL.md and a scoped capability", async () => {
    const user = userEvent.setup();
    renderPage(<SkillsPage />);
    expect(await screen.findByText("合同复核")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "新建技能" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(/名称/), "daily-report");
    await user.selectOptions(within(dialog).getByLabelText("所需能力"), "business_object.write:contract");
    await user.click(within(dialog).getByRole("button", { name: "创建技能" }));
    await waitFor(() => expect(configuration.createSkill).toHaveBeenCalledWith(expect.objectContaining({
      name: "daily-report",
      required_capability: "business_object.write:contract",
      files: expect.objectContaining({ "SKILL.md": expect.any(String) }),
    })));
  });

  it("falls back to SKILL.md required_capability when the picker is untouched", async () => {
    const user = userEvent.setup();
    renderPage(<SkillsPage />);
    expect(await screen.findByText("合同复核")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "新建技能" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(/名称/), "frontmatter-skill");
    fireEvent.change(within(dialog).getByLabelText("SKILL.md 内容"), {
      target: {
        value: "---\nname: frontmatter-skill\nrequired_capability: business_object.write:contract\n---\n\n# Review",
      },
    });

    expect(within(dialog).getByLabelText("所需能力")).toHaveValue("business_object.write:contract");
    expect(within(dialog).getByText(/已从 SKILL.md frontmatter 读取/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "创建技能" }));

    await waitFor(() => expect(configuration.createSkill).toHaveBeenCalledWith(expect.objectContaining({
      name: "frontmatter-skill",
      required_capability: "business_object.write:contract",
    })));
  });

  it("lets an editor explicitly clear a capability declared in SKILL.md", async () => {
    const user = userEvent.setup();
    configuration.getSkill.mockResolvedValue({
      ...skill,
      files: {
        "SKILL.md": "---\nname: contract-review\nrequired_capability: business_object.write:contract\n---\n\n# Review",
      },
    });
    renderPage(<SkillsPage />);
    expect(await screen.findByText("合同复核")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "编辑" }));
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("所需能力"), "");

    expect(within(dialog).getByText(/已明确忽略 SKILL.md/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "保存技能" }));

    await waitFor(() => expect(configuration.updateSkill).toHaveBeenCalledWith(
      "contract-review",
      expect.objectContaining({ required_capability: null }),
    ));
  });

  it("keeps the most recently selected skill when edit requests resolve out of order", async () => {
    const user = userEvent.setup();
    const secondSkill = { ...skill, id: "skill-2", name: "expense-review", title: "费用复核" };
    configuration.listSkills.mockResolvedValue({ data: [skill, secondSkill], meta: { ...meta, total: 2 } });
    let resolveFirst!: (value: typeof skill) => void;
    let resolveSecond!: (value: typeof secondSkill) => void;
    configuration.getSkill.mockImplementation((name: string) => new Promise((resolve) => {
      if (name === skill.name) resolveFirst = resolve;
      else resolveSecond = resolve;
    }));
    renderPage(<SkillsPage />);
    expect(await screen.findByText("合同复核")).toBeInTheDocument();
    const editButtons = screen.getAllByRole("button", { name: "编辑" });
    await user.click(editButtons[0]);
    await user.click(editButtons[1]);
    await act(async () => resolveSecond(secondSkill));
    expect(await within(screen.getByRole("dialog")).findByDisplayValue("expense-review")).toBeInTheDocument();
    await act(async () => resolveFirst(skill));
    expect(within(screen.getByRole("dialog")).getByDisplayValue("expense-review")).toBeInTheDocument();
    expect(within(screen.getByRole("dialog")).queryByDisplayValue("contract-review")).not.toBeInTheDocument();
  });

  it("blocks skill saves while the capability catalog is unavailable", async () => {
    const user = userEvent.setup();
    client.listCapabilities.mockRejectedValue(new Error("catalog unavailable"));
    renderPage(<SkillsPage />);
    expect(await screen.findByText("合同复核")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "新建技能" }));
    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByText(/能力目录加载失败/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "创建技能" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "重试" })).toBeInTheDocument();
  });

  it("shows a newly-created API key only-once panel and confirms deactivation", async () => {
    const user = userEvent.setup();
    renderPage(<ApiKeysPage />);
    expect(await screen.findByText("agent")).toBeInTheDocument();
    expect(screen.getByText("finance_reviewer")).toBeInTheDocument();
    expect(screen.getByText("签发时：member")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "创建凭证" }));
    const drawer = screen.getByRole("dialog");
    await user.selectOptions(await within(drawer).findByLabelText("绑定用户（可选）"), "user-1");
    await user.clear(within(drawer).getByLabelText("标签"));
    await user.type(within(drawer).getByLabelText("标签"), "integration");
    await user.click(within(drawer).getByRole("button", { name: "创建凭证" }));
    expect(configuration.createApiKey).toHaveBeenCalledWith({ label: "integration", user_id: "user-1" });
    const secret = await screen.findByText("oryh_secret_once");
    expect(secret).toHaveAttribute("aria-label", expect.stringContaining("主动复制"));
    expect(secret.closest('[role="status"]')).toBeNull();
    expect(screen.getByRole("status")).not.toHaveTextContent("oryh_secret_once");

    await user.click(screen.getByRole("button", { name: "停用" }));
    const confirm = screen.getByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: "确认停用" }));
    await waitFor(() => expect(configuration.updateApiKey).toHaveBeenCalledWith(apiKey.id, { is_active: false }));
  });

  it("does not present enabled keys with unavailable owners as effective", async () => {
    configuration.listApiKeys.mockResolvedValue({
      data: [
        { ...apiKey, effective_active: false, effective_role: null, user_status: "disabled" },
        {
          ...apiKey,
          id: "key-missing-owner",
          label: "orphaned-agent",
          user_name: null,
          user_email: null,
          user_status: null,
          effective_active: false,
          effective_role: null,
        },
      ],
      meta: { ...meta, total: 2 },
    });

    renderPage(<ApiKeysPage />);
    expect(await screen.findByText("用户已停用")).toBeInTheDocument();
    expect(screen.getByText("用户不存在")).toBeInTheDocument();
    expect(screen.getAllByText("无有效角色")).toHaveLength(2);
    expect(screen.queryByText("finance_reviewer")).not.toBeInTheDocument();
  });
});
