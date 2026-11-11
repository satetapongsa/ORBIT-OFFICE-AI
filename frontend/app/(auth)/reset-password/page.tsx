import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthCard } from "@/components/common/auth-card";
import { Skeleton } from "@/components/ui/skeleton";
import { ResetPasswordForm } from "@/features/auth/components/password-reset-forms";

export const metadata: Metadata = { title: "ตั้งรหัสผ่านใหม่" };

export default function ResetPasswordPage() {
  return (
    <AuthCard title="ตั้งรหัสผ่านใหม่" description="ลิงก์นี้ใช้ได้ครั้งเดียวและมีอายุจำกัด">
      <Suspense fallback={<Skeleton className="h-40 w-full" />}>
        <ResetPasswordForm />
      </Suspense>
    </AuthCard>
  );
}
