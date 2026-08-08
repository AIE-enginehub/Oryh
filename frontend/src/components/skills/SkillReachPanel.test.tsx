import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import type { SkillReach, SkillReachEntry } from "../../api/configuration";
import { LanguageProvider } from "../../i18n";
import { SkillReachPanel } from "./SkillReachPanel";

function entry(overrides: Partial<SkillReachEntry> & { name: string }): SkillReachEntry {
  return {
    title: null,
    description: null,
    kind: "custom",
    required_capability: null,
    distribution_mode: "capability",
    received: true,
    reasons: ["capability"],
    named_via: [],
    granted_by_roles: [],
    ...overrides,
  };
}

const reach: SkillReach = {
  subject_type: "user",
  subject_id: "user-1",
  subject_label: "小周",
  role: "member",
  received: [
    entry({ name: "acme-open", title: "开放技能" }),
    entry({ name: "acme-mine", title: "定向给我", reasons: ["targeted_user"], named_via: ["user"] }),
    entry({
      name: "acme-team",
      title: "团队技能",
      reasons: ["targeted_role"],
      named_via: ["role:project_manager"],
    }),
  ],
  withheld: [
    entry({
      name: "acme-gated",
      title: "受限技能",
      received: false,
      reasons: ["missing_capability"],
      required_capability: "purchase.submit_own",
      granted_by_roles: ["procurement", "admin"],
    }),
    entry({
      name: "acme-elsewhere",
      title: "别人的技能",
      received: false,
      reasons: ["not_in_audience"],
      distribution_mode: "targeted",
    }),
  ],
};

function renderPanel(data: SkillReach = reach) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider defaultLanguage="zh-CN">
        <SkillReachPanel subjectKey="user:user-1" fetcher={async () => data} />
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

describe("SkillReachPanel", () => {
  afterEach(cleanup);

  it("says what a withheld skill is for, not just its label", async () => {
    // The incident this panel is meant to prevent: an admin looking at a role
    // named hr_admin, and a withheld skill named "Oryh Payroll". A label does
    // not answer "should HR have this" — so the answer stayed no, the HR
    // agent never got the payroll skill, and it filed the wrong kind of record
    // when asked to 做工资单.
    const user = userEvent.setup();
    renderPanel({
      ...reach,
      withheld: [
        entry({
          name: "oryh-payroll",
          title: "Oryh Payroll",
          description: "Use when HR needs to 定薪/调薪, 生成工资条 for a period, and 发放工资.",
          received: false,
          reasons: ["missing_capability"],
          required_capability: "payroll.manage",
          granted_by_roles: ["admin"],
        }),
      ],
    });

    await user.click(await screen.findByRole("button", { name: /收不到的 1 个技能/ }));
    expect(await screen.findByText(/生成工资条/)).toBeInTheDocument();
    expect(screen.getByText("payroll.manage")).toBeInTheDocument();
  });

  it("names why each received skill arrived", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText("开放技能")).toBeInTheDocument());
    expect(screen.getByText("单独指定")).toBeInTheDocument();
    expect(screen.getByText("通过角色 project_manager 指定")).toBeInTheDocument();
  });

  it("keeps the withheld half one click away, and says how to fix each kind", async () => {
    const user = userEvent.setup();
    renderPanel();
    await waitFor(() => expect(screen.getByText("开放技能")).toBeInTheDocument());

    // collapsed by default — the common case is "what do they have"
    expect(screen.queryByText("受限技能")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /收不到的 2 个技能/ }));

    // a missing capability names the gate AND who holds it, so the person
    // knows what to ask their admin for
    expect(screen.getByText("受限技能")).toBeInTheDocument();
    expect(screen.getByText("purchase.submit_own")).toBeInTheDocument();
    expect(screen.getByText(/procurement、admin/)).toBeInTheDocument();

    // an audience miss is a different fix, and must not be confused with the above
    expect(screen.getByText("别人的技能")).toBeInTheDocument();
    expect(screen.getByText(/该技能为定向分发/)).toBeInTheDocument();
  });

  it("gives a skill blocked on both axes its own group and both fixes", async () => {
    const user = userEvent.setup();
    renderPanel({
      ...reach,
      withheld: [
        entry({
          name: "acme-both",
          title: "两样都缺",
          received: false,
          reasons: ["missing_capability", "not_in_audience"],
          required_capability: "order.submit_own",
          distribution_mode: "targeted",
          granted_by_roles: ["admin"],
        }),
      ],
    });
    await waitFor(() => expect(screen.getByText("开放技能")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /收不到的 1 个技能/ }));

    // NOT filed under "missing the capability" alone — that heading would send
    // the reader to request a grant that leaves the skill just as unreachable
    expect(screen.queryByText("缺少所需能力")).not.toBeInTheDocument();
    expect(screen.getByText("能力和分发范围都不满足")).toBeInTheDocument();
    expect(screen.getByText(/只做其中一样仍然收不到/)).toBeInTheDocument();
  });

  it("says so plainly when someone receives nothing", async () => {
    renderPanel({ ...reach, received: [], withheld: [] });
    await waitFor(() =>
      expect(screen.getByText("目前一个技能也收不到。")).toBeInTheDocument(),
    );
  });
});
