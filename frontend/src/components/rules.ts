import { zhCN } from "../locales/zh-CN/console";
import type { RuleKind } from "../api/configuration";

/** The three kinds keyed to an object type; a policy is keyed by its own code. */
export const SCOPED_RULE_KINDS: Exclude<RuleKind, "policy">[] = ["approval_flow", "data_rule", "linkage"];
export const RULE_KINDS: RuleKind[] = [...SCOPED_RULE_KINDS, "policy"];

type Localize = (chinese: string, english: string) => string;

export function ruleKindLabel(kind: string, text: Localize): string {
  switch (kind) {
    case "approval_flow": return text(zhCN.componentsRules.approvalFlow, "Approval flow");
    case "data_rule": return text(zhCN.componentsRules.dataRule, "Data rule");
    case "linkage": return text(zhCN.componentsRules.linkage, "Linkage");
    case "policy": return text(zhCN.componentsRules.policy, "Policy");
    default: return kind;
  }
}

/** Who reads a kind, and what for — shown beside the editor. */
export function ruleKindHint(kind: string, text: Localize): string {
  switch (kind) {
    case "approval_flow": return text(zhCN.componentsRules.readByTheFlowAgentOnlyWhereASubmitted, "Read by the flow agent only: where a submitted document goes and who approves it.");
    case "data_rule": return text(zhCN.componentsRules.checkedByTheMemberSAgentWhileFillingAnd, "Checked by the member's agent while filling and calibrated by the flow agent before routing: what a document must satisfy.");
    case "linkage": return text(zhCN.componentsRules.whatHappensElsewhereWhenADocumentReachesAState, "What happens elsewhere when a document reaches a state.");
    default: return "";
  }
}

export function ruleKindPlaceholder(kind: string, text: Localize): string {
  switch (kind) {
    case "approval_flow": return text(zhCN.componentsRules.eGTheLineManagerApprovesFirstAddThe, "e.g. the line manager approves first; add the GM above ¥10,000.");
    case "data_rule": return text(zhCN.componentsRules.eGEveryEntryMustReferenceAProjectTask, "e.g. every entry must reference a project task; the week must total exactly 40 hours.");
    case "linkage": return text(zhCN.componentsRules.eGAConfirmedOrderCreatesAPickingTask, "e.g. a confirmed order creates a picking task; a signed one is invoiced.");
    default: return "";
  }
}
