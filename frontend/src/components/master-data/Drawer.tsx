import { useEffect, useRef, type FormEvent, type ReactNode } from "react";
import { useI18n } from "../../i18n";

type DrawerProps = {
  open: boolean;
  title: string;
  description: string;
  submitLabel: string;
  busy?: boolean;
  submitDisabled?: boolean;
  error?: string | null;
  children: ReactNode;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function Drawer({
  open,
  title,
  description,
  submitLabel,
  busy = false,
  submitDisabled = false,
  error,
  children,
  onClose,
  onSubmit,
}: DrawerProps) {
  const { text } = useI18n();
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  const busyRef = useRef(busy);
  closeRef.current = onClose;
  busyRef.current = busy;

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const panel = panelRef.current;
    panel?.querySelector<HTMLElement>("input, select, textarea")?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) closeRef.current();
    };
    document.addEventListener("keydown", onKeyDown);
    document.body.classList.add("modal-open");
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.classList.remove("modal-open");
      previous?.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="drawer-layer">
      <button className="drawer-scrim" type="button" aria-label={text("关闭编辑面板", "Close edit panel")} onClick={onClose} />
      <section ref={panelRef} className="data-drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <header className="drawer-header">
          <div>
            <h2 id="drawer-title">{title}</h2>
            <p>{description}</p>
          </div>
          <button className="drawer-close" type="button" aria-label={text("关闭", "Close")} disabled={busy} onClick={onClose}>×</button>
        </header>
        <form className="drawer-form" onSubmit={onSubmit} noValidate>
          <div className="drawer-body">
            {error && <div className="form-error" role="alert">{error}</div>}
            {children}
          </div>
          <footer className="drawer-footer">
            <button className="button" type="button" disabled={busy} onClick={onClose}>{text("取消", "Cancel")}</button>
            <button className="button primary" type="submit" disabled={busy || submitDisabled}>
              {busy ? text("正在保存…", "Saving…") : submitLabel}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
