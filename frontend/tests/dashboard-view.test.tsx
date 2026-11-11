import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DashboardView } from "@/features/dashboard/components/dashboard-view";

import { adminSummary, createWrapper, employeeSummary, json, mockApi } from "./fixtures";

vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({ me: { user: { id: "u-1" } }, has: () => true }),
}));

describe("DashboardView", () => {
  it("shows personal metrics and hides sections the API did not return", async () => {
    mockApi({ "GET /api/v1/dashboard/summary": () => json(employeeSummary()) });
    render(<DashboardView />, { wrapper: createWrapper() });

    expect(await screen.findByText("สวัสดี, สมชาย ใจดี")).toBeInTheDocument();
    expect(screen.getByTestId("stat-unread")).toHaveTextContent("2");
    expect(screen.getByTestId("stat-sessions")).toHaveTextContent("2");
    expect(screen.getByTestId("stat-documents")).toHaveTextContent("7");
    // Fixture period: (0+1+2)×4 + 0 + 3 = 15 sign-ins.
    expect(screen.getByTestId("stat-sign-ins")).toHaveTextContent("15");

    expect(screen.queryByTestId("organization-section")).not.toBeInTheDocument();
    expect(screen.queryByTestId("security-section")).not.toBeInTheDocument();

    const preview = screen.getByTestId("notification-preview");
    expect(within(preview).getByText("รหัสผ่านของคุณถูกเปลี่ยนแล้ว")).toBeInTheDocument();
    expect(
      within(preview).getByRole("link", { name: /รหัสผ่านของคุณถูกเปลี่ยนแล้ว/ }),
    ).toHaveAttribute("href", "/account");

    // Document notifications (Phase 4) are part of the preview.
    expect(within(preview).getByRole("link", { name: /มีการแชร์เอกสารให้คุณ/ })).toHaveAttribute(
      "href",
      "/documents/doc-1",
    );
    const docs = screen.getByTestId("documents-card");
    expect(docs).toHaveTextContent("เอกสารของคุณ 2 รายการ · กำลังประมวลผล 1");
    expect(within(docs).getByRole("link", { name: /นโยบายการลา/ })).toHaveAttribute(
      "href",
      "/documents/doc-1",
    );

    const activity = within(screen.getByTestId("my-activity")).getAllByTestId("activity-item");
    expect(activity[0]).toHaveTextContent("เข้าสู่ระบบ");
    expect(activity[0]).not.toHaveTextContent("สมชาย"); // own actions are not attributed
    expect(activity[1]).toHaveTextContent("แก้ไขข้อมูลผู้ใช้ · ผู้ดูแล ระบบ");
  });

  it("renders organisation and security sections when present", async () => {
    mockApi({ "GET /api/v1/dashboard/summary": () => json(adminSummary()) });
    render(<DashboardView />, { wrapper: createWrapper() });

    const org = await screen.findByTestId("organization-section");
    expect(within(org).getByTestId("stat-active-users")).toHaveTextContent("42");
    expect(within(org).getByTestId("stat-active-users")).toHaveTextContent("ระงับ 3 บัญชี");
    expect(within(org).getByTestId("headcount-SALES")).toHaveTextContent("ฝ่ายขาย");
    expect(within(org).getByTestId("headcount-none")).toHaveTextContent("ไม่ระบุแผนก");

    const security = screen.getByTestId("security-section");
    expect(within(security).getByTestId("stat-failed-sign-ins")).toHaveTextContent("9");
    // The stacked chart has a legend naming both series.
    expect(within(security).getByLabelText("คำอธิบายสัญลักษณ์")).toHaveTextContent(
      "เข้าสู่ระบบไม่สำเร็จ",
    );
    expect(within(screen.getByTestId("org-activity")).getByText(/คำเตือน/)).toBeInTheDocument();
  });

  it("shows an error with a working retry", async () => {
    let calls = 0;
    mockApi({
      "GET /api/v1/dashboard/summary": () =>
        ++calls === 1
          ? json(
              { error: { code: "internal_error", message: "ระบบขัดข้อง", request_id: "r-1" } },
              500,
            )
          : json(employeeSummary()),
    });
    render(<DashboardView />, { wrapper: createWrapper() });

    expect(await screen.findByRole("alert")).toHaveTextContent("ไม่สามารถโหลดแดชบอร์ดได้");
    expect(screen.getByRole("alert")).toHaveTextContent("r-1");
    await userEvent.click(screen.getByRole("button", { name: "ลองใหม่" }));
    expect(await screen.findByText("สวัสดี, สมชาย ใจดี")).toBeInTheDocument();
  });
});
