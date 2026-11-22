import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { QuickAsk } from "@/features/assistant/components/quick-ask";
import { toParagraphs } from "@/services/quick-ai";

import { createWrapper, mockApi } from "./fixtures";

let permissions = ["ai:chat"];
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({ has: (p: string) => permissions.includes(p) }),
}));

const sse = (...events: [string, unknown][]) =>
  new Response(events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join(""), {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });

describe("toParagraphs", () => {
  it("splits on blank lines and drops Markdown markers", () => {
    expect(toParagraphs("## หัวข้อ\n**สำคัญ** มาก\n\n- ข้อแรก\n- ข้อสอง\n\n\n`code`")).toEqual([
      "หัวข้อ\nสำคัญ มาก",
      "• ข้อแรก\n• ข้อสอง",
      "code",
    ]);
  });
});

describe("QuickAsk", () => {
  it("is hidden without ai:chat", () => {
    permissions = [];
    const { container } = render(<QuickAsk />, { wrapper: createWrapper() });
    expect(container).toBeEmptyDOMElement();
    permissions = ["ai:chat"];
  });

  it("answers one question in paragraphs and forgets it when closed", async () => {
    const fetchMock = mockApi({
      "POST /api/v1/ai/quick": () =>
        sse(
          ["delta", { text: "ย่อหน้าแรก **ชัดเจน**" }],
          ["delta", { text: "\n\nย่อหน้าที่สอง" }],
          ["done", {}],
        ),
    });
    render(<QuickAsk />, { wrapper: createWrapper() });

    await userEvent.click(screen.getByRole("button", { name: "ถาม AI" }));
    expect(screen.getByRole("dialog", { name: "ถาม AI" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("คำถาม"), "ทดสอบ{Enter}");

    const answer = await screen.findByTestId("quick-answer");
    await waitFor(() =>
      expect([...answer.querySelectorAll("p")].map((p) => p.textContent)).toEqual([
        "ย่อหน้าแรก ชัดเจน",
        "ย่อหน้าที่สอง",
      ]),
    );
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ question: "ทดสอบ" });
    expect(await screen.findByRole("button", { name: "คัดลอก" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "ปิด" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "ถาม AI" }));
    expect(screen.queryByTestId("quick-answer")).not.toBeInTheDocument(); // nothing remembered
    expect(screen.getByText("ลองถาม เช่น")).toBeInTheDocument();
  });

  it("shows the server's error message", async () => {
    mockApi({
      "POST /api/v1/ai/quick": () =>
        sse([
          "error",
          { code: "ai_provider_error", message: "ผู้ให้บริการ AI ไม่ตอบสนองในขณะนี้" },
        ]),
    });
    render(<QuickAsk />, { wrapper: createWrapper() });
    await userEvent.click(screen.getByRole("button", { name: "ถาม AI" }));
    await userEvent.click(screen.getByRole("button", { name: "อธิบาย AI แบบเข้าใจง่าย" }));
    expect(await screen.findByText("ผู้ให้บริการ AI ไม่ตอบสนองในขณะนี้")).toBeInTheDocument();
  });
});
