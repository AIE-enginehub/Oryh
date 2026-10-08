import type { RuleKind } from "../api/configuration";

/** The three kinds keyed to an object type; a policy is keyed by its own code. */
export const SCOPED_RULE_KINDS: Exclude<RuleKind, "policy">[] = ["approval_flow", "data_rule", "linkage"];
export const RULE_KINDS: RuleKind[] = [...SCOPED_RULE_KINDS, "policy"];

type Localize = (chinese: string, english: string) => string;

export function ruleKindLabel(kind: string, text: Localize): string {
  switch (kind) {
    case "approval_flow": return text("审批流程", "Approval flow");
    case "data_rule": return text("数据要求", "Data rule");
    case "linkage": return text("单据联动", "Linkage");
    case "policy": return text("制度", "Policy");
    default: return kind;
  }
}

/** Who reads a kind, and what for — shown beside the editor. */
export function ruleKindHint(kind: string, text: Localize): string {
  switch (kind) {
    case "approval_flow": return text("仅工作流 agent 读取：单据提交后往哪走、谁来批。", "Read by the flow agent only: where a submitted document goes and who approves it.");
    case "data_rule": return text("员工侧 agent 填写时核对，工作流 agent 路由前校准：单据必须满足什么。", "Checked by the member's agent while filling and calibrated by the flow agent before routing: what a document must satisfy.");
    case "linkage": return text("单据到达某个状态时，别处要发生什么。", "What happens elsewhere when a document reaches a state.");
    default: return "";
  }
}

export function ruleKindPlaceholder(kind: string, text: Localize): string {
  switch (kind) {
    case "approval_flow": return text("例：提交后由直属经理审批，金额超过一万加签总经理。", "e.g. the line manager approves first; add the GM above ¥10,000.");
    case "data_rule": return text("例：每条工时必须关联到具体项目任务；一周合计恰好 40 小时。", "e.g. every entry must reference a project task; the week must total exactly 40 hours.");
    case "linkage": return text("例：订单 confirmed 后生成拣货任务；signed 后开票。", "e.g. a confirmed order creates a picking task; a signed one is invoiced.");
    default: return "";
  }
}
