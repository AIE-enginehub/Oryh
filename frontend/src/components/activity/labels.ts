import { zhCN } from "../../locales/zh-CN/console";
import type { ApprovalAction, ApprovalEntityType, TodoEntityType } from "../../api/activity";
import { useI18n } from "../../i18n";

export function useActivityLabels() {
  const { text } = useI18n();
  const entityLabels: Record<TodoEntityType | ApprovalEntityType, string> = {
    timesheet_header: text(zhCN.componentsActivityLabels.timesheet, "Timesheet"),
    expense_claim: text(zhCN.componentsActivityLabels.expenseClaim, "Expense claim"),
    purchase_request: text(zhCN.componentsActivityLabels.purchaseRequest, "Purchase request"),
    sales_quotation: text(zhCN.componentsActivityLabels.salesQuotation, "Sales quotation"),
    sales_order: text(zhCN.componentsActivityLabels.salesOrder, "Sales order"),
    project: text(zhCN.componentsActivityLabels.project, "Project"),
    approval_target: text(zhCN.componentsActivityLabels.approvalTarget, "Approval target"),
    business_object: text(zhCN.componentsActivityLabels.businessObject, "Business object"),
  };
  const approvalActionLabels: Record<ApprovalAction, string> = {
    submitted: text(zhCN.componentsActivityLabels.submitted, "Submitted"),
    approved: text(zhCN.componentsActivityLabels.approved, "Approved"),
    rejected: text(zhCN.componentsActivityLabels.rejected, "Rejected"),
    returned: text(zhCN.componentsActivityLabels.returned, "Returned"),
    commented: text(zhCN.componentsActivityLabels.commented, "Commented"),
  };
  const todoEntityOptions = Object.entries(entityLabels).map(([value, label]) => ({ value, label }));
  const approvalEntityOptions = todoEntityOptions.filter((option) => option.value !== "project");
  return { entityLabels, approvalActionLabels, todoEntityOptions, approvalEntityOptions };
}
