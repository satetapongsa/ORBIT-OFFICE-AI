import type { Metadata } from "next";

import { AssistantView } from "@/features/assistant/components/assistant-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "ผู้ช่วย AI" };

export default function AssistantPage() {
  return <AssistantView />;
}
