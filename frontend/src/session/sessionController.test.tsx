/**
 * The rules a 401 and a new sign-in follow, driven rather than described.
 *
 * Before this there was one 401 handler, on the bootstrap query, and logging in
 * invalidated one cache key. So a session that expired mid-work surfaced as a
 * broken table on whatever page the user was on, and a second user signing in
 * read the first one's data until each query happened to refetch.
 */

import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import {
  adoptNewIdentity,
  createConsoleQueryClient,
  isTransitioning,
  onSignedOut,
  reportUnauthorized,
  resolveSignedOut,
} from "./sessionController";

afterEach(() => {
  resolveSignedOut();
});

describe("signing out", () => {
  it("tells its listener where the user was", () => {
    const seen: string[] = [];
    const stop = onSignedOut(({ returnTo }) => seen.push(returnTo));
    window.history.replaceState({}, "", "/console/invoices?status=issued");

    reportUnauthorized();

    expect(seen).toEqual(["/invoices?status=issued"]);
    stop();
  });

  it("fires once when a page full of queries all 401 together", () => {
    // Eight widgets on a dashboard hit an expired session at the same moment.
    // The user should arrive at the login page once, from the page they were
    // on — not eight times, and not from wherever the last one resolved.
    const seen: string[] = [];
    const stop = onSignedOut(({ returnTo }) => seen.push(returnTo));

    for (let n = 0; n < 8; n += 1) reportUnauthorized();

    expect(seen).toHaveLength(1);
    stop();
  });

  it("can sign out again after the transition completes", () => {
    const seen: string[] = [];
    const stop = onSignedOut(({ returnTo }) => seen.push(returnTo));

    reportUnauthorized();
    expect(isTransitioning()).toBe(true);
    resolveSignedOut();
    reportUnauthorized();

    expect(seen).toHaveLength(2);
    stop();
  });
});

describe("the query client", () => {
  it("reports a 401 from any query, not just the session probe", async () => {
    const seen: string[] = [];
    const stop = onSignedOut(({ returnTo }) => seen.push(returnTo));
    const client = createConsoleQueryClient();

    await client
      .fetchQuery({
        queryKey: ["some", "ordinary", "table"],
        queryFn: () => Promise.reject(new ApiError(401, "session expired")),
      })
      .catch(() => undefined);

    expect(seen).toHaveLength(1);
    stop();
    client.clear();
  });

  it("leaves a 403 alone", async () => {
    // "You are not signed in" and "you may not do this" are different answers.
    // Collapsing them sends a member who opened an admin page to the login
    // screen, where signing in again changes nothing.
    const seen: string[] = [];
    const stop = onSignedOut(({ returnTo }) => seen.push(returnTo));
    const client = createConsoleQueryClient();

    await client
      .fetchQuery({
        queryKey: ["admin", "only"],
        queryFn: () => Promise.reject(new ApiError(403, "forbidden")),
      })
      .catch(() => undefined);

    expect(seen).toHaveLength(0);
    stop();
    client.clear();
  });

  it("does not retry an expired session", async () => {
    const queryFn = vi.fn(() => Promise.reject(new ApiError(401, "session expired")));
    const client = createConsoleQueryClient();

    await client.fetchQuery({ queryKey: ["x"], queryFn }).catch(() => undefined);

    expect(queryFn).toHaveBeenCalledTimes(1);
    client.clear();
  });
});

describe("adopting a new identity", () => {
  it("clears everything the previous identity fetched", async () => {
    const client = new QueryClient();
    client.setQueryData(["console", "bootstrap"], { user: "first" });
    client.setQueryData(["customers"], [{ id: "1", name: "first user's customer" }]);
    client.setQueryData(["todos"], [{ id: "t1" }]);

    await adoptNewIdentity(client);

    expect(client.getQueryData(["customers"])).toBeUndefined();
    expect(client.getQueryData(["todos"])).toBeUndefined();
    expect(client.getQueryData(["console", "bootstrap"])).toBeUndefined();
  });

  it("ends any sign-out transition in progress", async () => {
    reportUnauthorized();
    expect(isTransitioning()).toBe(true);

    await adoptNewIdentity(new QueryClient());

    expect(isTransitioning()).toBe(false);
  });
});
