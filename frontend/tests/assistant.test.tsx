import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AssistantView } from "@/features/assistant/components/assistant-view";
import { MessageText } from "@/features/assistant/components/message-text";
import { parseSseBlock, type AiAction, type ChatSessionDetail } from "@/services/ai";
import { CSRF_HEADER } from "@/services/api-client";

import { createWrapper, json, mockApi } from "./fixtures";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/assistant",
  useSearchParams: () => searchParams,
}));

let searchParams = new URLSearchParams();
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const TASK_ID = "0b6f2b5e-1c2d-4e5f-8a9b-0c1d2e3f4a5b";

const status = (enabled = true) => ({
  enabled,
  provider: enabled ? "anthropic" : null,
  model: enabled ? "claude-opus-5-5" : null,
  tools: enabled
    ? [
        { name: "get_my_tasks", label: "ค้นหางานของคุณ", requires_confirmation: false },
        { name: "create_task", label: "เตรียมสร้างงาน", requires_confirmation: true },
      ]
    : [],
  max_message_chars: 4000,
});

const session = {
  id: "s-1",
  title: "สร้างงานให้หน่อย",
  created_at: "2026-11-11T05:00:00Z",
  last_message_at: "2026-11-11T05:00:00Z",
};

const action = (overrides: Partial<AiAction> = {}): AiAction => ({
  id: "a-1",
  tool_name: "create_task",
  summary: "สร้างงาน “ทำรายงาน” · ความสำคัญสูง · ผู้รับผิดชอบ: คุณเอง",
  status: "PENDING",
  result: null,
  error: null,
  expires_at: "2026-11-11T05:15:00Z",
  decided_at: null,
  created_at: "2026-11-11T05:00:00Z",
  ...overrides,
});

const stored = (a: AiAction): ChatSessionDetail => ({
  ...session,
  messages: [
    {
      id: "m-1",
      role: "user",
      citations: [],
      content: "สร้างงานทำรายงานให้หน่อย",
      created_at: "2026-11-11T05:00:00Z",
    },
    {
      id: "m-2",
      role: "tool",
      citations: [],
      content: "",
      tool_name: "create_task",
      tool_label: "เตรียมสร้างงาน",
      tool_ok: true,
      action_id: "a-1",
      created_at: "2026-11-11T05:00:01Z",
    },
    {
      id: "m-3",
      role: "assistant",
      citations: [],
      content: "เตรียมงานไว้แล้ว กรุณากดยืนยัน",
      created_at: "2026-11-11T05:00:02Z",
    },
  ],
  actions: [a],
});

