import type { BootstrapData } from "./api/client";

function permissionCovers(permissions: string[], capability: string): boolean {
  return (
    permissions.includes(capability) || permissions.includes(`${capability}:*`)
  );
}

export function hasCapability(
  bootstrap: BootstrapData,
  capability: string,
): boolean {
  return permissionCovers(bootstrap.permissions, capability);
}

export function canManageTenantConfiguration(
  bootstrap: BootstrapData,
): boolean {
  return (
    bootstrap.role === "admin" ||
    permissionCovers(bootstrap.permissions, "users.manage")
  );
}

export function canManageObjectConfiguration(
  bootstrap: BootstrapData,
): boolean {
  return (
    canManageTenantConfiguration(bootstrap) ||
    hasCapability(bootstrap, "object_types.manage") ||
    hasCapability(bootstrap, "workflows.publish")
  );
}

export function canManageMasterData(bootstrap: BootstrapData): boolean {
  return (
    bootstrap.role === "admin" ||
    permissionCovers(bootstrap.permissions, "master_data.manage") ||
    permissionCovers(bootstrap.permissions, "users.manage")
  );
}

export function canManageEmployees(bootstrap: BootstrapData): boolean {
  return permissionCovers(bootstrap.permissions, "employees.manage");
}

export function canManageAccess(bootstrap: BootstrapData): boolean {
  return permissionCovers(bootstrap.permissions, "users.manage");
}
