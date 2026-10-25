import { zhCN } from "../locales/zh-CN/console";
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
        <h2>{text(zhCN.pagesObjectDetailPage.thisObjectLinkIsNotValid, "This object link is not valid")}</h2>
        <p>{text(zhCN.pagesObjectDetailPage.theObjectEntityTypeOrRecordIDIsIncomplete, "The object entity type or record ID is incomplete. Return to the object directory and choose again.")}</p>
        <Link className="button" to="/objects">{text(zhCN.pagesObjectDetailPage.backToBusinessObjects, "Back to business objects")}</Link>
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
          <Link className="object-back-link" to={backTo}>{text(zhCN.pagesObjectDetailPage.backToObjectRecords, "← Back to object records")}</Link>
          <span className="eyebrow">Object trace</span>
          <h2>{detail.data?.heading || text(zhCN.pagesObjectDetailPage.loadingObject, "Loading object…")}</h2>
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
          <section className="object-detail-summary" aria-label={text(zhCN.pagesObjectDetailPage.objectSummary, "Object summary")}>
            <div><span>{text(zhCN.pagesObjectDetailPage.currentStatus, "Current status")}</span><ObjectStatus status={recordStatus(detail.data)} translate={detail.data.entityKind === "builtin"} /></div>
            <div><span>{text(zhCN.pagesObjectDetailPage.objectType, "Object type")}</span><strong>{detail.data.objectType}</strong><small>{detail.data.entityKind === "builtin" ? text(zhCN.pagesObjectDetailPage.builtInEntity, "Built-in entity") : text(zhCN.pagesObjectDetailPage.customObject, "Custom object")}</small></div>
            <div><span>{text(zhCN.pagesObjectDetailPage.ownerCreator, "Owner / Creator")}</span><strong>{recordOwner(detail.data)}</strong></div>
            <div><span>{text(zhCN.pagesObjectDetailPage.lastUpdated, "Last updated")}</span><strong>{recordUpdated(detail.data, language)}</strong></div>
          </section>

          {detail.data.issues.length > 0 && <section className="object-detail-issues" role="status">
            <strong>{text(zhCN.pagesObjectDetailPage.someRelatedInformationCouldNotBeLoaded, "Some related information could not be loaded")}</strong>
            <p>{text(zhCN.pagesObjectDetailPage.thePrimaryRecordIsStillAvailableEmptySectionsBelow, "The primary record is still available. Empty sections below do not necessarily mean the business data is missing.")}</p>
            <ul>{detail.data.issues.map((issue) => {
              const labels: Record<string, string> = {
                [zhCN.pagesObjectDetailPage.businessRules]: text(zhCN.pagesObjectDetailPage.businessRules, "Business rules"),
                [zhCN.pagesObjectDetailPage.approvalHistory]: text(zhCN.pagesObjectDetailPage.approvalHistory, "Approval history"),
                [zhCN.pagesObjectDetailPage.todos]: text(zhCN.pagesObjectDetailPage.todos, "Todos"),
                [zhCN.pagesObjectDetailPage.auditTrail]: text(zhCN.pagesObjectDetailPage.auditTrail, "Audit trail"),
                [zhCN.pagesObjectDetailPage.relatedObjects]: text(zhCN.pagesObjectDetailPage.relatedObjects, "Related objects"),
                [zhCN.pagesObjectDetailPage.displayNames]: text(zhCN.pagesObjectDetailPage.displayNames, "Display names"),
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
