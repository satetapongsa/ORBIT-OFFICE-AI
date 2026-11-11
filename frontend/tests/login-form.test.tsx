import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/features/auth/components/login-form";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams("next=//evil.example.com"),
}));

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const me = {
  user: {
    id: "u1",
    employee_code: "E-1",
    email: "emp@example.com",
    first_name: "a",
    last_name: "b",
    display_name: "a b",
    department: null,
    job_title: null,
    phone_work: null,
    employment_status: "ACTIVE",
    is_active: true,
    roles: [{ id: "r1", code: "EMPLOYEE", name: "พนักงาน" }],
    last_login_at: null,
    created_at: "2026-11-11T00:00:00Z",
    updated_at: "2026-11-11T00:00:00Z",
  },
  permissions: ["documents:read"],
};

describe("LoginForm", () => {
  it("validates input in Thai before calling the API", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<LoginForm />, { wrapper: Wrapper });
    await userEvent.click(screen.getByRole("button", { name: "เข้าสู่ระบบ" }));
    expect(await screen.findByText("กรุณากรอกอีเมล")).toBeInTheDocument();
    expect(screen.getByText("กรุณากรอกรหัสผ่าน")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the backend error message on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "unauthenticated", message: "อีเมลหรือรหัสผ่านไม่ถูกต้อง", details: [] },
          }),
          { status: 401 },
        ),
      ),
    );
    render(<LoginForm />, { wrapper: Wrapper });
    await userEvent.type(screen.getByLabelText("อีเมล"), "emp@example.com");
    await userEvent.type(screen.getByLabelText("รหัสผ่าน"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "เข้าสู่ระบบ" }));
    expect(await screen.findByText("อีเมลหรือรหัสผ่านไม่ถูกต้อง")).toBeInTheDocument();
  });

  it("signs in and ignores an unsafe ?next= redirect", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(me), { status: 200 })),
    );
    render(<LoginForm />, { wrapper: Wrapper });
    await userEvent.type(screen.getByLabelText("อีเมล"), "emp@example.com");
    await userEvent.type(screen.getByLabelText("รหัสผ่าน"), "Correct-Password-1");
    await userEvent.click(screen.getByRole("button", { name: "เข้าสู่ระบบ" }));
    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });
});
