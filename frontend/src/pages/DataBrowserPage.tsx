import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowDown, ArrowUp, Database, Plus } from "@phosphor-icons/react";

import { ApiError } from "../api/client";
import {
  changedFields,
  dataCatalog,
  filledFields,
  findResource,
  formValue,
  listRows,
  nextOrderBy,
  parseOrderBy,
  recordUrl,
  writeRecord,
  type CatalogAction,
  type CatalogField,
  type CatalogResource,
  type CatalogWriteField,
  type DataRow,
  type WriteMethod,
} from "../api/dataCatalog";
import { getObjectDirectory, isObjectEntityType } from "../api/objects";
import { ReferencePicker, referenceTarget, rowTitle } from "../components/data/ReferencePicker";
import { RestrictedState } from "../components/activity/RestrictedState";
import { ConfirmDialog } from "../components/master-data/ConfirmDialog";
import { Drawer } from "../components/master-data/Drawer";
import { apiErrorMessage, ListState } from "../components/master-data/ListState";
import { Pagination } from "../components/master-data/Pagination";
import { useI18n } from "../i18n";
import "./data-browser.css";

const DETAIL_TYPES: Record<string, string> = {
  "timesheet-headers": "timesheet_header",
  "expense-claims": "expense_claim",
  "purchase-requests": "purchase_request",
  "sales-quotations": "sales_quotation",
  "sales-orders": "sales_order",
  invoices: "invoice",
  payments: "payment",
  "billing-accounts": "billing_account",
  "resource-bookings": "resource_booking",
  "business-objects": "business_object",
};

function pick(label: [string, string], language: string): string {
  return language === "en" ? label[1] : label[0];
}

export function DataBrowserPage() {
  const { resource: key } = useParams();
  const resource = findResource(key);
  if (!key) return <DataDirectory />;
  if (!resource) return <DataDirectory missing={key} />;
  return <DataList key={resource.key} resource={resource} />;
}

