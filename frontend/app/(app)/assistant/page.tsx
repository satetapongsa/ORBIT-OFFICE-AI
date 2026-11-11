import type { Metadata } from "next";
import { Suspense } from "react";

import { AssistantView } from "@/features/assistant/components/assistant-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "ผู้ช่วย AI" };

export default function AssistantPage() {
  // useSearchParams (prompt pre-fill) needs a Suspense boundary.
  return (
    <Suspense>
      <AssistantView />
    </Suspense>
  );
}
