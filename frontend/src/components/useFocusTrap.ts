import { useEffect, type RefObject } from "react";

/**
 * Keeps Tab inside a modal, and keeps the page behind it out of reach.
 *
 * The drawer declared `role="dialog" aria-modal="true"`, focused its first
 * field, handled Escape and restored focus on close — everything except the
 * part that makes those true. Tab walked straight out of it into the table
 * behind, which is still rendered, still focusable and still announced, so
 * `aria-modal` was a promise the markup did not keep. The 2026-08-16
 * architecture review's 6.3.
 *
 * `inert` on the siblings does the work that `aria-hidden` alone cannot: it
 * removes them from the tab order AND from the accessibility tree, and it is
 * what makes the wrap below the only way out.
 */
export function useFocusTrap(
  panelRef: RefObject<HTMLElement | null>,
  active: boolean,
): void {
  useEffect(() => {
    if (!active) return;
    const panel = panelRef.current;
    if (!panel) return;

    // Siblings at EVERY level from the panel up to <body>, not just the top.
    // The first version walked up to a child of <body> and inerted that node's
    // siblings — which in this app is nothing at all, because everything
    // renders inside a single `#root`. The page behind stayed fully live and
    // the trap looked like it worked.
    const backdrop: HTMLElement[] = [];
    for (let node: HTMLElement = panel; node.parentElement; node = node.parentElement) {
      for (const sibling of node.parentElement.children) {
        if (sibling !== node && sibling instanceof HTMLElement) backdrop.push(sibling);
      }
      if (node.parentElement === document.body) break;
    }
    const previouslyInert = backdrop.map((node) => node.inert);
    for (const node of backdrop) node.inert = true;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      // No `offsetParent` visibility filter: jsdom reports null for everything,
      // which emptied the list and made the trap a no-op under test. The
      // selector already excludes disabled and tabindex=-1, and a `hidden`
      // element inside an open panel is not a case these panels have.
      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((node) => !node.hasAttribute("hidden"));
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const current = document.activeElement;

      // Wrap at both ends, and pull focus back in if it has escaped — which it
      // has whenever the browser moved it before this handler ran.
      if (event.shiftKey && (current === first || !panel.contains(current))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (current === last || !panel.contains(current))) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      backdrop.forEach((node, index) => {
        node.inert = previouslyInert[index];
      });
    };
  }, [panelRef, active]);
}
