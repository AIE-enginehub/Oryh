import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Language = "zh-CN" | "en";

const storageKey = "oryh.console.language";

const messages = {
  "zh-CN": {
    language: "语言",
    chinese: "中文",
    english: "English",
    loadingConsole: "正在载入管理控制台…",
    connectionFailed: "连接失败",
    consoleUnavailable: "暂时无法打开控制台",
    retryLater: "请稍后重试。",
    reload: "重新加载",
    insufficientPermission: "权限不足",
    accessMasterData: "无法访问主数据管理",
    accessEmployees: "无法访问员工管理",
    accessPeopleAndAccess: "无法访问身份与权限管理",
    accessTenantConfiguration: "无法访问工作空间设置",
    accessObjectConfiguration: "无法访问对象类型与流程",
    accessPrefix: "无法访问",
    returnDashboard: "返回总览",
    tenantConsole: "管理控制台",
    overview: "概览",
    dashboard: "总览",
    peopleAndAccess: "人员与权限",
    users: "用户",
    rolesAndPermissions: "角色与权限",
    employees: "员工",
    masterData: "主数据",
    projects: "项目",
    vendors: "供应商",
    customers: "客户",
    products: "产品",
    resources: "资源",
    objectTypes: "对象类型",
    recordsAndActivity: "记录与活动",
    businessObjects: "业务对象",
    todos: "待办",
    approvals: "审批记录",
    automation: "自动化",
    skills: "技能",
    apiKeys: "访问凭证",
    flowAgent: "流程代理",
    closeNavigation: "关闭导航",
    navigation: "管理控制台导航",
    signOut: "退出登录",
    openNavigation: "打开导航",
    menu: "菜单",
    sessionRls: "安全访问",
    companyDataSeparated: "企业数据隔离",
    roleBasedAccess: "按角色授权",
    protectedRecords: "记录全程保护",
    loginProductLabel: "Oryh 产品说明",
    trustedFactLayer: "可信的业务事实层",
    loginHero: "让代理推动流程，\n让系统守住边界。",
    loginBody: "组织、权限、状态、审批和审计都会经过系统核验，登录信息始终受到保护。",
    loginWorkspace: "登录工作空间",
    loginIntro: "使用企业账号进入管理控制台。",
    email: "企业邮箱",
    password: "密码",
    enterPassword: "输入密码",
    forgotPassword: "忘记密码？",
    resetPassword: "重置密码",
    resetPasswordIntro: "输入账号邮箱，我们会发送一个限时、一次性的重置链接。",
    sendResetLink: "发送重置链接",
    sendingResetLink: "正在发送…",
    resetEmailSent: "如果该邮箱对应可用账号，重置链接已发送。请检查收件箱。",
    backToSignIn: "返回登录",
    signingIn: "正在登录…",
    enterConsole: "进入控制台",
    downloadConnectorSkill: "下载 Agent 连接 Skill",
    returnWebsite: "返回网站首页",
    registerCompany: "注册新公司",
    securityNote: "登录信息仅用于安全访问当前工作空间。",
    versionLabel: "版本",
    invalidCredentials: "邮箱或密码不正确。",
    activeUsers: "活跃用户",
    currentTenant: "当前工作空间",
    openTodos: "开放待办",
    awaitingAction: "等待处理",
    overdueTodos: "逾期待办",
    needsAttention: "需要关注",
    objects: "业务对象",
    undeletedRecords: "未删除记录",
    activeSkills: "活跃技能",
    distributable: "可分发",
    welcomeBack: "欢迎回来",
    dashboardDescription: "这里展示当前工作空间的最新业务概况。",
    currentRole: "当前身份",
    capabilityGrants: "项访问权限",
    tenantOperations: "工作空间概况",
    refresh: "刷新",
    dashboardUnavailable: "概况暂时不可用。",
    retry: "重试",
    consoleMigration: "工作区已准备就绪",
    complete: "已完成",
    connectAgent: "连接 Agent",
    connectAgentTitle: "把你的 Agent 接入 Oryh",
    connectAgentDescription: "解压到本地 Agent 的技能目录，然后对它说「帮我连上 oryh」。这个包不含密钥或公司数据；连接后你的个人技能会按角色自动安装。",
    connectAgentGuide: "查看安装说明",
    quickAccess: "快捷入口",
    continueManaging: "继续管理工作空间",
    quickAccessDescription: "所有工作空间管理功能都可以从这里进入。",
    pageNotFound: "页面不存在",
    notFoundDescription: "没有找到此页面。请检查链接，或返回控制台总览继续操作。",
  },
  en: {
    language: "Language",
    chinese: "中文",
    english: "English",
    loadingConsole: "Loading workspace console…",
    connectionFailed: "Connection failed",
    consoleUnavailable: "The console is unavailable",
    retryLater: "Please try again shortly.",
    reload: "Reload",
    insufficientPermission: "Access denied",
    accessMasterData: "Cannot access master data",
    accessEmployees: "Cannot access employee management",
    accessPeopleAndAccess: "Cannot access people and access management",
    accessTenantConfiguration: "Cannot access workspace settings",
    accessObjectConfiguration: "Cannot access object types and workflows",
    accessPrefix: "Cannot access",
    returnDashboard: "Back to dashboard",
    tenantConsole: "Workspace console",
    overview: "Overview",
    dashboard: "Dashboard",
    peopleAndAccess: "People & access",
    users: "Users",
    rolesAndPermissions: "Roles & permissions",
    employees: "Employees",
    masterData: "Master data",
    projects: "Projects",
    vendors: "Vendors",
    customers: "Customers",
    products: "Products",
    resources: "Resources",
    objectTypes: "Object types",
    recordsAndActivity: "Records & activity",
    businessObjects: "Business objects",
    todos: "To-dos",
    approvals: "Approval log",
    automation: "Automation",
    skills: "Skills",
    apiKeys: "Access credentials",
    flowAgent: "Flow agent",
    closeNavigation: "Close navigation",
    navigation: "Workspace console navigation",
    signOut: "Sign out",
    openNavigation: "Open navigation",
    menu: "Menu",
    sessionRls: "Secure access",
    companyDataSeparated: "Company data separation",
    roleBasedAccess: "Role-based access",
    protectedRecords: "Protected records",
    loginProductLabel: "About Oryh",
    trustedFactLayer: "A trusted business fact layer",
    loginHero: "Let agents move work forward.\nLet systems hold the boundary.",
    loginBody: "Organization access, permissions, states, approvals, and audit history are verified by Oryh, while sign-in details stay protected.",
    loginWorkspace: "Sign in to your workspace",
    loginIntro: "Use your company account to open the workspace console.",
    email: "Work email",
    password: "Password",
    enterPassword: "Enter password",
    forgotPassword: "Forgot password?",
    resetPassword: "Reset password",
    resetPasswordIntro: "Enter your account email and we’ll send a time-limited, one-time reset link.",
    sendResetLink: "Send reset link",
    sendingResetLink: "Sending…",
    resetEmailSent: "If an eligible account exists for this email, a reset link has been sent. Check your inbox.",
    backToSignIn: "Back to sign in",
    signingIn: "Signing in…",
    enterConsole: "Open console",
    downloadConnectorSkill: "Download agent connector skill",
    returnWebsite: "Back to website",
    registerCompany: "Register a company",
    securityNote: "Your sign-in details are used only to protect access to this workspace.",
    versionLabel: "Version",
    invalidCredentials: "Incorrect email or password.",
    activeUsers: "Active users",
    currentTenant: "Current workspace",
    openTodos: "Open to-dos",
    awaitingAction: "Awaiting action",
    overdueTodos: "Overdue to-dos",
    needsAttention: "Needs attention",
    objects: "Business objects",
    undeletedRecords: "Undeleted records",
    activeSkills: "Active skills",
    distributable: "Ready to distribute",
    welcomeBack: "Welcome back",
    dashboardDescription: "This dashboard shows the latest business overview for your workspace.",
    currentRole: "Current role",
    capabilityGrants: "access permissions",
    tenantOperations: "Workspace overview",
    refresh: "Refresh",
    dashboardUnavailable: "The dashboard is unavailable right now.",
    retry: "Retry",
    consoleMigration: "Workspace ready",
    complete: "Complete",
    connectAgent: "Connect an agent",
    connectAgentTitle: "Connect your agent to Oryh",
    connectAgentDescription: "Unzip it into your local agent's skills folder, then ask it to connect you to Oryh. The download holds no key and no company data; your personal skills install themselves once you approve the device.",
    connectAgentGuide: "Installation guide",
    quickAccess: "Quick access",
    continueManaging: "Continue managing your workspace",
    quickAccessDescription: "Open every workspace management area from here.",
    pageNotFound: "Page not found",
    notFoundDescription: "This page could not be found. Check the link or return to the dashboard to continue.",
  },
} as const;

