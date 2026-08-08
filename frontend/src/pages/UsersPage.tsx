import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useOutletContext } from "react-router-dom";

import type { ConsoleContext } from "../App";
import {
  ApiError,
  generateUserSkillBundle,
  getEmployee,
  inviteUser,
  listEmployees,
  listRoles,
  listUsers,
  resendInvitation,
  sendPasswordResetEmail,
  updateUser,
  type FileDownload,
  type InvitationUser,
  type InviteUserInput,
  type PasswordResetEmail,
  type Role,
  type UpdateUserInput,
  type User,
} from "../api/client";
import { getUserSkillReach } from "../api/configuration";
import { ConfirmDialog } from "../components/master-data/ConfirmDialog";
import { Drawer } from "../components/master-data/Drawer";
import { apiErrorMessage, ListState } from "../components/master-data/ListState";
import { Pagination } from "../components/master-data/Pagination";
import { useI18n } from "../i18n";
import { SkillReachPanel } from "../components/skills/SkillReachPanel";
import "./users.css";

const PAGE_SIZE = 20;
const OPTION_PAGE_SIZE = 50;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type UserStatus = "invited" | "active" | "disabled";
type StatusFilter = "" | UserStatus;
type UserForm = {
  email: string;
  name: string;
  role: string;
  status: UserStatus;
  employeeId: string;
};
type UserFieldErrors = Partial<Record<"email" | "name" | "role", string>>;
type AccessNotice = {
  kind: "invitation" | "password-reset";
  tone: "success" | "warning";
  url: string | null;
  title: string;
  message: string;
};
type BundleNotice = { message: string; tone: "success" | "warning" };
type OneTimeCredentialAction = "invite" | "resend" | "password-reset";
type Localize = (chinese: string, english: string) => string;

function emptyUserForm(defaultRole: string): UserForm {
  return { email: "", name: "", role: defaultRole, status: "invited", employeeId: "" };
}

function formFromUser(user: User): UserForm {
  return {
    email: user.email,
    name: user.name ?? "",
    role: user.role,
    status: user.status,
    employeeId: user.employee_id ?? "",
  };
}

function validateForm(form: UserForm, text: Localize): UserFieldErrors {
  const errors: UserFieldErrors = {};
  const email = form.email.trim();
  const name = form.name.trim();
  if (!email) errors.email = text("邮箱不能为空。", "Email is required.");
  else if (!EMAIL_PATTERN.test(email)) errors.email = text("请输入有效的邮箱地址。", "Enter a valid email address.");
  else if (email.length > 320) errors.email = text("邮箱不能超过 320 个字符。", "Email cannot exceed 320 characters.");
  if (name.length > 200) errors.name = text("姓名不能超过 200 个字符。", "Name cannot exceed 200 characters.");
  if (!form.role) errors.role = text("请选择角色。", "Select a role.");
  return errors;
}

function roleLabel(role: Role, text: Localize): string {
  const systemTitle = role.is_system
    ? ({ admin: text("管理员", "Administrator"), member: text("成员", "Member") } as Record<string, string>)[role.name]
    : undefined;
  const title = systemTitle ?? role.title;
  return title ? text(`${title}（${role.name}）`, `${title} (${role.name})`) : role.name;
}

function UserStatusBadge({ status }: { status: UserStatus }) {
  const { text } = useI18n();
  const labels: Record<UserStatus, string> = {
    invited: text("待接受邀请", "Invitation pending"),
    active: text("已启用", "Active"),
    disabled: text("已停用", "Disabled"),
  };
  return <span className={`user-status ${status}`}>{labels[status]}</span>;
}

