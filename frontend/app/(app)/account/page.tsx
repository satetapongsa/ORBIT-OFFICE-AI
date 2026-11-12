import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";
import { AccountOverview } from "@/features/account/components/account-overview";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "บัญชีของฉัน" };

export default function AccountPage() {
  return (
    <>
      <PageHeader
        title="บัญชีของฉัน"
        description="ข้อมูลบัญชี บทบาท รหัสผ่าน และการแจ้งเตือนทางอีเมล"
      />
      <AccountOverview />
    </>
  );
}
