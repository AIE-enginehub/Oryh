import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useOutletContext } from "react-router-dom";

import type { ConsoleContext } from "../App";
import {
  ApiError,
  createEmployee,
  inviteUser,
  listEmployees,
  listRoles,
  updateEmployee,
  type CreateEmployeeInput,
  type Employee,
  type InvitationUser,
  type Role,
} from "../api/client";
import { Drawer } from "../components/master-data/Drawer";
import { apiErrorMessage, ListState, StatusBadge } from "../components/master-data/ListState";
import { ListToolbar } from "../components/master-data/ListToolbar";
import { Pagination } from "../components/master-data/Pagination";
import { useI18n } from "../i18n";
import "./employees.css";

const PAGE_SIZE = 20;
const TIMEZONE_PATTERN = /^(?:UTC|[A-Za-z_+-]+(?:\/[A-Za-z0-9._+-]+)+)$/;

type EmployeeStatus = "active" | "inactive";
type StatusFilter = "" | EmployeeStatus;
type EmployeeForm = {
  name: string;
  code: string;
  email: string;
  timezone: string;
  status: EmployeeStatus;
};
type EmployeeFieldErrors = Partial<Record<keyof EmployeeForm, string>>;
type EmployeeSaveVariables =
  | { mode: "create"; input: CreateEmployeeInput; createUser: boolean; role: string }
  | { mode: "update"; id: string; input: CreateEmployeeInput };
type EmployeeSaveResult = {
  employee: Employee;
  invitation?: InvitationUser;
  invitationError?: unknown;
};
type CreationNotice = {
  tone: "success" | "warning";
  title: string;
  message: string;
  invitationUrl?: string | null;
};
type Localize = (chinese: string, english: string) => string;

const commonTimezones = [
  "UTC",
  "Asia/Shanghai",
  "Asia/Hong_Kong",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Europe/London",
  "Europe/Paris",
  "America/New_York",
  "America/Los_Angeles",
];

function newEmployeeForm(): EmployeeForm {
  return { name: "", code: "", email: "", timezone: "", status: "active" };
}

function employeeForm(employee?: Employee): EmployeeForm {
  if (!employee) return newEmployeeForm();
  return {
    name: employee.name,
    code: employee.employee_code ?? "",
    email: employee.email ?? "",
    timezone: employee.timezone ?? "",
    status: employee.status,
  };
}

function isValidLoginEmail(value: string): boolean {
  if (/\s/.test(value)) return false;
  const separator = value.lastIndexOf("@");
  if (separator <= 0 || separator !== value.indexOf("@")) return false;
  const domain = value.slice(separator + 1);
  return domain.includes(".") && !domain.startsWith(".") && !domain.endsWith(".");
}

function validateEmployee(form: EmployeeForm, text: Localize): EmployeeFieldErrors {
  const errors: EmployeeFieldErrors = {};
  const name = form.name.trim();
  const code = form.code.trim();
  const email = form.email.trim();
  const timezone = form.timezone.trim();

  if (!name) errors.name = text("姓名不能为空。", "Name is required.");
  else if (name.length > 200) errors.name = text("姓名不能超过 200 个字符。", "Name cannot exceed 200 characters.");
  if (code.length > 64) errors.code = text("工号不能超过 64 个字符。", "Employee ID cannot exceed 64 characters.");
  if (email && !isValidLoginEmail(email)) errors.email = text("请输入有效的邮箱地址。", "Enter a valid email address.");
  if (email.length > 320) errors.email = text("邮箱不能超过 320 个字符。", "Email cannot exceed 320 characters.");
  if (timezone && !TIMEZONE_PATTERN.test(timezone)) {
    errors.timezone = text("请输入 UTC 或 Area/Location 格式的 IANA 时区，例如 Asia/Shanghai。", "Enter UTC or an IANA time zone in Area/Location format, such as Asia/Shanghai.");
  } else if (timezone.length > 100) {
    errors.timezone = text("时区不能超过 100 个字符。", "Time zone cannot exceed 100 characters.");
  }
  return errors;
}

function permissionCovers(permissions: string[], capability: string): boolean {
  return permissions.includes(capability) || permissions.includes(`${capability}:*`);
}

function roleLabel(role: Role, text: Localize): string {
  const systemTitle = role.is_system
    ? ({ admin: text("管理员", "Administrator"), member: text("成员", "Member") } as Record<string, string>)[role.name]
    : undefined;
  const title = systemTitle ?? role.title;
  return title ? text(`${title}（${role.name}）`, `${title} (${role.name})`) : role.name;
}

