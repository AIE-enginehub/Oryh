import { useQuery } from "@tanstack/react-query";
import { Link, useOutletContext } from "react-router-dom";

import { ApiError, getDashboard } from "../api/client";
import type { ConsoleContext } from "../App";
import { useI18n } from "../i18n";
import {
  canManageAccess,
  canManageEmployees,
  canManageMasterData,
  canManageObjectConfiguration,
  canManageTenantConfiguration,
  hasCapability,
} from "../components/AppShell";

const metricDefinitions = [
  { key: "users", label: "activeUsers", note: "currentTenant" },
  { key: "todos_open", label: "openTodos", note: "awaitingAction" },
  { key: "todos_overdue", label: "overdueTodos", note: "needsAttention", alert: true },
  { key: "objects", label: "objects", note: "undeletedRecords" },
  { key: "skills", label: "activeSkills", note: "distributable" },
] as const;

export function DashboardPage() {
  const { t, text } = useI18n();
  const { bootstrap } = useOutletContext<ConsoleContext>();
  const canManageMaster = canManageMasterData(bootstrap);
  const canManageEmployeeRecords = canManageEmployees(bootstrap);
  const canManageIdentity = canManageAccess(bootstrap);
  const canManageConfiguration = canManageTenantConfiguration(bootstrap);
  const canManageObjectConfig = canManageObjectConfiguration(bootstrap);
  const canManageSkills = hasCapability(bootstrap, "skills.manage");
  const canManageKeys = hasCapability(bootstrap, "keys.manage");
  const dashboard = useQuery({
    queryKey: ["console", "dashboard"],
    queryFn: getDashboard,
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status < 500) && failureCount < 1,
  });

  return (
    <div className="dashboard-stack">
      <section className="welcome-row">
        <div>
          <span className="eyebrow">{bootstrap.tenant.email_domain || t("tenantConsole")}</span>
          <h2>{bootstrap.user.name ? `${t("welcomeBack")}, ${bootstrap.user.name}` : t("welcomeBack")}</h2>
          <p>{t("dashboardDescription")}</p>
        </div>
        <div className="role-card">
          <span>{t("currentRole")}</span>
          <strong>{bootstrap.role}</strong>
          <small>{bootstrap.permissions.length} {t("capabilityGrants")}</small>
        </div>
      </section>

      <section className="panel connect-panel" aria-labelledby="connect-agent-title">
        <div>
          <span className="eyebrow">{t("connectAgent")}</span>
          <h2 id="connect-agent-title">{t("connectAgentTitle")}</h2>
          <p>{t("connectAgentDescription")}</p>
        </div>
        <div className="connect-actions">
          <a className="button primary" href="/api/v1/connect-skill" download>
            {t("downloadConnectorSkill")} <span aria-hidden="true">↓</span>
          </a>
          <a className="connect-guide" href="/web/connect">{t("connectAgentGuide")}</a>
        </div>
      </section>

      <section aria-labelledby="metrics-title">
        <div className="section-heading">
          <div><span className="eyebrow">{text("最新概况", "Latest overview")}</span><h2 id="metrics-title">{t("tenantOperations")}</h2></div>
          <button className="button subtle" type="button" onClick={() => void dashboard.refetch()}>
            {t("refresh")}
          </button>
        </div>

        {dashboard.isError ? (
          <div className="inline-error" role="alert">
            <span>{t("dashboardUnavailable")}</span>
            <button type="button" onClick={() => void dashboard.refetch()}>{t("retry")}</button>
          </div>
        ) : (
          <div className="metric-grid" aria-busy={dashboard.isPending}>
            {metricDefinitions.map((metric) => (
              <article
                className={`metric-card ${"alert" in metric && metric.alert ? "alert" : ""}`}
                key={metric.key}
              >
                <span>{t(metric.label)}</span>
                <strong data-testid={`metric-${metric.key}`}>
                  {dashboard.data ? dashboard.data.counts[metric.key].toLocaleString() : "—"}
                </strong>
                <small>{t(metric.note)}</small>
              </article>
            ))}
          </div>
        )}
      </section>

      <div className="dashboard-columns">
        <section className="panel migration-panel">
          <div className="section-heading compact">
            <div><span className="eyebrow">{text("工作区状态", "Workspace status")}</span><h2>{t("consoleMigration")}</h2></div>
            <span className="phase-badge">{t("complete")}</span>
          </div>
          <div className="migration-list">
            <div><span className="step-state done">{text("已上线", "Live")}</span><strong>{text("人员与权限", "People & access")}</strong><p>{text("用户、角色、权限与员工档案可以统一管理。", "Users, roles, permissions, and employee profiles are managed in one place.")}</p></div>
            <div><span className="step-state done">{text("已上线", "Live")}</span><strong>{text("主数据", "Master data")}</strong><p>{text("项目、供应商、产品、SKU 与资源支持筛选和分页。", "Projects, vendors, products, SKUs, and resources support filtering and pagination.")}</p></div>
            <div><span className="step-state done">{text("已上线", "Live")}</span><strong>{text("对象与规则", "Objects & rules")}</strong><p>{text("业务对象详情、字段规则、状态流程与工作流版本可以统一管理。", "Business-object details, field rules, status flows, and workflow versions are managed together.")}</p></div>
            <div><span className="step-state done">{text("已上线", "Live")}</span><strong>{text("活动记录", "Activity records")}</strong><p>{text("个人待办完成和不可变审批审计在统一工作区处理。", "Personal to-do completion and immutable approval audit are handled in one workspace.")}</p></div>
            <div><span className="step-state done">{text("已上线", "Live")}</span><strong>{text("自动化", "Automation")}</strong><p>{text("Skill 文件包、权限分发与访问凭证可以统一管理。", "Skill bundles, permission distribution, and access credentials are managed together.")}</p></div>
          </div>
        </section>

        <section className="panel shortcuts-panel">
          <span className="eyebrow">{t("quickAccess")}</span>
          <h2>{t("continueManaging")}</h2>
          <p>{t("quickAccessDescription")}</p>
          <div className="shortcut-list">
            {canManageMaster && <Link to="/projects"><span>{text("项目主数据", "Project master data")}</span><b>{text("打开 →", "Open →")}</b></Link>}
            {canManageMaster && <Link to="/vendors"><span>{text("供应商主数据", "Vendor master data")}</span><b>{text("打开 →", "Open →")}</b></Link>}
            {canManageMaster && <Link to="/products"><span>{text("产品与 SKU", "Products & SKUs")}</span><b>{text("打开 →", "Open →")}</b></Link>}
            {canManageMaster && <Link to="/resources"><span>{text("资源主数据", "Resource master data")}</span><b>{text("打开 →", "Open →")}</b></Link>}
            {canManageEmployeeRecords && <Link to="/employees"><span>{text("员工档案", "Employee profiles")}</span><b>{text("打开 →", "Open →")}</b></Link>}
            {canManageIdentity && <Link to="/users"><span>{text("用户与邀请", "Users & invitations")}</span><b>{text("打开 →", "Open →")}</b></Link>}
            {canManageIdentity && <Link to="/roles"><span>{text("角色与权限", "Roles & permissions")}</span><b>{text("打开 →", "Open →")}</b></Link>}
            {canManageObjectConfig && <Link to="/object-types"><span>{text("对象类型与流程", "Object types & workflows")}</span><b>{text("打开 →", "Open →")}</b></Link>}
            {canManageConfiguration && <Link to="/objects"><span>{text("业务对象", "Business objects")}</span><b>{text("打开 →", "Open →")}</b></Link>}
            <Link to="/todos"><span>{text("待办", "To-dos")}</span><b>{text("打开 →", "Open →")}</b></Link>
            <Link to="/approvals"><span>{text("审批记录", "Approval log")}</span><b>{text("打开 →", "Open →")}</b></Link>
            {canManageSkills && <Link to="/skills"><span>{text("技能", "Skills")}</span><b>{text("打开 →", "Open →")}</b></Link>}
            {canManageKeys && <Link to="/api-keys"><span>{t("apiKeys")}</span><b>{text("打开 →", "Open →")}</b></Link>}
          </div>
        </section>
      </div>
    </div>
  );
}
