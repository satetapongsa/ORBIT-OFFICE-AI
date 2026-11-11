import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EmployeeProfileView } from "@/features/employees/components/employee-profile-view";
import { EmployeesView } from "@/features/employees/components/employees-view";
import type { Employee, EmployeeProfile, HrProfile } from "@/services/employees";

import { createWrapper, json, mockApi } from "./fixtures";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/employees",
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

let permissions = new Set<string>();
let selfId = "u-viewer";
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({
    me: { user: { id: selfId, department: null } },
    has: (p: string) => permissions.has(p),
  }),
}));

const employee = (overrides: Partial<Employee> = {}): Employee => ({
  id: "u-somchai",
  employee_code: "E001",
  display_name: "สมชาย ใจดี",
  first_name: "สมชาย",
  last_name: "ใจดี",
  job_title: "เจ้าหน้าที่ขาย",
  department: { id: "d-1", code: "SALES", name: "ฝ่ายขาย" },
  email: "somchai@aura.example.com",
  phone_work: "02-000-0001",
  is_active: true,
  ...overrides,
});

const NO_CAPS = {
  can_edit_account: false,
  can_manage_roles: false,
  can_change_active: false,
  can_view_hr: false,
  can_edit_hr: false,
};

const profile = (overrides: Partial<EmployeeProfile> = {}): EmployeeProfile => ({
  ...employee(),
  department_manager: { id: "u-boss", display_name: "มานพ ผู้จัดการ" },
  account: null,
  capabilities: NO_CAPS,
  ...overrides,
});

const hrRecord: HrProfile = {
  user_id: "u-somchai",
  exists: true,
  date_of_birth: "1990-04-13",
  national_id_last4: "1234",
  personal_phone: "081-234-5678",
  personal_email: null,
  address: "กรุงเทพฯ",
  hire_date: "2020-06-01",
  employment_type: "FULL_TIME",
  emergency_contact: { name: "สมหญิง", relationship: "ภรรยา", phone: "089-999-0000" },
  updated_at: "2026-11-11T05:00:00Z",
  updated_by: { id: "u-hr", display_name: "ฝ่ายบุคคล" },
};

const departments = [
  {
    id: "d-1",
    code: "SALES",
    name: "ฝ่ายขาย",
    description: null,
    parent_id: null,
    manager_id: null,
    member_count: 12,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
  },
];

beforeEach(() => {
  permissions = new Set(["employees:read_directory", "departments:read"]);
  selfId = "u-viewer";
  document.cookie = "aura_csrf=csrf-token; path=/";
});

describe("EmployeesView", () => {
  it("lists colleagues with work contacts and filters by department", async () => {
    const fetchMock = mockApi({
      "GET /api/v1/employees": () =>
        json({ items: [employee()], total: 1, page: 1, page_size: 24 }),
      "GET /api/v1/departments": () => json(departments),
    });
    render(<EmployeesView />, { wrapper: createWrapper() });

    const card = await screen.findByTestId("employee-card");
    expect(within(card).getByRole("link", { name: "สมชาย ใจดี" })).toHaveAttribute(
      "href",
      "/employees/u-somchai",
    );
    expect(within(card).getByRole("link", { name: "somchai@aura.example.com" })).toHaveAttribute(
      "href",
      "mailto:somchai@aura.example.com",
    );
    // Employees cannot add people or see suspended accounts.
    expect(screen.queryByRole("button", { name: "เพิ่มพนักงาน" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "รวมบัญชีที่ถูกระงับ" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "แผนก" }));
    const dept = await screen.findByTestId("department-card");
    expect(dept).toHaveTextContent("ฝ่ายขาย");
    expect(screen.queryByRole("button", { name: "เพิ่มแผนก" })).not.toBeInTheDocument();
    await userEvent.click(within(dept).getByRole("button", { name: /พนักงาน 12 คน/ }));
    await vi.waitFor(() => {
      const urls = fetchMock.mock.calls.map(([input]) => String(input));
      expect(urls.some((u) => u.includes("/employees?") && u.includes("department_id=d-1"))).toBe(
        true,
      );
    });
  });

  it("shows administration actions to HR", async () => {
    permissions = new Set([
      "employees:read_directory",
      "departments:read",
      "departments:manage",
      "users:read",
      "users:create",
    ]);
    mockApi({
      "GET /api/v1/employees": () => json({ items: [], total: 0, page: 1, page_size: 24 }),
      "GET /api/v1/departments": () => json(departments),
    });
    render(<EmployeesView />, { wrapper: createWrapper() });
    expect(await screen.findByRole("button", { name: "เพิ่มพนักงาน" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "รวมบัญชีที่ถูกระงับ" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "แผนก" }));
    expect(await screen.findByRole("button", { name: "เพิ่มแผนก" })).toBeInTheDocument();
  });
});

