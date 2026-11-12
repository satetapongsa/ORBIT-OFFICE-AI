import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EmailPreferencesCard } from "@/features/account/components/email-preferences-card";
import { RolesSettings, groupPermissions } from "@/features/settings/components/roles-settings";
import type { RoleDetail } from "@/services/roles";

import { createWrapper, json, mockApi } from "./fixtures";

vi.mock("next/navigation", () => ({ usePathname: () => "/settings" }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

let permissions = new Set<string>();
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({ me: { user: { id: "u-1" } }, has: (p: string) => permissions.has(p) }),
}));

const CATALOGUE = [
  { code: "documents:read", description: "ดูเอกสาร" },
  { code: "tasks:read_own", description: "ดูงานของตนเอง" },
  { code: "tickets:read_all", description: "ดูรายการแจ้งปัญหาทั้งหมด" },
  { code: "roles:manage", description: "สร้างและแก้ไขบทบาทและสิทธิ์" },
];

const role = (overrides: Partial<RoleDetail>): RoleDetail => ({
  id: "r-x",
  code: "X",
  name: "X",
  description: "",
  is_system: false,
  is_locked: false,
  permissions: [],
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
  ...overrides,
});

const ROLES = [
  role({ id: "r-admin", code: "ADMIN", name: "Admin", is_system: true, is_locked: true }),
  role({
    id: "r-finance",
    code: "FINANCE",
    name: "การเงิน",
    description: "ทีมการเงิน",
    permissions: ["documents:read"],
  }),
];

beforeEach(() => {
  permissions = new Set(["roles:read", "roles:manage", "documents:read", "tasks:read_own"]);
  document.cookie = "orbit_csrf=csrf-token; path=/";
});

describe("groupPermissions", () => {
  it("groups by domain in display order and keeps unknown domains", () => {
    const groups = groupPermissions([...CATALOGUE, { code: "billing:read", description: "x" }]);
    expect(groups.map((g) => g.label)).toEqual([
      "บทบาทและสิทธิ์",
      "เอกสาร",
      "งาน",
      "แจ้งปัญหาไอที",
      "อื่นๆ",
    ]);
  });
});

