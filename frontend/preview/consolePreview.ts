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
      ["上海远川机电有限公司", "张明", "上海 · 浦东新区"],
      ["苏州青禾精密制造", "陈悦", "江苏 · 苏州工业园区"],
      ["杭州知行智能科技", "李安", "浙江 · 杭州滨江区"],
      ["宁波同源设备有限公司", "周宁", "浙江 · 宁波鄞州区"],
      ["无锡新原工业设计", "林晓", "江苏 · 无锡新吴区"],
      ["成都川谷电子科技", "赵青", "四川 · 成都高新区"],
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
    vendors: ["昆山合力精工", "上海联泽供应链", "宁波森远材料"].map((name, i) =>
      record(`vendor-${i + 1}`, {
        name,
        vendor_code: `VEN-00${i + 1}`,
        contact: ["王工", "陈经理", "郑工"][i],
        email: `vendor${i + 1}@example.com`,
        phone: null,
        tax_id: null,
      }),
    ),
    projects: ["远川自动化产线升级", "青禾精密零件交付", "知行设备试制"].map(
      (project_name, i) =>
        record(`project-${i + 1}`, {
          project_name,
          project_code: `PRJ-2026-00${i + 1}`,
          client: [
            "上海远川机电有限公司",
            "苏州青禾精密制造",
            "杭州知行智能科技",
          ][i],
          start_date: "2026-08-01",
          end_date: "2026-12-31",
        }),
    ),
    products: [
      "精密定位模组",
      "工业视觉传感器",
      "轻型装配支架",
      "标准连接组件",
    ].map((name, i) =>
      record(`product-${i + 1}`, {
        name,
        product_code: `PRD-00${i + 1}`,
        spec: [
          "行程 200 mm / 精度 0.02 mm",
          "500 万像素 / 千兆以太网",
          "铝合金 / 可调式",
          "不锈钢 / M8",
        ][i],
        unit: "件",
        list_price: [2800, 1600, 380, 45][i],
        currency: "CNY",
        has_skus: i === 0,
        sku_count: i === 0 ? 2 : 0,
      }),
    ),
    "product-skus": ["标准版", "增强版"].map((name, i) =>
      record(`sku-${i + 1}`, {
        product_id: "product-1",
        sku_code: `PRD-001-${i + 1}`,
        variant_attrs: { 版本: name },
        list_price: 2800 + i * 600,
      }),
    ),
    resources: [
      record("resource-1", {
        name: "青禾会议室",
        code: "ROOM-01",
        resource_type: "meeting_room",
        location: "上海办公室 · 3F",
        capacity: 12,
        booking_mode: "exclusive",
        max_quantity: null,
      }),
      record("resource-2", {
        name: "便携式检测仪",
        code: "EQ-01",
        resource_type: "equipment",
        location: "样品实验室",
        capacity: null,
        booking_mode: "shared",
        max_quantity: 3,
      }),
    ],
    employees: ["林晓", "陈悦", "周宁", "李安"].map((name, i) =>
      record(`employee-${i + 1}`, {
        name,
        employee_code: `EMP-00${i + 1}`,
        email: `employee${i + 1}@example.com`,
        timezone: "Asia/Shanghai",
        hire_date: "2026-07-01",
      }),
    ),
    "auth/users": ["林晓", "陈悦", "周宁", "李安"].map((name, i) =>
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
        title: "管理员",
        description: "维护企业工作空间、团队权限和业务资料",
        permissions,
        is_system: true,
      }),
      record("role-member", {
        tenant_id: "preview-tenant",
        name: "member",
        title: "团队成员",
        description: "查看自己的工作项并完成待办",
        permissions: ["todos.complete_own"],
        is_system: true,
      }),
    ],
    todos: [
      record("todo-1", {
        title: "确认远川项目的报价明细",
        description: "销售报价已准备，请核对产品规格与交付日期。",
        employee_id: "employee-1",
        entity_type: "sales_quotation",
        entity_id: "quote-1",
        status: "open",
        due_at: day(-1),
        created_by: "user:user-1",
      }),
      record("todo-2", {
        title: "补充青禾供应商的开票资料",
        description: "采购前完成供应商信息核对。",
        employee_id: "employee-2",
        entity_type: "purchase_request",
        entity_id: "purchase-1",
        status: "open",
        due_at: day(1),
        created_by: "user:user-1",
      }),
      record("todo-3", {
        title: "复核本月样品检测费用",
        description: "检查费用说明与原始凭证。",
        employee_id: "employee-1",
        entity_type: "expense_claim",
        entity_id: "expense-1",
        status: "open",
        due_at: day(3),
        created_by: "user:user-2",
      }),
      record("todo-4", {
        title: "确认知行试制项目里程碑",
        description: "同步验收范围与项目负责人。",
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
                name: "青禾制造 · 示例",
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
              "此功能未配置本地样例。Preview data is not configured for this action.",
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
              "本地预览仅支持主数据 CRUD 和完成待办。Preview supports master data CRUD and to-do completion.",
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
          return fail("本地样例请求格式无效。Invalid preview request.", 400);
        }
      });
    },
  };
}
