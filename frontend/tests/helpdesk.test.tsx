import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HelpdeskView } from "@/features/helpdesk/components/helpdesk-view";
import { TicketDetailView } from "@/features/helpdesk/components/ticket-detail-view";
import type { TicketDetail, TicketListItem } from "@/services/tickets";

import { createWrapper, json, mockApi } from "./fixtures";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/helpdesk",
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

let permissions = new Set<string>();
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({
    me: { user: { id: "u-alice", department: null } },
    has: (p: string) => permissions.has(p),
  }),
}));

const EMPLOYEE = ["tickets:create", "tickets:read_own"];
const IT = [
  ...EMPLOYEE,
  "tickets:read_all",
  "tickets:assign",
  "tickets:manage",
  "tickets:comment_internal",
];

const item = (overrides: Partial<TicketListItem> = {}): TicketListItem => ({
  id: "k-1",
  ticket_number: "IT-2026-000007",
  title: "เครื่องพิมพ์ชั้น 3 ใช้ไม่ได้",
  category: "PRINTER",
  priority: "HIGH",
  status: "OPEN",
  requester: { id: "u-alice", display_name: "อลิซ ใจดี" },
  assignee: null,
  created_at: "2026-11-11T03:00:00Z",
  updated_at: "2026-11-11T03:00:00Z",
  resolved_at: null,
  closed_at: null,
  ...overrides,
});

const detail = (overrides: Partial<TicketDetail> = {}): TicketDetail => ({
  ...item(),
  description: "กระดาษติดทุกครั้ง",
  capabilities: {
    can_manage: false,
    can_assign: false,
    can_comment: true,
    can_comment_internal: false,
    allowed_statuses: ["CANCELLED"],
  },
  ...overrides,
});

function ticketApi(ticket: TicketDetail, extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    "GET /api/v1/tickets/k-1": () => json(ticket),
    "GET /api/v1/tickets/k-1/comments": () =>
      json([
        {
          id: "c-1",
          author: { id: "u-it", display_name: "ไอที สมชาย" },
          body: "<b>กำลังตรวจสอบ</b>",
          is_internal: false,
          created_at: "2026-11-11T04:00:00Z",
        },
      ]),
    "GET /api/v1/tickets/k-1/history": () =>
      json([
        {
          id: "e-1",
          event_type: "STATUS_CHANGED",
          actor: { id: "u-it", display_name: "ไอที สมชาย" },
          from_value: "OPEN",
          to_value: "IN_PROGRESS",
          is_internal: false,
          created_at: "2026-11-11T05:00:00Z",
        },
      ]),
    "GET /api/v1/tickets/assignees": () =>
      json([{ id: "u-it", display_name: "ไอที สมชาย", job_title: null, department: null }]),
    ...extra,
  });
}

beforeEach(() => {
  permissions = new Set(EMPLOYEE);
  push.mockReset();
  document.cookie = "aura_csrf=csrf-token; path=/";
});

describe("HelpdeskView", () => {
  it("lists my open tickets for employees, without staff scopes", async () => {
    const fetchMock = mockApi({
      "GET /api/v1/tickets": () => json({ items: [item()], total: 1, page: 1, page_size: 20 }),
    });
    render(<HelpdeskView />, { wrapper: createWrapper() });
    const row = await screen.findByTestId("ticket-row");
    expect(row).toHaveTextContent("IT-2026-000007");
    expect(row).toHaveTextContent("รอรับเรื่อง");
    expect(row).toHaveTextContent("ยังไม่มีผู้รับเรื่อง");
    expect(row).not.toHaveTextContent("ผู้แจ้ง");
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    const url = new URL(String(fetchMock.mock.calls[0]?.[0]), "http://x");
    expect(url.searchParams.get("scope")).toBe("mine");
    expect(url.searchParams.get("open_only")).toBe("true");
  });

  it("gives IT staff the queue scopes and shows requesters", async () => {
    permissions = new Set(IT);
    const fetchMock = mockApi({
      "GET /api/v1/tickets": () => json({ items: [item()], total: 1, page: 1, page_size: 20 }),
    });
    render(<HelpdeskView />, { wrapper: createWrapper() });
    expect(await screen.findByTestId("ticket-row")).toHaveTextContent("ผู้แจ้ง อลิซ ใจดี");
    await userEvent.click(screen.getByRole("tab", { name: "ยังไม่มีผู้รับเรื่อง" }));
    const scopes = fetchMock.mock.calls.map((c) =>
      new URL(String(c[0]), "http://x").searchParams.get("scope"),
    );
    expect(scopes[0]).toBe("all");
    expect(scopes).toContain("unassigned");
  });

  it("creates a ticket and opens it", async () => {
    let body: unknown = null;
    mockApi({
      "GET /api/v1/tickets": () => json({ items: [], total: 0, page: 1, page_size: 20 }),
      "POST /api/v1/tickets": (_url, init) => {
        body = JSON.parse(String(init?.body));
        return json(detail(), 201);
      },
    });
    render(<HelpdeskView />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: "แจ้งปัญหาใหม่" }));
    const form = screen.getByRole("form", { name: "ฟอร์มแจ้งปัญหา" });
    await userEvent.click(within(form).getByRole("button", { name: "ส่งเรื่อง" }));
    expect(await within(form).findByText("กรุณาระบุเรื่อง")).toBeInTheDocument();

    await userEvent.type(within(form).getByLabelText("เรื่อง"), "เมาส์เสีย");
    await userEvent.type(within(form).getByLabelText("รายละเอียด"), "คลิกไม่ติด");
    await userEvent.selectOptions(within(form).getByLabelText("หมวด"), "COMPUTER");
    await userEvent.click(within(form).getByRole("button", { name: "ส่งเรื่อง" }));
    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/helpdesk/k-1"));
    expect(body).toEqual({
      title: "เมาส์เสีย",
      description: "คลิกไม่ติด",
      category: "COMPUTER",
      priority: "MEDIUM",
    });
  });
});

