import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, MagnifyingGlass, Plus, X } from "@phosphor-icons/react";
import { useI18n } from "../i18n";
import type { NavigationGroup } from "../navigation";
import { useFocusTrap } from "./useFocusTrap";

type CommandMenuProps = {
  groups: NavigationGroup[];
  mode: "navigate" | "create";
  onClose: () => void;
};

export function CommandMenu({ groups, mode, onClose }: CommandMenuProps) {
  const { t, text } = useI18n();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const id = useId();
  const panel = useRef<HTMLElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  useFocusTrap(panel, true);

  const entries = useMemo(
    () =>
      groups
        .flatMap((group) => group.items)
        .filter((item) => mode === "navigate" || item.createLabel)
        .map((item) => ({
          ...item,
          title:
            mode === "create" && item.createLabel
              ? text(...item.createLabel)
              : t(item.label),
          to: mode === "create" ? `${item.href}?create=1` : item.href,
        })),
    [groups, mode, t, text],
  );
  const matches = entries.filter((item) =>
    `${item.title} ${item.description.join(" ")} ${item.href} ${item.createLabel?.join(" ") ?? ""}`
      .toLocaleLowerCase()
      .includes(query.trim().toLocaleLowerCase()),
  );
  const selected = Math.min(active, Math.max(0, matches.length - 1));

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    input.current?.focus();
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  useEffect(() => {
    panel.current
      ?.querySelector('[aria-selected="true"]')
      ?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);

  const choose = (to: string) => {
    onClose();
    navigate(to);
  };
  return (
    <div
      className="command-layer"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <button
        className="command-scrim"
        aria-label={text("关闭快捷查找", "Close quick finder")}
        onClick={onClose}
      />
      <section
        ref={panel}
        className="command-menu"
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
      >
        <header>
          <div>
            <span className="eyebrow">ORYH CONSOLE</span>
            <h2 id={`${id}-title`}>
              {mode === "create"
                ? text("新建记录", "Create a record")
                : text("查找页面与功能", "Find a page or action")}
            </h2>
          </div>
          <button
            className="icon-button"
            type="button"
            onClick={onClose}
            aria-label={text("关闭", "Close")}
          >
            <X size={20} />
          </button>
        </header>
        <div className="command-input">
          <MagnifyingGlass size={20} aria-hidden />
          <input
            ref={input}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            role="combobox"
            aria-expanded="true"
            aria-autocomplete="list"
            aria-controls={`${id}-results`}
            aria-activedescendant={
              matches.length ? `${id}-option-${selected}` : undefined
            }
            aria-label={text("搜索页面或功能", "Search pages or actions")}
            placeholder={text(
              "输入客户、产品、待办…",
              "Try customers, products, to-dos…",
            )}
            onKeyDown={(event) => {
              if (
                (event.key === "ArrowDown" || event.key === "ArrowUp") &&
                matches.length
              ) {
                event.preventDefault();
                setActive(
                  (selected +
                    (event.key === "ArrowDown" ? 1 : -1) +
                    matches.length) %
                    matches.length,
                );
              }
              if (event.key === "Enter" && matches[selected]) {
                event.preventDefault();
                choose(matches[selected].to);
              }
            }}
          />
        </div>
        <div
          id={`${id}-results`}
          className="command-results"
          role="listbox"
          aria-label={text("匹配功能", "Matching actions")}
        >
          {matches.map((item, index) => (
            <button
              type="button"
              role="option"
              tabIndex={-1}
              id={`${id}-option-${index}`}
              aria-selected={selected === index}
              key={item.href}
              onClick={() => choose(item.to)}
            >
              {mode === "create" ? (
                <Plus size={20} aria-hidden />
              ) : (
                <item.icon size={20} aria-hidden />
              )}
              <span>
                <strong>{item.title}</strong>
                <small>{text(...item.description)}</small>
              </span>
              <ArrowRight size={16} aria-hidden />
            </button>
          ))}
        </div>
        {matches.length === 0 && (
          <p className="command-empty" role="status">
            {text(
              "没有匹配项，试试其他名称。",
              "No matches. Try another name.",
            )}
          </p>
        )}
        <footer>
          <span>{text("↑ ↓ 选择", "↑ ↓ Select")}</span>
          <span>{text("↵ 打开", "↵ Open")}</span>
          <span>Esc {text("关闭", "Close")}</span>
        </footer>
      </section>
    </div>
  );
}
