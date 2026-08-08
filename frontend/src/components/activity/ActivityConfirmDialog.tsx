import { useEffect, useRef } from "react";
import { useI18n } from "../../i18n";

type ActivityConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  busy: boolean;
  error?: string | null;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ActivityConfirmDialog({ open, title, description, busy, error, onCancel, onConfirm }: ActivityConfirmDialogProps) {
  const { text } = useI18n();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const cancelHandler = useRef(onCancel);
  const busyRef = useRef(busy);
  cancelHandler.current = onCancel;
  busyRef.current = busy;
  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) cancelHandler.current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  if (!open) return null;
  return (
    <div className="dialog-layer">
      <button className="drawer-scrim" type="button" aria-label={text("取消完成待办", "Cancel completing to-do")} onClick={onCancel} />
      <section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="activity-confirm-title" aria-describedby="activity-confirm-description">
        <span className="eyebrow">Complete todo</span>
        <h2 id="activity-confirm-title">{title}</h2>
        <p id="activity-confirm-description">{description}</p>
        {error && <div className="form-error" role="alert">{error}</div>}
        <div className="dialog-actions">
          <button ref={cancelRef} className="button" type="button" disabled={busy} onClick={onCancel}>{text("取消", "Cancel")}</button>
          <button className="button primary" type="button" disabled={busy} onClick={onConfirm}>{busy ? text("正在完成…", "Completing…") : text("确认完成", "Confirm completion")}</button>
        </div>
      </section>
    </div>
  );
}
