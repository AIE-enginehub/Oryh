import { apiRequest, apiRequestEnvelope, type PaginationMeta } from "./client";

export type FlowRunTrigger = "cadence" | "signal" | "manual";
export type FlowRunStatus = "running" | "succeeded" | "failed" | "skipped";

export type FlowSubscription = {
  id: string;
  tenant_id: string;
  entity_type: string;
  driver_skill: string;
  queue_filter: Record<string, unknown>;
  cadence_seconds: number;
  enabled: boolean;
  api_key_id?: string | null;
  created_by?: string | null;
  unmoved_runs: number;
  parked_at?: string | null;
  parked_reason?: string | null;
  last_run_at?: string | null;
  created_at: string;
  updated_at?: string | null;
};

/**
 * An enabled subscription writes at least an hourly "looked, nothing here" row,
 * so silence for much longer than that means no runner is driving it. Twice the
 * heartbeat: long enough that a late tick is not an alarm, short enough to be
 * worth saying.
 */
export const DRIVER_SILENT_MS = 2 * 60 * 60 * 1000;

/** How long a just-created subscription is given before silence counts. */
const STARTUP_GRACE_MS = 10 * 60 * 1000;

export type DriverState = "parked" | "off" | "silent" | "starting" | "running";

/**
 * Why nothing may be happening — kept in one place because `enabled` alone
 * cannot answer it. `enabled` says the tenant has not switched this off; it says
 * nothing about whether a runner exists, so a stopped runner and a working one
 * render identically through that field unless something else is checked.
 */
export function driverState(
  subscription: FlowSubscription,
  now: number = Date.now(),
): DriverState {
  if (subscription.parked_at) return "parked";
  if (!subscription.enabled) return "off";
  const lastSeen = subscription.last_run_at ?? null;
  if (!lastSeen) {
    // Never run. Freshly enrolled and still starting, or enrolled long ago and
    // never once picked up — the same field, two very different sentences.
    const age = now - new Date(subscription.created_at).getTime();
    return age < STARTUP_GRACE_MS ? "starting" : "silent";
  }
  return now - new Date(lastSeen).getTime() > DRIVER_SILENT_MS ? "silent" : "running";
}

export type FlowRun = {
  id: string;
  tenant_id: string;
  subscription_id?: string | null;
  entity_type: string;
  trigger: FlowRunTrigger;
  status: FlowRunStatus;
  started_at: string;
  finished_at?: string | null;
  queue_size?: number | null;
  items_advanced?: number | null;
  error?: string | null;
  detail: Record<string, unknown>;
  recorded_by?: string | null;
  created_at: string;
};

export type FlowRunPage = { data: FlowRun[]; meta: PaginationMeta };

export async function listFlowSubscriptions(): Promise<FlowSubscription[]> {
  return apiRequest<FlowSubscription[]>("/api/v1/flow-subscriptions");
}

export async function setFlowSubscriptionEnabled(
  id: string,
  enabled: boolean,
): Promise<FlowSubscription> {
  return apiRequest<FlowSubscription>(`/api/v1/flow-subscriptions/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}

export async function listFlowRuns(
  filters: { page?: number; size?: number; entity_type?: string; status?: FlowRunStatus } = {},
): Promise<FlowRunPage> {
  const page = filters.page ?? 1;
  const size = filters.size ?? 20;
  const search = new URLSearchParams({ page: String(page), size: String(size) });
  if (filters.entity_type) search.set("entity_type", filters.entity_type);
  if (filters.status) search.set("status", filters.status);
  const response = await apiRequestEnvelope<FlowRun[], Partial<PaginationMeta>>(
    `/api/v1/flow-runs?${search.toString()}`,
  );
  const total = typeof response.meta.total === "number" ? response.meta.total : response.data.length;
  return {
    data: response.data,
    meta: {
      total,
      page: response.meta.page ?? page,
      page_size: response.meta.page_size ?? size,
      pages: response.meta.pages ?? Math.max(1, Math.ceil(total / size)),
    },
  };
}

/** A run that opened and never reported back — the only shape "it hung" takes. */
export function isStalled(run: FlowRun, now: number = Date.now()): boolean {
  if (run.status !== "running") return false;
  return now - new Date(run.started_at).getTime() > 30 * 60 * 1000;
}

/**
 * Whether the queue this run looked at was deeper than the run was allowed to
 * take on. Without this, "advanced 10" beside a queue of 200 reads as done.
 */
export function wasCapped(run: FlowRun): boolean {
  return typeof run.detail?.batch_limit === "number";
}
