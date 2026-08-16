/**
 * `aria-modal` and an off-screen transform are claims. These are the mechanisms.
 *
 * The drawer declared `role="dialog" aria-modal="true"`, focused its first
 * field, handled Escape and restored focus — everything except keeping Tab
 * inside it. And the mobile sidebar was moved off-screen with a CSS transform,
 * which hides it from sight and from nothing else: every nav link stayed in
 * the tab order and in the accessibility tree.
 *
 * The 2026-08-16 architecture review's 6.3. Both are the same shape as the rest
 * of this week — a property asserted in markup with nothing enforcing it.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef } from "react";
import { describe, expect, it } from "vitest";

import { useFocusTrap } from "./useFocusTrap";

function Modal({ open }: { open: boolean }) {
  const panel = useRef<HTMLElement>(null);
  useFocusTrap(panel, open);
  if (!open) return null;
  return (
    <div>
      <section ref={panel} role="dialog" aria-modal="true">
        <input aria-label="first" />
        <input aria-label="second" />
        <button type="button">save</button>
      </section>
    </div>
  );
}

function Page({ open }: { open: boolean }) {
  return (
    <>
      <div>
        <button type="button">behind the modal</button>
      </div>
      <Modal open={open} />
    </>
  );
}

/**
 * jsdom does not implement `inert` as a real property, so an untouched element
 * reads `undefined` rather than `false`. What matters either way is whether
 * the flag is set — the enforcement itself is the browser's, and asserting
 * `=== false` would be asserting a jsdom detail.
 */
const isInert = (node: HTMLElement) => Boolean(node.inert);

describe("useFocusTrap", () => {
  it("wraps forward from the last element to the first", async () => {
    render(<Page open />);
    const first = screen.getByLabelText("first");
    const save = screen.getByRole("button", { name: "save" });
    save.focus();

    await userEvent.tab();

    expect(document.activeElement).toBe(first);
  });

  it("wraps backward from the first element to the last", async () => {
    render(<Page open />);
    const first = screen.getByLabelText("first");
    const save = screen.getByRole("button", { name: "save" });
    first.focus();

    await userEvent.tab({ shift: true });

    expect(document.activeElement).toBe(save);
  });

  it("makes everything behind the modal inert", () => {
    // The half `aria-hidden` alone cannot do: out of the tab order AND out of
    // the accessibility tree, which is what `aria-modal` was asserting.
    const { container } = render(<Page open />);
    const backdrop = container.firstElementChild as HTMLElement;

    expect(isInert(backdrop)).toBe(true);
  });

  it("gives the page back when the modal closes", () => {
    const { container, rerender } = render(<Page open />);
    const backdrop = container.firstElementChild as HTMLElement;
    expect(isInert(backdrop)).toBe(true);

    rerender(<Page open={false} />);

    expect(isInert(backdrop)).toBe(false);
  });

  it("does nothing while closed", () => {
    const { container } = render(<Page open={false} />);
    const backdrop = container.firstElementChild as HTMLElement;
    expect(isInert(backdrop)).toBe(false);
  });
});
