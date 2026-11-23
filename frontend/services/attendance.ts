import { z } from "zod";

import { apiDownload, apiRequest } from "@/services/api-client";

/** Mirrors backend `app/schemas/attendance.py` (ADR-069). */
export const workModeSchema = z.enum(["OFFICE", "WFH", "ONSITE"]);
export type WorkMode = z.infer<typeof workModeSchema>;

export const WORK_MODE_LABELS: Record<WorkMode, string> = {
  OFFICE: "ที่ออฟฟิศ",
  WFH: "ทำงานที่บ้าน (WFH)",
  ONSITE: "นอกสถานที่",
};

export const attendanceSchema = z.object({
  id: z.string(),
  work_date: z.string(),
  check_in_at: z.string(),
  check_out_at: z.string().nullable(),
  work_mode: workModeSchema,
  late: z.boolean(),
  check_in_note: z.string().nullable(),
  check_out_note: z.string().nullable(),
  worked_minutes: z.number().int().nullable(),
});

const todaySchema = z.object({
  date: z.string(),
  server_time: z.string(),
  hours: z.object({ start: z.string(), end: z.string(), late_after: z.string() }),
  record: attendanceSchema.nullable(),
  on_leave: z.string().nullable(),
});

const summarySchema = z.object({
  days_present: z.number().int(),
  late_days: z.number().int(),
  wfh_days: z.number().int(),
  total_minutes: z.number().int(),
  average_check_in: z.string().nullable(),
});

const myMonthSchema = z.object({
  month: z.string(),
  records: z.array(attendanceSchema),
  summary: summarySchema,
});

const personSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  department_name: z.string().nullable(),
  job_title: z.string().nullable(),
});

const teamDaySchema = z.object({
  date: z.string(),
  rows: z.array(
    z.object({
      person: personSchema,
      record: attendanceSchema.nullable(),
      on_leave: z.string().nullable(),
    }),
  ),
  present: z.number().int(),
  late: z.number().int(),
  on_leave: z.number().int(),
  missing: z.number().int(),
});

const reportSchema = z.object({
  month: z.string(),
  working_days: z.number().int(),
  rows: z.array(
    z.object({
      person: personSchema,
      days_present: z.number().int(),
      late_days: z.number().int(),
      wfh_days: z.number().int(),
      leave_days: z.number(),
      total_minutes: z.number().int(),
    }),
  ),
});

export type Attendance = z.infer<typeof attendanceSchema>;
export type AttendanceToday = z.infer<typeof todaySchema>;
export type TeamDay = z.infer<typeof teamDaySchema>;
export type MonthlyReport = z.infer<typeof reportSchema>;

export const attendanceQueryKeys = {
  all: ["attendance"] as const,
  today: ["attendance", "today"] as const,
  me: (month: string) => ["attendance", "me", month] as const,
  team: (date: string, department: string) => ["attendance", "team", date, department] as const,
  report: (month: string, department: string) =>
    ["attendance", "report", month, department] as const,
};

export function fmtMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h} ชม. ${m} นาที` : `${m} นาที`;
}

export function getAttendanceToday(signal?: AbortSignal) {
  return apiRequest("/attendance/today", { schema: todaySchema, signal });
}

export function checkIn(work_mode: WorkMode, note: string) {
  return apiRequest("/attendance/check-in", {
    method: "POST",
    schema: todaySchema,
    body: { work_mode, note },
  });
}

export function checkOut(note: string) {
  return apiRequest("/attendance/check-out", {
    method: "POST",
    schema: todaySchema,
    body: { note },
  });
}

export function getMyAttendance(month: string, signal?: AbortSignal) {
  return apiRequest("/attendance/me", { schema: myMonthSchema, signal, query: { month } });
}

export function getTeamDay(date: string, departmentId: string, signal?: AbortSignal) {
  return apiRequest("/attendance/team", {
    schema: teamDaySchema,
    signal,
    query: { date, department_id: departmentId || undefined },
  });
}

export function getAttendanceReport(month: string, departmentId: string, signal?: AbortSignal) {
  return apiRequest("/attendance/report", {
    schema: reportSchema,
    signal,
    query: { month, department_id: departmentId || undefined },
  });
}

export function downloadAttendanceCsv(month: string, departmentId: string) {
  return apiDownload("/attendance/report.csv", {
    query: { month, department_id: departmentId || undefined },
    fallbackName: `attendance-${month}.csv`,
  });
}
