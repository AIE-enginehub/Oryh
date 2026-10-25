import { zhCN } from "../../locales/zh-CN/console";
import { Tray } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { useI18n } from "../../i18n";

type ListStateProps = {
  loading: boolean;
  error: string | null;
  empty: boolean;
  emptyTitle: string;
  emptyDescription: string;
  onRetry: () => void;
  children: ReactNode;
};

export function ListState({ loading, error, empty, emptyTitle, emptyDescription, onRetry, children }: ListStateProps) {
  const { text } = useI18n();
  if (loading) {
    return <div className="table-state" aria-busy="true"><span className="spinner" />{text(zhCN.componentsMasterDataListState.loadingData, "Loading data…")}</div>;
  }
  if (error) {
    return <div className="table-state error-state" role="alert"><strong>{text(zhCN.componentsMasterDataListState.dataCouldNotBeLoaded, "Data could not be loaded")}</strong><span>{error}</span><button className="button" type="button" onClick={onRetry}>{text(zhCN.componentsMasterDataListState.retry, "Retry")}</button></div>;
  }
  if (empty) {
    return <div className="table-state empty-state"><span className="empty-mark" aria-hidden="true"><Tray size={25} /></span><strong>{emptyTitle}</strong><span>{emptyDescription}</span></div>;
  }
  return <>{children}</>;
}

export function StatusBadge({ status }: { status: string }) {
  const { text } = useI18n();
  const labels: Record<string, string> = {
    active: text(zhCN.componentsMasterDataListState.active, "Active"), inactive: text(zhCN.componentsMasterDataListState.inactive, "Inactive"), archived: text(zhCN.componentsMasterDataListState.archived, "Archived"),
    draft: text(zhCN.componentsMasterDataListState.draft, "Draft"), published: text(zhCN.componentsMasterDataListState.published, "Published"), superseded: text(zhCN.componentsMasterDataListState.superseded, "Superseded"), repealed: text(zhCN.componentsMasterDataListState.repealed, "Repealed"),
  };
  return <span className={`status-badge ${status}`}>{labels[status] ?? status}</span>;
}

export function apiErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return typeof document !== "undefined" && document.documentElement.lang === "en"
    ? "Request failed. Please try again shortly."
    : zhCN.componentsMasterDataListState.message;
}
