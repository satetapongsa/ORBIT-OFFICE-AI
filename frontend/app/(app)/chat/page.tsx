import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { ChatView } from "@/features/chat/components/chat-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "แชท" };

export default function ChatPage() {
  return (
    <Suspense fallback={<Skeleton className="h-[28rem] w-full rounded-xl" />}>
      <ChatView />
    </Suspense>
  );
}
