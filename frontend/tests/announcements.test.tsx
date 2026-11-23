import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnnouncementsView } from "@/features/announcements/components/announcements-view";

import { createWrapper, json, mockApi } from "./fixtures";

let permissions: string[] = [];
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({ has: (p: string) => permissions.includes(p) }),
}));

const base = {
  body: "หยุดยาวช่วงปีใหม่\n\nกลับมาทำงานวันที่ 3 ม.ค.",
  important: false,
  pinned: false,
  department_id: null,
  department_name: null,
  author_name: "ฝ่ายบุคคล",
  published_at: "2026-11-23T03:00:00Z",
  expires_at: null,
  expired: false,
  edited: false,
  is_read: false,
};

beforeEach(() => {
  permissions = [];
  Element.prototype.scrollIntoView = vi.fn();
});

describe("AnnouncementsView", () => {
  it("lists announcements, opens one and marks it read", async () => {
    let items = [
      { ...base, id: "a1", title: "วันหยุดปีใหม่", important: true, pinned: true },
      { ...base, id: "a2", title: "ทำความสะอาดออฟฟิศ", is_read: true },
    ];
    const fetchMock = mockApi({
      "GET /api/v1/announcements": () =>
        json({ items, unread_count: items.filter((a) => !a.is_read).length }),
      "POST /api/v1/announcements/a1/read": () => {
        items = items.map((a) => (a.id === "a1" ? { ...a, is_read: true } : a));
        return json({ unread_count: 0 });
      },
    });
    render(<AnnouncementsView />, { wrapper: createWrapper() });

    expect(await screen.findByText("วันหยุดปีใหม่")).toBeInTheDocument();
    expect(screen.getByText("ปักหมุด")).toBeInTheDocument();
    expect(screen.getByText("สำคัญ")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ยังไม่อ่าน (1)" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "สร้างประกาศ" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /วันหยุดปีใหม่/ }));
    expect(await screen.findByText("กลับมาทำงานวันที่ 3 ม.ค.")).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/announcements/a1/read"))).toBe(
        true,
      ),
    );
    await userEvent.click(await screen.findByRole("button", { name: "ยังไม่อ่าน" }));
    expect(await screen.findByText("อ่านครบทุกประกาศแล้ว")).toBeInTheDocument();
  });

  it("lets HR publish an announcement for one department", async () => {
    permissions = ["announcements:manage"];
    const fetchMock = mockApi({
      "GET /api/v1/announcements": () => json({ items: [], unread_count: 0 }),
      "GET /api/v1/departments": () => json([{ id: "d1", code: "SALES", name: "ฝ่ายขาย" }]),
      "POST /api/v1/announcements": (_u, init) =>
        json({ ...base, ...JSON.parse(String(init?.body)), id: "new", is_read: true }, 201),
    });
    render(<AnnouncementsView />, { wrapper: createWrapper() });

    await userEvent.click(await screen.findByRole("button", { name: "สร้างประกาศ" }));
    await userEvent.type(screen.getByLabelText("หัวข้อ"), "ประชุมทีมขาย");
    await userEvent.type(screen.getByLabelText("รายละเอียด"), "วันศุกร์ 10 โมง");
    await screen.findByRole("option", { name: "เฉพาะฝ่ายขาย" });
    await userEvent.selectOptions(screen.getByLabelText("ผู้รับประกาศ"), "d1");
    await userEvent.click(screen.getByLabelText("ประกาศสำคัญ"));
    await userEvent.click(screen.getByRole("button", { name: "เผยแพร่" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true),
    );
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      title: "ประชุมทีมขาย",
      body: "วันศุกร์ 10 โมง",
      important: true,
      pinned: false,
      department_id: "d1",
      expires_at: null,
      notify: true,
    });
  });
});