describe("TicketDetailView", () => {
  it("shows requesters plain actions and renders messages as text", async () => {
    let posted: unknown = null;
    ticketApi(detail(), {
      "POST /api/v1/tickets/k-1/status": (_u, init) => {
        posted = JSON.parse(String(init?.body));
        return json(detail({ status: "CANCELLED" }));
      },
    });
    render(<TicketDetailView id="k-1" />, { wrapper: createWrapper() });
    expect(
      await screen.findByRole("heading", { name: "เครื่องพิมพ์ชั้น 3 ใช้ไม่ได้" }),
    ).toBeVisible();
    // No staff controls for requesters.
    expect(screen.queryByLabelText("เปลี่ยนสถานะ")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("ผู้รับผิดชอบ")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/บันทึกภายใน/)).not.toBeInTheDocument();

    const comment = await screen.findByTestId("ticket-comment");
    expect(comment).toHaveTextContent("<b>กำลังตรวจสอบ</b>");
    expect(comment.querySelector("b")).toBeNull();
    expect(await screen.findByTestId("ticket-event")).toHaveTextContent(
      "เปลี่ยนสถานะ: รอรับเรื่อง → กำลังดำเนินการ",
    );

    await userEvent.click(screen.getByRole("button", { name: "ยกเลิกการแจ้ง" }));
    await vi.waitFor(() => expect(posted).toEqual({ status: "CANCELLED" }));
  });

  it("lets IT assign, change status and add internal notes", async () => {
    permissions = new Set(IT);
    const calls: Record<string, unknown> = {};
    const staffTicket = detail({
      capabilities: {
        can_manage: true,
        can_assign: true,
        can_comment: true,
        can_comment_internal: true,
        allowed_statuses: ["IN_PROGRESS", "WAITING_FOR_USER", "RESOLVED", "CLOSED", "CANCELLED"],
      },
    });
    ticketApi(staffTicket, {
      "PUT /api/v1/tickets/k-1/assignee": (_u, init) => {
        calls.assign = JSON.parse(String(init?.body));
        return json(staffTicket);
      },
      "POST /api/v1/tickets/k-1/status": (_u, init) => {
        calls.status = JSON.parse(String(init?.body));
        return json(staffTicket);
      },
      "POST /api/v1/tickets/k-1/comments": (_u, init) => {
        calls.comment = JSON.parse(String(init?.body));
        return json([], 201);
      },
    });
    render(<TicketDetailView id="k-1" />, { wrapper: createWrapper() });

    const assignee = await screen.findByLabelText("ผู้รับผิดชอบ");
    await vi.waitFor(() =>
      expect(within(assignee).getByRole("option", { name: "ไอที สมชาย" })).toBeInTheDocument(),
    );
    await userEvent.selectOptions(assignee, "u-it");
    await vi.waitFor(() => expect(calls.assign).toEqual({ assignee_id: "u-it" }));

    await userEvent.selectOptions(screen.getByLabelText("เปลี่ยนสถานะ"), "RESOLVED");
    await vi.waitFor(() => expect(calls.status).toEqual({ status: "RESOLVED" }));

    await userEvent.click(screen.getByLabelText("บันทึกภายใน (ผู้แจ้งไม่เห็น)"));
    await userEvent.type(screen.getByLabelText("บันทึกภายใน"), "รอสั่งอะไหล่");
    await userEvent.click(screen.getByRole("button", { name: "ส่ง" }));
    await vi.waitFor(() =>
      expect(calls.comment).toEqual({ body: "รอสั่งอะไหล่", is_internal: true }),
    );
  });

  it("shows a not-found state for invisible tickets", async () => {
    mockApi({});
    render(<TicketDetailView id="k-1" />, { wrapper: createWrapper() });
    expect(await screen.findByText("ไม่พบรายการแจ้งปัญหา")).toBeInTheDocument();
  });
});
