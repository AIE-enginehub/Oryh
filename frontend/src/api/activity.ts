import { apiRequest, apiRequestEnvelope, ApiError, type PaginationMeta } from "./client";

export type TodoStatus = "open" | "completed";
export type TodoEntityType =
  | "timesheet_header"
  | "expense_claim"
  | "purchase_request"
  | "sales_quotation"
  | "sales_order"
  | "project"
  | "approval_target"
  | "business_object";

export type Todo = {
  id: string;
  employee_id: string;
  entity_type: TodoEntityType;
  entity_id: string;
  title: string;
  description?: string | null;
  todo_type?: string | null;
  status: TodoStatus;
  due_at?: string | null;
  created_by?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at?: string | null;
  completed_at?: string | null;
  completed_by?: string | null;
};

export type ApprovalAction = "submitted" | "approved" | "rejected" | "returned" | "commented";
export type ApprovalEntityType =
  | "timesheet_header"
  | "expense_claim"
  | "purchase_request"
  | "sales_quotation"
  | "sales_order"
  | "approval_target"
  | "business_object";

export type ApprovalRecord = {
  id: string;
  entity_type: ApprovalEntityType;
  entity_id: string;
  round_no: number;
  sequence_no: number;
  action: ApprovalAction;
  approver_id?: string | null;
  approver_role?: string | null;
  comment?: string | null;
  source?: "web" | "api" | "ai" | "system" | null;
  metadata?: Record<string, unknown>;
  acted_at: string;
  created_at: string;
};

export type ActivityPage<T> = { data: T[]; meta: PaginationMeta };

export type TodoEmployeeOption = {
  id: string;
  employee_code?: string | null;
  name: string;
  status: "active" | "inactive";
};

export type ActivityDisplayNames = {
  employees: Record<string, string>;
  actors: Record<string, string>;
};

export type TodoListFilters = {
  page?: number;
  size?: number;
  keyword?: string;
  status?: TodoStatus;
  entity_type?: TodoEntityType;
  employee_id?: string;
};

export type ApprovalListFilters = {
  page?: number;
  size?: number;
  keyword?: string;
  action?: ApprovalAction;
  entity_type?: ApprovalEntityType;
  entity_id?: string;
};

type LegacyMeta = Partial<PaginationMeta> & { request_id?: string | null };

function listUrl(path: string, values: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(values)) {
    if (value === undefined || value === "") continue;
    search.set(name, String(value));
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

function includes(value: string | null | undefined, keyword: string): boolean {
  return value?.toLocaleLowerCase().includes(keyword) ?? false;
}

function normalizePage<T>(
  data: T[],
  meta: LegacyMeta,
  page: number,
  size: number,
  matches: (item: T) => boolean,
  compare: (left: T, right: T) => number,
): ActivityPage<T> {
  const serverPaged = Number.isInteger(meta.page) && Number.isInteger(meta.page_size);
  if (serverPaged) {
    const total = typeof meta.total === "number" ? meta.total : data.length;
    return {
      data,
      meta: {
        total,
        page: meta.page as number,
        page_size: meta.page_size as number,
        pages: typeof meta.pages === "number" ? Math.max(meta.pages, 1) : Math.max(1, Math.ceil(total / size)),
      },
    };
  }

  const filtered = data.filter(matches).sort(compare);
  const total = filtered.length;
  const pages = Math.max(1, Math.ceil(total / size));
  const start = (page - 1) * size;
  return {
    data: filtered.slice(start, start + size),
    meta: { total, page, page_size: size, pages },
  };
}

export async function listTodos(filters: TodoListFilters = {}): Promise<ActivityPage<Todo>> {
  const page = filters.page ?? 1;
  const size = filters.size ?? 20;
  const response = await apiRequestEnvelope<Todo[], LegacyMeta>(listUrl("/api/v1/todos", {
    page,
    size,
    keyword: filters.keyword?.trim(),
    status: filters.status,
    entity_type: filters.entity_type,
    employee_id: filters.employee_id,
  }));
  const keyword = filters.keyword?.trim().toLocaleLowerCase() ?? "";
  return normalizePage(
    response.data,
    response.meta,
    page,
    size,
    (todo) =>
      (!filters.status || todo.status === filters.status) &&
      (!filters.entity_type || todo.entity_type === filters.entity_type) &&
      (!filters.employee_id || todo.employee_id === filters.employee_id) &&
      (!keyword || [todo.title, todo.description, todo.todo_type, todo.entity_type, todo.entity_id]
        .some((value) => includes(value, keyword))),
    (left, right) => Date.parse(right.created_at) - Date.parse(left.created_at),
  );
}

export function listTodoEmployeeOptions(
  keyword?: string,
): Promise<ActivityPage<TodoEmployeeOption>> {
  return apiRequestEnvelope<TodoEmployeeOption[], PaginationMeta>(listUrl("/api/v1/employees", {
    page: 1,
    size: 20,
    keyword: keyword?.trim(),
  }));
}

function resolveDisplayNames(
  employeeIds: string[],
  actorLabels: string[],
): Promise<ActivityDisplayNames> {
  const boundedEmployees = Array.from(new Set(employeeIds.filter(Boolean))).slice(0, 200);
  const boundedActors = Array.from(new Set(actorLabels.filter(Boolean))).slice(0, 200);
  if (boundedEmployees.length === 0 && boundedActors.length === 0) {
    return Promise.resolve({ employees: {}, actors: {} });
  }
  return apiRequest<ActivityDisplayNames>("/api/v1/directory/display-names/resolve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ employee_ids: boundedEmployees, actor_labels: boundedActors }),
  });
}