export type MessageKey = keyof (typeof messages)["zh-CN"];

type I18nContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: MessageKey) => string;
  text: (chinese: string, english: string) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);
const fallbackI18n: I18nContextValue = {
  language: "zh-CN",
  setLanguage: () => undefined,
  t: (key) => messages["zh-CN"][key],
  text: (chinese) => chinese,
};

function initialLanguage(defaultLanguage?: Language): Language {
  try {
    const saved = window.localStorage.getItem(storageKey);
    if (saved === "zh-CN" || saved === "en") return saved;
  } catch {
    // Private-mode storage failures should not stop the console from loading.
  }
  return defaultLanguage ?? (navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en");
}

export function LanguageProvider({ children, defaultLanguage }: { children: ReactNode; defaultLanguage?: Language }) {
  const [language, setLanguage] = useState<Language>(() => initialLanguage(defaultLanguage));

  useEffect(() => {
    document.documentElement.lang = language;
    try {
      window.localStorage.setItem(storageKey, language);
    } catch {
      // Language selection still applies for this browser session.
    }
  }, [language]);

  const value = useMemo<I18nContextValue>(() => ({
    language,
    setLanguage,
    t: (key) => messages[language][key],
    text: (chinese, english) => language === "en" ? english : chinese,
  }), [language]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  return context ?? fallbackI18n;
}

export function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { language, setLanguage, t } = useI18n();
  return (
    <label className={`language-switcher ${className}`.trim()}>
      <span className="sr-only">{t("language")}</span>
      <select
        aria-label={t("language")}
        value={language}
        onChange={(event) => setLanguage(event.target.value as Language)}
      >
        <option value="zh-CN">{t("chinese")}</option>
        <option value="en">{t("english")}</option>
      </select>
    </label>
  );
}
