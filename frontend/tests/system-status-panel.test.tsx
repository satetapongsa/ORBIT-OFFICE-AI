import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SystemStatusPanel } from "@/features/system-status/components/system-status-panel";

let permissions = new Set<string>();
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({ has: (p: string) => permissions.has(p) }),
}));

beforeEach(() => {
  permissions = new Set(["system:configure"]);
});

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const readiness = {
  status: "error",
  service: "ORBIT OFFICE AI",
  version: "0.1.0",
  environment: "development",
  checked_at: "2026-11-10T08:00:00Z",
  components: [
    { name: "database", status: "ok", required: true, latency_ms: 3.2, detail: "pgvector enabled" },
    { name: "redis", status: "error", required: true, latency_ms: 1.1, detail: "unavailable" },
    { name: "object_storage", status: "ok", required: true, latency_ms: 5, detail: null },
    { name: "ai_chat", status: "not_configured", required: false },
    { name: "ai_embedding", status: "not_configured", required: false },
  ],
};

describe("SystemStatusPanel", () => {
  it("renders component statuses from a 503 readiness report", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(readiness), { status: 503 })),
    );
    render(<SystemStatusPanel />, { wrapper: Wrapper });
    expect(await screen.findByText("ระบบขัดข้องบางส่วน")).toBeInTheDocument();
    expect(screen.getByTestId("component-redis")).toHaveTextContent("ขัดข้อง");
    expect(screen.getByTestId("component-redis")).toHaveTextContent("ไม่สามารถเชื่อมต่อได้");
    expect(screen.getByTestId("component-database")).toHaveTextContent("pgvector enabled");
    expect(screen.getByTestId("component-database")).toHaveTextContent("ปกติ");
    expect(screen.getByTestId("component-ai_chat")).toHaveTextContent("ยังไม่ได้ตั้งค่า");
  });

  it("asks administrators' details from /health/details", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(new Response(JSON.stringify(readiness), { status: 503 })),
      );
    vi.stubGlobal("fetch", fetchMock);
    render(<SystemStatusPanel />, { wrapper: Wrapper });
    await screen.findByText("ระบบขัดข้องบางส่วน");
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/v1/health/details");
  });

  it("shows only the overall status when details are withheld", async () => {
    permissions = new Set();
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            ...readiness,
            status: "ok",
            environment: null,
            components: [],
            details_hidden: true,
          }),
          { status: 200 },
        ),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<SystemStatusPanel />, { wrapper: Wrapper });
    expect(await screen.findByText("ระบบพร้อมใช้งาน")).toBeInTheDocument();
    expect(screen.getByTestId("details-hidden")).toHaveTextContent("เฉพาะผู้ดูแลระบบ");
    expect(screen.queryByTestId("component-database")).not.toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/\/api\/v1\/health$/);
  });

  it("shows an error state when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<SystemStatusPanel />, { wrapper: Wrapper });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ API ได้",
    );
  });
});
