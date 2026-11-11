import type { Metadata } from "next";

import { PageHeader } from "@/components/common/page-header";
import { AccountOverview } from "@/features/account/components/account-overview";

export const metadata: Metadata = { title: "บัญชีของฉัน" };

export default function AccountPage() {
  return (
    <>
      <PageHeader title="บัญชีของฉัน" description="ข้อมูลบัญชี บทบาท และการตั้งรหัสผ่าน" />
      <AccountOverview />
    </>
  );
}
