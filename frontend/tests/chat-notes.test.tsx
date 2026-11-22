import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatRealtime } from "@/features/chat/components/chat-realtime";
import { ChatUnreadBadge } from "@/features/chat/components/chat-unread-badge";
import { ChatView } from "@/features/chat/components/chat-view";
import { NotesView } from "@/features/notes/components/notes-view";

import { createWrapper, json, mockApi } from "./fixtures";

let search = new URLSearchParams();
const push = vi.fn();
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
  useSearchParams: () => search,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({
    me: { user: { id: "me" } },
    isAuthenticated: true,
    has: (p: string) => ["chat:use", "notes:use", "ai:chat"].includes(p),
  }),
}));

const NOW = "2026-11-22T10:00:00Z";
const person = {
  id: "bob",
  display_name: "สมชาย ใจดี",
  job_title: "นักบัญชี",
  department_name: "บัญชี",
  is_active: true,
};
const message = (id: string, sender: string, body: string) => ({
  id,
  conversation_id: "c1",
  sender_id: sender,
  body,
  created_at: NOW,
});

beforeEach(() => {
  search = new URLSearchParams();
  push.mockReset();
  replace.mockReset();
  Element.prototype.scrollIntoView = vi.fn();
});

describe("ChatUnreadBadge", () => {
  it("shows the number of unread messages", async () => {
    mockApi({ "GET /api/v1/chat/unread-count": () => json({ unread_total: 3 }) });
    render(<ChatUnreadBadge />, { wrapper: createWrapper() });
    expect(await screen.findByLabelText("ข้อความใหม่ 3 ข้อความ")).toHaveTextContent("3");
  });
});

