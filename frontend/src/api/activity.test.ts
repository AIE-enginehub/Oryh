import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./client";
import {
  completeTodo,
  isActivityForbidden,
  listApprovalRecords,
  listTodoEmployeeOptions,
  listTodos,
  resolveApprovalDisplayNames,
  resolveTodoDisplayNames,
  type ApprovalRecord,
  type Todo,
} from "./activity";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 403 ? "Forbidden" : "OK",
    headers: new Headers({ "Content-Type": "application/json" }),
    json: async () => body,
  } as Response;
}

const todos = [
  { id: "todo-old", employee_id: "employee-1", entity_type: "project", entity_id: "project-1", title: "准备旧报告", description: "季度复盘", todo_type: "review", status: "open", due_at: null, created_by: null, metadata: {}, created_at: "2026-07-01T00:00:00Z", updated_at: null, completed_at: null, completed_by: null },
  { id: "todo-new", employee_id: "employee-1", entity_type: "project", entity_id: "project-2", title: "准备新报告", description: "季度复盘", todo_type: "review", status: "open", due_at: null, created_by: null, metadata: {}, created_at: "2026-07-03T00:00:00Z", updated_at: null, completed_at: null, completed_by: null },
  { id: "todo-done", employee_id: "employee-1", entity_type: "project", entity_id: "project-3", title: "其他事项", description: null, todo_type: null, status: "completed", due_at: null, created_by: null, metadata: {}, created_at: "2026-07-02T00:00:00Z", updated_at: null, completed_at: "2026-07-02T01:00:00Z", completed_by: "user:1" },
] as Todo[];

const approvals = [
  { id: "approval-old", entity_type: "expense_claim", entity_id: "expense-1", round_no: 1, sequence_no: 1, action: "approved", approver_id: "user:old", approver_role: "manager", comment: "预算内", source: "web", metadata: {}, acted_at: "2026-07-01T00:00:00Z", created_at: "2026-07-01T00:00:00Z" },
  { id: "approval-new", entity_type: "expense_claim", entity_id: "expense-2", round_no: 1, sequence_no: 2, action: "approved", approver_id: "user:new", approver_role: "manager", comment: "预算内，同意", source: "api", metadata: {}, acted_at: "2026-07-03T00:00:00Z", created_at: "2026-07-03T00:00:00Z" },
  { id: "approval-rejected", entity_type: "purchase_request", entity_id: "purchase-1", round_no: 1, sequence_no: 1, action: "rejected", approver_id: "user:2", approver_role: "finance", comment: "超预算", source: "web", metadata: {}, acted_at: "2026-07-02T00:00:00Z", created_at: "2026-07-02T00:00:00Z" },
] as ApprovalRecord[];

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "oryh_csrf=; Max-Age=0; Path=/";
});

