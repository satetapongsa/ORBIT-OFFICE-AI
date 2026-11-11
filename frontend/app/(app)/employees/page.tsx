import type { Metadata } from "next";

import { EmployeesView } from "@/features/employees/components/employees-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "ศูนย์พนักงาน" };

export default function EmployeesPage() {
  return <EmployeesView />;
}
