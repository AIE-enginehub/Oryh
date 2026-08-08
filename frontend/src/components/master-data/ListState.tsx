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
    return <div className="table-state" aria-busy="true"><span className="spinner" />{text("正在加载数据…", "Loading data…")}</div>;
  }
  if (error) {
    return <div className="table-state error-state" role="alert"><strong>{text("数据加载失败", "Data could not be loaded")}</strong><span>{error}</span><button className="button" type="button" onClick={onRetry}>{text("重试", "Retry")}</button></div>;
  }
  if (empty) {
    return <div className="table-state empty-state"><span className="empty-mark" aria-hidden="true">∅</span><strong>{emptyTitle}</strong><span>{emptyDescription}</span></div>;
  }
  return <>{children}</>;
}

export function StatusBadge({ status }: { status: string }) {
  const { text } = useI18n();
  const labels: Record<string, string> = { active: text("启用", "Active"), inactive: text("停用", "Inactive"), archived: text("已归档", "Archived") };
  return <span className={`status-badge ${status}`}>{labels[status] ?? status}</span>;
}

export function apiErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return typeof document !== "undefined" && document.documentElement.lang === "en"
    ? "Request failed. Please try again shortly."
    : "请求失败，请稍后重试。";
}
