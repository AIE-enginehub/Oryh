import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowSquareOut,
  CaretRight,
  List,
  MagnifyingGlass,
  Plus,
  SignOut,
  X,
} from "@phosphor-icons/react";

import { browserLogout, type BootstrapData } from "../api/client";
import { LanguageSwitcher, useI18n } from "../i18n";
import { navigation, visibleNavigation } from "../navigation";
import { CommandMenu } from "./CommandMenu";
import { OryhLogo } from "./OryhLogo";
import { useNarrowViewport } from "./useNarrowViewport";
import { useFocusTrap } from "./useFocusTrap";

// Keep existing page imports stable while sharing access policy outside the shell.
export {
  hasCapability,
  canManageTenantConfiguration,
  canManageObjectConfiguration,
  canManageMasterData,
  canManageEmployees,
  canManageAccess,
} from "../access";

type AppShellProps = { bootstrap: BootstrapData; children: ReactNode };

export function AppShell({ bootstrap, children }: AppShellProps) {
  const { t, text } = useI18n();
  const [menuOpen, setMenuOpen] = useState(false);
  const [command, setCommand] = useState<"navigate" | "create" | null>(null);
  const sidebar = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const narrow = useNarrowViewport();
  const navHidden = narrow && !menuOpen;
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const groups = visibleNavigation(bootstrap);
  const canCreate = groups.some((group) =>
    group.items.some((item) => item.createLabel),
  );
  const displayName = bootstrap.user.name || bootstrap.user.email;
  const currentGroup = navigation.find((group) =>
    group.items.some(
      (item) =>
        item.href === location.pathname ||
        (item.href === "/objects" &&
          /^\/objects\/[^/]+\/[^/]+\/?$/.test(location.pathname)),
    ),
  );
  const currentPage = currentGroup?.items.find(
    (item) =>
      item.href === location.pathname ||
      (item.href === "/objects" && location.pathname.startsWith("/objects/")),
  );
  const roleLabel =
    bootstrap.role === "admin"
      ? text("租户管理员", "Tenant administrator")
      : bootstrap.role === "member"
        ? text("团队成员", "Team member")
        : bootstrap.role;

  useFocusTrap(sidebar, narrow && menuOpen);
  useEffect(() => {
    setMenuOpen(false);
    setCommand(null);
  }, [location.pathname, location.search]);
  useEffect(() => {
    if (!menuOpen || !narrow) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    sidebar.current
      ?.querySelector<HTMLElement>(".nav-link.active, .nav-link")
      ?.focus();
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    };
    document.addEventListener("keydown", close);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", close);
    };
  }, [menuOpen, narrow]);
  useEffect(() => {
    const openFinder = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "k")
        return;
      if (
        !command &&
        event.target instanceof Element &&
        event.target.closest('[role="dialog"], [role="alertdialog"]')
      )
        return;
      event.preventDefault();
      setMenuOpen(false);
      setCommand((value) => (value ? null : "navigate"));
    };
    document.addEventListener("keydown", openFinder);
    return () => document.removeEventListener("keydown", openFinder);
  }, [command]);

  const logout = useMutation({
    mutationFn: browserLogout,
    onSuccess: () => {
      queryClient.clear();
      navigate("/login", { replace: true });
    },
  });

  return (
    <div className="console-layout">
      <a className="console-skip-link" href="#console-content">
        {text("跳到主要内容", "Skip to main content")}
      </a>
      {menuOpen && (
        <button
          className="nav-scrim"
          aria-label={text("关闭导航遮罩", "Close navigation backdrop")}
          onClick={() => setMenuOpen(false)}
        />
      )}
      <aside
        ref={sidebar}
        className={`sidebar ${menuOpen ? "open" : ""}`}
        inert={navHidden || undefined}
        id="console-sidebar"
        role={narrow && menuOpen ? "dialog" : undefined}
        aria-modal={(narrow && menuOpen) || undefined}
        aria-label={narrow && menuOpen ? t("navigation") : undefined}
      >
        <div className="brand-block">
          <NavLink
            to="/dashboard"
            aria-label={text("ORYH 工作台", "ORYH workspace")}
            onClick={() => setMenuOpen(false)}
          >
            <OryhLogo />
          </NavLink>
          <span className="console-brand-label">CONSOLE</span>
          <button
            className="sidebar-close icon-button"
            type="button"
            onClick={() => {
              setMenuOpen(false);
              menuButton.current?.focus();
            }}
            aria-label={t("closeNavigation")}
          >
            <X size={20} />
          </button>
        </div>
        <div className="workspace-identity">
          <span aria-hidden="true">{bootstrap.tenant.name.slice(0, 1)}</span>
          <div>
            <strong title={bootstrap.tenant.name}>
              {bootstrap.tenant.name}
            </strong>
            <small>{text("企业工作空间", "Company workspace")}</small>
          </div>
        </div>
        <nav className="sidebar-nav" aria-label={t("navigation")}>
          {groups.map((group) => (
            <div className="nav-group" key={group.label[1]}>
              <div className="nav-group-label">{text(...group.label)}</div>
              {group.items.map((item) => (
                <NavLink
                  key={item.href}
                  to={item.href}
                  onClick={() => setMenuOpen(false)}
                  className={({ isActive }) =>
                    `nav-link ${isActive ? "active" : ""}`
                  }
                >
                  <item.icon size={19} weight="regular" aria-hidden />
                  <span>{t(item.label)}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <a className="sidebar-help" href="/web/connect">
          {text("使用指南与智能体接入", "Guide & agent connection")}
          <ArrowSquareOut size={15} aria-hidden />
        </a>
        {logout.isError && (
          <p className="signout-error" role="alert">
            {text("退出失败，请重试。", "Could not sign out. Please retry.")}
          </p>
        )}
        <div className="identity-block">
          <span className="avatar" aria-hidden>
            {displayName.slice(0, 1).toUpperCase()}
          </span>
          <span className="identity-copy">
            <strong title={bootstrap.user.email}>{displayName}</strong>
            <small>{roleLabel}</small>
          </span>
          <button
            className="icon-button"
            type="button"
            aria-label={t("signOut")}
            title={t("signOut")}
            disabled={logout.isPending}
            onClick={() => logout.mutate()}
          >
            <SignOut size={19} />
          </button>
        </div>
      </aside>

      <div className="main-panel">
        <header className="topbar">
          <button
            ref={menuButton}
            className="menu-button"
            type="button"
            aria-label={t("openNavigation")}
            aria-expanded={menuOpen}
            aria-controls="console-sidebar"
            onClick={() => setMenuOpen(true)}
          >
            <List size={22} />
          </button>
          <div className="console-breadcrumb">
            <span>
              {currentGroup ? text(...currentGroup.label) : t("tenantConsole")}
            </span>
            <CaretRight size={13} aria-hidden />
            <h1>{currentPage ? t(currentPage.label) : t("pageNotFound")}</h1>
          </div>
          <div className="console-header-actions">
            <button
              className="console-find"
              type="button"
              onClick={() => setCommand("navigate")}
              aria-label={text("查找页面与功能", "Find pages and actions")}
            >
              <MagnifyingGlass size={17} aria-hidden />
              <span>{text("查找页面与功能", "Find pages and actions")}</span>
              <kbd>⌘ K</kbd>
            </button>
            {canCreate && (
              <button
                className="button primary console-create"
                type="button"
                aria-label={text("新建", "Create")}
                onClick={() => setCommand("create")}
              >
                <Plus size={17} aria-hidden />
                <span>{text("新建", "Create")}</span>
              </button>
            )}
            <LanguageSwitcher />
          </div>
        </header>
        {import.meta.env.MODE === "preview" && (
          <div className="console-preview-note">
            {text(
              "本地样例预览 · 操作仅影响内存中的样例数据",
              "Local sample preview · Changes only affect in-memory sample data",
            )}
          </div>
        )}
        <main className="page-content" id="console-content" tabIndex={-1}>
          {children}
        </main>
      </div>
      {command && (
        <CommandMenu
          groups={groups}
          mode={command}
          onClose={() => setCommand(null)}
        />
      )}
    </div>
  );
}
