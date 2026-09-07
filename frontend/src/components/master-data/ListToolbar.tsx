import { MagnifyingGlass, Plus } from "@phosphor-icons/react";
import { useCreateIntent } from "./useCreateIntent";
import { useEffect, useId, useState, type FormEvent } from "react";
import { useI18n } from "../../i18n";

type ListToolbarProps = {
  keyword: string;
  status: string;
  placeholder: string;
  createLabel: string;
  statusOptions: Array<{ value: string; label: string }>;
  onApply: (filters: { keyword: string; status: string }) => void;
  onCreate: () => void;
};

export function ListToolbar({ keyword, status, placeholder, createLabel, statusOptions, onApply, onCreate }: ListToolbarProps) {
  const { text } = useI18n();
  const id = useId();
  useCreateIntent(onCreate);
  const [draftKeyword, setDraftKeyword] = useState(keyword);
  const [draftStatus, setDraftStatus] = useState(status);
  useEffect(() => setDraftKeyword(keyword), [keyword]);
  useEffect(() => setDraftStatus(status), [status]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onApply({ keyword: draftKeyword.trim(), status: draftStatus });
  };

  return (
    <div className="list-toolbar">
      <form className="filter-form" role="search" onSubmit={submit}>
        <label className="sr-only" htmlFor={`${id}-search`}>{text("搜索", "Search")}</label>
        <div className="list-search"><MagnifyingGlass size={18} aria-hidden /><input id={`${id}-search`} type="search" value={draftKeyword} placeholder={placeholder} onChange={(event) => setDraftKeyword(event.target.value)} /></div>
        <label className="sr-only" htmlFor={`${id}-status`}>{text("状态", "Status")}</label>
        <select id={`${id}-status`} value={draftStatus} onChange={(event) => { setDraftStatus(event.target.value); onApply({ keyword: draftKeyword.trim(), status: event.target.value }); }}>
          <option value="">{text("全部状态", "All statuses")}</option>
          {statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
        <button className="button" type="submit">{text("筛选", "Filter")}</button>
        {(keyword || status) && (
          <button className="button quiet" type="button" onClick={() => { setDraftKeyword(""); setDraftStatus(""); onApply({ keyword: "", status: "" }); }}>{text("清除", "Clear")}</button>
        )}
      </form>
      <button className="button primary" type="button" onClick={onCreate}><Plus size={17} aria-hidden />{createLabel}</button>
    </div>
  );
}
