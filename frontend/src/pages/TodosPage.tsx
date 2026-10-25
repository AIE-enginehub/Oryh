import { zhCN } from "../locales/zh-CN/console";
import { useListFilters } from "../components/master-data/useListFilters";
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
  const { keyword, status, page, setPage, applyFilters } = useListFilters<StatusFilter>(["open", "completed"]);
  const [entityType, setEntityType] = useState<EntityFilter>("");
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
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["activity", "todos"] }),
        queryClient.invalidateQueries({ queryKey: ["console", "dashboard"] }),
      ]);
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
        <div><span className="eyebrow">{text(zhCN.pagesTodosPage.humanWorkQueue, "Human work queue")}</span><h2>{canSeeAll ? text(zhCN.pagesTodosPage.workspaceToDos, "Workspace to-dos") : text(zhCN.pagesTodosPage.myToDos, "My to-dos")}</h2><p>{text(zhCN.pagesTodosPage.reviewWorkItemsCreatedByAgentsAndAdministratorsAnd, "Review work items created by agents and administrators, and keep a completion record when the work is done.")}</p></div>
      </header>

      {!canComplete && <div className="activity-banner" role="status"><span className="restricted-mark" aria-hidden="true">i</span><div><strong>{text(zhCN.pagesTodosPage.readOnlyMode, "Read-only mode")}</strong><span>{text(zhCN.pagesTodosPage.theTodosCompleteOwnCapabilityIsMissingYouCan, "The todos.complete_own capability is missing. You can view to-dos but cannot mark them complete.")}</span></div></div>}

      {missingEmployee ? (
        <RestrictedState title={text(zhCN.pagesTodosPage.noEmployeeProfileIsLinkedToThisAccount, "No employee profile is linked to this account")} description={text(zhCN.pagesTodosPage.personalToDosAreShownByEmployeeIdentityAsk, "Personal to-dos are shown by employee identity. Ask a workspace administrator to link an employee profile before continuing.")} />
      ) : todos.isError && isActivityForbidden(todos.error) ? (
        <RestrictedState title={text(zhCN.pagesTodosPage.cannotAccessToDos, "Cannot access to-dos")} description={text(zhCN.pagesTodosPage.theSignedInIdentityDoesNotHavePermissionTo, "The signed-in identity does not have permission to read this activity queue.")} />
      ) : (
        <section className="data-panel" aria-label={text(zhCN.pagesTodosPage.toDoList, "To-do list")} aria-busy={todos.isFetching}>
          {canSeeAll && <form className="todo-employee-filter" aria-label={text(zhCN.pagesTodosPage.filterToDosByAssignee, "Filter to-dos by assignee")} onSubmit={searchEmployees}>
            <label htmlFor="todo-employee-search">{text(zhCN.pagesTodosPage.findAssignee, "Find assignee")}</label>
            <div className="todo-employee-search"><input id="todo-employee-search" type="search" value={employeeKeywordDraft} placeholder={text(zhCN.pagesTodosPage.enterAnEmployeeName, "Enter an employee name")} onChange={(event) => setEmployeeKeywordDraft(event.target.value)} /><button className="button compact" type="submit">{text(zhCN.pagesTodosPage.searchEmployees, "Search employees")}</button></div>
            <label className="sr-only" htmlFor="todo-employee-filter">{text(zhCN.pagesTodosPage.assigneeFilter, "Assignee filter")}</label>
            <select id="todo-employee-filter" aria-label={text(zhCN.pagesTodosPage.assigneeFilter, "Assignee filter")} value={employeeFilter} onChange={(event) => {
              const value = event.target.value;
              setEmployeeFilter(value);
              setSelectedEmployee(employeeOptions.find((employee) => employee.id === value) ?? null);
              setPage(1);
            }}>
              <option value="">{text(zhCN.pagesTodosPage.allEmployees, "All employees")}</option>
              {employeeOptions.map((employee) => <option key={employee.id} value={employee.id}>{employeeOptionLabel(employee, text(zhCN.pagesTodosPage.inactive, "Inactive"))}</option>)}
            </select>
            <small>{employeeChoices.isFetching ? text(zhCN.pagesTodosPage.searchingEmployees, "Searching employees…") : employeeChoices.isError ? <span className="field-error" role="alert">{text(zhCN.pagesTodosPage.employeeSearchIsTemporarilyUnavailableTheSelectedFilterWill, "Employee search is temporarily unavailable; the selected filter will be preserved.")}</span> : text(zhCN.pagesTodosPage.matchesShowingUpTo20(`${employeeChoices.data?.meta.total ?? 0}`), `${employeeChoices.data?.meta.total ?? 0} matches; showing up to 20`)}</small>
          </form>}
          <ActivityToolbar
            idPrefix="todo"
            keyword={keyword}
            primary={status}
            entityType={entityType}
            keywordPlaceholder={text(zhCN.pagesTodosPage.searchTitleDescriptionOrObjectID, "Search title, description, or object ID")}
            primaryLabel={text(zhCN.pagesTodosPage.status, "status")}
            primaryOptions={[{ value: "open", label: text(zhCN.pagesTodosPage.open, "Open") }, { value: "completed", label: text(zhCN.pagesTodosPage.completed, "Completed") }]}
            entityOptions={todoEntityOptions}
            onApply={(filters) => {
              applyFilters({ keyword: filters.keyword, status: filters.primary });
              setEntityType(filters.entityType as EntityFilter);
            }}
          />
          {displayNames.isError && <div className="activity-name-warning" role="status">{text(zhCN.pagesTodosPage.nameResolutionIsTemporarilyUnavailableRawEmployeeIDsOr, "Name resolution is temporarily unavailable; raw employee IDs or actor identifiers are shown.")}</div>}
          <ListState
            loading={todos.isPending}
            error={todos.isError ? apiErrorMessage(todos.error) : null}
            empty={Boolean(result && result.data.length === 0)}
            emptyTitle={keyword || status || entityType || employeeFilter ? text(zhCN.pagesTodosPage.noMatchingToDos, "No matching to-dos") : text(zhCN.pagesTodosPage.noToDosYet, "No to-dos yet")}
            emptyDescription={keyword || status || entityType || employeeFilter ? text(zhCN.pagesTodosPage.tryChangingTheKeywordStatusAssigneeOrObjectType, "Try changing the keyword, status, assignee, or object type.") : text(zhCN.pagesTodosPage.newHumanWorkItemsAppearHereAfterAnAgent, "New human work items appear here after an agent or administrator creates them.")}
            onRetry={() => void todos.refetch()}
          >
            {result && <>
              <div className="table-scroll"><table className="data-table activity-table todo-table">
                <thead><tr><th>{text(zhCN.pagesTodosPage.toDo, "To-do")}</th><th>{text(zhCN.pagesTodosPage.assignee, "Assignee")}</th><th>{text(zhCN.pagesTodosPage.relatedObject, "Related object")}</th><th>{text(zhCN.pagesTodosPage.dueDate, "Due date")}</th><th>{text(zhCN.pagesTodosPage.status, "Status")}</th><th>{text(zhCN.pagesTodosPage.createdBy, "Created by")}</th><th>{text(zhCN.pagesTodosPage.completion, "Completion")}</th><th><span className="sr-only">{text(zhCN.pagesTodosPage.actions, "Actions")}</span></th></tr></thead>
                <tbody>{result.data.map((todo) => {
                  const allowed = canCompleteItem(todo);
                  const employeeName = names.employees[todo.employee_id];
                  const ownerLabel = bootstrap.employee_id === todo.employee_id
                    ? zhCN.pagesTodosPage.template2(`${text(zhCN.pagesTodosPage.me, "Me")}`, `${employeeName ? ` · ${employeeName}` : ""}`)
                    : undefined;
                  return <tr key={todo.id}>
                    <td className="activity-title"><strong>{todo.title}</strong><small>{todo.description || todo.todo_type || text(zhCN.pagesTodosPage.noAdditionalDetails, "No additional details")}</small></td>
                    <td><IdentityReference value={todo.employee_id} names={names} label={ownerLabel} /></td>
                    <td className="entity-reference"><strong>{entityLabels[todo.entity_type]}</strong><code title={todo.entity_id}>{todo.entity_id}</code></td>
                    <td><span className={`due-date ${isOverdue(todo) ? "overdue" : ""}`}>{formatDate(todo.due_at, language)}</span>{isOverdue(todo) && <small className="activity-completion">{text(zhCN.pagesTodosPage.overdue, "Overdue")}</small>}</td>
                    <td><span className={`activity-status ${todo.status}`}>{todo.status === "open" ? text(zhCN.pagesTodosPage.open, "Open") : text(zhCN.pagesTodosPage.completed, "Completed")}</span></td>
                    <td><IdentityReference value={todo.created_by} names={names} /><small className="activity-completion">{formatDate(todo.created_at, language)}</small></td>
                    <td>{todo.completed_at || todo.completed_by ? <><IdentityReference value={todo.completed_by} names={names} /><small className="activity-completion">{formatDate(todo.completed_at, language)}</small></> : <span className="muted-value">—</span>}</td>
                    <td className="row-actions">{todo.status === "open" && <button className="text-action" type="button" disabled={!allowed} title={allowed ? text(zhCN.pagesTodosPage.markToDoComplete, "Mark to-do complete") : text(zhCN.pagesTodosPage.youCanOnlyCompleteYourOwnToDosAnd, "You can only complete your own to-dos and need the todos.complete_own capability")} aria-label={text(zhCN.pagesTodosPage.complete2(`${todo.title}`), `Complete “${todo.title}”`)} onClick={() => { complete.reset(); setConfirming(todo); }}>{text(zhCN.pagesTodosPage.complete, "Complete")}</button>}</td>
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
        title={text(zhCN.pagesTodosPage.complete3(`${confirming?.title ?? ""}`), `Complete “${confirming?.title ?? ""}”?`)}
        description={text(zhCN.pagesTodosPage.theCompletionTimeAndCurrentUserWillBeWritten, "The completion time and current user will be written to the audit log; this does not delete the to-do.")}
        busy={complete.isPending}
        error={complete.isError ? apiErrorMessage(complete.error) : null}
        onCancel={() => !complete.isPending && setConfirming(null)}
        onConfirm={() => confirming && complete.mutate(confirming.id)}
      />
    </div>
  );
}
