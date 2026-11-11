import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { apiRequest, onSessionExpired } from "@/services/api-client";
import { safeRedirectPath } from "@/services/auth";

function json(status: number, body: unknown): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const unauthenticated = {
  error: { code: "unauthenticated", message: "กรุณาเข้าสู่ระบบ", details: [] },
};
const schema = z.object({ ok: z.boolean() });

describe("CSRF header", () => {
  beforeEach(() => {
    document.cookie = "aura_csrf=csrf-123; path=/";
  });
  afterEach(() => {
    document.cookie = "aura_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
  });

  it("is sent on state-changing requests only", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(json(200, { ok: true })));
    vi.stubGlobal("fetch", fetchMock);
    await apiRequest("/departments", { method: "POST", schema, body: {} });
    await apiRequest("/departments", { schema });
    const [, post] = fetchMock.mock.calls[0] as [string, RequestInit];
    const [, get] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect((post.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-123");
    expect((get.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
  });
});

describe("automatic session refresh", () => {
  it("refreshes once on 401 and retries the original request", async () => {
    document.cookie = "aura_csrf=csrf-123; path=/"; // a session exists in this browser
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(401, unauthenticated)) // original
      .mockResolvedValueOnce(json(200, { user: {}, permissions: [] })) // refresh
      .mockResolvedValueOnce(json(200, { ok: true })); // retry
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiRequest("/users", { schema })).resolves.toEqual({ ok: true });
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([
      "/api/v1/users",
      "/api/v1/auth/refresh",
      "/api/v1/users",
    ]);
  });

  it("skips the refresh call when there was never a session", async () => {
    document.cookie = "aura_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
    const fetchMock = vi.fn().mockResolvedValue(json(401, unauthenticated));
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiRequest("/users", { schema })).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("notifies listeners when the session cannot be refreshed", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(json(401, unauthenticated))
        .mockResolvedValueOnce(json(401, unauthenticated)),
    );
    const listener = vi.fn();
    const unsubscribe = onSessionExpired(listener);
    await expect(apiRequest("/users", { schema })).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it("never tries to refresh for the login endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(401, unauthenticated));
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      apiRequest("/auth/login", { method: "POST", schema, body: {} }),
    ).rejects.toMatchObject({ code: "unauthenticated" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("safeRedirectPath", () => {
  it("allows internal paths and rejects open redirects", () => {
    expect(safeRedirectPath("/account")).toBe("/account");
    expect(safeRedirectPath("/documents?id=1")).toBe("/documents?id=1");
    expect(safeRedirectPath("//evil.example.com")).toBe("/");
    expect(safeRedirectPath("/\\evil.example.com")).toBe("/");
    expect(safeRedirectPath("https://evil.example.com")).toBe("/");
    expect(safeRedirectPath("javascript:alert(1)")).toBe("/");
    expect(safeRedirectPath(null)).toBe("/");
  });
});
