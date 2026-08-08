import {
  apiRequest,
  apiRequestEnvelope,
  type ApiEnvelope,
  type PaginatedEnvelope,
  type PaginationMeta,
} from "./client";

const DEFAULT_PAGE = 1;
const DEFAULT_PAGE_SIZE = 20;

export type EntityKind = "business_object" | "builtin";
export type ObjectTypeStatus = "active" | "archived";

export type ObjectTypeDefinition = {
  id: string;
  tenant_id: string;
  entity_kind: EntityKind;
  object_type: string;
  title: string | null;
  description: string | null;
  json_schema: Record<string, unknown>;
  state_machine: Record<string, unknown> | null;
  version: number;
  status: ObjectTypeStatus;
  created_by: string | null;
  created_at: string;
  updated_at: string | null;
};

export type ObjectTypeInput = {
  object_type: string;
  entity_kind: EntityKind;
  title: string | null;
  description: string | null;
  json_schema: Record<string, unknown>;
  state_machine?: Record<string, unknown> | null;
};

export type WorkflowDefinition = {
  id: string;
  tenant_id: string;
  entity_kind: EntityKind;
  object_type: string;
  name: string;
  version: number;
  definition_text: string;
  status: "active" | "superseded";
  created_by: string | null;
  created_at: string;
};

export type WorkflowInput = {
  entity_kind: EntityKind;
  object_type: string;
  name: string;
  definition_text: string;
};

export type SkillStatus = "active" | "archived";
/** "capability" = whoever passes required_capability; "targeted" = only the
 *  named audience, and an empty audience means nobody. */
export type DistributionMode = "capability" | "targeted";
export type SkillAudienceSummary = { roles: string[]; user_count: number };
export type SkillSummary = {
  id: string;
  name: string;
  kind: "product" | "custom";
  title: string | null;
  description: string | null;
  required_capability: string | null;
  distribution_mode: DistributionMode;
  audience: SkillAudienceSummary | null;
  version: number;
  status: SkillStatus;
  updated_at: string | null;
};

export type Skill = SkillSummary & {
  tenant_id: string;
  files: Record<string, string>;
  created_by: string | null;
  created_at: string;
};

export type SkillInput = {
  name: string;
  title: string | null;
  description: string | null;
  required_capability: string | null;
  distribution_mode?: DistributionMode;
  files: Record<string, string>;
};

export type SkillAssignment = {
  id: string;
  skill_id: string;
  subject_type: "user" | "role";
  subject_id: string;
  subject_label: string | null;
  /** named here but their role cannot run it — they would install and 403 */
  blocked_members: string[];
  created_by: string | null;
  created_at: string;
};

/** What the audience would do, computed before anything is committed.
 *  `losing` is the one that gets missed: nobody reports a skill they quietly
 *  stopped receiving. */
export type SkillAudienceImpact = {
  distribution_mode: DistributionMode;
  reaches_now: string[];
  would_reach: string[];
  gaining: string[];
  losing: string[];
  blocked: string[];
};

export type SkillAudience = { assignments: SkillAssignment[]; impact: SkillAudienceImpact };

export type SkillReachReason =
  | "capability"
  | "targeted_role"
  | "targeted_user"
  | "missing_capability"
  | "not_in_audience";

export type SkillReachEntry = {
  name: string;
  title: string | null;
  /** What the skill is for. `title` is a label ("Oryh Payroll"); deciding
   *  whether a role should hold something needs the sentence. */
  description: string | null;
  kind: "product" | "custom";
  required_capability: string | null;
  distribution_mode: DistributionMode;
  received: boolean;
  reasons: SkillReachReason[];
  named_via: string[];
  granted_by_roles: string[];
};

export type SkillReach = {
  subject_type: "user" | "role";
  subject_id: string;
  subject_label: string;
  role: string | null;
  received: SkillReachEntry[];
  withheld: SkillReachEntry[];
};

export type ApiKey = {
  id: string;
  tenant_id: string;
  label: string | null;
  user_id: string | null;
  role: string;
  effective_role: string | null;
  effective_active: boolean;
  user_name: string | null;
  user_email: string | null;
  user_status: "invited" | "active" | "disabled" | null;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
};

export type ApiKeyOwner = {
  id: string;
  email: string;
  name: string | null;
  role: string;
  status: "active";
};

