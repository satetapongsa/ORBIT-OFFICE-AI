import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
