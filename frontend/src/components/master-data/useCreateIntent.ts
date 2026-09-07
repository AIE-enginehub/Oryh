import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";

export function useCreateIntent(onCreate: () => void) {
  const [params, setParams] = useSearchParams();
  const callback = useRef(onCreate);
  callback.current = onCreate;
  const requested = params.get("create") === "1";
  const consumed = useRef(false);
  useEffect(() => {
    if (!requested) {
      consumed.current = false;
      return;
    }
    if (consumed.current) return;
    consumed.current = true;
    callback.current();
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.delete("create");
        return next;
      },
      { replace: true, preventScrollReset: true },
    );
  }, [requested, setParams]);
}
