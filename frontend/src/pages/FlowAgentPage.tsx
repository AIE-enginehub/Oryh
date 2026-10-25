import { zhCN } from "../locales/zh-CN/console";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  clearFlowSubscriptionPark,
  driverState,
  getFlowRunnerAvailability,
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
  if (!run.finished_at) return text(zhCN.pagesFlowAgentPage.running, "running");
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
    ? text(zhCN.pagesFlowAgentPage.stillWaiting(`${remaining}`), `, ${remaining} still waiting`)
    : "";

  if (run.status === "running") {
    return isStalled(run)
      ? { tone: "failed", label: text(zhCN.pagesFlowAgentPage.noReport, "No report"), note: text(zhCN.pagesFlowAgentPage.thisRunStartedAndNeverReportedFinishingItMay, "This run started and never reported finishing; it may have died.") }
      : { tone: "running", label: text(zhCN.pagesFlowAgentPage.running, "Running"), note: text(zhCN.pagesFlowAgentPage.inProgress, "In progress.") };
  }
  if (run.status === "failed") {
    return { tone: "failed", label: text(zhCN.pagesFlowAgentPage.failed, "Failed"), note: run.error || text(zhCN.pagesFlowAgentPage.noReasonRecorded, "No reason recorded.") };
  }
  if (run.status === "skipped") {
    return { tone: "skipped", label: text(zhCN.pagesFlowAgentPage.nothingToDo, "Nothing to do"), note: text(zhCN.pagesFlowAgentPage.lookedAtTheQueueAndFoundNothingWaiting, "Looked at the queue and found nothing waiting.") };
  }
  if (advanced === 0) {
    return {
      tone: "stuck",
      label: text(zhCN.pagesFlowAgentPage.movedNothing, "Moved nothing"),
      note: text(
        zhCN.pagesFlowAgentPage.foundRecordSAndMovedNoneUsuallyAnApproval(`${run.queue_size ?? 0}`),
        `Found ${run.queue_size ?? 0} record(s) and moved none — usually an approval flow routing nowhere, or an approver with no employee record.`,
      ),
    };
  }
  return {
    tone: "succeeded",
    label: text(zhCN.pagesFlowAgentPage.advanced(`${advanced}`), `Advanced ${advanced}`),
    note: wasCapped(run)
      ? text(zhCN.pagesFlowAgentPage.cappedAtThisRun(`${run.detail.batch_limit}`, `${more}`), `Capped at ${run.detail.batch_limit} this run${more}.`)
      : text(zhCN.pagesFlowAgentPage.handledWhatThisPassFound(`${more}`), `Handled what this pass found${more}.`),
  };
}

const STATE_TONE: Record<DriverState, string> = {
  parked: "failed",
  silent: "failed",
  paused: "completed",
  off: "completed",
  starting: "running",
  running: "open",
};

