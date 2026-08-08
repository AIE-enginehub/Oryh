import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createCapability,
  createRole,
  deleteCapability,
  deleteRole,
  listCapabilities,
  listRoles,
  updateRole,
  type Capability,
  type Role,
} from "../api/client";
import { getRoleSkillReach } from "../api/configuration";
import { ConfirmDialog } from "../components/master-data/ConfirmDialog";
import { Drawer } from "../components/master-data/Drawer";
import { apiErrorMessage, ListState } from "../components/master-data/ListState";
import { PermissionMatrix } from "../components/roles/PermissionMatrix";
import { useI18n } from "../i18n";
import { SkillReachPanel } from "../components/skills/SkillReachPanel";
import "./roles.css";

const ROLE_NAME_PATTERN = /^[a-z0-9_]+$/;
const CAPABILITY_NAME_PATTERN = /^[a-z0-9_.]+$/;

type RoleForm = {
  name: string;
  title: string;
  description: string;
  permissions: string[];
};

type CapabilityForm = {
  name: string;
  title: string;
  description: string;
};

type RoleRequestFields = {
  title: string | null;
  description: string | null;
  permissions: string[];
};

type CapabilityRequest = {
  name: string;
  title: string | null;
  description: string | null;
};
type Localize = (chinese: string, english: string) => string;

function newRoleForm(): RoleForm {
  return { name: "", title: "", description: "", permissions: [] };
}

function newCapabilityForm(): CapabilityForm {
  return { name: "", title: "", description: "" };
}

function roleForm(role: Role): RoleForm {
  const permissions = new Set<string>(role.permissions as string[]);
  if (role.is_system && role.name === "admin") permissions.add("users.manage");
  return {
    name: role.name,
    title: role.title ?? "",
    description: role.description ?? "",
    permissions: Array.from(permissions).sort(),
  };
}

function roleLabel(role: Role, text: Localize): string {
  if (role.is_system && role.name === "admin") return text("管理员", "Administrator");
  if (role.is_system && role.name === "member") return text("成员", "Member");
  return role.title && role.title !== role.name ? role.title : role.name;
}

