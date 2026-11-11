import type { Metadata } from "next";

import { EmployeeProfileView } from "@/features/employees/components/employee-profile-view";

// Rendered after the client-side session check (AuthGate); see app/(app)/layout.tsx.
export const instant = false;

export const metadata: Metadata = { title: "ข้อมูลพนักงาน" };

export default async function EmployeePage({ params }: PageProps<"/employees/[id]">) {
  const { id } = await params;
  return <EmployeeProfileView id={id} />;
}
