import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";

import { apiRequestEnvelope } from "../../api/client";
import { findResource, type CatalogResource, type DataRow } from "../../api/dataCatalog";
import { useI18n } from "../../i18n";

// A `*_id` field names a row of another collection. Which one is a naming
// convention the API keeps consistently, so the picker resolves the target
// by the field's name and searches it by keyword; the person picks a row
// and the id lands in the field. Unknown names stay a plain text box.
const TARGETS: Record<string, string> = {
  customer_id: "customers",
  vendor_id: "vendors",
  product_id: "products",
  sku_id: "product-skus",
  employee_id: "employees",
  payee_employee_id: "employees",
  approver_employee_id: "employees",
  owner_employee_id: "employees",
  project_id: "projects",
  store_id: "stores",
  facility_id: "facilities",
  contract_id: "contracts",
  billing_account_id: "billing-accounts",
  fin_account_id: "fin-accounts",
  quotation_id: "sales-quotations",
  order_id: "sales-orders",
  sales_order_id: "sales-orders",
  original_order_id: "sales-orders",
  supersedes_order_id: "sales-orders",
  po_id: "purchase-orders",
  purchase_order_id: "purchase-orders",
  request_id: "purchase-requests",
  purchase_request_id: "purchase-requests",
  invoice_id: "invoices",
  payment_id: "payments",
  shipment_id: "shipments",
  picklist_id: "picklists",
  resource_id: "resources",
  category_id: "product-categories",
  channel_id: "sales-channels",
  bom_id: "bills-of-materials",
  attachment_id: "attachments",
  lead_id: "leads",
  campaign_id: "campaigns",
  parent_campaign_id: "campaigns",
  contact_id: "customer-contacts",
  event_id: "events",
  geo_id: "geos",
  parent_geo_id: "geos",
  territory_id: "territories",
  parent_territory_id: "territories",
  manager_employee_id: "employees",
  activity_id: "activities",
  communication_event_id: "communication-events",
  opportunity_id: "opportunities",
  policy_id: "policies",
  todo_id: "todos",
};

export function referenceTarget(fieldName: string): CatalogResource | undefined {
  const key = TARGETS[fieldName];
  return key ? findResource(key) : undefined;
}

// What a row is called to a person: its code, its number, its name — the
// first that exists — and the id as the last resort.
export function rowTitle(row: DataRow): string {
  for (const key of ["order_no", "quote_number", "invoice_no", "payment_no", "shipment_no", "picklist_no", "contract_no", "employee_code", "customer_code", "vendor_code", "product_code", "sku_code", "project_code", "code", "title", "name", "id"]) {
    const value = row[key];
    if (typeof value === "string" && value) return value;
  }
  return "";
}

function rowCaption(row: DataRow): string {
  const title = rowTitle(row);
  for (const key of ["name", "title", "customer_name_snapshot", "counterparty_name_snapshot", "product_name_snapshot"]) {
    const value = row[key];
    if (typeof value === "string" && value && value !== title) return value;
  }
  return "";
}

type ReferencePickerProps = {
  id: string;
  target: CatalogResource;
  value: string;
  required?: boolean;
  onChange: (value: string) => void;
};

export function ReferencePicker({ id, target, value, required, onChange }: ReferencePickerProps) {
  const { text, language } = useI18n();
  const listId = useId();
  const [keyword, setKeyword] = useState("");
  const [open, setOpen] = useState(false);
  const search = useQuery({
    queryKey: ["reference", target.key, keyword],
    queryFn: () => apiRequestEnvelope<DataRow[]>(`${target.path}?${new URLSearchParams({ keyword, size: "8", page: "1" })}`).then((envelope) => envelope.data),
    enabled: open && keyword.trim().length > 0 && target.filters.some((filter) => filter.name === "keyword"),
    staleTime: 30_000,
  });
  // the picked row, read back by id so the field shows a name, not a uuid
  const picked = useQuery({
    queryKey: ["reference", target.key, "row", value],
    queryFn: () => apiRequestEnvelope<DataRow>(`${target.path}/${encodeURIComponent(value)}`).then((envelope) => envelope.data),
    enabled: value.trim().length > 0 && Boolean(target.recordPath),
    staleTime: 5 * 60_000,
    retry: false,
  });
  useEffect(() => { if (!value) setKeyword(""); }, [value]);
  const label = target.label[language === "en" ? 1 : 0];

  return (
    <div className="reference-picker">
      <input
        id={id}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        required={required}
        placeholder={text(`搜索${label}…或粘贴 id`, `Search ${label}… or paste an id`)}
        value={open ? keyword : value}
        onFocus={() => { setOpen(true); setKeyword(""); }}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onChange={(event) => {
          setKeyword(event.target.value);
          // a pasted uuid is an answer, not a search
          if (/^[0-9a-f-]{32,36}$/i.test(event.target.value.trim())) { onChange(event.target.value.trim()); setOpen(false); }
        }}
      />
      {value && picked.data && (
        <small className="reference-picked">{rowTitle(picked.data)}{rowCaption(picked.data) ? ` · ${rowCaption(picked.data)}` : ""}</small>
      )}
      {value && picked.isError && <small className="reference-picked muted-value">{value}</small>}
      {value && !open && (
        <button type="button" className="text-action" onClick={() => onChange("")}>{text("清除", "Clear")}</button>
      )}
      {open && keyword.trim() && (
        <ul id={listId} role="listbox" className="reference-options">
          {search.isPending && <li className="muted-value">{text("搜索中…", "Searching…")}</li>}
          {search.data?.length === 0 && <li className="muted-value">{text("没有匹配", "No match")}</li>}
          {(search.data ?? []).map((row) => (
            <li key={String(row.id)} role="option" aria-selected={row.id === value}>
              <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => { onChange(String(row.id)); setOpen(false); }}>
                <strong>{rowTitle(row)}</strong>{rowCaption(row) && <span> · {rowCaption(row)}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
