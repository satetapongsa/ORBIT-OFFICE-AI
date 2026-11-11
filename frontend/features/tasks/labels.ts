import type { TaskEventType, TaskPriority, TaskStatus } from "@/services/tasks";

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  TODO: "รอดำเนินการ",
  IN_PROGRESS: "กำลังดำเนินการ",
  REVIEW: "รอตรวจสอบ",
  COMPLETED: "เสร็จสิ้น",
  CANCELLED: "ยกเลิก",
};

export const TASK_PRIORITY_LABELS: Record<TaskPriority, string> = {
  LOW: "ต่ำ",
  MEDIUM: "ปานกลาง",
  HIGH: "สูง",
  URGENT: "ด่วนที่สุด",
};

export const TASK_FIELD_LABELS: Record<string, string> = {
  title: "ชื่องาน",
  description: "รายละเอียด",
  priority: "ความสำคัญ",
  due_at: "กำหนดส่ง",
  department_id: "แผนก",
};

export const TASK_EVENT_LABELS: Record<TaskEventType, string> = {
  CREATED: "สร้างงาน",
  UPDATED: "แก้ไขงาน",
  STATUS_CHANGED: "เปลี่ยนสถานะ",
  ASSIGNED: "มอบหมายให้",
  UNASSIGNED: "ถอนการมอบหมาย",
  COMMENTED: "แสดงความคิดเห็น",
  ATTACHMENT_ADDED: "แนบไฟล์",
  ATTACHMENT_REMOVED: "ลบไฟล์แนบ",
};

/** Statuses are kept in DB order; this is also the board/progress order in the UI. */
export const STATUS_ORDER: TaskStatus[] = [
  "TODO",
  "IN_PROGRESS",
  "REVIEW",
  "COMPLETED",
  "CANCELLED",
];

const BANGKOK_OFFSET = "+07:00"; // Asia/Bangkok has no daylight-saving time.

/** `YYYY-MM-DD` from a date input → end of that business day in Bangkok (ISO with offset). */
export function dueDateToIso(day: string): string | null {
  return day ? `${day}T23:59:00${BANGKOK_OFFSET}` : null;
}

/** ISO timestamp → `YYYY-MM-DD` in the business time zone, for a date input. */
export function isoToDueDate(iso: string | null): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok" }).format(new Date(iso));
}

export function formatDue(iso: string): string {
  return new Intl.DateTimeFormat("th-TH", {
    day: "numeric",
    month: "short",
    year: "2-digit",
    timeZone: "Asia/Bangkok",
  }).format(new Date(iso));
}
