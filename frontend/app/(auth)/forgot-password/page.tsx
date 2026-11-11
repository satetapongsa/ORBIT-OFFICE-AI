import type { Metadata } from "next";

import { AuthCard } from "@/components/common/auth-card";
import { ForgotPasswordForm } from "@/features/auth/components/password-reset-forms";

export const metadata: Metadata = { title: "ลืมรหัสผ่าน" };

export default function ForgotPasswordPage() {
  return (
    <AuthCard title="ลืมรหัสผ่าน" description="กรอกอีเมลเพื่อรับลิงก์สำหรับตั้งรหัสผ่านใหม่">
      <ForgotPasswordForm />
    </AuthCard>
  );
}
