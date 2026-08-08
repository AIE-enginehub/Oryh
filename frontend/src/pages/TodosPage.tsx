import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useOutletContext } from "react-router-dom";

import type { ConsoleContext } from "../App";
import {
  completeTodo,
  isActivityForbidden,
  listTodoEmployeeOptions,
  listTodos,
  resolveTodoDisplayNames,
  type ActivityDisplayNames,
  type Todo,
  type TodoEmployeeOption,
  type TodoEntityType,
  type TodoStatus,
} from "../api/activity";
import { ActivityConfirmDialog } from "../components/activity/ActivityConfirmDialog";
import { apiErrorMessage, ListState } from "../components/master-data/ListState";
import { Pagination } from "../components/master-data/Pagination";
import { ActivityToolbar } from "../components/activity/ActivityToolbar";
import { useActivityLabels } from "../components/activity/labels";
import { RestrictedState } from "../components/activity/RestrictedState";
import { useI18n } from "../i18n";
import "./activity.css";

const PAGE_SIZE = 20;
type StatusFilter = "" | TodoStatus;
type EntityFilter = "" | TodoEntityType;

function permissionCovers(permissions: string[], capability: string): boolean {
  return permissions.includes(capability) || permissions.includes(`${capability}:*`);
}

function formatDate(value: string | null | undefined, locale: string): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function isOverdue(todo: Todo): boolean {
  return todo.status === "open" && Boolean(todo.due_at) && Date.parse(todo.due_at!) < Date.now();
}

const EMPTY_NAMES: ActivityDisplayNames = { employees: {}, actors: {} };

function resolvedReference(value: string, names: ActivityDisplayNames): string {
  return names.actors[value] || names.employees[value] || value;
}

function IdentityReference({
  value,
  names,
  label,
}: {
  value: string | null | undefined;
  names: ActivityDisplayNames;
  label?: string;
}) {
  if (!value) return <span className="muted-value">—</span>;
  const resolved = label || resolvedReference(value, names);
  const hasDisplayName = resolved !== value;
  return <span className="activity-identity"><strong className={hasDisplayName ? undefined : "mono-cell"} title={resolved}>{resolved}</strong>{hasDisplayName && <small className="mono-cell" title={value}>{value}</small>}</span>;
}

function employeeOptionLabel(employee: TodoEmployeeOption, inactiveLabel: string): string {
  const code = employee.employee_code ? ` · ${employee.employee_code}` : "";
  const status = employee.status === "inactive" ? ` (${inactiveLabel})` : "";
  return `${employee.name}${code}${status}`;
}

