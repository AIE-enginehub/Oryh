import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ConsoleContext } from "../App";
import { ApiError } from "../api/client";
import type { ApprovalRecord, Todo } from "../api/activity";
import { ApprovalsPage } from "./ApprovalsPage";
import { TodosPage } from "./TodosPage";

const api = vi.hoisted(() => ({
  listTodos: vi.fn(),
  completeTodo: vi.fn(),
  listTodoEmployeeOptions: vi.fn(),
  resolveTodoDisplayNames: vi.fn(),
  listApprovalRecords: vi.fn(),
  resolveApprovalDisplayNames: vi.fn(),
}));

vi.mock("../api/activity", async () => {
  const actual = await vi.importActual<typeof import("../api/activity")>("../api/activity");
  return { ...actual, ...api };
});

const todo = {
  id: "todo-1",
  employee_id: "employee-1",
  entity_type: "expense_claim",
  entity_id: "expense-1",
  title: "补充报销票据",
  description: "请上传清晰发票",
  todo_type: "document",
  status: "open",
  due_at: "2026-07-20T09:00:00Z",
  created_by: "user:manager",
  metadata: {},
  created_at: "2026-07-10T09:00:00Z",
  updated_at: null,
  completed_at: null,
  completed_by: null,
} as Todo;

const approval = {
  id: "approval-1",
  entity_type: "expense_claim",
  entity_id: "expense-1",
  round_no: 2,
  sequence_no: 1,
  action: "approved",
  approver_id: "user:finance",
  approver_role: "finance_manager",
  comment: "票据齐全，同意报销",
  source: "web",
  metadata: {},
  acted_at: "2026-07-11T09:30:00Z",
  created_at: "2026-07-11T09:30:00Z",
} as ApprovalRecord;

function renderPage(page: "todos" | "approvals", options?: { permissions?: string[]; employeeId?: string | null; role?: string }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const context = {
    bootstrap: {
      user: { id: "user-1", email: "member@example.com", name: "Member" },
      tenant: { id: "tenant-1", name: "Acme", email_domain: "acme.example" },
      role: options?.role ?? "member",
      permissions: options?.permissions ?? ["todos.complete_own"],
      employee_id: options?.employeeId === undefined ? "employee-1" : options.employeeId,
    },
  } as ConsoleContext;
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Routes><Route element={<Outlet context={context} />}><Route index element={page === "todos" ? <TodosPage /> : <ApprovalsPage />} /></Route></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listTodos.mockImplementation(({ page = 1 }: { page?: number }) => Promise.resolve({
    data: [todo],
    meta: { total: 21, page, page_size: 20, pages: 2 },
  }));
  api.completeTodo.mockResolvedValue({ ...todo, status: "completed" });
  api.listTodoEmployeeOptions.mockResolvedValue({
    data: [{ id: "employee-2", employee_code: "E-002", name: "Manager Mike", status: "active" }],
    meta: { total: 1, page: 1, page_size: 20, pages: 1 },
  });
  api.resolveTodoDisplayNames.mockResolvedValue({
    employees: { "employee-1": "王琳" },
    actors: { "user:manager": "租户经理" },
  });
  api.listApprovalRecords.mockImplementation(({ page = 1 }: { page?: number }) => Promise.resolve({
    data: [approval],
    meta: { total: 21, page, page_size: 20, pages: 2 },
  }));
  api.resolveApprovalDisplayNames.mockResolvedValue({
    employees: {},
    actors: { "user:finance": "财务负责人" },
  });
});

afterEach(cleanup);