function saveDownload(download: FileDownload): void {
  const url = URL.createObjectURL(download.blob);
  const anchor = document.createElement("a");
  try {
    anchor.href = url;
    anchor.download = download.filename;
    anchor.hidden = true;
    document.body.append(anchor);
    anchor.click();
  } finally {
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}

export function UsersPage() {
  const { bootstrap } = useOutletContext<ConsoleContext>();
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [role, setRole] = useState("");
  const [draftKeyword, setDraftKeyword] = useState("");
  const [draftStatus, setDraftStatus] = useState<StatusFilter>("");
  const [draftRole, setDraftRole] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<User | null | undefined>(undefined);
  const [form, setForm] = useState<UserForm>(() => emptyUserForm("member"));
  const [fieldErrors, setFieldErrors] = useState<UserFieldErrors>({});
  const [accessNotice, setAccessNotice] = useState<AccessNotice | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const [employeeSearchDraft, setEmployeeSearchDraft] = useState("");
  const [employeeKeyword, setEmployeeKeyword] = useState("");
  const [bundleTarget, setBundleTarget] = useState<User | null>(null);
  const [bundleNotice, setBundleNotice] = useState<BundleNotice | null>(null);
  const [bundleError, setBundleError] = useState<string | null>(null);
  const [resetTarget, setResetTarget] = useState<User | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);
  const oneTimeCredentialMutex = useRef<OneTimeCredentialAction | null>(null);
  const [oneTimeCredentialAction, setOneTimeCredentialAction] = useState<OneTimeCredentialAction | null>(null);

  const acquireOneTimeCredentialMutex = (action: OneTimeCredentialAction): boolean => {
    if (oneTimeCredentialMutex.current !== null) return false;
    oneTimeCredentialMutex.current = action;
    setOneTimeCredentialAction(action);
    return true;
  };
  const releaseOneTimeCredentialMutex = (action: OneTimeCredentialAction): void => {
    if (oneTimeCredentialMutex.current !== action) return;
    oneTimeCredentialMutex.current = null;
    setOneTimeCredentialAction((current) => current === action ? null : current);
  };

  const users = useQuery({
    queryKey: ["users", { keyword, status, role, page }],
    queryFn: () => listUsers({
      page,
      size: PAGE_SIZE,
      keyword: keyword || undefined,
      status: status || undefined,
      role: role || undefined,
    }),
    placeholderData: keepPreviousData,
  });
  const roles = useQuery({ queryKey: ["roles", "options"], queryFn: listRoles, staleTime: 60_000 });
  const employees = useQuery({
    queryKey: ["employees", "user-options", employeeKeyword],
    queryFn: () => listEmployees({
      page: 1,
      size: OPTION_PAGE_SIZE,
      keyword: employeeKeyword || undefined,
    }),
    staleTime: 60_000,
  });
  const linkedEmployee = useQuery({
    queryKey: ["employees", "linked-option", editing?.employee_id],
    queryFn: () => getEmployee(editing!.employee_id!),
    enabled: Boolean(editing?.employee_id),
    staleTime: 60_000,
  });

  const roleOptions = roles.data ?? [];
  const employeeOptions = useMemo(() => {
    const options = [...(employees.data?.data ?? [])];
    if (linkedEmployee.data && !options.some((employee) => employee.id === linkedEmployee.data.id)) {
      options.unshift(linkedEmployee.data);
    }
    return options;
  }, [employees.data, linkedEmployee.data]);
  const roleNames = useMemo(() => new Set(roleOptions.map((item) => item.name)), [roleOptions]);
  const defaultRole = roleNames.has("member") ? "member" : (roleOptions[0]?.name ?? "member");
  const employeeById = useMemo(
    () => new Map(employeeOptions.map((employee) => [employee.id, employee])),
    [employeeOptions],
  );
  const roleByName = useMemo(
    () => new Map(roleOptions.map((item) => [item.name, item])),
    [roleOptions],
  );

  const showInvitation = (result: InvitationUser, resent: boolean) => {
    const url = result.invitation_url ?? null;
    setAccessNotice({
      kind: "invitation",
      tone: "success",
      url,
      title: `${resent ? text("邀请已重新发送", "Invitation resent") : text("用户已邀请", "User invited")} · ${result.email}`,
      message: url
        ? text("该链接仅在本次响应中显示，请立即安全发送给受邀人。", "This link is shown only in this response. Send it securely to the invitee now.")
        : text("邀请邮件已发送；当前环境未返回一次性链接。", "The invitation email was sent; this environment did not return a one-time link."),
    });
    setCopyState("idle");
  };

  const invite = useMutation({
    mutationFn: (input: InviteUserInput) => inviteUser(input),
    onSuccess: async (result) => {
      setEditing(undefined);
      setPage(1);
      showInvitation(result, false);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onSettled: () => releaseOneTimeCredentialMutex("invite"),
  });
  const update = useMutation({
    mutationFn: ({ id, input }: { id: string; input: UpdateUserInput }) => updateUser(id, input),
    onSuccess: async () => {
      setEditing(undefined);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["users"] }),
        queryClient.invalidateQueries({ queryKey: ["api-keys"] }),
      ]);
    },
  });
  const resend = useMutation({
    mutationFn: (user: User) => resendInvitation(user.id),
    onSuccess: async (result) => {
      showInvitation(result, true);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onSettled: () => releaseOneTimeCredentialMutex("resend"),
  });
  const passwordReset = useMutation({
    mutationFn: (user: User): Promise<PasswordResetEmail> => sendPasswordResetEmail(user.id),
    onMutate: () => {
      setResetError(null);
    },
    onSuccess: (result) => {
      setResetTarget(null);
      setCopyState("idle");
      setAccessNotice({
        kind: "password-reset",
        tone: result.email_sent ? "success" : "warning",
        url: null,
        title: result.email_sent
          ? `${text("重置密码邮件已发送", "Password reset email sent")} · ${result.user.email}`
          : `${text("重置链接已生成，但邮件未送达", "Reset link created, but email delivery failed")} · ${result.user.email}`,
        message: result.email_sent
          ? text("用户可通过邮件中的一次性链接设置新密码；完成后旧会话会全部退出。", "The user can set a new password using the one-time link in the email. Existing sessions will end after the reset.")
          : text("当前密码和会话仍然有效。请检查邮件配置后再次发送；再次发送会作废本次链接。", "The current password and sessions remain valid. Check the email configuration before sending again; another send will invalidate this link."),
      });
    },
    onError: (error, user) => {
      const knownRejection = error instanceof ApiError && error.status >= 400 && error.status < 500;
      const message = knownRejection
        ? `${text("无法发送重置邮件", "Could not send the reset email")}: ${apiErrorMessage(error)}`
        : `${text("无法确认重置邮件是否送达", "Could not confirm reset email delivery")}: ${apiErrorMessage(error)}. ${text("系统可能已生成并发送链接；请先让用户检查邮箱，再决定是否重试。", "Oryh may already have generated and sent a link. Ask the user to check their inbox before retrying.")}`;
      setResetError(message);
      if (!knownRejection) {
        setCopyState("idle");
        setAccessNotice({
          kind: "password-reset",
          tone: "warning",
          url: null,
          title: `${text("重置邮件结果未能确认", "Reset email outcome could not be confirmed")} · ${user.email}`,
          message,
        });
      }
    },
    onSettled: () => releaseOneTimeCredentialMutex("password-reset"),
  });
  const bundle = useMutation({
    mutationFn: (user: User) => generateUserSkillBundle(user.id),
    onMutate: () => {
      setBundleError(null);
      setBundleNotice(null);
    },
    onSuccess: (download, user) => {
      try {
        saveDownload(download);
      } catch {
        const message = text(
          "系统已更新该用户的访问凭证，但未能保存下载文件。请先检查访问凭证状态；再次尝试会再次更新凭证。",
          "Oryh updated this user's access credential, but could not save the download. Check the credential status first; another attempt will update it again.",
        );
        setBundleError(message);
        setBundleNotice({ message, tone: "warning" });
        return;
      }
      setBundleTarget(null);
      setBundleNotice({
        message: text(
          `${user.name || user.email} 的 Skill 包已生成；此前的访问凭证已失效。`,
          `The Skill bundle for ${user.name || user.email} was generated; the previous access credential is now invalid.`,
        ),
        tone: "success",
      });
    },
    onError: (error) => {
      const message = text(
        `无法确认 Skill 包是否完整送达：${apiErrorMessage(error)}。系统可能已经更新访问凭证；请先检查凭证状态，再决定是否重试。`,
        `Could not confirm complete delivery of the Skill bundle: ${apiErrorMessage(error)}. Oryh may already have updated the access credential; check its status before retrying.`,
      );
      setBundleError(message);
      setBundleNotice({ message, tone: "warning" });
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["api-keys"] }),
  });

  const result = users.data;
  const availablePages = result?.meta.pages;
  useEffect(() => {
    if (availablePages !== undefined && page > availablePages) {
      setPage(Math.max(availablePages, 1));
    }
  }, [availablePages, page]);

  const updateField = <Field extends keyof UserForm>(field: Field, value: UserForm[Field]) => {
    setForm((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => {
      if (!(field in current)) return current;
      const next = { ...current };
      delete next[field as keyof UserFieldErrors];
      return next;
    });
  };

  const openInvite = () => {
    if (oneTimeCredentialMutex.current !== null) return;
    setForm(emptyUserForm(defaultRole));
    setFieldErrors({});
    setEditing(null);
    invite.reset();
    update.reset();
    setEmployeeSearchDraft("");
    setEmployeeKeyword("");
  };
  const openEdit = (user: User) => {
    setForm(formFromUser(user));
    setFieldErrors({});
    setEditing(user);
    invite.reset();
    update.reset();
    setEmployeeSearchDraft("");
    setEmployeeKeyword("");
  };
  const closeDrawer = () => {
    if (!invite.isPending && !update.isPending) setEditing(undefined);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const errors = validateForm(form, text);
    const needsRoleOptions = editing === null || editing?.id !== bootstrap.user.id;
    if (needsRoleOptions && (roles.isPending || roles.isError)) {
      errors.role = text("角色选项尚未加载，请重试。", "Role options have not loaded. Try again.");
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    if (editing) {
      const isSelf = editing.id === bootstrap.user.id;
      const input: UpdateUserInput = {
        email: form.email.trim(),
        name: form.name.trim() || null,
        employee_id: form.employeeId || null,
      };
      if (!isSelf) {
        input.role = form.role;
        if (form.status !== "invited") input.status = form.status;
      }
      update.mutate({ id: editing.id, input });
      return;
    }

    const input: InviteUserInput = {
      email: form.email.trim(),
      name: form.name.trim() || null,
      role: form.role,
      employee_id: form.employeeId || null,
    };
    if (acquireOneTimeCredentialMutex("invite")) invite.mutate(input);
  };

  const resendUserInvitation = (user: User) => {
    if (acquireOneTimeCredentialMutex("resend")) resend.mutate(user);
  };

  const openPasswordReset = (user: User) => {
    if (oneTimeCredentialMutex.current !== null) return;
    passwordReset.reset();
    setResetError(null);
    setResetTarget(user);
  };

  const submitPasswordReset = () => {
    if (!resetTarget || !acquireOneTimeCredentialMutex("password-reset")) return;
    passwordReset.mutate(resetTarget);
  };

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setKeyword(draftKeyword.trim());
    setStatus(draftStatus);
    setRole(draftRole);
    setPage(1);
  };
  const clearFilters = () => {
    setDraftKeyword("");
    setDraftStatus("");
    setDraftRole("");
    setKeyword("");
    setStatus("");
    setRole("");
    setPage(1);
  };

  const copyAccessLink = async () => {
    if (!accessNotice?.url) return;
    try {
      await navigator.clipboard.writeText(accessNotice.url);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  };

  const isEditingSelf = editing?.id === bootstrap.user.id;
  const canIssueSkillBundles = bootstrap.permissions.includes("keys.manage") ||
    bootstrap.permissions.includes("keys.manage:*");
  const oneTimeCredentialPending = oneTimeCredentialAction !== null ||
    invite.isPending || resend.isPending || passwordReset.isPending;
  const drawerError = editing === null
    ? (invite.isError ? apiErrorMessage(invite.error) : null)
    : (update.isError ? apiErrorMessage(update.error) : null);

  return (
    <div className="master-data-page users-page" data-testid="users-page">
      <header className="page-intro">
        <div><span className="eyebrow">Identity & access</span><h2>{text("用户管理", "User management")}</h2><p>{text("邀请登录用户，分配角色并关联员工档案；系统会按照权限规则核验每项操作。", "Invite users, assign roles, and link employee records. Oryh checks every action against its access rules.")}</p></div>
      </header>

      {accessNotice && (
        <section
          className={`invitation-result ${accessNotice.tone}`}
          role={accessNotice.tone === "warning" ? "alert" : "status"}
          aria-live="polite"
        >
          <div>
            <span className="eyebrow">{accessNotice.kind === "invitation" ? text("一次性邀请", "One-time invitation") : text("密码重置", "Password reset")}</span>
            <strong>{accessNotice.title}</strong>
            <p>{accessNotice.message}</p>
          </div>
          {accessNotice.url && (
            <div className="invitation-link-row">
              <label className="sr-only" htmlFor="one-time-access-url">
                {accessNotice.kind === "invitation" ? text("一次性邀请链接", "One-time invitation link") : text("一次性重置链接", "One-time reset link")}
              </label>
              <input id="one-time-access-url" readOnly value={accessNotice.url} onFocus={(event) => event.currentTarget.select()} />
              <button className="button" type="button" onClick={() => void copyAccessLink()}>{copyState === "copied" ? text("已复制", "Copied") : text("复制链接", "Copy link")}</button>
            </div>
          )}
          {copyState === "failed" && <p className="copy-error" role="alert">{text("无法自动复制，请手动选择链接。", "Could not copy automatically. Select and copy the link manually.")}</p>}
          <button
            className="notice-close"
            type="button"
            aria-label={accessNotice.kind === "invitation" ? text("关闭邀请结果", "Close invitation result") : text("关闭重置结果", "Close reset result")}
            onClick={() => setAccessNotice(null)}
          >×</button>
        </section>
      )}

      {resend.isError && <div className="form-error list-mutation-error" role="alert">{text("重发失败", "Resend failed")}: {apiErrorMessage(resend.error)}</div>}
      {bundleNotice && !bundleTarget && <section className={`bundle-result ${bundleNotice.tone}`} role={bundleNotice.tone === "warning" ? "alert" : "status"}><span>{bundleNotice.message}</span><button className="notice-close" type="button" aria-label={text("关闭 Skill 包结果", "Close Skill bundle result")} onClick={() => setBundleNotice(null)}>×</button></section>}

      <section className="data-panel" aria-label={text("用户列表", "User list")} aria-busy={users.isFetching}>
        <div className="users-toolbar">
          <form className="users-filter" role="search" onSubmit={applyFilters}>
            <label className="sr-only" htmlFor="user-search">{text("搜索用户", "Search users")}</label>
            <input id="user-search" type="search" value={draftKeyword} placeholder={text("按姓名或邮箱搜索", "Search by name or email")} onChange={(event) => setDraftKeyword(event.target.value)} />
            <label className="sr-only" htmlFor="user-status-filter">{text("用户状态", "User status")}</label>
            <select id="user-status-filter" value={draftStatus} onChange={(event) => setDraftStatus(event.target.value as StatusFilter)}><option value="">{text("全部状态", "All statuses")}</option><option value="invited">{text("待接受邀请", "Invitation pending")}</option><option value="active">{text("已启用", "Active")}</option><option value="disabled">{text("已停用", "Disabled")}</option></select>
            <label className="sr-only" htmlFor="user-role-filter">{text("用户角色", "User role")}</label>
            <select id="user-role-filter" value={draftRole} onChange={(event) => setDraftRole(event.target.value)}><option value="">{text("全部角色", "All roles")}</option>{roleOptions.map((item) => <option key={item.id} value={item.name}>{roleLabel(item, text)}</option>)}</select>
            <button className="button" type="submit">{text("筛选", "Filter")}</button>
            {(keyword || status || role) && <button className="button quiet" type="button" onClick={clearFilters}>{text("清除", "Clear")}</button>}
          </form>
          <button className="button primary" type="button" disabled={oneTimeCredentialPending} onClick={openInvite}>＋ {text("邀请用户", "Invite user")}</button>
        </div>

        <ListState
          loading={users.isPending}
          error={users.isError ? apiErrorMessage(users.error) : null}
          empty={Boolean(result && result.data.length === 0)}
          emptyTitle={keyword || status || role ? text("没有匹配的用户", "No users match") : text("还没有用户", "No users yet")}
          emptyDescription={keyword || status || role ? text("尝试调整姓名、邮箱、状态或角色筛选。", "Try changing the name, email, status, or role filters.") : text("邀请第一位用户加入管理控制台。", "Invite the first user to the workspace console.")}
          onRetry={() => void users.refetch()}
        >
          {result && <>
            <div className="table-scroll"><table className="data-table users-table">
              <thead><tr><th>{text("用户", "User")}</th><th>{text("角色", "Role")}</th><th>{text("关联员工", "Linked employee")}</th><th>{text("状态", "Status")}</th><th aria-label={text("操作", "Actions")} /></tr></thead>
              <tbody>{result.data.map((user) => {
                const linkedEmployee = user.employee_id ? employeeById.get(user.employee_id) : undefined;
                const userRole = roleByName.get(user.role);
                const isSelf = user.id === bootstrap.user.id;
                const canReinvite = user.status === "invited" || (
                  user.status === "disabled" && user.invitation_pending
                );
                return (
                  <tr key={user.id}>
                    <td><div className="user-name"><strong>{user.name || user.email}</strong>{isSelf && <span className="self-badge">{text("当前用户", "Current user")}</span>}</div><small>{user.email}{user.email_verified_at ? ` · ${text("已验证", "Verified")}` : ""}</small></td>
                    <td><strong>{userRole ? roleLabel(userRole, text) : user.role}</strong><small>{text("工作空间角色", "Workspace role")}</small></td>
                    <td>{linkedEmployee ? <><strong>{linkedEmployee.name}</strong><small>{linkedEmployee.employee_code || text("无工号", "No employee ID")}</small></> : user.employee_id ? <span className="mono-cell">{user.employee_id}</span> : <span className="muted-value">{text("未关联", "Not linked")}</span>}</td>
                    <td><UserStatusBadge status={user.status} /></td>
                    <td className="row-actions"><button className="text-action" type="button" onClick={() => openEdit(user)}>{text("编辑", "Edit")}</button>{canReinvite && <button className="text-action" type="button" disabled={oneTimeCredentialPending} onClick={() => resendUserInvitation(user)}>{resend.isPending && resend.variables?.id === user.id ? text("发送中…", "Sending…") : user.status === "invited" ? text("重发邀请", "Resend invitation") : text("恢复邀请", "Restore invitation")}</button>}{user.status === "active" && <button className="text-action" type="button" disabled={oneTimeCredentialPending} onClick={() => openPasswordReset(user)}>{passwordReset.isPending && passwordReset.variables?.id === user.id ? text("发送中…", "Sending…") : text("发送重置邮件", "Send reset email")}</button>}{user.status === "active" && canIssueSkillBundles && <button className="text-action" type="button" onClick={() => { bundle.reset(); setBundleError(null); setBundleNotice(null); setBundleTarget(user); }}>{text("生成 Skill 包", "Generate Skill bundle")}</button>}</td>
                  </tr>
                );
              })}</tbody>
            </table></div>
            <Pagination meta={result.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <Drawer
        open={editing !== undefined}
        title={editing ? text("编辑用户", "Edit user") : text("邀请用户", "Invite user")}
        description={editing ? text(`更新 ${editing.name || editing.email} 的登录身份。`, `Update the sign-in identity for ${editing.name || editing.email}.`) : text("受邀人会收到设置密码的一次性链接。", "The invitee will receive a one-time link to set a password.")}
        submitLabel={editing ? text("保存更改", "Save changes") : text("发送邀请", "Send invitation")}
        busy={invite.isPending || update.isPending}
        submitDisabled={editing === null && oneTimeCredentialPending}
        error={drawerError}
        onClose={closeDrawer}
        onSubmit={submit}
      >
        {(roles.isError || employees.isError || linkedEmployee.isError) && <div className="option-warning" role="alert">{roles.isError ? `${text("角色加载失败", "Could not load roles")}: ${apiErrorMessage(roles.error)}` : ""}{roles.isError && (employees.isError || linkedEmployee.isError) ? text("；", "; ") : ""}{employees.isError ? `${text("员工选项加载失败", "Could not load employee options")}: ${apiErrorMessage(employees.error)}` : linkedEmployee.isError ? `${text("当前员工加载失败", "Could not load the linked employee")}: ${apiErrorMessage(linkedEmployee.error)}` : ""}</div>}
        {isEditingSelf && <div className="self-protection" id="self-edit-note"><strong>{text("正在编辑当前登录用户", "Editing the current user")}</strong><span>{text("为避免锁定自己的管理访问，角色和状态不能在这里修改。", "To avoid locking yourself out of administrative access, role and status cannot be changed here.")}</span></div>}
        <div className="field-grid user-form">
          <div className="field span-2"><label htmlFor="user-email">{text("邮箱", "Email")} <b>*</b></label><input id="user-email" type="email" maxLength={320} required value={form.email} aria-invalid={Boolean(fieldErrors.email)} aria-describedby={fieldErrors.email ? "user-email-error" : undefined} onChange={(event) => updateField("email", event.target.value)} />{fieldErrors.email && <small id="user-email-error" className="field-error" role="alert">{fieldErrors.email}</small>}</div>
          <div className="field span-2"><label htmlFor="user-name">{text("姓名", "Name")}</label><input id="user-name" maxLength={200} value={form.name} aria-invalid={Boolean(fieldErrors.name)} aria-describedby={fieldErrors.name ? "user-name-error" : undefined} onChange={(event) => updateField("name", event.target.value)} />{fieldErrors.name && <small id="user-name-error" className="field-error" role="alert">{fieldErrors.name}</small>}</div>
          <div className="field"><label htmlFor="user-role">{text("角色", "Role")} <b>*</b></label><select id="user-role" value={form.role} disabled={isEditingSelf || roles.isPending || roles.isError} aria-describedby={isEditingSelf ? "self-edit-note" : fieldErrors.role ? "user-role-error" : undefined} aria-invalid={Boolean(fieldErrors.role)} onChange={(event) => updateField("role", event.target.value)}>{!roleNames.has(form.role) && <option value={form.role}>{form.role}</option>}{roleOptions.map((item) => <option key={item.id} value={item.name}>{roleLabel(item, text)}</option>)}</select>{fieldErrors.role && <small id="user-role-error" className="field-error" role="alert">{fieldErrors.role}</small>}</div>
          {editing && <div className="field"><label htmlFor="user-status">{text("状态", "Status")}</label><select id="user-status" value={form.status} disabled={isEditingSelf || (editing.status === "disabled" && editing.invitation_pending)} aria-describedby={isEditingSelf ? "self-edit-note" : undefined} onChange={(event) => updateField("status", event.target.value as UserStatus)}>{editing.status === "invited" ? <><option value="invited" disabled>{text("待接受邀请", "Invitation pending")}</option><option value="disabled">{text("已停用", "Disabled")}</option></> : editing.status === "disabled" && editing.invitation_pending ? <option value="disabled">{text("已停用（未验证）", "Disabled (unverified)")}</option> : <><option value="active">{text("已启用", "Active")}</option><option value="disabled">{text("已停用", "Disabled")}</option></>}</select>{editing.status === "invited" && <small>{text("受邀人只能通过一次性链接激活账号；此处可停用邀请。", "The invitee can activate the account only through the one-time link; you can disable the invitation here.")}</small>}{editing.status === "disabled" && editing.invitation_pending && <small>{text("该账号尚未验证，请从列表中恢复邀请后再激活。", "This account is not verified. Restore its invitation from the list before activating it.")}</small>}</div>}
          <div className="field span-2 employee-option-search"><label htmlFor="user-employee-search">{text("查找员工", "Find employee")}</label><div><input id="user-employee-search" value={employeeSearchDraft} placeholder={text("按员工姓名搜索", "Search by employee name")} onChange={(event) => setEmployeeSearchDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); setEmployeeKeyword(employeeSearchDraft.trim()); } }} /><button className="button compact" type="button" onClick={() => setEmployeeKeyword(employeeSearchDraft.trim())}>{text("搜索员工", "Search employees")}</button>{employeeKeyword && <button className="button quiet compact" type="button" onClick={() => { setEmployeeSearchDraft(""); setEmployeeKeyword(""); }}>{text("清除", "Clear")}</button>}</div><small>{text(`按需显示最多 ${OPTION_PAGE_SIZE} 条匹配结果，避免一次加载全部员工。`, `Shows up to ${OPTION_PAGE_SIZE} matching results at a time.`)}</small></div>
          <div className="field span-2"><label htmlFor="user-employee">{text("关联员工", "Linked employee")}</label><select id="user-employee" value={form.employeeId} disabled={employees.isPending || employees.isError} onChange={(event) => updateField("employeeId", event.target.value)}><option value="">{text("不关联员工", "Do not link an employee")}</option>{form.employeeId && !employeeOptions.some((employee) => employee.id === form.employeeId) && <option value={form.employeeId}>{form.employeeId}</option>}{employeeOptions.map((employee) => <option key={employee.id} value={employee.id}>{employee.name}{employee.employee_code ? ` · ${employee.employee_code}` : ""}{employee.status !== "active" ? text("（停用）", " (inactive)") : ""}</option>)}</select><small>{text("一个员工档案只能关联一个登录用户。", "An employee record can be linked to only one login user.")}</small></div>
        </div>
        {editing && (
          <SkillReachPanel subjectKey={`user:${editing.id}`} fetcher={() => getUserSkillReach(editing.id)} />
        )}
      </Drawer>

      <ConfirmDialog
        open={resetTarget !== null}
        title={text(`向「${resetTarget?.name || resetTarget?.email || "用户"}」发送密码重置邮件？`, `Send a password reset email to “${resetTarget?.name || resetTarget?.email || "user"}”?`)}
        description={text(`系统会生成新的单次重置链接并发送到 ${resetTarget?.email || "该用户邮箱"}。用户完成重置前，当前密码和会话仍有效；完成后旧会话全部失效。再次发送会使上一条重置链接失效。${resetTarget?.id === bootstrap.user.id ? " 这是当前登录账号。" : ""}`, `The system will generate a new one-time reset link and send it to ${resetTarget?.email || "the user's email address"}. The current password and sessions remain valid until the reset is completed; then all old sessions will end. Sending again invalidates the previous reset link.${resetTarget?.id === bootstrap.user.id ? " This is the current account." : ""}`)}
        kicker={text("账号安全", "Account security")}
        confirmLabel={text("发送重置邮件", "Send reset email")}
        busyLabel={text("正在发送…", "Sending…")}
        scrimLabel={text("取消发送重置邮件", "Cancel password reset email")}
        busy={oneTimeCredentialPending}
        error={resetError}
        onCancel={() => { if (!oneTimeCredentialPending) { setResetTarget(null); setResetError(null); } }}
        onConfirm={submitPasswordReset}
      />

      <ConfirmDialog
        open={bundleTarget !== null}
        title={text(`生成「${bundleTarget?.name || bundleTarget?.email || "用户"}」的 Skill 包？`, `Generate a Skill bundle for “${bundleTarget?.name || bundleTarget?.email || "user"}”?`)}
        description={text("这会立即更新该用户的访问凭证，使旧 Skill 包和旧凭证失效；新包将只下载一次。", "This immediately updates the user's access credential, invalidating the old Skill bundle and credential. The new bundle is downloaded only once.")}
        kicker={text("更新访问凭证", "Update access credential")}
        confirmLabel={text("更新凭证并下载", "Update credential and download")}
        busyLabel={text("正在生成…", "Generating…")}
        scrimLabel={text("取消生成 Skill 包", "Cancel Skill bundle generation")}
        busy={bundle.isPending}
        error={bundleError}
        onCancel={() => { if (!bundle.isPending) { setBundleTarget(null); setBundleError(null); } }}
        onConfirm={() => bundleTarget && bundle.mutate(bundleTarget)}
      />
    </div>
  );
}
