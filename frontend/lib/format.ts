/** Thai date/time formatting. The business time zone matches the backend's APP_TIMEZONE. */
export const DEFAULT_TIME_ZONE = "Asia/Bangkok";

export function formatDateTime(value: string, timeZone: string = DEFAULT_TIME_ZONE): string {
  return new Intl.DateTimeFormat("th-TH", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  }).format(new Date(value));
}

/** A calendar day (`YYYY-MM-DD`) as a short Thai label, e.g. "11 พ.ย.". */
export function formatDay(isoDate: string, options: Intl.DateTimeFormatOptions = {}): string {
  return new Intl.DateTimeFormat("th-TH", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
    ...options,
  }).format(new Date(`${isoDate}T00:00:00Z`));
}

export function formatLongDate(date: Date, timeZone: string = DEFAULT_TIME_ZONE): string {
  return new Intl.DateTimeFormat("th-TH", { dateStyle: "full", timeZone }).format(date);
}

const relative = new Intl.RelativeTimeFormat("th-TH", { numeric: "auto" });
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

/** "5 นาทีที่ผ่านมา"; falls back to an absolute date after a week. */
export function formatRelative(value: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(value).getTime() - now.getTime()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return "เมื่อสักครู่";
  if (abs >= 7 * 86_400) return formatDateTime(value);
  for (const [unit, size] of UNITS) {
    if (abs >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return relative.format(Math.round(seconds / 60), "minute");
}

export const numberFormat = new Intl.NumberFormat("th-TH");

/** Clock time only, e.g. "14:05" (business time zone). */
export function formatTime(value: string, timeZone: string = DEFAULT_TIME_ZONE): string {
  return new Intl.DateTimeFormat("th-TH", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(new Date(value));
}

/** Calendar day key `YYYY-MM-DD` in the business time zone (for grouping by day). */
export function dayKey(value: string | Date, timeZone: string = DEFAULT_TIME_ZONE): string {
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone,
  }).format(new Date(value));
}

/** Chat day separator: "วันนี้", "เมื่อวาน", or a date such as "จ. 20 พ.ย. 2569". */
export function formatChatDay(
  value: string,
  now: Date = new Date(),
  timeZone: string = DEFAULT_TIME_ZONE,
): string {
  const key = dayKey(value, timeZone);
  if (key === dayKey(now, timeZone)) return "วันนี้";
  if (key === dayKey(new Date(now.getTime() - 86_400_000), timeZone)) return "เมื่อวาน";
  return new Intl.DateTimeFormat("th-TH", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone,
  }).format(new Date(value));
}
