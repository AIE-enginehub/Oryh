import { zhCN } from "../../locales/zh-CN/console";
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
    return <section className="skill-reach"><p className="muted-value">{text(zhCN.componentsSkillsSkillReachPanel.workingItOut, "Working it out…")}</p></section>;
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
        {text(zhCN.componentsSkillsSkillReachPanel.skillsReceived, "Skills received")}
        <span className="reach-count">{received.length}</span>
      </h4>
      <p className="reach-hint">
        {text(
          zhCN.componentsSkillsSkillReachPanel.whatTheNextSyncWouldInstallOnThisAgent,
          "What the next sync would install on this agent.",
        )}
      </p>

      {received.length === 0 ? (
        <p className="muted-value">{text(zhCN.componentsSkillsSkillReachPanel.receivesNothingRightNow, "Receives nothing right now.")}</p>
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
              ? text(zhCN.componentsSkillsSkillReachPanel.hideWhatIsNotReceived, "Hide what is not received")
              : text(zhCN.componentsSkillsSkillReachPanel.notReceivedAndWhy(`${withheld.length}`), `${withheld.length} not received — and why`)}
          </button>

          {showWithheld && (
            <div className="reach-withheld">
              {blocked.length > 0 && (
                <>
                  <h5>{text(zhCN.componentsSkillsSkillReachPanel.missingTheCapability, "Missing the capability")}</h5>
                  <ul className="reach-list">
                    {blocked.map((entry) => (
                      <li key={entry.name}>
                        <strong>{entry.title || entry.name}</strong>
                        <code>{entry.name}</code>
                        <small className="reach-reason">
                          {text(zhCN.componentsSkillsSkillReachPanel.needs, "Needs ")}
                          <code>{entry.required_capability}</code>
                          {entry.granted_by_roles.length > 0
                            ? text(
                                zhCN.componentsSkillsSkillReachPanel.currentlyHeldBy(`${entry.granted_by_roles.join("、")}`),
                                `, currently held by: ${entry.granted_by_roles.join(", ")}`,
                              )
                            : text(zhCN.componentsSkillsSkillReachPanel.whichNoRoleCurrentlyHolds, ", which no role currently holds")}
                        </small>
                        <SkillPurpose entry={entry} />
                      </li>
                    ))}
                  </ul>
                </>
              )}

              {both.length > 0 && (
                <>
                  <h5>{text(zhCN.componentsSkillsSkillReachPanel.blockedOnBoth, "Blocked on both")}</h5>
                  <ul className="reach-list">
                    {both.map((entry) => (
                      <li key={entry.name}>
                        <strong>{entry.title || entry.name}</strong>
                        <code>{entry.name}</code>
                        <small className="reach-reason">
                          {text(zhCN.componentsSkillsSkillReachPanel.needs, "Needs ")}
                          <code>{entry.required_capability}</code>
                          {text(
                            zhCN.componentsSkillsSkillReachPanel.andToBeAddedToTheSkillSAudience,
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
                  <h5>{text(zhCN.componentsSkillsSkillReachPanel.allowedButTargetedElsewhere, "Allowed, but targeted elsewhere")}</h5>
                  <ul className="reach-list">
                    {unnamed.map((entry) => (
                      <li key={entry.name}>
                        <strong>{entry.title || entry.name}</strong>
                        <code>{entry.name}</code>
                        <small className="reach-reason">
                          {text(
                            zhCN.componentsSkillsSkillReachPanel.thisSkillIsTargetedAddThisSubjectToIts,
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
 * the wrong kind of record when asked to generate payslips.
 */
function SkillPurpose({ entry }: { entry: SkillReachEntry }) {
  if (!entry.description) return null;
  return <small className="reach-purpose">{entry.description}</small>;
}

function ReceivedReason({ entry }: { entry: SkillReachEntry }) {
  const { text } = useI18n();
  if (entry.reasons.includes("targeted_user")) {
    return <small className="reach-reason">{text(zhCN.componentsSkillsSkillReachPanel.namedIndividually, "Named individually")}</small>;
  }
  if (entry.reasons.includes("targeted_role")) {
    const role = entry.named_via.find((via) => via.startsWith("role:"))?.slice(5);
    return (
      <small className="reach-reason">
        {role ? text(zhCN.componentsSkillsSkillReachPanel.namedViaTheRole(`${role}`), `Named via the ${role} role`) : text(zhCN.componentsSkillsSkillReachPanel.namedViaARole, "Named via a role")}
      </small>
    );
  }
  return (
    <small className="reach-reason muted-value">
      {entry.required_capability
        ? text(zhCN.componentsSkillsSkillReachPanel.byCapability, "By capability")
        : text(zhCN.componentsSkillsSkillReachPanel.openToEveryone, "Open to everyone")}
    </small>
  );
}