export type ObjectDirectoryEntry = {
  entity_kind: EntityKind;
  object_type: string;
  count: number;
  title: string | null;
  definition_status: ObjectTypeStatus | null;
};

export type CreatedApiKey = {
  api_key: ApiKey;
  plain_text_api_key: string;
};

type PageFilters = { page?: number; size?: number; keyword?: string };

function url(path: string, values: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(values)) {
    if (value === undefined || value === "") continue;
    search.set(name, String(value));
  }
  return search.size ? `${path}?${search}` : path;
}

function normalizePage<T>(
  envelope: ApiEnvelope<T[], Partial<PaginationMeta>>,
  page: number,
  size: number,
  fallbackMatch?: (item: T) => boolean,
): PaginatedEnvelope<T> {
  const serverPaged = Number.isInteger(envelope.meta.page) &&
    Number.isInteger(envelope.meta.page_size) &&
    Number.isInteger(envelope.meta.pages);
  if (serverPaged) {
    const total = envelope.meta.total ?? envelope.data.length;
    return {
      data: envelope.data,
      meta: {
        total,
        page: envelope.meta.page as number,
        page_size: envelope.meta.page_size as number,
        pages: Math.max(1, envelope.meta.pages as number),
      },
    };
  }
  const filtered = fallbackMatch ? envelope.data.filter(fallbackMatch) : envelope.data;
  const total = filtered.length;
  const pageSize = envelope.meta.page_size ?? size;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, pages);
  const start = (safePage - 1) * pageSize;
  return {
    data: filtered.slice(start, start + pageSize),
    meta: {
      total,
      page: safePage,
      page_size: pageSize,
      pages,
    },
  };
}

async function listPage<T>(
  path: string,
  filters: PageFilters & Record<string, string | number | boolean | undefined>,
  fallbackMatch?: (item: T) => boolean,
): Promise<PaginatedEnvelope<T>> {
  const page = filters.page ?? DEFAULT_PAGE;
  const size = filters.size ?? DEFAULT_PAGE_SIZE;
  const result = await apiRequestEnvelope<T[], Partial<PaginationMeta>>(
    url(path, { ...filters, page, size }),
  );
  return normalizePage(result, page, size, fallbackMatch);
}

