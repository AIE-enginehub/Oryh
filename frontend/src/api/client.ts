import type { components } from "./schema";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const CSRF_COOKIE_NAME = "oryh_csrf";
const CSRF_HEADER_NAME = "X-CSRF-Token";
const DEFAULT_PAGE = 1;
const DEFAULT_PAGE_SIZE = 50;

export type LoginInput = components["schemas"]["LoginRequest"];
export type PasswordResetRequestInput = components["schemas"]["PasswordResetRequest"];
export type PasswordResetRequestRead = components["schemas"]["PasswordResetRequestRead"];
export type BrowserLoginData = components["schemas"]["BrowserLoginData"];
export type BrowserCsrfData = components["schemas"]["BrowserCsrfData"];
export type BootstrapData = components["schemas"]["ConsoleBootstrapData"];
export type DashboardData = components["schemas"]["ConsoleDashboardData"];
export type ProjectRead = components["schemas"]["ProjectRead"];
export type ProjectCreate = components["schemas"]["CreateProjectRequest"];
export type ProjectUpdate = components["schemas"]["UpdateProjectRequest"];
export type VendorRead = components["schemas"]["VendorRead"];
export type VendorCreate = components["schemas"]["CreateVendorRequest"];
export type VendorUpdate = components["schemas"]["UpdateVendorRequest"];
export type CustomerRead = components["schemas"]["CustomerRead"];
export type CustomerCreate = components["schemas"]["CreateCustomerRequest"];
export type CustomerUpdate = components["schemas"]["UpdateCustomerRequest"];
export type ResourceRead = components["schemas"]["ResourceRead"];
export type ResourceCreate = components["schemas"]["CreateResourceRequest"];
export type ResourceUpdate = components["schemas"]["UpdateResourceRequest"];
export type ProductRead = components["schemas"]["ProductRead"];
export type ProductCreate = components["schemas"]["CreateProductRequest"];
export type ProductUpdate = components["schemas"]["UpdateProductRequest"];
export type ProductSkuRead = components["schemas"]["ProductSkuRead"];
export type ProductPriceRead = components["schemas"]["ProductPriceRead"];
export type SupplierProductRead = components["schemas"]["SupplierProductRead"];
export type InventoryItemRead = components["schemas"]["InventoryItemRead"];
export type InventoryItemDetailRead = components["schemas"]["InventoryItemDetailRead"];
export type ProductSkuCreate = components["schemas"]["CreateProductSkuRequest"];
export type ProductSkuUpdate = components["schemas"]["UpdateProductSkuRequest"];
export type BatchCreateProductSkusInput = components["schemas"]["BatchCreateProductSkusRequest"];
export type BatchCreateProductSkusResult = components["schemas"]["BatchCreateProductSkusRead"];
export type EmployeeRead = components["schemas"]["EmployeeRead"];
export type EmployeeCreate = components["schemas"]["CreateEmployeeRequest"];
export type EmployeeUpdate = components["schemas"]["UpdateEmployeeRequest"];
export type UserRead = components["schemas"]["UserRead"];
export type InvitationUserRead = components["schemas"]["InvitationUserRead"];
export type PasswordResetEmailRead = components["schemas"]["PasswordResetEmailRead"];
export type InviteUserInput = components["schemas"]["InviteUserRequest"];
export type UpdateUserInput = components["schemas"]["UpdateUserRequest"];
export type RoleRead = components["schemas"]["RoleRead"];
export type CreateRoleInput = components["schemas"]["CreateRoleRequest"];
export type UpdateRoleInput = components["schemas"]["UpdateRoleRequest"];
export type CapabilityRead = components["schemas"]["CapabilityRead"];
export type CapabilityCatalog = components["schemas"]["CapabilityCatalog"];
export type CreateCapabilityInput = components["schemas"]["CreateCapabilityRequest"];

