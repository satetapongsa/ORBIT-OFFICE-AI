"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { ErrorState } from "@/components/common/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/features/auth/hooks/use-session";
import { onSessionExpired } from "@/services/api-client";
import { ApiError } from "@/services/api-client";

function loginUrl(pathname: string): string {
  return pathname && pathname !== "/" ? `/login?next=${encodeURIComponent(pathname)}` : "/login";
}

/**
 * Renders the app only for signed-in users and sends everyone else to the login page.
 * This is a convenience for the UI — every API call is still authorised by the backend.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname() ?? "/";

  useEffect(() => {
    if (session.isUnauthenticated) router.replace(loginUrl(pathname));
  }, [session.isUnauthenticated, router, pathname]);

  useEffect(
    () => onSessionExpired(() => router.replace(loginUrl(window.location.pathname))),
    [router],
  );

  if (session.isAuthenticated) return <>{children}</>;

  if (session.error && !session.isUnauthenticated) {
    const apiError = session.error instanceof ApiError ? session.error : null;
    return (
      <div className="mx-auto max-w-lg p-6 pt-24">
        <ErrorState
          title="ไม่สามารถตรวจสอบสถานะการเข้าสู่ระบบได้"
          message={apiError?.message ?? "เกิดข้อผิดพลาดที่ไม่ทราบสาเหตุ"}
          requestId={apiError?.requestId}
          onRetry={session.refetch}
        />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen" aria-busy="true" aria-label="กำลังตรวจสอบการเข้าสู่ระบบ">
      <Skeleton className="hidden h-screen w-64 rounded-none lg:block" />
      <div className="flex-1 space-y-4 p-6">
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    </div>
  );
}
