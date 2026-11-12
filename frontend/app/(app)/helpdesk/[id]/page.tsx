import type { Metadata } from "next";

import { TicketDetailView } from "@/features/helpdesk/components/ticket-detail-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "แจ้งปัญหาไอที" };

export default async function TicketPage({ params }: PageProps<"/helpdesk/[id]">) {
  const { id } = await params;
  return <TicketDetailView id={id} />;
}
