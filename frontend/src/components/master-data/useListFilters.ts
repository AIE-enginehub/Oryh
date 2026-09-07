import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

// Keep list state in the URL so refresh, shared links and browser Back agree.
// Filters are applied atomically: separate setSearchParams calls are not queued.
export function useListFilters<Status extends string>(
  allowedStatuses: readonly Status[],
) {
  const [params, setParams] = useSearchParams();
  const keyword = params.get("keyword") ?? "";
  const requested = params.get("status") ?? "";
  const status = (
    allowedStatuses.includes(requested as Status) ? requested : ""
  ) as Status | "";
  const rawPage = Number(params.get("page"));
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
  const setPage = useCallback(
    (nextPage: number) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (nextPage <= 1) next.delete("page");
          else next.set("page", String(nextPage));
          return next;
        },
        { preventScrollReset: true },
      );
    },
    [setParams],
  );
  const applyFilters = useCallback(
    (filters: { keyword: string; status: string }) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          const normalized = filters.keyword.trim();
          if (normalized) next.set("keyword", normalized);
          else next.delete("keyword");
          if (filters.status) next.set("status", filters.status);
          else next.delete("status");
          next.delete("page");
          return next;
        },
        { preventScrollReset: true },
      );
    },
    [setParams],
  );
  return { keyword, status, page, setPage, applyFilters };
}