// Ergonomic aliases for components and form inputs. The explicit *Read,
// *Create, and *Update names above remain useful when mirroring OpenAPI.
export type Project = ProjectRead;
export type CreateProjectInput = ProjectCreate;
export type UpdateProjectInput = ProjectUpdate;
export type Vendor = VendorRead;
export type CreateVendorInput = VendorCreate;
export type UpdateVendorInput = VendorUpdate;
export type Customer = CustomerRead;
export type CreateCustomerInput = CustomerCreate;
export type UpdateCustomerInput = CustomerUpdate;
export type Resource = ResourceRead;
export type CreateResourceInput = ResourceCreate;
export type UpdateResourceInput = ResourceUpdate;
export type Product = ProductRead;
export type CreateProductInput = ProductCreate;
export type UpdateProductInput = ProductUpdate;
export type ProductSku = ProductSkuRead;
export type CreateProductSkuInput = ProductSkuCreate;
export type UpdateProductSkuInput = ProductSkuUpdate;
export type Employee = EmployeeRead;
export type CreateEmployeeInput = EmployeeCreate;
export type UpdateEmployeeInput = EmployeeUpdate;
export type User = UserRead;
export type InvitationUser = InvitationUserRead;
export type PasswordResetEmail = PasswordResetEmailRead;
export type Role = RoleRead;
export type Capability = CapabilityRead;

export type PaginationMeta = {
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export type ApiEnvelope<T, M = Record<string, unknown>> = {
  data: T;
  meta: M;
};

export type PaginatedEnvelope<T> = ApiEnvelope<T[], PaginationMeta>;

export type FileDownload = {
  blob: Blob;
  filename: string;
};

type CommonListFilters<Status extends string> = {
  page?: number;
  size?: number;
  keyword?: string;
  status?: Status;
};

export type ProjectListFilters = CommonListFilters<ProjectRead["status"]>;

export type VendorListFilters = CommonListFilters<VendorRead["status"]> & {
  tax_id?: string;
};

export type CustomerListFilters = CommonListFilters<CustomerRead["status"]> & {
  tax_id?: string;
};

export type ResourceListFilters = CommonListFilters<ResourceRead["status"]> & {
  resource_type?: string;
  booking_mode?: ResourceRead["booking_mode"];
};

export type ProductListFilters = CommonListFilters<ProductRead["status"]>;

export type ProductSkuListFilters = {
  page?: number;
  size?: number;
  product_id?: string;
  sku_code?: string;
  status?: ProductSkuRead["status"];
};

export type EmployeeListFilters = CommonListFilters<EmployeeRead["status"]>;

export type UserListFilters = CommonListFilters<UserRead["status"]> & {
  role?: string;
};

type ErrorBody = {
  detail?: unknown;
  message?: unknown;
};

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly requestId?: string;

  constructor(status: number, message: string, detail?: unknown, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.requestId = requestId;
  }
}

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") {
    return undefined;
  }

  for (const part of document.cookie.split(";")) {
    const cookie = part.trim();
    const separator = cookie.indexOf("=");
    if (separator < 0 || cookie.slice(0, separator) !== name) {
      continue;
    }

    const value = cookie.slice(separator + 1);
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  }

  return undefined;
}

function errorMessage(response: Response, body: ErrorBody | undefined): string {
  if (typeof body?.detail === "string") {
    return body.detail;
  }
  if (Array.isArray(body?.detail)) {
    const messages = body.detail
      .map((item) => {
        if (typeof item === "object" && item !== null && "msg" in item) {
          return String(item.msg);
        }
        return String(item);
      })
      .filter(Boolean);
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }
  if (typeof body?.message === "string") {
    return body.message;
  }
  return response.statusText || `Request failed with status ${response.status}`;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ErrorBody | undefined;
  try {
    body = (await response.json()) as ErrorBody;
  } catch {
    body = undefined;
  }

  return new ApiError(
    response.status,
    errorMessage(response, body),
    body?.detail,
    response.headers.get("X-Request-ID") ?? undefined,
  );
}

/**
 * Execute a same-origin API request and retain Oryh's `{ data, meta }`
 * envelope. Browser credentials never leave HttpOnly cookies.
 */
