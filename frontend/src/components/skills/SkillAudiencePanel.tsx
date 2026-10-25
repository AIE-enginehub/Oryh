import { zhCN } from "../../locales/zh-CN/console";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { listRoles, listUsers } from "../../api/client";
import {
  addSkillAssignment,
  getSkillAudience,
  removeSkillAssignment,
  setSkillDistributionMode,
  type DistributionMode,
  type SkillAudienceImpact,
} from "../../api/configuration";
import { useI18n } from "../../i18n";
import { apiErrorMessage } from "../master-data/ListState";

/** Who a skill is for, beside what it requires.
 *
 * The panel's real job is the impact block: switching a skill to targeted
 * takes it away from everyone left out, and nobody reports a skill they
 * quietly stopped receiving. So `losing` is shown as a warning, not a stat.
 */
export function SkillAudiencePanel({ skillName }: { skillName: string }) {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [subjectType, setSubjectType] = useState<"role" | "user">("role");
  const [subjectId, setSubjectId] = useState("");
  const [department, setDepartment] = useState("");

  const audience = useQuery({
    queryKey: ["skill-audience", skillName],
    queryFn: () => getSkillAudience(skillName),
  });
  const roles = useQuery({ queryKey: ["roles"], queryFn: listRoles });
  const users = useQuery({
    queryKey: ["users", "audience-picker"],
    queryFn: () => listUsers({ size: 200, status: "active" }),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["skill-audience", skillName] });
    await queryClient.invalidateQueries({ queryKey: ["skills"] });
  };

  const setMode = useMutation({
    mutationFn: (mode: DistributionMode) => setSkillDistributionMode(skillName, mode),
    onSuccess: invalidate,
  });
  const add = useMutation({
    mutationFn: (subject: { subject_type: "user" | "role"; subject_id: string }) =>
      addSkillAssignment(skillName, subject),
    onSuccess: async () => { setSubjectId(""); await invalidate(); },
  });
  const remove = useMutation({
    mutationFn: (assignmentId: string) => removeSkillAssignment(skillName, assignmentId),
    onSuccess: invalidate,
  });

  // Department is a selection helper only — it expands to individual people.
  // It is deliberately NOT a distribution axis: roles are what the server
  // enforces, and a second, weaker org hierarchy would drift from them.
  const departments = useMemo(() => {
    const found = new Set<string>();
    for (const user of users.data?.data ?? []) {
      const value = (user as { department?: string | null }).department;
      if (value) found.add(value);
    }
    return [...found].sort();
  }, [users.data]);

  const impact = audience.data?.impact;
  const mode = impact?.distribution_mode ?? "capability";
  const assignments = audience.data?.assignments ?? [];

  return (
    <section className="skill-audience">
      <h4>{text(zhCN.componentsSkillsSkillAudiencePanel.distribution, "Distribution")}</h4>

      <div className="audience-mode">
        <label>
          <input
            type="radio"
            name="distribution-mode"
            checked={mode === "capability"}
            disabled={setMode.isPending}
            onChange={() => setMode.mutate("capability")}
          />
          <span>
            <b>{text(zhCN.componentsSkillsSkillAudiencePanel.byCapability, "By capability")}</b>
            <small>{text(zhCN.componentsSkillsSkillAudiencePanel.everyoneWhoseRoleCoversTheRequiredCapabilityReceivesIt, "Everyone whose role covers the required capability receives it.")}</small>
          </span>
        </label>
        <label>
          <input
            type="radio"
            name="distribution-mode"
            checked={mode === "targeted"}
            disabled={setMode.isPending}
            onChange={() => setMode.mutate("targeted")}
          />
          <span>
            <b>{text(zhCN.componentsSkillsSkillAudiencePanel.targeted, "Targeted")}</b>
            <small>{text(zhCN.componentsSkillsSkillAudiencePanel.onlyTheRolesAndPeopleNamedBelowAndThey, "Only the roles and people named below, and they must still hold the required capability.")}</small>
          </span>
        </label>
      </div>

      {impact && <AudienceImpact impact={impact} mode={mode} />}

      <div className="audience-picker">
        <select
          aria-label={text(zhCN.componentsSkillsSkillAudiencePanel.audienceType, "Audience type")}
          value={subjectType}
          onChange={(event) => { setSubjectType(event.target.value as "role" | "user"); setSubjectId(""); }}
        >
          <option value="role">{text(zhCN.componentsSkillsSkillAudiencePanel.role, "Role")}</option>
          <option value="user">{text(zhCN.componentsSkillsSkillAudiencePanel.user, "User")}</option>
        </select>

        {subjectType === "role" ? (
          <select aria-label={text(zhCN.componentsSkillsSkillAudiencePanel.chooseRole, "Choose role")} value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
            <option value="">{text(zhCN.componentsSkillsSkillAudiencePanel.chooseARole, "Choose a role…")}</option>
            {(roles.data ?? []).map((role) => (
              <option key={role.name} value={role.name}>{role.title || role.name}</option>
            ))}
          </select>
        ) : (
          <>
            {departments.length > 0 && (
              <select aria-label={text(zhCN.componentsSkillsSkillAudiencePanel.filterByDepartment, "Filter by department")} value={department} onChange={(e) => setDepartment(e.target.value)}>
                <option value="">{text(zhCN.componentsSkillsSkillAudiencePanel.allDepartments, "All departments")}</option>
                {departments.map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            )}
            <select aria-label={text(zhCN.componentsSkillsSkillAudiencePanel.chooseUser, "Choose user")} value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
              <option value="">{text(zhCN.componentsSkillsSkillAudiencePanel.chooseAPerson, "Choose a person…")}</option>
              {(users.data?.data ?? [])
                .filter((user) => !department || (user as { department?: string | null }).department === department)
                .map((user) => (
                  <option key={user.id} value={user.id}>{user.name || user.email}</option>
                ))}
            </select>
          </>
        )}

        <button
          className="button compact"
          type="button"
          disabled={!subjectId || add.isPending}
          onClick={() => add.mutate({ subject_type: subjectType, subject_id: subjectId })}
        >
          {text(zhCN.componentsSkillsSkillAudiencePanel.add, "Add")}
        </button>
      </div>

      {add.isError && <p className="form-error">{apiErrorMessage(add.error)}</p>}

      {assignments.length === 0 ? (
        <p className="muted-value">{text(zhCN.componentsSkillsSkillAudiencePanel.nobodyNamedYet, "Nobody named yet.")}</p>
      ) : (
        <ul className="audience-list">
          {assignments.map((row) => (
            <li key={row.id}>
              <span className={`kind-chip ${row.subject_type}`}>
                {row.subject_type === "role" ? text(zhCN.componentsSkillsSkillAudiencePanel.role, "Role") : text(zhCN.componentsSkillsSkillAudiencePanel.user, "User")}
              </span>
              <strong>{row.subject_label || row.subject_id}</strong>
              {row.blocked_members.length > 0 && (
                <small className="audience-blocked">
                  {text(
                    zhCN.componentsSkillsSkillAudiencePanel.lackTheCapabilityAndWillNotReceiveIt(`${row.blocked_members.length}`),
                    `${row.blocked_members.length} lack the capability and will not receive it`,
                  )}
                </small>
              )}
              <button className="text-action danger-text" type="button" disabled={remove.isPending} onClick={() => remove.mutate(row.id)}>
                {text(zhCN.componentsSkillsSkillAudiencePanel.remove, "Remove")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function AudienceImpact({ impact, mode }: { impact: SkillAudienceImpact; mode: DistributionMode }) {
  const { text } = useI18n();
  const pending = mode === "capability" && (impact.losing.length > 0 || impact.gaining.length > 0);
  return (
    <div className="audience-impact">
      <p>
        {text(
          zhCN.componentsSkillsSkillAudiencePanel.peopleReceiveItToday(`${impact.reaches_now.length}`),
          `${impact.reaches_now.length} people receive it today`,
        )}
        {mode === "targeted" && text(zhCN.componentsSkillsSkillAudiencePanel.targeted2(`${impact.would_reach.length}`), ` (targeted: ${impact.would_reach.length})`)}
      </p>

      {pending && (
        <p className="audience-note">
          {text(
            zhCN.componentsSkillsSkillAudiencePanel.switchingToTargetedWouldMakeThat(`${impact.would_reach.length}`),
            `Switching to targeted would make that ${impact.would_reach.length}.`,
          )}
        </p>
      )}

      {impact.losing.length > 0 && (
        <p className="audience-warning">
          <b>{text(zhCN.componentsSkillsSkillAudiencePanel.wouldLoseThisSkill(`${impact.losing.length}`), `${impact.losing.length} would lose this skill`)}</b>
          <small>
            {text(zhCN.componentsSkillsSkillAudiencePanel.removedFromTheirBundleOnNextSync, "Removed from their bundle on next sync: ")}
            {impact.losing.slice(0, 8).join("、")}
            {impact.losing.length > 8 && text(zhCN.componentsSkillsSkillAudiencePanel.andMore(`${impact.losing.length}`), ` and ${impact.losing.length - 8} more`)}
          </small>
        </p>
      )}

      {impact.blocked.length > 0 && (
        <p className="audience-warning">
          <b>{text(zhCN.componentsSkillsSkillAudiencePanel.namedButCannotRunIt(`${impact.blocked.length}`), `${impact.blocked.length} named but cannot run it`)}</b>
          <small>
            {text(
              zhCN.componentsSkillsSkillAudiencePanel.theyWillNotReceiveItGrantTheCapabilityFirst,
              "They will not receive it. Grant the capability first, or drop them from the audience.",
            )}
          </small>
        </p>
      )}
    </div>
  );
}
