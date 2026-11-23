"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarCheck, ChevronLeft, ChevronRight, Download, Loader2, Users } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { CheckInCard } from "@/features/attendance/components/check-in-card";
import { useSession } from "@/features/auth/hooks/use-session";
import { formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import {
  WORK_MODE_LABELS,
  attendanceQueryKeys,
  downloadAttendanceCsv,
  fmtMinutes,
  getAttendanceReport,
  getMyAttendance,
  getTeamDay,
  type Attendance,
} from "@/services/attendance";
import { listDepartments } from "@/services/documents";

type Tab = "mine" | "team" | "report";

const pad = (n: number) => String(n).padStart(2, "0");
const thisMonth = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
};
const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + by, 1));
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}`;
}
const monthLabel = (month: string) =>
  new Intl.DateTimeFormat("th-TH", { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(`${month}-01T00:00:00Z`),
  );
const dayLabel = (iso: string) =>
  new Intl.DateTimeFormat("th-TH", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(`${iso}T00:00:00Z`));

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function MonthPicker({ month, onChange }: { month: string; onChange: (m: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <Button
        variant="outline"
        size="icon"
        aria-label="เดือนก่อน"
        onClick={() => onChange(shiftMonth(month, -1))}
      >
        <ChevronLeft aria-hidden />
      </Button>
      <span className="min-w-36 text-center font-medium">{monthLabel(month)}</span>
      <Button
        variant="outline"
        size="icon"
        aria-label="เดือนถัดไป"
        onClick={() => onChange(shiftMonth(month, 1))}
        disabled={month >= thisMonth()}
      >
        <ChevronRight aria-hidden />
      </Button>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <Card>
      <CardContent className="space-y-1 p-4">
        <p className="text-muted-foreground text-xs">{label}</p>
        <p className={cn("text-xl font-semibold tabular-nums", tone)}>{value}</p>
      </CardContent>
    </Card>
  );
}

function RecordTimes({ r }: { r: Attendance }) {
  return (
    <span className="tabular-nums">
      {formatTime(r.check_in_at)} – {r.check_out_at ? formatTime(r.check_out_at) : "ยังไม่ออก"}
    </span>
  );
}

function MineTab() {
  const [month, setMonth] = useState(thisMonth());
  const mine = useQuery({
    queryKey: attendanceQueryKeys.me(month),
    queryFn: ({ signal }) => getMyAttendance(month, signal),
  });
  return (
    <div className="space-y-6">
      <CheckInCard />
      <MonthPicker month={month} onChange={setMonth} />
      {mine.isPending ? (
        <Skeleton className="h-40 w-full rounded-xl" />
      ) : mine.isError ? (
        <ErrorState
          message={errorText(mine.error, "โหลดประวัติไม่สำเร็จ")}
          onRetry={() => void mine.refetch()}
        />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Stat label="วันที่มาทำงาน" value={`${mine.data.summary.days_present} วัน`} />
            <Stat
              label="มาสาย"
              value={`${mine.data.summary.late_days} วัน`}
              tone={mine.data.summary.late_days ? "text-amber-600" : undefined}
            />
            <Stat label="WFH" value={`${mine.data.summary.wfh_days} วัน`} />
            <Stat label="ชั่วโมงทำงานรวม" value={fmtMinutes(mine.data.summary.total_minutes)} />
            <Stat
              label="เข้างานเฉลี่ย"
              value={
                mine.data.summary.average_check_in
                  ? `${mine.data.summary.average_check_in} น.`
                  : "—"
              }
            />
          </div>
          {mine.data.records.length === 0 ? (
            <EmptyState icon={CalendarCheck} title="ยังไม่มีการลงเวลาในเดือนนี้" />
          ) : (
            <ul className="divide-y rounded-xl border">
              {mine.data.records.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 p-3 text-sm">
                  <span className="w-32 font-medium">{dayLabel(r.work_date)}</span>
                  <RecordTimes r={r} />
                  {r.late ? (
                    <Badge variant="outline" className="border-amber-300 text-amber-700">
                      สาย
                    </Badge>
                  ) : null}
                  <span className="text-muted-foreground">{WORK_MODE_LABELS[r.work_mode]}</span>
                  {r.worked_minutes !== null ? (
                    <span className="text-muted-foreground ml-auto">
                      {fmtMinutes(r.worked_minutes)}
                    </span>
                  ) : null}
                  {r.check_in_note || r.check_out_note ? (
                    <span className="text-muted-foreground w-full text-xs">
                      {[r.check_in_note, r.check_out_note].filter(Boolean).join(" · ")}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function DepartmentFilter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const departments = useQuery({
    queryKey: ["departments", "list"],
    queryFn: ({ signal }) => listDepartments(signal),
  });
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label="แผนก"
      className="border-input bg-background h-9 rounded-lg border px-2.5 text-sm"
    >
      <option value="">ทุกแผนก</option>
      {(departments.data ?? []).map((d) => (
        <option key={d.id} value={d.id}>
          {d.name}
        </option>
      ))}
    </select>
  );
}

function TeamTab({ all }: { all: boolean }) {
  const [date, setDate] = useState(todayIso());
  const [department, setDepartment] = useState("");
  const team = useQuery({
    queryKey: attendanceQueryKeys.team(date, department),
    queryFn: ({ signal }) => getTeamDay(date, department, signal),
    refetchInterval: 60_000,
  });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="date"
          value={date}
          max={todayIso()}
          onChange={(e) => setDate(e.target.value)}
          className="w-44"
          aria-label="วันที่"
        />
        {all ? <DepartmentFilter value={department} onChange={setDepartment} /> : null}
      </div>
      {team.isPending ? (
        <Skeleton className="h-40 w-full rounded-xl" />
      ) : team.isError ? (
        <ErrorState
          message={errorText(team.error, "โหลดไม่สำเร็จ")}
          onRetry={() => void team.refetch()}
        />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            <Stat label="เข้างานแล้ว" value={`${team.data.present} คน`} tone="text-emerald-600" />
            <Stat
              label="มาสาย"
              value={`${team.data.late} คน`}
              tone={team.data.late ? "text-amber-600" : undefined}
            />
            <Stat label="ลา" value={`${team.data.on_leave} คน`} />
            <Stat
              label="ยังไม่ลงเวลา"
              value={`${team.data.missing} คน`}
              tone={team.data.missing ? "text-rose-600" : undefined}
            />
          </div>
          <ul className="divide-y rounded-xl border">
            {team.data.rows.map((row) => (
              <li
                key={row.person.id}
                className="flex flex-wrap items-center gap-x-4 gap-y-1 p-3 text-sm"
              >
                <span className="min-w-44 flex-1">
                  <span className="font-medium">{row.person.display_name}</span>
                  <span className="text-muted-foreground block text-xs">
                    {[row.person.job_title, row.person.department_name]
                      .filter(Boolean)
                      .join(" · ") || "—"}
                  </span>
                </span>
                {row.record ? (
                  <>
                    <RecordTimes r={row.record} />
                    <Badge
                      variant="outline"
                      className={
                        row.record.late
                          ? "border-amber-300 text-amber-700"
                          : "border-emerald-300 text-emerald-700"
                      }
                    >
                      {row.record.late ? "สาย" : "ตรงเวลา"}
                    </Badge>
                    <span className="text-muted-foreground">
                      {WORK_MODE_LABELS[row.record.work_mode]}
                    </span>
                  </>
                ) : row.on_leave ? (
                  <Badge variant="secondary">{row.on_leave}</Badge>
                ) : (
                  <Badge variant="outline" className="border-rose-300 text-rose-700">
                    ยังไม่ลงเวลา
                  </Badge>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function ReportTab({ all }: { all: boolean }) {
  const [month, setMonth] = useState(thisMonth());
  const [department, setDepartment] = useState("");
  const report = useQuery({
    queryKey: attendanceQueryKeys.report(month, department),
    queryFn: ({ signal }) => getAttendanceReport(month, department, signal),
  });
  const download = useMutation({
    mutationFn: () => downloadAttendanceCsv(month, department),
    onError: (error) => toast.error(errorText(error, "ดาวน์โหลดไม่สำเร็จ")),
  });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <MonthPicker month={month} onChange={setMonth} />
        {all ? <DepartmentFilter value={department} onChange={setDepartment} /> : null}
        <Button
          variant="outline"
          className="ml-auto"
          onClick={() => download.mutate()}
          disabled={download.isPending}
        >
          {download.isPending ? (
            <Loader2 className="animate-spin" aria-hidden />
          ) : (
            <Download aria-hidden />
          )}
          ดาวน์โหลด CSV (Excel)
        </Button>
      </div>
      {report.isPending ? (
        <Skeleton className="h-40 w-full rounded-xl" />
      ) : report.isError ? (
        <ErrorState
          message={errorText(report.error, "โหลดไม่สำเร็จ")}
          onRetry={() => void report.refetch()}
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full text-sm">
            <caption className="text-muted-foreground p-3 text-left text-xs">
              วันทำงานในเดือนนี้ {report.data.working_days} วัน (จันทร์–ศุกร์)
            </caption>
            <thead className="bg-muted/50 text-left">
              <tr>
                <th className="p-3 font-medium">พนักงาน</th>
                <th className="p-3 text-right font-medium">มาทำงาน</th>
                <th className="p-3 text-right font-medium">สาย</th>
                <th className="p-3 text-right font-medium">WFH</th>
                <th className="p-3 text-right font-medium">ลา</th>
                <th className="p-3 text-right font-medium">ชั่วโมงรวม</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {report.data.rows.map((r) => (
                <tr key={r.person.id}>
                  <td className="p-3">
                    {r.person.display_name}
                    <span className="text-muted-foreground block text-xs">
                      {r.person.department_name ?? "—"}
                    </span>
                  </td>
                  <td className="p-3 text-right tabular-nums">{r.days_present}</td>
                  <td
                    className={cn("p-3 text-right tabular-nums", r.late_days && "text-amber-600")}
                  >
                    {r.late_days}
                  </td>
                  <td className="p-3 text-right tabular-nums">{r.wfh_days}</td>
                  <td className="p-3 text-right tabular-nums">{r.leave_days}</td>
                  <td className="p-3 text-right tabular-nums">
                    {(r.total_minutes / 60).toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function AttendanceView() {
  const { has } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const all = has("attendance:read_all");
  const canSeeTeam = all || has("attendance:read_department");
  const tabs: { key: Tab; label: string; icon: typeof Users; show: boolean }[] = [
    { key: "mine", label: "ของฉัน", icon: CalendarCheck, show: true },
    { key: "team", label: "ทีมวันนี้", icon: Users, show: canSeeTeam },
    { key: "report", label: "สรุปรายเดือน", icon: Download, show: canSeeTeam },
  ];
  const visible = tabs.filter((t) => t.show);
  const requested = params.get("tab") as Tab | null;
  const tab = visible.some((t) => t.key === requested) ? (requested as Tab) : "mine";
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">ลงเวลาทำงาน</h1>
        <p className="text-muted-foreground text-sm">
          เช็กอิน–เช็กเอาต์ด้วยเวลาของเซิร์ฟเวอร์ และดูสรุปการเข้างาน
        </p>
      </div>
      {visible.length > 1 ? (
        <div className="flex flex-wrap gap-2 border-b pb-3" role="tablist">
          {visible.map((t) => {
            const Icon = t.icon;
            return (
              <Button
                key={t.key}
                role="tab"
                aria-selected={tab === t.key}
                size="sm"
                variant={tab === t.key ? "default" : "ghost"}
                onClick={() =>
                  router.replace(t.key === "mine" ? "/attendance" : `/attendance?tab=${t.key}`)
                }
              >
                <Icon aria-hidden />
                {t.label}
              </Button>
            );
          })}
        </div>
      ) : null}
      {tab === "mine" ? <MineTab /> : null}
      {tab === "team" ? <TeamTab all={all} /> : null}
      {tab === "report" ? <ReportTab all={all} /> : null}
    </div>
  );
}