describe("EmployeeProfileView", () => {
  it("shows directory data only, without account or HR sections, to colleagues", async () => {
    const fetchMock = mockApi({ "GET /api/v1/employees/u-somchai": () => json(profile()) });
    render(<EmployeeProfileView id="u-somchai" />, { wrapper: createWrapper() });

    expect(await screen.findByRole("heading", { name: "สมชาย ใจดี" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "มานพ ผู้จัดการ" })).toHaveAttribute(
      "href",
      "/employees/u-boss",
    );
    expect(screen.queryByTestId("account-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hr-card")).not.toBeInTheDocument();
    const urls = fetchMock.mock.calls.map(([input]) => String(input));
    expect(urls.some((u) => u.includes("/hr"))).toBe(false);
  });

  it("loads someone else's HR record only after an explicit click", async () => {
    let hrCalls = 0;
    mockApi({
      "GET /api/v1/employees/u-somchai": () =>
        json(
          profile({
            account: {
              employment_status: "ACTIVE",
              roles: [{ id: "r-1", code: "EMPLOYEE", name: "พนักงาน" }],
              last_login_at: null,
              created_at: "2026-11-01T00:00:00Z",
            },
            capabilities: {
              ...NO_CAPS,
              can_edit_account: true,
              can_view_hr: true,
              can_edit_hr: true,
            },
          }),
        ),
      "GET /api/v1/employees/u-somchai/hr": () => {
        hrCalls += 1;
        return json(hrRecord);
      },
      "GET /api/v1/departments": () => json(departments),
    });
    render(<EmployeeProfileView id="u-somchai" />, { wrapper: createWrapper() });

    const hrCard = await screen.findByTestId("hr-card");
    expect(within(screen.getByTestId("account-card")).getByText("พนักงาน")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "แก้ไขข้อมูล" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "กำหนดบทบาท" })).not.toBeInTheDocument();
    expect(hrCalls).toBe(0);

    await userEvent.click(within(hrCard).getByRole("button", { name: "แสดงข้อมูลบุคคล" }));
    expect(await within(hrCard).findByText("•••• •••• 1234")).toBeInTheDocument();
    expect(hrCalls).toBe(1);
    expect(within(hrCard).getByText("พนักงานประจำ")).toBeInTheDocument();
    expect(within(hrCard).getByRole("button", { name: "แก้ไข" })).toBeInTheDocument();
  });

  it("shows my own HR record immediately, read-only", async () => {
    selfId = "u-somchai";
    mockApi({
      "GET /api/v1/employees/u-somchai": () =>
        json(profile({ capabilities: { ...NO_CAPS, can_view_hr: true } })),
      "GET /api/v1/employees/u-somchai/hr": () => json(hrRecord),
    });
    render(<EmployeeProfileView id="u-somchai" />, { wrapper: createWrapper() });
    const hrCard = await screen.findByTestId("hr-card");
    expect(await within(hrCard).findByText("081-234-5678")).toBeInTheDocument();
    expect(within(hrCard).queryByRole("button", { name: "แก้ไข" })).not.toBeInTheDocument();
  });

  it("validates the HR form before sending", async () => {
    let sent: unknown = null;
    mockApi({
      "GET /api/v1/employees/u-somchai": () =>
        json(profile({ capabilities: { ...NO_CAPS, can_view_hr: true, can_edit_hr: true } })),
      "GET /api/v1/employees/u-somchai/hr": () =>
        json({ ...hrRecord, exists: false, national_id_last4: null, emergency_contact: null }),
      "PUT /api/v1/employees/u-somchai/hr": (_, init) => {
        sent = JSON.parse(String(init?.body));
        return json(hrRecord);
      },
    });
    render(<EmployeeProfileView id="u-somchai" />, { wrapper: createWrapper() });
    const hrCard = await screen.findByTestId("hr-card");
    await userEvent.click(within(hrCard).getByRole("button", { name: "แสดงข้อมูลบุคคล" }));
    await userEvent.click(await within(hrCard).findByRole("button", { name: "แก้ไข" }));
    const dialog = await screen.findByRole("dialog");

    const nationalId = within(dialog).getByLabelText("เลขบัตรประชาชน 4 หลักสุดท้าย");
    await userEvent.type(nationalId, "12a4");
    await userEvent.type(within(dialog).getByLabelText("ชื่อ"), "สมหญิง");
    await userEvent.click(within(dialog).getByRole("button", { name: "บันทึก" }));
    expect(await within(dialog).findByText("ระบุเฉพาะเลข 4 หลักสุดท้าย")).toBeInTheDocument();
    expect(
      within(dialog).getByText("กรอกผู้ติดต่อฉุกเฉินให้ครบทั้ง 3 ช่อง หรือเว้นว่างทั้งหมด"),
    ).toBeInTheDocument();
    expect(sent).toBeNull();

    await userEvent.clear(nationalId);
    await userEvent.type(nationalId, "5678");
    await userEvent.type(within(dialog).getByLabelText("ความสัมพันธ์"), "ภรรยา");
    await userEvent.type(within(dialog).getByLabelText("เบอร์โทร"), "089-999-0000");
    await userEvent.click(within(dialog).getByRole("button", { name: "บันทึก" }));
    await vi.waitFor(() => expect(sent).not.toBeNull());
    expect(sent).toMatchObject({
      national_id_last4: "5678",
      emergency_contact: { name: "สมหญิง", relationship: "ภรรยา", phone: "089-999-0000" },
    });
  });
});