function stateLabel(state: DriverState, text: Text): string {
  switch (state) {
    case "parked": return text(zhCN.pagesFlowAgentPage.stopped, "Stopped");
    case "silent": return text(zhCN.pagesFlowAgentPage.notRunning, "Not running");
    case "off": return text(zhCN.pagesFlowAgentPage.off, "Off");
    case "paused": return text(zhCN.pagesFlowAgentPage.pausedByORYH, "Paused by ORYH");
    case "starting": return text(zhCN.pagesFlowAgentPage.starting, "Starting");
    default: return text(zhCN.pagesFlowAgentPage.running2, "Running");
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
  const availability = useQuery({
    queryKey: ["flow-runner-availability"],
    queryFn: getFlowRunnerAvailability,
  });
  // Unknown reads as on: while the tenant record is still loading, the rows
  // should not flash "paused" at a workspace that is being driven.
  const platformEnabled = availability.data?.flow_runner_enabled !== false;
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

  const clearPark = useMutation({
    mutationFn: (id: string) => clearFlowSubscriptionPark(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["flow-subscriptions"] });
      void queryClient.invalidateQueries({ queryKey: ["flow-runs"] });
    },
  });

  const rows = subscriptions.data ?? [];
  // Both mean "enabled, and yet nothing is being driven" — the one case that has
  // to interrupt the reader, because only a person resolves either.
  const parked = rows.filter((row) => row.parked_at);
  const stateOf = (row: FlowSubscription): DriverState =>
    driverState(row, Date.now(), platformEnabled);
  const silent = rows.filter((row) => stateOf(row) === "silent");

  return (
    <div className="page flow-agent-page">
      <header className="page-header">
        <div>
          <h1>{text(zhCN.pagesFlowAgentPage.flowAgent, "Flow agent")}</h1>
          <p>
            {text(
              zhCN.pagesFlowAgentPage.approvalDrivingOperatedByORYHOnYourBehalfIt,
              zhCN.pagesFlowAgentPage.message,
            )}
          </p>
        </div>
      </header>

      {!platformEnabled && (
        <section className="flow-park-banner" role="status">
          <h2>{text(zhCN.pagesFlowAgentPage.oRYHHasPausedHostedDrivingForYourCompany, "ORYH has paused hosted driving for your company")}</h2>
          <ul>
            <li>
              <span>
                {text(
                  zhCN.pagesFlowAgentPage.everythingBelowStaysEnrolledAsItIsButThe,
                  "Everything below stays enrolled as it is, but the hosted agent will not advance any document until ORYH resumes. Nothing on your side caused this, and none of your switches need changing.",
                )}
              </span>
              <small>{text(zhCN.pagesFlowAgentPage.contactUsForTheReasonAndWhenItResumes, "Contact us for the reason and when it resumes.")}</small>
            </li>
          </ul>
        </section>
      )}

      {(parked.length > 0 || silent.length > 0) && (
        <section className="flow-park-banner" role="status">
          <h2>{text(zhCN.pagesFlowAgentPage.nothingIsDrivingThese, "Nothing is driving these")}</h2>
          <ul>
            {parked.map((row) => (
              <li key={row.id}>
                <strong>{row.entity_type}</strong>
                <span>{row.parked_reason}</span>
                <small>
                  {text(
                    zhCN.pagesFlowAgentPage.usuallyTheApprovalFlowForThisFamilyDoesNot,
                    "Usually the approval flow for this family does not say where these go: publishing its next version resumes driving by itself. If the cause was elsewhere, fix it and press Try again.",
                  )}
                </small>
                {row.enabled && (
                  <button
                    className="text-action"
                    type="button"
                    disabled={clearPark.isPending}
                    onClick={() => clearPark.mutate(row.id)}
                  >
                    {text(zhCN.pagesFlowAgentPage.tryAgain, "Try again")}
                  </button>
                )}
                {clearPark.isError && clearPark.variables === row.id && (
                  <span className="form-error">{apiErrorMessage(clearPark.error)}</span>
                )}
              </li>
            ))}
            {silent.map((row) => (
              <li key={row.id}>
                <strong>{row.entity_type}</strong>
                <span>
                  {row.last_run_at
                    ? text(
                        zhCN.pagesFlowAgentPage.thisOneIsSwitchedOnButHasNotRun,
                        "This one is switched on but has not run in a long time — the driving service itself may be down.",
                      )
                    : text(
                        zhCN.pagesFlowAgentPage.thisOneIsSwitchedOnButHasNeverRun,
                        "This one is switched on but has never run — the driving service may not have picked it up.",
                      )}
                </span>
                <small>{text(zhCN.pagesFlowAgentPage.thisIsNotSomethingYouCanFixContactUs, "This is not something you can fix; contact us.")}</small>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="page-section">
        <h2>{text(zhCN.pagesFlowAgentPage.whatIsDriven, "What is driven")}</h2>
        <ListState
          loading={subscriptions.isPending}
          error={subscriptions.isError ? apiErrorMessage(subscriptions.error) : null}
          empty={rows.length === 0}
          emptyTitle={text(zhCN.pagesFlowAgentPage.nothingIsHosted, "Nothing is hosted")}
          emptyDescription={text(
            zhCN.pagesFlowAgentPage.allApprovalDrivingIsCurrentlyDoneByYourOwn,
            "All approval driving is currently done by your own agent. Contact us to hand a document type over.",
          )}
          onRetry={() => void subscriptions.refetch()}
        >
          <div className="table-scroll">
            <table className="data-table activity-table">
              <thead>
                <tr>
                  <th>{text(zhCN.pagesFlowAgentPage.documentType, "Document type")}</th>
                  <th>{text(zhCN.pagesFlowAgentPage.driverSkill, "Driver skill")}</th>
                  <th>{text(zhCN.pagesFlowAgentPage.checkedEvery, "Checked every")}</th>
                  <th>{text(zhCN.pagesFlowAgentPage.state, "State")}</th>
                  <th><span className="sr-only">{text(zhCN.pagesFlowAgentPage.actions, "Actions")}</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className={
                    ["parked", "silent"].includes(stateOf(row)) ? "flow-row-parked" : undefined
                  }>
                    <td><strong>{row.entity_type}</strong></td>
                    <td><code>{row.driver_skill}</code></td>
                    <td>{text(zhCN.pagesFlowAgentPage.s(`${row.cadence_seconds}`), `${row.cadence_seconds}s`)}</td>
                    <td>
                      <span className={`activity-status ${STATE_TONE[stateOf(row)]}`}>
                        {stateLabel(stateOf(row), text)}
                      </span>
                    </td>
                    <td className="row-actions">
                      <button
                        className="text-action"
                        type="button"
                        onClick={() => { toggle.reset(); setConfirming(row); }}
                      >
                        {row.enabled ? text(zhCN.pagesFlowAgentPage.switchOff, "Switch off") : text(zhCN.pagesFlowAgentPage.switchOn, "Switch on")}
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
        <h2>{text(zhCN.pagesFlowAgentPage.runHistory, "Run history")}</h2>
        <p className="section-hint">
          {text(
            zhCN.pagesFlowAgentPage.everyCheckLeavesARowTheBusinessWritesThemselves,
            "Every check leaves a row. The business writes themselves are in the audit log; this is the envelope around them — when it ran, what it found, what it moved.",
          )}
        </p>
        <ListState
          loading={runs.isPending}
          error={runs.isError ? apiErrorMessage(runs.error) : null}
          empty={Boolean(runs.data && runs.data.data.length === 0)}
          emptyTitle={text(zhCN.pagesFlowAgentPage.noRunsYet, "No runs yet")}
          emptyDescription={text(
            zhCN.pagesFlowAgentPage.theFirstCheckAfterEnrolmentWillAppearHere,
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
                      <th>{text(zhCN.pagesFlowAgentPage.started, "Started")}</th>
                      <th>{text(zhCN.pagesFlowAgentPage.documentType, "Document type")}</th>
                      <th>{text(zhCN.pagesFlowAgentPage.outcome, "Outcome")}</th>
                      <th>{text(zhCN.pagesFlowAgentPage.found, "Found")}</th>
                      <th>{text(zhCN.pagesFlowAgentPage.took, "Took")}</th>
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
            ? text(zhCN.pagesFlowAgentPage.switchOffHostedDrivingFor(`${confirming?.entity_type}`), `Switch off hosted driving for ${confirming?.entity_type}?`)
            : text(zhCN.pagesFlowAgentPage.switchOnHostedDrivingFor(`${confirming?.entity_type}`), `Switch on hosted driving for ${confirming?.entity_type}?`)
        }
        description={
          confirming?.enabled
            ? text(
                zhCN.pagesFlowAgentPage.takesEffectImmediatelyNothingAlreadySubmittedIsUndoneBut,
                "Takes effect immediately. Nothing already submitted is undone, but no one will assign approvals automatically after this — your own agent takes over.",
              )
            : confirming?.parked_at
              ? text(
                  zhCN.pagesFlowAgentPage.thisOneStoppedAfterSeveralRunsMovedNothingSwitching,
                  "This one stopped after several runs moved nothing. Switching on clears that stop and resumes checking — make sure the cause is fixed.",
                )
              : text(
                  zhCN.pagesFlowAgentPage.checkingForUnassignedRecordsResumesAtTheFrequencyShown,
                  "Checking for unassigned records resumes at the frequency shown above.",
                )
        }
        busy={toggle.isPending}
        error={toggle.isError ? apiErrorMessage(toggle.error) : null}
        confirmLabel={confirming?.enabled ? text(zhCN.pagesFlowAgentPage.switchOff2, "Switch off") : text(zhCN.pagesFlowAgentPage.switchOn2, "Switch on")}
        onCancel={() => setConfirming(null)}
        onConfirm={() => {
          if (!confirming) return;
          toggle.mutate({ id: confirming.id, enabled: !confirming.enabled });
        }}
      />
    </div>
  );
}
