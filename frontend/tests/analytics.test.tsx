import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnalyticsView, bangkokDay } from "@/features/analytics/components/analytics-view";
import type { AnalyticsOverview } from "@/services/analytics";

import { createWrapper, json, mockApi } from "./fixtures";

vi.mock("next/navigation", () => ({ usePathname: () => "/analytics" }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

let permissions = new Set<string>();
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({
    me: { user: { id: "u-boss", department: { id: "d-1", code: "SALES", name: "ฝ่ายขาย" } } },
    has: (p: string) => permissions.has(p),
  }),
}));

const MANAGER = ["analytics:read_own", "analytics:read_department", "reports:export", "ai:chat"];

function overview(overrides: Partial<AnalyticsOverview> = {}): AnalyticsOverview {
  const daily = Array.from({ length: 30 }, (_, i) => ({
    date: `2026-11-${String((i % 28) + 1).padStart(2, "0")}`,
    opened: i % 3,
    closed: i % 2,
  }));
  return {
    scope: "department",
    department: { id: "d-1", code: "SALES", name: "ฝ่ายขาย" },
    date_from: "2026-10-14",
    date_to: "2026-11-12",
    timezone: "Asia/Bangkok",
    generated_at: "2026-11-12T03:00:00Z",
    available_scopes: ["own", "department"],
    can_export: true,
    tasks: {
      open: 5,
      overdue: 2,
      created: 8,
      completed: 6,
      completion_rate: 0.75,
      avg_completion_hours: 30.5,
      by_status: [
        { key: "TODO", count: 3 },
        { key: "COMPLETED", count: 6 },
      ],
      open_by_priority: [{ key: "HIGH", count: 2 }],
      daily,
      workload: [
        { user: { id: "u-alice", display_name: "อลิซ ใจดี" }, open: 3, overdue: 2, completed: 4 },
      ],
    },
    tickets: {
      open: 1,
      opened: 2,
      resolved: 1,
      avg_resolution_hours: 72,
      by_status: [{ key: "OPEN", count: 1 }],
      by_category: [{ key: "PRINTER", count: 2 }],
      daily,
    },
    documents: { total: 4, uploaded: 1, by_category: [{ key: "POLICY", count: 4 }] },
    ...overrides,
  };
}

beforeEach(() => {
  permissions = new Set(MANAGER);
  document.cookie = "aura_csrf=csrf-token; path=/";
});

describe("bangkokDay", () => {
  it("uses the Bangkok calendar day", () => {
    const lateUtc = new Date("2026-11-11T18:30:00Z"); // 01:30 on the 12th in Bangkok
    expect(bangkokDay(0, lateUtc)).toBe("2026-11-12");
    expect(bangkokDay(29, lateUtc)).toBe("2026-10-14");
  });
});

describe("AnalyticsView", () => {
  it("opens the widest permitted scope and shows the figures", async () => {
    const fetchMock = mockApi({
      "GET /api/v1/analytics/overview": () => json(overview()),
      "GET /api/v1/ai/status": () =>
        json({ enabled: false, provider: null, model: null, tools: [], max_message_chars: 4000 }),
    });
    render(<AnalyticsView />, { wrapper: createWrapper() });

    const metrics = await screen.findAllByTestId("metric");
    expect(metrics[0]).toHaveTextContent("งานที่ยังไม่เสร็จ");
    expect(metrics[0]).toHaveTextContent("5");
    expect(metrics[2]).toHaveTextContent("75%");
    expect(metrics[3]).toHaveTextContent("30.5 ชม.");
    expect(metrics[5]).toHaveTextContent("3 วัน");
    const url = new URL(String(fetchMock.mock.calls[0]?.[0]), "http://x");
    expect(url.searchParams.get("scope")).toBe("department");
    expect(url.searchParams.get("date_to")).toBe(bangkokDay(0));
    expect(url.searchParams.get("date_from")).toBe(bangkokDay(29));

    expect(screen.getByRole("tab", { name: /แผนกของฉัน · ฝ่ายขาย/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(within(screen.getByTestId("workload")).getByText("อลิซ ใจดี")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "แจ้งปัญหาตามหมวด" })).toHaveTextContent(
      "เครื่องพิมพ์",
    );
    expect(screen.getByRole("button", { name: "Excel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PDF" })).toBeInTheDocument();
    expect(await screen.findByText(/ผู้ช่วย AI ยังไม่ได้เปิดใช้งาน/)).toBeInTheDocument();
  });

  it("hides exports and other scopes for employees", async () => {
    permissions = new Set(["analytics:read_own"]);
    const fetchMock = mockApi({
      "GET /api/v1/analytics/overview": () =>
        json(
          overview({
            scope: "own",
            department: null,
            available_scopes: ["own"],
            can_export: false,
            tasks: { ...overview().tasks, workload: [] },
          }),
        ),
    });
    render(<AnalyticsView />, { wrapper: createWrapper() });
    await screen.findAllByTestId("metric");
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Excel" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("workload")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-summary")).not.toBeInTheDocument();
    expect(
      new URL(String(fetchMock.mock.calls[0]?.[0]), "http://x").searchParams.get("scope"),
    ).toBe("own");
  });

  it("changes the period and asks the assistant for a summary", async () => {
    let summaryBody: unknown = null;
    const fetchMock = mockApi({
      "GET /api/v1/analytics/overview": () => json(overview()),
      "GET /api/v1/ai/status": () =>
        json({
          enabled: true,
          provider: "scripted",
          model: "m",
          tools: [],
          max_message_chars: 4000,
        }),
      "POST /api/v1/analytics/summary": (_u, init) => {
        summaryBody = JSON.parse(String(init?.body));
        return json({
          summary: "• งานค้าง 5 งาน <script>",
          model: "m",
          generated_at: "2026-11-12T03:00:00Z",
        });
      },
    });
    render(<AnalyticsView />, { wrapper: createWrapper() });
    await screen.findAllByTestId("metric");

    await userEvent.selectOptions(screen.getByLabelText("ช่วงเวลา"), "7");
    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          (c) => new URL(String(c[0]), "http://x").searchParams.get("date_from") === bangkokDay(6),
        ),
      ).toBe(true),
    );

    await userEvent.click(await screen.findByRole("button", { name: "สรุปรายงานนี้" }));
    expect(await screen.findByText("• งานค้าง 5 งาน <script>")).toBeInTheDocument();
    expect(summaryBody).toEqual({
      scope: "department",
      date_from: bangkokDay(6),
      date_to: bangkokDay(0),
    });
  });

  it("downloads exports with the same filters", async () => {
    const fetchMock = mockApi({
      "GET /api/v1/analytics/overview": () => json(overview()),
      "GET /api/v1/ai/status": () =>
        json({ enabled: false, provider: null, model: null, tools: [], max_message_chars: 4000 }),
      "GET /api/v1/reports/overview.xlsx": () =>
        new Response(new Blob(["x"]), {
          headers: { "Content-Disposition": 'attachment; filename="aura-report.xlsx"' },
        }),
    });
    URL.createObjectURL = vi.fn(() => "blob:report");
    URL.revokeObjectURL = vi.fn();
    render(<AnalyticsView />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: "Excel" }));
    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find((c) => String(c[0]).includes("overview.xlsx"));
      expect(call).toBeDefined();
      const url = new URL(String(call?.[0]), "http://x");
      expect(url.searchParams.get("scope")).toBe("department");
      expect(url.searchParams.get("date_from")).toBe(bangkokDay(29));
    });
  });
});
