import type { Metadata } from "next";

import { DashboardView } from "@/features/dashboard/components/dashboard-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "แดชบอร์ด" };

export default function DashboardPage() {
  return <DashboardView />;
}
