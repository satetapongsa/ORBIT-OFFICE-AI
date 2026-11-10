import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { SystemStatusPanel } from "@/features/system-status/components/system-status-panel";

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const readiness = {
  status: "error",
  service: "AURA OFFICE AI",
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

  it("shows an error state when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<SystemStatusPanel />, { wrapper: Wrapper });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ API ได้",
    );
  });
});
