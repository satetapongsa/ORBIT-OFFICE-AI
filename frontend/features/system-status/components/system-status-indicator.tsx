"use client";

import Link from "next/link";

import { cn } from "@/lib/utils";
import { useReadiness } from "@/features/system-status/hooks/use-readiness";

/** Compact header indicator backed by the real readiness endpoint. */
export function SystemStatusIndicator() {
  const { data, isPending, isError } = useReadiness();

  let label = "กำลังตรวจสอบระบบ…";
  let dot = "bg-muted-foreground/40 animate-pulse";
  if (isError) {
    label = "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้";
    dot = "bg-red-500";
  } else if (!isPending && data) {
    const ok = data.status === "ok";
    label = ok ? "ระบบพร้อมใช้งาน" : "ระบบขัดข้องบางส่วน";
    dot = ok ? "bg-emerald-500" : "bg-amber-500";
  }

  return (
    <Link
      href="/"
      className="text-muted-foreground hover:bg-muted flex items-center gap-2 rounded-full border px-3 py-1 text-xs transition-colors"
      aria-live="polite"
    >
      <span className={cn("size-2 rounded-full", dot)} aria-hidden />
      {label}
    </Link>
  );
}
