import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";
import { RolesSettings } from "@/features/settings/components/roles-settings";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "ตั้งค่า" };

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        title="ตั้งค่า"
        description="บทบาทและสิทธิ์การใช้งาน (ผู้ใช้และแผนกจัดการได้ที่ศูนย์พนักงาน)"
      />
      <RolesSettings />
    </>
  );
}
