import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatView } from "@/features/chat/components/chat-view";

import { createWrapper, json, mockApi } from "./fixtures";

let search = new URLSearchParams();
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => search,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({
    me: {
      user: {
        id: "me",
        display_name: "ฉัน เอง",
        department: { id: "d1", code: "SALES", name: "ฝ่ายขาย" },
      },
    },
    isAuthenticated: true,
    has: (p: string) => p === "chat:use",
  }),
}));

const T0 = "2026-11-23T09:00:00Z";
const T1 = "2026-11-23T09:05:00Z";
const member = (id: string, name: string, role: "ADMIN" | "MEMBER", read: string | null) => ({
  id,
  display_name: name,
  department_name: "ฝ่ายขาย",
  role,
  last_read_at: read,
});
const msg = (id: string, sender: string | null, name: string | null, body: string, at = T1) => ({
  id,
  group_id: "g1",
  sender_id: sender,
  sender_name: name,
  kind: sender ? "TEXT" : "SYSTEM",
  body,
  created_at: at,
  edited_at: null,
});
const summary = {
  id: "g1",
  name: "ทีมขาย",
  member_count: 3,
  my_role: "ADMIN",
  last_message: msg("m2", "me", "ฉัน เอง", "สวัสดีทีม"),
  last_message_at: T1,
  unread_count: 0,
  typing_names: [],
};

beforeEach(() => {
  search = new URLSearchParams();
  push.mockReset();
  Element.prototype.scrollIntoView = vi.fn();
});

describe("Group chat", () => {
  it("lists groups with DMs and shows names, system messages, read count and typing", async () => {
    search = new URLSearchParams("g=g1");
    mockApi({
      "GET /api/v1/chat/conversations": () => json({ items: [], unread_total: 0 }),
      "GET /api/v1/chat/groups": () => json([summary]),
      "GET /api/v1/chat/groups/g1/messages": () =>
        json({
          items: [
            msg("m0", null, null, "ฉัน เอง สร้างกลุ่ม “ทีมขาย”", T0),
            msg("m1", "bob", "สมชาย ใจดี", "ประชุมบ่ายนี้"),
            msg("m2", "me", "ฉัน เอง", "สวัสดีทีม"),
          ],
          has_more: false,
          reads: [
            member("me", "ฉัน เอง", "ADMIN", T1),
            member("bob", "สมชาย ใจดี", "MEMBER", T1),
            member("ann", "สมหญิง รักดี", "MEMBER", null),
          ],
          typing_names: ["สมหญิง รักดี"],
        }),
      "POST /api/v1/chat/groups/g1/read": () => json({ unread_total: 0 }),
    });
    render(<ChatView />, { wrapper: createWrapper() });

    const thread = await screen.findByRole("region", { name: "กลุ่ม ทีมขาย" });
    expect(await within(thread).findByText("สมชาย ใจดี")).toBeInTheDocument();
    expect(within(thread).getByTestId("system-message")).toHaveTextContent("สร้างกลุ่ม");
    expect(within(thread).getByTestId("message-status")).toHaveTextContent("อ่านแล้ว 1 คน");
    expect(within(thread).getByText("สมหญิง รักดี กำลังพิมพ์…")).toBeInTheDocument();
    const list = screen.getByRole("complementary", { name: "รายการแชท" });
    expect(within(list).getByText("ทีมขาย")).toBeInTheDocument();
    expect(within(list).getByText("คุณ: สวัสดีทีม")).toBeInTheDocument();
  });

  it("creates a group with picked people and the whole department", async () => {
    const fetchMock = mockApi({
      "GET /api/v1/chat/conversations": () => json({ items: [], unread_total: 0 }),
      "GET /api/v1/chat/groups": () => json([]),
      "GET /api/v1/directory/users": () =>
        json([
          {
            id: "bob",
            display_name: "สมชาย ใจดี",
            job_title: null,
            department: null,
            email: "bob@x",
            employee_code: "E1",
          },
        ]),
      "POST /api/v1/chat/groups": () =>
        json(
          { ...summary, last_message: null, members: [member("me", "ฉัน", "ADMIN", null)] },
          201,
        ),
    });
    const user = userEvent.setup();
    render(<ChatView />, { wrapper: createWrapper() });

    await user.click(await screen.findByRole("button", { name: "สร้างกลุ่ม" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("ชื่อกลุ่ม"), "ทีมขาย");
    await user.type(within(dialog).getByLabelText("ค้นหาสมาชิก"), "สม");
    await user.click(await within(dialog).findByRole("button", { name: /สมชาย ใจดี/ }));
    await user.click(within(dialog).getByRole("checkbox"));
    await user.click(within(dialog).getByRole("button", { name: "สร้างกลุ่ม" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/chat?g=g1"));
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      name: "ทีมขาย",
      member_ids: ["bob"],
      include_department_id: "d1",
    });
  });
});
