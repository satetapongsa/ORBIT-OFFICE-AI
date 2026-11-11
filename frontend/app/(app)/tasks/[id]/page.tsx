import type { Metadata } from "next";

import { TaskDetailView } from "@/features/tasks/components/task-detail-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "งาน" };

export default async function TaskPage({ params }: PageProps<"/tasks/[id]">) {
  const { id } = await params;
  return <TaskDetailView id={id} />;
}
