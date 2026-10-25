import { zhCN } from "../locales/zh-CN/console";
import { useRecordNotice } from "../components/master-data/RecordNotice";
import { useListFilters } from "../components/master-data/useListFilters";
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

  if (!name) errors.name = text(zhCN.pagesEmployeesPage.nameIsRequired, "Name is required.");
  else if (name.length > 200) errors.name = text(zhCN.pagesEmployeesPage.nameCannotExceed200Characters, "Name cannot exceed 200 characters.");
  if (code.length > 64) errors.code = text(zhCN.pagesEmployeesPage.employeeIDCannotExceed64Characters, "Employee ID cannot exceed 64 characters.");
  if (email && !isValidLoginEmail(email)) errors.email = text(zhCN.pagesEmployeesPage.enterAValidEmailAddress, "Enter a valid email address.");
  if (email.length > 320) errors.email = text(zhCN.pagesEmployeesPage.emailCannotExceed320Characters, "Email cannot exceed 320 characters.");
  if (timezone && !TIMEZONE_PATTERN.test(timezone)) {
    errors.timezone = text(zhCN.pagesEmployeesPage.enterUTCOrAnIANATimeZoneInArea, "Enter UTC or an IANA time zone in Area/Location format, such as Asia/Shanghai.");
  } else if (timezone.length > 100) {
    errors.timezone = text(zhCN.pagesEmployeesPage.timeZoneCannotExceed100Characters, "Time zone cannot exceed 100 characters.");
  }
  return errors;
}

function permissionCovers(permissions: string[], capability: string): boolean {
  return permissions.includes(capability) || permissions.includes(`${capability}:*`);
}

function roleLabel(role: Role, text: Localize): string {
  const systemTitle = role.is_system
    ? ({ admin: text(zhCN.pagesEmployeesPage.administrator, "Administrator"), member: text(zhCN.pagesEmployeesPage.member, "Member") } as Record<string, string>)[role.name]
    : undefined;
  const title = systemTitle ?? role.title;
  return title ? text(`${title}（${role.name}）`, `${title} (${role.name})`) : role.name;
}

function invitationFailureNotice(employee: Employee, error: unknown, text: Localize): CreationNotice {
  const knownRejection = error instanceof ApiError && error.status >= 400 && error.status < 500;
  return knownRejection
    ? {
        tone: "warning",
        title: text(zhCN.pagesEmployeesPage.employeeWasCreatedButTheUserInvitationWasNot(`${employee.name}`), `Employee “${employee.name}” was created, but the user invitation was not completed`),
        message: text(zhCN.pagesEmployeesPage.theEmployeeRecordWasRetainedOpenUserManagementTo(`${apiErrorMessage(error)}`), `${apiErrorMessage(error)}. The employee record was retained. Open user management to correct the issue and retry the invitation.`),
      }
    : {
        tone: "warning",
        title: text(zhCN.pagesEmployeesPage.employeeWasCreatedButTheInvitationOutcomeCouldNot(`${employee.name}`), `Employee “${employee.name}” was created, but the invitation outcome could not be confirmed`),
        message: text(zhCN.pagesEmployeesPage.theRequestMayHaveCreatedAUserCheckUser(`${apiErrorMessage(error)}`), `${apiErrorMessage(error)}. The request may have created a user. Check user management first and resend the invitation if needed.`),
      };
}

