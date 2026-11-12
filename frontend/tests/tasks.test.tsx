import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TaskDetailView } from "@/features/tasks/components/task-detail-view";
import { TasksView } from "@/features/tasks/components/tasks-view";
import { dueDateToIso, isoToDueDate } from "@/features/tasks/labels";
import { CSRF_HEADER } from "@/services/api-client";
import type { TaskDetail, TaskListItem } from "@/services/tasks";

import { createWrapper, json, mockApi } from "./fixtures";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/tasks",
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

let permissions = new Set<string>();
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({
    me: { user: { id: "u-alice", department: { id: "d-1", code: "SALES", name: "ฝ่ายขาย" } } },
    has: (p: string) => permissions.has(p),
  }),
}));

const listItem = (overrides: Partial<TaskListItem> = {}): TaskListItem => ({
  id: "t-1",
  title: "เตรียมรายงานยอดขาย",
  status: "IN_PROGRESS",
  priority: "HIGH",
  due_at: "2026-11-10T16:59:00Z",
  is_overdue: true,
  department: { id: "d-1", code: "SALES", name: "ฝ่ายขาย" },
  created_by: { id: "u-boss", display_name: "มานพ ผู้จัดการ" },
  assignees: [{ id: "u-alice", display_name: "อลิซ ใจดี" }],
  comment_count: 2,
  attachment_count: 1,
  completed_at: null,
  created_at: "2026-11-09T05:00:00Z",
  updated_at: "2026-11-11T05:00:00Z",
  ...overrides,
});

const detail = (overrides: Partial<TaskDetail> = {}): TaskDetail => ({
  ...listItem(),
  description: "ใช้ข้อมูลไตรมาส 3",
  capabilities: {
    can_edit: false,
    can_change_status: true,
    can_cancel: false,
    can_assign: false,
    can_delete: false,
    can_comment: true,
    can_attach: true,
  },
  ...overrides,
});

const emptyPage = { items: [], total: 0, page: 1, page_size: 20 };

function taskApi(
  task: TaskDetail,
  extra: Record<string, Parameters<typeof mockApi>[0][string]> = {},
) {
  return mockApi({
    "GET /api/v1/tasks/t-1": () => json(task),
    "GET /api/v1/tasks/t-1/comments": () =>
      json([
        {
          id: "c-1",
          author: { id: "u-boss", display_name: "มานพ ผู้จัดการ" },
          body: "<b>อย่าลืม</b> แนบตัวเลข",
          created_at: "2026-11-11T04:00:00Z",
          edited_at: null,
          can_edit: false,
          can_delete: false,
        },
      ]),
    "GET /api/v1/tasks/t-1/attachments": () => json([]),
    "GET /api/v1/tasks/t-1/history": () =>
      json([
        {
          id: "e-1",
          event_type: "STATUS_CHANGED",
          actor: { id: "u-alice", display_name: "อลิซ ใจดี" },
          from_value: "TODO",
          to_value: "IN_PROGRESS",
          created_at: "2026-11-11T05:00:00Z",
        },
      ]),
    ...extra,
  });
}

beforeEach(() => {
  permissions = new Set(["tasks:read_own", "tasks:create"]);
  push.mockReset();
  document.cookie = "orbit_csrf=csrf-token; path=/";
});

describe("due dates", () => {
  it("round-trips a date as the end of the Bangkok business day", () => {
    expect(dueDateToIso("2026-11-30")).toBe("2026-11-30T23:59:00+07:00");
    expect(dueDateToIso("")).toBeNull();
    expect(isoToDueDate("2026-11-30T16:59:00Z")).toBe("2026-11-30");
    expect(isoToDueDate(null)).toBe("");
  });
});