describe("ChatView", () => {
  it("shows the conversation, sends a message and marks it read", async () => {
    search = new URLSearchParams("c=c1");
    let messages = [message("m1", "bob", "ประชุมบ่ายสองนะ")];
    const fetchMock = mockApi({
      "GET /api/v1/chat/conversations": () =>
        json({
          items: [
            {
              id: "c1",
              other: person,
              last_message: messages.at(-1),
              last_message_at: NOW,
              unread_count: 1,
              other_last_read_at: null,
              other_typing: false,
            },
          ],
          unread_total: 1,
        }),
      "GET /api/v1/chat/conversations/c1/messages": () =>
        json({ items: messages, has_more: false }),
      "POST /api/v1/chat/conversations/c1/read": () => json({ unread_total: 0 }),
      "POST /api/v1/chat/conversations/c1/messages": (_url, init) => {
        const body = JSON.parse(String(init?.body)) as { body: string };
        const sent = message("m2", "me", body.body);
        messages = [...messages, sent];
        return json(sent, 201);
      },
    });
    render(<ChatView />, { wrapper: createWrapper() });

    expect(await screen.findByRole("link", { name: "สมชาย ใจดี" })).toHaveAttribute(
      "href",
      "/employees/bob",
    );
    expect(screen.getAllByText("ประชุมบ่ายสองนะ").length).toBeGreaterThan(0);
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).endsWith("/chat/conversations/c1/read")),
      ).toBe(true),
    );

    await userEvent.type(screen.getByLabelText("ข้อความ"), "รับทราบครับ{Enter}");
    expect(await screen.findByText("รับทราบครับ")).toBeInTheDocument();
    expect(screen.getByLabelText("ข้อความ")).toHaveValue("");
  });

  it("updates live: seen status and typing arrive through the long poll", async () => {
    search = new URLSearchParams("c=c1");
    const sentAt = "2026-11-22T07:05:00Z"; // 14:05 in Bangkok
    let page = {
      items: [{ ...message("m1", "me", "ส่งรายงานแล้วนะ"), created_at: sentAt }],
      has_more: false,
      other_last_read_at: null as string | null,
      other_typing: false,
    };
    const conversation = {
      id: "c1",
      other: person,
      last_message: page.items[0],
      last_message_at: sentAt,
      unread_count: 0,
      other_last_read_at: null,
      other_typing: false,
    };
    // Long poll: answers at once when `since` is stale, otherwise when the test calls wake().
    let version = 1;
    const gate: { wake: (() => void) | null } = { wake: null };
    const fetchMock = mockApi({
      "GET /api/v1/chat/events": (url) => {
        if (Number(url.searchParams.get("since")) !== version) return json({ version });
        return new Promise<Response>((resolve) => {
          gate.wake = () => resolve(json({ version }));
        }) as unknown as Response;
      },
      "GET /api/v1/chat/conversations": () => json({ items: [conversation], unread_total: 0 }),
      "GET /api/v1/chat/conversations/c1/messages": () => json(page),
      "POST /api/v1/chat/conversations/c1/read": () => json({ unread_total: 0 }),
      "POST /api/v1/chat/conversations/c1/typing": () => new Response(null, { status: 204 }),
    });
    render(
      <>
        <ChatRealtime />
        <ChatView />
      </>,
      { wrapper: createWrapper() },
    );

    expect((await screen.findAllByText("14:05")).length).toBeGreaterThan(0);
    expect(screen.getByRole("separator")).toBeInTheDocument(); // day separator
    expect(screen.getByTestId("message-status")).toHaveTextContent("ส่งแล้ว");

    page = { ...page, other_last_read_at: new Date().toISOString(), other_typing: true };
    await waitFor(() => expect(gate.wake).not.toBeNull());
    version += 1;
    gate.wake?.();
    // Delivered by the long poll, well before the 30 s safety-net poll.
    await waitFor(
      () => expect(screen.getByTestId("message-status")).toHaveTextContent(/อ่านแล้ว/),
      { timeout: 1000 },
    );
    expect(screen.getByRole("status", { name: "สมชาย ใจดี กำลังพิมพ์" })).toBeInTheDocument();

    // Typing sends at most one signal per few seconds.
    await userEvent.type(screen.getByLabelText("ข้อความ"), "กำลังตอบ");
    const typingCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/typing"));
    expect(typingCalls).toHaveLength(1);
  });

  it("lets me edit my message and shows 'แก้ไขแล้ว'", async () => {
    search = new URLSearchParams("c=c1");
    const fresh = new Date().toISOString();
    let items = [
      { ...message("m1", "bob", "ประชุมกี่โมง"), created_at: fresh },
      { ...message("m2", "me", "10 โมง"), created_at: fresh },
    ];
    const fetchMock = mockApi({
      "GET /api/v1/chat/conversations": () =>
        json({
          items: [
            {
              id: "c1",
              other: person,
              last_message: items[1],
              last_message_at: fresh,
              unread_count: 0,
              other_last_read_at: null,
              other_typing: false,
            },
          ],
          unread_total: 0,
        }),
      "GET /api/v1/chat/conversations/c1/messages": () => json({ items, has_more: false }),
      "POST /api/v1/chat/conversations/c1/read": () => json({ unread_total: 0 }),
      "PATCH /api/v1/chat/conversations/c1/messages/m2": (_url, init) => {
        const { body } = JSON.parse(String(init?.body)) as { body: string };
        const saved = { ...items[1], body, edited_at: new Date().toISOString() };
        items = [items[0], saved];
        return json(saved);
      },
    });
    render(<ChatView />, { wrapper: createWrapper() });

    // Only my own message has the menu.
    const menus = await screen.findAllByRole("button", { name: "ตัวเลือกข้อความ" });
    expect(menus).toHaveLength(1);
    await userEvent.click(menus[0]);
    await userEvent.click(await screen.findByRole("menuitem", { name: "แก้ไขข้อความ" }));
    const box = screen.getByLabelText("แก้ไขข้อความ");
    expect(box).toHaveValue("10 โมง");
    await userEvent.clear(box);
    await userEvent.type(box, "11 โมง{Enter}");

    expect(await screen.findByText("11 โมง")).toBeInTheDocument();
    expect(screen.getByText(/แก้ไขแล้ว/)).toBeInTheDocument();
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ body: "11 โมง" });
  });

  it("unsends my message for everyone and keeps long text as one paragraph", async () => {
    search = new URLSearchParams("c=c1");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const long = "บรรทัดแรก\nบรรทัดที่สอง 64565456465645654564656456545646";
    let items = [
      { ...message("m1", "bob", long), created_at: NOW },
      { ...message("m2", "me", "ส่งผิดคน"), created_at: NOW },
    ];
    const fetchMock = mockApi({
      "GET /api/v1/chat/conversations": () =>
        json({
          items: [
            {
              id: "c1",
              other: person,
              last_message: items[1],
              last_message_at: NOW,
              unread_count: 0,
              other_last_read_at: null,
              other_typing: false,
            },
          ],
          unread_total: 0,
        }),
      "GET /api/v1/chat/conversations/c1/messages": () => json({ items, has_more: false }),
      "POST /api/v1/chat/conversations/c1/read": () => json({ unread_total: 0 }),
      "DELETE /api/v1/chat/conversations/c1/messages/m2": () => {
        const gone = { ...items[1], body: "", deleted_at: NOW };
        items = [items[0], gone];
        return json(gone);
      },
    });
    render(<ChatView />, { wrapper: createWrapper() });

    // The text keeps the sender's line breaks inside one bubble.
    const bubble = await screen.findByText(/บรรทัดแรก/);
    expect(bubble.textContent).toContain("บรรทัดแรก\nบรรทัดที่สอง");
    expect(bubble.className).toContain("whitespace-pre-wrap");

    await userEvent.click(screen.getByRole("button", { name: "ตัวเลือกข้อความ" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "ยกเลิกข้อความ" }));
    expect(await screen.findByText("คุณยกเลิกข้อความนี้")).toBeInTheDocument();
    expect(screen.queryByText("ส่งผิดคน")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "ตัวเลือกข้อความ" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(true);
  });

  it("opens the thread with a colleague from their profile link", async () => {
    search = new URLSearchParams("with=bob");
    mockApi({
      "GET /api/v1/chat/conversations": () => json({ items: [], unread_total: 0 }),
      "POST /api/v1/chat/conversations": () =>
        json({
          id: "c9",
          other: person,
          last_message: null,
          last_message_at: null,
          unread_count: 0,
          other_last_read_at: null,
          other_typing: false,
        }),
    });
    render(<ChatView />, { wrapper: createWrapper() });
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat?c=c9"));
  });
});

