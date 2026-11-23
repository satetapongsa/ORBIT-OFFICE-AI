import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { LeaveView } from "@/features/leave/components/leave-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "ลางาน" };

export default function LeavePage() {
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full rounded-xl" />}>
      <LeaveView />
    </Suspense>
  );
}