export async function apiRequestEnvelope<T, M = Record<string, unknown>>(
  path: string,
  init: RequestInit = {},
): Promise<ApiEnvelope<T, M>> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);

  if (!SAFE_METHODS.has(method) && !headers.has(CSRF_HEADER_NAME)) {
    const csrfToken = readCookie(CSRF_COOKIE_NAME);
    if (csrfToken !== undefined) {
      headers.set(CSRF_HEADER_NAME, csrfToken);
    }
  }

  const response = await fetch(path, {
    ...init,
    method,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    throw await parseError(response);
  }
  if (response.status === 204) {
    return { data: undefined as T, meta: {} as M };
  }

  const body = (await response.json()) as unknown;
  if (typeof body === "object" && body !== null && "data" in body) {
    const envelope = body as { data: T; meta?: unknown };
    return {
      data: envelope.data,
      meta:
        typeof envelope.meta === "object" && envelope.meta !== null
          ? (envelope.meta as M)
          : ({} as M),
    };
  }
  return { data: body as T, meta: {} as M };
}

/**
 * Execute a same-origin API request and return only its data payload. Existing
 * call sites can stay data-oriented while paginated lists retain metadata via
 * `apiRequestEnvelope`.
 */
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await apiRequestEnvelope<T>(path, init)).data;
}

function appendQueryParam(
  search: URLSearchParams,
  name: string,
  value: string | number | undefined,
): void {
  if (value === undefined) {
    return;
  }
  if (typeof value === "string") {
    const normalized = value.trim();
    if (normalized === "") {
      return;
    }
    search.set(name, normalized);
    return;
  }
  search.set(name, String(value));
}

function listUrl<T extends object>(path: string, filters: T): string {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(filters) as [
    string,
    string | number | undefined,
  ][]) {
    appendQueryParam(search, name, value);
  }
  const query = search.toString();
  return query === "" ? path : `${path}?${query}`;
}