describe("NotesView", () => {
  it("opens a note and stores an AI summary", async () => {
    search = new URLSearchParams("n=n1");
    const note = {
      id: "n1",
      title: "งานสัปดาห์นี้",
      content: "ส่งรายงานวันศุกร์",
      ai_summary: null as string | null,
      ai_summary_at: null as string | null,
      summary_outdated: false,
      content_updated_at: NOW,
      created_at: NOW,
    };
    const fetchMock = mockApi({
      "GET /api/v1/notes": () =>
        json([
          {
            id: "n1",
            title: note.title,
            preview: note.content,
            has_summary: note.ai_summary !== null,
            content_updated_at: NOW,
            created_at: NOW,
          },
        ]),
      "GET /api/v1/notes/n1": () => json(note),
      "POST /api/v1/notes/n1/summary": () => {
        note.ai_summary = "ต้องส่งรายงานภายในวันศุกร์";
        note.ai_summary_at = NOW;
        return json(note);
      },
    });
    render(<NotesView />, { wrapper: createWrapper() });

    expect(await screen.findByLabelText("หัวข้อโน้ต")).toHaveValue("งานสัปดาห์นี้");
    expect(screen.getByLabelText("เนื้อหาโน้ต")).toHaveValue("ส่งรายงานวันศุกร์");
    await userEvent.click(screen.getByRole("button", { name: "สรุปด้วย AI" }));
    expect(await screen.findByText("ต้องส่งรายงานภายในวันศุกร์")).toBeInTheDocument();
    // Nothing was edited, so no save was needed before summarising.
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
  });

  it("creates a note and opens it", async () => {
    mockApi({
      "GET /api/v1/notes": () => json([]),
      "POST /api/v1/notes": () =>
        json(
          {
            id: "n2",
            title: "โน้ตใหม่",
            content: "",
            ai_summary: null,
            ai_summary_at: null,
            summary_outdated: false,
            content_updated_at: NOW,
            created_at: NOW,
          },
          201,
        ),
    });
    render(<NotesView />, { wrapper: createWrapper() });
    expect(await screen.findByText("ยังไม่มีโน้ต")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "โน้ตใหม่" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/notes?n=n2"));
  });
});
