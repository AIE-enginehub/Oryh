import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 401 ? "Unauthorized" : "OK",
    headers: new Headers({ "Content-Type": "application/json" }),
    json: async () => body,
  } as Response;
}

function renderApp(path = "/dashboard") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  document.cookie = "oryh_csrf=; Max-Age=0; Path=/";
  vi.unstubAllGlobals();
});

beforeEach(() => {
  window.localStorage.setItem("oryh.console.language", "zh-CN");
});

describe("tenant console shell", () => {
  it("switches the login console to English and persists the choice", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "browser session required" }, 401)),
    );
    const user = userEvent.setup();

    renderApp();

    await screen.findByRole("heading", { name: "登录工作空间" });
    await user.selectOptions(screen.getByRole("combobox", { name: "语言" }), "en");

    expect(screen.getByRole("heading", { name: "Sign in to your workspace" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open console" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download agent connector skill" })).toHaveAttribute("href", "/api/v1/connect-skill");
    expect(document.documentElement.lang).toBe("en");
    expect(window.localStorage.getItem("oryh.console.language")).toBe("en");
  });

  it("renders authenticated dashboard content in English", async () => {
    window.localStorage.setItem("oryh.console.language", "en");
    document.cookie = "oryh_csrf=existing; Path=/";
    vi.stubGlobal("fetch", vi.fn((path: string) => {
      if (path === "/api/v1/console/bootstrap") {
        return Promise.resolve(jsonResponse({
          data: {
            user: { id: "user-en", email: "english@acme.example", name: "English User" },
            tenant: { id: "tenant-1", name: "Acme Corp", email_domain: "acme.example" },
            role: "admin",
            permissions: ["users.manage", "master_data.manage"],
            employee_id: null,
          },
          meta: {},
        }));
      }
      return Promise.resolve(jsonResponse({
        data: { counts: { users: 3, todos_open: 2, todos_overdue: 1, objects: 4, skills: 5 } },
        meta: {},
      }));
    }));

    renderApp();

    expect(await screen.findByRole("heading", { name: "Workspace overview" })).toBeInTheDocument();
    expect(screen.getByText("Active users")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Continue managing your workspace" })).toBeInTheDocument();
    expect(screen.queryByText("租户运行概况")).not.toBeInTheDocument();
  });

  it("offers the connector download on the dashboard of a member with no admin capabilities", async () => {
    document.cookie = "oryh_csrf=existing; Path=/";
    vi.stubGlobal("fetch", vi.fn((path: string) => {
      if (path === "/api/v1/console/bootstrap") {
        return Promise.resolve(jsonResponse({
          data: {
            user: { id: "user-member", email: "member@acme.example", name: "Member User" },
            tenant: { id: "tenant-1", name: "Acme Corp", email_domain: "acme.example" },
            role: "member",
            permissions: [],
            employee_id: "employee-1",
          },
          meta: {},
        }));
      }
      return Promise.resolve(jsonResponse({
        data: { counts: { users: 3, todos_open: 2, todos_overdue: 1, objects: 4, skills: 5 } },
        meta: {},
      }));
    }));

    renderApp();

    expect(await screen.findByRole("heading", { name: "把你的 Agent 接入 Oryh" })).toBeInTheDocument();
    const download = screen.getByRole("link", { name: /下载 Agent 连接 Skill/ });
    expect(download).toHaveAttribute("href", "/api/v1/connect-skill");
    expect(download).toHaveAttribute("download");
    expect(screen.getByRole("link", { name: "查看安装说明" })).toHaveAttribute("href", "/web/connect");
    // a plain member sees no management shortcuts, so the download must not be gated behind one
    expect(screen.queryByRole("link", { name: /用户与邀请/ })).not.toBeInTheDocument();
  });

  it("redirects an unauthenticated browser session to login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "browser session required" }, 401)),
    );

    renderApp();

    expect(await screen.findByRole("heading", { name: "登录工作空间" })).toBeInTheDocument();
    const connectorDownload = screen.getByRole("link", { name: "下载 Agent 连接 Skill" });
    expect(connectorDownload).toHaveAttribute("href", "/api/v1/connect-skill");
    expect(connectorDownload).toHaveAttribute("download");
    expect(screen.queryByText(/PostgreSQL/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "忘记密码？" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "使用旧版登录" })).not.toBeInTheDocument();
  });

  it("requests a private password-reset email from the login page", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      data: {
        message: "if an active account exists for this email, a password reset link has been sent",
      },
      meta: {},
    }, 202));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderApp("/login?mode=reset");

    expect(screen.getByRole("heading", { name: "重置密码" })).toBeInTheDocument();
    expect(screen.queryByLabelText("密码")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("企业邮箱"), "alice@acme.example");
    await user.click(screen.getByRole("button", { name: "发送重置链接" }));

    expect(await screen.findByRole("status")).toHaveTextContent("如果该邮箱对应可用账号");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/password-reset-email",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "alice@acme.example" }),
      }),
    );
    await user.click(screen.getByRole("button", { name: "返回登录" }));
    expect(screen.getByRole("heading", { name: "登录工作空间" })).toBeInTheDocument();
  });

  it("renders an authenticated unknown route as a real not-found page", async () => {
    document.cookie = "oryh_csrf=existing; Path=/";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      data: {
        user: { id: "user-404", email: "lost@acme.example", name: "Lost User" },
        tenant: { id: "tenant-1", name: "Acme Corp", email_domain: "acme.example" },
        role: "member",
        permissions: [],
        employee_id: null,
      },
      meta: {},
    }));
    vi.stubGlobal("fetch", fetchMock);

    renderApp("/objects/report/123/extra?source=bookmark");

    expect(await screen.findByRole("heading", { name: "页面不存在", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "页面不存在", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("/objects/report/123/extra?source=bookmark")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalledWith("/api/v1/console/dashboard", expect.anything());
  });

  it("returns to the full pathname and search after login", async () => {
    let bootstrapCalls = 0;
    const fetchMock = vi.fn().mockImplementation((path: string) => {
      if (path === "/api/v1/console/bootstrap") {
        bootstrapCalls += 1;
        if (bootstrapCalls === 1) {
          return Promise.resolve(jsonResponse({ detail: "browser session required" }, 401));
        }
        return Promise.resolve(jsonResponse({
          data: {
            user: { id: "user-return", email: "return@acme.example", name: "Return User" },
            tenant: { id: "tenant-1", name: "Acme Corp", email_domain: "acme.example" },
            role: "member",
            permissions: [],
            employee_id: null,
          },
          meta: {},
        }));
      }
      if (path === "/api/v1/auth/browser/login") {
        document.cookie = "oryh_csrf=after-login; Path=/";
        return Promise.resolve(jsonResponse({ data: {}, meta: {} }));
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderApp("/missing/report?source=invite&attempt=2");
    await screen.findByRole("heading", { name: "登录工作空间" });
    await user.type(screen.getByLabelText("企业邮箱"), "return@acme.example");
    await user.type(screen.getByLabelText("密码"), "password-1");
    await user.click(screen.getByRole("button", { name: "进入控制台" }));

    expect(await screen.findByRole("heading", { name: "页面不存在", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("/missing/report?source=invite&attempt=2")).toBeInTheDocument();
    expect(bootstrapCalls).toBe(2);
  });

  it("renders tenant identity and dashboard projection", async () => {
    document.cookie = "oryh_csrf=existing; Path=/";
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/v1/console/bootstrap") {
        return Promise.resolve(
          jsonResponse({
            data: {
              user: { id: "user-1", email: "owner@acme.example", name: "Alice" },
              tenant: { id: "tenant-1", name: "Acme Corp", email_domain: "acme.example" },
              role: "admin",
              permissions: ["users.manage"],
              employee_id: null,
            },
            meta: {},
          }),
        );
      }
      return Promise.resolve(
        jsonResponse({
          data: {
            counts: { users: 12, todos_open: 5, todos_overdue: 2, objects: 48, skills: 7 },
          },
          meta: {},
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderApp();

    expect(await screen.findByText("Acme Corp")).toBeInTheDocument();
    expect(await screen.findByTestId("metric-users")).toHaveTextContent("12");
    expect(screen.getByTestId("metric-todos_overdue")).toHaveTextContent("2");
    expect(document.body).not.toHaveTextContent(/React|PostgreSQL|\bSQL\b|\bRLS\b|\bRBAC\b|HttpOnly|JSON Schema|\bAPI\b|backend|server-rendered/i);
  });

  it("blocks a direct master-data route without a management capability", async () => {
    document.cookie = "oryh_csrf=existing; Path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: {
          user: { id: "user-2", email: "member@acme.example", name: "Member" },
          tenant: { id: "tenant-1", name: "Acme Corp", email_domain: "acme.example" },
          role: "member",
          permissions: [],
          employee_id: null,
        },
        meta: {},
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderApp("/projects");

    expect(await screen.findByRole("heading", { name: "无法访问主数据管理" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("allows a direct master-data route with master_data.manage", async () => {
    document.cookie = "oryh_csrf=existing; Path=/";
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/v1/console/bootstrap") {
        return Promise.resolve(jsonResponse({
          data: {
            user: { id: "user-3", email: "operator@acme.example", name: "Operator" },
            tenant: { id: "tenant-1", name: "Acme Corp", email_domain: "acme.example" },
            role: "member",
            permissions: ["master_data.manage"],
            employee_id: null,
          },
          meta: {},
        }));
      }
      return Promise.resolve(jsonResponse({ data: [], meta: { total: 0, page: 1, page_size: 20, pages: 1 } }));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderApp("/projects");

    expect(await screen.findByRole("heading", { name: "项目主数据" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([path]) => String(path).startsWith("/api/v1/projects?"))).toBe(true);
  });

  it("blocks a direct employee route when employees.manage was removed", async () => {
    document.cookie = "oryh_csrf=existing; Path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: {
          user: { id: "user-4", email: "admin@acme.example", name: "Admin" },
          tenant: { id: "tenant-1", name: "Acme Corp", email_domain: "acme.example" },
          role: "admin",
          permissions: ["users.manage"],
          employee_id: null,
        },
        meta: {},
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderApp("/employees");

    expect(await screen.findByRole("heading", { name: "无法访问员工管理" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("blocks direct identity routes without users.manage", async () => {
    document.cookie = "oryh_csrf=existing; Path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: {
          user: { id: "user-6", email: "member@acme.example", name: "Member" },
          tenant: { id: "tenant-1", name: "Acme Corp", email_domain: "acme.example" },
          role: "member",
          permissions: ["employees.manage"],
          employee_id: null,
        },
        meta: {},
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderApp("/users");

    expect(
      await screen.findByRole("heading", { name: "无法访问身份与权限管理" }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("allows a direct employee route with employees.manage", async () => {
    document.cookie = "oryh_csrf=existing; Path=/";
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/v1/console/bootstrap") {
        return Promise.resolve(jsonResponse({
          data: {
            user: { id: "user-5", email: "people@acme.example", name: "People Ops" },
            tenant: { id: "tenant-1", name: "Acme Corp", email_domain: "acme.example" },
            role: "people_ops",
            permissions: ["employees.manage"],
            employee_id: null,
          },
          meta: {},
        }));
      }
      return Promise.resolve(jsonResponse({
        data: [],
        meta: { total: 0, page: 1, page_size: 20, pages: 1 },
      }));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderApp("/employees");

    expect(await screen.findByRole("heading", { name: "员工档案" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([path]) => String(path).startsWith("/api/v1/employees?"))).toBe(true);
  });

  it("allows a workflow publisher to open object configuration without users.manage", async () => {
    document.cookie = "oryh_csrf=existing; Path=/";
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/v1/console/bootstrap") {
        return Promise.resolve(jsonResponse({
          data: {
            user: { id: "user-7", email: "flow@acme.example", name: "Flow Owner" },
            tenant: { id: "tenant-1", name: "Acme Corp", email_domain: "acme.example" },
            role: "flow_owner",
            permissions: ["workflows.publish"],
            employee_id: null,
          },
          meta: {},
        }));
      }
      return Promise.resolve(jsonResponse({ data: [], meta: { total: 0, page: 1, page_size: 20, pages: 1 } }));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderApp("/object-types");

    expect(await screen.findByTestId("object-types-page")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "发布流程" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "定义类型" })).not.toBeInTheDocument();
  });

  it("blocks access-credential management without keys.manage even for a customized admin role", async () => {
    document.cookie = "oryh_csrf=existing; Path=/";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      data: {
        user: { id: "user-8", email: "admin@acme.example", name: "Admin" },
        tenant: { id: "tenant-1", name: "Acme Corp", email_domain: "acme.example" },
        role: "admin",
        permissions: ["users.manage"],
        employee_id: "employee-8",
      },
      meta: {},
    }));
    vi.stubGlobal("fetch", fetchMock);

    renderApp("/api-keys");

    expect(await screen.findByRole("heading", { name: "无法访问访问凭证管理" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
