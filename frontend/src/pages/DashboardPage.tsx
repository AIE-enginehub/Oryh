import { useQuery } from "@tanstack/react-query";
import { Link, useOutletContext } from "react-router-dom";
import {
  ArrowClockwise,
  ArrowRight,
  CheckCircle,
  Clock,
  Files,
  Plus,
  Robot,
  Users,
} from "@phosphor-icons/react";

import { ApiError, getDashboard } from "../api/client";
import { listTodos } from "../api/activity";
import type { ConsoleContext } from "../App";
import { useI18n } from "../i18n";
import {
  canManageAccess,
  canManageTenantConfiguration,
  hasCapability,
} from "../access";
import { visibleNavigation } from "../navigation";
import { useActivityLabels } from "../components/activity/labels";
import {
  ListState,
  apiErrorMessage,
} from "../components/master-data/ListState";

export function DashboardPage() {
  const { t, text, language } = useI18n();
  const { bootstrap } = useOutletContext<ConsoleContext>();
  const { entityLabels } = useActivityLabels();
  const canSeeAll =
    bootstrap.role === "admin" ||
    hasCapability(bootstrap, "tenant.act_for_any_employee");
  const employeeScope = canSeeAll
    ? undefined
    : (bootstrap.employee_id ?? undefined);
  const canReadTodos = canSeeAll || Boolean(employeeScope);
  const canReadObjects = canManageTenantConfiguration(bootstrap);
  const canReadUsers = canManageAccess(bootstrap);
  const shortcuts = visibleNavigation(bootstrap)
    .flatMap((group) => group.items)
    .filter((item) => item.createLabel);
  const dashboard = useQuery({
    queryKey: ["console", "dashboard"],
    queryFn: getDashboard,
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status < 500) && failureCount < 1,
  });
  const todos = useQuery({
    queryKey: ["activity", "todos", "dashboard", employeeScope],
    queryFn: () =>
      listTodos({ status: "open", size: 5, employee_id: employeeScope }),
    enabled: canReadTodos,
    retry: false,
  });
  const metrics = [
    {
      key: "objects",
      label: text("业务记录", "Business records"),
      icon: Files,
      note: text("未删除的业务对象", "Business objects on record"),
      href: canReadObjects ? "/objects" : undefined,
    },
    {
      key: "todos_open",
      label: text("未完成待办", "Open to-dos"),
      icon: CheckCircle,
      note: text("等待处理的工作项", "Work awaiting completion"),
      href: canSeeAll ? "/todos?status=open" : undefined,
    },
    {
      key: "todos_overdue",
      label: text("逾期待办", "Overdue to-dos"),
      icon: Clock,
      note: text("已超过截止时间", "Past their due date"),
      warning: true,
    },
    {
      key: "users",
      label: text("活跃用户", "Active users"),
      icon: Users,
      note: text("当前工作空间", "In this workspace"),
      href: canReadUsers ? "/users" : undefined,
    },
  ] as const;
  const refresh = () => {
    void dashboard.refetch();
    if (canReadTodos) void todos.refetch();
  };
  const updated = dashboard.dataUpdatedAt
    ? new Intl.DateTimeFormat(language, {
        hour: "2-digit",
        minute: "2-digit",
      }).format(dashboard.dataUpdatedAt)
    : null;
  return (
    <div className="workspace-dashboard">
      <header className="workspace-welcome">
        <div>
          <span className="workspace-kicker">{bootstrap.tenant.name}</span>
          <h2>{text("工作，从这里开始。", "A clear view of your work.")}</h2>
          <p>
            {text(
              "查看业务进展，找到所需数据，处理日常事务。",
              "See what needs attention, find your data, and keep business moving.",
            )}
          </p>
        </div>
        <div className="workspace-refresh">
          <button
            className="button"
            type="button"
            onClick={refresh}
            disabled={dashboard.isFetching || todos.isFetching}
          >
            <ArrowClockwise size={16} aria-hidden />
            {t("refresh")}
          </button>
          {updated && (
            <small>{text(`${updated} 更新`, `Updated ${updated}`)}</small>
          )}
        </div>
      </header>
      <section className="workspace-overview" aria-labelledby="metrics-title">
        <div className="workspace-section-label">
          <h3 id="metrics-title">{t("tenantOperations")}</h3>
          <span>
            {text("统计范围：整个工作空间", "Scope: entire workspace")}
          </span>
        </div>
        {dashboard.isError ? (
          <div className="inline-error" role="alert">
            <span>{t("dashboardUnavailable")}</span>
            <button type="button" onClick={() => void dashboard.refetch()}>
              {t("retry")}
            </button>
          </div>
        ) : (
          <div className="workspace-metrics" aria-busy={dashboard.isPending}>
            {metrics.map((metric) => {
              const value = dashboard.data?.counts[metric.key];
              const href = "href" in metric ? metric.href : undefined;
              const content = (
                <>
                  <div className="metric-label">
                    <span>{metric.label}</span>
                    <metric.icon size={19} aria-hidden />
                  </div>
                  <strong data-testid={`metric-${metric.key}`}>
                    {value === undefined ? "—" : value.toLocaleString(language)}
                  </strong>
                  <div className="metric-caption">
                    <small>{metric.note}</small>
                    {href && <ArrowRight size={16} aria-hidden />}
                  </div>
                </>
              );
              return (
                <article
                  key={metric.key}
                  className={`workspace-metric ${"warning" in metric && value ? "needs-attention" : ""}`}
                >
                  {href ? (
                    <Link to={href}>{content}</Link>
                  ) : (
                    <div>{content}</div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>
      <div className="workspace-grid">
        <section
          className="workspace-card workspace-todos"
          aria-labelledby="work-queue-title"
        >
          <header className="workspace-card-heading">
            <div>
              <h3 id="work-queue-title">
                {canSeeAll
                  ? text("最近未完成待办", "Recent open to-dos")
                  : text("我的未完成待办", "My open to-dos")}
              </h3>
              <p>
                {text(
                  "需要人来推进的下一步。",
                  "The next steps that need a human touch.",
                )}
              </p>
            </div>
            <Link className="workspace-text-link" to="/todos?status=open">
              {text("查看全部", "View all")}
              <ArrowRight size={15} aria-hidden />
            </Link>
          </header>
          {!canReadTodos ? (
            <div className="workspace-empty">
              <CheckCircle size={30} />
              <strong>
                {text(
                  "关联员工档案后查看个人待办",
                  "Link an employee profile to see your to-dos",
                )}
              </strong>
              <p>
                {text(
                  "请联系工作空间管理员完成关联。",
                  "Ask a workspace administrator to link your profile.",
                )}
              </p>
            </div>
          ) : (
            <ListState
              loading={todos.isPending}
              error={todos.isError ? apiErrorMessage(todos.error) : null}
              empty={todos.data?.data.length === 0}
              emptyTitle={text("当前没有未完成待办", "No open to-dos")}
              emptyDescription={text(
                "有新的工作项时，会在这里显示。",
                "New work items will appear here.",
              )}
              onRetry={() => void todos.refetch()}
            >
              <ul className="workspace-todo-list">
                {todos.data?.data.map((todo) => {
                  const due = todo.due_at ? new Date(todo.due_at) : null;
                  const validDate = due && !Number.isNaN(due.getTime());
                  const overdue = validDate && due.getTime() < Date.now();
                  return (
                    <li key={todo.id}>
                      <Link
                        to={`/todos?status=open&keyword=${encodeURIComponent(todo.title)}`}
                      >
                        <span
                          className={`todo-indicator ${overdue ? "overdue" : ""}`}
                          aria-hidden
                        >
                          <CheckCircle size={20} />
                        </span>
                        <div className="workspace-todo-copy">
                          <strong>{todo.title}</strong>
                          <span>
                            {entityLabels[todo.entity_type]}
                            {todo.description && ` · ${todo.description}`}
                          </span>
                        </div>
                        <div
                          className={`workspace-todo-date ${overdue ? "overdue" : ""}`}
                        >
                          {validDate ? (
                            <>
                              <span>
                                {new Intl.DateTimeFormat(language, {
                                  month: "short",
                                  day: "numeric",
                                }).format(due)}
                              </span>
                              <small>
                                {overdue
                                  ? text("已逾期", "Overdue")
                                  : text("截止", "Due")}
                              </small>
                            </>
                          ) : (
                            <span>{text("未设期限", "No due date")}</span>
                          )}
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </ListState>
          )}
          <footer className="workspace-card-footer">
            <span>
              {text(
                "保留处理记录，每一步都有据可查。",
                "Completion history stays with every work item.",
              )}
            </span>
            <Link to="/approvals">
              {text("审批记录", "Approval log")}
              <ArrowRight size={14} aria-hidden />
            </Link>
          </footer>
        </section>
        {shortcuts.length > 0 && (
          <section
            className="workspace-card workspace-shortcuts"
            aria-labelledby="data-shortcuts-title"
          >
            <header className="workspace-card-heading">
              <div>
                <h3 id="data-shortcuts-title">
                  {text("常用数据", "Everyday data")}
                </h3>
                <p>
                  {text(
                    "快速查阅，也能随时补充。",
                    "Find a record or add a new one.",
                  )}
                </p>
              </div>
            </header>
            <div className="workspace-data-links">
              {shortcuts.map((item) => (
                <div key={item.href}>
                  <Link to={item.href}>
                    <item.icon size={21} aria-hidden />
                    <span>
                      <strong>{t(item.label)}</strong>
                      <small>{text(...item.description)}</small>
                    </span>
                  </Link>
                  <Link
                    className="workspace-add"
                    to={`${item.href}?create=1`}
                    aria-label={text(...item.createLabel!)}
                    title={text(...item.createLabel!)}
                  >
                    <Plus size={18} />
                  </Link>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
      {canReadObjects && (
        <section className="workspace-records" aria-labelledby="records-title">
          <div>
            <h3 id="records-title">{text("业务单据", "Business records")}</h3>
            <p>
              {text(
                "从业务类型进入，查看记录与详情。",
                "Browse records by business type.",
              )}
            </p>
          </div>
          <div>
            {(
              [
                ["sales_quotation", text("销售报价", "Sales quotations")],
                ["purchase_request", text("采购申请", "Purchase requests")],
                ["expense_claim", text("费用报销", "Expense claims")],
              ] as const
            ).map(([type, label]) => (
              <Link key={type} to={`/objects?kind=builtin&object_type=${type}`}>
                {label}
                <ArrowRight size={15} aria-hidden />
              </Link>
            ))}
          </div>
        </section>
      )}
      <section
        className="workspace-agent"
        aria-labelledby="connect-agent-title"
      >
        <Robot size={25} aria-hidden />
        <div>
          <h3 id="connect-agent-title">{t("connectAgentTitle")}</h3>
          <p>
            {text(
              "让智能体处理流程，在 Console 中掌握数据与结果。",
              "Let agents handle workflows. Keep data and outcomes in view here.",
            )}
          </p>
        </div>
        <div className="workspace-agent-actions">
          <a href="/web/connect">{t("connectAgentGuide")}</a>
          <a className="button" href="/api/v1/connect-skill" download>
            {t("downloadConnectorSkill")}
          </a>
        </div>
      </section>
    </div>
  );
}
