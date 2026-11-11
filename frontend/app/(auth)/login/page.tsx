import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthCard } from "@/components/common/auth-card";
import { Skeleton } from "@/components/ui/skeleton";
import { LoginForm } from "@/features/auth/components/login-form";

export const metadata: Metadata = { title: "เข้าสู่ระบบ" };

export default function LoginPage() {
  return (
    <AuthCard title="เข้าสู่ระบบ" description="ใช้อีเมลและรหัสผ่านของบริษัท">
      <Suspense fallback={<Skeleton className="h-56 w-full" />}>
        <LoginForm />
      </Suspense>
    </AuthCard>
  );
}
