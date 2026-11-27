import { zhCN } from "../locales/zh-CN/console";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  getAccountLedger,
  getBalanceSheet,
  getCashSummary,
  getIncomeStatement,
  type Change,
  type CompareMode,
  type LayoutBlock,
  type Provisional,
  type StatementKind,
  type StatementSection,
} from "../api/statements";
import { apiErrorMessage, ListState } from "../components/master-data/ListState";
import { useI18n } from "../i18n";
import "./statements.css";

const z = zhCN.pagesStatementsPage;

function isoDay(day: Date): string {
  const month = String(day.getMonth() + 1).padStart(2, "0");
  return `${day.getFullYear()}-${month}-${String(day.getDate()).padStart(2, "0")}`;
}

function thisMonth(): { from: string; to: string; today: string } {
  const now = new Date();
  return {
    from: isoDay(new Date(now.getFullYear(), now.getMonth(), 1)),
    to: isoDay(new Date(now.getFullYear(), now.getMonth() + 1, 0)),
    today: isoDay(now),
  };
}

const numberFormat = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return numberFormat.format(value);
}

type Drill = { accountId: string; label: string; dateFrom?: string; dateTo: string };

/**
 * The three statements, read-only: what the book says, summed by the server.
 * Nothing here writes; keeping the book is the agent's (oryh-ledger).
 */
