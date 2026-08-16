/**
 * One place that owns what a 401 means, and what a new identity means.
 *
 * Before this, `SessionBoundary` redirected on a 401 from the bootstrap query
 * and nothing else did. A session that expired while somebody was working —
 * which is the ordinary way sessions end — surfaced as a failed table, a
 * failed save, an error toast, on whatever page they happened to be on. The
 * app still believed it was signed in, because the only query that could tell
 * it otherwise had been answered half an hour earlier.
 *
 * And logging in only invalidated the bootstrap key, so every other cached
 * answer belonged to the previous identity: open the console as one user, sign
 * in as another, and the second user reads the first one's customers until
 * each query happens to refetch.
 *
 * The 2026-08-16 architecture review's 6.1. Two rules, one owner:
 *
 *   a 401 from ANY query transitions to signed-out, once, remembering where
 *   a new identity clears the whole cache, not one key
 *
 * 403 is deliberately untouched. "You are not signed in" and "you may not do
 * this" are different answers and collapsing them sends a member who opened an
 * admin page to the login screen, where signing in again changes nothing.
 */

import { QueryCache, QueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";

/** Where the user was when the session ended, for the login page to return to. */
export type SignedOutReason = { returnTo: string };

type Listener = (reason: SignedOutReason) => void;

const listeners = new Set<Listener>();

/** Guards against a burst: eight queries on a dashboard all 401 at once, and
 *  the user should be sent to the login page once, from the page they were on
 *  — not eight times, and not from wherever the last one resolved. */
let transitioning = false;

export function onSignedOut(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function reportUnauthorized(): void {
  if (transitioning) return;
  transitioning = true;
  const returnTo = `${window.location.pathname}${window.location.search}`.replace(
    /^\/console/,
    "",
  );
  for (const listener of listeners) listener({ returnTo: returnTo || "/dashboard" });
}

/** Called once the app has finished moving to the login screen. */
export function resolveSignedOut(): void {
  transitioning = false;
}

export function isTransitioning(): boolean {
  return transitioning;
}

/**
 * Everything cached belongs to the identity that fetched it. A new sign-in
 * gets a new cache — not an invalidated bootstrap key beside stale customers,
 * projects and todos from whoever was signed in before.
 */
export async function adoptNewIdentity(queryClient: QueryClient): Promise<void> {
  queryClient.clear();
  resolveSignedOut();
  await queryClient.invalidateQueries({ queryKey: ["console", "bootstrap"] });
}

export function createConsoleQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      // Every query, not the one that happened to be the session probe.
      onError: (error) => {
        if (error instanceof ApiError && error.status === 401) {
          reportUnauthorized();
        }
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Retrying an expired session is a retry that cannot succeed, and it
        // delays the redirect by exactly as long as it takes to fail again.
        retry: (failureCount, error) =>
          !(error instanceof ApiError && (error.status === 401 || error.status === 403)) &&
          failureCount < 1,
      },
    },
  });
}
