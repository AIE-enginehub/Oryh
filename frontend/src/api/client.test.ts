import { afterEach, describe, expect, it, vi } from "vitest";

import {
  apiRequest,
  apiRequestEnvelope,
  archiveProduct,
  archiveProductSku,
  archiveProject,
  archiveResource,
  archiveVendor,
  batchCreateProductSkus,
  bootstrap,
  createCapability,
  createEmployee,
  createProduct,
  createProductSku,
  createProject,
  createResource,
  createRole,
  createVendor,
  deleteCapability,
  deleteRole,
  inviteUser,
  generateUserSkillBundle,
  getEmployee,
  listCapabilities,
  listEmployees,
  listProducts,
  listProductSkus,
  listProjects,
  listResources,
  listRoles,
  listUsers,
  listVendors,
  login,
  updateEmployee,
  updateProduct,
  updateProductSku,
  updateProject,
  updateResource,
  updateRole,
  updateUser,
  updateVendor,
  resendInvitation,
  sendPasswordResetEmail,
} from "./client";

function jsonResponse(body: unknown, status = 200): Response {
  const serialized = JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "Content-Type": "application/json" }),
    json: async () => body,
    text: async () => serialized,
  } as Response;
}

function noContentResponse(): Response {
  return {
    ok: true,
    status: 204,
    headers: new Headers(),
    json: async () => undefined,
    text: async () => "",
  } as Response;
}

afterEach(() => {
  document.cookie = "oryh_csrf=; Max-Age=0; Path=/";
  vi.unstubAllGlobals();
});

