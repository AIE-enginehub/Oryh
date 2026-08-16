import { useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { browserLogout, type BootstrapData } from "../api/client";
import { LanguageSwitcher, type MessageKey, useI18n } from "../i18n";
import { OryhLogo } from "./OryhLogo";
import { useNarrowViewport } from "./useNarrowViewport";

type AppShellProps = {
  bootstrap: BootstrapData;
  children: ReactNode;
};

type NavItem = {
  label: MessageKey;
  href: string;
  capability?: string;
  adminOnly?: boolean;
  masterData?: boolean;
  objectConfiguration?: boolean;
};

const navigation: Array<{ label: MessageKey; items: NavItem[] }> = [
  {
    label: "overview",
    items: [{ label: "dashboard", href: "/dashboard" }],
  },
  {
    label: "peopleAndAccess",
    items: [
      { label: "users", href: "/users", capability: "users.manage" },
      { label: "rolesAndPermissions", href: "/roles", capability: "users.manage" },
      { label: "employees", href: "/employees", capability: "employees.manage" },
    ],
  },
  {
    label: "masterData",
    items: [
      { label: "projects", href: "/projects", masterData: true },
      { label: "vendors", href: "/vendors", masterData: true },
      { label: "customers", href: "/customers", masterData: true },
      { label: "products", href: "/products", masterData: true },
      { label: "resources", href: "/resources", masterData: true },
      { label: "objectTypes", href: "/object-types", objectConfiguration: true },
    ],
  },
  {
    label: "recordsAndActivity",
    items: [
      { label: "businessObjects", href: "/objects", adminOnly: true },
      { label: "todos", href: "/todos" },
      { label: "approvals", href: "/approvals" },
    ],
  },
  {
    label: "automation",
    items: [
      { label: "skills", href: "/skills", capability: "skills.manage" },
      { label: "apiKeys", href: "/api-keys", capability: "keys.manage" },
      { label: "flowAgent", href: "/flow-agent", capability: "keys.manage" },
    ],
  },
];

function permissionCovers(permissions: string[], capability: string): boolean {
  return permissions.includes(capability) || permissions.includes(`${capability}:*`);
}

export function hasCapability(bootstrap: BootstrapData, capability: string): boolean {
  return permissionCovers(bootstrap.permissions, capability);
}

export function canManageTenantConfiguration(bootstrap: BootstrapData): boolean {
  return bootstrap.role === "admin" || permissionCovers(bootstrap.permissions, "users.manage");
}

export function canManageObjectConfiguration(bootstrap: BootstrapData): boolean {
  return canManageTenantConfiguration(bootstrap) ||
    hasCapability(bootstrap, "object_types.manage") ||
    hasCapability(bootstrap, "workflows.publish");
}

export function canManageMasterData(bootstrap: BootstrapData): boolean {
  return bootstrap.role === "admin" ||
    permissionCovers(bootstrap.permissions, "master_data.manage") ||
    permissionCovers(bootstrap.permissions, "users.manage");
}

export function canManageEmployees(bootstrap: BootstrapData): boolean {
  return permissionCovers(bootstrap.permissions, "employees.manage");
}

export function canManageAccess(bootstrap: BootstrapData): boolean {
  return permissionCovers(bootstrap.permissions, "users.manage");
}

const routeTitles: Record<string, { section: MessageKey; title: MessageKey }> = {
  "/dashboard": { section: "tenantConsole", title: "dashboard" },
  "/users": { section: "peopleAndAccess", title: "users" },
  "/roles": { section: "peopleAndAccess", title: "rolesAndPermissions" },
  "/employees": { section: "peopleAndAccess", title: "employees" },
  "/projects": { section: "masterData", title: "projects" },
  "/vendors": { section: "masterData", title: "vendors" },
  "/customers": { section: "masterData", title: "customers" },
  "/products": { section: "masterData", title: "products" },
  "/resources": { section: "masterData", title: "resources" },
  "/object-types": { section: "masterData", title: "objectTypes" },
  "/objects": { section: "recordsAndActivity", title: "businessObjects" },
  "/todos": { section: "recordsAndActivity", title: "todos" },
  "/approvals": { section: "recordsAndActivity", title: "approvals" },
  "/skills": { section: "automation", title: "skills" },
  "/api-keys": { section: "automation", title: "apiKeys" },
  "/flow-agent": { section: "automation", title: "flowAgent" },
};
const notFoundTitle = { section: "tenantConsole" as const, title: "pageNotFound" as const };
const objectDetailPath = /^\/objects\/[^/]+\/[^/]+\/?$/;

export function AppShell({ bootstrap, children }: AppShellProps) {
  const { t } = useI18n();
  const [menuOpen, setMenuOpen] = useState(false);
  // Below 820px the sidebar is moved off-screen with `translateX(-102%)`, which
  // hides it from sight and from nothing else: every nav link stayed in the tab
  // order and in the accessibility tree, so a keyboard user tabbing across a
  // "closed" mobile page walked through the whole navigation first, and a
  // screen reader read it out. `inert` is what CSS transform cannot say.
  const narrow = useNarrowViewport();
  const navHidden = narrow && !menuOpen;
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const isAdmin = canManageTenantConfiguration(bootstrap);
  const displayName = bootstrap.user.name || bootstrap.user.email;
  const pageTitle = routeTitles[location.pathname] ??
    (objectDetailPath.test(location.pathname) ? routeTitles["/objects"] : notFoundTitle);

  const logout = useMutation({
    mutationFn: browserLogout,
    onSuccess: () => {
      queryClient.clear();
      navigate("/login", { replace: true });
    },
  });

  const visible = (item: NavItem) =>
    (!item.adminOnly || isAdmin) &&
    (!item.masterData || canManageMasterData(bootstrap)) &&
    (!item.objectConfiguration || canManageObjectConfiguration(bootstrap)) &&
    (!item.capability || hasCapability(bootstrap, item.capability));

  return (
    <div className="console-layout">
      {menuOpen && (
        <button
          className="nav-scrim"
          aria-label={t("closeNavigation")}
          onClick={() => setMenuOpen(false)}
        />
      )}
      <aside className={`sidebar ${menuOpen ? "open" : ""}`} inert={navHidden || undefined}>
        <div className="brand-block">
          <OryhLogo subtitle={bootstrap.tenant.name} />
        </div>

        <nav className="sidebar-nav" aria-label={t("navigation")}>
          {navigation.map((group) => {
            const items = group.items.filter(visible);
            if (items.length === 0) return null;
            return (
              <div className="nav-group" key={group.label}>
                <div className="nav-group-label">{t(group.label)}</div>
                {items.map((item) => (
                  <NavLink
                    key={item.href}
                    to={item.href}
                    onClick={() => setMenuOpen(false)}
                    className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
                  >
                    <span>{t(item.label)}</span>
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="identity-block">
          <span className="avatar" aria-hidden="true">{displayName.slice(0, 1).toUpperCase()}</span>
          <span className="identity-copy">
            <strong>{displayName}</strong>
            <small>{bootstrap.role}</small>
          </span>
          <button
            className="icon-button"
            type="button"
            aria-label={t("signOut")}
            title={t("signOut")}
            disabled={logout.isPending}
            onClick={() => logout.mutate()}
          >
            {t("signOut")}
          </button>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <button
            className="menu-button"
            type="button"
            aria-label={t("openNavigation")}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen(true)}
          >
            {t("menu")}
          </button>
          <div>
            <span className="eyebrow">{t(pageTitle.section)}</span>
            <h1>{t(pageTitle.title)}</h1>
          </div>
          <div className="topbar-meta">
            <span className="status-dot" aria-hidden="true" />
            {t("sessionRls")}
          </div>
          <LanguageSwitcher />
        </header>
        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}
