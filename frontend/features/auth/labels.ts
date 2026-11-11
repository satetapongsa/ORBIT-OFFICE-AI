/** Thai labels for system roles; custom roles use the name stored in the database. */
const SYSTEM_ROLE_LABELS: Record<string, string> = {
  ADMIN: "ผู้ดูแลระบบ",
  MANAGER: "ผู้จัดการ",
  EMPLOYEE: "พนักงาน",
  HR: "ฝ่ายบุคคล",
  IT_SUPPORT: "ฝ่ายไอที",
};

export function roleLabel(code: string, fallback: string): string {
  return SYSTEM_ROLE_LABELS[code] ?? fallback;
}
