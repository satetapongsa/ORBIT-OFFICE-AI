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