export function StatementsPage() {
  const { text } = useI18n();
  const month = thisMonth();
  const [kind, setKind] = useState<StatementKind>("income-statement");
  const [dateFrom, setDateFrom] = useState(month.from);
  const [dateTo, setDateTo] = useState(month.to);
  const [asOf, setAsOf] = useState(month.today);
  const [compare, setCompare] = useState<CompareMode>("previous_period");
  const [drill, setDrill] = useState<Drill | null>(null);

  const tabs: { key: StatementKind; label: string }[] = [
    { key: "income-statement", label: text(z.incomeStatement, "Income statement") },
    { key: "balance-sheet", label: text(z.balanceSheet, "Balance sheet") },
    { key: "cash-summary", label: text(z.cashSummary, "Cash summary") },
  ];

  const income = useQuery({
    queryKey: ["statements", "income-statement", dateFrom, dateTo, compare],
    queryFn: () => getIncomeStatement(dateFrom, dateTo, compare),
    enabled: kind === "income-statement",
    placeholderData: keepPreviousData,
  });
  const sheet = useQuery({
    queryKey: ["statements", "balance-sheet", asOf, compare],
    queryFn: () => getBalanceSheet(asOf, compare),
    enabled: kind === "balance-sheet",
    placeholderData: keepPreviousData,
  });
  const cash = useQuery({
    queryKey: ["statements", "cash-summary", dateFrom, dateTo, compare],
    queryFn: () => getCashSummary(dateFrom, dateTo, compare),
    enabled: kind === "cash-summary",
    placeholderData: keepPreviousData,
  });
  const active = kind === "income-statement" ? income : kind === "balance-sheet" ? sheet : cash;

  // the ledger behind a line: for a span, its lines in the span; at a day,
  // the lines of that day's month after the balance brought forward
  const open = (accountId: string, label: string) =>
    setDrill(kind === "balance-sheet"
      ? { accountId, label, dateFrom: `${asOf.slice(0, 8)}01`, dateTo: asOf }
      : { accountId, label, dateFrom, dateTo });

  return (
    <div className="master-data-page statements-page" data-testid="statements-page">
      <header className="page-intro">
        <div>
          <span className="eyebrow">{text(z.theBooks, "The books")}</span>
          <h2>{text(z.financialStatements, "Financial statements")}</h2>
          <p>{text(z.intro, "Every figure is summed from posted journal entries each time it is read. This page only reads; the book is kept by your agent.")}</p>
        </div>
      </header>

      <div className="statement-tabs" role="tablist" aria-label={text(z.statement, "Statement")}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={kind === tab.key}
            className={kind === tab.key ? "statement-tab active" : "statement-tab"}
            onClick={() => { setKind(tab.key); setDrill(null); }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <form className="statement-controls" onSubmit={(event) => event.preventDefault()}>
        {kind === "balance-sheet" ? (
          <div className="field"><label htmlFor="statement-as-of">{text(z.asOf, "As of")}</label>
            <input id="statement-as-of" type="date" value={asOf} onChange={(event) => event.target.value && setAsOf(event.target.value)} /></div>
        ) : (
          <>
            <div className="field"><label htmlFor="statement-from">{text(z.from, "From")}</label>
              <input id="statement-from" type="date" value={dateFrom} onChange={(event) => event.target.value && setDateFrom(event.target.value)} /></div>
            <div className="field"><label htmlFor="statement-to">{text(z.to, "To")}</label>
              <input id="statement-to" type="date" value={dateTo} onChange={(event) => event.target.value && setDateTo(event.target.value)} /></div>
          </>
        )}
        <div className="field"><label htmlFor="statement-compare">{text(z.compareWith, "Compare with")}</label>
          <select id="statement-compare" value={compare} onChange={(event) => setCompare(event.target.value as CompareMode)}>
            <option value="previous_period">{text(z.previousPeriod, "Previous period")}</option>
            <option value="previous_year">{text(z.previousYear, "Same period last year")}</option>
            <option value="none">{text(z.noComparison, "No comparison")}</option>
          </select></div>
      </form>

      <section className="data-panel" role="tabpanel" aria-label={tabs.find((tab) => tab.key === kind)?.label}>
        <ListState
          loading={active.isPending}
          error={active.isError ? apiErrorMessage(active.error) : null}
          empty={false}
          emptyTitle=""
          emptyDescription=""
          onRetry={() => void active.refetch()}
        >
          {kind === "income-statement" && income.data && (
            <>
              <ProvisionalNotice data={income.data} />
              <LayoutLines layout={income.data.layout} hasCompare={Boolean(income.data.compare)} onOpen={open} />
              <SectionsTable sections={income.data.sections} hasCompare={Boolean(income.data.compare)} onOpen={open}
                footer={{ label: text(z.result, "Result (income − expenses)"), figure: income.data.result }} />
            </>
          )}
          {kind === "balance-sheet" && sheet.data && (
            <>
              <ProvisionalNotice data={sheet.data} />
              {!sheet.data.balanced && (
                <p className="statement-alert" role="alert">{text(z.notBalanced, "Assets do not equal liabilities plus equity. This is a defect in the book: tell whoever keeps it.")}</p>
              )}
              <LayoutLines layout={sheet.data.layout} hasCompare={Boolean(sheet.data.compare)} onOpen={open} />
              <SectionsTable sections={sheet.data.sections} hasCompare={Boolean(sheet.data.compare)} onOpen={open} />
              <dl className="statement-totals">
                <div><dt>{text(z.totalAssets, "Total assets")}</dt><dd>{money(sheet.data.totals.assets)}</dd></div>
                <div><dt>{text(z.totalClaims, "Liabilities and equity")}</dt><dd>{money(sheet.data.totals.liabilities_and_equity)}</dd></div>
                <div><dt>{text(z.balanced, "Balanced")}</dt><dd>{sheet.data.balanced ? text(z.yes, "Yes") : text(z.no, "No")}</dd></div>
              </dl>
            </>
          )}
          {kind === "cash-summary" && cash.data && (
            <>
              <ProvisionalNotice data={cash.data} />
              {cash.data.cash_accounts.length === 0 ? (
                <p className="statement-notice" role="status">{text(z.noCashAccounts, "No ledger account is marked as a cash account yet. Ask your agent to mark the bank and cash accounts; the summary follows the money in and out of them.")}</p>
              ) : (
                <>
                  {!cash.data.reconciled && (
                    <p className="statement-alert" role="alert">{text(z.notReconciled, "Opening cash plus the net change does not equal closing cash. This is a defect in the book: tell whoever keeps it.")}</p>
                  )}
                  <LayoutLines layout={cash.data.layout} hasCompare={Boolean(cash.data.compare)} onOpen={open} />
                  <div className="table-scroll"><table className="data-table statement-table">
                    <caption>{text(z.cashAccounts, "Cash accounts")}</caption>
                    <thead><tr><th>{text(z.account, "Account")}</th><th className="figure">{text(z.opening, "Opening")}</th><th className="figure">{text(z.change, "Change")}</th><th className="figure">{text(z.closing, "Closing")}</th></tr></thead>
                    <tbody>{cash.data.cash_accounts.map((account) => (
                      <tr key={account.ledger_account_id}>
                        <td style={{ paddingInlineStart: `${0.75 + account.depth * 1.25}rem` }}>
                          <button className="record-name" type="button" onClick={() => open(account.ledger_account_id, `${account.account_code} ${account.name}`)}>{account.account_code} {account.name}</button>
                        </td>
                        <td className="figure">{money(account.opening)}</td><td className="figure">{money(account.change)}</td><td className="figure">{money(account.closing)}</td>
                      </tr>
                    ))}</tbody>
                    <tfoot><tr><th>{text(z.total, "Total")}</th><td className="figure">{money(cash.data.opening)}</td><td className="figure">{money(cash.data.net_change)}</td><td className="figure">{money(cash.data.closing)}</td></tr></tfoot>
                  </table></div>
                  <div className="table-scroll"><table className="data-table statement-table">
                    <caption>{text(z.whereTheMoneyCameFromAndWent, "Where the money came from and went")}</caption>
                    <thead><tr><th>{text(z.otherSide, "Other side")}</th><th className="figure">{text(z.received, "Received")}</th><th className="figure">{text(z.paid, "Paid")}</th><th className="figure">{text(z.net, "Net")}</th>{cash.data.compare && <th className="figure">{text(z.compare, "Compare")}</th>}</tr></thead>
                    {cash.data.sections.map((section) => (
                      <tbody key={section.key}>
                        <tr className="section-row"><th colSpan={3}>{section.label}</th><td className="figure">{money(section.net)}</td>{cash.data.compare && <td className="figure">{money(section.compare)}</td>}</tr>
                        {section.rows.map((row) => (
                          <tr key={row.ledger_account_id}>
                            <td><button className="record-name" type="button" onClick={() => open(row.ledger_account_id, `${row.account_code} ${row.name}`)}>{row.account_code} {row.name}</button></td>
                            <td className="figure">{money(row.received)}</td><td className="figure">{money(row.paid)}</td><td className="figure">{money(row.net)}</td>
                            {cash.data.compare && <td className="figure">{money(row.compare)}</td>}
                          </tr>
                        ))}
                      </tbody>
                    ))}
                  </table></div>
                  {cash.data.transfers.count > 0 && (
                    <p className="statement-notice">{text(z.transfers(cash.data.transfers.count, money(cash.data.transfers.amount)), `${cash.data.transfers.count} transfer(s) between cash accounts, ${money(cash.data.transfers.amount)} in all, move no money in or out.`)}</p>
                  )}
                  <p className="statement-basis">{cash.data.basis}</p>
                </>
              )}
            </>
          )}
        </ListState>
      </section>

      {drill && <AccountLedgerPanel drill={drill} onClose={() => setDrill(null)} />}
    </div>
  );
}

function ProvisionalNotice({ data }: { data: Provisional }) {
  const { text } = useI18n();
  const open = data.period_status.open_months.map((day) => day.slice(0, 7));
  const missing = data.coverage.reduce((sum, month) => sum + month.missing, 0);
  const stale = data.coverage.reduce((sum, month) => sum + month.stale, 0);
  const reasons: string[] = [];
  if (open.length) reasons.push(text(z.openMonths(open.join(", ")), `${open.join(", ")} not closed`));
  if (data.drafts) reasons.push(text(z.drafts(data.drafts), `${data.drafts} draft entr${data.drafts === 1 ? "y" : "ies"} left out`));
  if (missing) reasons.push(text(z.missing(missing), `${missing} document(s) not in the book yet`));
  if (stale) reasons.push(text(z.stale(stale), `${stale} entr${stale === 1 ? "y" : "ies"} for documents since voided`));
  return (
    <div className="statement-status" role="status">
      {reasons.length
        ? <p className="statement-notice"><strong>{text(z.notFinal, "These figures are not final:")}</strong> {reasons.join("; ")}.</p>
        : <p className="statement-notice final">{text(z.final, "Every month in this span is closed and nothing is missing.")}</p>}
      {data.currency && <span className="statement-currency">{data.currency}</span>}
    </div>
  );
}

function Figures({ figure, hasCompare }: { figure: Change & { amount?: number | null; total?: number }; hasCompare: boolean }) {
  const { text } = useI18n();
  const amount = figure.amount ?? figure.total;
  return (
    <>
      <td className="figure">{money(amount)}</td>
      {hasCompare && <td className="figure">{money(figure.compare)}</td>}
      {hasCompare && (
        <td className="figure">
          {figure.change === undefined ? "" : money(figure.change)}
          {figure.change_ratio !== undefined && (
            <small>{figure.change_ratio === null ? text(z.new, "new") : `${(figure.change_ratio * 100).toFixed(1)}%`}</small>
          )}
        </td>
      )}
    </>
  );
}

function FigureHeads({ hasCompare }: { hasCompare: boolean }) {
  const { text } = useI18n();
  return (
    <>
      <th className="figure">{text(z.amount, "Amount")}</th>
      {hasCompare && <th className="figure">{text(z.compare, "Compare")}</th>}
      {hasCompare && <th className="figure">{text(z.change, "Change")}</th>}
    </>
  );
}

function SectionsTable({ sections, hasCompare, onOpen, footer }: {
  sections: StatementSection[];
  hasCompare: boolean;
  onOpen: (accountId: string, label: string) => void;
  footer?: { label: string; figure: Change & { amount: number } };
}) {
  const { text } = useI18n();
  return (
    <div className="table-scroll"><table className="data-table statement-table">
      <caption>{text(z.byAccount, "By account")}</caption>
      <thead><tr><th>{text(z.account, "Account")}</th><FigureHeads hasCompare={hasCompare} /></tr></thead>
      {sections.map((section) => (
        <tbody key={section.key}>
          <tr className="section-row"><th>{section.label}</th><Figures figure={section} hasCompare={hasCompare} /></tr>
          {section.rows.map((row) => (
            <tr key={row.ledger_account_id} className={row.summary ? "summary-row" : undefined}>
              <td style={{ paddingInlineStart: `${0.75 + row.depth * 1.25}rem` }}>
                <button className="record-name" type="button" onClick={() => onOpen(row.ledger_account_id, `${row.account_code} ${row.name}`)}>
                  {row.account_code} {row.name}
                </button>
              </td>
              <Figures figure={row} hasCompare={hasCompare} />
            </tr>
          ))}
          {section.earnings_not_yet_closed && (
            <tr><td>{text(z.earningsNotYetClosed, "Earnings not yet closed")}</td><Figures figure={section.earnings_not_yet_closed} hasCompare={hasCompare} /></tr>
          )}
        </tbody>
      ))}
      {footer && (
        <tfoot><tr><th>{footer.label}</th><Figures figure={footer.figure} hasCompare={hasCompare} /></tr></tfoot>
      )}
    </table></div>
  );
}

function LayoutLines({ layout, hasCompare, onOpen }: {
  layout: LayoutBlock | null;
  hasCompare: boolean;
  onOpen: (accountId: string, label: string) => void;
}) {
  const { text } = useI18n();
  if (!layout) return null;
  return (
    <>
      {layout.unplaced.length > 0 && (
        <p className="statement-alert" role="alert">
          {text(z.unplaced, "Accounts no line of this layout takes (their money is still in the totals):")}{" "}
          {layout.unplaced.map((item) => `${item.account_code ?? ""} ${item.name} ${money(item.amount)}`.trim()).join("; ")}
        </p>
      )}
      {layout.clashes.length > 0 && (
        <p className="statement-alert" role="alert">
          {text(z.clashes, "Accounts that fall into two lines (the first takes them):")}{" "}
          {layout.clashes.map((clash) => `${clash.account_code} → ${clash.rows.join(", ")}`).join("; ")}
        </p>
      )}
      <div className="table-scroll"><table className="data-table statement-table layout-table">
        <caption>{layout.name} <small>{text(z.confirmedBy(layout.confirmed_by), `confirmed by ${layout.confirmed_by}`)}</small></caption>
        <thead><tr><th>{text(z.line, "Line")}</th><FigureHeads hasCompare={hasCompare} /></tr></thead>
        <tbody>{layout.lines.map((line) => (
          <tr key={line.code} className={`layout-${line.kind}`}>
            <th scope="row">
              {line.label}
              {line.accounts && line.accounts.length > 0 && (
                <small className="layout-accounts">{line.accounts.map((account) => (
                  <button key={account.ledger_account_id} type="button" className="text-action" onClick={() => onOpen(account.ledger_account_id, `${account.account_code} ${account.name}`)}>
                    {account.account_code}
                  </button>
                ))}</small>
              )}
            </th>
            {line.kind === "heading" ? <td colSpan={hasCompare ? 3 : 1} /> : <Figures figure={line} hasCompare={hasCompare} />}
          </tr>
        ))}</tbody>
      </table></div>
    </>
  );
}

function AccountLedgerPanel({ drill, onClose }: { drill: Drill; onClose: () => void }) {
  const { text } = useI18n();
  const ledger = useQuery({
    queryKey: ["statements", "ledger", drill.accountId, drill.dateFrom, drill.dateTo],
    queryFn: () => getAccountLedger(drill.accountId, drill.dateFrom, drill.dateTo),
  });
  return (
    <section className="data-panel statement-ledger" aria-label={text(z.accountLedger, "Account ledger")}>
      <header className="statement-ledger-head">
        <h3>{drill.label} <small>{drill.dateFrom ?? ""} – {drill.dateTo}</small></h3>
        <button className="button" type="button" onClick={onClose}>{text(z.close, "Close")}</button>
      </header>
      <ListState
        loading={ledger.isPending}
        error={ledger.isError ? apiErrorMessage(ledger.error) : null}
        empty={Boolean(ledger.data && ledger.data.lines.length === 0)}
        emptyTitle={text(z.noLines, "No posted lines in this span")}
        emptyDescription={text(z.noLinesDescription, "The balance brought forward is the whole figure.")}
        onRetry={() => void ledger.refetch()}
      >
        {ledger.data && (
          <div className="table-scroll"><table className="data-table statement-table">
            <thead><tr><th>{text(z.date, "Date")}</th><th>{text(z.entry, "Entry")}</th><th>{text(z.description, "Description")}</th><th className="figure">{text(z.debit, "Debit")}</th><th className="figure">{text(z.credit, "Credit")}</th><th className="figure">{text(z.balance, "Balance")}</th></tr></thead>
            <tbody>
              <tr className="section-row"><td colSpan={5}>{text(z.broughtForward, "Brought forward")}</td><td className="figure">{money(ledger.data.opening)}</td></tr>
              {ledger.data.lines.map((line, index) => (
                <tr key={`${line.entry_no}-${index}`}>
                  <td className="mono-cell">{line.posting_date}</td><td className="mono-cell">{line.entry_no}</td><td>{line.description}</td>
                  <td className="figure">{line.debit ? money(line.debit) : ""}</td><td className="figure">{line.credit ? money(line.credit) : ""}</td><td className="figure">{money(line.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </ListState>
    </section>
  );
}