describe("todo activity page", () => {
  it("scopes members, sends filters/pages, and completes an owned todo", async () => {
    const user = userEvent.setup();
    renderPage("todos");
    expect(await screen.findByText("补充报销票据")).toBeInTheDocument();
    expect(await screen.findByText("我 · 王琳")).toBeInTheDocument();
    expect(await screen.findByText("租户经理")).toBeInTheDocument();
    expect(api.listTodos).toHaveBeenCalledWith(expect.objectContaining({ employee_id: "employee-1" }));

    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listTodos).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));
    await user.type(screen.getByRole("searchbox"), "票据");
    await user.selectOptions(screen.getByLabelText("状态"), "open");
    await user.selectOptions(screen.getByLabelText("对象类型"), "expense_claim");
    await user.click(screen.getByRole("button", { name: "筛选" }));
    await waitFor(() => expect(api.listTodos).toHaveBeenCalledWith(expect.objectContaining({ page: 1, keyword: "票据", status: "open", entity_type: "expense_claim" })));

    await user.click(screen.getByRole("button", { name: "完成“补充报销票据”" }));
    const confirm = screen.getByRole("alertdialog");
    expect(within(confirm).getByText(/写入审计记录/)).toBeInTheDocument();
    await user.click(within(confirm).getByRole("button", { name: "确认完成" }));
    await waitFor(() => expect(api.completeTodo).toHaveBeenCalledWith("todo-1"));
  });

  it("lets administrators search a bounded employee picker and filter by employee_id", async () => {
    const user = userEvent.setup();
    renderPage("todos", {
      role: "admin",
      permissions: ["todos.complete_own", "tenant.act_for_any_employee"],
      employeeId: "employee-admin",
    });
    expect(await screen.findByText("补充报销票据")).toBeInTheDocument();
    expect(api.listTodoEmployeeOptions).toHaveBeenCalledWith(undefined);

    await user.type(screen.getByLabelText("查找负责人"), "Manager");
    await user.click(screen.getByRole("button", { name: "搜索员工" }));
    await waitFor(() => expect(api.listTodoEmployeeOptions).toHaveBeenCalledWith("Manager"));
    await user.selectOptions(screen.getByLabelText("负责人筛选"), "employee-2");
    await waitFor(() => expect(api.listTodos).toHaveBeenCalledWith(expect.objectContaining({
      page: 1,
      employee_id: "employee-2",
    })));
    expect(screen.getByRole("option", { name: "Manager Mike · E-002" })).toBeInTheDocument();
  });

  it("resolves raw employee completion attribution and keeps actor fallbacks on lookup failure", async () => {
    api.listTodos.mockResolvedValueOnce({
      data: [{ ...todo, status: "completed", completed_at: "2026-07-12T09:00:00Z", completed_by: "employee-1" }],
      meta: { total: 1, page: 1, page_size: 20, pages: 1 },
    });
    const resolved = renderPage("todos");
    expect(await screen.findByText("租户经理")).toBeInTheDocument();
    expect(screen.getByText("王琳")).toBeInTheDocument();
    expect(api.resolveTodoDisplayNames).toHaveBeenCalledWith([
      expect.objectContaining({ employee_id: "employee-1", created_by: "user:manager", completed_by: "employee-1" }),
    ]);
    resolved.unmount();

    api.resolveTodoDisplayNames.mockRejectedValueOnce(new Error("resolver unavailable"));
    renderPage("todos");
    expect(await screen.findByText(/名称解析暂时不可用/)).toBeInTheDocument();
    expect(screen.getByText("user:manager")).toBeInTheDocument();
  });

  it("shows read-only and missing-employee restrictions without hiding facts", async () => {
    const first = renderPage("todos", { permissions: [] });
    expect(await screen.findByText("当前为只读模式")).toBeInTheDocument();
    await screen.findByText("补充报销票据");
    expect(screen.getByRole("button", { name: "完成“补充报销票据”" })).toBeDisabled();
    first.unmount();

    api.listTodos.mockClear();
    renderPage("todos", { permissions: [], employeeId: null });
    expect(await screen.findByText("账号尚未关联员工档案")).toBeInTheDocument();
    expect(api.listTodos).not.toHaveBeenCalled();
  });

  it("handles loading, empty, errors, and forbidden access", async () => {
    api.listTodos.mockReturnValueOnce(new Promise(() => {}));
    const pending = renderPage("todos");
    expect(screen.getByText("正在加载数据…")).toBeInTheDocument();
    pending.unmount();

    api.listTodos.mockResolvedValueOnce({ data: [], meta: { total: 0, page: 1, page_size: 20, pages: 1 } });
    const empty = renderPage("todos");
    expect(await screen.findByText("当前没有待办")).toBeInTheDocument();
    empty.unmount();

    api.listTodos.mockRejectedValueOnce(new Error("待办服务暂时不可用"));
    const failed = renderPage("todos");
    expect(await screen.findByText("数据加载失败")).toBeInTheDocument();
    expect(screen.getByText("待办服务暂时不可用")).toBeInTheDocument();
    failed.unmount();

    api.listTodos.mockRejectedValueOnce(new ApiError(403, "forbidden"));
    renderPage("todos");
    expect(await screen.findByText("无法访问待办")).toBeInTheDocument();
  });
});

describe("approval records page", () => {
  it("filters and pages immutable approval facts", async () => {
    const user = userEvent.setup();
    renderPage("approvals");
    expect(await screen.findByText("票据齐全，同意报销")).toBeInTheDocument();
    expect(await screen.findByText("财务负责人")).toBeInTheDocument();
    expect(screen.getByText("user:finance")).toBeInTheDocument();
    expect(api.resolveApprovalDisplayNames).toHaveBeenCalledWith([
      expect.objectContaining({ approver_id: "user:finance" }),
    ]);
    expect(screen.getByText("只读审计视图")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /编辑|删除|归档/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(api.listApprovalRecords).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })));
    await user.type(screen.getByRole("searchbox"), "finance");
    await user.selectOptions(screen.getByLabelText("动作"), "approved");
    await user.selectOptions(screen.getByLabelText("对象类型"), "expense_claim");
    await user.click(screen.getByRole("button", { name: "筛选" }));
    await waitFor(() => expect(api.listApprovalRecords).toHaveBeenCalledWith(expect.objectContaining({ page: 1, keyword: "finance", action: "approved", entity_type: "expense_claim" })));
  });

  it("falls back to the approver ID when display-name resolution fails", async () => {
    api.resolveApprovalDisplayNames.mockRejectedValueOnce(new Error("resolver unavailable"));
    renderPage("approvals");

    expect(await screen.findByText(/操作者名称解析暂时不可用/)).toBeInTheDocument();
    expect(screen.getByText("user:finance")).toBeInTheDocument();
  });

  it("shows approval loading, empty, error, and forbidden states", async () => {
    api.listApprovalRecords.mockReturnValueOnce(new Promise(() => {}));
    const pending = renderPage("approvals");
    expect(screen.getByText("正在加载数据…")).toBeInTheDocument();
    pending.unmount();

    api.listApprovalRecords.mockResolvedValueOnce({ data: [], meta: { total: 0, page: 1, page_size: 20, pages: 1 } });
    const empty = renderPage("approvals");
    expect(await screen.findByText("还没有审批记录")).toBeInTheDocument();
    empty.unmount();

    api.listApprovalRecords.mockRejectedValueOnce(new Error("审批服务暂时不可用"));
    const failed = renderPage("approvals");
    expect(await screen.findByText("数据加载失败")).toBeInTheDocument();
    expect(screen.getByText("审批服务暂时不可用")).toBeInTheDocument();
    failed.unmount();

    api.listApprovalRecords.mockRejectedValueOnce(new ApiError(403, "forbidden"));
    renderPage("approvals");
    expect(await screen.findByText("无法访问审批记录")).toBeInTheDocument();
  });
});
