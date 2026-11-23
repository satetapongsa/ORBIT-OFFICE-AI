import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AttendanceView } from "@/features/attendance/components/attendance-view";

import { createWrapper, json, mockApi } from "./fixtures";

let permissions: string[] = ["attendance:checkin"];
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useSearchParams: () => search,
  useRouter: () => ({ replace: vi.fn() }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({ has: (p: string) => permissions.includes(p) }),
}));

const hours = { start: "09:00", end: "18:00", late_after: "09:15" };
const record = (over: object = {}) => ({
  id: "a1",
  work_date: "2026-11-23",
  check_in_at: "2026-11-23T02:20:00Z", // 09:20 Bangkok
  check_out_at: null,
  work_mode: "OFFICE",
  late: true,
  check_in_note: null,
  check_out_note: null,
  worked_minutes: null,
  ...over,
});
const month = {
  month: "2026-11",
  records: [] as unknown[],
  summary: { days_present: 0, late_days: 0, wfh_days: 0, total_minutes: 0, average_check_in: null },
};

beforeEach(() => {
  permissions = ["attendance:checkin"];
  search = new URLSearchParams();
});

describe("AttendanceView", () => {
  it("checks in with the chosen work mode and shows the result", async () => {
    let today = {
      date: "2026-11-23",
      server_time: "2026-11-23T02:20:00Z",
      hours,
      record: null as unknown,
      on_leave: null,
    };
    const fetchMock = mockApi({
      "GET /api/v1/attendance/today": () => json(today),
      "GET /api/v1/attendance/me": () => json(month),
      "POST /api/v1/attendance/check-in": (_u, init) => {
        const body = JSON.parse(String(init?.body)) as { work_mode: string };
        today = { ...today, record: record({ work_mode: body.work_mode }) };
        return json(today);
      },
    });
    render(<AttendanceView />, { wrapper: createWrapper() });

    expect(await screen.findByText("วันนี้ยังไม่ได้ลงเวลาเข้างาน")).toBeInTheDocument();
    expect(screen.getByText(/สายหลัง 09:15 น\./)).toBeInTheDocument();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument(); // no team tabs for staff
    await userEvent.selectOptions(screen.getByLabelText("รูปแบบการทำงาน"), "WFH");
    await userEvent.click(screen.getByRole("button", { name: "ลงเวลาเข้างาน" }));

    expect(await screen.findByText("เข้า 09:20")).toBeInTheDocument();
    // "มาสาย" badge on the card, next to the monthly summary label of the same name.
    expect(screen.getAllByText("มาสาย")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "ลงเวลาออกงาน" })).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ work_mode: "WFH", note: "" });
  });

  it("shows the team board to a manager", async () => {
    permissions = ["attendance:checkin", "attendance:read_department"];
    search = new URLSearchParams("tab=team");
    mockApi({
      "GET /api/v1/attendance/team": () =>
        json({
          date: "2026-11-23",
          rows: [
            {
              person: { id: "u1", display_name: "สมชาย", department_name: "ขาย", job_title: null },
              record: record(),
              on_leave: null,
            },
            {
              person: { id: "u2", display_name: "สมหญิง", department_name: "ขาย", job_title: null },
              record: null,
              on_leave: "ลาป่วย",
            },
            {
              person: {
                id: "u3",
                display_name: "สมศักดิ์",
                department_name: "ขาย",
                job_title: null,
              },
              record: null,
              on_leave: null,
            },
          ],
          present: 1,
          late: 1,
          on_leave: 1,
          missing: 1,
        }),
    });
    render(<AttendanceView />, { wrapper: createWrapper() });

    expect(await screen.findByText("สมชาย")).toBeInTheDocument();
    expect(screen.getByText("ลาป่วย")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("ยังไม่ลงเวลา").length).toBeGreaterThan(0));
    expect(screen.getByRole("tab", { name: /ทีมวันนี้/ })).toHaveAttribute("aria-selected", "true");
  });
});
