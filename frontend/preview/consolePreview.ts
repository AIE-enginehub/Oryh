import { zhAttributes } from "../src/locales/zh-CN/attributes";
import { zhCN } from "../src/locales/zh-CN/preview";
import type { Plugin } from "vite";
import type { IncomingMessage } from "node:http";

// Dev server only. This middleware never contacts a backend or sets auth cookies.
// All values are fictional and discarded when the preview server restarts.
type Sample = { id: string; [key: string]: unknown };
const now = () => new Date().toISOString();
const day = (offset: number) =>
  new Date(Date.now() + offset * 86400000).toISOString();
const record = (id: string, data: Record<string, unknown>): Sample => ({
  id,
  status: "active",
  metadata: {},
  created_at: day(-14),
  updated_at: null,
  ...data,
});
const permissions = [
  "users.manage",
  "employees.manage",
  "master_data.manage",
  "object_types.manage",
  "workflows.publish",
  "skills.manage",
  "keys.manage",
  "todos.complete_own",
  "tenant.act_for_any_employee",
];
function samples(): Record<string, Sample[]> {
  return {
    customers: [
      [zhCN.previewConsolePreview.message, zhCN.previewConsolePreview.message2, zhCN.previewConsolePreview.message3],
      [zhCN.previewConsolePreview.message4, zhCN.previewConsolePreview.message5, zhCN.previewConsolePreview.message6],
      [zhCN.previewConsolePreview.message7, zhCN.previewConsolePreview.message8, zhCN.previewConsolePreview.message9],
      [zhCN.previewConsolePreview.message10, zhCN.previewConsolePreview.message11, zhCN.previewConsolePreview.message12],
      [zhCN.previewConsolePreview.message13, zhCN.previewConsolePreview.message14, zhCN.previewConsolePreview.message15],
      [zhCN.previewConsolePreview.message16, zhCN.previewConsolePreview.message17, zhCN.previewConsolePreview.message18],
    ].map(([name, contact, address], i) =>
      record(`customer-${i + 1}`, {
        name,
        contact,
        address,
        customer_code: `CUS-${String(i + 1).padStart(3, "0")}`,
        email: `customer${i + 1}@example.com`,
        phone: null,
        tax_id: null,
        status: i === 5 ? "archived" : "active",
      }),
    ),
    vendors: [zhCN.previewConsolePreview.message19, zhCN.previewConsolePreview.message20, zhCN.previewConsolePreview.message21].map((name, i) =>
      record(`vendor-${i + 1}`, {
        name,
        vendor_code: `VEN-00${i + 1}`,
        contact: [zhCN.previewConsolePreview.message22, zhCN.previewConsolePreview.message23, zhCN.previewConsolePreview.message24][i],
        email: `vendor${i + 1}@example.com`,
        phone: null,
        tax_id: null,
      }),
    ),
    projects: [zhCN.previewConsolePreview.message25, zhCN.previewConsolePreview.message26, zhCN.previewConsolePreview.message27].map(
      (project_name, i) =>
        record(`project-${i + 1}`, {
          project_name,
          project_code: `PRJ-2026-00${i + 1}`,
          client: [
            zhCN.previewConsolePreview.message,
            zhCN.previewConsolePreview.message4,
            zhCN.previewConsolePreview.message7,
          ][i],
          start_date: "2026-08-01",
          end_date: "2026-12-31",
        }),
    ),
    products: [
      zhCN.previewConsolePreview.message28,
      zhCN.previewConsolePreview.message29,
      zhCN.previewConsolePreview.message30,
      zhCN.previewConsolePreview.message31,
    ].map((name, i) =>
      record(`product-${i + 1}`, {
        name,
        product_code: `PRD-00${i + 1}`,
        spec: [
          zhCN.previewConsolePreview.message32,
          zhCN.previewConsolePreview.message33,
          zhCN.previewConsolePreview.message34,
          zhCN.previewConsolePreview.message35,
        ][i],
        unit: zhCN.previewConsolePreview.unit,
        list_price: [2800, 1600, 380, 45][i],
        currency: "CNY",
        has_skus: i === 0,
        sku_count: i === 0 ? 2 : 0,
      }),
    ),
    "product-skus": [zhCN.previewConsolePreview.message36, zhCN.previewConsolePreview.message37].map((name, i) =>
      record(`sku-${i + 1}`, {
        product_id: "product-1",
        sku_code: `PRD-001-${i + 1}`,
        variant_attrs: { [zhAttributes.version]: name },
        list_price: 2800 + i * 600,
      }),
    ),
    resources: [
      record("resource-1", {
        name: zhCN.previewConsolePreview.name,
        code: "ROOM-01",
        resource_type: "meeting_room",
        location: zhCN.previewConsolePreview.location,
        capacity: 12,
        booking_mode: "exclusive",
        max_quantity: null,
      }),
      record("resource-2", {
        name: zhCN.previewConsolePreview.name2,
        code: "EQ-01",
        resource_type: "equipment",
        location: zhCN.previewConsolePreview.location2,
        capacity: null,
        booking_mode: "shared",
        max_quantity: 3,
      }),
    ],
    employees: [zhCN.previewConsolePreview.message14, zhCN.previewConsolePreview.message5, zhCN.previewConsolePreview.message11, zhCN.previewConsolePreview.message8].map((name, i) =>
      record(`employee-${i + 1}`, {
        name,
        employee_code: `EMP-00${i + 1}`,
        email: `employee${i + 1}@example.com`,
        timezone: "Asia/Shanghai",
        hire_date: "2026-07-01",
      }),
    ),
    "auth/users": [zhCN.previewConsolePreview.message14, zhCN.previewConsolePreview.message5, zhCN.previewConsolePreview.message11, zhCN.previewConsolePreview.message8].map((name, i) =>
      record(`user-${i + 1}`, {
        name,
        tenant_id: "preview-tenant",
        email: `employee${i + 1}@example.com`,
        employee_id: `employee-${i + 1}`,
        role: i === 0 ? "admin" : "member",
        invitation_pending: false,
        email_verified_at: day(-14),
      }),
    ),
    roles: [
      record("role-admin", {
        tenant_id: "preview-tenant",
        name: "admin",
        title: zhCN.previewConsolePreview.title,
        description: zhCN.previewConsolePreview.description,
        permissions,
        is_system: true,
      }),
      record("role-member", {
        tenant_id: "preview-tenant",
        name: "member",
        title: zhCN.previewConsolePreview.title2,
        description: zhCN.previewConsolePreview.description2,
        permissions: ["todos.complete_own"],
        is_system: true,
      }),
    ],
    todos: [
      record("todo-1", {
        title: zhCN.previewConsolePreview.title3,
        description: zhCN.previewConsolePreview.description3,
        employee_id: "employee-1",
        entity_type: "sales_quotation",
        entity_id: "quote-1",
        status: "open",
        due_at: day(-1),
        created_by: "user:user-1",
      }),
      record("todo-2", {
        title: zhCN.previewConsolePreview.title4,
        description: zhCN.previewConsolePreview.description4,
        employee_id: "employee-2",
        entity_type: "purchase_request",
        entity_id: "purchase-1",
        status: "open",
        due_at: day(1),
        created_by: "user:user-1",
      }),
      record("todo-3", {
        title: zhCN.previewConsolePreview.title5,
        description: zhCN.previewConsolePreview.description5,
        employee_id: "employee-1",
        entity_type: "expense_claim",
        entity_id: "expense-1",
        status: "open",
        due_at: day(3),
        created_by: "user:user-2",
      }),
      record("todo-4", {
        title: zhCN.previewConsolePreview.title6,
        description: zhCN.previewConsolePreview.description6,
        employee_id: "employee-3",
        entity_type: "project",
        entity_id: "project-3",
        status: "open",
        due_at: day(5),
        created_by: "user:user-1",
      }),
    ],
    skills: [],
    "tenant/api-keys": [],
    "tenant/api-key-owners": [],
    "flow-runs": [],
    "flow-subscriptions": [],
    payments: [],
    "approval-records": [],
    "object-type-definitions": [],
    "workflow-definitions": [],
    "object-directory": [],
    "business-objects": [],
    timesheets: [],
    "expense-claims": [],
    "purchase-requests": [],
    "sales-quotations": [],
    "sales-orders": [],
    "resource-bookings": [],
    "billing-accounts": [],
    invoices: [],
    "product-images": [],
    "product-prices": [],
    "supplier-products": [],
    "inventory-items": [],
    "inventory-item-details": [],
  };
}
async function readBody(
  req: IncomingMessage,
): Promise<Record<string, unknown>> {
  let input = "";
  for await (const chunk of req) {
    input += chunk;
    if (input.length > 1_000_000)
      throw new Error("Preview request is too large");
  }
  return input ? JSON.parse(input) : {};
}
export function consolePreview(): Plugin {
  const data = samples();
  let loggedIn = true;
  return {
    name: "oryh-isolated-console-preview",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url ?? "/", "http://127.0.0.1");
        if (!url.pathname.startsWith("/api/")) return next();
        const method = req.method ?? "GET";
        const path = decodeURIComponent(
          url.pathname.replace(/^\/api\/v1\//, ""),
        );
        const send = (
          value: unknown,
          meta: Record<string, unknown> = {},
          status = 200,
        ) => {
          res.statusCode = status;
          res.setHeader("Content-Type", "application/json");
          res.setHeader("Cache-Control", "no-store");
          res.end(JSON.stringify({ data: value, meta }));
        };
        const fail = (message: string, status = 404) => {
          res.statusCode = status;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ detail: message }));
        };
        try {
          if (path === "auth/browser/csrf" && method === "GET")
            return send({ csrf_token: "local-preview" });
          if (path === "auth/browser/logout" && method === "POST") {
            loggedIn = false;
            return send(null);
          }
          if (path === "auth/browser/login" && method === "POST") {
            await readBody(req);
            loggedIn = true;
            return send({
              user: data["auth/users"][0],
              csrf_token: "local-preview",
            });
          }
          if (!loggedIn)
            return fail(
              "Preview session signed out. Restart the preview to reset.",
              401,
            );
          if (path === "console/bootstrap" && method === "GET")
            return send({
              user: data["auth/users"][0],
              tenant: {
                id: "preview-tenant",
                name: zhCN.previewConsolePreview.name3,
                email_domain: "example.com",
              },
              role: "admin",
              permissions,
              employee_id: "employee-1",
            });
          if (path === "console/dashboard" && method === "GET")
            return send({
              counts: {
                users: data["auth/users"].filter((x) => x.status === "active")
                  .length,
                todos_open: data.todos.filter((x) => x.status === "open")
                  .length,
                todos_overdue: data.todos.filter(
                  (x) =>
                    x.status === "open" &&
                    Date.parse(String(x.due_at)) < Date.now(),
                ).length,
                objects: 0,
                skills: 0,
              },
            });
          if (path === "directory/display-names/resolve" && method === "POST")
            return send({
              employees: Object.fromEntries(
                data.employees.map((x) => [x.id, x.name]),
              ),
              actors: Object.fromEntries(
                data["auth/users"].map((x) => [`user:${x.id}`, x.name]),
              ),
            });
          if (path === "capabilities" && method === "GET")
            return send({
              capabilities: permissions.map((name) => ({
                id: name,
                name,
                title: name,
                kind: "system",
                scopable: false,
                created_at: day(-14),
              })),
              object_types: [],
            });
          const reach = /^(users|roles)\/([^/]+)\/skills$/.exec(path);
          if (reach && method === "GET")
            return send({
              subject_type: reach[1] === "users" ? "user" : "role",
              subject_id: reach[2],
              subject_label: reach[2],
              role: null,
              received: [],
              withheld: [],
            });
          const complete = /^todos\/([^/]+)$/.exec(path);
          if (complete && method === "PATCH") {
            const body = await readBody(req);
            if (body.status !== "completed")
              return fail("Unsupported sample to-do change", 400);
            const todo = data.todos.find((x) => x.id === complete[1]);
            if (!todo) return fail("Sample to-do not found");
            Object.assign(todo, {
              status: "completed",
              completed_at: now(),
              completed_by: "user:user-1",
            });
            return send(todo);
          }
          const collection = Object.keys(data)
            .sort((a, b) => b.length - a.length)
            .find((key) => path === key || path.startsWith(`${key}/`));
          if (!collection)
            return fail(
              zhCN.previewConsolePreview.message38,
            );
          const id =
            path === collection ? null : path.slice(collection.length + 1);
          const row = id ? data[collection].find((x) => x.id === id) : null;
          if (id && !row) return fail("Sample record not found");
          if (method === "GET" && row) return send(row);
          if (method === "GET" && collection === "products") {
            for (const product of data.products) {
              const count = data["product-skus"].filter(
                (sku) => sku.product_id === product.id,
              ).length;
              product.sku_count = count;
              product.has_skus = count > 0;
            }
          }
          if (method === "GET") {
            const keyword = (
              url.searchParams.get("keyword") ?? ""
            ).toLocaleLowerCase();
            const filterKeys = [
              "status",
              "product_id",
              "employee_id",
              "entity_type",
              "entity_id",
              "role",
            ];
            const rows = data[collection].filter(
              (x) =>
                (!keyword ||
                  JSON.stringify(x).toLocaleLowerCase().includes(keyword)) &&
                filterKeys.every((key) => {
                  const value = url.searchParams.get(key);
                  return !value || value === "all" || x[key] === value;
                }),
            );
            const size = Math.max(
              1,
              Number(url.searchParams.get("size")) || 50,
            );
            const page = Math.max(1, Number(url.searchParams.get("page")) || 1);
            return send(rows.slice((page - 1) * size, page * size), {
              total: rows.length,
              page,
              page_size: size,
              pages: Math.max(1, Math.ceil(rows.length / size)),
            });
          }
          const editable = [
            "customers",
            "vendors",
            "products",
            "product-skus",
            "projects",
            "resources",
            "employees",
          ];
          if (!editable.includes(collection))
            return fail(
              zhCN.previewConsolePreview.message39,
              405,
            );
          if (method === "POST" && !id) {
            const body = await readBody(req);
            const created = record(crypto.randomUUID(), {
              ...body,
              created_at: now(),
            });
            if (collection === "products")
              Object.assign(created, { sku_count: 0, has_skus: false });
            data[collection].unshift(created);
            return send(created, {}, 201);
          }
          if (method === "PATCH" && row) {
            Object.assign(row, await readBody(req), {
              id: row.id,
              updated_at: now(),
            });
            return send(row);
          }
          if (method === "DELETE" && row && collection !== "employees") {
            row.status = "archived";
            return send(null);
          }
          return fail("Action unavailable in local preview", 405);
        } catch {
          return fail(zhCN.previewConsolePreview.message40, 400);
        }
      });
    },
  };
}
