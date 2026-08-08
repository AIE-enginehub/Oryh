import type { Capability } from "../../api/client";
import { useI18n } from "../../i18n";

type PermissionMatrixProps = {
  capabilities: Capability[];
  objectTypes: string[];
  permissions: string[];
  lockAdminUsersManage: boolean;
  onChange: (permissions: string[]) => void;
};

const systemCapabilityEnglish: Record<string, { title: string; description: string }> = {
  "timesheet.submit_own": { title: "Submit own timesheets", description: "Create, edit, submit, and resubmit your own timesheets" },
  "timesheet.advance": { title: "Advance timesheet status", description: "Move timesheets through workflow states, including final approval and return" },
  "expense.submit_own": { title: "Submit own expenses", description: "Create, edit, submit, and resubmit your own expense claims, including receipt uploads" },
  "expense.advance": { title: "Advance expense status", description: "Move expense claims through workflow states, including final approval, return, and payment marking" },
  "purchase.submit_own": { title: "Submit own purchase requests", description: "Create, edit, submit, and resubmit your own purchase requests" },
  "purchase.advance": { title: "Advance purchase request status", description: "Move purchase requests through workflow states, including final approval, return, and order marking" },
  "business_object.write": { title: "Create/edit business objects", description: "Scoped by object type; includes links, soft deletion, and restoration" },
  "business_object.advance": { title: "Advance business object status", description: "Move business objects through workflow states within assigned object-type scopes" },
  "business_object.summarize": { title: "Summarize business objects", description: "Gate distribution of summary Skills by object-type scope; reading business objects itself is not restricted by this grant" },
  "approval.record": { title: "Record approval facts", description: "Write approval records such as approved, rejected, returned, or commented" },
  "todos.assign": { title: "Assign to-dos to others", description: "Create to-dos assigned to any employee" },
  "todos.complete_own": { title: "Complete own to-dos", description: "Complete to-dos assigned to yourself" },
  "booking.own": { title: "Book resources", description: "Create, update, or cancel resource bookings on your own behalf" },
  "master_data.manage": { title: "Manage master data", description: "Create, edit, and archive workspace master data such as projects, vendors, products, SKUs, and resources" },
  "employees.manage": { title: "Manage employees", description: "Create and maintain employee records" },
  "users.manage": { title: "Manage users and roles", description: "Invite users, assign roles, and manage roles and custom capabilities" },
  "keys.manage": { title: "Manage access credentials", description: "Issue, view, and disable workspace and personal access credentials" },
  "object_types.manage": { title: "Manage object types", description: "Define object fields and status flows" },
  "workflows.publish": { title: "Publish workflows", description: "Publish new workflow definition versions" },
  "skills.manage": { title: "Manage Skills", description: "Create, revise, and archive workspace Skills" },
  "tenant.act_for_any_employee": { title: "Act for any employee", description: "Override self-only restrictions to operate records on behalf of any employee" },
};

function sortedPermissions(values: Set<string>): string[] {
  return Array.from(values).sort((left, right) => left.localeCompare(right));
}

