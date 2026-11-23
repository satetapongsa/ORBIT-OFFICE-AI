"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Loader2,
  Plane,
  Plus,
  Settings2,
  X,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/features/auth/hooks/use-session";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import {
  HALF_DAY_LABELS,
  LEAVE_STATUS_LABELS,
  cancelLeave,
  createLeaveRequest,
  decideLeave,
  fmtDays,
  getLeaveCalendar,
  getMyLeave,
  leaveQueryKeys,
  listLeaveApprovals,
  listLeaveTypes,
  updateLeaveType,
  workingDays,
  type HalfDay,
  type LeaveBalance,
  type LeaveRequest,
  type LeaveStatus,
} from "@/services/leave";

type Tab = "mine" | "approvals" | "team" | "settings";

const COLORS: Record<string, string> = {
  emerald: "bg-emerald-500",
  rose: "bg-rose-500",
  amber: "bg-amber-500",
  violet: "bg-violet-500",
  slate: "bg-slate-500",
  blue: "bg-blue-500",
};

const STATUS_STYLE: Record<LeaveStatus, string> = {
  PENDING: "bg-amber-100 text-amber-800 border-amber-200",
  APPROVED: "bg-emerald-100 text-emerald-800 border-emerald-200",
  REJECTED: "bg-rose-100 text-rose-800 border-rose-200",
  CANCELLED: "bg-muted text-muted-foreground",
};

function errorText(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  const detail = error.details.map((d) => d.message).join(" ");
  return detail ? detail : error.message;
}

