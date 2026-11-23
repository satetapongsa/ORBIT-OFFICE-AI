import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatView } from "@/features/chat/components/chat-view";

import { createWrapper, json, mockApi } from "./fixtures";

const search = new URLSearchParams("c=c1");
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => search,
}));
const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: (m: string) => toastError(m) } }));
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({
    me: { user: { id: "me", display_name: "ฉัน" } },
    isAuthenticated: true,
    has: () => true,
  }),
}));

const NOW = "2026-11-23T10:00:00Z";
const person = {
  id: "bob",
  display_name: "สมชาย ใจดี",
  job_title: null,
  department_name: null,
  is_active: true,
};
const file = (id: string, name: string, type: string, image: boolean) => ({
  id,
  original_filename: name,
  file_type: type,
  mime_type: image ? "image/png" : "application/pdf",
  size_bytes: 2048,
  is_image: image,
});
const message = (id: string, sender: string, body: string, attachment: unknown) => ({
  id,
  conversation_id: "c1",
  sender_id: sender,
  body,
  created_at: NOW,
  edited_at: null,
  attachment,
});

beforeEach(() => {
  toastError.mockReset();
  Element.prototype.scrollIntoView = vi.fn();
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});

function routes(messages: unknown[]) {
  return {
    "GET /api/v1/chat/groups": () => json([]),
    "GET /api/v1/chat/conversations": () =>
      json({
        items: [
          {
            id: "c1",
            other: person,
            last_message: messages.at(-1) ?? null,
            last_message_at: NOW,
            unread_count: 0,
            other_last_read_at: null,
            other_typing: false,
          },
        ],
        unread_total: 0,
      }),
    "GET /api/v1/chat/conversations/c1/messages": () => json({ items: messages, has_more: false }),
    "POST /api/v1/chat/conversations/c1/read": () => json({ unread_total: 0 }),
    "GET /api/v1/chat/attachments/img1": () =>
      new Response("png", { status: 200, headers: { "Content-Type": "image/png" } }),
  };
}

describe("Chat files", () => {
  it("shows images inline and files as cards, with previews in the list", async () => {
    mockApi(
      routes([
        message("m1", "bob", "", file("img1", "หน้าจอ.png", "PNG", true)),
        message("m2", "bob", "รายงานครับ", file("f1", "สรุป.pdf", "PDF", false)),
      ]),
    );
    render(<ChatView />, { wrapper: createWrapper() });
    const thread = await screen.findByRole("region", { name: "แชทกับ สมชาย ใจดี" });
    expect(await within(thread).findByTestId("chat-image")).toHaveAttribute("src", "blob:preview");
    const card = within(thread).getByTestId("chat-file");
    expect(card).toHaveTextContent("สรุป.pdf");
    expect(card).toHaveTextContent("PDF · 2.0 KB");
    expect(within(card).getByRole("button", { name: "ดาวน์โหลด สรุป.pdf" })).toBeInTheDocument();
    expect(within(thread).getByText("รายงานครับ")).toBeInTheDocument();
  });

  it("sends a picked file with the typed caption", async () => {
    let messages: unknown[] = [];
    const fetchMock = mockApi({
      ...routes(messages),
      "GET /api/v1/chat/conversations/c1/messages": () =>
        json({ items: messages, has_more: false }),
      "POST /api/v1/chat/conversations/c1/files": () => {
        const saved = message("m9", "me", "ดูไฟล์นี้", file("f9", "งบ.pdf", "PDF", false));
        messages = [saved];
        return json(saved, 201);
      },
    });
    const user = userEvent.setup();
    render(<ChatView />, { wrapper: createWrapper() });
    await screen.findByRole("region", { name: "แชทกับ สมชาย ใจดี" });

    const pdf = new File(["%PDF-1.4"], "งบ.pdf", { type: "application/pdf" });
    await user.upload(screen.getByTestId("chat-file-input"), pdf);
    expect(screen.getByTestId("staged-file")).toHaveTextContent("งบ.pdf");
    await user.type(screen.getByLabelText("ข้อความ", { exact: true }), "ดูไฟล์นี้{Enter}");

    await waitFor(() => expect(screen.getByTestId("chat-file")).toHaveTextContent("PDF · 2.0 KB"));
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/files"));
    const form = call?.[1]?.body as FormData;
    expect((form.get("file") as File).name).toBe("งบ.pdf");
    expect(form.get("body")).toBe("ดูไฟล์นี้");
    expect(screen.queryByTestId("staged-file")).not.toBeInTheDocument();
  });

  it("refuses unsupported files before uploading", async () => {
    mockApi(routes([]));
    const user = userEvent.setup({ applyAccept: false });
    render(<ChatView />, { wrapper: createWrapper() });
    await screen.findByRole("region", { name: "แชทกับ สมชาย ใจดี" });
    await user.upload(
      screen.getByTestId("chat-file-input"),
      new File(["MZ"], "tool.exe", { type: "application/octet-stream" }),
    );
    expect(toastError).toHaveBeenCalledWith("ส่งได้เฉพาะรูป PNG/JPG และไฟล์ PDF, DOCX, XLSX, TXT");
    expect(screen.queryByTestId("staged-file")).not.toBeInTheDocument();
  });
});
