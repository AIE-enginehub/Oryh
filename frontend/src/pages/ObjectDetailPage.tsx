import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { getObjectDetail, isObjectEntityType, type ObjectDetail } from "../api/objects";
import { apiErrorMessage, ListState } from "../components/master-data/ListState";
import { ObjectDetailSections, ObjectRecordDetail } from "../components/objects/ObjectDetailSections";
import { formatDateTime, ObjectStatus } from "../components/objects/ObjectRecordTable";
import { useI18n } from "../i18n";
import "./objects.css";

function recordStatus(detail: ObjectDetail): string {
  return detail.subject.record.status;
}

function recordOwner(detail: ObjectDetail): string {
  const subject = detail.subject;
  if (subject.entityType === "timesheet_header" || subject.entityType === "expense_claim" || subject.entityType === "purchase_request" || subject.entityType === "sales_quotation" || subject.entityType === "sales_order" || subject.entityType === "invoice" || subject.entityType === "payment") {
    return detail.employees[subject.record.employee_id] || subject.record.employee_id;
  }
  if (subject.entityType === "resource_booking") {
    return detail.employees[subject.record.booked_by_employee_id] || subject.record.booked_by_employee_id;
  }
  if (subject.entityType === "billing_account") {
    // the owner is a party, not necessarily a person
    return subject.record.owner_name_snapshot || "—";
  }
  return subject.record.created_by ? detail.actors[subject.record.created_by] || subject.record.created_by : "—";
}

function recordUpdated(detail: ObjectDetail, locale: string): string {
  return formatDateTime(detail.subject.record.updated_at || detail.subject.record.created_at, locale);
}

export function ObjectDetailPage() {
  const { language, text } = useI18n();
  const { entityType, recordId } = useParams<{ entityType: string; recordId: string }>();
  const [searchParams] = useSearchParams();
  const validEntityType = isObjectEntityType(entityType) ? entityType : null;
  const decodedRecordId = recordId ? decodeURIComponent(recordId) : "";
  const detail = useQuery({
    queryKey: ["objects", "detail", validEntityType, decodedRecordId, language],
    queryFn: () => getObjectDetail(validEntityType!, decodedRecordId, language),
    enabled: validEntityType !== null && decodedRecordId !== "",
  });

  if (!validEntityType || !decodedRecordId) {
    return (
      <section className="data-panel object-invalid-detail" role="alert">
        <span className="eyebrow">Invalid object</span>
        <h2>{text("无法识别这条对象链接", "This object link is not valid")}</h2>
        <p>{text("对象实体类型或记录 ID 不完整，请返回对象目录重新选择。", "The object entity type or record ID is incomplete. Return to the object directory and choose again.")}</p>
        <Link className="button" to="/objects">{text("返回业务对象", "Back to business objects")}</Link>
      </section>
    );
  }

  const objectTypeHint = searchParams.get("object_type")
    || detail.data?.objectType
    || (validEntityType === "business_object" ? "" : validEntityType);
  const kindHint = searchParams.get("kind") || (validEntityType === "business_object" ? "business_object" : "builtin");
  const backSearch = new URLSearchParams({ kind: kindHint, object_type: objectTypeHint });
  const backTo = objectTypeHint ? `/objects?${backSearch.toString()}` : "/objects";

  return (
    <div className="object-detail-page" data-testid="object-detail-page">
      <header className="object-detail-intro">
        <div>
          <Link className="object-back-link" to={backTo}>{text("← 返回对象记录", "← Back to object records")}</Link>
          <span className="eyebrow">Object trace</span>
          <h2>{detail.data?.heading || text("正在加载对象…", "Loading object…")}</h2>
          <p><code>{validEntityType}</code><span>·</span><code>{decodedRecordId}</code></p>
        </div>
      </header>

      <ListState
        loading={detail.isPending}
        error={detail.isError ? apiErrorMessage(detail.error) : null}
        empty={false}
        emptyTitle=""
        emptyDescription=""
        onRetry={() => void detail.refetch()}
      >
        {detail.data && <div className="object-detail-stack">
          <section className="object-detail-summary" aria-label={text("对象摘要", "Object summary")}>
            <div><span>{text("当前状态", "Current status")}</span><ObjectStatus status={recordStatus(detail.data)} translate={detail.data.entityKind === "builtin"} /></div>
            <div><span>{text("对象类型", "Object type")}</span><strong>{detail.data.objectType}</strong><small>{detail.data.entityKind === "builtin" ? text("内建实体", "Built-in entity") : text("自定义对象", "Custom object")}</small></div>
            <div><span>{text("负责人 / 创建者", "Owner / Creator")}</span><strong>{recordOwner(detail.data)}</strong></div>
            <div><span>{text("最近更新", "Last updated")}</span><strong>{recordUpdated(detail.data, language)}</strong></div>
          </section>

          {detail.data.issues.length > 0 && <section className="object-detail-issues" role="status">
            <strong>{text("部分关联信息未能加载", "Some related information could not be loaded")}</strong>
            <p>{text("主记录仍可查看；以下区块显示为空不代表业务数据不存在。", "The primary record is still available. Empty sections below do not necessarily mean the business data is missing.")}</p>
            <ul>{detail.data.issues.map((issue) => {
              const labels: Record<string, string> = {
                "流程版本": text("流程版本", "Workflow versions"),
                "审批记录": text("审批记录", "Approval history"),
                "待办": text("待办", "Todos"),
                "审计轨迹": text("审计轨迹", "Audit trail"),
                "关联对象": text("关联对象", "Related objects"),
                "人员名称": text("人员名称", "Display names"),
              };
              return <li key={`${issue.section}:${issue.message}`}><b>{labels[issue.section] || issue.section}</b>{text("：", ": ")}{issue.message}</li>;
            })}</ul>
          </section>}

          <ObjectRecordDetail detail={detail.data} />
          <ObjectDetailSections detail={detail.data} />
        </div>}
      </ListState>
    </div>
  );
}
