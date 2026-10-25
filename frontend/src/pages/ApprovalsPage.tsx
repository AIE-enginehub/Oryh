import { zhCN } from "../locales/zh-CN/console";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  isActivityForbidden,
  listApprovalRecords,
  resolveApprovalDisplayNames,
  type ActivityDisplayNames,
  type ApprovalAction,
  type ApprovalEntityType,
} from "../api/activity";
import { ActivityToolbar } from "../components/activity/ActivityToolbar";
import { useActivityLabels } from "../components/activity/labels";
import { RestrictedState } from "../components/activity/RestrictedState";
import { apiErrorMessage, ListState } from "../components/master-data/ListState";
import { Pagination } from "../components/master-data/Pagination";
import { useI18n } from "../i18n";
import "./activity.css";

const PAGE_SIZE = 20;
type ActionFilter = "" | ApprovalAction;
type EntityFilter = "" | ApprovalEntityType;
const EMPTY_NAMES: ActivityDisplayNames = { employees: {}, actors: {} };

function formatDate(value: string, locale: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function approverName(value: string | null | undefined, names: ActivityDisplayNames): string {
  if (!value) return "—";
  return names.actors[value] || names.employees[value] || value;
}

export function ApprovalsPage() {
  const { language, text } = useI18n();
  const { approvalActionLabels, approvalEntityOptions, entityLabels } = useActivityLabels();
  const [keyword, setKeyword] = useState("");
  const [action, setAction] = useState<ActionFilter>("");
  const [entityType, setEntityType] = useState<EntityFilter>("");
  const [page, setPage] = useState(1);

  const approvals = useQuery({
    queryKey: ["activity", "approval-records", { keyword, action, entityType, page }],
    queryFn: () => listApprovalRecords({
      page,
      size: PAGE_SIZE,
      keyword: keyword || undefined,
      action: action || undefined,
      entity_type: entityType || undefined,
    }),
    placeholderData: keepPreviousData,
  });
  const displayNames = useQuery({
    queryKey: ["activity", "approval-display-names", approvals.data?.data.map((record) => record.approver_id ?? "") ?? []],
    queryFn: () => resolveApprovalDisplayNames(approvals.data!.data),
    enabled: Boolean(approvals.data?.data.some((record) => record.approver_id)),
    retry: false,
  });
  const result = approvals.data;
  const availablePages = result?.meta.pages;
  useEffect(() => {
    if (availablePages !== undefined && page > availablePages) setPage(Math.max(availablePages, 1));
  }, [availablePages, page]);
  const names = displayNames.data ?? EMPTY_NAMES;

  return (
    <div className="activity-page" data-testid="approvals-page">
      <header className="page-intro">
        <div><span className="eyebrow">{text(zhCN.pagesApprovalsPage.completeApprovalHistory, "Complete approval history")}</span><h2>{text(zhCN.pagesApprovalsPage.approvalLog, "Approval log")}</h2><p>{text(zhCN.pagesApprovalsPage.reviewApprovalHistoryByMostRecentActionTimeWorkflows, "Review approval history by most recent action time; workflows and business rules continue to control status changes.")}</p></div>
      </header>
      <div className="activity-banner" role="status"><span className="restricted-mark" aria-hidden="true">i</span><div><strong>{text(zhCN.pagesApprovalsPage.readOnlyAuditView, "Read-only audit view")}</strong><span>{text(zhCN.pagesApprovalsPage.approvalRecordsAreWrittenOnlyByBusinessApprovalActions, "Approval records are written only by business approval actions; this page does not support editing or deletion.")}</span></div></div>

      {approvals.isError && isActivityForbidden(approvals.error) ? (
        <RestrictedState title={text(zhCN.pagesApprovalsPage.cannotAccessApprovalRecords, "Cannot access approval records")} description={text(zhCN.pagesApprovalsPage.theSignedInIdentityDoesNotHavePermissionTo, "The signed-in identity does not have permission to read approval audit facts.")} />
      ) : (
        <section className="data-panel" aria-label={text(zhCN.pagesApprovalsPage.approvalRecordList, "Approval record list")} aria-busy={approvals.isFetching}>
          <ActivityToolbar
            idPrefix="approval"
            keyword={keyword}
            primary={action}
            entityType={entityType}
            keywordPlaceholder={text(zhCN.pagesApprovalsPage.searchActorCommentOrObjectID, "Search actor, comment, or object ID")}
            primaryLabel={text(zhCN.pagesApprovalsPage.action, "action")}
            primaryOptions={Object.entries(approvalActionLabels).map(([value, label]) => ({ value, label }))}
            entityOptions={approvalEntityOptions}
            onApply={(filters) => {
              setKeyword(filters.keyword);
              setAction(filters.primary as ActionFilter);
              setEntityType(filters.entityType as EntityFilter);
              setPage(1);
            }}
          />
          {displayNames.isError && <div className="activity-name-warning" role="status">{text(zhCN.pagesApprovalsPage.actorNameResolutionIsTemporarilyUnavailableTheRawApprover, "Actor name resolution is temporarily unavailable; the raw approver ID is shown.")}</div>}
          <ListState
            loading={approvals.isPending}
            error={approvals.isError ? apiErrorMessage(approvals.error) : null}
            empty={Boolean(result && result.data.length === 0)}
            emptyTitle={keyword || action || entityType ? text(zhCN.pagesApprovalsPage.noMatchingApprovalRecords, "No matching approval records") : text(zhCN.pagesApprovalsPage.noApprovalRecordsYet, "No approval records yet")}
            emptyDescription={keyword || action || entityType ? text(zhCN.pagesApprovalsPage.tryChangingTheKeywordActionOrObjectType, "Try changing the keyword, action, or object type.") : text(zhCN.pagesApprovalsPage.approvalFactsAppearAfterAWorkflowProducesActionsSuch, "Approval facts appear after a workflow produces actions such as submission, approval, or return.")}
            onRetry={() => void approvals.refetch()}
          >
            {result && <>
              <div className="table-scroll"><table className="data-table activity-table">
                <thead><tr><th>{text(zhCN.pagesApprovalsPage.actionTime, "Action time")}</th><th>{text(zhCN.pagesApprovalsPage.relatedObject, "Related object")}</th><th>{text(zhCN.pagesApprovalsPage.roundSequence, "Round / sequence")}</th><th>{text(zhCN.pagesApprovalsPage.action, "Action")}</th><th>{text(zhCN.pagesApprovalsPage.actor, "Actor")}</th><th>{text(zhCN.pagesApprovalsPage.comment, "Comment")}</th></tr></thead>
                <tbody>{result.data.map((record) => <tr key={record.id}>
                  <td className="due-date">{formatDate(record.acted_at, language)}</td>
                  <td className="entity-reference"><strong>{entityLabels[record.entity_type]}</strong><code title={record.entity_id}>{record.entity_id}</code></td>
                  <td className="mono-cell">{record.round_no} / {record.sequence_no}</td>
                  <td><span className={`approval-action ${record.action}`}>{approvalActionLabels[record.action]}</span></td>
                  <td><strong>{approverName(record.approver_id, names)}</strong>{record.approver_id && approverName(record.approver_id, names) !== record.approver_id && <small className="mono-cell">{record.approver_id}</small>}<small>{record.approver_role || record.source || text(zhCN.pagesApprovalsPage.roleNotSpecified, "Role not specified")}</small></td>
                  <td className="approval-comment"><span title={record.comment || undefined}>{record.comment || "—"}</span></td>
                </tr>)}</tbody>
              </table></div>
              <Pagination meta={result.meta} onPageChange={setPage} />
            </>}
          </ListState>
        </section>
      )}
    </div>
  );
}
