import { z } from "zod";

import { apiRequest } from "@/services/api-client";

/** Mirrors backend `app/schemas/meetings.py` (ADR-070). */
export const responseSchema = z.enum(["PENDING", "ACCEPTED", "TENTATIVE", "DECLINED"]);
export type MeetingResponse = z.infer<typeof responseSchema>;

export const RESPONSE_LABELS: Record<MeetingResponse, string> = {
  PENDING: "ยังไม่ตอบ",
  ACCEPTED: "เข้าร่วม",
  TENTATIVE: "อาจเข้าร่วม",
  DECLINED: "ไม่เข้าร่วม",
};

const personSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  department_name: z.string().nullable(),
});

export const meetingSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string(),
  location: z.string().nullable(),
  online_url: z.string().nullable(),
  start_at: z.string(),
  end_at: z.string(),
  organizer: personSchema.nullable(),
  attendees: z.array(personSchema.extend({ response: responseSchema, is_organizer: z.boolean() })),
  my_response: responseSchema.nullable(),
  is_organizer: z.boolean(),
  cancelled: z.boolean(),
  reminder_minutes: z.number().int(),
});

export const leaveEventSchema = z.object({
  id: z.string(),
  person_name: z.string(),
  leave_type: z.string(),
  color: z.string(),
  start_date: z.string(),
  end_date: z.string(),
  half_day: z.string(),
});

const feedSchema = z.object({ meetings: z.array(meetingSchema), leave: z.array(leaveEventSchema) });
const availabilitySchema = z.object({
  conflicts: z.array(
    z.object({
      user_id: z.string(),
      display_name: z.string(),
      kind: z.enum(["meeting", "leave"]),
      detail: z.string(),
    }),
  ),
});

export type Meeting = z.infer<typeof meetingSchema>;
export type LeaveEvent = z.infer<typeof leaveEventSchema>;
export type Conflict = z.infer<typeof availabilitySchema>["conflicts"][number];

export interface MeetingInput {
  title: string;
  description: string;
  location: string | null;
  online_url: string | null;
  start_at: string;
  end_at: string;
  attendee_ids: string[];
  reminder_minutes: number;
}

export const calendarQueryKeys = {
  all: ["calendar"] as const,
  events: (start: string, end: string) => ["calendar", "events", start, end] as const,
  meeting: (id: string) => ["calendar", "meeting", id] as const,
};

export function getCalendar(start: string, end: string, signal?: AbortSignal) {
  return apiRequest("/calendar/events", { schema: feedSchema, signal, query: { start, end } });
}

export function getMeeting(id: string, signal?: AbortSignal) {
  return apiRequest(`/calendar/meetings/${encodeURIComponent(id)}`, {
    schema: meetingSchema,
    signal,
  });
}

export function createMeeting(input: MeetingInput) {
  return apiRequest("/calendar/meetings", { method: "POST", schema: meetingSchema, body: input });
}

export function updateMeeting(id: string, input: MeetingInput) {
  return apiRequest(`/calendar/meetings/${encodeURIComponent(id)}`, {
    method: "PATCH",
    schema: meetingSchema,
    body: input,
  });
}

export function cancelMeeting(id: string) {
  return apiRequest(`/calendar/meetings/${encodeURIComponent(id)}/cancel`, {
    method: "POST",
    schema: meetingSchema,
  });
}

export function respondMeeting(id: string, response: Exclude<MeetingResponse, "PENDING">) {
  return apiRequest(`/calendar/meetings/${encodeURIComponent(id)}/respond`, {
    method: "POST",
    schema: meetingSchema,
    body: { response },
  });
}

export function checkAvailability(input: {
  user_ids: string[];
  start_at: string;
  end_at: string;
  exclude_meeting_id?: string;
}) {
  return apiRequest("/calendar/availability", {
    method: "POST",
    schema: availabilitySchema,
    body: input,
  });
}
