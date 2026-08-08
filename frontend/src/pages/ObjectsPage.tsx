import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import {
  BUILTIN_OBJECT_TYPES,
  getObjectDirectory,
  listObjectRecords,
  resolveObjectListDisplayNames,
  type ObjectEntityKind,
  type ObjectEntityType,
  type ObjectTypeSummary,
} from "../api/objects";
import { apiErrorMessage, ListState } from "../components/master-data/ListState";
import { Pagination } from "../components/master-data/Pagination";
import { ObjectRecordTable } from "../components/objects/ObjectRecordTable";
import { useI18n } from "../i18n";
import "./objects.css";

const PAGE_SIZE = 20;
type TypeFilter = "all" | "builtin" | "business_object" | "workflow";

function positivePage(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

function selectionFromParams(kind: string | null, objectType: string): {
  entityKind: ObjectEntityKind;
  entityType: ObjectEntityType;
} | null {
  if (kind === "business_object" && objectType) {
    return { entityKind: "business_object", entityType: "business_object" };
  }
  if (kind === "builtin" && BUILTIN_OBJECT_TYPES.includes(objectType as (typeof BUILTIN_OBJECT_TYPES)[number])) {
    return { entityKind: "builtin", entityType: objectType as ObjectEntityType };
  }
  return null;
}

type LocalText = (chinese: string, english: string) => string;

const BUILTIN_TYPE_LABELS: Partial<Record<ObjectEntityType, [string, string]>> = {
  timesheet_header: ["工时单", "Timesheets"],
  expense_claim: ["报销单", "Expense claims"],
  purchase_request: ["采购申请", "Purchase requests"],
  sales_quotation: ["销售报价", "Sales quotations"],
  sales_order: ["销售订单", "Sales orders"],
  invoice: ["发票", "Invoices"],
  payment: ["收付款", "Payments"],
  billing_account: ["往来账户", "Billing accounts"],
  resource_booking: ["资源预订", "Resource bookings"],
};

function typeTitle(type: ObjectTypeSummary, text: LocalText): string {
  const labels = type.entityKind === "builtin" ? BUILTIN_TYPE_LABELS[type.objectType as ObjectEntityType] : undefined;
  return labels ? text(...labels) : type.title;
}

function builtinStatusLabel(status: string, text: LocalText): string {
  const labels: Record<string, [string, string]> = {
    active: ["启用", "Active"], archived: ["已归档", "Archived"], confirmed: ["已确认", "Confirmed"],
    cancelled: ["已取消", "Cancelled"], draft: ["草稿", "Draft"], submitted: ["已提交", "Submitted"],
    approved: ["已通过", "Approved"], rejected: ["已拒绝", "Rejected"], returned: ["已退回", "Returned"],
    sent: ["已发送", "Sent"], accepted: ["已成交", "Accepted"], declined: ["已谢绝", "Declined"],
    expired: ["已过期", "Expired"], superseded: ["已替代", "Superseded"],
    open: ["进行中", "Open"], completed: ["已完成", "Completed"],
    shipped: ["已发货", "Shipped"], signed: ["已签收", "Signed"],
    in_delivery: ["配送中", "In delivery"], delivered: ["已送达", "Delivered"],
    issued: ["已开具", "Issued"], paid: ["已付款", "Paid"],
    written_off: ["已核销坏账", "Written off"], void: ["已作废", "Void"],
    frozen: ["已冻结", "Frozen"], closed: ["已销户", "Closed"],
  };
  return labels[status] ? text(...labels[status]) : status;
}

function syntheticType(kind: ObjectEntityKind, objectType: string, description: string): ObjectTypeSummary {
  return {
    entityKind: kind,
    objectType,
    title: objectType,
    description,
    status: kind === "builtin" ? "builtin" : "active",
    definitionVersion: null,
    hasWorkflow: false,
    statuses: [],
    count: 0,
  };
}

export function ObjectsPage() {
  const { language, text } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const objectType = searchParams.get("object_type")?.trim() ?? "";
  const selection = selectionFromParams(searchParams.get("kind"), objectType);
  const page = positivePage(searchParams.get("page"));
  const keyword = searchParams.get("keyword") ?? "";
  const status = searchParams.get("status") ?? "";
  const [keywordDraft, setKeywordDraft] = useState(keyword);
  const [typeSearch, setTypeSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");

  useEffect(() => setKeywordDraft(keyword), [keyword]);

  const directory = useQuery({
    queryKey: ["objects", "directory", language],
    queryFn: () => getObjectDirectory(language),
  });
  const records = useQuery({
    queryKey: ["objects", "records", selection?.entityType, objectType, { keyword, status, page }],
    queryFn: () => listObjectRecords({
      entityType: selection!.entityType,
      objectType,
      keyword: keyword || undefined,
      status: status || undefined,
      page,
      size: PAGE_SIZE,
    }),
    enabled: selection !== null,
  });
  const displayNames = useQuery({
    queryKey: ["objects", "display-names", records.data?.data.map((item) => item.record.id) ?? []],
    queryFn: () => resolveObjectListDisplayNames(records.data!.data),
    enabled: Boolean(records.data?.data.length),
    retry: false,
  });

  useEffect(() => {
    if (!records.data || page === records.data.meta.page) return;
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("page", String(records.data!.meta.page));
      return next;
    }, { replace: true });
  }, [page, records.data, setSearchParams]);

  const availableTypes = useMemo(() => {
    const types = [...(directory.data?.types ?? [])];
    if (selection && !types.some((type) => type.entityKind === selection.entityKind && type.objectType === objectType)) {
      types.push(syntheticType(selection.entityKind, objectType, text("此类型来自当前链接，但类型目录中没有对应定义。", "This type came from the current link, but the type directory has no matching definition.")));
    }
    return types;
  }, [directory.data?.types, objectType, selection, text]);

  const selectedType = availableTypes.find((type) =>
    type.entityKind === selection?.entityKind && type.objectType === objectType) ?? null;
  const visibleTypes = availableTypes.filter((type) => {
    const needle = typeSearch.trim().toLocaleLowerCase(language);
    const matchesSearch = !needle || `${type.objectType} ${typeTitle(type, text)}`.toLocaleLowerCase(language).includes(needle);
    const matchesFilter = typeFilter === "all"
      || typeFilter === type.entityKind
      || typeFilter === "workflow" && type.hasWorkflow;
    return matchesSearch && matchesFilter;
  });

  const chooseType = (type: ObjectTypeSummary) => {
    setSearchParams({ kind: type.entityKind, object_type: type.objectType, page: "1" });
  };
  const submitFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      const normalized = keywordDraft.trim();
      if (normalized) next.set("keyword", normalized); else next.delete("keyword");
      next.set("page", "1");
      return next;
    });
  };
  const changeStatus = (nextStatus: string) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (nextStatus) next.set("status", nextStatus); else next.delete("status");
      next.set("page", "1");
      return next;
    });
  };
  const changePage = (nextPage: number) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("page", String(nextPage));
      return next;
    });
  };

  const builtinCount = availableTypes.filter((type) => type.entityKind === "builtin").length;
  const customCount = availableTypes.filter((type) => type.entityKind === "business_object").length;

  return (
    <div className="objects-page" data-testid="objects-page">
      <header className="page-intro">
        <div>
          <span className="eyebrow">Object registry</span>
          <h2>{text("业务对象", "Business objects")}</h2>
          <p>{text("统一查看工作空间内建单据与自定义对象，并下钻流程版本、审批、待办和审计轨迹。", "Browse built-in records and custom objects in one place, then inspect workflow versions, approvals, to-dos, and audit history.")}</p>
        </div>
      </header>

      <div className="object-browser-grid">
        <aside className="data-panel object-type-panel" aria-label={text("对象类型", "Object types")}>
          <div className="object-type-controls">
            <label className="object-type-search">
              <span className="sr-only">{text("搜索对象类型", "Search object types")}</span>
              <input value={typeSearch} onChange={(event) => setTypeSearch(event.target.value)} placeholder={text("搜索对象类型", "Search object types")} />
            </label>
            <div className="object-type-filters" aria-label={text("类型筛选", "Type filters")}>
              {(["all", "builtin", "business_object", "workflow"] as TypeFilter[]).map((filter) => {
                const labels: Record<TypeFilter, string> = { all: text("全部", "All"), builtin: text("内建", "Built-in"), business_object: text("自定义", "Custom"), workflow: text("有流程", "With workflow") };
                return <button className={filter === typeFilter ? "active" : ""} type="button" aria-pressed={filter === typeFilter} onClick={() => setTypeFilter(filter)} key={filter}>{labels[filter]}</button>;
              })}
            </div>
          </div>

          {directory.isPending ? <div className="object-type-state" aria-busy="true"><span className="spinner" />{text("加载类型…", "Loading types…")}</div> :
            directory.isError ? <div className="object-type-state error-state" role="alert"><strong>{text("类型目录加载失败", "Failed to load the type directory")}</strong><span>{apiErrorMessage(directory.error)}</span><button className="button compact" type="button" onClick={() => void directory.refetch()}>{text("重试", "Retry")}</button></div> :
              <div className="object-type-list">
                {visibleTypes.length === 0 ? <div className="object-type-state"><span className="empty-mark">∅</span>{text("没有匹配的对象类型。", "No matching object types.")}</div> : <>
                  {visibleTypes.some((type) => type.entityKind === "builtin") && <div className="object-type-group">{text("内建实体", "Built-in entities")}</div>}
                  {visibleTypes.filter((type) => type.entityKind === "builtin").map((type) => (
                    <button className={`object-type-item ${selectedType === type ? "selected" : ""}`} type="button" aria-pressed={selectedType === type} key={`builtin:${type.objectType}`} onClick={() => chooseType(type)}>
                      <span className="object-type-dot builtin" /><span><strong>{typeTitle(type, text)}</strong><code>{type.objectType}</code></span>
                      {type.hasWorkflow && <small>{text("流程", "Workflow")}</small>}
                      <b>{type.count}</b>
                    </button>
                  ))}
                  {visibleTypes.some((type) => type.entityKind === "business_object") && <div className="object-type-group">{text("自定义类型", "Custom types")}</div>}
                  {visibleTypes.filter((type) => type.entityKind === "business_object").map((type) => (
                    <button className={`object-type-item ${selectedType === type ? "selected" : ""}`} type="button" aria-pressed={selectedType === type} key={`custom:${type.objectType}`} onClick={() => chooseType(type)}>
                      <span className="object-type-dot custom" /><span><strong>{type.title}</strong><code>{type.objectType}</code></span>
                      {type.hasWorkflow && <small>{text("流程", "Workflow")}</small>}
                      <b>{type.count}</b>
                    </button>
                  ))}
                </>}
              </div>}
          <footer className="object-type-footer">{text(`${builtinCount} 个内建 · ${customCount} 个自定义`, `${builtinCount} built-in · ${customCount} custom`)}</footer>
        </aside>

        <main className="object-record-workspace">
          {!selection ? (
            <section className="data-panel object-placeholder">
              <span className="object-placeholder-mark" aria-hidden="true">◎</span>
              <h3>{text("选择一个对象类型", "Select an object type")}</h3>
              <p>{text("从左侧类型目录开始。记录列表仅展示当前工作空间和所选业务类型的内容。", "Start with the type directory on the left. Records show only the current workspace and selected business type.")}</p>
            </section>
          ) : (
            <section className="data-panel object-record-panel" aria-label={text(`${selectedType ? typeTitle(selectedType, text) : objectType} 记录`, `${selectedType ? typeTitle(selectedType, text) : objectType} records`)}>
              <header className="object-workspace-header">
                <div><span className="eyebrow">{selection.entityKind === "builtin" ? "Built-in entity" : "Business object"}</span><h3>{selectedType ? typeTitle(selectedType, text) : objectType}</h3><code>{objectType}</code></div>
                <span className="object-record-count">{records.data ? text(`${records.data.meta.total} 条记录`, `${records.data.meta.total} records`) : text("正在统计", "Counting…")}</span>
              </header>
              <form className="object-filter-bar" onSubmit={submitFilters}>
                <label><span className="sr-only">{text("搜索记录", "Search records")}</span><input type="search" value={keywordDraft} onChange={(event) => setKeywordDraft(event.target.value)} placeholder={text("搜索标题、ID 或关键字段", "Search title, ID, or key fields")} /></label>
                <label><span>{text("状态", "Status")}</span><select aria-label={text("状态", "Status")} value={status} onChange={(event) => changeStatus(event.target.value)}>
                  <option value="">{text("全部状态", "All statuses")}</option>
                  {selectedType?.statuses.map((option) => <option value={option} key={option}>{selectedType.entityKind === "builtin" ? builtinStatusLabel(option, text) : option}</option>)}
                  {status && !selectedType?.statuses.includes(status) && <option value={status}>{selectedType?.entityKind === "builtin" ? builtinStatusLabel(status, text) : status}</option>}
                </select></label>
                <button className="button" type="submit">{text("筛选", "Filter")}</button>
                {(keyword || status) && <button className="button quiet" type="button" onClick={() => {
                  setKeywordDraft("");
                  setSearchParams({ kind: selection.entityKind, object_type: objectType, page: "1" });
                }}>{text("清除", "Clear")}</button>}
              </form>
              {records.isFetching && !records.isPending && <div className="object-refreshing" role="status">{text("正在更新结果…", "Updating results…")}</div>}
              {displayNames.isError && <div className="object-refreshing" role="status">{text("名称解析暂时不可用，当前显示记录 ID。", "Name resolution is temporarily unavailable; record IDs are shown instead.")}</div>}
              <ListState
                loading={records.isPending}
                error={records.isError ? apiErrorMessage(records.error) : null}
                empty={records.data?.data.length === 0}
                emptyTitle={text("没有匹配记录", "No matching records")}
                emptyDescription={text("调整关键词或状态筛选后重试。", "Change the keyword or status filter and try again.")}
                onRetry={() => void records.refetch()}
              >
                {records.data && <>
                  <ObjectRecordTable records={records.data.data} objectType={objectType} employees={displayNames.data?.employees ?? {}} actors={displayNames.data?.actors ?? {}} />
                  <Pagination meta={records.data.meta} onPageChange={changePage} />
                </>}
              </ListState>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
