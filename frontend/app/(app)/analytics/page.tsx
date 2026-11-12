import type { Metadata } from "next";

import { AnalyticsView } from "@/features/analytics/components/analytics-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "รายงานและการวิเคราะห์" };

export default function AnalyticsPage() {
  return <AnalyticsView />;
}
