import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiKey, listApiKeyOwners, listApiKeys, listSkills } from "./configuration";

function response(data: unknown, meta: Record<string, unknown> = {}, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    headers: new Headers({ "Content-Type": "application/json" }),
    json: async () => ({ data, meta }),
  } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "oryh_csrf=; Max-Age=0; Path=/";
});

describe("configuration API", () => {
  it("forwards skill filters and preserves server pagination metadata", async () => {
    const meta = { total: 42, page: 2, page_size: 20, pages: 3 };
    const fetchMock = vi.fn().mockResolvedValue(response([{ id: "skill-1", name: "review" }], meta));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listSkills({ page: 2, size: 20, keyword: "contract review", status: "all" }))
      .resolves.toEqual({ data: [{ id: "skill-1", name: "review" }], meta });

    const url = new URL(String(fetchMock.mock.calls[0][0]), "https://console.example");
    expect(url.pathname).toBe("/api/v1/skills");
    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      page: "2", size: "20", keyword: "contract review", status: "all",
    });
  });

  it("locally filters and pages a legacy API-key list without page metadata", async () => {
    const keys = [
      { id: "key-1", label: "finance", is_active: true },
      { id: "key-2", label: "finance-old", is_active: false },
      { id: "key-3", label: "finance-bot", is_active: true },
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(keys, { total: 3 })));

    const result = await listApiKeys({ page: 2, size: 1, keyword: "finance", status: "active" });

    expect(result.data).toEqual([keys[2]]);
    expect(result.meta).toEqual({ total: 2, page: 2, page_size: 1, pages: 2 });
  });

  it("creates a key through the CSRF-aware JSON client and unwraps the one-time secret", async () => {
    document.cookie = "oryh_csrf=test-token; Path=/";
    const created = { api_key: { id: "key-1", label: "agent" }, plain_text_api_key: "secret-once" };
    const fetchMock = vi.fn().mockResolvedValue(response(created));
    vi.stubGlobal("fetch", fetchMock);

    await expect(createApiKey({ label: "agent", user_id: null })).resolves.toEqual(created);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("test-token");
    expect(JSON.parse(String(init.body))).toEqual({ label: "agent", user_id: null });
  });

  it("searches active key owners through the keys.manage-scoped paginated endpoint", async () => {
    const meta = { total: 31, page: 2, page_size: 20, pages: 2 };
    const owner = { id: "user-31", email: "owner@example.com", name: "Owner", role: "reviewer", status: "active" };
    const fetchMock = vi.fn().mockResolvedValue(response([owner], meta));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listApiKeyOwners({ keyword: "owner", page: 2, size: 20 })).resolves.toEqual({ data: [owner], meta });
    const url = new URL(String(fetchMock.mock.calls[0][0]), "https://console.example");
    expect(url.pathname).toBe("/api/v1/tenant/api-key-owners");
    expect(Object.fromEntries(url.searchParams)).toMatchObject({ keyword: "owner", page: "2", size: "20" });
  });
});
