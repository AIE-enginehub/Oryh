import { zhCN } from "../../locales/zh-CN/console";
import { useEffect, useState, type FormEvent } from "react";
import { useI18n } from "../../i18n";

type Option = { value: string; label: string };

type ActivityToolbarProps = {
  idPrefix: string;
  keyword: string;
  primary: string;
  entityType: string;
  keywordPlaceholder: string;
  primaryLabel: string;
  primaryOptions: Option[];
  entityOptions: Option[];
  onApply: (filters: { keyword: string; primary: string; entityType: string }) => void;
};

export function ActivityToolbar({
  idPrefix,
  keyword,
  primary,
  entityType,
  keywordPlaceholder,
  primaryLabel,
  primaryOptions,
  entityOptions,
  onApply,
}: ActivityToolbarProps) {
  const { text } = useI18n();
  const [draftKeyword, setDraftKeyword] = useState(keyword);
  const [draftPrimary, setDraftPrimary] = useState(primary);
  const [draftEntityType, setDraftEntityType] = useState(entityType);
  useEffect(() => setDraftKeyword(keyword), [keyword]);
  useEffect(() => setDraftPrimary(primary), [primary]);
  useEffect(() => setDraftEntityType(entityType), [entityType]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onApply({ keyword: draftKeyword.trim(), primary: draftPrimary, entityType: draftEntityType });
  };
  const clear = () => {
    setDraftKeyword("");
    setDraftPrimary("");
    setDraftEntityType("");
    onApply({ keyword: "", primary: "", entityType: "" });
  };

  return (
    <div className="activity-toolbar">
      <form className="activity-filter" role="search" onSubmit={submit}>
        <label className="sr-only" htmlFor={`${idPrefix}-keyword`}>{text(zhCN.componentsActivityActivityToolbar.search, "Search")}</label>
        <input id={`${idPrefix}-keyword`} type="search" value={draftKeyword} placeholder={keywordPlaceholder} onChange={(event) => setDraftKeyword(event.target.value)} />
        <label className="sr-only" htmlFor={`${idPrefix}-primary`}>{primaryLabel}</label>
        <select id={`${idPrefix}-primary`} value={draftPrimary} onChange={(event) => setDraftPrimary(event.target.value)}>
          <option value="">{text(zhCN.componentsActivityActivityToolbar.all(`${primaryLabel}`), `All ${primaryLabel}`)}</option>
          {primaryOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
        <label className="sr-only" htmlFor={`${idPrefix}-entity`}>{text(zhCN.componentsActivityActivityToolbar.objectType, "Object type")}</label>
        <select id={`${idPrefix}-entity`} value={draftEntityType} onChange={(event) => setDraftEntityType(event.target.value)}>
          <option value="">{text(zhCN.componentsActivityActivityToolbar.allObjectTypes, "All object types")}</option>
          {entityOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
        <button className="button" type="submit">{text(zhCN.componentsActivityActivityToolbar.filter, "Filter")}</button>
        {(keyword || primary || entityType) && <button className="button quiet" type="button" onClick={clear}>{text(zhCN.componentsActivityActivityToolbar.clear, "Clear")}</button>}
      </form>
    </div>
  );
}
