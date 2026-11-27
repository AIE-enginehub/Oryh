import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../i18n";
import { StatementsPage } from "./StatementsPage";

const api = vi.hoisted(() => ({
  getIncomeStatement: vi.fn(),
  getBalanceSheet: vi.fn(),
  getCashSummary: vi.fn(),
  getAccountLedger: vi.fn(),
}));
vi.mock("../api/statements", async () => ({
  ...(await vi.importActual<typeof import("../api/statements")>("../api/statements")),
  ...api,
}));

const provisional = {
  currency: "CNY",
  period_status: { open_months: ["2026-03-01"], closed_months: [] },
  drafts: 1,
  coverage: [{ period: "2026-03-01", missing: 3, stale: 0 }],
  layout: null,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider defaultLanguage="en">
        <MemoryRouter><StatementsPage /></MemoryRouter>
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.setItem("oryh.console.language", "en");
  api.getIncomeStatement.mockResolvedValue({
    ...provisional,
    date_from: "2026-03-01", date_to: "2026-03-31",
    compare: { date_from: "2026-02-01", date_to: "2026-02-28" },
    sections: [
      { key: "income", label: "Income", total: 5000, compare: 1000, change: 4000, change_ratio: 4,
        rows: [{ ledger_account_id: "acc-sales", account_code: "6001", name: "Sales", depth: 0, summary: false,
                 amount: 5000, compare: 1000, change: 4000, change_ratio: 4 }] },
      { key: "expense", label: "Expenses", total: 2000, compare: 0, change: 2000, change_ratio: null, rows: [] },
    ],
    result: { amount: 3000, compare: 1000, change: 2000, change_ratio: 2 },
  });
  api.getAccountLedger.mockResolvedValue({
    ledger_account_id: "acc-sales", account_code: "6001", opening: 0, closing: -5000, total_lines: 1,
    lines: [{ posting_date: "2026-03-05", entry_no: "JE-0007", description: "March sales", debit: 0, credit: 5000,
              balance: -5000 }],
  });
  api.getBalanceSheet.mockResolvedValue({
    ...provisional,
    as_of: "2026-03-31", compare: null,
    sections: [
      { key: "asset", label: "Assets", total: 10500, rows: [] },
      { key: "liability", label: "Liabilities", total: 0, rows: [] },
      { key: "equity", label: "Equity", total: 10500, rows: [],
        earnings_not_yet_closed: { key: "earnings_not_yet_closed", name: "Earnings not yet closed", amount: 500 } },
    ],
    totals: { assets: 10500, liabilities_and_equity: 10400 },
    balanced: false,
  });
  api.getCashSummary.mockResolvedValue({
    ...provisional,
    date_from: "2026-03-01", date_to: "2026-03-31", compare: null, basis: "Money into and out of the cash accounts.",
    cash_accounts: [], opening: 0, closing: 0, net_change: 0, sections: [],
    transfers: { count: 0, amount: 0 }, reconciled: true,
  });
});

afterEach(cleanup);

describe("StatementsPage", () => {
  it("says the figures are not final before showing them, and opens an account's ledger", async () => {
    const user = userEvent.setup();
    renderPage();
    const notice = await screen.findByText(/These figures are not final/);
    expect(notice.parentElement).toHaveTextContent("2026-03 not closed");
    expect(notice.parentElement).toHaveTextContent("1 draft entry left out");
    expect(notice.parentElement).toHaveTextContent("3 document(s) not in the book yet");
    expect(screen.getByText("Result (income − expenses)").closest("tr")).toHaveTextContent("3,000.00");
    const sales = screen.getByRole("button", { name: "6001 Sales" }).closest("tr");
    expect(sales).toHaveTextContent("5,000.00");
    expect(sales).toHaveTextContent("400.0%");
    expect(screen.getByText("Expenses").closest("tr")).toHaveTextContent("new");

    await user.click(screen.getByRole("button", { name: "6001 Sales" }));
    const ledger = await screen.findByRole("region", { name: "Account ledger" });
    expect(await within(ledger).findByText("JE-0007")).toBeInTheDocument();
    expect(api.getAccountLedger).toHaveBeenCalledWith("acc-sales", expect.stringMatching(/-01$/), expect.any(String));
  });

  it("states a balance sheet that does not balance as a defect", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Balance sheet" }));
    expect(await screen.findByText(/Assets do not equal liabilities plus equity/)).toBeInTheDocument();
    expect(screen.getByText("Earnings not yet closed").closest("tr")).toHaveTextContent("500.00");
  });

  it("asks for cash accounts when none is marked", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Cash summary" }));
    expect(await screen.findByText(/No ledger account is marked as a cash account yet/)).toBeInTheDocument();
  });
});
