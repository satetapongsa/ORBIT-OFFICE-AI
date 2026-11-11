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

// Thai vowels written before the consonant they follow in speech (เ แ โ ใ ไ).
const LEADING_VOWELS = /^[เ-ไ]+/;

function initial(name: string): string {
  return Array.from(name.trim().replace(LEADING_VOWELS, ""))[0] ?? "";
}

/** Avatar initials: first consonant/letter of first and last name ("ไอรดา เทคโน" → "อท"). */
export function initials(first: string, last: string): string {
  return `${initial(first)}${initial(last)}`.toUpperCase();
}

export function formatThaiDate(isoDate: string): string {
  return new Intl.DateTimeFormat("th-TH", { dateStyle: "long", timeZone: "UTC" }).format(
    new Date(`${isoDate}T00:00:00Z`),
  );
}
