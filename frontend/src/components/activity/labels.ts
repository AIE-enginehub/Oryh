import type { ApprovalAction, ApprovalEntityType, TodoEntityType } from "../../api/activity";
import { useI18n } from "../../i18n";

export function useActivityLabels() {
  const { text } = useI18n();
  const entityLabels: Record<TodoEntityType | ApprovalEntityType, string> = {
    timesheet_header: text("工时表", "Timesheet"),
    expense_claim: text("报销单", "Expense claim"),
    purchase_request: text("采购申请", "Purchase request"),
    sales_quotation: text("销售报价", "Sales quotation"),
    sales_order: text("销售订单", "Sales order"),
    project: text("项目", "Project"),
    approval_target: text("审批对象", "Approval target"),
    business_object: text("业务对象", "Business object"),
  };
  const approvalActionLabels: Record<ApprovalAction, string> = {
    submitted: text("已提交", "Submitted"),
    approved: text("已批准", "Approved"),
    rejected: text("已拒绝", "Rejected"),
    returned: text("已退回", "Returned"),
    commented: text("已评论", "Commented"),
  };
  const todoEntityOptions = Object.entries(entityLabels).map(([value, label]) => ({ value, label }));
  const approvalEntityOptions = todoEntityOptions.filter((option) => option.value !== "project");
  return { entityLabels, approvalActionLabels, todoEntityOptions, approvalEntityOptions };
}
