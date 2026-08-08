import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  driverState,
  isStalled,
  listFlowRuns,
  listFlowSubscriptions,
  setFlowSubscriptionEnabled,
  wasCapped,
  type DriverState,
  type FlowRun,
  type FlowSubscription,
} from "../api/flows";
import { ConfirmDialog } from "../components/master-data/ConfirmDialog";
import { apiErrorMessage, ListState } from "../components/master-data/ListState";
import { Pagination } from "../components/master-data/Pagination";
import { useI18n } from "../i18n";
import "./activity.css";
import "./flow-agent.css";

const PAGE_SIZE = 20;

type Text = (chinese: string, english: string) => string;

function formatMoment(value: string | null | undefined, locale: string, text: Text): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(date);
}

function duration(run: FlowRun, text: Text): string {
  if (!run.finished_at) return text("进行中", "running");
  const seconds = Math.round(
    (new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000,
  );
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

/**
 * The sentence a customer actually wants: not the status word, but whether
 * anything moved and whether there is more waiting.
 */
function outcomeOf(run: FlowRun, text: Text): { tone: string; label: string; note: string } {
  const advanced = run.items_advanced ?? 0;
  const remaining = run.detail?.queue_remaining;
  const more = typeof remaining === "number" && remaining > 0
    ? text(`，仍有 ${remaining} 单在排队`, `, ${remaining} still waiting`)
    : "";

  if (run.status === "running") {
    return isStalled(run)
      ? { tone: "failed", label: text("未回报", "No report"), note: text("这次运行开始后没有回报结束，可能已中断。", "This run started and never reported finishing; it may have died.") }
      : { tone: "running", label: text("进行中", "Running"), note: text("正在处理。", "In progress.") };
  }
  if (run.status === "failed") {
    return { tone: "failed", label: text("失败", "Failed"), note: run.error || text("未记录原因。", "No reason recorded.") };
  }
  if (run.status === "skipped") {
    return { tone: "skipped", label: text("无事可做", "Nothing to do"), note: text("查看了队列，没有待安排的单据。", "Looked at the queue and found nothing waiting.") };
  }
  if (advanced === 0) {
    return {
      tone: "stuck",
      label: text("没有推进", "Moved nothing"),
      note: text(
        `发现 ${run.queue_size ?? 0} 单，但一单也没有推进——通常是流程定义指向了不存在的节点，或审批人没有员工记录。`,
        `Found ${run.queue_size ?? 0} record(s) and moved none — usually a workflow definition routing nowhere, or an approver with no employee record.`,
      ),
    };
  }
  return {
    tone: "succeeded",
    label: text(`推进 ${advanced} 单`, `Advanced ${advanced}`),
    note: wasCapped(run)
      ? text(`本次上限 ${run.detail.batch_limit} 单${more}。`, `Capped at ${run.detail.batch_limit} this run${more}.`)
      : text(`已处理完本轮发现的单据${more}。`, `Handled what this pass found${more}.`),
  };
}

const STATE_TONE: Record<DriverState, string> = {
  parked: "failed",
  silent: "failed",
  off: "completed",
  starting: "running",
  running: "open",
};

function stateLabel(state: DriverState, text: Text): string {
  switch (state) {
    case "parked": return text("已暂停", "Stopped");
    case "silent": return text("未在运行", "Not running");
    case "off": return text("已关闭", "Off");
    case "starting": return text("准备中", "Starting");
    default: return text("运行中", "Running");
  }
}


export function FlowAgentPage() {
  const { language, text } = useI18n();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [confirming, setConfirming] = useState<FlowSubscription | null>(null);

  const subscriptions = useQuery({
    queryKey: ["flow-subscriptions"],
    queryFn: listFlowSubscriptions,
  });
  const runs = useQuery({
    queryKey: ["flow-runs", { page }],
    queryFn: () => listFlowRuns({ page, size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      setFlowSubscriptionEnabled(id, enabled),
    onSuccess: () => {
      setConfirming(null);
      void queryClient.invalidateQueries({ queryKey: ["flow-subscriptions"] });
      void queryClient.invalidateQueries({ queryKey: ["flow-runs"] });
    },
  });

  const rows = subscriptions.data ?? [];
  // Both mean "enabled, and yet nothing is being driven" — the one case that has
  // to interrupt the reader, because only a person resolves either.
  const parked = rows.filter((row) => row.parked_at);
  const silent = rows.filter((row) => driverState(row) === "silent");

  return (
    <div className="page flow-agent-page">
      <header className="page-header">
        <div>
          <h1>{text("流程代理", "Flow agent")}</h1>
          <p>
            {text(
              "由 ORYH 代为运行的审批推进。它读你们自己的流程定义决定下一步，写入一律署名「ORYH 托管流程代理」，随时可以关掉。",
              "Approval driving operated by ORYH on your behalf. It reads your own workflow definitions to decide the next step, signs every write as “ORYH 托管流程代理”, and can be switched off at any time.",
            )}
          </p>
        </div>
      </header>

      {(parked.length > 0 || silent.length > 0) && (
        <section className="flow-park-banner" role="status">
          <h2>{text("有流程没有在推进", "Nothing is driving these")}</h2>
          <ul>
            {parked.map((row) => (
              <li key={row.id}>
                <strong>{row.entity_type}</strong>
                <span>{row.parked_reason}</span>
                <small>
                  {text(
                    "原因处理完后，把下面的开关关掉再打开，即可恢复。",
                    "Once the cause is fixed, switch it off and on again below to resume.",
                  )}
                </small>
              </li>
            ))}
            {silent.map((row) => (
              <li key={row.id}>
                <strong>{row.entity_type}</strong>
                <span>
                  {row.last_run_at
                    ? text(
                        "这条流程是开启的，但已经很久没有任何运行记录——推进服务本身可能没有在跑。",
                        "This one is switched on but has not run in a long time — the driving service itself may be down.",
                      )
                    : text(
                        "这条流程是开启的，但从来没有运行过一次——推进服务可能还没有接管它。",
                        "This one is switched on but has never run — the driving service may not have picked it up.",
                      )}
                </span>
                <small>{text("这不是你们这边能修的，请联系我们。", "This is not something you can fix; contact us.")}</small>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="page-section">
        <h2>{text("驱动范围", "What is driven")}</h2>
        <ListState
          loading={subscriptions.isPending}
          error={subscriptions.isError ? apiErrorMessage(subscriptions.error) : null}
          empty={rows.length === 0}
          emptyTitle={text("没有托管的流程", "Nothing is hosted")}
          emptyDescription={text(
            "目前所有审批推进都由你们自己的代理负责。需要 ORYH 代管某类单据时，联系我们开通。",
            "All approval driving is currently done by your own agent. Contact us to hand a document type over.",
          )}
          onRetry={() => void subscriptions.refetch()}
        >
          <div className="table-scroll">
            <table className="data-table activity-table">
              <thead>
                <tr>
                  <th>{text("单据类型", "Document type")}</th>
                  <th>{text("驱动技能", "Driver skill")}</th>
                  <th>{text("检查频率", "Checked every")}</th>
                  <th>{text("状态", "State")}</th>
                  <th><span className="sr-only">{text("操作", "Actions")}</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className={
                    ["parked", "silent"].includes(driverState(row)) ? "flow-row-parked" : undefined
                  }>
                    <td><strong>{row.entity_type}</strong></td>
                    <td><code>{row.driver_skill}</code></td>
                    <td>{text(`${row.cadence_seconds} 秒`, `${row.cadence_seconds}s`)}</td>
                    <td>
                      <span className={`activity-status ${STATE_TONE[driverState(row)]}`}>
                        {stateLabel(driverState(row), text)}
                      </span>
                    </td>
                    <td className="row-actions">
                      <button
                        className="text-action"
                        type="button"
                        onClick={() => { toggle.reset(); setConfirming(row); }}
                      >
                        {row.enabled ? text("关闭", "Switch off") : text("开启", "Switch on")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ListState>
      </section>

      <section className="page-section">
        <h2>{text("运行记录", "Run history")}</h2>
        <p className="section-hint">
          {text(
            "每次检查都会留一条记录。业务写入本身在审计日志里，这里是它们的外壳：什么时候跑的、发现多少、推进多少。",
            "Every check leaves a row. The business writes themselves are in the audit log; this is the envelope around them — when it ran, what it found, what it moved.",
          )}
        </p>
        <ListState
          loading={runs.isPending}
          error={runs.isError ? apiErrorMessage(runs.error) : null}
          empty={Boolean(runs.data && runs.data.data.length === 0)}
          emptyTitle={text("还没有运行记录", "No runs yet")}
          emptyDescription={text(
            "开通后第一次检查会出现在这里。",
            "The first check after enrolment will appear here.",
          )}
          onRetry={() => void runs.refetch()}
        >
          {runs.data && (
            <>
              <div className="table-scroll">
                <table className="data-table activity-table flow-run-table">
                  <thead>
                    <tr>
                      <th>{text("开始时间", "Started")}</th>
                      <th>{text("单据类型", "Document type")}</th>
                      <th>{text("结果", "Outcome")}</th>
                      <th>{text("发现", "Found")}</th>
                      <th>{text("耗时", "Took")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.data.data.map((run) => {
                      const outcome = outcomeOf(run, text);
                      return (
                        <tr key={run.id}>
                          <td>{formatMoment(run.started_at, language, text)}</td>
                          <td><strong>{run.entity_type}</strong></td>
                          <td className="activity-title">
                            <span className={`activity-status ${outcome.tone}`}>{outcome.label}</span>
                            <small>{outcome.note}</small>
                          </td>
                          <td>{run.queue_size ?? "—"}</td>
                          <td>{duration(run, text)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <Pagination meta={runs.data.meta} onPageChange={setPage} />
            </>
          )}
        </ListState>
      </section>

      <ConfirmDialog
        open={Boolean(confirming)}
        title={
          confirming?.enabled
            ? text(`关闭 ${confirming?.entity_type} 的托管推进？`, `Switch off hosted driving for ${confirming?.entity_type}?`)
            : text(`开启 ${confirming?.entity_type} 的托管推进？`, `Switch on hosted driving for ${confirming?.entity_type}?`)
        }
        description={
          confirming?.enabled
            ? text(
                "立即生效。已提交的单据不会被撤销，但之后不会再有人自动安排审批——需要你们自己的代理接手。",
                "Takes effect immediately. Nothing already submitted is undone, but no one will assign approvals automatically after this — your own agent takes over.",
              )
            : confirming?.parked_at
              ? text(
                  "这条流程此前因为连续没有推进而暂停。开启会清除暂停状态并重新开始检查——请确认原因已经处理。",
                  "This one stopped after several runs moved nothing. Switching on clears that stop and resumes checking — make sure the cause is fixed.",
                )
              : text(
                  "开启后会按上面的频率检查待安排的单据。",
                  "Checking for unassigned records resumes at the frequency shown above.",
                )
        }
        busy={toggle.isPending}
        error={toggle.isError ? apiErrorMessage(toggle.error) : null}
        confirmLabel={confirming?.enabled ? text("关闭推进", "Switch off") : text("开启推进", "Switch on")}
        onCancel={() => setConfirming(null)}
        onConfirm={() => {
          if (!confirming) return;
          toggle.mutate({ id: confirming.id, enabled: !confirming.enabled });
        }}
      />
    </div>
  );
}