function invitationFailureNotice(employee: Employee, error: unknown, text: Localize): CreationNotice {
  const knownRejection = error instanceof ApiError && error.status >= 400 && error.status < 500;
  return knownRejection
    ? {
        tone: "warning",
        title: text(`员工「${employee.name}」已创建，用户邀请未完成`, `Employee “${employee.name}” was created, but the user invitation was not completed`),
        message: text(`${apiErrorMessage(error)}。员工档案已保留，可前往用户管理修正后重试邀请。`, `${apiErrorMessage(error)}. The employee record was retained. Open user management to correct the issue and retry the invitation.`),
      }
    : {
        tone: "warning",
        title: text(`员工「${employee.name}」已创建，用户邀请结果未能确认`, `Employee “${employee.name}” was created, but the invitation outcome could not be confirmed`),
        message: text(`${apiErrorMessage(error)}。请求可能已创建用户，请先前往用户管理核对，必要时重发邀请。`, `${apiErrorMessage(error)}. The request may have created a user. Check user management first and resend the invitation if needed.`),
      };
}

export function EmployeesPage() {
  const context = useOutletContext<ConsoleContext | null>();
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Employee | null | undefined>(undefined);
  const [form, setForm] = useState<EmployeeForm>(newEmployeeForm);
  const [fieldErrors, setFieldErrors] = useState<EmployeeFieldErrors>({});
  const [createUser, setCreateUser] = useState(false);
  const [userRole, setUserRole] = useState("member");
  const [inviteValidation, setInviteValidation] = useState<string | null>(null);
  const [creationNotice, setCreationNotice] = useState<CreationNotice | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  const canCreateUsers = Boolean(
    context?.bootstrap && permissionCovers(context.bootstrap.permissions, "users.manage"),
  );

  const employees = useQuery({
    queryKey: ["employees", { keyword, status, page }],
    queryFn: () => listEmployees({
      page,
      size: PAGE_SIZE,
      keyword: keyword || undefined,
      status: status || undefined,
    }),
    placeholderData: keepPreviousData,
  });
  const roles = useQuery({
    queryKey: ["roles", "employee-create-options"],
    queryFn: listRoles,
    enabled: editing === null && createUser && canCreateUsers,
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    if (!roles.data || roles.data.length === 0) return;
    if (roles.data.some((role) => role.name === userRole)) return;
    const fallback = roles.data.find((role) => role.name === "member") ?? roles.data[0];
    setUserRole(fallback.name);
  }, [roles.data, userRole]);

  const save = useMutation({
    mutationFn: async (variables: EmployeeSaveVariables): Promise<EmployeeSaveResult> => {
      if (variables.mode === "update") {
        return { employee: await updateEmployee(variables.id, variables.input) };
      }
      const employee = await createEmployee(variables.input);
      if (!variables.createUser) return { employee };
      try {
        const invitation = await inviteUser({
          email: employee.email ?? variables.input.email ?? "",
          name: employee.name,
          role: variables.role,
          employee_id: employee.id,
        });
        return { employee, invitation };
      } catch (invitationError) {
        return { employee, invitationError };
      }
    },
    onSuccess: async (result, variables) => {
      setEditing(undefined);
      if (variables.mode === "create") setPage(1);
      if (variables.mode === "create" && variables.createUser) {
        setCopyState("idle");
        if (result.invitationError) {
          setCreationNotice(invitationFailureNotice(result.employee, result.invitationError, text));
        } else if (result.invitation) {
          setCreationNotice({
            tone: "success",
            title: `${text("员工与登录用户已创建", "Employee and login user created")} · ${result.invitation.email}`,
            message: result.invitation.invitation_url
              ? text("一次性邀请链接仅在本次响应中显示，请立即安全发送给员工。", "The one-time invitation link is shown only in this response. Send it securely to the employee now.")
              : text("邀请邮件已发送；员工接受邀请后即可登录。", "The invitation email was sent. The employee can sign in after accepting it."),
            invitationUrl: result.invitation.invitation_url,
          });
        }
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["employees"] }),
        ...(variables.mode === "create" && variables.createUser
          ? [queryClient.invalidateQueries({ queryKey: ["users"] })]
          : []),
      ]);
    },
  });

  const result = employees.data;
  const availablePages = result?.meta.pages;
  useEffect(() => {
    if (availablePages !== undefined && page > availablePages) {
      setPage(Math.max(availablePages, 1));
    }
  }, [availablePages, page]);

  const updateField = <Field extends keyof EmployeeForm>(
    field: Field,
    value: EmployeeForm[Field],
  ) => {
    setForm((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => {
      if (!current[field]) return current;
      const next = { ...current };
      delete next[field];
      return next;
    });
  };

  const openCreate = () => {
    setForm(newEmployeeForm());
    setEditing(null);
    setFieldErrors({});
    setCreateUser(false);
    setUserRole("member");
    setInviteValidation(null);
    save.reset();
  };

  const openEdit = (employee: Employee) => {
    setForm(employeeForm(employee));
    setEditing(employee);
    setFieldErrors({});
    setCreateUser(false);
    setInviteValidation(null);
    save.reset();
  };

  const closeDrawer = () => {
    if (!save.isPending) setEditing(undefined);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const errors = validateEmployee(form, text);
    let invitationError: string | null = null;
    if (!editing && createUser) {
      if (!canCreateUsers) {
        invitationError = text("当前身份缺少 users.manage，不能同时创建登录用户。", "Your current identity does not have users.manage and cannot create a login user at the same time.");
      } else if (!form.email.trim()) {
        errors.email = text("同时创建登录用户时必须填写邮箱。", "Email is required when creating a login user at the same time.");
      } else if (roles.isPending) {
        invitationError = text("正在加载角色，请稍候。", "Roles are loading. Please wait.");
      } else if (roles.isError) {
        invitationError = text("角色目录加载失败，请重试或取消同时创建用户。", "The role directory could not be loaded. Retry or cancel creating the user.");
      } else if (!roles.data?.some((role) => role.name === userRole)) {
        invitationError = text("请选择有效的用户角色。", "Select a valid user role.");
      }
    }
    setFieldErrors(errors);
    setInviteValidation(invitationError);
    if (Object.keys(errors).length > 0 || invitationError) return;

    const input: CreateEmployeeInput = {
      name: form.name.trim(),
      employee_code: form.code.trim() || null,
      email: form.email.trim() || null,
      timezone: form.timezone.trim() || null,
      status: form.status,
    };
    if (editing) {
      save.mutate({ mode: "update", id: editing.id, input });
    } else {
      save.mutate({ mode: "create", input, createUser, role: userRole });
    }
  };

  const copyInvitation = async () => {
    if (!creationNotice?.invitationUrl) return;
    try {
      await navigator.clipboard.writeText(creationNotice.invitationUrl);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  };

  return (
    <div className="master-data-page employee-page" data-testid="employees-page">
      <header className="page-intro">
        <div>
          <span className="eyebrow">Employee directory</span>
          <h2>{text("员工档案", "Employee directory")}</h2>
          <p>{text("维护员工身份、工号和工作时区，供工时、审批及人员关联流程使用。", "Maintain employee identities, employee IDs, and working time zones for timesheets, approvals, and people-linked workflows.")}</p>
        </div>
        <Link className="related-page-link" to="/users">{text("管理登录用户与邀请", "Manage login users and invitations")} →</Link>
      </header>

      {creationNotice && (
        <section className={`employee-creation-notice ${creationNotice.tone}`} role={creationNotice.tone === "warning" ? "alert" : "status"}>
          <div>
            <strong>{creationNotice.title}</strong>
            <p>{creationNotice.message}</p>
          </div>
          {creationNotice.invitationUrl && (
            <div className="employee-invitation-link">
              <label className="sr-only" htmlFor="employee-invitation-url">{text("一次性邀请链接", "One-time invitation link")}</label>
              <input id="employee-invitation-url" readOnly value={creationNotice.invitationUrl} onFocus={(event) => event.currentTarget.select()} />
              <button className="button compact" type="button" onClick={() => void copyInvitation()}>{copyState === "copied" ? text("已复制", "Copied") : text("复制邀请链接", "Copy invitation link")}</button>
            </div>
          )}
          {creationNotice.tone === "warning" && <Link className="text-action" to="/users">{text("前往用户管理", "Open user management")}</Link>}
          {copyState === "failed" && <small className="field-error" role="alert">{text("浏览器未允许自动复制，请手动选择链接。", "The browser did not allow automatic copying. Select and copy the link manually.")}</small>}
          <button className="employee-notice-close" type="button" aria-label={text("关闭创建结果", "Close creation result")} onClick={() => setCreationNotice(null)}>×</button>
        </section>
      )}

      <section className="data-panel" aria-label={text("员工列表", "Employee list")}>
        <ListToolbar
          keyword={keyword}
          status={status}
          placeholder={text("按员工姓名搜索", "Search by employee name")}
          createLabel={text("新增员工", "Add employee")}
          statusOptions={[
            { value: "active", label: text("在职", "Active") },
            { value: "inactive", label: text("停用", "Inactive") },
          ]}
          onCreate={openCreate}
          onApply={(filters) => {
            setKeyword(filters.keyword);
            setStatus(filters.status as StatusFilter);
            setPage(1);
          }}
        />

        <ListState
          loading={employees.isPending}
          error={employees.isError ? apiErrorMessage(employees.error) : null}
          empty={Boolean(result && result.data.length === 0)}
          emptyTitle={keyword || status ? text("没有匹配的员工", "No employees match") : text("还没有员工", "No employees yet")}
          emptyDescription={
            keyword || status
              ? text("尝试调整姓名或在职状态筛选。", "Try changing the name or employment status filters.")
              : text("新增第一位员工，开始关联登录用户和业务记录。", "Add the first employee to start linking login users and business records.")
          }
          onRetry={() => void employees.refetch()}
        >
          {result && (
            <>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{text("员工", "Employee")}</th>
                      <th>{text("邮箱", "Email")}</th>
                      <th>{text("工作时区", "Working time zone")}</th>
                      <th>{text("状态", "Status")}</th>
                      <th><span className="sr-only">{text("操作", "Actions")}</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.data.map((employee) => (
                      <tr key={employee.id}>
                        <td>
                          <strong>{employee.name}</strong>
                          <small>{employee.employee_code || text("未设置工号", "No employee ID")}</small>
                        </td>
                        <td>{employee.email || <span className="muted-value">—</span>}</td>
                        <td className="mono-cell">
                          {employee.timezone || <span className="muted-value">{text("未设置", "Not set")}</span>}
                        </td>
                        <td><StatusBadge status={employee.status} /></td>
                        <td className="row-actions">
                          <button className="text-action" type="button" onClick={() => openEdit(employee)}>
                            {text("编辑", "Edit")}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination meta={result.meta} onPageChange={setPage} />
            </>
          )}
        </ListState>
      </section>

      <Drawer
        open={editing !== undefined}
        title={editing ? text("编辑员工", "Edit employee") : text("新增员工", "Add employee")}
        description={editing ? text(`更新 ${editing.name} 的员工档案。`, `Update the employee record for ${editing.name}.`) : createUser ? text("一次创建员工档案，并发送关联登录用户的邀请。", "Create an employee record and send an invitation for its linked login user.") : text("创建员工档案；登录用户可稍后关联。", "Create an employee record; a login user can be linked later.")}
        submitLabel={editing ? text("保存更改", "Save changes") : createUser ? text("新增员工并邀请", "Add employee and invite") : text("新增员工", "Add employee")}
        busy={save.isPending}
        submitDisabled={!editing && createUser && (roles.isPending || roles.isError || !roles.data?.length)}
        error={inviteValidation || (save.isError ? apiErrorMessage(save.error) : null)}
        onClose={closeDrawer}
        onSubmit={submit}
      >
        <div className="field-grid employee-form">
          <div className="field span-2">
            <label htmlFor="employee-name">{text("姓名", "Name")} <b>*</b></label>
            <input
              id="employee-name"
              required
              maxLength={200}
              value={form.name}
              aria-invalid={Boolean(fieldErrors.name)}
              aria-describedby={fieldErrors.name ? "employee-name-error" : undefined}
              onChange={(event) => updateField("name", event.target.value)}
            />
            {fieldErrors.name && <small id="employee-name-error" className="field-error" role="alert">{fieldErrors.name}</small>}
          </div>

          <div className="field">
            <label htmlFor="employee-code">{text("工号", "Employee ID")}</label>
            <input
              id="employee-code"
              maxLength={64}
              value={form.code}
              aria-invalid={Boolean(fieldErrors.code)}
              aria-describedby={fieldErrors.code ? "employee-code-error" : undefined}
              onChange={(event) => updateField("code", event.target.value)}
            />
            {fieldErrors.code && <small id="employee-code-error" className="field-error" role="alert">{fieldErrors.code}</small>}
          </div>

          <div className="field">
            <label htmlFor="employee-status">{text("状态", "Status")}</label>
            <select
              id="employee-status"
              value={form.status}
              disabled={!editing && createUser}
              onChange={(event) => updateField("status", event.target.value as EmployeeStatus)}
            >
              <option value="active">{text("在职", "Active")}</option>
              <option value="inactive">{text("停用", "Inactive")}</option>
            </select>
            {!editing && createUser && <small>{text("创建登录用户时，员工档案必须保持在职。", "The employee record must remain active when creating a login user.")}</small>}
          </div>

          <div className="field span-2">
            <label htmlFor="employee-email">{text("邮箱", "Email")} {createUser && <b>*</b>}</label>
            <input
              id="employee-email"
              type="email"
              maxLength={320}
              required={createUser}
              value={form.email}
              aria-invalid={Boolean(fieldErrors.email)}
              aria-describedby={fieldErrors.email ? "employee-email-error" : undefined}
              onChange={(event) => updateField("email", event.target.value)}
            />
            {fieldErrors.email && <small id="employee-email-error" className="field-error" role="alert">{fieldErrors.email}</small>}
          </div>

          <div className="field span-2">
            <label htmlFor="employee-timezone">{text("工作时区", "Working time zone")}</label>
            <input
              id="employee-timezone"
              list="employee-timezones"
              maxLength={100}
              placeholder="Asia/Shanghai"
              value={form.timezone}
              aria-invalid={Boolean(fieldErrors.timezone)}
              aria-describedby={fieldErrors.timezone ? "employee-timezone-error" : "employee-timezone-hint"}
              onChange={(event) => updateField("timezone", event.target.value)}
            />
            <datalist id="employee-timezones">
              {commonTimezones.map((timezone) => <option key={timezone} value={timezone} />)}
            </datalist>
            {fieldErrors.timezone ? (
              <small id="employee-timezone-error" className="field-error" role="alert">{fieldErrors.timezone}</small>
            ) : (
              <small id="employee-timezone-hint">{text("可输入 UTC 或 IANA 区域时区。", "Enter UTC or an IANA regional time zone.")}</small>
            )}
          </div>

          {!editing && canCreateUsers && (
            <section className={`employee-user-option span-2 ${createUser ? "selected" : ""}`}>
              <label className="employee-user-toggle" htmlFor="employee-create-user">
                <input
                  id="employee-create-user"
                  type="checkbox"
                  aria-label={text("同时创建登录用户", "Create a login user at the same time")}
                  aria-describedby="employee-create-user-hint"
                  checked={createUser}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setCreateUser(checked);
                    setInviteValidation(null);
                    if (checked) updateField("status", "active");
                  }}
                />
                <span><strong>{text("同时创建登录用户", "Create a login user at the same time")}</strong><small id="employee-create-user-hint">{text("使用同一姓名和邮箱，创建关联用户并发送一次性邀请。", "Use the same name and email to create a linked user and send a one-time invitation.")}</small></span>
              </label>
              {createUser && (
                <div className="employee-user-role">
                  <label htmlFor="employee-user-role">{text("用户角色", "User role")}</label>
                  <select
                    id="employee-user-role"
                    value={userRole}
                    disabled={roles.isPending || roles.isError}
                    onChange={(event) => { setUserRole(event.target.value); setInviteValidation(null); }}
                  >
                    {roles.data?.map((role) => <option key={role.id} value={role.name}>{roleLabel(role, text)}</option>)}
                  </select>
                  {roles.isPending && <small>{text("正在加载可用角色…", "Loading available roles…")}</small>}
                  {roles.isError && (
                    <div className="employee-user-role-recovery">
                      <small className="field-error">{text("角色加载失败；也可取消勾选，只创建员工。", "Roles could not be loaded. You can clear the checkbox to create only the employee.")}</small>
                      <button className="text-action" type="button" disabled={roles.isFetching} onClick={() => void roles.refetch()}>
                        {roles.isFetching ? text("正在重试…", "Retrying…") : text("重试加载角色", "Retry loading roles")}
                      </button>
                    </div>
                  )}
                  {!roles.isPending && !roles.isError && roles.data?.length === 0 && (
                    <small className="field-error">{text("当前工作空间没有可用角色；取消勾选后仍可只创建员工。", "This workspace has no available roles. Clear the checkbox to create only the employee.")}</small>
                  )}
                  {!roles.isPending && !roles.isError && Boolean(roles.data?.length) && (
                    <small>{text("员工接受邀请后，以所选角色进入管理控制台。", "After accepting the invitation, the employee enters the workspace console with the selected role.")}</small>
                  )}
                </div>
              )}
            </section>
          )}
        </div>
      </Drawer>
    </div>
  );
}