export function EmployeesPage() {
  const context = useOutletContext<ConsoleContext | null>();
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const { notice, notify } = useRecordNotice();
  const { keyword, status, page, setPage, applyFilters } = useListFilters<StatusFilter>(["active", "inactive"]);
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
      notify(variables.mode === "create" ? "created" : "saved");
      if (variables.mode === "create") setPage(1);
      if (variables.mode === "create" && variables.createUser) {
        setCopyState("idle");
        if (result.invitationError) {
          setCreationNotice(invitationFailureNotice(result.employee, result.invitationError, text));
        } else if (result.invitation) {
          setCreationNotice({
            tone: "success",
            title: zhCN.pagesEmployeesPage.title(`${text(zhCN.pagesEmployeesPage.employeeAndLoginUserCreated, "Employee and login user created")}`, `${result.invitation.email}`),
            message: result.invitation.invitation_url
              ? text(zhCN.pagesEmployeesPage.theOneTimeInvitationLinkIsShownOnlyIn, "The one-time invitation link is shown only in this response. Send it securely to the employee now.")
              : text(zhCN.pagesEmployeesPage.theInvitationEmailWasSentTheEmployeeCanSign, "The invitation email was sent. The employee can sign in after accepting it."),
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
        invitationError = text(zhCN.pagesEmployeesPage.yourCurrentIdentityDoesNotHaveUsersManageAnd, "Your current identity does not have users.manage and cannot create a login user at the same time.");
      } else if (!form.email.trim()) {
        errors.email = text(zhCN.pagesEmployeesPage.emailIsRequiredWhenCreatingALoginUserAt, "Email is required when creating a login user at the same time.");
      } else if (roles.isPending) {
        invitationError = text(zhCN.pagesEmployeesPage.rolesAreLoadingPleaseWait, "Roles are loading. Please wait.");
      } else if (roles.isError) {
        invitationError = text(zhCN.pagesEmployeesPage.theRoleDirectoryCouldNotBeLoadedRetryOr, "The role directory could not be loaded. Retry or cancel creating the user.");
      } else if (!roles.data?.some((role) => role.name === userRole)) {
        invitationError = text(zhCN.pagesEmployeesPage.selectAValidUserRole, "Select a valid user role.");
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
          <h2>{text(zhCN.pagesEmployeesPage.employeeDirectory, "Employee directory")}</h2>
          <p>{text(zhCN.pagesEmployeesPage.maintainEmployeeIdentitiesEmployeeIDsAndWorkingTimeZones, "Maintain employee identities, employee IDs, and working time zones for timesheets, approvals, and people-linked workflows.")}</p>
        </div>
        <Link className="related-page-link" to="/users">{text(zhCN.pagesEmployeesPage.manageLoginUsersAndInvitations, "Manage login users and invitations")} →</Link>
      </header>
      {notice}

      {creationNotice && (
        <section className={`employee-creation-notice ${creationNotice.tone}`} role={creationNotice.tone === "warning" ? "alert" : "status"}>
          <div>
            <strong>{creationNotice.title}</strong>
            <p>{creationNotice.message}</p>
          </div>
          {creationNotice.invitationUrl && (
            <div className="employee-invitation-link">
              <label className="sr-only" htmlFor="employee-invitation-url">{text(zhCN.pagesEmployeesPage.oneTimeInvitationLink, "One-time invitation link")}</label>
              <input id="employee-invitation-url" readOnly value={creationNotice.invitationUrl} onFocus={(event) => event.currentTarget.select()} />
              <button className="button compact" type="button" onClick={() => void copyInvitation()}>{copyState === "copied" ? text(zhCN.pagesEmployeesPage.copied, "Copied") : text(zhCN.pagesEmployeesPage.copyInvitationLink, "Copy invitation link")}</button>
            </div>
          )}
          {creationNotice.tone === "warning" && <Link className="text-action" to="/users">{text(zhCN.pagesEmployeesPage.openUserManagement, "Open user management")}</Link>}
          {copyState === "failed" && <small className="field-error" role="alert">{text(zhCN.pagesEmployeesPage.theBrowserDidNotAllowAutomaticCopyingSelectAnd, "The browser did not allow automatic copying. Select and copy the link manually.")}</small>}
          <button className="employee-notice-close" type="button" aria-label={text(zhCN.pagesEmployeesPage.closeCreationResult, "Close creation result")} onClick={() => setCreationNotice(null)}>×</button>
        </section>
      )}

      <section className="data-panel" aria-label={text(zhCN.pagesEmployeesPage.employeeList, "Employee list")}>
        <ListToolbar
          keyword={keyword}
          status={status}
          placeholder={text(zhCN.pagesEmployeesPage.searchByEmployeeName, "Search by employee name")}
          createLabel={text(zhCN.pagesEmployeesPage.addEmployee, "Add employee")}
          statusOptions={[
            { value: "active", label: text(zhCN.pagesEmployeesPage.active, "Active") },
            { value: "inactive", label: text(zhCN.pagesEmployeesPage.inactive, "Inactive") },
          ]}
          onCreate={openCreate}
          onApply={applyFilters}
        />

        <ListState
          loading={employees.isPending}
          error={employees.isError ? apiErrorMessage(employees.error) : null}
          empty={Boolean(result && result.data.length === 0)}
          emptyTitle={keyword || status ? text(zhCN.pagesEmployeesPage.noEmployeesMatch, "No employees match") : text(zhCN.pagesEmployeesPage.noEmployeesYet, "No employees yet")}
          emptyDescription={
            keyword || status
              ? text(zhCN.pagesEmployeesPage.tryChangingTheNameOrEmploymentStatusFilters, "Try changing the name or employment status filters.")
              : text(zhCN.pagesEmployeesPage.addTheFirstEmployeeToStartLinkingLoginUsers, "Add the first employee to start linking login users and business records.")
          }
          onRetry={() => void employees.refetch()}
        >
          {result && (
            <>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{text(zhCN.pagesEmployeesPage.employee, "Employee")}</th>
                      <th>{text(zhCN.pagesEmployeesPage.email, "Email")}</th>
                      <th>{text(zhCN.pagesEmployeesPage.workingTimeZone, "Working time zone")}</th>
                      <th>{text(zhCN.pagesEmployeesPage.status, "Status")}</th>
                      <th><span className="sr-only">{text(zhCN.pagesEmployeesPage.actions, "Actions")}</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.data.map((employee) => (
                      <tr key={employee.id}>
                        <td>
                          <button className="record-name" type="button" onClick={() => openEdit(employee)}>{employee.name}</button>
                          <small>{employee.employee_code || text(zhCN.pagesEmployeesPage.noEmployeeID, "No employee ID")}</small>
                        </td>
                        <td>{employee.email || <span className="muted-value">—</span>}</td>
                        <td className="mono-cell">
                          {employee.timezone || <span className="muted-value">{text(zhCN.pagesEmployeesPage.notSet, "Not set")}</span>}
                        </td>
                        <td><StatusBadge status={employee.status} /></td>
                        <td className="row-actions">
                          <button className="text-action" type="button" onClick={() => openEdit(employee)}>
                            {text(zhCN.pagesEmployeesPage.edit, "Edit")}
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
        title={editing ? text(zhCN.pagesEmployeesPage.editEmployee, "Edit employee") : text(zhCN.pagesEmployeesPage.addEmployee, "Add employee")}
        description={editing ? text(zhCN.pagesEmployeesPage.updateTheEmployeeRecordFor(`${editing.name}`), `Update the employee record for ${editing.name}.`) : createUser ? text(zhCN.pagesEmployeesPage.createAnEmployeeRecordAndSendAnInvitationFor, "Create an employee record and send an invitation for its linked login user.") : text(zhCN.pagesEmployeesPage.createAnEmployeeRecordALoginUserCanBe, "Create an employee record; a login user can be linked later.")}
        submitLabel={editing ? text(zhCN.pagesEmployeesPage.saveChanges, "Save changes") : createUser ? text(zhCN.pagesEmployeesPage.addEmployeeAndInvite, "Add employee and invite") : text(zhCN.pagesEmployeesPage.addEmployee, "Add employee")}
        busy={save.isPending}
        submitDisabled={!editing && createUser && (roles.isPending || roles.isError || !roles.data?.length)}
        error={inviteValidation || (save.isError ? apiErrorMessage(save.error) : null)}
        onClose={closeDrawer}
        onSubmit={submit}
      >
        <div className="field-grid employee-form">
          <div className="field span-2">
            <label htmlFor="employee-name">{text(zhCN.pagesEmployeesPage.name, "Name")} <b>*</b></label>
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
            <label htmlFor="employee-code">{text(zhCN.pagesEmployeesPage.employeeID, "Employee ID")}</label>
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
            <label htmlFor="employee-status">{text(zhCN.pagesEmployeesPage.status, "Status")}</label>
            <select
              id="employee-status"
              value={form.status}
              disabled={!editing && createUser}
              onChange={(event) => updateField("status", event.target.value as EmployeeStatus)}
            >
              <option value="active">{text(zhCN.pagesEmployeesPage.active, "Active")}</option>
              <option value="inactive">{text(zhCN.pagesEmployeesPage.inactive, "Inactive")}</option>
            </select>
            {!editing && createUser && <small>{text(zhCN.pagesEmployeesPage.theEmployeeRecordMustRemainActiveWhenCreatingA, "The employee record must remain active when creating a login user.")}</small>}
          </div>

          <div className="field span-2">
            <label htmlFor="employee-email">{text(zhCN.pagesEmployeesPage.email, "Email")} {createUser && <b>*</b>}</label>
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
            <label htmlFor="employee-timezone">{text(zhCN.pagesEmployeesPage.workingTimeZone, "Working time zone")}</label>
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
              <small id="employee-timezone-hint">{text(zhCN.pagesEmployeesPage.enterUTCOrAnIANARegionalTimeZone, "Enter UTC or an IANA regional time zone.")}</small>
            )}
          </div>

          {!editing && canCreateUsers && (
            <section className={`employee-user-option span-2 ${createUser ? "selected" : ""}`}>
              <label className="employee-user-toggle" htmlFor="employee-create-user">
                <input
                  id="employee-create-user"
                  type="checkbox"
                  aria-label={text(zhCN.pagesEmployeesPage.createALoginUserAtTheSameTime, "Create a login user at the same time")}
                  aria-describedby="employee-create-user-hint"
                  checked={createUser}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setCreateUser(checked);
                    setInviteValidation(null);
                    if (checked) updateField("status", "active");
                  }}
                />
                <span><strong>{text(zhCN.pagesEmployeesPage.createALoginUserAtTheSameTime, "Create a login user at the same time")}</strong><small id="employee-create-user-hint">{text(zhCN.pagesEmployeesPage.useTheSameNameAndEmailToCreateA, "Use the same name and email to create a linked user and send a one-time invitation.")}</small></span>
              </label>
              {createUser && (
                <div className="employee-user-role">
                  <label htmlFor="employee-user-role">{text(zhCN.pagesEmployeesPage.userRole, "User role")}</label>
                  <select
                    id="employee-user-role"
                    value={userRole}
                    disabled={roles.isPending || roles.isError}
                    onChange={(event) => { setUserRole(event.target.value); setInviteValidation(null); }}
                  >
                    {roles.data?.map((role) => <option key={role.id} value={role.name}>{roleLabel(role, text)}</option>)}
                  </select>
                  {roles.isPending && <small>{text(zhCN.pagesEmployeesPage.loadingAvailableRoles, "Loading available roles…")}</small>}
                  {roles.isError && (
                    <div className="employee-user-role-recovery">
                      <small className="field-error">{text(zhCN.pagesEmployeesPage.rolesCouldNotBeLoadedYouCanClearThe, "Roles could not be loaded. You can clear the checkbox to create only the employee.")}</small>
                      <button className="text-action" type="button" disabled={roles.isFetching} onClick={() => void roles.refetch()}>
                        {roles.isFetching ? text(zhCN.pagesEmployeesPage.retrying, "Retrying…") : text(zhCN.pagesEmployeesPage.retryLoadingRoles, "Retry loading roles")}
                      </button>
                    </div>
                  )}
                  {!roles.isPending && !roles.isError && roles.data?.length === 0 && (
                    <small className="field-error">{text(zhCN.pagesEmployeesPage.thisWorkspaceHasNoAvailableRolesClearTheCheckbox, "This workspace has no available roles. Clear the checkbox to create only the employee.")}</small>
                  )}
                  {!roles.isPending && !roles.isError && Boolean(roles.data?.length) && (
                    <small>{text(zhCN.pagesEmployeesPage.afterAcceptingTheInvitationTheEmployeeEntersTheWorkspace, "After accepting the invitation, the employee enters the workspace console with the selected role.")}</small>
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
