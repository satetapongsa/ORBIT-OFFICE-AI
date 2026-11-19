import type { Metadata } from "next";

import { AuthCard } from "@/components/common/auth-card";
import { RegisterForm } from "@/features/auth/components/register-forms";

export const metadata: Metadata = { title: "สมัครสมาชิก" };

export default function RegisterPage() {
  return (
    <AuthCard
      title="สมัครสมาชิก"
      description="สมัครด้วยอีเมลบริษัท แล้วยืนยันผ่านลิงก์ที่ส่งไปทางอีเมล"
    >
      <RegisterForm />
    </AuthCard>
  );
}
