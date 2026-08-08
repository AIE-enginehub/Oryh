import { useEffect, useRef } from "react";
import { useI18n } from "../../i18n";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  busy?: boolean;
  error?: string | null;
  kicker?: string;
  confirmLabel?: string;
  busyLabel?: string;
  scrimLabel?: string;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  busy,
  error,
  kicker,
  confirmLabel,
  busyLabel,
  scrimLabel,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const { text } = useI18n();
  const resolvedKicker = kicker ?? text("归档确认", "Archive confirmation");
  const resolvedConfirmLabel = confirmLabel ?? text("确认归档", "Confirm archive");
  const resolvedBusyLabel = busyLabel ?? text("正在归档…", "Archiving…");
  const resolvedScrimLabel = scrimLabel ?? text("取消归档", "Cancel archive");
  const cancelRef = useRef<HTMLButtonElement>(null);
  const cancelHandlerRef = useRef(onCancel);
  const busyRef = useRef(busy);
  cancelHandlerRef.current = onCancel;
  busyRef.current = busy;
  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) cancelHandlerRef.current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  if (!open) return null;
  return (
    <div className="dialog-layer">
      <button className="drawer-scrim" type="button" aria-label={resolvedScrimLabel} onClick={onCancel} />
      <section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-description">
        <span className="danger-kicker">{resolvedKicker}</span>
        <h2 id="confirm-title">{title}</h2>
        <p id="confirm-description">{description}</p>
        {error && <div className="form-error" role="alert">{error}</div>}
        <div className="dialog-actions">
          <button ref={cancelRef} className="button" type="button" disabled={busy} onClick={onCancel}>{text("取消", "Cancel")}</button>
          <button className="button danger" type="button" disabled={busy} onClick={onConfirm}>
            {busy ? resolvedBusyLabel : resolvedConfirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