const dateFmt = new Intl.DateTimeFormat("th-TH", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const shortFmt = new Intl.DateTimeFormat("th-TH", {
  weekday: "short",
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});
const showDate = (iso: string) => dateFmt.format(new Date(`${iso}T00:00:00Z`));

function period(r: Pick<LeaveRequest, "start_date" | "end_date" | "half_day">): string {
  const text =
    r.start_date === r.end_date
      ? showDate(r.start_date)
      : `${showDate(r.start_date)} – ${showDate(r.end_date)}`;
  return r.half_day === "NONE" ? text : `${text} (${HALF_DAY_LABELS[r.half_day]})`;
}

function isoToday(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function TypeDot({ color }: { color: string }) {
  return <span className={cn("size-2.5 shrink-0 rounded-full", COLORS[color] ?? "bg-blue-500")} />;
}

function StatusBadge({ status }: { status: LeaveStatus }) {
  return (
    <Badge variant="outline" className={STATUS_STYLE[status]}>
      {LEAVE_STATUS_LABELS[status]}
    </Badge>
  );
}

function BalanceCard({ b }: { b: LeaveBalance }) {
  const quota = b.quota;
  const usedPct = quota ? Math.min(100, ((b.used + b.pending) / quota) * 100) : 0;
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center gap-2">
          <TypeDot color={b.leave_type.color} />
          <span className="text-sm font-medium">{b.leave_type.name}</span>
        </div>
        <p className="text-2xl font-semibold tabular-nums">
          {b.remaining === null ? "ไม่จำกัด" : fmtDays(b.remaining)}
          {b.remaining !== null ? (
            <span className="text-muted-foreground text-sm font-normal">
              {" "}
              / {fmtDays(quota ?? 0)} วัน
            </span>
          ) : null}
        </p>
        {quota ? (
          <div className="bg-muted h-1.5 overflow-hidden rounded-full" aria-hidden>
            <div
              className={cn("h-full rounded-full", COLORS[b.leave_type.color] ?? "bg-blue-500")}
              style={{ width: `${usedPct}%` }}
            />
          </div>
        ) : null}
        <p className="text-muted-foreground text-xs">
          ใช้ไป {fmtDays(b.used)} วัน{b.pending ? ` · รออนุมัติ ${fmtDays(b.pending)} วัน` : ""}
        </p>
      </CardContent>
    </Card>
  );
}

function RequestDialog({
  open,
  onOpenChange,
  balances,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  balances: LeaveBalance[];
}) {
  const client = useQueryClient();
  const [typeId, setTypeId] = useState(balances[0]?.leave_type.id ?? "");
  const [start, setStart] = useState(isoToday());
  const [end, setEnd] = useState(isoToday());
  const [half, setHalf] = useState<HalfDay>("NONE");
  const [reason, setReason] = useState("");
  const single = start === end;
  const days = workingDays(start, end, single ? half : "NONE");
  const balance = balances.find((b) => b.leave_type.id === typeId);
  const over =
    balance?.remaining !== null && balance !== undefined && days > (balance.remaining ?? 0);

  const submit = useMutation({
    mutationFn: () =>
      createLeaveRequest({
        leave_type_id: typeId,
        start_date: start,
        end_date: end,
        half_day: single ? half : "NONE",
        reason: reason.trim(),
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: leaveQueryKeys.all });
      toast.success("ส่งใบลาแล้ว รอการอนุมัติ");
      onOpenChange(false);
    },
    onError: (error) => toast.error(errorText(error, "ยื่นใบลาไม่สำเร็จ")),
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!typeId || days <= 0) return;
    submit.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>ยื่นใบลา</DialogTitle>
          <DialogDescription>
            นับเฉพาะวันทำงาน จันทร์–ศุกร์ ใบลาจะส่งถึงหัวหน้าแผนกเพื่ออนุมัติ
          </DialogDescription>
        </DialogHeader>
        <form id="leave-form" className="space-y-4" onSubmit={onSubmit}>
          <div className="space-y-1.5">
            <Label htmlFor="l-type">ประเภทการลา</Label>
            <select
              id="l-type"
              value={typeId}
              onChange={(e) => setTypeId(e.target.value)}
              className="border-input bg-background h-9 w-full rounded-lg border px-2.5 text-sm"
            >
              {balances.map((b) => (
                <option key={b.leave_type.id} value={b.leave_type.id}>
                  {b.leave_type.name}
                  {b.remaining === null ? "" : ` (คงเหลือ ${fmtDays(b.remaining)} วัน)`}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="l-start">วันเริ่มลา</Label>
              <Input
                id="l-start"
                type="date"
                value={start}
                onChange={(e) => {
                  setStart(e.target.value);
                  if (e.target.value > end) setEnd(e.target.value);
                }}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="l-end">ถึงวันที่</Label>
              <Input
                id="l-end"
                type="date"
                value={end}
                min={start}
                onChange={(e) => setEnd(e.target.value)}
                required
              />
            </div>
          </div>
          {single ? (
            <div className="space-y-1.5">
              <span className="text-sm font-medium">ช่วงเวลา</span>
              <div className="flex gap-2" role="radiogroup" aria-label="ช่วงเวลา">
                {(["NONE", "MORNING", "AFTERNOON"] as HalfDay[]).map((h) => (
                  <Button
                    key={h}
                    type="button"
                    size="sm"
                    variant={half === h ? "default" : "outline"}
                    role="radio"
                    aria-checked={half === h}
                    onClick={() => setHalf(h)}
                  >
                    {HALF_DAY_LABELS[h]}
                  </Button>
                ))}
              </div>
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="l-reason">เหตุผล (ไม่บังคับ)</Label>
            <Textarea
              id="l-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={2000}
              placeholder="เช่น ไปพบแพทย์ ธุระครอบครัว"
            />
          </div>
          <div
            className={cn(
              "rounded-lg border px-3 py-2 text-sm",
              days <= 0 || over
                ? "border-destructive/40 bg-destructive/5 text-destructive"
                : "bg-muted/50",
            )}
            data-testid="leave-days"
          >
            {days <= 0
              ? "ช่วงที่เลือกไม่มีวันทำงาน"
              : over
                ? `ลา ${fmtDays(days)} วัน เกินวันลาคงเหลือ (${fmtDays(balance?.remaining ?? 0)} วัน)`
                : `รวม ${fmtDays(days)} วันทำงาน`}
          </div>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            ยกเลิก
          </Button>
          <Button
            type="submit"
            form="leave-form"
            disabled={submit.isPending || days <= 0 || over || !typeId}
          >
            {submit.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ส่งใบลา
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RequestRow({ r, showPerson }: { r: LeaveRequest; showPerson: boolean }) {
  const client = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const refresh = () => client.invalidateQueries({ queryKey: leaveQueryKeys.all });
  const decide = useMutation({
    mutationFn: ({ approve, note }: { approve: boolean; note: string }) =>
      decideLeave(r.id, approve, note),
    onSuccess: async (_d, v) => {
      await refresh();
      toast.success(v.approve ? "อนุมัติแล้ว" : "ไม่อนุมัติแล้ว");
      setRejecting(false);
    },
    onError: (error) => toast.error(errorText(error, "บันทึกผลไม่สำเร็จ")),
  });
  const cancel = useMutation({
    mutationFn: () => cancelLeave(r.id),
    onSuccess: async () => {
      await refresh();
      toast.success("ยกเลิกใบลาแล้ว");
    },
    onError: (error) => toast.error(errorText(error, "ยกเลิกไม่สำเร็จ")),
  });
  return (
    <li className="bg-card space-y-3 rounded-xl border p-4">
      <div className="flex flex-wrap items-start gap-3">
        <TypeDot color={r.leave_type.color} />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
            {showPerson ? <span>{r.person.display_name} ·</span> : null}
            {r.leave_type.name} {fmtDays(r.days)} วัน
            <StatusBadge status={r.status} />
          </p>
          <p className="text-muted-foreground text-sm">{period(r)}</p>
          {showPerson && r.person.department_name ? (
            <p className="text-muted-foreground text-xs">{r.person.department_name}</p>
          ) : null}
          {r.reason ? <p className="text-sm whitespace-pre-wrap">“{r.reason}”</p> : null}
          {r.decided_by_name ? (
            <p className="text-muted-foreground text-xs">
              {LEAVE_STATUS_LABELS[r.status]}โดย {r.decided_by_name}
              {r.decided_at ? ` · ${formatRelative(r.decided_at)}` : ""}
              {r.decision_note ? ` — ${r.decision_note}` : ""}
            </p>
          ) : (
            <p className="text-muted-foreground text-xs">
              ยื่นเมื่อ {formatRelative(r.created_at)}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {r.can_decide && !rejecting ? (
            <>
              <Button
                size="sm"
                onClick={() => decide.mutate({ approve: true, note: "" })}
                disabled={decide.isPending}
              >
                <Check aria-hidden />
                อนุมัติ
              </Button>
              <Button size="sm" variant="outline" onClick={() => setRejecting(true)}>
                <X aria-hidden />
                ไม่อนุมัติ
              </Button>
            </>
          ) : null}
          {r.can_cancel && !r.can_decide ? (
            <Button
              size="sm"
              variant="outline"
              disabled={cancel.isPending}
              onClick={() => {
                if (window.confirm("ยกเลิกใบลานี้ใช่ไหม?")) cancel.mutate();
              }}
            >
              ยกเลิกใบลา
            </Button>
          ) : null}
        </div>
      </div>
      {rejecting ? (
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            autoFocus
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="เหตุผลที่ไม่อนุมัติ (จำเป็น)"
            aria-label="เหตุผลที่ไม่อนุมัติ"
          />
          <Button
            size="sm"
            variant="destructive"
            disabled={!note.trim() || decide.isPending}
            onClick={() => decide.mutate({ approve: false, note: note.trim() })}
          >
            ยืนยันไม่อนุมัติ
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setRejecting(false)}>
            ยกเลิก
          </Button>
        </div>
      ) : null}
    </li>
  );
}

function MineTab() {
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [open, setOpen] = useState(false);
  const mine = useQuery({
    queryKey: leaveQueryKeys.me(year),
    queryFn: ({ signal }) => getMyLeave(year, signal),
  });
  if (mine.isPending) return <Skeleton className="h-48 w-full rounded-xl" />;
  if (mine.isError)
    return (
      <ErrorState
        message={errorText(mine.error, "โหลดข้อมูลการลาไม่สำเร็จ")}
        onRetry={() => void mine.refetch()}
      />
    );
  const data = mine.data;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" aria-label="ปีก่อน" onClick={() => setYear(year - 1)}>
          <ChevronLeft aria-hidden />
        </Button>
        <span className="min-w-24 text-center font-medium">ปี {year + 543}</span>
        <Button
          variant="outline"
          size="icon"
          aria-label="ปีถัดไป"
          onClick={() => setYear(year + 1)}
          disabled={year >= thisYear + 1}
        >
          <ChevronRight aria-hidden />
        </Button>
        <Button className="ml-auto" onClick={() => setOpen(true)}>
          <Plus aria-hidden />
          ยื่นใบลา
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {data.balances.map((b) => (
          <BalanceCard key={b.leave_type.id} b={b} />
        ))}
      </div>
      <section className="space-y-3">
        <h2 className="font-medium">ใบลาของฉัน</h2>
        {data.requests.length === 0 ? (
          <EmptyState
            icon={Plane}
            title="ยังไม่มีใบลาในปีนี้"
            description="กด “ยื่นใบลา” เพื่อเริ่ม"
          />
        ) : (
          <ul className="space-y-3">
            {data.requests.map((r) => (
              <RequestRow key={r.id} r={r} showPerson={false} />
            ))}
          </ul>
        )}
      </section>
      {open ? <RequestDialog open={open} onOpenChange={setOpen} balances={data.balances} /> : null}
    </div>
  );
}

function ApprovalsTab() {
  const list = useQuery({
    queryKey: leaveQueryKeys.approvals,
    queryFn: ({ signal }) => listLeaveApprovals(signal),
  });
  if (list.isPending) return <Skeleton className="h-32 w-full rounded-xl" />;
  if (list.isError)
    return (
      <ErrorState
        message={errorText(list.error, "โหลดไม่สำเร็จ")}
        onRetry={() => void list.refetch()}
      />
    );
  if (list.data.length === 0)
    return (
      <EmptyState
        icon={Inbox}
        title="ไม่มีใบลารออนุมัติ"
        description="ใบลาใหม่ของทีมจะแสดงที่นี่"
      />
    );
  return (
    <ul className="space-y-3">
      {list.data.map((r) => (
        <RequestRow key={r.id} r={r} showPerson />
      ))}
    </ul>
  );
}

function TeamTab() {
  const [offset, setOffset] = useState(0);
  const base = new Date();
  const first = new Date(Date.UTC(base.getFullYear(), base.getMonth() + offset, 1));
  const last = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0));
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const start = iso(first);
  const end = iso(last);
  const cal = useQuery({
    queryKey: leaveQueryKeys.calendar(start, end),
    queryFn: ({ signal }) => getLeaveCalendar(start, end, signal),
  });
  // Group by each working day of the month that has someone away.
  const days: { date: string; people: LeaveRequest[] }[] = [];
  for (let t = first.getTime(); t <= last.getTime(); t += 86_400_000) {
    const date = iso(new Date(t));
    const wd = new Date(t).getUTCDay();
    if (wd === 0 || wd === 6) continue;
    const people = (cal.data ?? []).filter((r) => r.start_date <= date && r.end_date >= date);
    if (people.length) days.push({ date, people });
  }
  const monthName = new Intl.DateTimeFormat("th-TH", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(first);
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          aria-label="เดือนก่อน"
          onClick={() => setOffset(offset - 1)}
        >
          <ChevronLeft aria-hidden />
        </Button>
        <span className="min-w-40 text-center font-medium">{monthName}</span>
        <Button
          variant="outline"
          size="icon"
          aria-label="เดือนถัดไป"
          onClick={() => setOffset(offset + 1)}
        >
          <ChevronRight aria-hidden />
        </Button>
        {offset !== 0 ? (
          <Button variant="ghost" size="sm" onClick={() => setOffset(0)}>
            เดือนนี้
          </Button>
        ) : null}
      </div>
      {cal.isPending ? (
        <Skeleton className="h-32 w-full rounded-xl" />
      ) : days.length === 0 ? (
        <EmptyState
          icon={CalendarDays}
          title="เดือนนี้ไม่มีใครลา"
          description="แสดงเฉพาะใบลาที่อนุมัติแล้วของคนในแผนกเดียวกัน"
        />
      ) : (
        <ul className="divide-y rounded-xl border">
          {days.map((d) => (
            <li key={d.date} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-start">
              <span className="w-36 shrink-0 text-sm font-medium">
                {shortFmt.format(new Date(`${d.date}T00:00:00Z`))}
              </span>
              <span className="flex flex-wrap gap-2">
                {d.people.map((r) => (
                  <span
                    key={r.id}
                    className="bg-muted inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs"
                  >
                    <TypeDot color={r.leave_type.color} />
                    {r.person.display_name} · {r.leave_type.name}
                    {r.half_day !== "NONE" ? ` (${HALF_DAY_LABELS[r.half_day]})` : ""}
                  </span>
                ))}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SettingsTab() {
  const client = useQueryClient();
  const types = useQuery({
    queryKey: leaveQueryKeys.types(true),
    queryFn: ({ signal }) => listLeaveTypes(true, signal),
  });
  const save = useMutation({
    mutationFn: ({ id, input }: { id: string; input: Parameters<typeof updateLeaveType>[1] }) =>
      updateLeaveType(id, input),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: leaveQueryKeys.all });
      toast.success("บันทึกแล้ว");
    },
    onError: (error) => toast.error(errorText(error, "บันทึกไม่สำเร็จ")),
  });
  if (types.isPending) return <Skeleton className="h-40 w-full rounded-xl" />;
  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">
        จำนวนวันลาต่อปีของแต่ละประเภท (ค่าเริ่มต้นตามกฎหมายแรงงาน) เว้นว่าง = ไม่จำกัด
      </p>
      <ul className="divide-y rounded-xl border">
        {(types.data ?? []).map((t) => (
          <li key={t.id} className="flex flex-wrap items-center gap-3 p-3">
            <TypeDot color={t.color} />
            <span className="min-w-32 flex-1 text-sm font-medium">{t.name}</span>
            <Input
              type="number"
              min={0}
              max={365}
              step={0.5}
              defaultValue={t.days_per_year ?? ""}
              aria-label={`วันลาต่อปีของ${t.name}`}
              className="w-24"
              onBlur={(e) => {
                const raw = e.target.value.trim();
                const next = raw === "" ? null : Number(raw);
                if (next === t.days_per_year) return;
                save.mutate({
                  id: t.id,
                  input: next === null ? { unlimited: true } : { days_per_year: next },
                });
              }}
            />
            <span className="text-muted-foreground text-sm">วัน/ปี</span>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={t.is_active}
                onChange={(e) => save.mutate({ id: t.id, input: { is_active: e.target.checked } })}
              />
              เปิดใช้
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function LeaveView() {
  const { has } = useSession();
  const params = useSearchParams();
  const router = useRouter();
  const canApprove = has("leave:approve_department") || has("leave:manage");
  const canManage = has("leave:manage");
  const requested = params.get("tab") as Tab | null;
  const tabs: { key: Tab; label: string; icon: typeof Plane; show: boolean }[] = [
    { key: "mine", label: "การลาของฉัน", icon: Plane, show: true },
    { key: "approvals", label: "รออนุมัติ", icon: Inbox, show: canApprove },
    { key: "team", label: "ใครลาบ้าง", icon: CalendarDays, show: true },
    { key: "settings", label: "ตั้งค่าวันลา", icon: Settings2, show: canManage },
  ];
  const visible = tabs.filter((t) => t.show);
  const tab = visible.some((t) => t.key === requested) ? (requested as Tab) : "mine";
  const approvals = useQuery({
    queryKey: leaveQueryKeys.approvals,
    queryFn: ({ signal }) => listLeaveApprovals(signal),
    enabled: canApprove,
  });
  const pending = approvals.data?.length ?? 0;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">ลางาน</h1>
        <p className="text-muted-foreground text-sm">
          ยื่นใบลา ดูวันลาคงเหลือ และดูว่าใครในทีมลาวันไหน
        </p>
      </div>
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
              onClick={() => router.replace(t.key === "mine" ? "/leave" : `/leave?tab=${t.key}`)}
            >
              <Icon aria-hidden />
              {t.label}
              {t.key === "approvals" && pending ? (
                <Badge variant="secondary" className="ml-1 h-5 px-1.5">
                  {pending}
                </Badge>
              ) : null}
            </Button>
          );
        })}
      </div>
      {tab === "mine" ? <MineTab /> : null}
      {tab === "approvals" ? <ApprovalsTab /> : null}
      {tab === "team" ? <TeamTab /> : null}
      {tab === "settings" ? <SettingsTab /> : null}
    </div>
  );
}
