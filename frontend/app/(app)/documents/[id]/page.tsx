import type { Metadata } from "next";

import { DocumentDetailView } from "@/features/documents/components/document-detail-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "เอกสาร" };

export default async function DocumentPage({ params }: PageProps<"/documents/[id]">) {
  const { id } = await params;
  return <DocumentDetailView id={id} />;
}
