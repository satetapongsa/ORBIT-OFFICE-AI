import { describe, expect, it } from "vitest";

import nextConfig from "../next.config";

async function pageHeaders(): Promise<Record<string, string>> {
  const rules = (await nextConfig.headers?.()) ?? [];
  const all = rules.find((r) => r.source === "/:path*");
  expect(all).toBeDefined();
  return Object.fromEntries((all?.headers ?? []).map((h) => [h.key, h.value]));
}

describe("page security headers", () => {
  it("sends a restrictive Content-Security-Policy outside development", async () => {
    const csp = (await pageHeaders())["Content-Security-Policy"] ?? "";
    const directives = Object.fromEntries(
      csp.split("; ").map((d) => {
        const [name, ...values] = d.split(" ");
        return [name, values.join(" ")];
      }),
    );
    expect(directives["default-src"]).toBe("'self'");
    expect(directives["frame-ancestors"]).toBe("'none'");
    expect(directives["object-src"]).toBe("'none'");
    expect(directives["base-uri"]).toBe("'self'");
    expect(directives["form-action"]).toBe("'self'");
    expect(directives["connect-src"]).toBe("'self'");
    // No eval and no third-party script hosts in production builds.
    expect(directives["script-src"]).toBe("'self' 'unsafe-inline'");
    expect(csp).toContain("upgrade-insecure-requests");
  });

  it("keeps the other hardening headers", async () => {
    const headers = await pageHeaders();
    expect(headers["X-Frame-Options"]).toBe("DENY");
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["Permissions-Policy"]).toContain("camera=()");
  });
});