describe("TasksView", () => {
  it("shows my open tasks by default and sends filters", async () => {
    const fetchMock = mockApi({
      "GET /api/v1/tasks": () => json({ items: [listItem()], total: 1, page: 1, page_size: 20 }),
    });
    render(<TasksView />, { wrapper: createWrapper() });

    const row = await screen.findByTestId("task-row");
    expect(row).toHaveTextContent("เตรียมรายงานยอดขาย");
    expect(row).toHaveTextContent("กำลังดำเนินการ");
    expect(within(row).getByTestId("task-due")).toHaveTextContent("เลยกำหนด");
    expect(within(row).getByRole("link")).toHaveAttribute("href", "/tasks/t-1");
    const first = decodeURIComponent(String(fetchMock.mock.calls[0]?.[0]));
    expect(first).toContain("scope=assigned");
    expect(first).toContain("open_only=true");

    // Employees have no department scope tab.
    expect(screen.queryByRole("tab", { name: "งานของแผนก" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "ที่ฉันสร้าง" }));
    await userEvent.selectOptions(screen.getByLabelText("ความสำคัญ"), "URGENT");
    await userEvent.click(screen.getByRole("button", { name: "เลยกำหนด" }));
    await vi.waitFor(() => {
      const urls = fetchMock.mock.calls.map(([input]) => decodeURIComponent(String(input)));
      expect(
        urls.some(
          (u) =>
            u.includes("scope=created") &&
            u.includes("priority=URGENT") &&
            u.includes("overdue=true"),
        ),
      ).toBe(true);
    });
  });

  it("offers the department tab to managers", async () => {
    permissions.add("tasks:read_department");
    mockApi({ "GET /api/v1/tasks": () => json(emptyPage) });
    render(<TasksView />, { wrapper: createWrapper() });
    expect(await screen.findByRole("tab", { name: "งานของแผนก" })).toBeInTheDocument();
  });

  it("creates a self-assigned task without an assignee picker for employees", async () => {
    let body: Record<string, unknown> | null = null;
    let csrf: string | null = null;
    mockApi({
      "GET /api/v1/tasks": () => json(emptyPage),
      "POST /api/v1/tasks": (_, init) => {
        body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        csrf = new Headers(init?.headers).get(CSRF_HEADER);
        return json(detail({ id: "t-9" }), 201);
      },
    });
    render(<TasksView />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: "สร้างงาน" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByLabelText("ผู้รับผิดชอบ")).not.toBeInTheDocument();
    expect(within(dialog).getByText("งานนี้จะมอบหมายให้คุณเอง")).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole("button", { name: "สร้างงาน" }));
    expect(await within(dialog).findByText("กรุณาระบุชื่องาน")).toBeInTheDocument();

    await userEvent.type(within(dialog).getByLabelText("ชื่องาน"), "สรุปยอดเดือนพฤศจิกายน");
    await userEvent.selectOptions(within(dialog).getByLabelText("ความสำคัญ"), "HIGH");
    await userEvent.type(within(dialog).getByLabelText("กำหนดส่ง"), "2026-11-30");
    await userEvent.click(within(dialog).getByRole("button", { name: "สร้างงาน" }));

    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/tasks/t-9"));
    expect(csrf).toBe("csrf-token");
    expect(body).toEqual({
      title: "สรุปยอดเดือนพฤศจิกายน",
      description: null,
      priority: "HIGH",
      due_at: "2026-11-30T23:59:00+07:00",
      assignee_ids: [],
    });
  });

  it("lets managers pick assignees from the people they may assign", async () => {
    permissions.add("tasks:assign");
    let body: Record<string, unknown> | null = null;
    mockApi({
      "GET /api/v1/tasks": () => json(emptyPage),
      "GET /api/v1/tasks/assignable-users": () =>
        json([
          { id: "u-bob", display_name: "บ็อบ ขยัน", job_title: "พนักงานขาย", department: null },
        ]),
      "POST /api/v1/tasks": (_, init) => {
        body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return json(detail({ id: "t-2" }), 201);
      },
    });
    render(<TasksView />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: "สร้างงาน" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("ชื่องาน"), "ติดตามลูกค้า");
    await userEvent.click(await within(dialog).findByRole("button", { name: "เพิ่ม บ็อบ ขยัน" }));
    expect(within(dialog).getByRole("list", { name: "ผู้รับผิดชอบที่เลือก" })).toHaveTextContent(
      "บ็อบ ขยัน",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "สร้างงาน" }));
    await vi.waitFor(() => expect(body).not.toBeNull());
    expect((body as unknown as { assignee_ids: string[] }).assignee_ids).toEqual(["u-bob"]);
  });
});

describe("TaskDetailView", () => {
  it("lets an assignee change status but hides owner-only actions", async () => {
    let sent: unknown = null;
    taskApi(detail(), {
      "POST /api/v1/tasks/t-1/status": (_, init) => {
        sent = JSON.parse(String(init?.body));
        return json(detail({ status: "REVIEW" }));
      },
    });
    render(<TaskDetailView id="t-1" />, { wrapper: createWrapper() });

    expect(await screen.findByRole("heading", { name: "เตรียมรายงานยอดขาย" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "แก้ไข" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "ลบงาน" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "จัดการผู้รับผิดชอบ" })).not.toBeInTheDocument();

    const select = screen.getByLabelText("เปลี่ยนสถานะ");
    // Assignees cannot cancel.
    expect(within(select).queryByRole("option", { name: "ยกเลิก" })).not.toBeInTheDocument();
    await userEvent.selectOptions(select, "REVIEW");
    await vi.waitFor(() => expect(sent).toEqual({ status: "REVIEW" }));

    // Comments are plain text, never HTML.
    const comment = await screen.findByTestId("task-comment");
    expect(comment).toHaveTextContent("<b>อย่าลืม</b> แนบตัวเลข");
    expect(comment.querySelector("b")).toBeNull();
    expect(await screen.findByTestId("task-event")).toHaveTextContent(
      "เปลี่ยนสถานะ: รอดำเนินการ → กำลังดำเนินการ",
    );
  });

  it("shows owner actions and posts comments", async () => {
    let comment: unknown = null;
    taskApi(
      detail({
        capabilities: {
          can_edit: true,
          can_change_status: true,
          can_cancel: true,
          can_assign: true,
          can_delete: true,
          can_comment: true,
          can_attach: true,
        },
      }),
      {
        "POST /api/v1/tasks/t-1/comments": (_, init) => {
          comment = JSON.parse(String(init?.body));
          return json([], 201);
        },
      },
    );
    render(<TaskDetailView id="t-1" />, { wrapper: createWrapper() });
    expect(await screen.findByRole("button", { name: "แก้ไข" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ลบงาน" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "จัดการผู้รับผิดชอบ" })).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("เปลี่ยนสถานะ")).getByRole("option", { name: "ยกเลิก" }),
    ).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("เพิ่มความคิดเห็น"), "  ส่งแล้วครับ  ");
    await userEvent.click(screen.getByRole("button", { name: "ส่ง" }));
    await vi.waitFor(() => expect(comment).toEqual({ body: "ส่งแล้วครับ" }));
  });

  it("shows a not-found state for tasks the user cannot see", async () => {
    mockApi({
      "GET /api/v1/tasks/t-1": () =>
        json({ error: { code: "not_found", message: "ไม่พบงาน", details: [] } }, 404),
    });
    render(<TaskDetailView id="t-1" />, { wrapper: createWrapper() });
    expect(await screen.findByText("ไม่พบงาน")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "กลับไปหน้ารายการงาน" })).toHaveAttribute(
      "href",
      "/tasks",
    );
  });
});
