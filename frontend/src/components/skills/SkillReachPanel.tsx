import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { type SkillReach, type SkillReachEntry } from "../../api/configuration";
import { useI18n } from "../../i18n";
import { apiErrorMessage } from "../master-data/ListState";

/** Which skills a person or role receives — and why not for the rest.
 *
 * The withheld half is why this exists. "Why doesn't my agent have that
 * skill" was previously answerable only by deriving the capability matrix by
 * hand, so it went unanswered; each withheld row here names the reason and,
 * for a missing capability, the roles that hold it.
 */
export function SkillReachPanel({
  subjectKey,
  fetcher,
}: {
  subjectKey: string;
  fetcher: () => Promise<SkillReach>;
}) {
  const { text } = useI18n();
  const [showWithheld, setShowWithheld] = useState(false);
  const reach = useQuery({ queryKey: ["skill-reach", subjectKey], queryFn: fetcher });

  if (reach.isPending) {
    return <section className="skill-reach"><p className="muted-value">{text("正在计算…", "Working it out…")}</p></section>;
  }
  if (reach.isError) {
    return (
      <section className="skill-reach">
        <p className="form-error">{apiErrorMessage(reach.error)}</p>
      </section>
    );
  }

  const { received, withheld } = reach.data;
  // Three groups, not two. A skill blocked on BOTH axes needs both fixes, and
  // filing it under either heading alone sends the reader to do half the work.
  const both = withheld.filter((entry) => entry.reasons.length > 1);
  const blocked = withheld.filter(
    (entry) => entry.reasons.length === 1 && entry.reasons[0] === "missing_capability",
  );
  const unnamed = withheld.filter(
    (entry) => entry.reasons.length === 1 && entry.reasons[0] === "not_in_audience",
  );

  return (
    <section className="skill-reach">
      <h4>
        {text("会收到的技能", "Skills received")}
        <span className="reach-count">{received.length}</span>
      </h4>
      <p className="reach-hint">
        {text(
          "下次同步时安装到这个人的 agent 上。",
          "What the next sync would install on this agent.",
        )}
      </p>

      {received.length === 0 ? (
        <p className="muted-value">{text("目前一个技能也收不到。", "Receives nothing right now.")}</p>
      ) : (
        <ul className="reach-list">
          {received.map((entry) => (
            <li key={entry.name}>
              <strong>{entry.title || entry.name}</strong>
              <code>{entry.name}</code>
              <ReceivedReason entry={entry} />
              <SkillPurpose entry={entry} />
            </li>
          ))}
        </ul>
      )}

      {withheld.length > 0 && (
        <>
          <button
            className="text-action reach-toggle"
            type="button"
            aria-expanded={showWithheld}
            onClick={() => setShowWithheld((open) => !open)}
          >
            {showWithheld
              ? text("收起收不到的技能", "Hide what is not received")
              : text(`收不到的 ${withheld.length} 个技能，及原因`, `${withheld.length} not received — and why`)}
          </button>

          {showWithheld && (
            <div className="reach-withheld">
              {blocked.length > 0 && (
                <>
                  <h5>{text("缺少所需能力", "Missing the capability")}</h5>
                  <ul className="reach-list">
                    {blocked.map((entry) => (
                      <li key={entry.name}>
                        <strong>{entry.title || entry.name}</strong>
                        <code>{entry.name}</code>
                        <small className="reach-reason">
                          {text("需要 ", "Needs ")}
                          <code>{entry.required_capability}</code>
                          {entry.granted_by_roles.length > 0
                            ? text(
                                `，目前持有该能力的角色：${entry.granted_by_roles.join("、")}`,
                                `, currently held by: ${entry.granted_by_roles.join(", ")}`,
                              )
                            : text("，目前没有任何角色持有该能力", ", which no role currently holds")}
                        </small>
                        <SkillPurpose entry={entry} />
                      </li>
                    ))}
                  </ul>
                </>
              )}

              {both.length > 0 && (
                <>
                  <h5>{text("能力和分发范围都不满足", "Blocked on both")}</h5>
                  <ul className="reach-list">
                    {both.map((entry) => (
                      <li key={entry.name}>
                        <strong>{entry.title || entry.name}</strong>
                        <code>{entry.name}</code>
                        <small className="reach-reason">
                          {text("需要 ", "Needs ")}
                          <code>{entry.required_capability}</code>
                          {text(
                            "，并且要被加入该技能的受众。只做其中一样仍然收不到。",
                            ", and to be added to the skill's audience. Doing only one of the two still leaves it out of reach.",
                          )}
                        </small>
                        <SkillPurpose entry={entry} />
                      </li>
                    ))}
                  </ul>
                </>
              )}

              {unnamed.length > 0 && (
                <>
                  <h5>{text("能力够，但不在分发范围内", "Allowed, but targeted elsewhere")}</h5>
                  <ul className="reach-list">
                    {unnamed.map((entry) => (
                      <li key={entry.name}>
                        <strong>{entry.title || entry.name}</strong>
                        <code>{entry.name}</code>
                        <small className="reach-reason">
                          {text(
                            "该技能为定向分发，在「技能」页把这里加入受众即可。",
                            "This skill is targeted; add this subject to its audience on the Skills page.",
                          )}
                        </small>
                        <SkillPurpose entry={entry} />
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}

/** What the skill is FOR, under the name.
 *
 * Every row used to show `title || name` — "Oryh Payroll" — which is a label.
 * An admin looking at a role called `hr_admin` and a withheld skill called
 * "Oryh Payroll" still has to guess whether HR needs it, and in the workspace
 * this was found in, the guess went the other way for months: the HR role held
 * no payroll verb, so the HR agent never received the skill and quietly filed
 * the wrong kind of record when asked to 做工资单.
 */
function SkillPurpose({ entry }: { entry: SkillReachEntry }) {
  if (!entry.description) return null;
  return <small className="reach-purpose">{entry.description}</small>;
}

function ReceivedReason({ entry }: { entry: SkillReachEntry }) {
  const { text } = useI18n();
  if (entry.reasons.includes("targeted_user")) {
    return <small className="reach-reason">{text("单独指定", "Named individually")}</small>;
  }
  if (entry.reasons.includes("targeted_role")) {
    const role = entry.named_via.find((via) => via.startsWith("role:"))?.slice(5);
    return (
      <small className="reach-reason">
        {role ? text(`通过角色 ${role} 指定`, `Named via the ${role} role`) : text("通过角色指定", "Named via a role")}
      </small>
    );
  }
  return (
    <small className="reach-reason muted-value">
      {entry.required_capability
        ? text("按能力分发", "By capability")
        : text("对所有人开放", "Open to everyone")}
    </small>
  );
}
