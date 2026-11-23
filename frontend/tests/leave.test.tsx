import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LeaveView } from "@/features/leave/components/leave-view";
import { workingDays } from "@/services/leave";

import { createWrapper, json, mockApi } from "./fixtures";

let permissions: string[] = ["leave:request"];
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useSearchParams: () => search,
  useRouter: () => ({ replace: vi.fn() }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({ has: (p: string) => permissions.includes(p) }),
}));

const annual = {
  id: "t1",
  code: "ANNUAL",
  name: "ลาพักร้อน",
  days_per_year: "6.0",
  color: "emerald",
  is_active: true,
};
const request = (over: object = {}) => ({
  id: "r1",
  person: { id: "u2", display_name: "สมชาย ใจดี", department_name: "ฝ่ายขาย" },
  leave_type: annual,
  start_date: "2030-03-04",
  end_date: "2030-03-05",
  half_day: "NONE",
  days: "2.0",
  reason: "ไปต่างจังหวัด",
  status: "PENDING",
  decided_by_name: null,
  decided_at: null,
  decision_note: null,
  created_at: "2030-03-01T03:00:00Z",
  can_decide: false,
  can_cancel: true,
  ...over,
});

beforeEach(() => {
  permissions = ["leave:request"];
  search = new URLSearchParams();
});

describe("workingDays", () => {
  it("counts Monday to Friday and half days", () => {
    expect(workingDays("2030-03-04", "2030-03-08")).toBe(5);
    expect(workingDays("2030-03-08", "2030-03-11")).toBe(2); // Fri-Mon
    expect(workingDays("2030-03-09", "2030-03-10")).toBe(0); // weekend
    expect(workingDays("2030-03-04", "2030-03-04", "MORNING")).toBe(0.5);
  });
});

describe("LeaveView", () => {
  it("shows balances and submits a request with the working-day count", async () => {
    const fetchMock = mockApi({
      "GET /api/v1/leave/me": () =>
        json({
          year: 2030,
          balances: [
            {
              leave_type: annual,
              year: 2030,
              quota: "6.0",
              used: "1.0",
              pending: "0",
              remaining: "5.0",
            },
          ],
          requests: [],
        }),
      "POST /api/v1/leave/requests": (_u, init) =>
        json(request(JSON.parse(String(init?.body))), 201),
    });
    render(<LeaveView />, { wrapper: createWrapper() });

    expect(await screen.findByText("ลาพักร้อน")).toBeInTheDocument();
    expect(screen.getByText(/ใช้ไป 1 วัน/)).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /รออนุมัติ/ })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "ยื่นใบลา" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.clear(within(dialog).getByLabelText("วันเริ่มลา"));
    await userEvent.type(within(dialog).getByLabelText("วันเริ่มลา"), "2030-03-04");
    await userEvent.clear(within(dialog).getByLabelText("ถึงวันที่"));
    await userEvent.type(within(dialog).getByLabelText("ถึงวันที่"), "2030-03-06");
    expect(within(dialog).getByTestId("leave-days")).toHaveTextContent("รวม 3 วันทำงาน");
    await userEvent.type(within(dialog).getByLabelText("เหตุผล (ไม่บังคับ)"), "พักผ่อน");
    await userEvent.click(within(dialog).getByRole("button", { name: "ส่งใบลา" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true),
    );
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      leave_type_id: "t1",
      start_date: "2030-03-04",
      end_date: "2030-03-06",
      half_day: "NONE",
      reason: "พักผ่อน",
    });
  });

  it("lets a manager approve a pending request", async () => {
    permissions = ["leave:request", "leave:approve_department"];
    search = new URLSearchParams("tab=approvals");
    let pending = [request({ can_decide: true })];
    const fetchMock = mockApi({
      "GET /api/v1/leave/requests": () => json(pending),
      "POST /api/v1/leave/requests/r1/decision": () => {
        pending = [];
        return json(request({ status: "APPROVED" }));
      },
    });
    render(<LeaveView />, { wrapper: createWrapper() });

    expect(await screen.findByText(/สมชาย ใจดี/)).toBeInTheDocument();
    expect(screen.getByText("“ไปต่างจังหวัด”")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "อนุมัติ" }));
    expect(await screen.findByText("ไม่มีใบลารออนุมัติ")).toBeInTheDocument();
    const decision = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/decision"));
    expect(JSON.parse(String(decision?.[1]?.body))).toEqual({ approve: true, note: "" });
  });
});
