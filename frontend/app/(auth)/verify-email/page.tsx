import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthCard } from "@/components/common/auth-card";
import { Skeleton } from "@/components/ui/skeleton";
import { VerifyEmailForm } from "@/features/auth/components/register-forms";

export const metadata: Metadata = { title: "ยืนยันอีเมล" };

export default function VerifyEmailPage() {
  return (
    <AuthCard title="ยืนยันอีเมล" description="กดปุ่มด้านล่างเพื่อยืนยันอีเมลและเริ่มใช้งาน">
      <Suspense fallback={<Skeleton className="h-24 w-full" />}>
        <VerifyEmailForm />
      </Suspense>
    </AuthCard>
  );
}
