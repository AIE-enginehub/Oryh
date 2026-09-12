import catalog from "./data-catalog.json";
import { apiRequestEnvelope, type PaginationMeta } from "./client";

// The data browser's catalogue is generated from the API contract by
// `scripts/export_console_catalog.py`: one entry per paged collection, its
// list filters, its row columns, and what the API lets a person do to a
// record — create, update, delete, and the record's own verbs. Nothing here
// is hand-typed per resource.

export type ScalarKind = "string" | "integer" | "number" | "boolean";
export type CatalogField = {
  name: string;
  type: ScalarKind;
  format?: string;
  enum?: string[];
  description?: string;
};
export type CatalogWriteField = CatalogField & {
  required: boolean;
  maxLength?: number;
};
export type CatalogAction = {
  verb: string;
  path: string;
  summary: string;
  fields: CatalogWriteField[];
};
export type CatalogResource = {
  key: string;
  path: string;
  group: string;
  label: [string, string];
  filters: CatalogField[];
  columns: CatalogField[];
  recordPath?: string;
  create?: CatalogWriteField[];
  update?: CatalogWriteField[];
  remove?: boolean;
  actions?: CatalogAction[];
  // this record's own sub-collections, already filtered to it
  related?: { resource: string; param: string; label: [string, string] }[];
};
export type CatalogGroup = { key: string; label: [string, string] };

export const dataCatalog = catalog as { groups: CatalogGroup[]; resources: CatalogResource[] };

export function findResource(key: string | undefined): CatalogResource | undefined {
  return dataCatalog.resources.find((resource) => resource.key === key);
}

export type DataRow = Record<string, unknown>;

export const DATA_PAGE_SIZE = 25;

// A URL's search params, minus the page, are exactly the request's query:
// the browser keeps the filter and sort state in the URL, so refresh, Back
// and a shared link land on the same rows.
export function listRows(
  resource: CatalogResource,
  params: URLSearchParams,
): Promise<{ data: DataRow[]; meta: PaginationMeta }> {
  const search = new URLSearchParams();
  for (const filter of resource.filters) {
    const value = params.get(filter.name);
    if (value !== null && value.trim() !== "") search.set(filter.name, value.trim());
  }
  const orderBy = params.get("order_by");
  if (orderBy) search.set("order_by", orderBy);
  const page = Number(params.get("page"));
  search.set("page", String(Number.isSafeInteger(page) && page > 0 ? page : 1));
  search.set("size", String(DATA_PAGE_SIZE));
  return apiRequestEnvelope<DataRow[], PaginationMeta>(`${resource.path}?${search.toString()}`);
}

// `-name` descending, `name` ascending, one key at a time from the header.
export function parseOrderBy(value: string | null): { column: string; descending: boolean } | null {
  if (!value) return null;
  const first = value.split(",")[0].trim();
  if (!first) return null;
  return first.startsWith("-") ? { column: first.slice(1), descending: true } : { column: first, descending: false };
}

export function nextOrderBy(current: string | null, column: string): string {
  const parsed = parseOrderBy(current);
  if (parsed?.column === column && !parsed.descending) return `-${column}`;
  return column;
}

// --- writes -----------------------------------------------------------------

export type WriteMethod = "POST" | "PATCH" | "DELETE";

// `/api/v1/sales-orders/{order_id}` + a row → the record's own URL.
export function recordUrl(template: string, id: string): string {
  return template.replace(/\{[^}]+\}/, encodeURIComponent(id));
}

export function writeRecord(method: WriteMethod, path: string, body?: DataRow): Promise<DataRow | undefined> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  return apiRequestEnvelope<DataRow | undefined>(path, init).then((envelope) => envelope.data);
}

// What a text box holds is a string; what the API wants is the field's type.
// An emptied field is `null` on update (clear it) and omitted on create.
export function coerceValue(field: CatalogWriteField, raw: string): unknown {
  const value = raw.trim();
  if (value === "") return null;
  if (field.type === "boolean") return value === "true";
  if (field.type === "integer") return Number.parseInt(value, 10);
  if (field.type === "number") return Number(value);
  return value;
}

export function formValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

// The body of an update is only what changed, so the confirmation shows
// exactly the fields about to be written and the server sees nothing else.
export function changedFields(fields: CatalogWriteField[], row: DataRow, draft: Record<string, string>): DataRow {
  const body: DataRow = {};
  for (const field of fields) {
    const before = formValue(row[field.name]);
    const after = (draft[field.name] ?? "").trim();
    if (before === after) continue;
    body[field.name] = coerceValue(field, after);
  }
  return body;
}

export function filledFields(fields: CatalogWriteField[], draft: Record<string, string>): DataRow {
  const body: DataRow = {};
  for (const field of fields) {
    const value = coerceValue(field, draft[field.name] ?? "");
    if (value !== null) body[field.name] = value;
  }
  return body;
}
