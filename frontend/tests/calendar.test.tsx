import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CalendarView } from "@/features/calendar/components/calendar-view";

import { createWrapper, json, mockApi } from "./fixtures";

let search = new URLSearchParams();
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useSearchParams: () => search,
  useRouter: () => ({ replace }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({ me: { user: { id: "me" } }, has: () => true }),
}));

const now = new Date();
const at = (h: number) =>
  new Date(now.getFullYear(), now.getMonth(), now.getDate(), h).toISOString();
const meeting = (over: object = {}) => ({
  id: "m1",
  title: "ประชุมทีมขาย",
  description: "",
  location: "ห้อง 3",
  online_url: null,
  start_at: at(10),
  end_at: at(11),
  organizer: { id: "boss", display_name: "หัวหน้า", department_name: null },
  attendees: [
    {
      id: "boss",
      display_name: "หัวหน้า",
      department_name: null,
      response: "ACCEPTED",
      is_organizer: true,
    },
    {
      id: "me",
      display_name: "ฉัน",
      department_name: null,
      response: "PENDING",
      is_organizer: false,
    },
  ],
  my_response: "PENDING",
  is_organizer: false,
  cancelled: false,
  reminder_minutes: 15,
  ...over,
});

beforeEach(() => {
  search = new URLSearchParams();
  replace.mockReset();
});

describe("CalendarView", () => {
  it("shows today's meetings and team leave in the day panel", async () => {
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    mockApi({
      "GET /api/v1/calendar/events": () =>
        json({
          meetings: [meeting()],
          leave: [
            {
              id: "l1",
              person_name: "สมหญิง ใจดี",
              leave_type: "ลาป่วย",
              color: "rose",
              start_date: today,
              end_date: today,
              half_day: "NONE",
            },
          ],
        }),
    });
    render(<CalendarView />, { wrapper: createWrapper() });
    const panel = await screen.findByRole("complementary", { name: "รายการของวันที่เลือก" });
    expect(await within(panel).findByText("ประชุมทีมขาย")).toBeInTheDocument();
    expect(within(panel).getByText(/ห้อง 3/)).toBeInTheDocument();
    expect(within(panel).getByText("ยังไม่ตอบ")).toBeInTheDocument();
    const isWeekend = now.getDay() === 0 || now.getDay() === 6;
    if (!isWeekend) expect(within(panel).getByText(/สมหญิง ใจดี · ลาป่วย/)).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: /ประชุมทีมขาย/ }));
    expect(replace).toHaveBeenCalledWith("/calendar?meeting=m1");
  });

  it("lets an invitee accept from the meeting detail", async () => {
    search = new URLSearchParams("meeting=m1");
    let current = meeting();
    const fetchMock = mockApi({
      "GET /api/v1/calendar/events": () => json({ meetings: [current], leave: [] }),
      "GET /api/v1/calendar/meetings/m1": () => json(current),
      "POST /api/v1/calendar/meetings/m1/respond": (_u, init) => {
        const { response } = JSON.parse(String(init?.body)) as { response: string };
        current = meeting({ my_response: response });
        return json(current);
      },
    });
    render(<CalendarView />, { wrapper: createWrapper() });
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("ประชุมทีมขาย")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "เข้าร่วม" }));
    await waitFor(() =>
      expect(within(dialog).getByRole("button", { name: "เข้าร่วม" })).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ response: "ACCEPTED" });
  });

  it("schedules a meeting with attendees and warns about conflicts", async () => {
    const fetchMock = mockApi({
      "GET /api/v1/calendar/events": () => json({ meetings: [], leave: [] }),
      "GET /api/v1/directory/users": () =>
        json([{ id: "u2", display_name: "สมชาย ใจดี", job_title: "เซลส์", department: null }]),
      "POST /api/v1/calendar/availability": () =>
        json({
          conflicts: [
            {
              user_id: "u2",
              display_name: "สมชาย ใจดี",
              kind: "meeting",
              detail: "ติดประชุมอื่น 10:00-11:00",
            },
          ],
        }),
      "POST /api/v1/calendar/meetings": (_u, init) =>
        json(meeting(JSON.parse(String(init?.body))), 201),
    });
    render(<CalendarView />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: "นัดประชุม" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("หัวข้อ"), "วางแผนไตรมาส");
    await userEvent.type(within(dialog).getByLabelText("ค้นหาผู้เข้าร่วม"), "สม");
    await userEvent.click(await within(dialog).findByRole("button", { name: /สมชาย ใจดี/ }));
    expect(
      await within(dialog).findByText(/ติดประชุมอื่น/, {}, { timeout: 3000 }),
    ).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "นัดประชุม" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([u, init]) => String(u).endsWith("/calendar/meetings") && init?.method === "POST",
        ),
      ).toBe(true),
    );
    const post = fetchMock.mock.calls.find(
      ([u, init]) => String(u).endsWith("/calendar/meetings") && init?.method === "POST",
    );
    const body = JSON.parse(String(post?.[1]?.body)) as Record<string, unknown>;
    expect(body).toMatchObject({
      title: "วางแผนไตรมาส",
      attendee_ids: ["u2"],
      reminder_minutes: 15,
    });
    expect(
      new Date(String(body.end_at)).getTime() - new Date(String(body.start_at)).getTime(),
    ).toBe(3_600_000);
  });
});
