// The three financial statements (plan docs/plans/financial-statements-2026-11-25.md).
// Read-only: every figure is derived by the server from posted journal lines.
// The routes return untyped JSON, so the shapes the console reads are declared here.
import { apiRequest } from "./client";

export type StatementKind = "income-statement" | "balance-sheet" | "cash-summary";
export type CompareMode = "previous_period" | "previous_year" | "none";

export type Change = {
  compare?: number;
  change?: number;
  change_ratio?: number | null;
};

export type StatementRow = Change & {
  ledger_account_id: string;
  account_code: string;
  name: string;
  depth: number;
  summary: boolean;
  amount: number;
};

export type StatementSection = Change & {
  key: string;
  label: string;
  total: number;
  rows: StatementRow[];
  earnings_not_yet_closed?: Change & { key: string; name: string; amount: number };
};

export type LayoutLine = Change & {
  row_no: number;
  code: string;
  label: string;
  kind: "accounts" | "total" | "heading";
  amount: number | null;
  accounts?: { ledger_account_id: string; account_code: string; name: string; amount: number }[];
};

export type LayoutBlock = {
  id: string;
  name: string;
  confirmed_by: string;
  lines: LayoutLine[];
  unplaced: { ledger_account_id?: string; key?: string; account_code?: string; name: string; amount: number }[];
  clashes: { ledger_account_id: string; account_code: string; rows: string[] }[];
};

export type Provisional = {
  currency: string | null;
  period_status: { open_months: string[]; closed_months: string[] };
  drafts: number;
  coverage: { period: string; missing: number; stale: number }[];
  layout: LayoutBlock | null;
};

export type IncomeStatement = Provisional & {
  date_from: string;
  date_to: string;
  compare: { date_from: string; date_to: string } | null;
  sections: StatementSection[];
  result: Change & { amount: number };
};

export type BalanceSheet = Provisional & {
  as_of: string;
  compare: { as_of: string } | null;
  sections: StatementSection[];
  totals: { assets: number; liabilities_and_equity: number };
  balanced: boolean;
};

export type CashRow = Change & {
  ledger_account_id: string;
  account_code: string;
  name: string;
  received: number;
  paid: number;
  net: number;
};

export type CashSummary = Provisional & {
  date_from: string;
  date_to: string;
  compare: { date_from: string; date_to: string } | null;
  basis: string;
  cash_accounts: {
    ledger_account_id: string;
    account_code: string;
    name: string;
    depth: number;
    opening: number;
    closing: number;
    change: number;
  }[];
  opening: number;
  closing: number;
  net_change: number;
  net_change_compare?: number;
  sections: (Change & { key: string; label: string; net: number; rows: CashRow[] })[];
  transfers: { count: number; amount: number };
  reconciled: boolean;
};

export type AccountLedger = {
  ledger_account_id: string;
  account_code: string;
  opening: number;
  closing: number;
  total_lines: number;
  lines: {
    posting_date: string;
    entry_no: string;
    description: string | null;
    debit: number;
    credit: number;
    balance: number;
  }[];
};

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (value) search.set(name, value);
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function getIncomeStatement(dateFrom: string, dateTo: string, compare: CompareMode): Promise<IncomeStatement> {
  return apiRequest<IncomeStatement>(
    `/api/v1/income-statement${query({ date_from: dateFrom, date_to: dateTo, compare })}`,
  );
}

export function getBalanceSheet(asOf: string, compare: CompareMode): Promise<BalanceSheet> {
  return apiRequest<BalanceSheet>(`/api/v1/balance-sheet${query({ as_of: asOf, compare })}`);
}

export function getCashSummary(dateFrom: string, dateTo: string, compare: CompareMode): Promise<CashSummary> {
  return apiRequest<CashSummary>(`/api/v1/cash-summary${query({ date_from: dateFrom, date_to: dateTo, compare })}`);
}

export function getAccountLedger(accountId: string, dateFrom: string | undefined, dateTo: string): Promise<AccountLedger> {
  return apiRequest<AccountLedger>(
    `/api/v1/ledger-accounts/${encodeURIComponent(accountId)}/ledger${query({ date_from: dateFrom, date_to: dateTo, size: "200" })}`,
  );
}