export function PermissionMatrix({
  capabilities,
  objectTypes,
  permissions,
  lockAdminUsersManage,
  onChange,
}: PermissionMatrixProps) {
  const { text } = useI18n();
  const grants = new Set(permissions);
  const systemCapabilities = capabilities.filter((capability) => capability.kind === "system");
  const simpleCapabilities = systemCapabilities.filter((capability) => !capability.scopable);
  const scopedCapabilities = systemCapabilities.filter((capability) => capability.scopable);
  const customCapabilities = capabilities.filter((capability) => capability.kind === "custom");
  const capabilityTitle = (capability: Capability) => capability.kind === "system"
    ? text(capability.title || capability.name, systemCapabilityEnglish[capability.name]?.title ?? capability.name)
    : capability.title || capability.name;
  const capabilityDescription = (capability: Capability) => capability.kind === "system"
    ? text(capability.description || "", systemCapabilityEnglish[capability.name]?.description ?? capability.description ?? "")
    : capability.description;

  const toggleGrant = (grant: string, checked: boolean) => {
    if (lockAdminUsersManage && grant === "users.manage") return;
    const next = new Set(grants);
    if (checked) next.add(grant);
    else next.delete(grant);
    onChange(sortedPermissions(next));
  };

  const toggleAllScopes = (verb: string, checked: boolean) => {
    const next = new Set(grants);
    for (const grant of next) {
      if (grant === verb || grant.startsWith(`${verb}:`)) next.delete(grant);
    }
    if (checked) next.add(`${verb}:*`);
    onChange(sortedPermissions(next));
  };

  const knownGrants = new Set<string>();
  for (const capability of simpleCapabilities) knownGrants.add(capability.name);
  for (const capability of customCapabilities) knownGrants.add(capability.name);
  for (const capability of scopedCapabilities) {
    // A bare scopable verb is a legacy/global grant with the same effective
    // coverage as verb:*; keep it in the matrix instead of treating it as an
    // unknown permission.
    knownGrants.add(capability.name);
    knownGrants.add(`${capability.name}:*`);
    for (const objectType of objectTypes) knownGrants.add(`${capability.name}:${objectType}`);
  }
  const retainedGrants = permissions.filter((grant) => !knownGrants.has(grant));

  return (
    <div className="permission-matrix">
      <section className="permission-section" aria-labelledby="system-capabilities-title">
        <div className="permission-heading">
          <div>
            <h3 id="system-capabilities-title">{text("系统能力", "System capabilities")}</h3>
            <p>{text("控制 Oryh 中各项业务操作的访问权限。", "Control access to business operations in Oryh.")}</p>
          </div>
          <span>{simpleCapabilities.length}</span>
        </div>
        {simpleCapabilities.length === 0 ? (
          <div className="permission-empty">{text("暂无非作用域系统能力。", "No unscoped system capabilities.")}</div>
        ) : (
          <div className="permission-checks">
            {simpleCapabilities.map((capability) => {
              const locked = lockAdminUsersManage && capability.name === "users.manage";
              return (
                <label className={`permission-check ${locked ? "locked" : ""}`} key={capability.id}>
                  <input
                    type="checkbox"
                    checked={locked || grants.has(capability.name)}
                    disabled={locked}
                    onChange={(event) => toggleGrant(capability.name, event.target.checked)}
                  />
                  <span>
                    <strong>{capabilityTitle(capability)}</strong>
                    <code>{capability.name}</code>
                    {capabilityDescription(capability) && <small>{capabilityDescription(capability)}</small>}
                    {locked && <small className="lock-note">{text("管理员锁定保护，不能移除", "Protected for the administrator role and cannot be removed")}</small>}
                  </span>
                </label>
              );
            })}
          </div>
        )}
      </section>

      <section className="permission-section" aria-labelledby="scoped-capabilities-title">
        <div className="permission-heading">
          <div>
            <h3 id="scoped-capabilities-title">{text("作用域能力", "Scoped capabilities")}</h3>
            <p>{text("授予全部对象类型，或仅授予指定 object_type。", "Grant access to all object types or only selected object_type values.")}</p>
          </div>
          <span>{scopedCapabilities.length}</span>
        </div>
        {scopedCapabilities.length === 0 ? (
          <div className="permission-empty">{text("暂无作用域系统能力。", "No scoped system capabilities.")}</div>
        ) : (
          <div className="scoped-capability-list">
            {scopedCapabilities.map((capability) => {
              const wildcard = `${capability.name}:*`;
              const allScopes = grants.has(wildcard) || grants.has(capability.name);
              return (
                <fieldset className="scoped-capability" key={capability.id}>
                  <legend>
                    <strong>{capabilityTitle(capability)}</strong>
                    <code>{capability.name}</code>
                  </legend>
                  {capabilityDescription(capability) && <p>{capabilityDescription(capability)}</p>}
                  <div className="scope-options">
                    <label className="scope-option wildcard">
                      <input
                        type="checkbox"
                        checked={allScopes}
                        onChange={(event) => toggleAllScopes(capability.name, event.target.checked)}
                      />
                      <span>{text("全部对象类型", "All object types")} <code>{wildcard}</code></span>
                    </label>
                    {objectTypes.map((objectType) => {
                      const grant = `${capability.name}:${objectType}`;
                      return (
                        <label className="scope-option" key={grant}>
                          <input
                            type="checkbox"
                            checked={allScopes || grants.has(grant)}
                            disabled={allScopes}
                            onChange={(event) => toggleGrant(grant, event.target.checked)}
                          />
                          <span>{objectType}</span>
                        </label>
                      );
                    })}
                  </div>
                  {objectTypes.length === 0 && !allScopes && (
                    <small className="permission-hint">{text("当前没有启用的业务对象类型；仍可授予全部类型。", "No business object types are enabled; access to all types can still be granted.")}</small>
                  )}
                </fieldset>
              );
            })}
          </div>
        )}
      </section>

      <section className="permission-section" aria-labelledby="custom-capabilities-title">
        <div className="permission-heading">
          <div>
            <h3 id="custom-capabilities-title">{text("自定义能力", "Custom capabilities")}</h3>
            <p>{text("用于 Skill 分发门槛与流程参与资格，不会自动改变其他业务操作权限。", "Use these for Skill-distribution gates and workflow eligibility; they do not automatically change other business permissions.")}</p>
          </div>
          <span>{customCapabilities.length}</span>
        </div>
        {customCapabilities.length === 0 ? (
          <div className="permission-empty">{text("还没有自定义能力。", "No custom capabilities yet.")}</div>
        ) : (
          <div className="permission-checks">
            {customCapabilities.map((capability) => (
              <label className="permission-check" key={capability.id}>
                <input
                  type="checkbox"
                  checked={grants.has(capability.name)}
                  onChange={(event) => toggleGrant(capability.name, event.target.checked)}
                />
                <span>
                  <strong>{capability.title || capability.name}</strong>
                  <code>{capability.name}</code>
                  {capability.description && <small>{capability.description}</small>}
                </span>
              </label>
            ))}
          </div>
        )}
      </section>

      {retainedGrants.length > 0 && (
        <section className="permission-section retained-permissions" aria-labelledby="retained-capabilities-title">
          <div className="permission-heading">
            <div>
              <h3 id="retained-capabilities-title">{text("其他既有授权", "Other existing grants")}</h3>
              <p>{text("这些授权当前不在能力目录中；保存时默认保留，也可以显式移除。", "These grants are not currently in the capability catalog. They are retained by default when saving, but can be removed explicitly.")}</p>
            </div>
            <span>{retainedGrants.length}</span>
          </div>
          <div className="permission-checks">
            {retainedGrants.map((grant) => (
              <label className="permission-check" key={grant}>
                <input
                  type="checkbox"
                  checked={grants.has(grant)}
                  onChange={(event) => toggleGrant(grant, event.target.checked)}
                />
                <span><code>{grant}</code></span>
              </label>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
