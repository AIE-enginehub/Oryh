import { useEffect, useState } from "react";

/**
 * Whether the viewport is at the width where the sidebar becomes a drawer.
 *
 * The breakpoint is duplicated from `styles.css` and that is a real cost — but
 * the alternative is reading a computed style every render, and the number
 * only changes when somebody deliberately redesigns the layout. Named here so
 * the next person changing it can find both.
 */
export const NARROW_MAX_WIDTH = 820;

export function useNarrowViewport(): boolean {
  const [narrow, setNarrow] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(`(max-width: ${NARROW_MAX_WIDTH}px)`).matches
      : false,
  );

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(`(max-width: ${NARROW_MAX_WIDTH}px)`);
    const update = (event: MediaQueryListEvent) => setNarrow(event.matches);
    setNarrow(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return narrow;
}
