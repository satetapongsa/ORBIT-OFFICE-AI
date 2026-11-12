import type { Metadata } from "next";

import { HelpdeskView } from "@/features/helpdesk/components/helpdesk-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "แจ้งปัญหาไอที" };

export default function HelpdeskPage() {
  return <HelpdeskView />;
}