export function TodosPage() {
  const { language, text } = useI18n();
  const { entityLabels, todoEntityOptions } = useActivityLabels();
  const { bootstrap } = useOutletContext<ConsoleContext>();
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [entityType, setEntityType] = useState<EntityFilter>("");
  const [page, setPage] = useState(1);
  const [confirming, setConfirming] = useState<Todo | null>(null);
  const [employeeFilter, setEmployeeFilter] = useState("");
  const [employeeKeyword, setEmployeeKeyword] = useState("");
  const [employeeKeywordDraft, setEmployeeKeywordDraft] = useState("");
  const [selectedEmployee, setSelectedEmployee] = useState<TodoEmployeeOption | null>(null);

  const canComplete = permissionCovers(bootstrap.permissions, "todos.complete_own");
  const canActForAny = permissionCovers(bootstrap.permissions, "tenant.act_for_any_employee");
  const canSeeAll = bootstrap.role === "admin" || canActForAny;
  const missingEmployee = !canSeeAll && !bootstrap.employee_id;
  const employeeScope = canSeeAll ? (employeeFilter || undefined) : (bootstrap.employee_id ?? undefined);

  const employeeChoices = useQuery({
    queryKey: ["activity", "todo-employee-options", employeeKeyword],
    queryFn: () => listTodoEmployeeOptions(employeeKeyword || undefined),
    enabled: canSeeAll,
    retry: false,
  });
  const employeeOptions = useMemo(() => {
    const options = [...(employeeChoices.data?.data ?? [])];
    if (selectedEmployee && !options.some((employee) => employee.id === selectedEmployee.id)) {
      options.unshift(selectedEmployee);
    }
    return options;
  }, [employeeChoices.data?.data, selectedEmployee]);

  const todos = useQuery({
    queryKey: ["activity", "todos", { keyword, status, entityType, employeeScope, page }],
    queryFn: () => listTodos({
      page,
      size: PAGE_SIZE,
      keyword: keyword || undefined,
      status: status || undefined,
      entity_type: entityType || undefined,
      employee_id: employeeScope,
    }),
    enabled: !missingEmployee,
    placeholderData: keepPreviousData,
  });

  const displayNames = useQuery({
    queryKey: ["activity", "todo-display-names", todos.data?.data.map((todo) => `${todo.id}:${todo.employee_id}:${todo.created_by ?? ""}:${todo.completed_by ?? ""}`) ?? []],
    queryFn: () => resolveTodoDisplayNames(todos.data!.data),
    enabled: Boolean(todos.data?.data.length),
    retry: false,
  });

  const complete = useMutation({
    mutationFn: (id: string) => completeTodo(id),
    onSuccess: async () => {
      setConfirming(null);
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["activity", "todos"] });
    },
  });

  const result = todos.data;
  const availablePages = result?.meta.pages;
  useEffect(() => {
    if (availablePages !== undefined && page > availablePages) setPage(Math.max(availablePages, 1));
  }, [availablePages, page]);

  const canCompleteItem = (todo: Todo) =>
    canComplete && (canActForAny || bootstrap.employee_id === todo.employee_id);

  const searchEmployees = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setEmployeeKeyword(employeeKeywordDraft.trim());
  };

  const names = displayNames.data ?? EMPTY_NAMES;

  return (
    <div className="activity-page" data-testid="todos-page">
      <header className="page-intro">
        <div><span className="eyebrow">{text("人工工作队列", "Human work queue")}</span><h2>{canSeeAll ? text("工作空间待办", "Workspace to-dos") : text("我的待办", "My to-dos")}</h2><p>{text("查看代理与管理员创建的人工工作项，并在完成后保留处理记录。", "Review work items created by agents and administrators, and keep a completion record when the work is done.")}</p></div>
      </header>

      {!canComplete && <div className="activity-banner" role="status"><span className="restricted-mark" aria-hidden="true">i</span><div><strong>{text("当前为只读模式", "Read-only mode")}</strong><span>{text("缺少 todos.complete_own 能力，可以查看待办但不能标记完成。", "The todos.complete_own capability is missing. You can view to-dos but cannot mark them complete.")}</span></div></div>}

      {missingEmployee ? (
        <RestrictedState title={text("账号尚未关联员工档案", "No employee profile is linked to this account")} description={text("个人待办按员工身份显示。请联系工作空间管理员关联员工后再查看。", "Personal to-dos are shown by employee identity. Ask a workspace administrator to link an employee profile before continuing.")} />
      ) : todos.isError && isActivityForbidden(todos.error) ? (
        <RestrictedState title={text("无法访问待办", "Cannot access to-dos")} description={text("当前登录身份没有读取此活动队列的权限。", "The signed-in identity does not have permission to read this activity queue.")} />
      ) : (
        <section className="data-panel" aria-label={text("待办列表", "To-do list")} aria-busy={todos.isFetching}>
          {canSeeAll && <form className="todo-employee-filter" aria-label={text("按负责人筛选待办", "Filter to-dos by assignee")} onSubmit={searchEmployees}>
            <label htmlFor="todo-employee-search">{text("查找负责人", "Find assignee")}</label>
            <div className="todo-employee-search"><input id="todo-employee-search" type="search" value={employeeKeywordDraft} placeholder={text("输入员工姓名", "Enter an employee name")} onChange={(event) => setEmployeeKeywordDraft(event.target.value)} /><button className="button compact" type="submit">{text("搜索员工", "Search employees")}</button></div>
            <label className="sr-only" htmlFor="todo-employee-filter">{text("负责人筛选", "Assignee filter")}</label>
            <select id="todo-employee-filter" aria-label={text("负责人筛选", "Assignee filter")} value={employeeFilter} onChange={(event) => {
              const value = event.target.value;
              setEmployeeFilter(value);
              setSelectedEmployee(employeeOptions.find((employee) => employee.id === value) ?? null);
              setPage(1);
            }}>
              <option value="">{text("全部员工", "All employees")}</option>
              {employeeOptions.map((employee) => <option key={employee.id} value={employee.id}>{employeeOptionLabel(employee, text("停用", "Inactive"))}</option>)}
            </select>
            <small>{employeeChoices.isFetching ? text("正在搜索员工…", "Searching employees…") : employeeChoices.isError ? <span className="field-error" role="alert">{text("员工搜索暂时不可用；已选筛选仍会保留。", "Employee search is temporarily unavailable; the selected filter will be preserved.")}</span> : text(`匹配 ${employeeChoices.data?.meta.total ?? 0} 位，最多显示 20 位`, `${employeeChoices.data?.meta.total ?? 0} matches; showing up to 20`)}</small>
          </form>}
          <ActivityToolbar
            idPrefix="todo"
            keyword={keyword}
            primary={status}
            entityType={entityType}
            keywordPlaceholder={text("搜索标题、描述或对象 ID", "Search title, description, or object ID")}
            primaryLabel={text("状态", "status")}
            primaryOptions={[{ value: "open", label: text("未完成", "Open") }, { value: "completed", label: text("已完成", "Completed") }]}
            entityOptions={todoEntityOptions}
            onApply={(filters) => {
              setKeyword(filters.keyword);
              setStatus(filters.primary as StatusFilter);
              setEntityType(filters.entityType as EntityFilter);
              setPage(1);
            }}
          />
          {displayNames.isError && <div className="activity-name-warning" role="status">{text("名称解析暂时不可用，当前保留原 employee ID 或 actor 标识。", "Name resolution is temporarily unavailable; raw employee IDs or actor identifiers are shown.")}</div>}
          <ListState
            loading={todos.isPending}
            error={todos.isError ? apiErrorMessage(todos.error) : null}
            empty={Boolean(result && result.data.length === 0)}
            emptyTitle={keyword || status || entityType || employeeFilter ? text("没有匹配的待办", "No matching to-dos") : text("当前没有待办", "No to-dos yet")}
            emptyDescription={keyword || status || entityType || employeeFilter ? text("尝试调整关键词、状态、负责人或对象类型。", "Try changing the keyword, status, assignee, or object type.") : text("新的人工工作项会在代理或管理员创建后出现在这里。", "New human work items appear here after an agent or administrator creates them.")}
            onRetry={() => void todos.refetch()}
          >
            {result && <>
              <div className="table-scroll"><table className="data-table activity-table todo-table">
                <thead><tr><th>{text("待办", "To-do")}</th><th>{text("负责人", "Assignee")}</th><th>{text("关联对象", "Related object")}</th><th>{text("截止时间", "Due date")}</th><th>{text("状态", "Status")}</th><th>{text("创建者", "Created by")}</th><th>{text("完成信息", "Completion")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
                <tbody>{result.data.map((todo) => {
                  const allowed = canCompleteItem(todo);
                  const employeeName = names.employees[todo.employee_id];
                  const ownerLabel = bootstrap.employee_id === todo.employee_id
                    ? `${text("我", "Me")}${employeeName ? ` · ${employeeName}` : ""}`
                    : undefined;
                  return <tr key={todo.id}>
                    <td className="activity-title"><strong>{todo.title}</strong><small>{todo.description || todo.todo_type || text("无补充说明", "No additional details")}</small></td>
                    <td><IdentityReference value={todo.employee_id} names={names} label={ownerLabel} /></td>
                    <td className="entity-reference"><strong>{entityLabels[todo.entity_type]}</strong><code title={todo.entity_id}>{todo.entity_id}</code></td>
                    <td><span className={`due-date ${isOverdue(todo) ? "overdue" : ""}`}>{formatDate(todo.due_at, language)}</span>{isOverdue(todo) && <small className="activity-completion">{text("已逾期", "Overdue")}</small>}</td>
                    <td><span className={`activity-status ${todo.status}`}>{todo.status === "open" ? text("未完成", "Open") : text("已完成", "Completed")}</span></td>
                    <td><IdentityReference value={todo.created_by} names={names} /><small className="activity-completion">{formatDate(todo.created_at, language)}</small></td>
                    <td>{todo.completed_at || todo.completed_by ? <><IdentityReference value={todo.completed_by} names={names} /><small className="activity-completion">{formatDate(todo.completed_at, language)}</small></> : <span className="muted-value">—</span>}</td>
                    <td className="row-actions">{todo.status === "open" && <button className="text-action" type="button" disabled={!allowed} title={allowed ? text("标记待办完成", "Mark to-do complete") : text("只能完成自己的待办，且需要 todos.complete_own 能力", "You can only complete your own to-dos and need the todos.complete_own capability")} aria-label={text(`完成“${todo.title}”`, `Complete “${todo.title}”`)} onClick={() => { complete.reset(); setConfirming(todo); }}>{text("完成", "Complete")}</button>}</td>
                  </tr>;
                })}</tbody>
              </table></div>
              <Pagination meta={result.meta} onPageChange={setPage} />
            </>}
          </ListState>
        </section>
      )}

      <ActivityConfirmDialog
        open={Boolean(confirming)}
        title={text(`完成“${confirming?.title ?? ""}”？`, `Complete “${confirming?.title ?? ""}”?`)}
        description={text("完成时间和当前用户会写入审计记录；此操作不会删除待办。", "The completion time and current user will be written to the audit log; this does not delete the to-do.")}
        busy={complete.isPending}
        error={complete.isError ? apiErrorMessage(complete.error) : null}
        onCancel={() => !complete.isPending && setConfirming(null)}
        onConfirm={() => confirming && complete.mutate(confirming.id)}
      />
    </div>
  );
}
