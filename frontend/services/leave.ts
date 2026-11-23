import { z } from "zod";

import { apiRequest } from "@/services/api-client";

/** Mirrors backend `app/schemas/leave.py` (ADR-068). Decimals arrive as strings ("2.0"). */
const decimal = z.union([z.string(), z.number()]).transform((v) => Number(v));

export const leaveTypeSchema = z.object({
  id: z.string(),
  code: z.string(),
  name: z.string(),
  days_per_year: decimal.nullable(),
  color: z.string(),
  is_active: z.boolean(),
});

export const leaveBalanceSchema = z.object({
  leave_type: leaveTypeSchema,
  year: z.number().int(),
  quota: decimal.nullable(),
  used: decimal,
  pending: decimal,
  remaining: decimal.nullable(),
});

export const leaveStatusSchema = z.enum(["PENDING", "APPROVED", "REJECTED", "CANCELLED"]);
export const halfDaySchema = z.enum(["NONE", "MORNING", "AFTERNOON"]);

export const leaveRequestSchema = z.object({
  id: z.string(),
  person: z.object({
    id: z.string(),
    display_name: z.string(),
    department_name: z.string().nullable(),
  }),
  leave_type: leaveTypeSchema,
  start_date: z.string(),
  end_date: z.string(),
  half_day: halfDaySchema,
  days: decimal,
  reason: z.string(),
  status: leaveStatusSchema,
  decided_by_name: z.string().nullable(),
  decided_at: z.string().nullable(),
  decision_note: z.string().nullable(),
  created_at: z.string(),
  can_decide: z.boolean(),
  can_cancel: z.boolean(),
});

const myLeaveSchema = z.object({
  year: z.number().int(),
  balances: z.array(leaveBalanceSchema),
  requests: z.array(leaveRequestSchema),
});

export type LeaveType = z.infer<typeof leaveTypeSchema>;
export type LeaveBalance = z.infer<typeof leaveBalanceSchema>;
export type LeaveRequest = z.infer<typeof leaveRequestSchema>;
export type LeaveStatus = z.infer<typeof leaveStatusSchema>;
export type HalfDay = z.infer<typeof halfDaySchema>;

export const LEAVE_STATUS_LABELS: Record<LeaveStatus, string> = {
  PENDING: "รออนุมัติ",
  APPROVED: "อนุมัติแล้ว",
  REJECTED: "ไม่อนุมัติ",
  CANCELLED: "ยกเลิกแล้ว",
};
export const HALF_DAY_LABELS: Record<HalfDay, string> = {
  NONE: "เต็มวัน",
  MORNING: "ครึ่งเช้า",
  AFTERNOON: "ครึ่งบ่าย",
};

export const leaveQueryKeys = {
  all: ["leave"] as const,
  me: (year: number) => ["leave", "me", year] as const,
  types: (all: boolean) => ["leave", "types", all] as const,
  approvals: ["leave", "approvals"] as const,
  calendar: (start: string, end: string) => ["leave", "calendar", start, end] as const,
};

/** 2 -> "2", 0.5 -> "0.5". */
export function fmtDays(days: number): string {
  return Number.isInteger(days) ? String(days) : days.toFixed(1);
}

/** Monday-Friday between two ISO dates (inclusive); mirrors the backend. */
export function workingDays(start: string, end: string, half: HalfDay = "NONE"): number {
  if (!start || !end || end < start) return 0;
  const from = new Date(`${start}T00:00:00Z`);
  const to = new Date(`${end}T00:00:00Z`);
  if (half !== "NONE") return from.getUTCDay() % 6 === 0 ? 0 : 0.5;
  let days = 0;
  for (let t = from.getTime(); t <= to.getTime(); t += 86_400_000) {
    const wd = new Date(t).getUTCDay();
    if (wd !== 0 && wd !== 6) days += 1;
  }
  return days;
}

export function getMyLeave(year: number, signal?: AbortSignal) {
  return apiRequest("/leave/me", { schema: myLeaveSchema, signal, query: { year } });
}

export function listLeaveTypes(includeInactive: boolean, signal?: AbortSignal) {
  return apiRequest("/leave/types", {
    schema: z.array(leaveTypeSchema),
    signal,
    query: { include_inactive: includeInactive || undefined },
  });
}

export function createLeaveRequest(input: {
  leave_type_id: string;
  start_date: string;
  end_date: string;
  half_day: HalfDay;
  reason: string;
}) {
  return apiRequest("/leave/requests", { method: "POST", schema: leaveRequestSchema, body: input });
}

export function listLeaveApprovals(signal?: AbortSignal) {
  return apiRequest("/leave/requests", {
    schema: z.array(leaveRequestSchema),
    signal,
    query: { scope: "approvals" },
  });
}

export function decideLeave(id: string, approve: boolean, note: string) {
  return apiRequest(`/leave/requests/${encodeURIComponent(id)}/decision`, {
    method: "POST",
    schema: leaveRequestSchema,
    body: { approve, note },
  });
}

export function cancelLeave(id: string) {
  return apiRequest(`/leave/requests/${encodeURIComponent(id)}/cancel`, {
    method: "POST",
    schema: leaveRequestSchema,
  });
}

export function getLeaveCalendar(start: string, end: string, signal?: AbortSignal) {
  return apiRequest("/leave/calendar", {
    schema: z.array(leaveRequestSchema),
    signal,
    query: { start, end },
  });
}

export function updateLeaveType(
  id: string,
  input: { name?: string; days_per_year?: number; unlimited?: boolean; is_active?: boolean },
) {
  return apiRequest(`/leave/types/${encodeURIComponent(id)}`, {
    method: "PATCH",
    schema: leaveTypeSchema,
    body: input,
  });
}