describe("activity API compatibility", () => {
  it("filters, sorts and paginates a legacy todo envelope without page metadata", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: todos, meta: { total: 3 } }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await listTodos({ page: 2, size: 1, keyword: "报告", status: "open", entity_type: "project", employee_id: "employee-1" });

    expect(fetchMock.mock.calls[0][0]).toContain("/api/v1/todos?");
    expect(fetchMock.mock.calls[0][0]).toContain("page=2");
    expect(fetchMock.mock.calls[0][0]).toContain("keyword=%E6%8A%A5%E5%91%8A");
    expect(fetchMock.mock.calls[0][0]).toContain("employee_id=employee-1");
    expect(result.meta).toEqual({ total: 2, page: 2, page_size: 1, pages: 2 });
    expect(result.data.map((todo) => todo.id)).toEqual(["todo-old"]);
  });

  it("uses bounded employee search and resolves todo identity references", async () => {
    document.cookie = "oryh_csrf=todo-names-token; Path=/";
    const ownerId = "11111111-1111-4111-8111-111111111111";
    const userId = "22222222-2222-4222-8222-222222222222";
    const completerId = "33333333-3333-4333-8333-333333333333";
    const referencedTodo = {
      ...todos[2],
      employee_id: ownerId,
      created_by: `user:${userId}`,
      completed_by: completerId,
    } as Todo;
    const fetchMock = vi.fn().mockImplementation((input: string, init?: RequestInit) => {
      const request = new URL(input, "https://console.example");
      if (request.pathname === "/api/v1/employees") {
        return Promise.resolve(jsonResponse({
          data: [{ id: completerId, employee_code: "E-003", name: "Manager Mike", status: "active" }],
          meta: { total: 1, page: 1, page_size: 20, pages: 1 },
        }));
      }
      if (request.pathname === "/api/v1/directory/display-names/resolve") {
        expect(JSON.parse(String(init?.body))).toEqual({
          employee_ids: [ownerId, `user:${userId}`, completerId],
          actor_labels: [`user:${userId}`, completerId],
        });
        return Promise.resolve(jsonResponse({
          data: { employees: { [ownerId]: "Todo Owner", [completerId]: "Manager Mike" }, actors: { [`user:${userId}`]: "租户经理" } },
          meta: {},
        }));
      }
      throw new Error(`Unexpected URL ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(listTodoEmployeeOptions("  Manager  ")).resolves.toEqual({
      data: [{ id: completerId, employee_code: "E-003", name: "Manager Mike", status: "active" }],
      meta: { total: 1, page: 1, page_size: 20, pages: 1 },
    });
    const employeeRequest = new URL(String(fetchMock.mock.calls[0][0]), "https://console.example");
    expect(Object.fromEntries(employeeRequest.searchParams)).toEqual({ page: "1", size: "20", keyword: "Manager" });

    await expect(resolveTodoDisplayNames([referencedTodo])).resolves.toEqual({
      employees: { [ownerId]: "Todo Owner", [completerId]: "Manager Mike" },
      actors: { [`user:${userId}`]: "租户经理" },
    });
    const resolverHeaders = new Headers((fetchMock.mock.calls[1][1] as RequestInit).headers);
    expect(resolverHeaders.get("X-CSRF-Token")).toBe("todo-names-token");
  });

  it("locally adapts approval action and keyword filters for a legacy envelope", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ data: approvals, meta: { total: 3 } })));

    const result = await listApprovalRecords({ page: 1, size: 10, keyword: "预算内", action: "approved", entity_type: "expense_claim" });

    expect(result.meta.total).toBe(2);
    expect(result.data.map((record) => record.id)).toEqual(["approval-new", "approval-old"]);
  });

  it("resolves approval actors through both actor and legacy employee projections", async () => {
    document.cookie = "oryh_csrf=approval-names-token; Path=/";
    const fetchMock = vi.fn().mockImplementation((_input: string, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toEqual({
        employee_ids: ["user:new", "user:old"],
        actor_labels: ["user:new", "user:old"],
      });
      return Promise.resolve(jsonResponse({
        data: { employees: {}, actors: { "user:new": "New Approver", "user:old": "Old Approver" } },
        meta: {},
      }));
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(resolveApprovalDisplayNames([approvals[1], approvals[0]])).resolves.toEqual({
      employees: {},
      actors: { "user:new": "New Approver", "user:old": "Old Approver" },
    });
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/directory/display-names/resolve");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("approval-names-token");
  });

  it("preserves complete server pagination metadata when the backend provides it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      data: [todos[0]],
      meta: { total: 41, page: 3, page_size: 20, pages: 3 },
    })));

    const result = await listTodos({ page: 3, size: 20 });
    expect(result.meta).toEqual({ total: 41, page: 3, page_size: 20, pages: 3 });
    expect(result.data).toEqual([todos[0]]);
  });

  it("completes a todo with a CSRF-protected PATCH and identifies forbidden errors", async () => {
    document.cookie = "oryh_csrf=csrf-token; Path=/";
    const completed = { ...todos[0], status: "completed" } as Todo;
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: completed, meta: {} }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(completeTodo("todo/unsafe")).resolves.toEqual(completed);
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/todos/todo%2Funsafe");
    expect(init.method).toBe("PATCH");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-token");
    expect(JSON.parse(String(init.body))).toEqual({ status: "completed" });
    expect(isActivityForbidden(new ApiError(403, "forbidden"))).toBe(true);
    expect(isActivityForbidden(new ApiError(500, "failed"))).toBe(false);
  });
});
