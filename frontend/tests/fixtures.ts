import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { vi } from "vitest";

import type { DashboardSummary } from "@/services/dashboard";
import type { AppNotification } from "@/services/notifications";

export function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client }, children);
  };
}

type Handler = (url: URL, init: RequestInit | undefined) => Response;

/** Stub `fetch` with a router; returns the mock so tests can inspect calls. */
export function mockApi(routes: Record<string, Handler>) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://127.0.0.1:3000");
    const key = `${init?.method ?? "GET"} ${url.pathname}`;
    const handler = routes[key];
    if (!handler) {
      return Promise.resolve(
        new Response(JSON.stringify({ error: { code: "not_found", message: key } }), {
          status: 404,
        }),
      );
    }
    return Promise.resolve(handler(url, init));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

export function notification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: "n-1",
    type: "SECURITY",
    title: "รหัสผ่านของคุณถูกเปลี่ยนแล้ว",
    body: "ระบบได้ออกจากระบบอุปกรณ์อื่นทั้งหมดแล้ว",
    link_url: "/account",
    entity_type: "user",
    entity_id: "u-1",
    read_at: null,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

const days = Array.from({ length: 14 }, (_, i) => {
  const d = new Date(Date.UTC(2026, 9, 29 + i));
  return d.toISOString().slice(0, 10);
});

export function employeeSummary(): DashboardSummary {
  return {
    generated_at: "2026-11-11T06:00:00Z",
    timezone: "Asia/Bangkok",
    period_days: 14,
    account: {
      display_name: "สมชาย ใจดี",
      job_title: "เจ้าหน้าที่ขาย",
      department: { id: "d-1", code: "SALES", name: "ฝ่ายขาย" },
      roles: [{ id: "r-1", code: "EMPLOYEE", name: "พนักงาน" }],
      last_login_at: "2026-11-11T05:00:00Z",
      previous_login_at: "2026-11-10T02:00:00Z",
      password_changed_at: "2026-11-01T02:00:00Z",
      active_sessions: 2,
    },
    notifications: {
      unread_count: 2,
      latest: [
        notification(),
        notification({
          id: "n-2",
          type: "DOCUMENT",
          title: "มีการแชร์เอกสารให้คุณ: นโยบายการลา",
          link_url: "/documents/doc-1",
        }),
      ],
    },
    my_activity: {
      daily_sign_ins: days.map((date, i) => ({ date, count: i === 13 ? 3 : i % 3 })),
      recent: [
        {
          id: "a-1",
          action: "auth.login",
          occurred_at: "2026-11-11T05:00:00Z",
          actor: { id: "u-1", display_name: "สมชาย ใจดี" },
          entity_type: "user",
        },
        {
          id: "a-2",
          action: "user.updated",
          occurred_at: "2026-11-10T05:00:00Z",
          actor: { id: "u-9", display_name: "ผู้ดูแล ระบบ" },
          entity_type: "user",
        },
      ],
    },
    documents: {
      accessible_count: 7,
      my_documents: 2,
      my_processing: 1,
      my_failed: 0,
      recent: [
        {
          id: "doc-1",
          title: "นโยบายการลา",
          category: "POLICY",
          file_type: "PDF",
          processing_status: "READY",
          updated_at: "2026-11-11T05:00:00Z",
        },
      ],
    },
    organization: null,
    security: null,
  };
}

export function adminSummary(): DashboardSummary {
  return {
    ...employeeSummary(),
    organization: {
      active_users: 42,
      inactive_users: 3,
      departments: 5,
      users_by_department: [
        { department: { id: "d-1", code: "SALES", name: "ฝ่ายขาย" }, count: 20 },
        { department: null, count: 2 },
      ],
    },
    security: {
      sign_ins: 120,
      failed_sign_ins: 9,
      rate_limited: 1,
      daily: days.map((date, i) => ({ date, sign_ins: 8 + i, failed_sign_ins: i % 2 })),
      recent: [
        {
          id: "a-3",
          action: "auth.login_failed",
          occurred_at: "2026-11-11T05:30:00Z",
          actor: null,
          entity_type: null,
        },
      ],
    },
  };
}
