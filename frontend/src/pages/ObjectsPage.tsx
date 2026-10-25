import { zhCN } from "../locales/zh-CN/console";
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
  timesheet_header: [zhCN.pagesObjectsPage.title4, "Timesheets"],
  expense_claim: [zhCN.pagesObjectsPage.title3, "Expense claims"],
  purchase_request: [zhCN.pagesObjectsPage.title42, "Purchase requests"],
  sales_quotation: [zhCN.pagesObjectsPage.title5, "Sales quotations"],
  sales_order: [zhCN.pagesObjectsPage.title6, "Sales orders"],
  invoice: [zhCN.pagesObjectsPage.message6, "Invoices"],
  payment: [zhCN.pagesObjectsPage.message7, "Payments"],
  billing_account: [zhCN.pagesObjectsPage.message8, "Billing accounts"],
  resource_booking: [zhCN.pagesObjectsPage.title7, "Resource bookings"],
};

function typeTitle(type: ObjectTypeSummary, text: LocalText): string {
  const labels = type.entityKind === "builtin" ? BUILTIN_TYPE_LABELS[type.objectType as ObjectEntityType] : undefined;
  return labels ? text(...labels) : type.title;
}

function builtinStatusLabel(status: string, text: LocalText): string {
  const labels: Record<string, [string, string]> = {
    active: [zhCN.pagesObjectsPage.active, "Active"], archived: [zhCN.pagesObjectsPage.archived, "Archived"], confirmed: [zhCN.pagesObjectsPage.message12, "Confirmed"],
    cancelled: [zhCN.pagesObjectsPage.message13, "Cancelled"], draft: [zhCN.pagesObjectsPage.draft, "Draft"], submitted: [zhCN.pagesObjectsPage.submitted, "Submitted"],
    approved: [zhCN.pagesObjectsPage.message16, "Approved"], rejected: [zhCN.pagesObjectsPage.rejected, "Rejected"], returned: [zhCN.pagesObjectsPage.returned, "Returned"],
    sent: [zhCN.pagesObjectsPage.message19, "Sent"], accepted: [zhCN.pagesObjectsPage.message20, "Accepted"], declined: [zhCN.pagesObjectsPage.message21, "Declined"],
    expired: [zhCN.pagesObjectsPage.message22, "Expired"], superseded: [zhCN.pagesObjectsPage.superseded, "Superseded"],
    open: [zhCN.pagesObjectsPage.running, "Open"], completed: [zhCN.pagesObjectsPage.completed, "Completed"],
    shipped: [zhCN.pagesObjectsPage.message26, "Shipped"], signed: [zhCN.pagesObjectsPage.message27, "Signed"],
    in_delivery: [zhCN.pagesObjectsPage.message28, "In delivery"], delivered: [zhCN.pagesObjectsPage.message29, "Delivered"],
    issued: [zhCN.pagesObjectsPage.message30, "Issued"], paid: [zhCN.pagesObjectsPage.message31, "Paid"],
    written_off: [zhCN.pagesObjectsPage.message32, "Written off"], void: [zhCN.pagesObjectsPage.message33, "Void"],
    frozen: [zhCN.pagesObjectsPage.message34, "Frozen"], closed: [zhCN.pagesObjectsPage.message35, "Closed"],
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
      types.push(syntheticType(selection.entityKind, objectType, text(zhCN.pagesObjectsPage.thisTypeCameFromTheCurrentLinkButThe, "This type came from the current link, but the type directory has no matching definition.")));
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
          <h2>{text(zhCN.pagesObjectsPage.businessObjects, "Business objects")}</h2>
          <p>{text(zhCN.pagesObjectsPage.browseBuiltInRecordsAndCustomObjectsInOne, "Browse built-in records and custom objects in one place, then inspect business rules, approvals, to-dos, and audit history.")}</p>
        </div>
      </header>

      <div className="object-browser-grid">
        <aside className="data-panel object-type-panel" aria-label={text(zhCN.pagesObjectsPage.objectTypes, "Object types")}>
          <div className="object-type-controls">
            <label className="object-type-search">
              <span className="sr-only">{text(zhCN.pagesObjectsPage.searchObjectTypes, "Search object types")}</span>
              <input value={typeSearch} onChange={(event) => setTypeSearch(event.target.value)} placeholder={text(zhCN.pagesObjectsPage.searchObjectTypes, "Search object types")} />
            </label>
            <div className="object-type-filters" aria-label={text(zhCN.pagesObjectsPage.typeFilters, "Type filters")}>
              {(["all", "builtin", "business_object", "workflow"] as TypeFilter[]).map((filter) => {
                const labels: Record<TypeFilter, string> = { all: text(zhCN.pagesObjectsPage.all, "All"), builtin: text(zhCN.pagesObjectsPage.builtIn, "Built-in"), business_object: text(zhCN.pagesObjectsPage.custom, "Custom"), workflow: text(zhCN.pagesObjectsPage.withApprovalFlow, "With approval flow") };
                return <button className={filter === typeFilter ? "active" : ""} type="button" aria-pressed={filter === typeFilter} onClick={() => setTypeFilter(filter)} key={filter}>{labels[filter]}</button>;
              })}
            </div>
          </div>

          {directory.isPending ? <div className="object-type-state" aria-busy="true"><span className="spinner" />{text(zhCN.pagesObjectsPage.loadingTypes, "Loading types…")}</div> :
            directory.isError ? <div className="object-type-state error-state" role="alert"><strong>{text(zhCN.pagesObjectsPage.failedToLoadTheTypeDirectory, "Failed to load the type directory")}</strong><span>{apiErrorMessage(directory.error)}</span><button className="button compact" type="button" onClick={() => void directory.refetch()}>{text(zhCN.pagesObjectsPage.retry, "Retry")}</button></div> :
              <div className="object-type-list">
                {visibleTypes.length === 0 ? <div className="object-type-state"><span className="empty-mark">∅</span>{text(zhCN.pagesObjectsPage.noMatchingObjectTypes, "No matching object types.")}</div> : <>
                  {visibleTypes.some((type) => type.entityKind === "builtin") && <div className="object-type-group">{text(zhCN.pagesObjectsPage.builtInEntities, "Built-in entities")}</div>}
                  {visibleTypes.filter((type) => type.entityKind === "builtin").map((type) => (
                    <button className={`object-type-item ${selectedType === type ? "selected" : ""}`} type="button" aria-pressed={selectedType === type} key={`builtin:${type.objectType}`} onClick={() => chooseType(type)}>
                      <span className="object-type-dot builtin" /><span><strong>{typeTitle(type, text)}</strong><code>{type.objectType}</code></span>
                      {type.hasWorkflow && <small>{text(zhCN.pagesObjectsPage.workflow, "Workflow")}</small>}
                      <b>{type.count}</b>
                    </button>
                  ))}
                  {visibleTypes.some((type) => type.entityKind === "business_object") && <div className="object-type-group">{text(zhCN.pagesObjectsPage.customTypes, "Custom types")}</div>}
                  {visibleTypes.filter((type) => type.entityKind === "business_object").map((type) => (
                    <button className={`object-type-item ${selectedType === type ? "selected" : ""}`} type="button" aria-pressed={selectedType === type} key={`custom:${type.objectType}`} onClick={() => chooseType(type)}>
                      <span className="object-type-dot custom" /><span><strong>{type.title}</strong><code>{type.objectType}</code></span>
                      {type.hasWorkflow && <small>{text(zhCN.pagesObjectsPage.workflow, "Workflow")}</small>}
                      <b>{type.count}</b>
                    </button>
                  ))}
                </>}
              </div>}
          <footer className="object-type-footer">{text(zhCN.pagesObjectsPage.builtInCustom(`${builtinCount}`, `${customCount}`), `${builtinCount} built-in · ${customCount} custom`)}</footer>
        </aside>

        <div className="object-record-workspace">
          {!selection ? (
            <section className="data-panel object-placeholder">
              <span className="object-placeholder-mark" aria-hidden="true">◎</span>
              <h3>{text(zhCN.pagesObjectsPage.selectAnObjectType, "Select an object type")}</h3>
              <p>{text(zhCN.pagesObjectsPage.startWithTheTypeDirectoryOnTheLeftRecords, "Start with the type directory on the left. Records show only the current workspace and selected business type.")}</p>
            </section>
          ) : (
            <section className="data-panel object-record-panel" aria-label={text(zhCN.pagesObjectsPage.records(`${selectedType ? typeTitle(selectedType, text) : objectType}`), `${selectedType ? typeTitle(selectedType, text) : objectType} records`)}>
              <header className="object-workspace-header">
                <div><span className="eyebrow">{selection.entityKind === "builtin" ? "Built-in entity" : "Business object"}</span><h3>{selectedType ? typeTitle(selectedType, text) : objectType}</h3><code>{objectType}</code></div>
                <span className="object-record-count">{records.data ? text(zhCN.pagesObjectsPage.records2(`${records.data.meta.total}`), `${records.data.meta.total} records`) : text(zhCN.pagesObjectsPage.counting, "Counting…")}</span>
              </header>
              <form className="object-filter-bar" onSubmit={submitFilters}>
                <label><span className="sr-only">{text(zhCN.pagesObjectsPage.searchRecords, "Search records")}</span><input type="search" value={keywordDraft} onChange={(event) => setKeywordDraft(event.target.value)} placeholder={text(zhCN.pagesObjectsPage.searchTitleIDOrKeyFields, "Search title, ID, or key fields")} /></label>
                <label><span>{text(zhCN.pagesObjectsPage.status, "Status")}</span><select aria-label={text(zhCN.pagesObjectsPage.status, "Status")} value={status} onChange={(event) => changeStatus(event.target.value)}>
                  <option value="">{text(zhCN.pagesObjectsPage.allStatuses, "All statuses")}</option>
                  {selectedType?.statuses.map((option) => <option value={option} key={option}>{selectedType.entityKind === "builtin" ? builtinStatusLabel(option, text) : option}</option>)}
                  {status && !selectedType?.statuses.includes(status) && <option value={status}>{selectedType?.entityKind === "builtin" ? builtinStatusLabel(status, text) : status}</option>}
                </select></label>
                <button className="button" type="submit">{text(zhCN.pagesObjectsPage.filter, "Filter")}</button>
                {(keyword || status) && <button className="button quiet" type="button" onClick={() => {
                  setKeywordDraft("");
                  setSearchParams({ kind: selection.entityKind, object_type: objectType, page: "1" });
                }}>{text(zhCN.pagesObjectsPage.clear, "Clear")}</button>}
              </form>
              {records.isFetching && !records.isPending && <div className="object-refreshing" role="status">{text(zhCN.pagesObjectsPage.updatingResults, "Updating results…")}</div>}
              {displayNames.isError && <div className="object-refreshing" role="status">{text(zhCN.pagesObjectsPage.nameResolutionIsTemporarilyUnavailableRecordIDsAreShown, "Name resolution is temporarily unavailable; record IDs are shown instead.")}</div>}
              <ListState
                loading={records.isPending}
                error={records.isError ? apiErrorMessage(records.error) : null}
                empty={records.data?.data.length === 0}
                emptyTitle={text(zhCN.pagesObjectsPage.noMatchingRecords, "No matching records")}
                emptyDescription={text(zhCN.pagesObjectsPage.changeTheKeywordOrStatusFilterAndTryAgain, "Change the keyword or status filter and try again.")}
                onRetry={() => void records.refetch()}
              >
                {records.data && <>
                  <ObjectRecordTable records={records.data.data} objectType={objectType} employees={displayNames.data?.employees ?? {}} actors={displayNames.data?.actors ?? {}} />
                  <Pagination meta={records.data.meta} onPageChange={changePage} />
                </>}
              </ListState>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
