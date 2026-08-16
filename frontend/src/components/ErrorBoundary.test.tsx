/**
 * A render error must not leave a blank page.
 *
 * Neither entry had a boundary, so any exception during render unmounted the
 * whole tree: no message, no way back, and nothing for the user to tell
 * support except "it went white". The 2026-08-16 architecture review's 6.4.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";

function Explodes(): never {
  throw new Error("the invoice total was not a number");
}

let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  // React logs the caught error itself; the boundary logs it again for the
  // operator. Neither is a test failure.
  consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  consoleError.mockRestore();
});

describe("ErrorBoundary", () => {
  it("renders its children when nothing is wrong", () => {
    render(<ErrorBoundary><p>the invoice list</p></ErrorBoundary>);
    expect(screen.getByText("the invoice list")).toBeTruthy();
  });

  it("shows the message instead of an empty document", () => {
    render(<ErrorBoundary><Explodes /></ErrorBoundary>);

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("the invoice total was not a number")).toBeTruthy();
  });

  it("offers a retry that remounts the subtree", async () => {
    let shouldThrow = true;
    function Flaky() {
      if (shouldThrow) throw new Error("transient");
      return <p>recovered</p>;
    }
    render(<ErrorBoundary><Flaky /></ErrorBoundary>);
    expect(screen.getByRole("alert")).toBeTruthy();

    shouldThrow = false;
    await userEvent.click(screen.getByRole("button", { name: /Try again/ }));

    expect(screen.getByText("recovered")).toBeTruthy();
  });

  it("clears the cache before sending the user to sign in again", async () => {
    // The recovery that exists for a corrupt or identity-mismatched cache —
    // and the reason this cannot be a plain reload.
    const onResetCache = vi.fn();
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      value: { ...window.location, assign },
      writable: true,
    });

    render(
      <ErrorBoundary onResetCache={onResetCache}>
        <Explodes />
      </ErrorBoundary>,
    );
    await userEvent.click(screen.getByRole("button", { name: /Sign in again/ }));

    expect(onResetCache).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledWith("/console/login");
  });

  it("keeps the stack out of the page", () => {
    // A user has no use for it, and a screenshot of it in a support channel is
    // a small leak. It goes to the console instead.
    const { container } = render(<ErrorBoundary><Explodes /></ErrorBoundary>);
    expect(container.textContent).not.toContain("at Explodes");
    expect(consoleError).toHaveBeenCalled();
  });
});