export function RolesPage() {
  const queryClient = useQueryClient();
  const { text } = useI18n();
  const roles = useQuery({ queryKey: ["roles"], queryFn: listRoles });
  const catalog = useQuery({ queryKey: ["capabilities"], queryFn: listCapabilities });
  const [selectedRoleName, setSelectedRoleName] = useState<string | null>(null);
  const [editingRole, setEditingRole] = useState<Role | null | undefined>(undefined);
  const [roleDraft, setRoleDraft] = useState<RoleForm>(newRoleForm);
  const [roleValidation, setRoleValidation] = useState<string | null>(null);
  const [deletingRole, setDeletingRole] = useState<Role | null>(null);

  const [creatingCapability, setCreatingCapability] = useState(false);
  const [capabilityDraft, setCapabilityDraft] = useState<CapabilityForm>(newCapabilityForm);
  const [capabilityValidation, setCapabilityValidation] = useState<string | null>(null);
  const [deletingCapability, setDeletingCapability] = useState<Capability | null>(null);

  const selectedRole = useMemo(
    () => roles.data?.find((role) => role.name === selectedRoleName) ?? null,
    [roles.data, selectedRoleName],
  );

  useEffect(() => {
    if (!roles.data || roles.data.length === 0) {
      if (selectedRoleName !== null) setSelectedRoleName(null);
      return;
    }
    if (!selectedRoleName || !roles.data.some((role) => role.name === selectedRoleName)) {
      setSelectedRoleName(roles.data[0].name);
    }
  }, [roles.data, selectedRoleName]);

  type SaveRoleVariables =
    | { mode: "create"; input: RoleRequestFields & { name: string } }
    | { mode: "update"; id: string; input: RoleRequestFields };

  const saveRole = useMutation({
    mutationFn: (variables: SaveRoleVariables) => variables.mode === "create"
      ? createRole(variables.input)
      : updateRole(variables.id, variables.input),
    onSuccess: async (saved) => {
      setEditingRole(undefined);
      setSelectedRoleName(saved.name);
      await queryClient.invalidateQueries({ queryKey: ["roles"] });
    },
  });

  const removeRole = useMutation({
    mutationFn: (id: string) => deleteRole(id),
    onSuccess: async () => {
      setDeletingRole(null);
      setSelectedRoleName(null);
      await queryClient.invalidateQueries({ queryKey: ["roles"] });
    },
  });

  const addCapability = useMutation({
    mutationFn: (input: CapabilityRequest) => createCapability(input),
    onSuccess: async () => {
      setCreatingCapability(false);
      await queryClient.invalidateQueries({ queryKey: ["capabilities"] });
    },
  });

  const removeCapability = useMutation({
    mutationFn: (name: string) => deleteCapability(name),
    onSuccess: async () => {
      setDeletingCapability(null);
      await queryClient.invalidateQueries({ queryKey: ["capabilities"] });
    },
  });

  const openCreateRole = () => {
    setRoleDraft(newRoleForm());
    setRoleValidation(null);
    setEditingRole(null);
    saveRole.reset();
  };

  const openEditRole = (role: Role) => {
    setRoleDraft(roleForm(role));
    setRoleValidation(null);
    setEditingRole(role);
    saveRole.reset();
  };

  const submitRole = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = roleDraft.name.trim();
    const title = roleDraft.title.trim();
    const description = roleDraft.description.trim();
    if (!editingRole && !name) {
      setRoleValidation(text("角色名称不能为空。", "Role name is required."));
      return;
    }
    if (!editingRole && !ROLE_NAME_PATTERN.test(name)) {
      setRoleValidation(text("角色名称只能包含小写字母、数字和下划线。", "Role name can contain only lowercase letters, numbers, and underscores."));
      return;
    }
    if (name.length > 50) {
      setRoleValidation(text("角色名称不能超过 50 个字符。", "Role name cannot exceed 50 characters."));
      return;
    }
    if (title.length > 200) {
      setRoleValidation(text("角色标题不能超过 200 个字符。", "Role title cannot exceed 200 characters."));
      return;
    }
    if (description.length > 2000) {
      setRoleValidation(text("角色说明不能超过 2000 个字符。", "Role description cannot exceed 2,000 characters."));
      return;
    }

    const permissions = new Set<string>(roleDraft.permissions);
    if (editingRole?.is_system && editingRole.name === "admin") permissions.add("users.manage");
    const normalized = Array.from(permissions).sort();
    setRoleValidation(null);
    if (editingRole) {
      saveRole.mutate({
        mode: "update",
        id: editingRole.id,
        input: { title: title || null, description: description || null, permissions: normalized },
      });
    } else {
      saveRole.mutate({
        mode: "create",
        input: { name, title: title || null, description: description || null, permissions: normalized },
      });
    }
  };

  const openCreateCapability = () => {
    setCapabilityDraft(newCapabilityForm());
    setCapabilityValidation(null);
    setCreatingCapability(true);
    addCapability.reset();
  };

  const submitCapability = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = capabilityDraft.name.trim();
    const title = capabilityDraft.title.trim();
    const description = capabilityDraft.description.trim();
    if (!name) {
      setCapabilityValidation(text("能力名称不能为空。", "Capability name is required."));
      return;
    }
    if (!CAPABILITY_NAME_PATTERN.test(name)) {
      setCapabilityValidation(text("能力名称只能包含小写字母、数字、点和下划线。", "Capability name can contain only lowercase letters, numbers, dots, and underscores."));
      return;
    }
    if (name.length > 100 || title.length > 200 || description.length > 2000) {
      setCapabilityValidation(text("能力名称、标题或说明超过长度限制。", "The capability name, title, or description exceeds its length limit."));
      return;
    }
    setCapabilityValidation(null);
    addCapability.mutate({ name, title: title || null, description: description || null });
  };

  const loading = roles.isPending || catalog.isPending;
  const loadError = roles.isError
    ? apiErrorMessage(roles.error)
    : catalog.isError
      ? apiErrorMessage(catalog.error)
      : null;
  const capabilities = catalog.data?.capabilities ?? [];
  const objectTypes = catalog.data?.object_types ?? [];
  const customCapabilities = capabilities.filter((capability) => capability.kind === "custom");

  return (
    <div className="roles-page" data-testid="roles-page">
      <header className="page-intro">
        <div>
          <span className="eyebrow">Roles & capabilities</span>
          <h2>{text("角色与能力", "Roles and capabilities")}</h2>
          <p>{text("组合系统权限、业务类型范围和工作空间自定义资格，形成清晰可查的访问边界。", "Combine system permissions, business-type scopes, and workspace-defined qualifications into a clear, reviewable access boundary.")}</p>
        </div>
      </header>

      <ListState
        loading={loading}
        error={loadError}
        empty={false}
        emptyTitle=""
        emptyDescription=""
        onRetry={() => {
          void roles.refetch();
          void catalog.refetch();
        }}
      >
        <div className="roles-grid">
          <section className="role-directory data-panel" aria-label={text("角色列表", "Role list")}>
            <header className="workspace-header">
              <div><span className="eyebrow">Role directory</span><h3>{text("角色", "Roles")}</h3></div>
              <button className="button primary compact" type="button" onClick={openCreateRole}>＋ {text("新建角色", "New role")}</button>
            </header>
            {roles.data && roles.data.length > 0 ? (
              <div className="role-list">
                {roles.data.map((role) => (
                  <button
                    className={`role-list-item ${selectedRole?.id === role.id ? "selected" : ""}`}
                    type="button"
                    aria-pressed={selectedRole?.id === role.id}
                    key={role.id}
                    onClick={() => setSelectedRoleName(role.name)}
                  >
                    <span className="role-list-copy">
                      <strong>{roleLabel(role, text)}</strong>
                      <code>{role.name}</code>
                    </span>
                    <span className="role-list-meta">
                      <span className={`role-kind ${role.is_system ? "system" : "custom"}`}>
                        {role.is_system ? text("系统", "System") : text("自定义", "Custom")}
                      </span>
                      <small>{text(`${role.permissions.length} 项权限`, `${role.permissions.length} permissions`)}</small>
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="workspace-empty"><strong>{text("还没有角色", "No roles yet")}</strong><p>{text("创建第一个自定义角色并分配所需能力。", "Create the first custom role and assign the capabilities it needs.")}</p></div>
            )}
          </section>

          <section className="role-detail data-panel" aria-label={text("角色详情", "Role details")}>
            {!selectedRole ? (
              <div className="workspace-empty"><strong>{text("选择一个角色", "Select a role")}</strong><p>{text("查看其能力组合或开始编辑。", "Review its capabilities or start editing.")}</p></div>
            ) : (
              <>
                <header className="workspace-header role-detail-header">
                  <div>
                    <span className="eyebrow">{selectedRole.is_system ? "System role" : "Custom role"}</span>
                    <h3>{roleLabel(selectedRole, text)}</h3>
                    <code>{selectedRole.name}</code>
                  </div>
                  <div className="workspace-actions">
                    {!selectedRole.is_system && (
                      <button
                        className="button danger compact"
                        type="button"
                        onClick={() => { removeRole.reset(); setDeletingRole(selectedRole); }}
                      >
                        {text("删除角色", "Delete role")}
                      </button>
                    )}
                    <button className="button compact" type="button" onClick={() => openEditRole(selectedRole)}>
                      {text("编辑角色", "Edit role")}
                    </button>
                  </div>
                </header>
                <div className="role-detail-body">
                  <p className="role-description">{selectedRole.is_system && selectedRole.name === "admin" ? text("工作空间管理员", "Workspace administrator") : selectedRole.is_system && selectedRole.name === "member" ? text("工作空间成员", "Workspace member") : selectedRole.description || text("暂无角色说明。", "No role description.")}</p>
                  <div className="detail-stat-row">
                    <div><span>{text("角色类型", "Role type")}</span><strong>{selectedRole.is_system ? text("系统角色", "System role") : text("自定义角色", "Custom role")}</strong></div>
                    <div><span>{text("权限数量", "Permissions")}</span><strong>{selectedRole.permissions.length}</strong></div>
                  </div>
                  <div className="grant-summary">
                    <h4>{text("当前授权", "Current grants")}</h4>
                    {selectedRole.permissions.length > 0 ? (
                      <div className="grant-chips">
                        {(selectedRole.permissions as string[]).map((permission: string) => <code key={permission}>{permission}</code>)}
                      </div>
                    ) : (
                      <div className="permission-empty">{text("此角色尚未授予任何能力。", "No capabilities have been granted to this role.")}</div>
                    )}
                  </div>
                  <SkillReachPanel
                    subjectKey={`role:${selectedRole.name}`}
                    fetcher={() => getRoleSkillReach(selectedRole.name)}
                  />
                </div>
              </>
            )}
          </section>
        </div>

        <section className="custom-capability-panel data-panel" aria-label={text("自定义能力", "Custom capabilities")}>
          <header className="workspace-header">
            <div>
              <span className="eyebrow">Workspace vocabulary</span>
              <h3>{text("自定义能力", "Custom capabilities")}</h3>
              <p>{text("作为 Skill 分发门槛和流程参与条件，不会自动改变其他业务操作权限。", "Use these as Skill-distribution gates and workflow qualifications; they do not automatically change other business permissions.")}</p>
            </div>
            <button className="button primary compact" type="button" onClick={openCreateCapability}>＋ {text("新建能力", "New capability")}</button>
          </header>
          {customCapabilities.length > 0 ? (
            <div className="custom-capability-list">
              {customCapabilities.map((capability) => (
                <article className="custom-capability-row" key={capability.id}>
                  <div>
                    <strong>{capability.title || capability.name}</strong>
                    <code>{capability.name}</code>
                    <p>{capability.description || text("暂无说明。", "No description.")}</p>
                  </div>
                  <button
                    className="button danger compact"
                    type="button"
                    onClick={() => { removeCapability.reset(); setDeletingCapability(capability); }}
                  >
                    {text("删除能力", "Delete capability")}
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <div className="workspace-empty compact"><strong>{text("还没有自定义能力", "No custom capabilities yet")}</strong><p>{text("需要新的 Skill 或流程资格词汇时再创建。", "Create one when you need a new Skill or workflow qualification.")}</p></div>
          )}
        </section>
      </ListState>

      <Drawer
        open={editingRole !== undefined}
        title={editingRole ? text(`编辑角色 · ${editingRole.name}`, `Edit role · ${editingRole.name}`) : text("新建角色", "New role")}
        description={text("角色名称创建后不可修改；权限变更会经过系统核验并留下记录。", "Role names cannot be changed after creation. Permission changes are checked and recorded by Oryh.")}
        submitLabel={editingRole ? text("保存角色", "Save role") : text("创建角色", "Create role")}
        busy={saveRole.isPending}
        error={roleValidation || (saveRole.isError ? apiErrorMessage(saveRole.error) : null)}
        onClose={() => !saveRole.isPending && setEditingRole(undefined)}
        onSubmit={submitRole}
      >
        <div className="field-grid role-fields">
          <div className="field">
            <label htmlFor="role-name">{text("角色名称", "Role name")} <b>*</b></label>
            <input
              id="role-name"
              maxLength={50}
              required
              disabled={Boolean(editingRole)}
              value={roleDraft.name}
              onChange={(event) => setRoleDraft({ ...roleDraft, name: event.target.value })}
            />
            <small>{text("小写字母、数字和下划线。", "Lowercase letters, numbers, and underscores.")}</small>
          </div>
          <div className="field">
            <label htmlFor="role-title">{text("显示标题", "Display title")}</label>
            <input id="role-title" maxLength={200} value={roleDraft.title} onChange={(event) => setRoleDraft({ ...roleDraft, title: event.target.value })} />
          </div>
          <div className="field span-2">
            <label htmlFor="role-description">{text("角色说明", "Role description")}</label>
            <textarea id="role-description" rows={3} maxLength={2000} value={roleDraft.description} onChange={(event) => setRoleDraft({ ...roleDraft, description: event.target.value })} />
          </div>
        </div>
        <PermissionMatrix
          capabilities={capabilities}
          objectTypes={objectTypes}
          permissions={roleDraft.permissions}
          lockAdminUsersManage={Boolean(editingRole?.is_system && editingRole.name === "admin")}
          onChange={(permissions) => setRoleDraft({ ...roleDraft, permissions })}
        />
      </Drawer>

      <Drawer
        open={creatingCapability}
        title={text("新建自定义能力", "New custom capability")}
        description={text("自定义能力仅作为 Skill 分发和流程资格词汇。", "Custom capabilities are used only for Skill distribution and workflow qualifications.")}
        submitLabel={text("创建能力", "Create capability")}
        busy={addCapability.isPending}
        error={capabilityValidation || (addCapability.isError ? apiErrorMessage(addCapability.error) : null)}
        onClose={() => !addCapability.isPending && setCreatingCapability(false)}
        onSubmit={submitCapability}
      >
        <div className="field-grid">
          <div className="field span-2">
            <label htmlFor="capability-name">{text("能力名称", "Capability name")} <b>*</b></label>
            <input
              id="capability-name"
              required
              maxLength={100}
              placeholder="jc.warranty.approve"
              value={capabilityDraft.name}
              onChange={(event) => setCapabilityDraft({ ...capabilityDraft, name: event.target.value })}
            />
            <small>{text("小写字母、数字、点和下划线。", "Lowercase letters, numbers, dots, and underscores.")}</small>
          </div>
          <div className="field span-2">
            <label htmlFor="capability-title">{text("显示标题", "Display title")}</label>
            <input id="capability-title" maxLength={200} value={capabilityDraft.title} onChange={(event) => setCapabilityDraft({ ...capabilityDraft, title: event.target.value })} />
          </div>
          <div className="field span-2">
            <label htmlFor="capability-description">{text("能力说明", "Capability description")}</label>
            <textarea id="capability-description" rows={4} maxLength={2000} value={capabilityDraft.description} onChange={(event) => setCapabilityDraft({ ...capabilityDraft, description: event.target.value })} />
          </div>
        </div>
      </Drawer>

      <ConfirmDialog
        open={Boolean(deletingRole)}
        title={text(`删除角色“${deletingRole?.name ?? ""}”？`, `Delete role “${deletingRole?.name ?? ""}”?`)}
        description={text("只有未分配给用户的自定义角色才能删除。此操作会写入审计记录。", "Only custom roles that are not assigned to users can be deleted. This action is recorded in the audit log.")}
        busy={removeRole.isPending}
        error={removeRole.isError ? apiErrorMessage(removeRole.error) : null}
        kicker={text("删除确认", "Confirm deletion")}
        confirmLabel={text("确认删除", "Delete")}
        busyLabel={text("正在删除…", "Deleting…")}
        scrimLabel={text("取消删除", "Cancel deletion")}
        onCancel={() => !removeRole.isPending && setDeletingRole(null)}
        onConfirm={() => deletingRole && removeRole.mutate(deletingRole.id)}
      />

      <ConfirmDialog
        open={Boolean(deletingCapability)}
        title={text(`删除能力“${deletingCapability?.name ?? ""}”？`, `Delete capability “${deletingCapability?.name ?? ""}”?`)}
        description={text("已授予角色或被 Skill 使用的权限不能删除；系统会说明具体冲突原因。", "A permission granted to a role or used by a Skill cannot be deleted; Oryh will explain the conflict.")}
        busy={removeCapability.isPending}
        error={removeCapability.isError ? apiErrorMessage(removeCapability.error) : null}
        kicker={text("删除确认", "Confirm deletion")}
        confirmLabel={text("确认删除", "Delete")}
        busyLabel={text("正在删除…", "Deleting…")}
        scrimLabel={text("取消删除", "Cancel deletion")}
        onCancel={() => !removeCapability.isPending && setDeletingCapability(null)}
        onConfirm={() => deletingCapability && removeCapability.mutate(deletingCapability.name)}
      />
    </div>
  );
}