describe("RolesSettings", () => {
  it("shows the locked administrator role read-only", async () => {
    mockApi({
      "GET /api/v1/roles": () => json(ROLES),
      "GET /api/v1/permissions": () => json(CATALOGUE),
    });
    render(<RolesSettings />, { wrapper: createWrapper() });
    expect(await screen.findByText(/มีสิทธิ์ทั้งหมดของระบบเสมอ/)).toBeInTheDocument();
    for (const box of screen.getAllByRole("checkbox")) {
      expect(box).toBeChecked();
      expect(box).toBeDisabled();
    }
    expect(screen.queryByRole("button", { name: "ลบบทบาท" })).not.toBeInTheDocument();
  });

  it("only grants permissions the editor holds, and saves the full set", async () => {
    let saved: unknown = null;
    mockApi({
      "GET /api/v1/roles": () => json(ROLES),
      "GET /api/v1/permissions": () => json(CATALOGUE),
      "PUT /api/v1/roles/r-finance/permissions": (_u, init) => {
        saved = JSON.parse(String(init?.body));
        return json({ ...ROLES[1], permissions: ["documents:read", "tasks:read_own"] });
      },
    });
    render(<RolesSettings />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: /การเงิน/ }));

    expect(screen.getByRole("checkbox", { name: /ดูรายการแจ้งปัญหาทั้งหมด/ })).toBeDisabled();
    const save = screen.getByRole("button", { name: "บันทึกสิทธิ์" });
    expect(save).toBeDisabled(); // nothing changed yet
    await userEvent.click(screen.getByRole("checkbox", { name: /ดูงานของตนเอง/ }));
    expect(screen.getByText("เลือกไว้ 2 จาก 4 สิทธิ์")).toBeInTheDocument();
    await userEvent.click(save);
    await vi.waitFor(() =>
      expect(saved).toEqual({ permissions: ["documents:read", "tasks:read_own"] }),
    );
    expect(screen.getByRole("button", { name: "ลบบทบาท" })).toBeInTheDocument();
  });

  it("creates a role and selects it", async () => {
    let created: unknown = null;
    const newRole = role({ id: "r-new", code: "AUDITOR", name: "ผู้ตรวจสอบ" });
    let roles = ROLES;
    mockApi({
      "GET /api/v1/roles": () => json(roles),
      "GET /api/v1/permissions": () => json(CATALOGUE),
      "POST /api/v1/roles": (_u, init) => {
        created = JSON.parse(String(init?.body));
        roles = [...ROLES, newRole];
        return json(newRole, 201);
      },
    });
    render(<RolesSettings />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: "สร้างบทบาท" }));
    const form = screen.getByRole("form", { name: "ฟอร์มสร้างบทบาท" });
    await userEvent.type(within(form).getByLabelText("รหัสบทบาท"), "auditor");
    await userEvent.type(within(form).getByLabelText("ชื่อบทบาท"), "ผู้ตรวจสอบ");
    await userEvent.click(within(form).getByRole("button", { name: "สร้าง" }));
    expect(await within(form).findByText(/ใช้ตัวพิมพ์ใหญ่/)).toBeInTheDocument();

    await userEvent.clear(within(form).getByLabelText("รหัสบทบาท"));
    await userEvent.type(within(form).getByLabelText("รหัสบทบาท"), "AUDITOR");
    await userEvent.click(within(form).getByRole("button", { name: "สร้าง" }));
    await vi.waitFor(() =>
      expect(created).toEqual({
        code: "AUDITOR",
        name: "ผู้ตรวจสอบ",
        description: "",
        permissions: [],
      }),
    );
    expect(await screen.findByRole("button", { name: /ผู้ตรวจสอบ/, current: true })).toBeVisible();
  });

  it("is read-only without roles:manage", async () => {
    permissions = new Set(["roles:read"]);
    mockApi({
      "GET /api/v1/roles": () => json(ROLES),
      "GET /api/v1/permissions": () => json(CATALOGUE),
    });
    render(<RolesSettings />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: /การเงิน/ }));
    expect(screen.queryByRole("button", { name: "สร้างบทบาท" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "บันทึกสิทธิ์" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "ลบบทบาท" })).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /ดูเอกสาร/ })).toBeDisabled();
  });
});

describe("EmailPreferencesCard", () => {
  it("shows when mail is unavailable and saves a single choice", async () => {
    let body: unknown = null;
    const items = [
      { type: "SECURITY", email_enabled: true, default: true },
      { type: "TICKET", email_enabled: true, default: true },
      { type: "DOCUMENT", email_enabled: false, default: false },
    ];
    mockApi({
      "GET /api/v1/notifications/preferences": () => json({ email_available: false, items }),
      "PUT /api/v1/notifications/preferences": (_u, init) => {
        body = JSON.parse(String(init?.body));
        return json({
          email_available: false,
          items: items.map((i) => (i.type === "TICKET" ? { ...i, email_enabled: false } : i)),
        });
      },
    });
    render(<EmailPreferencesCard />, { wrapper: createWrapper() });
    expect(await screen.findByText(/ยังไม่ได้ตั้งค่าเซิร์ฟเวอร์อีเมล/)).toBeInTheDocument();
    const ticket = screen.getByRole("checkbox", { name: /แจ้งปัญหาไอที/ });
    expect(ticket).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /เอกสาร/ })).not.toBeChecked();
    await userEvent.click(ticket);
    await vi.waitFor(() =>
      expect(body).toEqual({ items: [{ type: "TICKET", email_enabled: false }] }),
    );
    await vi.waitFor(() =>
      expect(screen.getByRole("checkbox", { name: /แจ้งปัญหาไอที/ })).not.toBeChecked(),
    );
  });
});
