import { describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { ApiError, apiRequest } from "@/services/api-client";

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const schema = z.object({ value: z.number() });

describe("apiRequest", () => {
  it("calls the same-origin API base with query params and returns validated data", async () => {
    const fetchMock = mockFetch(200, { value: 42 });
    const data = await apiRequest("/things", {
      schema,
      query: { page: 2, q: "ลา", skip: undefined },
    });
    expect(data).toEqual({ value: 42 });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/things?page=2&q=%E0%B8%A5%E0%B8%B2");
    expect(init.credentials).toBe("same-origin");
  });

  it("maps the backend error envelope to ApiError", async () => {
    mockFetch(403, {
      error: {
        code: "permission_denied",
        message: "คุณไม่มีสิทธิ์ดำเนินการนี้",
        details: [],
        request_id: "req-12345678",
      },
    });
    const error = await apiRequest("/secret", { schema }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 403,
      code: "permission_denied",
      requestId: "req-12345678",
    });
  });

  it("returns a generic error when the response is not an envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("Internal Server Error", { status: 500 })),
    );
    const error = await apiRequest("/x", { schema }).catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 500, code: "service_unavailable" });
  });

  it("rejects responses that do not match the schema", async () => {
    mockFetch(200, { value: "not-a-number" });
    const error = await apiRequest("/x", { schema }).catch((e: unknown) => e);
    expect(error).toMatchObject({ code: "invalid_response" });
  });

  it("reports network failures as network_error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await apiRequest("/x", { schema }).catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 0, code: "network_error" });
  });

  it("accepts explicitly allowed non-2xx statuses", async () => {
    mockFetch(503, { value: 1 });
    await expect(apiRequest("/health", { schema, acceptStatuses: [503] })).resolves.toEqual({
      value: 1,
    });
  });
});
