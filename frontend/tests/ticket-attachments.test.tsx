import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CreateTicketDialog } from "@/features/helpdesk/components/create-ticket-dialog";
import { TicketAttachmentsCard } from "@/features/helpdesk/components/ticket-attachments";
import type { TicketAttachment, TicketDetail } from "@/services/tickets";

import { createWrapper, json, mockApi } from "./fixtures";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/helpdesk",
}));
const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: (m: string) => toastError(m) } }));

const ticket = (caps: Partial<TicketDetail["capabilities"]> = {}): TicketDetail => ({
  id: "k-1",
  ticket_number: "IT-2026-000007",
  title: "จอดับ",
  category: "COMPUTER",
  priority: "HIGH",
  status: "OPEN",
  requester: { id: "u-alice", display_name: "อลิซ ใจดี" },
  assignee: null,
  created_at: "2026-11-11T03:00:00Z",
  updated_at: "2026-11-11T03:00:00Z",
  resolved_at: null,
  closed_at: null,
  description: "เปิดไม่ติด",
  capabilities: {
    can_manage: false,
    can_assign: false,
    can_comment: true,
    can_comment_internal: false,
    can_attach: true,
    can_attach_internal: false,
    allowed_statuses: ["CANCELLED"],
    ...caps,
  },
});

const file = (overrides: Partial<TicketAttachment>): TicketAttachment => ({
  id: "a-1",
  original_filename: "หน้าจอ.png",
  file_type: "PNG",
  size_bytes: 2048,
  is_internal: false,
  uploaded_by: { id: "u-alice", display_name: "อลิซ ใจดี" },
  created_at: "2026-11-11T04:00:00Z",
  can_delete: true,
  ...overrides,
});

beforeEach(() => {
  push.mockReset();
  toastError.mockReset();
  document.cookie = "orbit_csrf=csrf-token; path=/";
});

describe("TicketAttachmentsCard", () => {
  it("lists files with preview for images and delete only where allowed", async () => {
    mockApi({
      "GET /api/v1/tickets/k-1/attachments": () =>
        json([
          file({}),
          file({
            id: "a-2",
            original_filename: "quote.pdf",
            file_type: "PDF",
            is_internal: true,
            can_delete: false,
          }),
        ]),
    });
    render(<TicketAttachmentsCard ticket={ticket()} />, { wrapper: createWrapper() });
    const [shot, quote] = await screen.findAllByTestId("ticket-attachment");
    expect(shot).toHaveTextContent("หน้าจอ.png");
    expect(within(shot!).getByRole("button", { name: "ดูรูป หน้าจอ.png" })).toBeInTheDocument();
    expect(within(shot!).getByRole("button", { name: "ลบ หน้าจอ.png" })).toBeInTheDocument();
    expect(quote).toHaveTextContent("ภายใน");
    expect(within(quote!).queryByRole("button", { name: /ดูรูป/ })).not.toBeInTheDocument();
    expect(within(quote!).queryByRole("button", { name: /^ลบ/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/ไฟล์ภายใน/)).not.toBeInTheDocument();
  });

  it("uploads as an internal file for IT and refuses unsupported files locally", async () => {
    const sent: { name: string; internal: string }[] = [];
    const fetchMock = mockApi({
      "GET /api/v1/tickets/k-1/attachments": () => json([]),
      "POST /api/v1/tickets/k-1/attachments": (_u, init) => {
        const form = init?.body as FormData;
        sent.push({
          name: (form.get("file") as File).name,
          internal: String(form.get("is_internal")),
        });
        return json([], 201);
      },
    });
    const user = userEvent.setup({ applyAccept: false });
    render(<TicketAttachmentsCard ticket={ticket({ can_attach_internal: true })} />, {
      wrapper: createWrapper(),
    });
    await screen.findByText(/ยังไม่มีไฟล์แนบ/);
    await user.click(screen.getByLabelText("แนบเป็นไฟล์ภายใน (ผู้แจ้งไม่เห็น)"));
    await user.upload(screen.getByLabelText("เลือกไฟล์แนบ"), [
      new File(["png"], "log.png", { type: "image/png" }),
      new File(["gif"], "anim.gif", { type: "image/gif" }),
    ]);
    await vi.waitFor(() => expect(sent).toEqual([{ name: "log.png", internal: "true" }]));
    expect(toastError).toHaveBeenCalledWith(expect.stringContaining("anim.gif"));
    expect(
      fetchMock.mock.calls.filter((c) => (c[1] as RequestInit | undefined)?.method === "POST"),
    ).toHaveLength(1);
  });

  it("previews screenshots from a blob URL", async () => {
    mockApi({
      "GET /api/v1/tickets/k-1/attachments": () => json([file({})]),
      "GET /api/v1/tickets/k-1/attachments/a-1/download": () =>
        new Response(new Blob(["png"], { type: "image/png" })),
    });
    URL.createObjectURL = vi.fn(() => "blob:preview");
    URL.revokeObjectURL = vi.fn();
    render(<TicketAttachmentsCard ticket={ticket()} />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: "ดูรูป หน้าจอ.png" }));
    const image = await screen.findByRole("img", { name: "หน้าจอ.png" });
    expect(image).toHaveAttribute("src", "blob:preview");
  });

  it("offers no upload once the ticket is closed", async () => {
    mockApi({ "GET /api/v1/tickets/k-1/attachments": () => json([]) });
    render(<TicketAttachmentsCard ticket={ticket({ can_attach: false })} />, {
      wrapper: createWrapper(),
    });
    expect(await screen.findByText("ไม่มีไฟล์แนบ")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "แนบไฟล์" })).not.toBeInTheDocument();
  });
});

describe("CreateTicketDialog with files", () => {
  it("creates the ticket, then uploads the chosen screenshot", async () => {
    const order: string[] = [];
    mockApi({
      "POST /api/v1/tickets": () => {
        order.push("create");
        return json(ticket(), 201);
      },
      "POST /api/v1/tickets/k-1/attachments": (_u, init) => {
        order.push(`upload:${((init?.body as FormData).get("file") as File).name}`);
        return json([], 201);
      },
    });
    const user = userEvent.setup();
    render(<CreateTicketDialog />, { wrapper: createWrapper() });
    await user.click(screen.getByRole("button", { name: "แจ้งปัญหาใหม่" }));
    const form = screen.getByRole("form", { name: "ฟอร์มแจ้งปัญหา" });
    await user.type(within(form).getByLabelText("เรื่อง"), "จอดับ");
    await user.type(within(form).getByLabelText("รายละเอียด"), "เปิดไม่ติด");
    await user.upload(
      within(form).getByLabelText("ไฟล์แนบ (ไม่บังคับ)"),
      new File(["png"], "error.png", { type: "image/png" }),
    );
    expect(within(form).getByRole("list", { name: "ไฟล์ที่เลือก" })).toHaveTextContent("error.png");
    await user.click(within(form).getByRole("button", { name: "ส่งเรื่อง" }));
    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/helpdesk/k-1"));
    expect(order).toEqual(["create", "upload:error.png"]);
  });
});
