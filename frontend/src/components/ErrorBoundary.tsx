import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * The last thing between a render error and a blank page.
 *
 * Neither entry had one, so any exception thrown during render unmounted the
 * whole tree and left the user looking at nothing — no message, no way back,
 * and nothing to tell support apart from "it went white". The 2026-08-16
 * architecture review's 6.4.
 *
 * Two recoveries, because render errors come in two kinds. "Try again" remounts
 * the subtree, which is enough when the cause was transient data. "Sign in
 * again" clears every cached answer first, which is what a corrupt or
 * identity-mismatched cache needs — and the second is why this cannot simply
 * be `window.location.reload()`.
 *
 * The message is shown; the stack is not. A user has no use for it and a
 * screenshot of it in a support channel is a small information leak. It goes
 * to the console, where an operator can find it.
 */

type Props = {
  children: ReactNode;
  /** Cleared before a re-authenticate recovery. Optional so the site entry,
   *  which has no query cache, can use the same component. */
  onResetCache?: () => void;
  label?: string;
};

type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console -- the operator's only copy
    console.error("[oryh] unhandled render error", error, info.componentStack);
  }

  private retry = () => {
    this.setState({ error: null });
  };

  private reauthenticate = () => {
    this.props.onResetCache?.();
    window.location.assign("/console/login");
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <main className="center-screen">
        <section className="state-card" role="alert">
          <span className="eyebrow">{this.props.label ?? "出错了 / Something went wrong"}</span>
          <h1>这个页面没能显示出来</h1>
          <p>{error.message}</p>
          <div className="row gap">
            <button className="button primary" onClick={this.retry}>
              重试 / Try again
            </button>
            <button className="button" onClick={this.reauthenticate}>
              重新登录 / Sign in again
            </button>
          </div>
        </section>
      </main>
    );
  }
}
