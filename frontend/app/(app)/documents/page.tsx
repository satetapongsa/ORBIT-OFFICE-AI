import type { Metadata } from "next";

import { DocumentsView } from "@/features/documents/components/documents-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "ศูนย์เอกสาร" };

export default function DocumentsPage() {
  return <DocumentsView />;
}
