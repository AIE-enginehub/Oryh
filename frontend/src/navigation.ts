import { zhCN } from "./locales/zh-CN/console";
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
    label: [zhCN.navigation.message, "Workspace"],
    items: [
      {
        label: "dashboard",
        href: "/dashboard",
        icon: SquaresFour,
        description: [zhCN.navigation.message2, "Overview and everyday shortcuts"],
      },
      {
        label: "todos",
        href: "/todos",
        icon: CheckSquare,
        description: [zhCN.navigation.message3, "Review and complete to-dos"],
      },
      {
        label: "approvals",
        href: "/approvals",
        icon: ClipboardText,
        description: [
          zhCN.navigation.message4,
          "Review decisions and approval history",
        ],
      },
    ],
  },
  {
    label: [zhCN.navigation.message5, "Business data"],
    items: [
      {
        label: "businessObjects",
        href: "/objects",
        icon: Files,
        description: [
          zhCN.navigation.message6,
          "Quotations, purchases, expenses and business records",
        ],
        visible: canManageTenantConfiguration,
      },
      {
        label: "dataBrowser",
        href: "/data",
        icon: Database,
        description: [
          zhCN.navigation.message7,
          "Every collection, with every filter, sort and paging",
        ],
        visible: canManageTenantConfiguration,
      },
      {
        label: "customers",
        href: "/customers",
        icon: Buildings,
        description: [
          zhCN.navigation.message8,
          "Customers, contacts and billing details",
        ],
        createLabel: [zhCN.navigation.newCustomer, "New customer"],
        visible: canManageMasterData,
      },
      {
        label: "products",
        href: "/products",
        icon: Cube,
        description: [
          zhCN.navigation.message10,
          "Product catalog, SKUs and variants",
        ],
        createLabel: [zhCN.navigation.newProduct, "New product"],
        visible: canManageMasterData,
      },
      {
        label: "vendors",
        href: "/vendors",
        icon: Storefront,
        description: [
          zhCN.navigation.message12,
          "Suppliers and purchasing contacts",
        ],
        createLabel: [zhCN.navigation.newVendor, "New vendor"],
        visible: canManageMasterData,
      },
      {
        label: "projects",
        href: "/projects",
        icon: Folders,
        description: [
          zhCN.navigation.message14,
          "Projects, clients and active periods",
        ],
        createLabel: [zhCN.navigation.newProject, "New project"],
        visible: canManageMasterData,
      },
      {
        label: "resources",
        href: "/resources",
        icon: CalendarBlank,
        description: [
          zhCN.navigation.message16,
          "Rooms, equipment and shared resources",
        ],
        createLabel: [zhCN.navigation.newResource, "New resource"],
        visible: canManageMasterData,
      },
    ],
  },
  {
    label: [zhCN.navigation.message18, "Team & access"],
    items: [
      {
        label: "employees",
        href: "/employees",
        icon: IdentificationCard,
        description: [
          zhCN.navigation.message19,
          "Employee profiles and organization",
        ],
        createLabel: [zhCN.navigation.name9, "Add employee"],
        visible: canManageEmployees,
      },
      {
        label: "users",
        href: "/users",
        icon: Users,
        description: [
          zhCN.navigation.message21,
          "Invite users and manage access",
        ],
        visible: canManageAccess,
      },
      {
        label: "rolesAndPermissions",
        href: "/roles",
        icon: ShieldCheck,
        description: [
          zhCN.navigation.message22,
          "Roles, permissions and skill access",
        ],
        visible: canManageAccess,
      },
    ],
  },
  {
    label: [zhCN.navigation.message23, "Settings & automation"],
    items: [
      {
        label: "objectTypes",
        href: "/object-types",
        icon: GearSix,
        description: [
          zhCN.navigation.message24,
          "Fields, states and workflows",
        ],
        visible: canManageObjectConfiguration,
      },
      {
        label: "skills",
        href: "/skills",
        icon: UsersThree,
        description: [
          zhCN.navigation.message25,
          "Manage skills and their audiences",
        ],
        visible: (b) => hasCapability(b, "skills.manage"),
      },
      {
        label: "apiKeys",
        href: "/api-keys",
        icon: Key,
        description: [
          zhCN.navigation.message26,
          "Device credentials and authorization",
        ],
        visible: (b) => hasCapability(b, "keys.manage"),
      },
      {
        label: "flowAgent",
        href: "/flow-agent",
        icon: Robot,
        description: [
          zhCN.navigation.message27,
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