export function resolveTodoDisplayNames(todos: Todo[]): Promise<ActivityDisplayNames> {
  const employeeIds: string[] = [];
  const actorLabels: string[] = [];
  for (const todo of todos) {
    employeeIds.push(todo.employee_id);
    for (const value of [todo.created_by, todo.completed_by]) {
      if (!value) continue;
      // Older agent clients may have written a raw employee UUID while newer
      // callers use user:/key: attribution labels. Sending both projections
      // lets the tenant-scoped resolver recognize either form.
      employeeIds.push(value);
      actorLabels.push(value);
    }
  }
  return resolveDisplayNames(employeeIds, actorLabels);
}

export function resolveApprovalDisplayNames(
  approvals: ApprovalRecord[],
): Promise<ActivityDisplayNames> {
  const identifiers = approvals
    .map((approval) => approval.approver_id)
    .filter((value): value is string => Boolean(value));
  // Approval attribution can be a user:/key: label or a legacy raw employee
  // UUID, so ask both projections and let the tenant-scoped resolver decide.
  return resolveDisplayNames(identifiers, identifiers);
}

export async function listApprovalRecords(
  filters: ApprovalListFilters = {},
): Promise<ActivityPage<ApprovalRecord>> {
  const page = filters.page ?? 1;
  const size = filters.size ?? 20;
  const response = await apiRequestEnvelope<ApprovalRecord[], LegacyMeta>(listUrl("/api/v1/approval-records", {
    page,
    size,
    keyword: filters.keyword?.trim(),
    action: filters.action,
    entity_type: filters.entity_type,
    entity_id: filters.entity_id,
  }));
  const keyword = filters.keyword?.trim().toLocaleLowerCase() ?? "";
  return normalizePage(
    response.data,
    response.meta,
    page,
    size,
    (record) =>
      (!filters.action || record.action === filters.action) &&
      (!filters.entity_type || record.entity_type === filters.entity_type) &&
      (!filters.entity_id || record.entity_id === filters.entity_id) &&
      (!keyword || [record.comment, record.approver_id, record.approver_role, record.entity_type, record.entity_id]
        .some((value) => includes(value, keyword))),
    (left, right) => Date.parse(right.acted_at) - Date.parse(left.acted_at),
  );
}

export function completeTodo(id: string): Promise<Todo> {
  return apiRequest<Todo>(`/api/v1/todos/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "completed" }),
  });
}

export function isActivityForbidden(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403;
}