function DataDirectory({ missing }: { missing?: string }) {
  const { text, language } = useI18n();
  return (
    <div className="master-data-page data-browser" data-testid="data-directory">
      <header className="page-intro">
        <div>
          <span className="eyebrow">Data browser</span>
          <h2>{text("数据浏览", "Data browser")}</h2>
          <p>{text("按集合查看和维护工作区的全部主数据和业务数据：服务端支持的每个筛选条件、任意列排序、分页；每一次写入都先确认。", "Every collection in the workspace, master and business data alike: every server-side filter, sort on any column, paging — and every write confirmed first.")}</p>
        </div>
      </header>
      {missing && <p className="notice error" role="alert">{text(`没有名为 ${missing} 的集合。`, `There is no collection named ${missing}.`)}</p>}
      {dataCatalog.groups.map((group) => {
        const resources = dataCatalog.resources.filter((item) => item.group === group.key);
        if (resources.length === 0) return null;
        return (
          <section className="data-panel data-group" key={group.key} aria-label={pick(group.label, language)}>
            <h3>{pick(group.label, language)}</h3>
            <ul className="data-group-list">
              {resources.map((item) => (
                <li key={item.key}>
                  <Link to={`/data/${item.key}`}><Database size={16} aria-hidden />{pick(item.label, language)}</Link>
                  <small>{item.filters.length} {text("个筛选", "filters")} · {item.columns.length} {text("列", "columns")}{item.update ? ` · ${text("可编辑", "editable")}` : ""}</small>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

// One write the person asked for, held until they confirm the facts it
// will send. `body` is exactly the request body; nothing is added after
// the confirmation.
type PendingWrite = {
  kind: "create" | "update" | "delete" | "action" | "status";
  label: string;
  method: WriteMethod;
  path: string;
  body?: DataRow;
  row?: DataRow;
};

type Editor =
  | { kind: "create"; fields: CatalogWriteField[] }
  | { kind: "update"; fields: CatalogWriteField[]; row: DataRow }
  | { kind: "action"; action: CatalogAction; row: DataRow }
  | { kind: "status"; row: DataRow; options: string[] }
  | { kind: "detail"; row: DataRow };


function DataList({ resource }: { resource: CatalogResource }) {
  const { text, language } = useI18n();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const orderBy = params.get("order_by");
  const sort = parseOrderBy(orderBy);
  const page = Math.max(1, Number(params.get("page")) || 1);
  const queryKey = useMemo(() => ["data-browser", resource.key, params.toString()], [resource.key, params]);
  const rows = useQuery({
    queryKey,
    queryFn: () => listRows(resource, params),
    placeholderData: keepPreviousData,
  });
  const [editor, setEditor] = useState<Editor | null>(null);
  const [pending, setPending] = useState<PendingWrite | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const detailType = DETAIL_TYPES[resource.key];
  const editableStatus = resource.update?.find((field) => field.name === "status");
  // the states a document may be set to: its own machine for the ten
  // built-in families, the contract's enum otherwise, free text failing both
  const machine = useQuery({
    queryKey: ["data-browser", "machine", detailType],
    queryFn: async () => {
      const directory = await getObjectDirectory(language === "en" ? "en" : "zh-CN");
      return directory.types.find((item) => item.entityKind === "builtin" && item.objectType === detailType)?.statuses ?? [];
    },
    enabled: Boolean(editableStatus && detailType && detailType !== "business_object" && isObjectEntityType(detailType)),
    staleTime: 5 * 60_000,
  });
  const statusOptions = (machine.data && machine.data.length > 0 ? machine.data : editableStatus?.enum) ?? [];

  const write = useMutation({
    mutationFn: (job: PendingWrite) => writeRecord(job.method, job.path, job.body),
    onSuccess: (_data, job) => {
      setPending(null);
      setEditor(null);
      setNotice({
        create: text("记录已创建。", "Record created."),
        update: text("更改已保存。", "Changes saved."),
        delete: text("记录已删除或归档。", "Record deleted or archived."),
        action: text(`已执行：${job.label}`, `Done: ${job.label}`),
        status: text("状态已更新。", "Status updated."),
      }[job.kind]);
      void queryClient.invalidateQueries({ queryKey: ["data-browser", resource.key] });
    },
  });

  const update = (mutate: (next: URLSearchParams) => void) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      mutate(next);
      return next;
    }, { preventScrollReset: true });
  };
  const applyFilters = (values: Record<string, string>) => update((next) => {
    for (const filter of resource.filters) {
      const value = values[filter.name]?.trim();
      if (value) next.set(filter.name, value);
      else next.delete(filter.name);
    }
    next.delete("page");
  });
  const sortBy = (column: string) => update((next) => {
    next.set("order_by", nextOrderBy(orderBy, column));
    next.delete("page");
  });
  const setPage = (nextPage: number) => update((next) => {
    if (nextPage <= 1) next.delete("page");
    else next.set("page", String(nextPage));
  });

  const restricted = rows.error instanceof ApiError && rows.error.status === 403;
  const activeFilters = resource.filters.filter((filter) => params.get(filter.name));
  const recordPath = resource.recordPath;
  const idOf = (row: DataRow) => String(row.id ?? "");
  const canEdit = Boolean(recordPath && resource.update && resource.update.some((field) => field.name !== "status"));
  const canAct = (row: DataRow) => Boolean(recordPath && idOf(row));

  // the editor's submit becomes a pending write; the confirmation sends it
  const stage = (job: PendingWrite) => { write.reset(); setPending(job); };
  const openCreate = () => resource.create && setEditor({ kind: "create", fields: resource.create });
  const submitEditor = (draft: Record<string, string>) => {
    if (!editor) return;
    if (editor.kind === "create") {
      stage({ kind: "create", label: text("新建", "Create"), method: "POST", path: resource.path, body: filledFields(editor.fields, draft) });
    } else if (editor.kind === "update" && recordPath) {
      const body = changedFields(editor.fields, editor.row, draft);
      stage({ kind: "update", label: text("编辑", "Edit"), method: "PATCH", path: recordUrl(recordPath, idOf(editor.row)), body, row: editor.row });
    } else if (editor.kind === "action") {
      stage({ kind: "action", label: editor.action.summary, method: "POST", path: recordUrl(editor.action.path, idOf(editor.row)), body: filledFields(editor.action.fields, draft), row: editor.row });
    } else if (editor.kind === "status" && recordPath) {
      stage({ kind: "status", label: text("状态", "Status"), method: "PATCH", path: recordUrl(recordPath, idOf(editor.row)), body: { status: draft.status }, row: editor.row });
    }
  };
  const runAction = (action: CatalogAction, row: DataRow) => {
    if (action.fields.length > 0) setEditor({ kind: "action", action, row });
    else stage({ kind: "action", label: action.summary, method: "POST", path: recordUrl(action.path, idOf(row)), body: {}, row });
  };
  const askDelete = (row: DataRow) => recordPath && stage({ kind: "delete", label: text("删除", "Delete"), method: "DELETE", path: recordUrl(recordPath, idOf(row)), row });

  return (
    <div className="master-data-page data-browser" data-testid="data-list">
      <header className="page-intro">
        <div>
          <span className="eyebrow"><Link to="/data">{text("数据浏览", "Data browser")}</Link></span>
          <h2>{pick(resource.label, language)}</h2>
          <p><code>GET {resource.path}</code>{activeFilters.length > 0 && <> · {text(`${activeFilters.length} 个筛选生效`, `${activeFilters.length} filters applied`)}</>}</p>
        </div>
        {resource.create && (
          <button className="button primary" type="button" onClick={openCreate}><Plus size={17} aria-hidden />{text("新建", "Create")}</button>
        )}
      </header>
      {notice && (
        <div className="record-notice"><div role="status"><span>{notice}</span></div><button className="icon-button" type="button" aria-label={text("关闭操作提示", "Dismiss update")} onClick={() => setNotice(null)}>×</button></div>
      )}
      <section className="data-panel" aria-label={pick(resource.label, language)}>
        <FilterForm key={params.toString()} resource={resource} params={params} onApply={applyFilters} />
        {restricted ? (
          <RestrictedState title={text("无权查看这个集合", "This collection is not visible to you")} description={text("你的角色没有读取它的能力；管理员可以在角色页调整。", "Your role lacks the capability to read it; an administrator can change that on the roles page.")} />
        ) : (
          <ListState
            loading={rows.isPending}
            error={rows.isError ? apiErrorMessage(rows.error) : null}
            empty={!rows.isPending && !rows.isError && (rows.data?.data.length ?? 0) === 0}
            emptyTitle={text("没有匹配的记录", "No matching records")}
            emptyDescription={text("放宽筛选条件再试。", "Loosen the filters and try again.")}
            onRetry={() => rows.refetch()}
          >
            <div className="table-scroll">
              <table className="data-table data-browser-table">
                <thead>
                  <tr>
                    <th><span className="sr-only">{text("操作", "Actions")}</span></th>
                    {resource.columns.map((column) => {
                      const active = sort?.column === column.name;
                      return (
                        <th key={column.name} aria-sort={active ? (sort?.descending ? "descending" : "ascending") : "none"}>
                          <button type="button" className="sort-header" onClick={() => sortBy(column.name)}>
                            {column.name}
                            {active && (sort?.descending ? <ArrowDown size={13} aria-hidden /> : <ArrowUp size={13} aria-hidden />)}
                          </button>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {(rows.data?.data ?? []).map((row, index) => (
                    <tr key={idOf(row) || index}>
                      <td className="row-actions data-row-actions">
                        <button className="text-action" type="button" onClick={() => setEditor({ kind: "detail", row })}>{text("详情", "Detail")}</button>
                        {detailType && idOf(row) && <Link className="text-action" to={detailUrl(detailType, row)}>{text("轨迹", "Trail")}</Link>}
                        {canEdit && canAct(row) && <button className="text-action" type="button" onClick={() => setEditor({ kind: "update", fields: resource.update!.filter((field) => field.name !== "status"), row })}>{text("编辑", "Edit")}</button>}
                        {editableStatus && canAct(row) && <button className="text-action" type="button" onClick={() => setEditor({ kind: "status", row, options: statusOptions })}>{text("状态", "Status")}</button>}
                        {(resource.actions ?? []).length > 0 && canAct(row) && (
                          <details className="row-menu">
                            <summary className="text-action">{text("动作", "Actions")}</summary>
                            <div className="row-menu-list">
                              {resource.actions!.map((action) => (
                                <button key={action.verb} className="text-action" type="button" onClick={(event) => { (event.currentTarget.closest("details") as HTMLDetailsElement | null)?.removeAttribute("open"); runAction(action, row); }}>{action.verb}</button>
                              ))}
                            </div>
                          </details>
                        )}
                        {resource.remove && canAct(row) && <button className="text-action danger-text" type="button" onClick={() => askDelete(row)}>{text("删除", "Delete")}</button>}
                      </td>
                      {resource.columns.map((column) => <td key={column.name} className={cellClass(column)}>{formatCell(row[column.name], column, language)}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {rows.data && <Pagination meta={{ ...rows.data.meta, page }} onPageChange={setPage} />}
          </ListState>
        )}
      </section>

      {editor && editor.kind !== "detail" && (
        <RecordEditor key={`${editor.kind}-${"row" in editor ? idOf(editor.row) : "new"}`} editor={editor} resource={resource} onClose={() => setEditor(null)} onSubmit={submitEditor} />
      )}
      {editor?.kind === "detail" && (
        <Drawer open title={rowTitle(editor.row) || text("记录", "Record")} description={`${pick(resource.label, language)} · ${idOf(editor.row)}`} submitLabel={text("关闭", "Close")} onClose={() => setEditor(null)} onSubmit={(event) => { event.preventDefault(); setEditor(null); }}>
          {(resource.related ?? []).length > 0 && (
            <nav className="data-related" aria-label={text("相关记录", "Related records")}>
              {resource.related!.map((link) => (
                <Link key={`${link.resource}-${link.param}`} className="button compact" to={`/data/${link.resource}?${link.param}=${encodeURIComponent(idOf(editor.row))}`} onClick={() => setEditor(null)}>
                  {pick(link.label, language)}
                </Link>
              ))}
            </nav>
          )}
          <dl className="data-detail">
            {Object.entries(editor.row).map(([key, value]) => (
              <div key={key}><dt>{key}</dt><dd>{value !== null && typeof value === "object" ? <pre>{JSON.stringify(value, null, 2)}</pre> : formValue(value) || <span className="muted-value">—</span>}</dd></div>
            ))}
          </dl>
        </Drawer>
      )}
      {pending && (
        <ConfirmDialog
          open
          tone={pending.kind === "delete" ? "danger" : "primary"}
          kicker={text("写入确认", "Confirm write")}
          title={pending.kind === "delete"
            ? text(`删除 ${rowTitle(pending.row ?? {})}？`, `Delete ${rowTitle(pending.row ?? {})}?`)
            : `${pending.label} · ${pending.row ? rowTitle(pending.row) : pick(resource.label, language)}`}
          description={text(`将发送 ${pending.method} ${pending.path}。下面是要写入的全部内容。`, `Sends ${pending.method} ${pending.path}. Everything it will write is listed below.`)}
          confirmLabel={text("确认写入", "Confirm write")}
          busyLabel={text("正在写入…", "Writing…")}
          scrimLabel={text("取消写入", "Cancel write")}
          busy={write.isPending}
          error={write.isError ? apiErrorMessage(write.error) : null}
          onCancel={() => { if (!write.isPending) setPending(null); }}
          onConfirm={() => write.mutate(pending)}
        >
          {pending.body !== undefined && (
            Object.keys(pending.body).length === 0
              ? <p className="muted-value">{text("不带任何字段。", "No fields.")}</p>
              : (
                <table className="data-table write-preview" aria-label={text("将写入的字段", "Fields to write")}>
                  <tbody>
                    {Object.entries(pending.body).map(([key, value]) => (
                      <tr key={key}>
                        <th scope="row">{key}</th>
                        {pending.row && key in pending.row && <td className="muted-value">{formValue(pending.row[key]) || "—"}</td>}
                        <td>{value === null ? <span className="muted-value">{text("清空", "clear")}</span> : formValue(value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
          )}
        </ConfirmDialog>
      )}
    </div>
  );
}

// The drawer form for a create, an update, a verb with inputs, or a status
// change. Fields come from the contract; required and length limits are
// the schema's; the submit stages the write for confirmation.
function RecordEditor({ editor, resource, onClose, onSubmit }: { editor: Exclude<Editor, { kind: "detail" }>; resource: CatalogResource; onClose: () => void; onSubmit: (draft: Record<string, string>) => void }) {
  const { text, language } = useI18n();
  const fields: CatalogWriteField[] = editor.kind === "action" ? editor.action.fields : editor.kind === "status" ? [] : editor.fields;
  const [draft, setDraft] = useState<Record<string, string>>(() => {
    if (editor.kind === "update") return Object.fromEntries(editor.fields.map((field) => [field.name, formValue(editor.row[field.name])]));
    if (editor.kind === "status") return { status: formValue(editor.row.status) };
    return Object.fromEntries(fields.map((field) => [field.name, ""]));
  });
  const [problem, setProblem] = useState<string | null>(null);
  const title = {
    create: text(`新建 ${pick(resource.label, language)}`, `New ${pick(resource.label, language)}`),
    update: text(`编辑 ${rowTitle(editor.kind === "update" ? editor.row : {})}`, `Edit ${rowTitle(editor.kind === "update" ? editor.row : {})}`),
    action: editor.kind === "action" ? editor.action.summary : "",
    status: text(`设置状态 · ${rowTitle(editor.kind === "status" ? editor.row : {})}`, `Set status · ${rowTitle(editor.kind === "status" ? editor.row : {})}`),
  }[editor.kind];
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (editor.kind === "update" && Object.keys(changedFields(editor.fields, editor.row, draft)).length === 0) {
      setProblem(text("没有任何更改。", "Nothing changed."));
      return;
    }
    if (editor.kind === "status" && !draft.status.trim()) {
      setProblem(text("请选择状态。", "Choose a status."));
      return;
    }
    setProblem(null);
    onSubmit(draft);
  };
  return (
    <Drawer open title={title} description={text("提交后会先显示将写入的内容，确认后才发送。", "Submitting shows what will be written; nothing is sent until you confirm.")} submitLabel={text("下一步：确认", "Next: confirm")} error={problem} onClose={onClose} onSubmit={submit}>
      <div className="field-grid">
        {editor.kind === "status" && (
          <div className="field span-2">
            <label htmlFor="data-status">status</label>
            {editor.options.length > 0
              ? <select id="data-status" value={draft.status} onChange={(event) => setDraft({ status: event.target.value })}><option value="">{text("选择…", "Choose…")}</option>{editor.options.map((option) => <option key={option} value={option}>{option}</option>)}</select>
              : <input id="data-status" value={draft.status} onChange={(event) => setDraft({ status: event.target.value })} />}
          </div>
        )}
        {fields.map((field) => (
          <div key={field.name} className={`field${field.maxLength && field.maxLength > 100 ? " span-2" : ""}`}>
            <label htmlFor={`data-${field.name}`} title={field.description}>{field.name}{field.required && <b> *</b>}</label>
            <WriteInput id={`data-${field.name}`} field={field} value={draft[field.name] ?? ""} onChange={(value) => setDraft({ ...draft, [field.name]: value })} />
            {field.description && <small className="muted-value">{field.description}</small>}
          </div>
        ))}
        {fields.length === 0 && editor.kind !== "status" && <p className="muted-value span-2">{text("这个动作不需要输入。", "This action takes no input.")}</p>}
      </div>
    </Drawer>
  );
}

function WriteInput({ id, field, value, onChange }: { id: string; field: CatalogWriteField; value: string; onChange: (value: string) => void }) {
  const { text } = useI18n();
  const required = field.required || undefined;
  const target = referenceTarget(field.name);
  if (target) return <ReferencePicker id={id} target={target} value={value} required={required} onChange={onChange} />;
  if (field.enum && field.enum.length > 0) {
    return <select id={id} required={required} value={value} onChange={(event) => onChange(event.target.value)}><option value="">{text("未设置", "Unset")}</option>{field.enum.map((option) => <option key={option} value={option}>{option}</option>)}</select>;
  }
  if (field.type === "boolean") {
    return <select id={id} required={required} value={value} onChange={(event) => onChange(event.target.value)}><option value="">{text("未设置", "Unset")}</option><option value="true">true</option><option value="false">false</option></select>;
  }
  if (field.format === "date") return <input id={id} type="date" required={required} value={value} onChange={(event) => onChange(event.target.value)} />;
  if (field.format === "date-time") return <input id={id} type="datetime-local" required={required} value={value.replace(/(\.\d+)?(Z|[+-]\d\d:\d\d)$/, "")} onChange={(event) => onChange(event.target.value)} />;
  if (field.type === "integer" || field.type === "number") return <input id={id} type="number" step={field.type === "integer" ? 1 : "any"} required={required} value={value} onChange={(event) => onChange(event.target.value)} />;
  if (field.maxLength && field.maxLength > 200) return <textarea id={id} rows={3} required={required} maxLength={field.maxLength} value={value} onChange={(event) => onChange(event.target.value)} />;
  return <input id={id} type="text" required={required} maxLength={field.maxLength} value={value} onChange={(event) => onChange(event.target.value)} />;
}

function detailUrl(entityType: string, row: DataRow): string {
  const kind = entityType === "business_object" ? "business_object" : "builtin";
  const objectType = entityType === "business_object" && typeof row.object_type === "string" ? row.object_type : entityType;
  const search = new URLSearchParams({ kind, object_type: objectType });
  return `/objects/${entityType}/${encodeURIComponent(String(row.id))}?${search.toString()}`;
}

function cellClass(column: CatalogField): string | undefined {
  if (column.type === "integer" || column.type === "number") return "numeric-cell";
  if (column.name === "id" || column.name.endsWith("_id")) return "mono-cell";
  return undefined;
}

function formatCell(value: unknown, column: CatalogField, language: string) {
  if (value === null || value === undefined || value === "") return <span className="muted-value">—</span>;
  if (typeof value === "boolean") return value ? (language === "en" ? "yes" : "是") : (language === "en" ? "no" : "否");
  if (column.format === "date-time" && typeof value === "string") {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString(language === "en" ? "en" : "zh-CN");
  }
  if (typeof value === "number") return value.toLocaleString(language === "en" ? "en" : "zh-CN");
  return String(value);
}

// One control per server-side filter, typed from the contract: enums become
// selects, booleans a yes/no select, dates a date input, the rest text.
function FilterForm({ resource, params, onApply }: { resource: CatalogResource; params: URLSearchParams; onApply: (values: Record<string, string>) => void }) {
  const { text } = useI18n();
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(resource.filters.map((filter) => [filter.name, params.get(filter.name) ?? ""])),
  );
  useEffect(() => {
    setDraft(Object.fromEntries(resource.filters.map((filter) => [filter.name, params.get(filter.name) ?? ""])));
  }, [resource, params]);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onApply(draft);
  };
  const clear = () => {
    const empty = Object.fromEntries(resource.filters.map((filter) => [filter.name, ""]));
    setDraft(empty);
    onApply(empty);
  };
  const dirty = resource.filters.some((filter) => (params.get(filter.name) ?? "") !== "");
  if (resource.filters.length === 0) return null;
  return (
    <form className="data-filters" role="search" onSubmit={submit}>
      {resource.filters.map((filter) => (
        <label key={filter.name} className="data-filter" title={filter.description}>
          <span>{filter.name}</span>
          <FilterInput filter={filter} value={draft[filter.name] ?? ""} onChange={(value) => setDraft({ ...draft, [filter.name]: value })} />
        </label>
      ))}
      <div className="data-filter-actions">
        <button className="button" type="submit">{text("筛选", "Filter")}</button>
        {dirty && <button className="button quiet" type="button" onClick={clear}>{text("清除", "Clear")}</button>}
      </div>
    </form>
  );
}

function FilterInput({ filter, value, onChange }: { filter: CatalogField; value: string; onChange: (value: string) => void }) {
  const { text } = useI18n();
  const target = referenceTarget(filter.name);
  if (target) return <ReferencePicker id={`filter-${filter.name}`} target={target} value={value} onChange={onChange} />;
  if (filter.enum && filter.enum.length > 0) {
    return (
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{text("全部", "Any")}</option>
        {filter.enum.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    );
  }
  if (filter.type === "boolean") {
    return (
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{text("全部", "Any")}</option>
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    );
  }
  if (filter.format === "date") return <input type="date" value={value} onChange={(event) => onChange(event.target.value)} />;
  if (filter.type === "integer" || filter.type === "number") return <input type="number" value={value} onChange={(event) => onChange(event.target.value)} />;
  return <input type="text" value={value} onChange={(event) => onChange(event.target.value)} />;
}
