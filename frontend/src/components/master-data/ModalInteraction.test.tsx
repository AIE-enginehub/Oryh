import { useState } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";
import { Drawer } from "./Drawer";

afterEach(cleanup);
describe("shared record modals", () => {
  it("traps confirmation focus, starts on Cancel, and restores the trigger", async () => {
    function Example() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Archive record</button>
          <ConfirmDialog
            open={open}
            title="Archive?"
            description="History is preserved."
            onCancel={() => setOpen(false)}
            onConfirm={() => setOpen(false)}
          />
        </>
      );
    }
    const user = userEvent.setup();
    render(<Example />);
    const trigger = screen.getByRole("button", { name: "Archive record" });
    await user.click(trigger);
    const dialog = screen.getByRole("alertdialog");
    const buttons = dialog.querySelectorAll("button");
    expect(buttons[0]).toHaveFocus();
    await user.tab({ shift: true });
    expect(buttons[1]).toHaveFocus();
    await user.tab();
    expect(buttons[0]).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
  });
  it("prevents the backdrop and Escape from dismissing a pending save", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    const { container } = render(
      <Drawer
        open
        title="Edit"
        description="Customer details"
        submitLabel="Save"
        busy
        onClose={onClose}
        onSubmit={vi.fn()}
      >
        <input aria-label="Customer" />
      </Drawer>,
    );
    const scrim = container.querySelector<HTMLButtonElement>(".drawer-scrim")!;
    expect(scrim).toBeDisabled();
    await user.click(scrim);
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
  });
  it("brings a save error into focus in the edit panel", () => {
    const props = {
      open: true,
      title: "Edit",
      description: "Customer details",
      submitLabel: "Save",
      onClose: vi.fn(),
      onSubmit: vi.fn(),
    };
    const { rerender } = render(
      <Drawer {...props}>
        <input aria-label="Customer" />
      </Drawer>,
    );
    rerender(
      <Drawer {...props} error="Customer name is required">
        <input aria-label="Customer" />
      </Drawer>,
    );
    expect(screen.getByRole("alert")).toHaveFocus();
  });
});