function jsonRequest<T>(path: string, method: "POST" | "PATCH", input: unknown): Promise<T> {
  return apiRequest<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function listObjectTypes(
  filters: PageFilters & { status?: ObjectTypeStatus; entity_kind?: EntityKind } = {},
): Promise<PaginatedEnvelope<ObjectTypeDefinition>> {
  const keyword = filters.keyword?.trim().toLocaleLowerCase() ?? "";
  return listPage<ObjectTypeDefinition>("/api/v1/object-type-definitions", filters, (item) =>
    (!filters.status || item.status === filters.status) &&
    (!filters.entity_kind || item.entity_kind === filters.entity_kind) &&
    (!keyword || `${item.object_type} ${item.title ?? ""} ${item.description ?? ""}`.toLocaleLowerCase().includes(keyword)));
}

export function listObjectDirectory(): Promise<ObjectDirectoryEntry[]> {
  return apiRequest<ObjectDirectoryEntry[]>("/api/v1/object-directory");
}

export function createObjectType(input: ObjectTypeInput): Promise<ObjectTypeDefinition> {
  return jsonRequest("/api/v1/object-type-definitions", "POST", input);
}

export function updateObjectType(
  id: string,
  input: Partial<Omit<ObjectTypeInput, "object_type" | "entity_kind">> & { status?: ObjectTypeStatus },
): Promise<ObjectTypeDefinition> {
  return jsonRequest(`/api/v1/object-type-definitions/${encodeURIComponent(id)}`, "PATCH", input);
}

export function listWorkflows(
  filters: PageFilters & { entity_kind?: EntityKind; object_type?: string; history?: boolean } = {},
): Promise<PaginatedEnvelope<WorkflowDefinition>> {
  const keyword = filters.keyword?.trim().toLocaleLowerCase() ?? "";
  return listPage<WorkflowDefinition>("/api/v1/workflow-definitions", filters, (item) =>
    (!filters.entity_kind || item.entity_kind === filters.entity_kind) &&
    (!filters.object_type || item.object_type === filters.object_type) &&
    (!keyword || `${item.object_type} ${item.name} ${item.definition_text}`.toLocaleLowerCase().includes(keyword)));
}

export function publishWorkflow(input: WorkflowInput): Promise<WorkflowDefinition> {
  return jsonRequest("/api/v1/workflow-definitions", "POST", input);
}

export function listSkills(
  filters: PageFilters & { status?: SkillStatus | "all" } = {},
): Promise<PaginatedEnvelope<SkillSummary>> {
  const keyword = filters.keyword?.trim().toLocaleLowerCase() ?? "";
  return listPage<SkillSummary>("/api/v1/skills", filters, (item) =>
    (!filters.status || filters.status === "all" || item.status === filters.status) &&
    (!keyword || `${item.name} ${item.title ?? ""} ${item.description ?? ""} ${item.required_capability ?? ""}`.toLocaleLowerCase().includes(keyword)));
}

export function getSkill(name: string): Promise<Skill> {
  return apiRequest<Skill>(`/api/v1/skills/${encodeURIComponent(name)}`);
}

export function createSkill(input: SkillInput): Promise<Skill> {
  return jsonRequest("/api/v1/skills", "POST", input);
}

export function updateSkill(name: string, input: Omit<SkillInput, "name"> & { status?: SkillStatus }): Promise<Skill> {
  return jsonRequest(`/api/v1/skills/${encodeURIComponent(name)}`, "PATCH", input);
}

export function setSkillStatus(name: string, status: SkillStatus): Promise<Skill> {
  return jsonRequest(`/api/v1/skills/${encodeURIComponent(name)}`, "PATCH", { status });
}

export function getUserSkillReach(userId: string): Promise<SkillReach> {
  return apiRequest<SkillReach>(`/api/v1/users/${encodeURIComponent(userId)}/skills`);
}

export function getRoleSkillReach(roleRef: string): Promise<SkillReach> {
  return apiRequest<SkillReach>(`/api/v1/roles/${encodeURIComponent(roleRef)}/skills`);
}

export function getSkillAudience(name: string): Promise<SkillAudience> {
  return apiRequest<SkillAudience>(`/api/v1/skills/${encodeURIComponent(name)}/assignments`);
}

export function addSkillAssignment(
  name: string,
  subject: { subject_type: "user" | "role"; subject_id: string },
): Promise<SkillAssignment> {
  return jsonRequest(`/api/v1/skills/${encodeURIComponent(name)}/assignments`, "POST", subject);
}

export async function removeSkillAssignment(name: string, assignmentId: string): Promise<void> {
  await apiRequest<void>(
    `/api/v1/skills/${encodeURIComponent(name)}/assignments/${encodeURIComponent(assignmentId)}`,
    { method: "DELETE" },
  );
}

export function setSkillDistributionMode(name: string, mode: DistributionMode): Promise<Skill> {
  return jsonRequest(`/api/v1/skills/${encodeURIComponent(name)}`, "PATCH", { distribution_mode: mode });
}

export function listApiKeys(
  filters: PageFilters & { status?: "active" | "inactive" } = {},
): Promise<PaginatedEnvelope<ApiKey>> {
  const keyword = filters.keyword?.trim().toLocaleLowerCase() ?? "";
  return listPage<ApiKey>("/api/v1/tenant/api-keys", filters, (item) =>
    (!filters.status || item.is_active === (filters.status === "active")) &&
    (!keyword || `${item.label ?? ""} ${item.id}`.toLocaleLowerCase().includes(keyword)));
}

export function listApiKeyOwners(
  filters: PageFilters = {},
): Promise<PaginatedEnvelope<ApiKeyOwner>> {
  const keyword = filters.keyword?.trim().toLocaleLowerCase() ?? "";
  return listPage<ApiKeyOwner>("/api/v1/tenant/api-key-owners", filters, (owner) =>
    !keyword || `${owner.name ?? ""} ${owner.email} ${owner.role}`.toLocaleLowerCase().includes(keyword));
}

export function createApiKey(input: { label: string | null; user_id: string | null }): Promise<CreatedApiKey> {
  return jsonRequest("/api/v1/tenant/api-keys", "POST", input);
}

export function updateApiKey(
  id: string,
  input: { label?: string | null; is_active?: boolean },
): Promise<ApiKey> {
  return jsonRequest(`/api/v1/tenant/api-keys/${encodeURIComponent(id)}`, "PATCH", input);
}
