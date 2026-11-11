import type { EmploymentStatus, EmploymentType } from "@/services/employees";

export const EMPLOYMENT_STATUS_LABELS: Record<EmploymentStatus, string> = {
  ACTIVE: "ปฏิบัติงาน",
  ON_LEAVE: "ลางาน",
  SUSPENDED: "พักงาน",
  TERMINATED: "พ้นสภาพ",
};

export const EMPLOYMENT_TYPE_LABELS: Record<EmploymentType, string> = {
  FULL_TIME: "พนักงานประจำ",
  PART_TIME: "พนักงานพาร์ทไทม์",
  CONTRACT: "พนักงานสัญญาจ้าง",
  INTERN: "นักศึกษาฝึกงาน",
};

/** Initials for avatars: first letter of first and last name (Thai or Latin). */
export function initials(first: string, last: string): string {
  return `${Array.from(first.trim())[0] ?? ""}${Array.from(last.trim())[0] ?? ""}`.toUpperCase();
}

export function formatThaiDate(isoDate: string): string {
  return new Intl.DateTimeFormat("th-TH", { dateStyle: "long", timeZone: "UTC" }).format(
    new Date(`${isoDate}T00:00:00Z`),
  );
}
