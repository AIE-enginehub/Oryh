import { zhCN } from "../../locales/zh-CN/console";
import { useI18n } from "../../i18n";
import { ConfirmDialog } from "../master-data/ConfirmDialog";

type ActivityConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  busy: boolean;
  error?: string | null;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ActivityConfirmDialog(props: ActivityConfirmDialogProps) {
  const { text } = useI18n();
  return <ConfirmDialog {...props} tone="primary"
    kicker={text(zhCN.componentsActivityActivityConfirmDialog.completeToDo, "Complete to-do")}
    confirmLabel={text(zhCN.componentsActivityActivityConfirmDialog.confirmCompletion, "Confirm completion")}
    busyLabel={text(zhCN.componentsActivityActivityConfirmDialog.completing, "Completing…")}
    scrimLabel={text(zhCN.componentsActivityActivityConfirmDialog.cancelCompletingToDo, "Cancel completing to-do")}
  />;
}