function jsonRequest<T>(
  path: string,
  method: "POST" | "PATCH",
  input: unknown,
): Promise<T> {
  return apiRequest<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function listProjects(
  filters: ProjectListFilters = {},
): Promise<PaginatedEnvelope<ProjectRead>> {
  return apiRequestEnvelope<ProjectRead[], PaginationMeta>(
    listUrl("/api/v1/projects", {
      page: filters.page ?? DEFAULT_PAGE,
      size: filters.size ?? DEFAULT_PAGE_SIZE,
      keyword: filters.keyword,
      status: filters.status,
    }),
  );
}

export function createProject(input: ProjectCreate): Promise<ProjectRead> {
  return jsonRequest<ProjectRead>("/api/v1/projects", "POST", input);
}

export function updateProject(id: string, input: ProjectUpdate): Promise<ProjectRead> {
  return jsonRequest<ProjectRead>(
    `/api/v1/projects/${encodeURIComponent(id)}`,
    "PATCH",
    input,
  );
}

export async function archiveProject(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/projects/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function listVendors(
  filters: VendorListFilters = {},
): Promise<PaginatedEnvelope<VendorRead>> {
  return apiRequestEnvelope<VendorRead[], PaginationMeta>(
    listUrl("/api/v1/vendors", {
      page: filters.page ?? DEFAULT_PAGE,
      size: filters.size ?? DEFAULT_PAGE_SIZE,
      keyword: filters.keyword,
      status: filters.status,
      tax_id: filters.tax_id,
    }),
  );
}

export function createVendor(input: VendorCreate): Promise<VendorRead> {
  return jsonRequest<VendorRead>("/api/v1/vendors", "POST", input);
}

export function updateVendor(id: string, input: VendorUpdate): Promise<VendorRead> {
  return jsonRequest<VendorRead>(
    `/api/v1/vendors/${encodeURIComponent(id)}`,
    "PATCH",
    input,
  );
}

export async function archiveVendor(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/vendors/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function listCustomers(
  filters: CustomerListFilters = {},
): Promise<PaginatedEnvelope<CustomerRead>> {
  return apiRequestEnvelope<CustomerRead[], PaginationMeta>(
    listUrl("/api/v1/customers", {
      page: filters.page ?? DEFAULT_PAGE,
      size: filters.size ?? DEFAULT_PAGE_SIZE,
      keyword: filters.keyword,
      status: filters.status,
      tax_id: filters.tax_id,
    }),
  );
}

export function createCustomer(input: CustomerCreate): Promise<CustomerRead> {
  return jsonRequest<CustomerRead>("/api/v1/customers", "POST", input);
}

export function updateCustomer(id: string, input: CustomerUpdate): Promise<CustomerRead> {
  return jsonRequest<CustomerRead>(
    `/api/v1/customers/${encodeURIComponent(id)}`,
    "PATCH",
    input,
  );
}

export async function archiveCustomer(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/customers/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function listResources(
  filters: ResourceListFilters = {},
): Promise<PaginatedEnvelope<ResourceRead>> {
  return apiRequestEnvelope<ResourceRead[], PaginationMeta>(
    listUrl("/api/v1/resources", {
      page: filters.page ?? DEFAULT_PAGE,
      size: filters.size ?? DEFAULT_PAGE_SIZE,
      keyword: filters.keyword,
      status: filters.status,
      resource_type: filters.resource_type,
      booking_mode: filters.booking_mode,
    }),
  );
}

export function createResource(input: ResourceCreate): Promise<ResourceRead> {
  return jsonRequest<ResourceRead>("/api/v1/resources", "POST", input);
}

export function updateResource(id: string, input: ResourceUpdate): Promise<ResourceRead> {
  return jsonRequest<ResourceRead>(
    `/api/v1/resources/${encodeURIComponent(id)}`,
    "PATCH",
    input,
  );
}

export async function archiveResource(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/resources/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function listProducts(
  filters: ProductListFilters = {},
): Promise<PaginatedEnvelope<ProductRead>> {
  return apiRequestEnvelope<ProductRead[], PaginationMeta>(
    listUrl("/api/v1/products", {
      page: filters.page ?? DEFAULT_PAGE,
      size: filters.size ?? DEFAULT_PAGE_SIZE,
      keyword: filters.keyword,
      status: filters.status,
    }),
  );
}

export function createProduct(input: ProductCreate): Promise<ProductRead> {
  return jsonRequest<ProductRead>("/api/v1/products", "POST", input);
}

export function updateProduct(id: string, input: ProductUpdate): Promise<ProductRead> {
  return jsonRequest<ProductRead>(
    `/api/v1/products/${encodeURIComponent(id)}`,
    "PATCH",
    input,
  );
}

export async function archiveProduct(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/products/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function listProductSkus(
  filters: ProductSkuListFilters = {},
): Promise<PaginatedEnvelope<ProductSkuRead>> {
  return apiRequestEnvelope<ProductSkuRead[], PaginationMeta>(
    listUrl("/api/v1/product-skus", {
      page: filters.page ?? DEFAULT_PAGE,
      size: filters.size ?? DEFAULT_PAGE_SIZE,
      product_id: filters.product_id,
      sku_code: filters.sku_code,
      status: filters.status,
    }),
  );
}

// The product-detail companions are read unpaginated: a detail panel wants
// the whole picture, and the server returns the full set when no page is
// asked for (meta carries only the total).
export type TotalMeta = { total?: number | null };

export function listProductPrices(filters: {
  product_id?: string;
  sku_id?: string;
  price_type?: ProductPriceRead["price_type"];
  currency?: string;
  status?: ProductPriceRead["status"];
}): Promise<ApiEnvelope<ProductPriceRead[], TotalMeta>> {
  return apiRequestEnvelope<ProductPriceRead[], TotalMeta>(
    listUrl("/api/v1/product-prices", filters),
  );
}

export function listSupplierProducts(filters: {
  product_id?: string;
  vendor_id?: string;
  status?: SupplierProductRead["status"];
}): Promise<ApiEnvelope<SupplierProductRead[], TotalMeta>> {
  return apiRequestEnvelope<SupplierProductRead[], TotalMeta>(
    listUrl("/api/v1/supplier-products", filters),
  );
}

export function listInventoryItems(filters: {
  product_id?: string;
  sku_id?: string;
  facility?: string;
  lot_id?: string;
  status?: InventoryItemRead["status"];
}): Promise<ApiEnvelope<InventoryItemRead[], TotalMeta>> {
  return apiRequestEnvelope<InventoryItemRead[], TotalMeta>(
    listUrl("/api/v1/inventory-items", filters),
  );
}

export function listInventoryItemDetails(filters: {
  inventory_item_id?: string;
  reason?: InventoryItemDetailRead["reason"];
  entity_type?: string;
  entity_id?: string;
}): Promise<ApiEnvelope<InventoryItemDetailRead[], TotalMeta>> {
  return apiRequestEnvelope<InventoryItemDetailRead[], TotalMeta>(
    listUrl("/api/v1/inventory-item-details", filters),
  );
}

export function createProductSku(input: ProductSkuCreate): Promise<ProductSkuRead> {
  return jsonRequest<ProductSkuRead>("/api/v1/product-skus", "POST", input);
}

export function updateProductSku(id: string, input: ProductSkuUpdate): Promise<ProductSkuRead> {
  return jsonRequest<ProductSkuRead>(
    `/api/v1/product-skus/${encodeURIComponent(id)}`,
    "PATCH",
    input,
  );
}

export function batchCreateProductSkus(
  productId: string,
  input: BatchCreateProductSkusInput,
): Promise<BatchCreateProductSkusResult> {
  return jsonRequest<BatchCreateProductSkusResult>(
    `/api/v1/products/${encodeURIComponent(productId)}/skus/batch`,
    "POST",
    input,
  );
}

export async function archiveProductSku(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/product-skus/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function listEmployees(
  filters: EmployeeListFilters = {},
): Promise<PaginatedEnvelope<EmployeeRead>> {
  return apiRequestEnvelope<EmployeeRead[], PaginationMeta>(
    listUrl("/api/v1/employees", {
      page: filters.page ?? DEFAULT_PAGE,
      size: filters.size ?? DEFAULT_PAGE_SIZE,
      keyword: filters.keyword,
      status: filters.status,
    }),
  );
}

export function getEmployee(id: string): Promise<EmployeeRead> {
  return apiRequest<EmployeeRead>(`/api/v1/employees/${encodeURIComponent(id)}`);
}

export function createEmployee(input: EmployeeCreate): Promise<EmployeeRead> {
  return jsonRequest<EmployeeRead>("/api/v1/employees", "POST", input);
}

export function updateEmployee(id: string, input: EmployeeUpdate): Promise<EmployeeRead> {
  return jsonRequest<EmployeeRead>(
    `/api/v1/employees/${encodeURIComponent(id)}`,
    "PATCH",
    input,
  );
}

export function listUsers(
  filters: UserListFilters = {},
): Promise<PaginatedEnvelope<UserRead>> {
  return apiRequestEnvelope<UserRead[], PaginationMeta>(
    listUrl("/api/v1/auth/users", {
      page: filters.page ?? DEFAULT_PAGE,
      size: filters.size ?? DEFAULT_PAGE_SIZE,
      keyword: filters.keyword,
      status: filters.status,
      role: filters.role,
    }),
  );
}

export function inviteUser(input: InviteUserInput): Promise<InvitationUser> {
  return jsonRequest<InvitationUser>("/api/v1/auth/invitations", "POST", input);
}

export function updateUser(id: string, input: UpdateUserInput): Promise<UserRead> {
  return jsonRequest<UserRead>(
    `/api/v1/auth/users/${encodeURIComponent(id)}`,
    "PATCH",
    input,
  );
}

export function resendInvitation(id: string): Promise<InvitationUser> {
  return jsonRequest<InvitationUser>(
    `/api/v1/auth/users/${encodeURIComponent(id)}/resend-invitation`,
    "POST",
    undefined,
  );
}

export function sendPasswordResetEmail(id: string): Promise<PasswordResetEmail> {
  return jsonRequest<PasswordResetEmail>(
    `/api/v1/auth/users/${encodeURIComponent(id)}/password-reset-email`,
    "POST",
    undefined,
  );
}

function downloadFilename(response: Response, fallback: string): string {
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const quoted = disposition.match(/filename="([^"]+)"/i)?.[1];
  const plain = disposition.match(/filename=([^;\s]+)/i)?.[1];
  let candidate = encoded ?? quoted ?? plain ?? fallback;
  if (encoded) {
    try {
      candidate = decodeURIComponent(encoded);
    } catch {
      candidate = fallback;
    }
  }
  const safe = candidate.replace(/[\\/\u0000-\u001f\u007f]/g, "_").trim();
  return safe || fallback;
}

export async function generateUserSkillBundle(id: string): Promise<FileDownload> {
  const headers = new Headers();
  const csrfToken = readCookie(CSRF_COOKIE_NAME);
  if (csrfToken !== undefined) headers.set(CSRF_HEADER_NAME, csrfToken);
  const response = await fetch(
    `/api/v1/users/${encodeURIComponent(id)}/skill-bundle`,
    { method: "POST", headers, credentials: "include", cache: "no-store" },
  );
  if (!response.ok) throw await parseError(response);
  const contentType = response.headers.get("Content-Type")
    ?.split(";", 1)[0]
    .trim()
    .toLowerCase();
  if (contentType !== "application/zip") {
    throw new Error("Skill bundle response was not a ZIP archive");
  }
  const blob = await response.blob();
  if (blob.size === 0) throw new Error("Skill bundle response was empty");
  return {
    blob,
    // the server names the file after the tenant and user; this only covers a
    // missing Content-Disposition
    filename: downloadFilename(response, "oryh-skill-bundle.zip"),
  };
}

export function listRoles(): Promise<RoleRead[]> {
  return apiRequest<RoleRead[]>("/api/v1/roles");
}

export function createRole(input: CreateRoleInput): Promise<RoleRead> {
  return jsonRequest<RoleRead>("/api/v1/roles", "POST", input);
}

export function updateRole(id: string, input: UpdateRoleInput): Promise<RoleRead> {
  return jsonRequest<RoleRead>(
    `/api/v1/roles/${encodeURIComponent(id)}`,
    "PATCH",
    input,
  );
}

export async function deleteRole(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/roles/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function listCapabilities(): Promise<CapabilityCatalog> {
  return apiRequest<CapabilityCatalog>("/api/v1/capabilities");
}

export function createCapability(input: CreateCapabilityInput): Promise<CapabilityRead> {
  return jsonRequest<CapabilityRead>("/api/v1/capabilities", "POST", input);
}

export async function deleteCapability(name: string): Promise<void> {
  await apiRequest<void>(`/api/v1/capabilities/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}

export function browserLogin(input: LoginInput): Promise<BrowserLoginData> {
  return apiRequest<BrowserLoginData>("/api/v1/auth/browser/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function requestOwnPasswordReset(
  input: PasswordResetRequestInput,
): Promise<PasswordResetRequestRead> {
  return jsonRequest<PasswordResetRequestRead>(
    "/api/v1/auth/password-reset-email",
    "POST",
    input,
  );
}

export async function browserLogout(): Promise<void> {
  await apiRequest<void>("/api/v1/auth/browser/logout", { method: "POST" });
}

/**
 * Upgrade a legacy SSR session to the SPA's double-submit CSRF contract.
 * Browser login already sets this cookie, so normal SPA sessions make no
 * extra request.
 */
export async function ensureBrowserCsrf(): Promise<void> {
  if (readCookie(CSRF_COOKIE_NAME) !== undefined) {
    return;
  }
  await apiRequest<BrowserCsrfData>("/api/v1/auth/browser/csrf");
}

export async function getBootstrap(): Promise<BootstrapData> {
  const data = await apiRequest<BootstrapData>("/api/v1/console/bootstrap");
  await ensureBrowserCsrf();
  return data;
}

export function getDashboard(): Promise<DashboardData> {
  return apiRequest<DashboardData>("/api/v1/console/dashboard");
}

// Short aliases keep call sites concise and preserve the public client surface.
export const login = browserLogin;
export const logout = browserLogout;
export const bootstrap = getBootstrap;
export const dashboard = getDashboard;
