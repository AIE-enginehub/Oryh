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
    kicker={text("完成待办", "Complete to-do")}
    confirmLabel={text("确认完成", "Confirm completion")}
    busyLabel={text("正在完成…", "Completing…")}
    scrimLabel={text("取消完成待办", "Cancel completing to-do")}
  />;
}
