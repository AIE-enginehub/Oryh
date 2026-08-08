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
      <h4>{text("分发范围", "Distribution")}</h4>

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
            <b>{text("按能力分发", "By capability")}</b>
            <small>{text("持有所需能力的人都会收到。", "Everyone whose role covers the required capability receives it.")}</small>
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
            <b>{text("定向分发", "Targeted")}</b>
            <small>{text("只发给下面指定的角色与用户，且他们仍需持有所需能力。", "Only the roles and people named below, and they must still hold the required capability.")}</small>
          </span>
        </label>
      </div>

      {impact && <AudienceImpact impact={impact} mode={mode} />}

      <div className="audience-picker">
        <select
          aria-label={text("受众类型", "Audience type")}
          value={subjectType}
          onChange={(event) => { setSubjectType(event.target.value as "role" | "user"); setSubjectId(""); }}
        >
          <option value="role">{text("角色", "Role")}</option>
          <option value="user">{text("用户", "User")}</option>
        </select>

        {subjectType === "role" ? (
          <select aria-label={text("选择角色", "Choose role")} value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
            <option value="">{text("选择角色…", "Choose a role…")}</option>
            {(roles.data ?? []).map((role) => (
              <option key={role.name} value={role.name}>{role.title || role.name}</option>
            ))}
          </select>
        ) : (
          <>
            {departments.length > 0 && (
              <select aria-label={text("按部门筛选", "Filter by department")} value={department} onChange={(e) => setDepartment(e.target.value)}>
                <option value="">{text("全部部门", "All departments")}</option>
                {departments.map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            )}
            <select aria-label={text("选择用户", "Choose user")} value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
              <option value="">{text("选择用户…", "Choose a person…")}</option>
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
          {text("加入受众", "Add")}
        </button>
      </div>

      {add.isError && <p className="form-error">{apiErrorMessage(add.error)}</p>}

      {assignments.length === 0 ? (
        <p className="muted-value">{text("尚未指定任何受众。", "Nobody named yet.")}</p>
      ) : (
        <ul className="audience-list">
          {assignments.map((row) => (
            <li key={row.id}>
              <span className={`kind-chip ${row.subject_type}`}>
                {row.subject_type === "role" ? text("角色", "Role") : text("用户", "User")}
              </span>
              <strong>{row.subject_label || row.subject_id}</strong>
              {row.blocked_members.length > 0 && (
                <small className="audience-blocked">
                  {text(
                    `${row.blocked_members.length} 人缺少所需能力，收不到`,
                    `${row.blocked_members.length} lack the capability and will not receive it`,
                  )}
                </small>
              )}
              <button className="text-action danger-text" type="button" disabled={remove.isPending} onClick={() => remove.mutate(row.id)}>
                {text("移除", "Remove")}
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
          `当前 ${impact.reaches_now.length} 人可收到`,
          `${impact.reaches_now.length} people receive it today`,
        )}
        {mode === "targeted" && text(`（定向后 ${impact.would_reach.length} 人）`, ` (targeted: ${impact.would_reach.length})`)}
      </p>

      {pending && (
        <p className="audience-note">
          {text(
            `切换到定向分发后将变为 ${impact.would_reach.length} 人。`,
            `Switching to targeted would make that ${impact.would_reach.length}.`,
          )}
        </p>
      )}

      {impact.losing.length > 0 && (
        <p className="audience-warning">
          <b>{text(`${impact.losing.length} 人会失去这个技能`, `${impact.losing.length} would lose this skill`)}</b>
          <small>
            {text("下次同步时从他们的技能包中移除：", "Removed from their bundle on next sync: ")}
            {impact.losing.slice(0, 8).join("、")}
            {impact.losing.length > 8 && text(` 等 ${impact.losing.length} 人`, ` and ${impact.losing.length - 8} more`)}
          </small>
        </p>
      )}

      {impact.blocked.length > 0 && (
        <p className="audience-warning">
          <b>{text(`${impact.blocked.length} 人被指定但缺少所需能力`, `${impact.blocked.length} named but cannot run it`)}</b>
          <small>
            {text(
              "他们不会收到这个技能。先给对应能力，或把他们从受众里去掉。",
              "They will not receive it. Grant the capability first, or drop them from the audience.",
            )}
          </small>
        </p>
      )}
    </div>
  );
}
