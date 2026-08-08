import type { PaginationMeta } from "../../api/client";
import { useI18n } from "../../i18n";

type PaginationProps = {
  meta: PaginationMeta;
  onPageChange: (page: number) => void;
};

export function Pagination({ meta, onPageChange }: PaginationProps) {
  const { text } = useI18n();
  if (meta.total === 0) return null;
  const start = (meta.page - 1) * meta.page_size + 1;
  const end = Math.min(meta.page * meta.page_size, meta.total);
  return (
    <footer className="pagination" aria-label={text("分页", "Pagination")}>
      <span>{text(`显示 ${start}–${end}，共 ${meta.total} 条`, `Showing ${start}–${end} of ${meta.total}`)}</span>
      <div>
        <button className="button compact" type="button" disabled={meta.page <= 1} onClick={() => onPageChange(meta.page - 1)}>{text("上一页", "Previous")}</button>
        <span className="page-indicator">{meta.page} / {Math.max(meta.pages, 1)}</span>
        <button className="button compact" type="button" disabled={meta.page >= meta.pages} onClick={() => onPageChange(meta.page + 1)}>{text("下一页", "Next")}</button>
      </div>
    </footer>
  );
}
