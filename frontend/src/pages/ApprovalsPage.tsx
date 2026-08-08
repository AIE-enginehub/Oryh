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
        <div><span className="eyebrow">{text("完整审批记录", "Complete approval history")}</span><h2>{text("审批记录", "Approval log")}</h2><p>{text("按最近操作时间查看审批记录；状态变化仍由工作流和业务规则控制。", "Review approval history by most recent action time; workflows and business rules continue to control status changes.")}</p></div>
      </header>
      <div className="activity-banner" role="status"><span className="restricted-mark" aria-hidden="true">i</span><div><strong>{text("只读审计视图", "Read-only audit view")}</strong><span>{text("审批记录只能通过业务审批动作写入，本页面不提供编辑或删除。", "Approval records are written only by business approval actions; this page does not support editing or deletion.")}</span></div></div>

      {approvals.isError && isActivityForbidden(approvals.error) ? (
        <RestrictedState title={text("无法访问审批记录", "Cannot access approval records")} description={text("当前登录身份没有读取审批审计事实的权限。", "The signed-in identity does not have permission to read approval audit facts.")} />
      ) : (
        <section className="data-panel" aria-label={text("审批记录列表", "Approval record list")} aria-busy={approvals.isFetching}>
          <ActivityToolbar
            idPrefix="approval"
            keyword={keyword}
            primary={action}
            entityType={entityType}
            keywordPlaceholder={text("搜索操作者、备注或对象 ID", "Search actor, comment, or object ID")}
            primaryLabel={text("动作", "action")}
            primaryOptions={Object.entries(approvalActionLabels).map(([value, label]) => ({ value, label }))}
            entityOptions={approvalEntityOptions}
            onApply={(filters) => {
              setKeyword(filters.keyword);
              setAction(filters.primary as ActionFilter);
              setEntityType(filters.entityType as EntityFilter);
              setPage(1);
            }}
          />
          {displayNames.isError && <div className="activity-name-warning" role="status">{text("操作者名称解析暂时不可用，当前保留原 approver ID。", "Actor name resolution is temporarily unavailable; the raw approver ID is shown.")}</div>}
          <ListState
            loading={approvals.isPending}
            error={approvals.isError ? apiErrorMessage(approvals.error) : null}
            empty={Boolean(result && result.data.length === 0)}
            emptyTitle={keyword || action || entityType ? text("没有匹配的审批记录", "No matching approval records") : text("还没有审批记录", "No approval records yet")}
            emptyDescription={keyword || action || entityType ? text("尝试调整关键词、动作或对象类型。", "Try changing the keyword, action, or object type.") : text("审批事实会在流程产生提交、批准、退回等动作后出现。", "Approval facts appear after a workflow produces actions such as submission, approval, or return.")}
            onRetry={() => void approvals.refetch()}
          >
            {result && <>
              <div className="table-scroll"><table className="data-table activity-table">
                <thead><tr><th>{text("操作时间", "Action time")}</th><th>{text("关联对象", "Related object")}</th><th>{text("轮次 / 顺序", "Round / sequence")}</th><th>{text("动作", "Action")}</th><th>{text("操作者", "Actor")}</th><th>{text("备注", "Comment")}</th></tr></thead>
                <tbody>{result.data.map((record) => <tr key={record.id}>
                  <td className="due-date">{formatDate(record.acted_at, language)}</td>
                  <td className="entity-reference"><strong>{entityLabels[record.entity_type]}</strong><code title={record.entity_id}>{record.entity_id}</code></td>
                  <td className="mono-cell">{record.round_no} / {record.sequence_no}</td>
                  <td><span className={`approval-action ${record.action}`}>{approvalActionLabels[record.action]}</span></td>
                  <td><strong>{approverName(record.approver_id, names)}</strong>{record.approver_id && approverName(record.approver_id, names) !== record.approver_id && <small className="mono-cell">{record.approver_id}</small>}<small>{record.approver_role || record.source || text("未注明角色", "Role not specified")}</small></td>
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
