import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { NotificationBell } from "@/features/notifications/components/notification-bell";
import { NotificationsView } from "@/features/notifications/components/notifications-view";
import { CSRF_HEADER } from "@/services/api-client";

import { createWrapper, json, mockApi, notification } from "./fixtures";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const page = (items = [notification()], unread = 1) => ({
  items,
  total: items.length,
  page: 1,
  page_size: 20,
  unread_count: unread,
});

describe("NotificationsView", () => {
  it("lists notifications, filters unread and marks all as read with CSRF", async () => {
    document.cookie = "aura_csrf=csrf-token; path=/";
    let unread = 1;
    const fetchMock = mockApi({
      "GET /api/v1/notifications": (url) =>
        json(
          url.searchParams.get("unread_only") === "true" && unread === 0
            ? page([], 0)
            : page([notification({ read_at: unread ? null : "2026-11-11T06:00:00Z" })], unread),
        ),
      "POST /api/v1/notifications/read-all": () => {
        unread = 0;
        return json({ updated: 1, unread_count: 0 });
      },
    });
    render(<NotificationsView />, { wrapper: createWrapper() });

    expect(await screen.findByText("รหัสผ่านของคุณถูกเปลี่ยนแล้ว")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ยังไม่อ่าน (1)" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /ทำเครื่องหมายว่าอ่านแล้ว: รหัสผ่าน/ }),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "อ่านทั้งหมด" }));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post).toBeDefined();
    expect(new Headers(post?.[1]?.headers).get(CSRF_HEADER)).toBe("csrf-token");

    await userEvent.click(await screen.findByRole("button", { name: "ยังไม่อ่าน" }));
    expect(await screen.findByText("ไม่มีการแจ้งเตือนที่ยังไม่อ่าน")).toBeInTheDocument();
    const urls = fetchMock.mock.calls.map(([input]) => String(input));
    expect(urls.some((u) => u.includes("unread_only=true"))).toBe(true);
  });

  it("shows an empty state", async () => {
    mockApi({ "GET /api/v1/notifications": () => json(page([], 0)) });
    render(<NotificationsView />, { wrapper: createWrapper() });
    expect(await screen.findByText("ยังไม่มีการแจ้งเตือน")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "อ่านทั้งหมด" })).toBeDisabled();
  });

  it("never renders external links from notification data", async () => {
    mockApi({
      "GET /api/v1/notifications": () =>
        json(page([notification({ link_url: "//evil.example.com" })])),
    });
    render(<NotificationsView />, { wrapper: createWrapper() });
    await screen.findByText("รหัสผ่านของคุณถูกเปลี่ยนแล้ว");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});

describe("NotificationBell", () => {
  it("shows the unread count from the API", async () => {
    mockApi({ "GET /api/v1/notifications/unread-count": () => json({ unread_count: 3 }) });
    render(<NotificationBell />, { wrapper: createWrapper() });
    expect(await screen.findByTestId("unread-badge")).toHaveTextContent("3");
    expect(screen.getByRole("button", { name: "การแจ้งเตือน (3 รายการยังไม่อ่าน)" })).toBeVisible();
  });

  it("hides the badge when everything is read", async () => {
    const fetchMock = mockApi({
      "GET /api/v1/notifications/unread-count": () => json({ unread_count: 0 }),
    });
    render(<NotificationBell />, { wrapper: createWrapper() });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByTestId("unread-badge")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "การแจ้งเตือน" })).toBeInTheDocument();
  });
});
