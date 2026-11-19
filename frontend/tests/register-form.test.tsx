import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RegisterForm, RegisterLink } from "@/features/auth/components/register-forms";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(""),
}));

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const OPEN = { enabled: true, allowed_domains: ["orbit.example.com"] };

afterEach(() => vi.unstubAllGlobals());

describe("RegisterForm", () => {
  it("explains that sign-up is closed when disabled", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ enabled: false, allowed_domains: [] })),
    );
    render(<RegisterForm />, { wrapper: Wrapper });
    expect(await screen.findByText(/ยังไม่เปิดให้สมัครสมาชิกเอง/)).toBeInTheDocument();
  });

  it("validates fields and password confirmation before calling the API", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(OPEN));
    vi.stubGlobal("fetch", fetchMock);
    render(<RegisterForm />, { wrapper: Wrapper });
    expect(await screen.findByText("ใช้ได้เฉพาะอีเมล @orbit.example.com")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("รหัสผ่าน"), "Long-Enough-Pass-1");
    await userEvent.type(screen.getByLabelText("ยืนยันรหัสผ่าน"), "Different-Pass-22");
    await userEvent.click(screen.getByRole("button", { name: "สมัครสมาชิก" }));
    expect(await screen.findByText("กรุณากรอกชื่อ")).toBeInTheDocument();
    expect(screen.getByText("รหัสผ่านทั้งสองช่องไม่ตรงกัน")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1); // only the registration-info request
  });

  it("submits and shows the check-your-e-mail message", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(OPEN))
      .mockResolvedValueOnce(json({ message: "เราได้ส่งลิงก์ยืนยันไปที่อีเมลแล้ว" }, 202));
    vi.stubGlobal("fetch", fetchMock);
    render(<RegisterForm />, { wrapper: Wrapper });
    await userEvent.type(await screen.findByLabelText("ชื่อ"), "สมชาย");
    await userEvent.type(screen.getByLabelText("นามสกุล"), "ใจดี");
    await userEvent.type(screen.getByLabelText("อีเมลบริษัท"), "somchai@orbit.example.com");
    await userEvent.type(screen.getByLabelText("รหัสผ่าน"), "Long-Enough-Pass-1");
    await userEvent.type(screen.getByLabelText("ยืนยันรหัสผ่าน"), "Long-Enough-Pass-1");
    await userEvent.click(screen.getByRole("button", { name: "สมัครสมาชิก" }));
    expect(await screen.findByText("เราได้ส่งลิงก์ยืนยันไปที่อีเมลแล้ว")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toContain("/auth/register");
    expect(JSON.parse(init.body as string)).toEqual({
      email: "somchai@orbit.example.com",
      first_name: "สมชาย",
      last_name: "ใจดี",
      password: "Long-Enough-Pass-1",
    });
  });
});

describe("RegisterLink", () => {
  it("is hidden while sign-up is closed and shown when open", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(OPEN)));
    render(<RegisterLink />, { wrapper: Wrapper });
    expect(await screen.findByRole("link", { name: "สมัครสมาชิก" })).toHaveAttribute(
      "href",
      "/register",
    );
  });
});
