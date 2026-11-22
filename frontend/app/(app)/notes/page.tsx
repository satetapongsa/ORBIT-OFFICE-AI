import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { NotesView } from "@/features/notes/components/notes-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "โน้ตของฉัน" };

export default function NotesPage() {
  return (
    <Suspense fallback={<Skeleton className="h-[28rem] w-full rounded-xl" />}>
      <NotesView />
    </Suspense>
  );
}
