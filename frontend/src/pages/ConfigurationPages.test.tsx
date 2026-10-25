import { zhCN } from "../locales/zh-CN/tests";
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
  listBusinessRules: vi.fn(),
  publishBusinessRule: vi.fn(),
  publishRuleDraft: vi.fn(),
  repealBusinessRule: vi.fn(),
  rescopeBusinessRule: vi.fn(),
  listPolicyCategories: vi.fn(),
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
  title: zhCN.pagesConfigurationPages.title, description: zhCN.pagesConfigurationPages.description, json_schema: { type: "object" }, state_machine: null,
  version: 2, status: "active", created_by: "user:1", created_at: "2026-07-01T00:00:00Z", updated_at: null,
};
const rule = {
  id: "rule-1", kind: "approval_flow", code: "approval_flow:business_object:contract:default", version: 3,
  entity_kind: "business_object", object_type: "contract", name: "default", origin: "tenant", category: null,
  title: zhCN.pagesConfigurationPages.title2, summary: null, body: zhCN.pagesConfigurationPages.body, rules_json: null, visibility: "internal",
  required_capability: null, status: "published", effective_from: "2026-07-01", effective_thru: null,
  published_at: "2026-07-01T00:00:00Z", published_by: "user:1", supersedes_id: null, attachment_id: null,
  owner_employee_id: null, created_by: "user:1", custom_fields: {}, created_at: "2026-07-01T00:00:00Z", updated_at: "2026-07-01T00:00:00Z",
};
const skill = {
  id: "skill-1", tenant_id: "tenant-1", name: "contract-review", kind: "custom", title: zhCN.pagesConfigurationPages.title3,
  description: zhCN.pagesConfigurationPages.description2, required_capability: "business_object.write:contract", files: { "SKILL.md": "# Review" },
  version: 1, status: "active", created_by: "user:1", created_at: "2026-07-01T00:00:00Z", updated_at: null,
};
const apiKey = {
  id: "key-12345678", tenant_id: "tenant-1", label: "agent", user_id: "user-1", role: "member",
  effective_role: "finance_reviewer", effective_active: true, user_name: zhCN.pagesConfigurationPages.userName, user_email: "admin@example.com", user_status: "active",
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
    user: { id: "user-1", email: "admin@example.com", name: zhCN.pagesConfigurationPages.userName },
    tenant: { id: "tenant-1", name: zhCN.pagesConfigurationPages.name, email_domain: "example.com" },
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
    { entity_kind: "builtin", object_type: "timesheet_header", count: 3, title: zhCN.pagesConfigurationPages.title4, definition_status: "active" },
    { entity_kind: "business_object", object_type: "contract", count: 8, title: zhCN.pagesConfigurationPages.title, definition_status: "active" },
  ]);
  configuration.listBusinessRules.mockResolvedValue({ data: [rule], meta });
  configuration.createObjectType.mockResolvedValue(objectType);
  configuration.updateObjectType.mockResolvedValue(objectType);
  configuration.publishBusinessRule.mockResolvedValue({ current: { ...rule, version: 4 }, superseded: rule });
  configuration.publishRuleDraft.mockResolvedValue({ current: rule, superseded: null });
  configuration.repealBusinessRule.mockResolvedValue({ ...rule, status: "repealed" });
  configuration.rescopeBusinessRule.mockResolvedValue(rule);
  configuration.listPolicyCategories.mockResolvedValue([{ id: "cat-1", name: "hr", title: zhCN.pagesConfigurationPages.title5, is_active: true }]);
  configuration.listSkills.mockResolvedValue({ data: [skill], meta });
  configuration.getSkill.mockResolvedValue(skill);
  configuration.createSkill.mockResolvedValue(skill);
  configuration.updateSkill.mockResolvedValue(skill);
  configuration.setSkillStatus.mockResolvedValue(skill);
  configuration.listApiKeys.mockResolvedValue({ data: [apiKey], meta });
  configuration.listApiKeyOwners.mockResolvedValue({ data: [{ id: "user-1", email: "admin@example.com", name: zhCN.pagesConfigurationPages.userName, role: "finance_reviewer", status: "active" }], meta });
  configuration.createApiKey.mockResolvedValue({ api_key: apiKey, plain_text_api_key: "oryh_secret_once" });
  configuration.updateApiKey.mockResolvedValue({ ...apiKey, is_active: false });
  client.listCapabilities.mockResolvedValue({
    capabilities: [{ id: "cap-1", name: "business_object.write", kind: "system", title: zhCN.pagesConfigurationPages.title6, description: null, scopable: true, created_at: "2026-07-01T00:00:00Z" }],
    object_types: ["contract"],
  });
  client.listUsers.mockResolvedValue({ data: [{ id: "user-1", email: "admin@example.com", name: zhCN.pagesConfigurationPages.userName, role: "admin", status: "active" }], meta });
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
  it("renders object types and business rules by kind and validates field rules before creating", async () => {
    const user = userEvent.setup();
    renderPage(<ObjectTypesPage />);
    expect(await screen.findByText(zhCN.pagesConfigurationPages.title)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesConfigurationPages.body)).toBeInTheDocument();
    expect(configuration.listBusinessRules).toHaveBeenCalledWith(expect.objectContaining({ kind: "approval_flow", status: "published" }));

    // the kind picker is the question; history widens it to every version
    await user.selectOptions(screen.getByLabelText(zhCN.pagesConfigurationPages.ruleKind), "data_rule");
    await waitFor(() => expect(configuration.listBusinessRules).toHaveBeenCalledWith(expect.objectContaining({ kind: "data_rule", status: "published" })));
    await user.click(screen.getByLabelText(zhCN.pagesConfigurationPages.showVersionHistory));
    await waitFor(() => expect(configuration.listBusinessRules).toHaveBeenCalledWith(expect.objectContaining({ kind: "data_rule", status: undefined })));

    await user.click(screen.getByRole("button", { name: zhCN.pagesConfigurationPages.name2 }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern()), "warranty_card");
    const schema = within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern2());
    await user.clear(schema);
    await user.type(schema, "not json");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesConfigurationPages.name3 }));
    expect(await within(dialog).findByText(zhCN.pagesConfigurationPages.pattern3())).toBeInTheDocument();
    expect(configuration.createObjectType).not.toHaveBeenCalled();

    fireEvent.change(schema, { target: { value: '{"type":"object"}' } });
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesConfigurationPages.name3 }));
    await waitFor(() => expect(configuration.createObjectType).toHaveBeenCalledWith(expect.objectContaining({ object_type: "warranty_card" })));
  });

  it("keeps object-type editing and rule publishing independently capability-gated", async () => {
    const user = userEvent.setup();
    const first = renderPage(<ObjectTypesPage />, { role: "schema_editor", permissions: ["object_types.manage"] });
    expect(await screen.findByRole("button", { name: zhCN.pagesConfigurationPages.name2 })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: zhCN.pagesConfigurationPages.name4 })).not.toBeInTheDocument();
    first.unmount();

    renderPage(<ObjectTypesPage />, { role: "flow_publisher", permissions: ["workflows.publish"] });
    const publishButton = await screen.findByRole("button", { name: zhCN.pagesConfigurationPages.name4 });
    expect(screen.queryByRole("button", { name: zhCN.pagesConfigurationPages.name2 })).not.toBeInTheDocument();
    await user.click(publishButton);
    const dialog = screen.getByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern()), "business_object:contract");
    // the editor opens on the version in force, and says which kind of reader it is for
    const body = within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern4());
    await waitFor(() => expect(body).toHaveValue(zhCN.pagesConfigurationPages.body));
    expect(within(dialog).getByText(zhCN.pagesConfigurationPages.pattern5())).toBeInTheDocument();
    expect(within(dialog).getByText(zhCN.pagesConfigurationPages.pattern6())).toBeInTheDocument();
    await user.selectOptions(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern7()), "data_rule");
    expect(within(dialog).getByText(zhCN.pagesConfigurationPages.pattern8())).toBeInTheDocument();
    expect(body).toHaveAttribute("placeholder", expect.stringContaining(zhCN.pagesConfigurationPages.message3));
    await user.clear(body);
    await user.type(body, zhCN.pagesConfigurationPages.message4);
    // the drawer shows what the draft drops from the version in force, and says so when it is everything
    expect(within(dialog).getByText(zhCN.pagesConfigurationPages.pattern9())).toBeInTheDocument();
    expect(within(dialog).getByText(zhCN.pagesConfigurationPages.pattern10())).toBeInTheDocument();
    expect(within(dialog).getByText(zhCN.pagesConfigurationPages.message5)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesConfigurationPages.name5 }));
    await waitFor(() => expect(configuration.publishBusinessRule).toHaveBeenCalledWith({
      kind: "data_rule", entity_kind: "business_object", object_type: "contract", name: "default", body: zhCN.pagesConfigurationPages.message4,
    }));
  });

  it("opens the publish drawer on the seeded draft when nothing is in force", async () => {
    const user = userEvent.setup();
    const seed = { ...rule, id: "seed-1", version: 1, status: "draft", origin: "catalog", published_at: null, published_by: null, effective_from: null, body: zhCN.pagesConfigurationPages.body2 };
    configuration.listBusinessRules.mockResolvedValue({ data: [seed], meta });
    renderPage(<ObjectTypesPage />, { role: "flow_publisher", permissions: ["workflows.publish"] });
    await user.click(await screen.findByRole("button", { name: zhCN.pagesConfigurationPages.name4 }));
    const dialog = screen.getByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern()), "business_object:contract");
    const body = within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern4());
    await waitFor(() => expect(body).toHaveValue(zhCN.pagesConfigurationPages.body2));
    expect(within(dialog).getByText(zhCN.pagesConfigurationPages.pattern11())).toBeInTheDocument();
  });

  it("publishes a policy from the drawer under policy.publish, with its own code, category and title", async () => {
    const user = userEvent.setup();
    configuration.listBusinessRules.mockResolvedValue({ data: [], meta: { ...meta, total: 0 } });
    renderPage(<ObjectTypesPage />, { role: "policy_publisher", permissions: ["policy.publish"] });
    await user.click(await screen.findByRole("button", { name: zhCN.pagesConfigurationPages.name4 }));
    const dialog = screen.getByRole("dialog");
    // without workflows.publish the only kind on offer is the policy
    const kinds = within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern7()) as HTMLSelectElement;
    expect(Array.from(kinds.options).map((o) => o.value)).toEqual(["policy"]);
    expect(within(dialog).queryByLabelText(zhCN.pagesConfigurationPages.pattern())).not.toBeInTheDocument();
    await user.type(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern12()), "HR-001");
    await waitFor(() => expect(configuration.listBusinessRules).toHaveBeenCalledWith(expect.objectContaining({ kind: "policy", code: "HR-001" })));
    await user.selectOptions(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern13()), "hr");
    await user.type(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern14()), zhCN.pagesConfigurationPages.message6);
    await user.type(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern4()), zhCN.pagesConfigurationPages.message7);
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesConfigurationPages.name5 }));
    await waitFor(() => expect(configuration.publishBusinessRule).toHaveBeenCalledWith({
      kind: "policy", code: "HR-001", category: "hr", title: zhCN.pagesConfigurationPages.message6, body: zhCN.pagesConfigurationPages.message7,
    }));
  });

  it("releases a draft, repeals the version in force and rescopes it from the row", async () => {
    const user = userEvent.setup();
    const seed = { ...rule, id: "seed-1", version: 1, status: "draft", origin: "catalog", published_at: null, published_by: null, effective_from: null };
    configuration.listBusinessRules.mockResolvedValue({ data: [seed, rule], meta: { ...meta, total: 2 } });
    renderPage(<ObjectTypesPage />, { role: "flow_publisher", permissions: ["workflows.publish"] });
    const draftRow = (await screen.findByText("v1")).closest("tr") as HTMLElement;
    const liveRow = screen.getByText("v3").closest("tr") as HTMLElement;
    // a draft can only be released; a version in force can be closed or re-scoped
    expect(within(draftRow).queryByRole("button", { name: zhCN.pagesConfigurationPages.name6 })).not.toBeInTheDocument();
    expect(within(liveRow).queryByRole("button", { name: zhCN.pagesConfigurationPages.name7 })).not.toBeInTheDocument();

    await user.click(within(draftRow).getByRole("button", { name: zhCN.pagesConfigurationPages.name7 }));
    let dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(zhCN.pagesConfigurationPages.publishDraft)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesConfigurationPages.name7 }));
    await waitFor(() => expect(configuration.publishRuleDraft).toHaveBeenCalledWith("seed-1", {}));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(within(liveRow).getByRole("button", { name: zhCN.pagesConfigurationPages.name6 }));
    dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern15()), { target: { value: "2026-12-31" } });
    await user.type(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern16()), zhCN.pagesConfigurationPages.message9);
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesConfigurationPages.name6 }));
    await waitFor(() => expect(configuration.repealBusinessRule).toHaveBeenCalledWith("rule-1", { effective_thru: "2026-12-31", note: zhCN.pagesConfigurationPages.message9 }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(within(liveRow).getByRole("button", { name: zhCN.pagesConfigurationPages.name8 }));
    dialog = screen.getByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern17()), "restricted");
    await user.type(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern18()), "payroll.read");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesConfigurationPages.name9 }));
    await waitFor(() => expect(configuration.rescopeBusinessRule).toHaveBeenCalledWith("rule-1", { visibility: "restricted", required_capability: "payroll.read" }));
  });

  it("creates a skill with SKILL.md and a scoped capability", async () => {
    const user = userEvent.setup();
    renderPage(<SkillsPage />);
    expect(await screen.findByText(zhCN.pagesConfigurationPages.title3)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: zhCN.pagesConfigurationPages.name10 }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern19()), "daily-report");
    await user.selectOptions(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.requiredCapability), "business_object.write:contract");
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesConfigurationPages.name11 }));
    await waitFor(() => expect(configuration.createSkill).toHaveBeenCalledWith(expect.objectContaining({
      name: "daily-report",
      required_capability: "business_object.write:contract",
      files: expect.objectContaining({ "SKILL.md": expect.any(String) }),
    })));
  });

  it("falls back to SKILL.md required_capability when the picker is untouched", async () => {
    const user = userEvent.setup();
    renderPage(<SkillsPage />);
    expect(await screen.findByText(zhCN.pagesConfigurationPages.title3)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: zhCN.pagesConfigurationPages.name10 }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.pattern19()), "frontmatter-skill");
    fireEvent.change(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.message11), {
      target: {
        value: "---\nname: frontmatter-skill\nrequired_capability: business_object.write:contract\n---\n\n# Review",
      },
    });

    expect(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.requiredCapability)).toHaveValue("business_object.write:contract");
    expect(within(dialog).getByText(zhCN.pagesConfigurationPages.pattern20())).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesConfigurationPages.name11 }));

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
    expect(await screen.findByText(zhCN.pagesConfigurationPages.title3)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: zhCN.pagesConfigurationPages.name12 }));
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText(zhCN.pagesConfigurationPages.requiredCapability), "");

    expect(within(dialog).getByText(zhCN.pagesConfigurationPages.pattern21())).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: zhCN.pagesConfigurationPages.name13 }));

    await waitFor(() => expect(configuration.updateSkill).toHaveBeenCalledWith(
      "contract-review",
      expect.objectContaining({ required_capability: null }),
    ));
  });

  it("keeps the most recently selected skill when edit requests resolve out of order", async () => {
    const user = userEvent.setup();
    const secondSkill = { ...skill, id: "skill-2", name: "expense-review", title: zhCN.pagesConfigurationPages.title7 };
    configuration.listSkills.mockResolvedValue({ data: [skill, secondSkill], meta: { ...meta, total: 2 } });
    let resolveFirst!: (value: typeof skill) => void;
    let resolveSecond!: (value: typeof secondSkill) => void;
    configuration.getSkill.mockImplementation((name: string) => new Promise((resolve) => {
      if (name === skill.name) resolveFirst = resolve;
      else resolveSecond = resolve;
    }));
    renderPage(<SkillsPage />);
    expect(await screen.findByText(zhCN.pagesConfigurationPages.title3)).toBeInTheDocument();
    const editButtons = screen.getAllByRole("button", { name: zhCN.pagesConfigurationPages.name12 });
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
    expect(await screen.findByText(zhCN.pagesConfigurationPages.title3)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: zhCN.pagesConfigurationPages.name10 }));
    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByText(zhCN.pagesConfigurationPages.pattern22())).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: zhCN.pagesConfigurationPages.name11 })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: zhCN.pagesConfigurationPages.name14 })).toBeInTheDocument();
  });

  it("shows a newly-created API key only-once panel and confirms deactivation", async () => {
    const user = userEvent.setup();
    renderPage(<ApiKeysPage />);
    expect(await screen.findByText("agent")).toBeInTheDocument();
    expect(screen.getByText("finance_reviewer")).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesConfigurationPages.message12)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: zhCN.pagesConfigurationPages.name15 }));
    const drawer = screen.getByRole("dialog");
    await user.selectOptions(await within(drawer).findByLabelText(zhCN.pagesConfigurationPages.bindUserOptional), "user-1");
    await user.clear(within(drawer).getByLabelText(zhCN.pagesConfigurationPages.message14));
    await user.type(within(drawer).getByLabelText(zhCN.pagesConfigurationPages.message14), "integration");
    await user.click(within(drawer).getByRole("button", { name: zhCN.pagesConfigurationPages.name15 }));
    expect(configuration.createApiKey).toHaveBeenCalledWith({ label: "integration", user_id: "user-1" });
    const secret = await screen.findByText("oryh_secret_once");
    expect(secret).toHaveAttribute("aria-label", expect.stringContaining(zhCN.pagesConfigurationPages.message15));
    expect(secret.closest('[role="status"]')).toBeNull();
    expect(screen.getByRole("status")).not.toHaveTextContent("oryh_secret_once");

    await user.click(screen.getByRole("button", { name: zhCN.pagesConfigurationPages.name16 }));
    const confirm = screen.getByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: zhCN.pagesConfigurationPages.name17 }));
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
    expect(await screen.findByText(zhCN.pagesConfigurationPages.userDisabled)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesConfigurationPages.userNotFound)).toBeInTheDocument();
    expect(screen.getAllByText(zhCN.pagesConfigurationPages.noEffectiveRole)).toHaveLength(2);
    expect(screen.queryByText("finance_reviewer")).not.toBeInTheDocument();
  });
});
