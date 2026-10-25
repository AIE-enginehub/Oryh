import { zhCN } from "../locales/zh-CN/tests";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FlowRun, FlowSubscription } from "../api/flows";
import { FlowAgentPage } from "./FlowAgentPage";

const api = vi.hoisted(() => ({
  listFlowSubscriptions: vi.fn(),
  listFlowRuns: vi.fn(),
  setFlowSubscriptionEnabled: vi.fn(),
  clearFlowSubscriptionPark: vi.fn(),
  getFlowRunnerAvailability: vi.fn(),
}));

vi.mock("../api/flows", async () => {
  const actual = await vi.importActual<typeof import("../api/flows")>("../api/flows");
  return { ...actual, ...api };
});

const subscription = {
  id: "sub-1",
  tenant_id: "tenant-1",
  entity_type: "timesheet_header",
  driver_skill: "oryh-timesheet-approval-flow",
  queue_filter: { status: "submitted" },
  cadence_seconds: 60,
  enabled: true,
  api_key_id: "key-1",
  created_by: "platform:ops",
  unmoved_runs: 0,
  parked_at: null,
  parked_reason: null,
  last_run_at: new Date().toISOString(),
  created_at: "2026-07-29T09:00:00Z",
  updated_at: null,
} as FlowSubscription;

function run(overrides: Partial<FlowRun>): FlowRun {
  return {
    id: "run-1",
    tenant_id: "tenant-1",
    subscription_id: "sub-1",
    entity_type: "timesheet_header",
    trigger: "cadence",
    status: "succeeded",
    started_at: "2026-07-29T10:00:00Z",
    finished_at: "2026-07-29T10:01:40Z",
    queue_size: 1,
    items_advanced: 1,
    error: null,
    detail: { queue_remaining: 0 },
    recorded_by: "key:hosted",
    created_at: "2026-07-29T10:00:00Z",
    ...overrides,
  } as FlowRun;
}

