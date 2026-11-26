import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { PaginatedEnvelope } from "../../api/client";
import { useI18n } from "../../i18n";
import { zhCN } from "../../locales/zh-CN/console";
import { apiErrorMessage } from "./ListState";
import { Pagination } from "./Pagination";

type NamedRecord = { id: string; name: string };
type Props = {
  id: string;
  label: string;
  emptyLabel: string;
  value: string;
  list: (filters: { keyword?: string; page: number; size: number; status: "active" }) => Promise<PaginatedEnvelope<NamedRecord>>;
  get: (id: string) => Promise<NamedRecord>;
  onChange: (id: string) => void;
};

export function RecordSelect({ id, label, emptyLabel, value, list, get, onChange }: Props) {
  const { text } = useI18n();
  const searchLabel = text(zhCN.pagesProjectsPage.searchRecords(label), `Search ${label}`);
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const filters = { page, size: 50, status: "active" as const, keyword: keyword.trim() || undefined };
  const options = useQuery({ queryKey: ["record-select", id, filters], queryFn: () => list(filters) });
  const rows = options.data?.data ?? [];
  const missing = Boolean(value) && !rows.some((row) => row.id === value);
  const selected = useQuery({
    queryKey: ["record-select", id, "selected", value],
    queryFn: () => get(value),
    enabled: missing && !options.isPending,
    retry: false,
  });
  return (
    <>
      <label htmlFor={id}>{label}</label>
      <input type="search" aria-label={searchLabel} placeholder={searchLabel} value={keyword}
        onKeyDown={(event) => { if (event.key === "Enter") event.preventDefault(); }}
        onChange={(event) => { setKeyword(event.target.value); setPage(1); }} />
      <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{emptyLabel}</option>
        {missing && <option value={value}>{selected.data?.name || value}</option>}
        {rows.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
      </select>
      {options.isPending && <small role="status">{text(zhCN.componentsDataReferencePicker.searching, "Searching…")}</small>}
      {options.isSuccess && !rows.length && keyword && <small role="status">{text(zhCN.componentsDataReferencePicker.noMatch, "No match")}</small>}
      {options.isError && <small role="alert">{apiErrorMessage(options.error)}</small>}
      {options.data && options.data.meta.pages > 1 && <Pagination meta={options.data.meta} onPageChange={setPage} />}
    </>
  );
}
