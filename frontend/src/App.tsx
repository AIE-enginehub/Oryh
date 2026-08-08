import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, Outlet, Route, Routes, useLocation, useOutletContext } from "react-router-dom";
import "@fontsource-variable/manrope";

import { ApiError, getBootstrap, type BootstrapData } from "./api/client";
import { LanguageProvider, useI18n } from "./i18n";
import { OryhLogo } from "./components/OryhLogo";
import {
  AppShell,
  canManageAccess,
  canManageEmployees,
  canManageMasterData,
  canManageObjectConfiguration,
  canManageTenantConfiguration,
  hasCapability,
} from "./components/AppShell";
import { ApiKeysPage } from "./pages/ApiKeysPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { CustomersPage } from "./pages/CustomersPage";
import { DashboardPage } from "./pages/DashboardPage";
import { EmployeesPage } from "./pages/EmployeesPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ObjectDetailPage } from "./pages/ObjectDetailPage";
import { ObjectTypesPage } from "./pages/ObjectTypesPage";
import { ObjectsPage } from "./pages/ObjectsPage";
import { ProductsPage } from "./pages/ProductsPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ResourcesPage } from "./pages/ResourcesPage";
import { RolesPage } from "./pages/RolesPage";
import { FlowAgentPage } from "./pages/FlowAgentPage";
import { SkillsPage } from "./pages/SkillsPage";
import { TodosPage } from "./pages/TodosPage";
import { UsersPage } from "./pages/UsersPage";
import { VendorsPage } from "./pages/VendorsPage";

export type ConsoleContext = {
  bootstrap: BootstrapData;
};

function LoadingScreen() {
  const { t } = useI18n();
  return (
    <main className="center-screen" aria-busy="true" aria-label={t("loadingConsole")}>
      <div className="loading-mark" aria-hidden="true"><OryhLogo /></div>
      <p>{t("loadingConsole")}</p>
    </main>
  );
}

function SessionBoundary() {
  const { t } = useI18n();
  const location = useLocation();
  const session = useQuery({
    queryKey: ["console", "bootstrap"],
    queryFn: getBootstrap,
    retry: (failureCount, error) =>
      !(error instanceof ApiError && (error.status === 401 || error.status === 403)) &&
      failureCount < 1,
  });

  if (session.isPending) {
    return <LoadingScreen />;
  }

  if (session.error instanceof ApiError && session.error.status === 401) {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  }

  if (session.isError || !session.data) {
    return (
      <main className="center-screen">
        <section className="state-card" role="alert">
          <span className="eyebrow">{t("connectionFailed")}</span>
          <h1>{t("consoleUnavailable")}</h1>
          <p>{session.error instanceof Error ? session.error.message : t("retryLater")}</p>
          <button className="button primary" onClick={() => void session.refetch()}>
            {t("reload")}
          </button>
        </section>
      </main>
    );
  }

  return (
    <AppShell bootstrap={session.data}>
      <Outlet context={{ bootstrap: session.data } satisfies ConsoleContext} />
    </AppShell>
  );
}

function MasterDataBoundary() {
  const { t, text } = useI18n();
  const context = useOutletContext<ConsoleContext>();
  if (!canManageMasterData(context.bootstrap)) {
    return (
      <section className="panel access-denied" role="alert">
        <span className="eyebrow">{t("insufficientPermission")}</span>
        <h2>{t("accessMasterData")}</h2>
        <p>{text("你的角色没有主数据管理权限。若你认为这是配置错误，请联系工作空间管理员。", "Your role does not include master-data access. Contact your workspace administrator if this looks incorrect.")}</p>
        <Link className="button" to="/dashboard">{t("returnDashboard")}</Link>
      </section>
    );
  }
  return <Outlet context={context} />;
}

function EmployeesBoundary() {
  const { t, text } = useI18n();
  const context = useOutletContext<ConsoleContext>();
  if (!canManageEmployees(context.bootstrap)) {
    return (
      <section className="panel access-denied" role="alert">
        <span className="eyebrow">{t("insufficientPermission")}</span>
        <h2>{t("accessEmployees")}</h2>
        <p>{text("你的角色没有员工管理权限。若你认为这是配置错误，请联系工作空间管理员。", "Your role does not include employee-management access. Contact your workspace administrator if this looks incorrect.")}</p>
        <Link className="button" to="/dashboard">{t("returnDashboard")}</Link>
      </section>
    );
  }
  return <Outlet context={context} />;
}

