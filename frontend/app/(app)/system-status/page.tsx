import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";
import { SystemStatusPanel } from "@/features/system-status/components/system-status-panel";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "สถานะระบบ" };

export default function SystemStatusPage() {
  return (
    <>
      <PageHeader
        title="สถานะระบบ"
        description="ผลการตรวจสอบบริการที่ AURA OFFICE AI ต้องใช้ ดึงข้อมูลจริงจาก API ของระบบ และรีเฟรชอัตโนมัติทุก 30 วินาที"
      />
      <SystemStatusPanel />
    </>
  );
}
