"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Loader2, LogIn, LogOut, Plane } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/features/auth/hooks/use-session";
import { formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import {
  WORK_MODE_LABELS,
  attendanceQueryKeys,
  checkIn,
  checkOut,
  fmtMinutes,
  getAttendanceToday,
  type WorkMode,
} from "@/services/attendance";

/** Live clock that follows the server time (offset measured when the response arrived). */
function useServerClock(
  serverTime: string | undefined,
  receivedAt: number | undefined,
): Date | null {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  if (!serverTime || receivedAt === undefined) return null;
  const offset = new Date(serverTime).getTime() - receivedAt;
  return new Date(now.getTime() + offset);
}

const clockFmt = new Intl.DateTimeFormat("th-TH", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  timeZone: "Asia/Bangkok",
});

export function CheckInCard({ compact = false }: { compact?: boolean }) {
  const { has } = useSession();
  if (!has("attendance:checkin")) return null;
  return <CheckInCardBody compact={compact} />;
}

function CheckInCardBody({ compact }: { compact: boolean }) {
  const client = useQueryClient();
  const today = useQuery({
    queryKey: attendanceQueryKeys.today,
    queryFn: async ({ signal }) => ({
      ...(await getAttendanceToday(signal)),
      receivedAt: Date.now(),
    }),
  });
  const clock = useServerClock(today.data?.server_time, today.data?.receivedAt);
  const [mode, setMode] = useState<WorkMode>("OFFICE");
  const [note, setNote] = useState("");

  const onDone = async (message: string) => {
    setNote("");
    await client.invalidateQueries({ queryKey: attendanceQueryKeys.all });
    toast.success(message);
  };
  const onError = (error: unknown) =>
    toast.error(error instanceof ApiError ? error.message : "บันทึกเวลาไม่สำเร็จ");
  const inMutation = useMutation({
    mutationFn: () => checkIn(mode, note.trim()),
    onSuccess: (data) =>
      onDone(data.record?.late ? "ลงเวลาเข้างานแล้ว (มาสาย)" : "ลงเวลาเข้างานแล้ว"),
    onError,
  });
  const outMutation = useMutation({
    mutationFn: () => checkOut(note.trim()),
    onSuccess: () => onDone("ลงเวลาออกงานแล้ว"),
    onError,
  });

  if (today.isPending) return <Skeleton className="h-36 w-full rounded-xl" />;
  if (today.isError) return null;
  const { record, hours, on_leave: onLeave } = today.data;
  const busy = inMutation.isPending || outMutation.isPending;
  const done = Boolean(record?.check_out_at);

  return (
    <Card>
      <CardContent
        className={cn("flex flex-col gap-4 p-5", !compact && "lg:flex-row lg:items-center")}
      >
        <div className="flex min-w-0 flex-1 items-center gap-4">
          <span className="bg-primary/10 text-primary flex size-12 shrink-0 items-center justify-center rounded-full">
            <Clock className="size-6" aria-hidden />
          </span>
          <div className="min-w-0 space-y-1">
            <p
              className="text-2xl font-semibold tabular-nums"
              aria-live="off"
              data-testid="server-clock"
            >
              {clock ? clockFmt.format(clock) : "--:--:--"}
            </p>
            <p className="text-muted-foreground text-xs">
              เวลาทำงาน {hours.start}–{hours.end} น. · สายหลัง {hours.late_after} น.
            </p>
            <div className="flex flex-wrap items-center gap-1.5 text-sm">
              {record ? (
                <>
                  <Badge
                    variant="outline"
                    className={
                      record.late
                        ? "border-amber-300 text-amber-700"
                        : "border-emerald-300 text-emerald-700"
                    }
                  >
                    {record.late ? "มาสาย" : "ตรงเวลา"}
                  </Badge>
                  <span>เข้า {formatTime(record.check_in_at)}</span>
                  {record.check_out_at ? (
                    <span>· ออก {formatTime(record.check_out_at)}</span>
                  ) : null}
                  {record.worked_minutes !== null ? (
                    <span className="text-muted-foreground">
                      · รวม {fmtMinutes(record.worked_minutes)}
                    </span>
                  ) : null}
                  <span className="text-muted-foreground">
                    · {WORK_MODE_LABELS[record.work_mode]}
                  </span>
                </>
              ) : (
                <span className="text-muted-foreground">วันนี้ยังไม่ได้ลงเวลาเข้างาน</span>
              )}
              {onLeave ? (
                <Badge variant="secondary" className="gap-1">
                  <Plane className="size-3" aria-hidden />
                  {onLeave}
                </Badge>
              ) : null}
            </div>
          </div>
        </div>

        {done ? (
          <p className="text-muted-foreground text-sm">ลงเวลาครบแล้ววันนี้ 👍</p>
        ) : (
          <div
            className={cn(
              "flex flex-col gap-2 sm:flex-row sm:items-center",
              !compact && "lg:w-[30rem]",
            )}
          >
            {!record ? (
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as WorkMode)}
                aria-label="รูปแบบการทำงาน"
                className="border-input bg-background h-9 rounded-lg border px-2.5 text-sm"
              >
                {(Object.keys(WORK_MODE_LABELS) as WorkMode[]).map((m) => (
                  <option key={m} value={m}>
                    {WORK_MODE_LABELS[m]}
                  </option>
                ))}
              </select>
            ) : null}
            <Input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={300}
              placeholder="หมายเหตุ (ไม่บังคับ)"
              aria-label="หมายเหตุการลงเวลา"
              className="sm:flex-1"
            />
            {!record ? (
              <Button onClick={() => inMutation.mutate()} disabled={busy}>
                {inMutation.isPending ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : (
                  <LogIn aria-hidden />
                )}
                ลงเวลาเข้างาน
              </Button>
            ) : (
              <Button variant="outline" onClick={() => outMutation.mutate()} disabled={busy}>
                {outMutation.isPending ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : (
                  <LogOut aria-hidden />
                )}
                ลงเวลาออกงาน
              </Button>
            )}
          </div>
        )}
        {compact ? (
          <Link href="/attendance" className="text-primary text-xs hover:underline">
            ดูประวัติการลงเวลา
          </Link>
        ) : null}
      </CardContent>
    </Card>
  );
}
