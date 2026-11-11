import type { Metadata } from "next";

import { TasksView } from "@/features/tasks/components/tasks-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "จัดการงาน" };

export default function TasksPage() {
  return <TasksView />;
}
