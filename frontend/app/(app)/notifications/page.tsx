import type { Metadata } from "next";

import { NotificationsView } from "@/features/notifications/components/notifications-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "การแจ้งเตือน" };

export default function NotificationsPage() {
  return <NotificationsView />;
}