function AccessBoundary() {
  const { t, text } = useI18n();
  const context = useOutletContext<ConsoleContext>();
  if (!canManageAccess(context.bootstrap)) {
    return (
      <section className="panel access-denied" role="alert">
        <span className="eyebrow">{t("insufficientPermission")}</span>
        <h2>{t("accessPeopleAndAccess")}</h2>
        <p>{text("你的角色没有人员与权限管理资格。若你认为这是配置错误，请联系工作空间管理员。", "Your role does not include people-and-access management. Contact your workspace administrator if this looks incorrect.")}</p>
        <Link className="button" to="/dashboard">{t("returnDashboard")}</Link>
      </section>
    );
  }
  return <Outlet context={context} />;
}

function TenantConfigurationBoundary() {
  const { t, text } = useI18n();
  const context = useOutletContext<ConsoleContext>();
  if (!canManageTenantConfiguration(context.bootstrap)) {
    return (
      <section className="panel access-denied" role="alert">
        <span className="eyebrow">{t("insufficientPermission")}</span>
        <h2>{t("accessTenantConfiguration")}</h2>
        <p>{text("业务类型、流程和整个工作空间的记录仅向管理员开放。", "Business types, workflows, and workspace-wide records are available only to administrators.")}</p>
        <Link className="button" to="/dashboard">{t("returnDashboard")}</Link>
      </section>
    );
  }
  return <Outlet context={context} />;
}

function ObjectConfigurationBoundary() {
  const { t, text } = useI18n();
  const context = useOutletContext<ConsoleContext>();
  if (!canManageObjectConfiguration(context.bootstrap)) {
    return (
      <section className="panel access-denied" role="alert">
        <span className="eyebrow">{t("insufficientPermission")}</span>
        <h2>{t("accessObjectConfiguration")}</h2>
        <p>{text("你的角色没有业务类型或流程设置权限。请联系工作空间管理员。", "Your role does not include business-type or workflow settings. Contact your workspace administrator.")}</p>
        <Link className="button" to="/dashboard">{t("returnDashboard")}</Link>
      </section>
    );
  }
  return <Outlet context={context} />;
}

function CapabilityBoundary({ capability, title }: { capability: string; title: string }) {
  const { t, text } = useI18n();
  const context = useOutletContext<ConsoleContext>();
  if (!hasCapability(context.bootstrap, capability)) {
    return (
      <section className="panel access-denied" role="alert">
        <span className="eyebrow">{t("insufficientPermission")}</span>
        <h2>{t("accessPrefix")}{title}</h2>
        <p>{text("你的角色没有此项管理权限。若你认为这是配置错误，请联系工作空间管理员。", "Your role does not include this management permission. Contact your workspace administrator if this looks incorrect.")}</p>
        <Link className="button" to="/dashboard">{t("returnDashboard")}</Link>
      </section>
    );
  }
  return <Outlet context={context} />;
}

export function App() {
  return (
    <LanguageProvider>
      <ConsoleRoutes />
    </LanguageProvider>
  );
}

function ConsoleRoutes() {
  const { text } = useI18n();
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<SessionBoundary />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route element={<AccessBoundary />}>
          <Route path="/users" element={<UsersPage />} />
          <Route path="/roles" element={<RolesPage />} />
        </Route>
        <Route element={<EmployeesBoundary />}>
          <Route path="/employees" element={<EmployeesPage />} />
        </Route>
        <Route element={<MasterDataBoundary />}>
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/vendors" element={<VendorsPage />} />
          <Route path="/customers" element={<CustomersPage />} />
          <Route path="/products" element={<ProductsPage />} />
          <Route path="/resources" element={<ResourcesPage />} />
        </Route>
        <Route element={<ObjectConfigurationBoundary />}>
          <Route path="/object-types" element={<ObjectTypesPage />} />
        </Route>
        <Route element={<TenantConfigurationBoundary />}>
          <Route path="/objects" element={<ObjectsPage />} />
          <Route path="/objects/:entityType/:recordId" element={<ObjectDetailPage />} />
        </Route>
        <Route path="/todos" element={<TodosPage />} />
        <Route path="/approvals" element={<ApprovalsPage />} />
        <Route element={<CapabilityBoundary capability="skills.manage" title={text("技能管理", "skill management")} />}>
          <Route path="/skills" element={<SkillsPage />} />
        </Route>
        <Route element={<CapabilityBoundary capability="keys.manage" title={text("访问凭证管理", "access credential management")} />}>
          <Route path="/api-keys" element={<ApiKeysPage />} />
          {/* Same gate as the credential it turns on and off: whoever may manage
              keys may decide whether ORYH's agent runs here. */}
          <Route path="/flow-agent" element={<FlowAgentPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