function page(
  runs: FlowRun[],
  subscriptions: FlowSubscription[] = [subscription],
  platformEnabled = true,
) {
  api.listFlowSubscriptions.mockResolvedValue(subscriptions);
  api.getFlowRunnerAvailability.mockResolvedValue({ flow_runner_enabled: platformEnabled });
  api.listFlowRuns.mockResolvedValue({
    data: runs,
    meta: { total: runs.length, page: 1, page_size: 20, pages: 1 },
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <FlowAgentPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("FlowAgentPage", () => {
  beforeEach(() => {
    api.listFlowSubscriptions.mockReset();
    api.listFlowRuns.mockReset();
    api.setFlowSubscriptionEnabled.mockReset();
    api.clearFlowSubscriptionPark.mockReset();
  });
  afterEach(cleanup);

  it("shows what is driven and who signs the writes", async () => {
    page([run({})]);
    expect(await screen.findByText("oryh-timesheet-approval-flow")).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesFlowAgentPage.pattern())).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesFlowAgentPage.running2)).toBeInTheDocument();
  });

  it("does not dress a run that moved nothing as a success", async () => {
    // The failure the ledger exists to surface: the agent reported success and
    // the queue did not budge. A green "succeeded" badge here would hide it.
    page([run({ items_advanced: 0, queue_size: 3, detail: { queue_remaining: 3 } })]);
    expect(await screen.findByText(zhCN.pagesFlowAgentPage.movedNothing)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesFlowAgentPage.pattern2())).toBeInTheDocument();
  });

  it("reads a capped batch as progress rather than completion", async () => {
    page([run({ items_advanced: 10, queue_size: 200, detail: { queue_remaining: 190, batch_limit: 10 } })]);
    expect(await screen.findByText(zhCN.pagesFlowAgentPage.message3)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesFlowAgentPage.pattern3())).toBeInTheDocument();
  });

  it("tells an idle service apart from a dead one", async () => {
    page([run({ status: "skipped", queue_size: 0, items_advanced: 0, detail: {} })]);
    expect(await screen.findByText(zhCN.pagesFlowAgentPage.nothingToDo)).toBeInTheDocument();
  });

  it("flags a run that opened and never reported back", async () => {
    page([run({ status: "running", finished_at: null, started_at: "2020-01-01T00:00:00Z" })]);
    expect(await screen.findByText(zhCN.pagesFlowAgentPage.noReport)).toBeInTheDocument();
  });

  it("does not call a subscription running when nothing has run in hours", async () => {
    // The bug this replaced: `enabled` was the only signal, so a stopped runner
    // and a working one rendered identically. Silence is the only evidence a
    // tenant has, and it has to be read.
    page([], [{ ...subscription, last_run_at: "2020-01-01T00:00:00Z" }]);
    expect(await screen.findByText(zhCN.pagesFlowAgentPage.notRunning)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesFlowAgentPage.nothingIsDrivingThese)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesFlowAgentPage.pattern4())).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesFlowAgentPage.pattern5())).toBeInTheDocument();
  });

  it("tells never-run-yet apart from just-enrolled", async () => {
    page([], [{ ...subscription, last_run_at: null, created_at: new Date().toISOString() }]);
    expect(await screen.findByText(zhCN.pagesFlowAgentPage.starting)).toBeInTheDocument();
    expect(screen.queryByText(zhCN.pagesFlowAgentPage.nothingIsDrivingThese)).not.toBeInTheDocument();

    cleanup();
    page([], [{ ...subscription, last_run_at: null, created_at: "2026-01-01T00:00:00Z" }]);
    expect(await screen.findByText(zhCN.pagesFlowAgentPage.notRunning)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesFlowAgentPage.pattern6())).toBeInTheDocument();
  });

  it("surfaces a stopped subscription and what to do about it", async () => {
    page([], [{ ...subscription, parked_at: "2026-07-29T11:00:00Z", parked_reason: "3 run(s) found work and moved nothing", unmoved_runs: 3 }]);
    expect(await screen.findByText(zhCN.pagesFlowAgentPage.nothingIsDrivingThese)).toBeInTheDocument();
    expect(screen.getByText("3 run(s) found work and moved nothing")).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesFlowAgentPage.pattern7())).toBeInTheDocument();

    api.clearFlowSubscriptionPark.mockResolvedValue({ ...subscription, parked_at: null, parked_reason: null });
    await userEvent.click(screen.getByRole("button", { name: zhCN.pagesFlowAgentPage.name }));
    await waitFor(() => expect(api.clearFlowSubscriptionPark).toHaveBeenCalledWith("sub-1"));
  });

  it("warns before switching driving off, and says what stops", async () => {
    page([run({})]);
    await userEvent.click(await screen.findByRole("button", { name: zhCN.pagesFlowAgentPage.name2 }));
    expect(screen.getByText(zhCN.pagesFlowAgentPage.pattern8())).toBeInTheDocument();

    api.setFlowSubscriptionEnabled.mockResolvedValue({ ...subscription, enabled: false });
    const dialog = screen.getByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: zhCN.pagesFlowAgentPage.name3 }));
    await waitFor(() =>
      expect(api.setFlowSubscriptionEnabled).toHaveBeenCalledWith("sub-1", false),
    );
  });

  it("says so when the platform, not the tenant, has paused driving", async () => {
    // Switched on, last ran hours ago: without the platform's word this would
    // read as "the driving service may be down" and tell them to contact us
    // about an outage. The truth is a decision, and the page must say whose.
    const stale = new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString();
    page([], [{ ...subscription, last_run_at: stale }], false);
    expect(await screen.findByText(zhCN.pagesFlowAgentPage.oRYHHasPausedHostedDrivingForYourCompany)).toBeInTheDocument();
    expect(screen.getByText(zhCN.pagesFlowAgentPage.pausedByORYH)).toBeInTheDocument();
    expect(screen.queryByText(zhCN.pagesFlowAgentPage.nothingIsDrivingThese)).not.toBeInTheDocument();
    // enrolment is untouched: the tenant's own switch is still theirs to use
    expect(screen.getByRole("button", { name: zhCN.pagesFlowAgentPage.name2 })).toBeInTheDocument();
  });

  it("does not raise the platform banner over a workspace that is being driven", async () => {
    page([run({})]);
    expect(await screen.findByText(zhCN.pagesFlowAgentPage.running2)).toBeInTheDocument();
    expect(screen.queryByText(zhCN.pagesFlowAgentPage.oRYHHasPausedHostedDrivingForYourCompany)).not.toBeInTheDocument();
  });

  it("says that switching a parked one on clears the stop", async () => {
    page([], [{ ...subscription, enabled: false, parked_at: "2026-07-29T11:00:00Z", parked_reason: "stuck" }]);
    await userEvent.click(await screen.findByRole("button", { name: zhCN.pagesFlowAgentPage.name4 }));
    expect(screen.getByText(zhCN.pagesFlowAgentPage.pattern9())).toBeInTheDocument();
  });
});
