import { useFocusTrap } from "../useFocusTrap";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { useI18n } from "../../i18n";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  busy?: boolean;
  error?: string | null;
  kicker?: string;
  confirmLabel?: string;
  tone?: "danger" | "primary";
  busyLabel?: string;
  scrimLabel?: string;
  // the facts about to be written, when the confirmation is a write
  children?: ReactNode;
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
  tone = "danger",
  busyLabel,
  scrimLabel,
  children,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const { text } = useI18n();
  const resolvedKicker = kicker ?? text("归档确认", "Archive confirmation");
  const resolvedConfirmLabel = confirmLabel ?? text("确认归档", "Confirm archive");
  const resolvedBusyLabel = busyLabel ?? text("正在归档…", "Archiving…");
  const resolvedScrimLabel = scrimLabel ?? text("取消归档", "Cancel archive");
  const id = useId();
  const panelRef = useRef<HTMLElement>(null);
  useFocusTrap(panelRef, open);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const cancelHandlerRef = useRef(onCancel);
  const busyRef = useRef(busy);
  cancelHandlerRef.current = onCancel;
  busyRef.current = busy;
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancelRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) cancelHandlerRef.current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("keydown", onKeyDown); document.body.style.overflow = overflow; previous?.focus(); };
  }, [open]);

  if (!open) return null;
  return (
    <div className="dialog-layer">
      <button className="drawer-scrim" type="button" aria-label={resolvedScrimLabel} disabled={busy} onClick={onCancel} />
      <section ref={panelRef} className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`}>
        <span className={tone === "danger" ? "danger-kicker" : "eyebrow"}>{resolvedKicker}</span>
        <h2 id={`${id}-title`}>{title}</h2>
        <p id={`${id}-description`}>{description}</p>
        {children}
        {error && <div className="form-error" role="alert">{error}</div>}
        <div className="dialog-actions">
          <button ref={cancelRef} className="button" type="button" disabled={busy} onClick={onCancel}>{text("取消", "Cancel")}</button>
          <button className={`button ${tone}`} type="button" disabled={busy} onClick={onConfirm}>
            {busy ? resolvedBusyLabel : resolvedConfirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
