import {
  Buildings,
  CalendarBlank,
  CheckSquare,
  ClipboardText,
  Database,
  Cube,
  Files,
  Folders,
  GearSix,
  IdentificationCard,
  Key,
  Robot,
  ShieldCheck,
  SquaresFour,
  Storefront,
  Users,
  UsersThree,
  type Icon,
} from "@phosphor-icons/react";
import type { BootstrapData } from "./api/client";
import type { MessageKey } from "./i18n";
import {
  canManageAccess,
  canManageEmployees,
  canManageMasterData,
  canManageObjectConfiguration,
  canManageTenantConfiguration,
  hasCapability,
} from "./access";

export type LocalLabel = readonly [string, string];
export type ConsoleDestination = {
  label: MessageKey;
  href: string;
  icon: Icon;
  description: LocalLabel;
  createLabel?: LocalLabel;
  visible?: (bootstrap: BootstrapData) => boolean;
};
export type NavigationGroup = {
  label: LocalLabel;
  items: ConsoleDestination[];
};

// One registry drives the sidebar, command search and quick-create actions.
// Route boundaries and server authorization remain the authority for access.
export const navigation: NavigationGroup[] = [
  {
    label: ["工作台", "Workspace"],
    items: [
      {
        label: "dashboard",
        href: "/dashboard",
        icon: SquaresFour,
        description: ["业务概况与常用入口", "Overview and everyday shortcuts"],
      },
      {
        label: "todos",
        href: "/todos",
        icon: CheckSquare,
        description: ["查看和处理人工待办", "Review and complete to-dos"],
      },
      {
        label: "approvals",
        href: "/approvals",
        icon: ClipboardText,
        description: [
          "查阅审批意见与处理记录",
          "Review decisions and approval history",
        ],
      },
    ],
  },
  {
    label: ["业务数据", "Business data"],
    items: [
      {
        label: "businessObjects",
        href: "/objects",
        icon: Files,
        description: [
          "报价、采购、费用及其他业务单据",
          "Quotations, purchases, expenses and business records",
        ],
        visible: canManageTenantConfiguration,
      },
      {
        label: "dataBrowser",
        href: "/data",
        icon: Database,
        description: [
          "按集合查看全部数据，任意筛选、排序与分页",
          "Every collection, with every filter, sort and paging",
        ],
        visible: canManageTenantConfiguration,
      },
      {
        label: "customers",
        href: "/customers",
        icon: Buildings,
        description: [
          "客户资料、联系人与开票信息",
          "Customers, contacts and billing details",
        ],
        createLabel: ["新建客户", "New customer"],
        visible: canManageMasterData,
      },
      {
        label: "products",
        href: "/products",
        icon: Cube,
        description: [
          "产品目录、SKU 与规格",
          "Product catalog, SKUs and variants",
        ],
        createLabel: ["新建产品", "New product"],
        visible: canManageMasterData,
      },
      {
        label: "vendors",
        href: "/vendors",
        icon: Storefront,
        description: [
          "供应商资料与采购联系人",
          "Suppliers and purchasing contacts",
        ],
        createLabel: ["新建供应商", "New vendor"],
        visible: canManageMasterData,
      },
      {
        label: "projects",
        href: "/projects",
        icon: Folders,
        description: [
          "项目编号、客户与有效期",
          "Projects, clients and active periods",
        ],
        createLabel: ["新建项目", "New project"],
        visible: canManageMasterData,
      },
      {
        label: "resources",
        href: "/resources",
        icon: CalendarBlank,
        description: [
          "会议室、设备与共享资源",
          "Rooms, equipment and shared resources",
        ],
        createLabel: ["新建资源", "New resource"],
        visible: canManageMasterData,
      },
    ],
  },
  {
    label: ["团队与访问", "Team & access"],
    items: [
      {
        label: "employees",
        href: "/employees",
        icon: IdentificationCard,
        description: [
          "员工档案与组织信息",
          "Employee profiles and organization",
        ],
        createLabel: ["新增员工", "Add employee"],
        visible: canManageEmployees,
      },
      {
        label: "users",
        href: "/users",
        icon: Users,
        description: [
          "邀请用户与分配登录权限",
          "Invite users and manage access",
        ],
        visible: canManageAccess,
      },
      {
        label: "rolesAndPermissions",
        href: "/roles",
        icon: ShieldCheck,
        description: [
          "角色、权限与技能分配",
          "Roles, permissions and skill access",
        ],
        visible: canManageAccess,
      },
    ],
  },
  {
    label: ["设置与自动化", "Settings & automation"],
    items: [
      {
        label: "objectTypes",
        href: "/object-types",
        icon: GearSix,
        description: [
          "字段定义、状态与业务流程",
          "Fields, states and workflows",
        ],
        visible: canManageObjectConfiguration,
      },
      {
        label: "skills",
        href: "/skills",
        icon: UsersThree,
        description: [
          "管理技能包与分发范围",
          "Manage skills and their audiences",
        ],
        visible: (b) => hasCapability(b, "skills.manage"),
      },
      {
        label: "apiKeys",
        href: "/api-keys",
        icon: Key,
        description: [
          "设备凭证与授权范围",
          "Device credentials and authorization",
        ],
        visible: (b) => hasCapability(b, "keys.manage"),
      },
      {
        label: "flowAgent",
        href: "/flow-agent",
        icon: Robot,
        description: [
          "流程代理的运行与配置",
          "Flow agent operation and configuration",
        ],
        visible: (b) => hasCapability(b, "keys.manage"),
      },
    ],
  },
];

export function visibleNavigation(bootstrap: BootstrapData): NavigationGroup[] {
  return navigation
    .map((group) => ({
      ...group,
      items: group.items.filter(
        (item) => !item.visible || item.visible(bootstrap),
      ),
    }))
    .filter((group) => group.items.length > 0);
}