function sse(events: [string, unknown][]): Response {
  const body = events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join("");
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

beforeEach(() => {
  document.cookie = "orbit_csrf=csrf-token; path=/";
  searchParams = new URLSearchParams();
});

describe("helpers", () => {
  it("parses server-sent events and skips malformed ones", () => {
    expect(parseSseBlock('event: delta\ndata: {"text":"สวัสดี"}')).toEqual({
      event: "delta",
      data: { text: "สวัสดี" },
    });
    expect(parseSseBlock("event: delta\ndata: {broken")).toBeNull();
    expect(parseSseBlock('event: unknown\ndata: {"x":1}')).toBeNull();
  });

  it("renders model output as plain text with in-app links only", () => {
    render(
      <MessageText
        text={`ดูที่ /tasks/${TASK_ID} <img src=x onerror=alert(1)> https://evil.example/tasks/${TASK_ID}x`}
      />,
    );
    expect(screen.getByRole("link", { name: `/tasks/${TASK_ID}` })).toHaveAttribute(
      "href",
      `/tasks/${TASK_ID}`,
    );
    expect(screen.getAllByRole("link")).toHaveLength(1); // not inside the external URL
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
  });
});

describe("AssistantView", () => {
  it("explains when no AI provider is configured", async () => {
    mockApi({
      "GET /api/v1/ai/status": () => json(status(false)),
      "GET /api/v1/ai/sessions": () => json({ items: [], total: 0, page: 1, page_size: 50 }),
    });
    render(<AssistantView />, { wrapper: createWrapper() });
    expect(await screen.findByText("ยังไม่ได้ตั้งค่าผู้ให้บริการ AI")).toBeInTheDocument();
    expect(screen.getByLabelText("ข้อความถึงผู้ช่วย AI")).toBeDisabled();
    expect(screen.queryByRole("button", { name: SUGGESTION })).not.toBeInTheDocument();
  });

  it("streams an answer, shows the proposed action and confirms it", async () => {
    let sent: unknown = null;
    let confirmCsrf: string | null = null;
    let current = action();
    const fetchMock = mockApi({
      "GET /api/v1/ai/status": () => json(status()),
      "GET /api/v1/ai/sessions": () => json({ items: [session], total: 1, page: 1, page_size: 50 }),
      "POST /api/v1/ai/sessions": () => json(session, 201),
      "POST /api/v1/ai/sessions/s-1/messages": (_, init) => {
        sent = JSON.parse(String(init?.body));
        return sse([
          ["start", { user_message_id: "m-1", title: session.title }],
          [
            "tool",
            {
              message_id: "m-2",
              name: "create_task",
              label: "เตรียมสร้างงาน",
              ok: true,
              action_id: "a-1",
            },
          ],
          ["action", current],
          ["delta", { text: "เตรียมงานไว้แล้ว " }],
          ["delta", { text: "กรุณากดยืนยัน" }],
          ["done", { message_id: "m-3", truncated: false }],
        ]);
      },
      "GET /api/v1/ai/sessions/s-1": () => json(stored(current)),
      "POST /api/v1/ai/actions/a-1/confirm": (_, init) => {
        confirmCsrf = new Headers(init?.headers).get(CSRF_HEADER);
        current = action({ status: "EXECUTED", result: { link: `/tasks/${TASK_ID}` } });
        return json(current);
      },
    });
    render(<AssistantView />, { wrapper: createWrapper() });

    expect(await screen.findByText("claude-opus-5-5")).toBeInTheDocument();
    const composer = screen.getByLabelText("ข้อความถึงผู้ช่วย AI");
    await userEvent.type(composer, "สร้างงานทำรายงานให้หน่อย{Enter}");

    expect(await screen.findByText("เตรียมงานไว้แล้ว กรุณากดยืนยัน")).toBeInTheDocument();
    expect(sent).toEqual({ content: "สร้างงานทำรายงานให้หน่อย" });
    expect(composer).toHaveValue("");
    const card = await screen.findByTestId("action-card");
    expect(card).toHaveTextContent("รอการยืนยันจากคุณ");
    expect(screen.getByTestId("chat-tool")).toHaveTextContent("เตรียมสร้างงาน");

    await userEvent.click(within(card).getByRole("button", { name: "ยืนยัน" }));
    await vi.waitFor(() =>
      expect(screen.getByTestId("action-card")).toHaveTextContent("ดำเนินการแล้ว"),
    );
    expect(confirmCsrf).toBe("csrf-token");
    expect(
      within(screen.getByTestId("action-card")).getByRole("link", { name: "เปิดดู" }),
    ).toHaveAttribute("href", `/tasks/${TASK_ID}`);
    expect(
      fetchMock.mock.calls.filter(
        ([, init]) => init?.method === "POST" && String(init?.body ?? "").includes("content"),
      ),
    ).toHaveLength(1);
  });

  it("shows provider errors from the stream", async () => {
    mockApi({
      "GET /api/v1/ai/status": () => json(status()),
      "GET /api/v1/ai/sessions": () => json({ items: [], total: 0, page: 1, page_size: 50 }),
      "POST /api/v1/ai/sessions": () => json(session, 201),
      "POST /api/v1/ai/sessions/s-1/messages": () =>
        sse([
          ["start", { user_message_id: "m-1", title: "x" }],
          ["error", { code: "ai_rate_limited", message: "ผู้ให้บริการ AI มีผู้ใช้งานหนาแน่น" }],
        ]),
      "GET /api/v1/ai/sessions/s-1": () =>
        json({
          ...session,
          messages: [
            {
              id: "m-1",
              role: "user",
              citations: [],
              content: "สวัสดี",
              created_at: "2026-11-11T05:00:00Z",
            },
          ],
          actions: [],
        }),
    });
    render(<AssistantView />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: SUGGESTION }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "ผู้ให้บริการ AI มีผู้ใช้งานหนาแน่น",
    );
  });

  it("reports a rate limit before streaming starts", async () => {
    mockApi({
      "GET /api/v1/ai/status": () => json(status()),
      "GET /api/v1/ai/sessions": () => json({ items: [session], total: 1, page: 1, page_size: 50 }),
      "GET /api/v1/ai/sessions/s-1": () => json({ ...session, messages: [], actions: [] }),
      "POST /api/v1/ai/sessions/s-1/messages": () =>
        json({ error: { code: "rate_limited", message: "ส่งข้อความถี่เกินไป", details: [] } }, 429),
    });
    render(<AssistantView />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: /^สร้างงานให้หน่อย/ }));
    await userEvent.type(screen.getByLabelText("ข้อความถึงผู้ช่วย AI"), "อีกครั้ง{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("ส่งข้อความถี่เกินไป");
  });
});

const SUGGESTION = "งานของฉันที่ใกล้ครบกำหนดมีอะไรบ้าง";

describe("AssistantView citations and pre-fill", () => {
  it("lists the sources an answer cites", async () => {
    mockApi({
      "GET /api/v1/ai/status": () => json(status()),
      "GET /api/v1/ai/sessions": () => json({ items: [session], total: 1, page: 1, page_size: 50 }),
      "GET /api/v1/ai/sessions/s-1": () =>
        json({
          ...session,
          messages: [
            {
              id: "m-1",
              role: "user",
              citations: [],
              content: "ลาพักร้อนได้กี่วัน",
              created_at: "2026-11-11T05:00:00Z",
            },
            {
              id: "m-2",
              role: "assistant",
              content: "ลาพักร้อนได้ปีละ 10 วันทำการ [1]",
              citations: [{ n: 1, document_id: TASK_ID, title: "นโยบายการลา", page: 3 }],
              created_at: "2026-11-11T05:00:01Z",
            },
          ],
          actions: [],
        }),
    });
    render(<AssistantView />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: /^สร้างงานให้หน่อย/ }));
    const sources = await screen.findByTestId("chat-sources");
    expect(within(sources).getByRole("link", { name: "นโยบายการลา" })).toHaveAttribute(
      "href",
      `/documents/${TASK_ID}`,
    );
    expect(sources).toHaveTextContent("[1] นโยบายการลา · หน้า 3");
  });

  it("pre-fills the composer from ?prompt= without sending", async () => {
    searchParams = new URLSearchParams({ prompt: "สรุปเอกสาร “นโยบายการลา” ให้หน่อย" });
    const fetchMock = mockApi({
      "GET /api/v1/ai/status": () => json(status()),
      "GET /api/v1/ai/sessions": () => json({ items: [], total: 0, page: 1, page_size: 50 }),
    });
    render(<AssistantView />, { wrapper: createWrapper() });
    expect(await screen.findByLabelText("ข้อความถึงผู้ช่วย AI")).toHaveValue(
      "สรุปเอกสาร “นโยบายการลา” ให้หน่อย",
    );
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });
});