describe("console API client", () => {
  it("logs in with a same-origin cookie request and unwraps the response", async () => {
    const payload = {
      user: {
        id: "user-1",
        tenant_id: "tenant-1",
        employee_id: null,
        email: "owner@example.com",
        name: "Owner",
        role: "tenant_admin",
        is_active: true,
        email_verified_at: "2026-07-11T08:00:00Z",
        created_at: "2026-07-11T08:00:00Z",
      },
      expires_at: "2026-07-12T08:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: payload, meta: {} }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      login({ email: "owner@example.com", password: "correct horse" }),
    ).resolves.toEqual(payload);

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/browser/login");
    expect(init).toMatchObject({ method: "POST", credentials: "include" });
    expect(new Headers(init.headers).get("Content-Type")).toBe(
      "application/json",
    );
    expect(JSON.parse(String(init.body))).toEqual({
      email: "owner@example.com",
      password: "correct horse",
    });
  });

  it("copies the decoded CSRF cookie into unsafe API requests", async () => {
    document.cookie = "oryh_csrf=csrf%2Btoken%2Fvalue; Path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { saved: true }, meta: {} }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      apiRequest<{ saved: boolean }>("/api/v1/example", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: true }),
      }),
    ).resolves.toEqual({ saved: true });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe(
      "csrf+token/value",
    );
  });

  it("can retain response metadata without changing data-only requests", async () => {
    const meta = { total: 23, page: 2, page_size: 10, pages: 3 };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ data: ["first"], meta }))
      .mockResolvedValueOnce(jsonResponse({ data: ["second"], meta }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      apiRequestEnvelope<string[], typeof meta>("/api/v1/items?page=2"),
    ).resolves.toEqual({ data: ["first"], meta });
    await expect(apiRequest<string[]>("/api/v1/items?page=2")).resolves.toEqual([
      "second",
    ]);
  });

  it("loads bootstrap and upgrades a legacy session with a CSRF cookie", async () => {
    const payload = {
      user: { id: "user-1", email: "owner@example.com", name: "Owner" },
      tenant: {
        id: "tenant-1",
        name: "Example tenant",
        email_domain: "example.com",
      },
      role: "tenant_admin",
      permissions: ["users.manage"],
      employee_id: null,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ data: payload, meta: {} }))
      .mockResolvedValueOnce(
        jsonResponse({ data: { csrf_token: "fresh-token" }, meta: {} }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(bootstrap()).resolves.toEqual(payload);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]).toEqual([
      "/api/v1/console/bootstrap",
      expect.objectContaining({ credentials: "include" }),
    ]);
    expect(fetchMock.mock.calls[1]).toEqual([
      "/api/v1/auth/browser/csrf",
      expect.objectContaining({ method: "GET", credentials: "include" }),
    ]);
  });

  it("does not rotate CSRF when bootstrap finds an existing cookie", async () => {
    document.cookie = "oryh_csrf=existing-token; Path=/";
    const payload = {
      user: { id: "user-1", email: "owner@example.com", name: null },
      tenant: { id: "tenant-1", name: "Example tenant", email_domain: null },
      role: "tenant_admin",
      permissions: [],
      employee_id: null,
    };
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: payload, meta: {} }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(bootstrap()).resolves.toEqual(payload);

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/console/bootstrap");
  });

  it("lists projects with encoded filters and retains pagination metadata", async () => {
    const project = {
      id: "project-1",
      project_name: "Alpha & Beta",
      status: "active",
    };
    const meta = { total: 51, page: 2, page_size: 25, pages: 3 };
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: [project], meta }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      listProjects({
        page: 2,
        size: 25,
        keyword: "  Alpha & Beta  ",
        status: "active",
      }),
    ).resolves.toEqual({ data: [project], meta });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/projects?page=2&size=25&keyword=Alpha+%26+Beta&status=active",
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
  });

  it("defaults list pagination so the response always has complete metadata", async () => {
    const meta = { total: 0, page: 1, page_size: 50, pages: 1 };
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: [], meta }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(listProjects({ keyword: "   " })).resolves.toEqual({
      data: [],
      meta,
    });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/projects?page=1&size=50");
  });

  it("builds vendor filters and omits undefined or empty values", async () => {
    const meta = { total: 0, page: 1, page_size: 50, pages: 1 };
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: [], meta }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      listVendors({
        page: 1,
        size: 50,
        keyword: "   ",
        status: undefined,
        tax_id: "  9131 0000/ABC  ",
      }),
    ).resolves.toEqual({ data: [], meta });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/vendors?page=1&size=50&tax_id=9131+0000%2FABC",
    );
  });

  it("builds resource type and booking-mode filters", async () => {
    const meta = { total: 4, page: 1, page_size: 20, pages: 1 };
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: [], meta }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await listResources({
      page: 1,
      size: 20,
      keyword: "Jade room",
      status: "active",
      resource_type: "meeting room",
      booking_mode: "exclusive",
    });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/resources?page=1&size=20&keyword=Jade+room&status=active&resource_type=meeting+room&booking_mode=exclusive",
    );
  });

  it("builds product, SKU, and employee pagination filters", async () => {
    const meta = { total: 3, page: 2, page_size: 20, pages: 2 };
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: [], meta }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await listProducts({ page: 2, size: 20, keyword: "  显示器  ", status: "active" });
    await listProductSkus({
      page: 1,
      size: 25,
      product_id: "product/1",
      sku_code: " SKU XL ",
      status: "archived",
    });
    await listEmployees({ page: 3, size: 10, keyword: "  王  ", status: "inactive" });

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/products?page=2&size=20&keyword=%E6%98%BE%E7%A4%BA%E5%99%A8&status=active",
      "/api/v1/product-skus?page=1&size=25&product_id=product%2F1&sku_code=SKU+XL&status=archived",
      "/api/v1/employees?page=3&size=10&keyword=%E7%8E%8B&status=inactive",
    ]);
  });

  it("creates a CSRF-protected batch of product SKUs for an encoded product", async () => {
    document.cookie = "oryh_csrf=batch-token; Path=/";
    const created = [{ id: "sku-1", product_id: "product/1", sku_code: "P-1-S", variant_attrs: { 尺码: "S" } }];
    const result = { created, skipped: ["M"] };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: result, meta: {} }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(batchCreateProductSkus("product/1", {
      dimension: "尺码",
      values: ["S", "M"],
      list_price: 129.9,
    })).resolves.toEqual(result);

    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/products/product%2F1/skus/batch");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("batch-token");
    expect(JSON.parse(String(init.body))).toEqual({
      dimension: "尺码",
      values: ["S", "M"],
      list_price: 129.9,
    });
  });

  it("loads one employee option by its encoded identifier", async () => {
    const employee = { id: "employee/1", name: "王小明", status: "active" };
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: employee, meta: {} }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getEmployee("employee/1")).resolves.toEqual(employee);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/employees/employee%2F1");
  });

  it("filters users and keeps invitation links in the one-time response", async () => {
    document.cookie = "oryh_csrf=access-token; Path=/";
    const meta = { total: 7, page: 2, page_size: 20, pages: 2 };
    const invited = {
      id: "user/1",
      email: "invitee@example.com",
      status: "invited",
      role: "member",
      invitation_url: "http://console.example/web/invitations/accept?token=secret",
    };
    const updated = { ...invited, name: "Invitee", invitation_url: undefined };
    const passwordReset = {
      user: updated,
      email_sent: true,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ data: [invited], meta }))
      .mockResolvedValueOnce(jsonResponse({ data: invited, meta: {} }, 201))
      .mockResolvedValueOnce(jsonResponse({ data: updated, meta: {} }))
      .mockResolvedValueOnce(jsonResponse({ data: invited, meta: {} }))
      .mockResolvedValueOnce(jsonResponse({ data: passwordReset, meta: {} }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listUsers({
      page: 2,
      size: 20,
      keyword: "  Invitee + ops  ",
      status: "invited",
      role: "external auditor",
    })).resolves.toEqual({ data: [invited], meta });
    await expect(inviteUser({
      email: "invitee@example.com",
      role: "member",
    })).resolves.toEqual(invited);
    await expect(updateUser("user/1", { name: "Invitee" })).resolves.toEqual(updated);
    await expect(resendInvitation("user/1")).resolves.toEqual(invited);
    await expect(sendPasswordResetEmail("user/1")).resolves.toEqual(passwordReset);

    expect(fetchMock.mock.calls.map(([url, init]) => [url, init.method])).toEqual([
      [
        "/api/v1/auth/users?page=2&size=20&keyword=Invitee+%2B+ops&status=invited&role=external+auditor",
        "GET",
      ],
      ["/api/v1/auth/invitations", "POST"],
      ["/api/v1/auth/users/user%2F1", "PATCH"],
      ["/api/v1/auth/users/user%2F1/resend-invitation", "POST"],
      ["/api/v1/auth/users/user%2F1/password-reset-email", "POST"],
    ]);
    for (const [, init] of fetchMock.mock.calls.slice(1) as [string, RequestInit][]) {
      expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("access-token");
    }
  });

  it("downloads a user skill bundle with CSRF protection and its server filename", async () => {
    document.cookie = "oryh_csrf=bundle-token; Path=/";
    const archive = new Blob(["zip-content"], { type: "application/zip" });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({
        "Content-Disposition": 'attachment; filename="oryh-skills-ops.zip"',
        "Content-Type": "application/zip",
      }),
      blob: async () => archive,
    } as Response);
    vi.stubGlobal("fetch", fetchMock);

    await expect(generateUserSkillBundle("user/1")).resolves.toEqual({
      blob: archive,
      filename: "oryh-skills-ops.zip",
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/users/user%2F1/skill-bundle");
    expect(init).toMatchObject({ method: "POST", credentials: "include", cache: "no-store" });
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("bundle-token");
  });

  it("rejects a successful skill-bundle response that is not a non-empty ZIP", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "Content-Type": "text/html" }),
        blob: async () => new Blob(["login page"]),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "Content-Type": "application/zip" }),
        blob: async () => new Blob([]),
      } as Response);
    vi.stubGlobal("fetch", fetchMock);

    await expect(generateUserSkillBundle("user-1")).rejects.toThrow("not a ZIP");
    await expect(generateUserSkillBundle("user-1")).rejects.toThrow("was empty");
  });

  it("reads and writes the role and capability catalog", async () => {
    document.cookie = "oryh_csrf=roles-token; Path=/";
    const role = {
      id: "role/1",
      name: "approver",
      title: "Approver",
      permissions: ["approval.record"],
      is_system: false,
    };
    const capability = {
      id: "cap/1",
      name: "finance.review",
      kind: "custom",
      scopable: false,
    };
    const catalog = { capabilities: [capability], object_types: ["invoice"] };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ data: [role], meta: { total: 1 } }))
      .mockResolvedValueOnce(jsonResponse({ data: catalog, meta: {} }))
      .mockResolvedValueOnce(jsonResponse({ data: role, meta: {} }, 201))
      .mockResolvedValueOnce(jsonResponse({ data: role, meta: {} }))
      .mockResolvedValueOnce(noContentResponse())
      .mockResolvedValueOnce(jsonResponse({ data: capability, meta: {} }, 201))
      .mockResolvedValueOnce(noContentResponse());
    vi.stubGlobal("fetch", fetchMock);

    await expect(listRoles()).resolves.toEqual([role]);
    await expect(listCapabilities()).resolves.toEqual(catalog);
    await createRole({ name: "approver", permissions: ["approval.record"] });
    await updateRole("role/1", { title: "Approver", permissions: ["approval.record"] });
    await deleteRole("role/1");
    await createCapability({ name: "finance.review", title: "Finance review" });
    await deleteCapability("finance.review");

    expect(fetchMock.mock.calls.map(([url, init]) => [url, init.method])).toEqual([
      ["/api/v1/roles", "GET"],
      ["/api/v1/capabilities", "GET"],
      ["/api/v1/roles", "POST"],
      ["/api/v1/roles/role%2F1", "PATCH"],
      ["/api/v1/roles/role%2F1", "DELETE"],
      ["/api/v1/capabilities", "POST"],
      ["/api/v1/capabilities/finance.review", "DELETE"],
    ]);
  });

  it("creates and updates projects with JSON, credentials, and CSRF", async () => {
    document.cookie = "oryh_csrf=project-token; Path=/";
    const created = { id: "project-1", project_name: "Apollo", status: "active" };
    const updated = { ...created, client: "Acme" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ data: created, meta: {} }, 201))
      .mockResolvedValueOnce(jsonResponse({ data: updated, meta: {} }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      createProject({ project_name: "Apollo", status: "active" }),
    ).resolves.toEqual(created);
    await expect(
      updateProject("project-1", { client: "Acme", status: "active" }),
    ).resolves.toEqual(updated);

    const [createUrl, createInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(createUrl).toBe("/api/v1/projects");
    expect(createInit).toMatchObject({ method: "POST", credentials: "include" });
    expect(new Headers(createInit.headers).get("Content-Type")).toBe(
      "application/json",
    );
    expect(new Headers(createInit.headers).get("X-CSRF-Token")).toBe(
      "project-token",
    );
    expect(JSON.parse(String(createInit.body))).toEqual({
      project_name: "Apollo",
      status: "active",
    });

    const [updateUrl, updateInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(updateUrl).toBe("/api/v1/projects/project-1");
    expect(updateInit).toMatchObject({ method: "PATCH", credentials: "include" });
    expect(new Headers(updateInit.headers).get("X-CSRF-Token")).toBe(
      "project-token",
    );
    expect(JSON.parse(String(updateInit.body))).toEqual({
      client: "Acme",
      status: "active",
    });
  });

  it("creates and updates vendors with the same unsafe-request contract", async () => {
    document.cookie = "oryh_csrf=vendor-token; Path=/";
    const created = { id: "vendor-1", name: "Acme", status: "active" };
    const updated = { ...created, tax_id: "91310000" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ data: created, meta: {} }, 201))
      .mockResolvedValueOnce(jsonResponse({ data: updated, meta: {} }));
    vi.stubGlobal("fetch", fetchMock);

    await createVendor({ name: "Acme", status: "active" });
    await updateVendor("vendor-1", { tax_id: "91310000", status: "active" });

    const [createUrl, createInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(createUrl).toBe("/api/v1/vendors");
    expect(createInit.method).toBe("POST");
    expect(createInit.credentials).toBe("include");
    expect(new Headers(createInit.headers).get("X-CSRF-Token")).toBe(
      "vendor-token",
    );
    expect(JSON.parse(String(createInit.body))).toEqual({
      name: "Acme",
      status: "active",
    });

    const [updateUrl, updateInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(updateUrl).toBe("/api/v1/vendors/vendor-1");
    expect(updateInit.method).toBe("PATCH");
    expect(updateInit.credentials).toBe("include");
    expect(new Headers(updateInit.headers).get("X-CSRF-Token")).toBe(
      "vendor-token",
    );
  });

  it("creates and updates resources with the same unsafe-request contract", async () => {
    document.cookie = "oryh_csrf=resource-token; Path=/";
    const created = {
      id: "resource-1",
      resource_type: "meeting_room",
      name: "Jade",
      booking_mode: "exclusive",
      status: "active",
    };
    const updated = { ...created, booking_mode: "shared" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ data: created, meta: {} }, 201))
      .mockResolvedValueOnce(jsonResponse({ data: updated, meta: {} }));
    vi.stubGlobal("fetch", fetchMock);

    await createResource({
      resource_type: "meeting_room",
      name: "Jade",
      booking_mode: "exclusive",
      status: "active",
    });
    await updateResource("resource-1", {
      booking_mode: "shared",
      status: "active",
    });

    const [createUrl, createInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(createUrl).toBe("/api/v1/resources");
    expect(createInit.method).toBe("POST");
    expect(createInit.credentials).toBe("include");
    expect(new Headers(createInit.headers).get("X-CSRF-Token")).toBe(
      "resource-token",
    );

    const [updateUrl, updateInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(updateUrl).toBe("/api/v1/resources/resource-1");
    expect(updateInit.method).toBe("PATCH");
    expect(updateInit.credentials).toBe("include");
    expect(new Headers(updateInit.headers).get("X-CSRF-Token")).toBe(
      "resource-token",
    );
    expect(JSON.parse(String(updateInit.body))).toEqual({
      booking_mode: "shared",
      status: "active",
    });
  });

  it("writes products, SKUs, and employees through typed JSON endpoints", async () => {
    document.cookie = "oryh_csrf=phase-three-token; Path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ data: { id: "saved-1" }, meta: {} }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createProduct({ name: "显示器", status: "active", currency: "CNY" });
    await updateProduct("product/1", { unit: "台", currency: "CNY", status: "active" });
    await createProductSku({
      product_id: "product/1",
      sku_code: "27-IN",
      variant_attrs: { 尺寸: "27" },
      status: "active",
    });
    await updateProductSku("sku/1", { list_price: 1299 });
    await createEmployee({ name: "王小明", status: "active" });
    await updateEmployee("employee/1", { timezone: "Asia/Shanghai", status: "active" });

    expect(fetchMock.mock.calls.map(([url, init]) => [url, init.method])).toEqual([
      ["/api/v1/products", "POST"],
      ["/api/v1/products/product%2F1", "PATCH"],
      ["/api/v1/product-skus", "POST"],
      ["/api/v1/product-skus/sku%2F1", "PATCH"],
      ["/api/v1/employees", "POST"],
      ["/api/v1/employees/employee%2F1", "PATCH"],
    ]);
    for (const [, init] of fetchMock.mock.calls as [string, RequestInit][]) {
      expect(init.credentials).toBe("include");
      expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("phase-three-token");
    }
  });

  it("archives all master-data records with DELETE, credentials, and CSRF", async () => {
    document.cookie = "oryh_csrf=archive-token; Path=/";
    const fetchMock = vi.fn().mockResolvedValue(noContentResponse());
    vi.stubGlobal("fetch", fetchMock);

    await expect(archiveProject("project/1")).resolves.toBeUndefined();
    await expect(archiveVendor("vendor/1")).resolves.toBeUndefined();
    await expect(archiveResource("resource/1")).resolves.toBeUndefined();
    await expect(archiveProduct("product/1")).resolves.toBeUndefined();
    await expect(archiveProductSku("sku/1")).resolves.toBeUndefined();

    expect(fetchMock).toHaveBeenCalledTimes(5);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/projects/project%2F1",
      "/api/v1/vendors/vendor%2F1",
      "/api/v1/resources/resource%2F1",
      "/api/v1/products/product%2F1",
      "/api/v1/product-skus/sku%2F1",
    ]);
    for (const [, init] of fetchMock.mock.calls as [string, RequestInit][]) {
      expect(init).toMatchObject({ method: "DELETE", credentials: "include" });
      expect(new Headers(init.headers).get("X-CSRF-Token")).toBe(
        "archive-token",
      );
    }
  });
});
