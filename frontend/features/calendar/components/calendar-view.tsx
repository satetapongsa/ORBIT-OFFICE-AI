"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock,
  Link2,
  Loader2,
  MapPin,
  Pencil,
  Plus,
  Search,
  X,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/common/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { dayKey, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import {
  RESPONSE_LABELS,
  calendarQueryKeys,
  cancelMeeting,
  checkAvailability,
  createMeeting,
  getCalendar,
  getMeeting,
  respondMeeting,
  updateMeeting,
  type Conflict,
  type LeaveEvent,
  type Meeting,
  type MeetingInput,
  type MeetingResponse,
} from "@/services/calendar";
import { searchDirectory } from "@/services/documents";

const WEEKDAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."];
const LEAVE_COLORS: Record<string, string> = {
  emerald: "bg-emerald-100 text-emerald-800",
  rose: "bg-rose-100 text-rose-800",
  amber: "bg-amber-100 text-amber-800",
  violet: "bg-violet-100 text-violet-800",
  slate: "bg-slate-200 text-slate-700",
  blue: "bg-blue-100 text-blue-800",
};
const RESPONSE_STYLE: Record<MeetingResponse, string> = {
  PENDING: "border-dashed border-primary/60 bg-background text-primary",
  ACCEPTED: "bg-primary text-primary-foreground",
  TENTATIVE: "bg-primary/20 text-primary",
  DECLINED: "bg-muted text-muted-foreground line-through",
};

const pad = (n: number) => String(n).padStart(2, "0");
const isoDate = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const longDay = (iso: string) =>
  new Intl.DateTimeFormat("th-TH", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(`${iso}T00:00:00`));

function errorText(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  const detail = error.details.map((d) => d.message).join(" ");
  return detail || error.message;
}

/** Monday-first weeks covering the month. */
function monthGrid(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const start = new Date(first);
  start.setDate(1 - ((first.getDay() + 6) % 7));
  return Array.from(
    { length: 42 },
    (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i),
  );
}

function meetingDays(m: Meeting): string[] {
  const days: string[] = [];
  const end = dayKey(m.end_at);
  const cursor = new Date(m.start_at);
  for (let i = 0; i < 3; i++) {
    const key = dayKey(cursor);
    days.push(key);
    if (key >= end) break;
    cursor.setDate(cursor.getDate() + 1);
  }
  return days;
}

function MeetingChip({ m, onOpen }: { m: Meeting; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onOpen();
      }}
      className={cn(
        "block w-full truncate rounded border px-1.5 py-0.5 text-left text-[11px] leading-tight",
        m.cancelled
          ? "bg-muted text-muted-foreground line-through"
          : RESPONSE_STYLE[m.my_response ?? "PENDING"],
      )}
      title={`${formatTime(m.start_at)} ${m.title}`}
    >
      {formatTime(m.start_at)} {m.title}
    </button>
  );
}

function LeaveChip({ l }: { l: LeaveEvent }) {
  return (
    <span
      className={cn(
        "block truncate rounded px-1.5 py-0.5 text-[11px] leading-tight",
        LEAVE_COLORS[l.color] ?? LEAVE_COLORS.blue,
      )}
      title={`${l.person_name} · ${l.leave_type}`}
    >
      {l.person_name.split(" ")[0]} · {l.leave_type}
    </span>
  );
}

// --- Meeting form -------------------------------------------------------------------------

interface Picked {
  id: string;
  display_name: string;
}

function AttendeePicker({
  picked,
  onChange,
}: {
  picked: Picked[];
  onChange: (p: Picked[]) => void;
}) {
  const [q, setQ] = useState("");
  const results = useQuery({
    queryKey: ["directory", "search", q],
    queryFn: ({ signal }) => searchDirectory(q, signal),
    enabled: q.trim().length > 0,
  });
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {picked.map((p) => (
          <span
            key={p.id}
            className="bg-muted inline-flex items-center gap-1 rounded-full py-0.5 pr-1 pl-2.5 text-xs"
          >
            {p.display_name}
            <button
              type="button"
              aria-label={`นำ ${p.display_name} ออก`}
              onClick={() => onChange(picked.filter((x) => x.id !== p.id))}
              className="hover:bg-background rounded-full p-0.5"
            >
              <X className="size-3" aria-hidden />
            </button>
          </span>
        ))}
      </div>
      <div className="relative">
        <Search
          className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
          aria-hidden
        />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="พิมพ์ชื่อเพื่อเพิ่มผู้เข้าร่วม"
          aria-label="ค้นหาผู้เข้าร่วม"
          className="pl-8"
        />
        {q.trim() && results.data ? (
          <ul className="bg-popover absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border shadow-lg">
            {results.data.filter((u) => !picked.some((p) => p.id === u.id)).length === 0 ? (
              <li className="text-muted-foreground p-2 text-sm">ไม่พบรายชื่อ</li>
            ) : (
              results.data
                .filter((u) => !picked.some((p) => p.id === u.id))
                .map((u) => (
                  <li key={u.id}>
                    <button
                      type="button"
                      className="hover:bg-accent w-full px-3 py-2 text-left text-sm"
                      onClick={() => {
                        onChange([...picked, { id: u.id, display_name: u.display_name }]);
                        setQ("");
                      }}
                    >
                      {u.display_name}
                      <span className="text-muted-foreground block text-xs">
                        {[u.job_title, u.department?.name].filter(Boolean).join(" · ") || "—"}
                      </span>
                    </button>
                  </li>
                ))
            )}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

function MeetingForm({
  initial,
  day,
  myId,
  onClose,
}: {
  initial: Meeting | null;
  day: string;
  myId: string | undefined;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const start0 = initial ? new Date(initial.start_at) : null;
  const end0 = initial ? new Date(initial.end_at) : null;
  const [title, setTitle] = useState(initial?.title ?? "");
  const [date, setDate] = useState(start0 ? isoDate(start0) : day);
  const [startTime, setStartTime] = useState(
    start0 ? `${pad(start0.getHours())}:${pad(start0.getMinutes())}` : "10:00",
  );
  const [endTime, setEndTime] = useState(
    end0 ? `${pad(end0.getHours())}:${pad(end0.getMinutes())}` : "11:00",
  );
  const [location, setLocation] = useState(initial?.location ?? "");
  const [url, setUrl] = useState(initial?.online_url ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [reminder, setReminder] = useState(initial?.reminder_minutes ?? 15);
  const [people, setPeople] = useState<Picked[]>(
    initial?.attendees
      .filter((a) => a.id !== myId)
      .map((a) => ({ id: a.id, display_name: a.display_name })) ?? [],
  );
  const startIso = new Date(`${date}T${startTime}`).toISOString();
  const endIso = new Date(`${date}T${endTime}`).toISOString();
  const validTime = Boolean(date && startTime && endTime) && endTime > startTime;
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const peopleKey = people.map((p) => p.id).join(",");

  useEffect(() => {
    if (!validTime || !people.length) return;
    const timer = setTimeout(() => {
      checkAvailability({
        user_ids: people.map((p) => p.id),
        start_at: startIso,
        end_at: endIso,
        exclude_meeting_id: initial?.id,
      })
        .then((r) => setConflicts(r.conflicts))
        .catch(() => setConflicts([]));
    }, 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- recheck when time or people change
  }, [startIso, endIso, peopleKey, validTime]);
  const shown = validTime && people.length ? conflicts : [];

  const save = useMutation({
    mutationFn: () => {
      const input: MeetingInput = {
        title: title.trim(),
        description: description.trim(),
        location: location.trim() || null,
        online_url: url.trim() || null,
        start_at: startIso,
        end_at: endIso,
        attendee_ids: people.map((p) => p.id),
        reminder_minutes: reminder,
      };
      return initial ? updateMeeting(initial.id, input) : createMeeting(input);
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: calendarQueryKeys.all });
      toast.success(
        initial ? "บันทึกการเปลี่ยนแปลงและแจ้งผู้เข้าร่วมแล้ว" : "นัดประชุมและส่งคำเชิญแล้ว",
      );
      onClose();
    },
    onError: (error) => toast.error(errorText(error, "บันทึกไม่สำเร็จ")),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim() || !validTime) return;
    save.mutate();
  }

  return (
    <Dialog open onOpenChange={(open) => (!open ? onClose() : undefined)}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{initial ? "แก้ไขการประชุม" : "นัดประชุม"}</DialogTitle>
          <DialogDescription>ผู้เข้าร่วมจะได้รับแจ้งเตือนและตอบรับได้จากปฏิทิน</DialogDescription>
        </DialogHeader>
        <form id="meeting-form" className="space-y-4" onSubmit={submit}>
          <div className="space-y-1.5">
            <Label htmlFor="m-title">หัวข้อ</Label>
            <Input
              id="m-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              required
              autoFocus
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="m-date">วันที่</Label>
              <Input
                id="m-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-start">เริ่ม</Label>
              <Input
                id="m-start"
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-end">สิ้นสุด</Label>
              <Input
                id="m-end"
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                required
              />
            </div>
          </div>
          {!validTime ? (
            <p className="text-destructive text-xs">เวลาสิ้นสุดต้องหลังเวลาเริ่ม</p>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="m-location">สถานที่</Label>
              <Input
                id="m-location"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                maxLength={200}
                placeholder="เช่น ห้องประชุม 3"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-url">ลิงก์ประชุมออนไลน์</Label>
              <Input
                id="m-url"
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <span className="text-sm font-medium">ผู้เข้าร่วม</span>
            <AttendeePicker picked={people} onChange={setPeople} />
          </div>
          {shown.length ? (
            <div
              className="space-y-1 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
              role="status"
            >
              <p className="flex items-center gap-1.5 font-medium">
                <AlertTriangle className="size-4" aria-hidden />
                มีผู้เข้าร่วมไม่ว่างในช่วงเวลานี้
              </p>
              <ul className="list-disc pl-5 text-xs">
                {shown.map((c, i) => (
                  <li key={`${c.user_id}-${i}`}>
                    {c.display_name}: {c.detail}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="m-reminder">แจ้งเตือนก่อนเริ่ม</Label>
              <select
                id="m-reminder"
                value={reminder}
                onChange={(e) => setReminder(Number(e.target.value))}
                className="border-input bg-background h-9 w-full rounded-lg border px-2.5 text-sm"
              >
                <option value={0}>ไม่แจ้งเตือน</option>
                <option value={5}>5 นาที</option>
                <option value={15}>15 นาที</option>
                <option value={30}>30 นาที</option>
                <option value={60}>1 ชั่วโมง</option>
                <option value={1440}>1 วัน</option>
              </select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="m-desc">รายละเอียด / วาระ</Label>
            <Textarea
              id="m-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={5000}
            />
          </div>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            ยกเลิก
          </Button>
          <Button
            type="submit"
            form="meeting-form"
            disabled={save.isPending || !title.trim() || !validTime}
          >
            {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {initial ? "บันทึก" : "นัดประชุม"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Meeting detail -----------------------------------------------------------------------

function MeetingDetail({
  id,
  onClose,
  onEdit,
}: {
  id: string;
  onClose: () => void;
  onEdit: (m: Meeting) => void;
}) {
  const client = useQueryClient();
  const meeting = useQuery({
    queryKey: calendarQueryKeys.meeting(id),
    queryFn: ({ signal }) => getMeeting(id, signal),
  });
  const refresh = () => client.invalidateQueries({ queryKey: calendarQueryKeys.all });
  const answer = useMutation({
    mutationFn: (r: Exclude<MeetingResponse, "PENDING">) => respondMeeting(id, r),
    onSuccess: async () => {
      await refresh();
      toast.success("ตอบรับแล้ว");
    },
    onError: (error) => toast.error(errorText(error, "ตอบรับไม่สำเร็จ")),
  });
  const cancel = useMutation({
    mutationFn: () => cancelMeeting(id),
    onSuccess: async () => {
      await refresh();
      toast.success("ยกเลิกการประชุมและแจ้งผู้เข้าร่วมแล้ว");
    },
    onError: (error) => toast.error(errorText(error, "ยกเลิกไม่สำเร็จ")),
  });
  const m = meeting.data;
  return (
    <Dialog open onOpenChange={(open) => (!open ? onClose() : undefined)}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-lg">
        {meeting.isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : meeting.isError || !m ? (
          <p className="text-sm">{errorText(meeting.error, "ไม่พบการประชุมนี้")}</p>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className={cn(m.cancelled && "line-through")}>{m.title}</DialogTitle>
              <DialogDescription>
                {m.cancelled ? "การประชุมนี้ถูกยกเลิกแล้ว · " : ""}
                โดย {m.organizer?.display_name ?? "—"}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3 text-sm">
              <p className="flex items-center gap-2">
                <Clock className="text-muted-foreground size-4" aria-hidden />
                {longDay(dayKey(m.start_at))} · {formatTime(m.start_at)}–{formatTime(m.end_at)} น.
              </p>
              {m.location ? (
                <p className="flex items-center gap-2">
                  <MapPin className="text-muted-foreground size-4" aria-hidden />
                  {m.location}
                </p>
              ) : null}
              {m.online_url ? (
                <p className="flex items-center gap-2">
                  <Link2 className="text-muted-foreground size-4" aria-hidden />
                  <a
                    href={m.online_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary break-all hover:underline"
                  >
                    เข้าร่วมประชุมออนไลน์
                  </a>
                </p>
              ) : null}
              {m.description ? (
                <p className="bg-muted/50 rounded-lg p-3 whitespace-pre-wrap">{m.description}</p>
              ) : null}
              <div className="space-y-1.5">
                <p className="font-medium">ผู้เข้าร่วม ({m.attendees.length})</p>
                <ul className="space-y-1">
                  {m.attendees.map((a) => (
                    <li key={a.id} className="flex items-center justify-between gap-2">
                      <span>
                        {a.display_name}
                        {a.is_organizer ? (
                          <span className="text-muted-foreground text-xs"> (ผู้จัด)</span>
                        ) : null}
                      </span>
                      <Badge
                        variant="outline"
                        className={cn(a.response === "DECLINED" && "text-muted-foreground")}
                      >
                        {RESPONSE_LABELS[a.response]}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            {!m.cancelled ? (
              <DialogFooter className="flex-wrap gap-2 sm:justify-between">
                {m.is_organizer ? (
                  <>
                    <Button
                      variant="outline"
                      disabled={cancel.isPending}
                      onClick={() => {
                        if (window.confirm("ยกเลิกการประชุมนี้และแจ้งผู้เข้าร่วมทุกคนใช่ไหม?"))
                          cancel.mutate();
                      }}
                    >
                      ยกเลิกการประชุม
                    </Button>
                    <Button onClick={() => onEdit(m)}>
                      <Pencil aria-hidden />
                      แก้ไข
                    </Button>
                  </>
                ) : (
                  <div className="flex flex-wrap gap-2" role="group" aria-label="ตอบรับการประชุม">
                    {(["ACCEPTED", "TENTATIVE", "DECLINED"] as const).map((r) => (
                      <Button
                        key={r}
                        size="sm"
                        variant={m.my_response === r ? "default" : "outline"}
                        aria-pressed={m.my_response === r}
                        disabled={answer.isPending}
                        onClick={() => answer.mutate(r)}
                      >
                        {RESPONSE_LABELS[r]}
                      </Button>
                    ))}
                  </div>
                )}
              </DialogFooter>
            ) : null}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// --- Page ---------------------------------------------------------------------------------

export function CalendarView() {
  const { me } = useSession();
  const params = useSearchParams();
  const router = useRouter();
  const today = new Date();
  const [cursor, setCursor] = useState({ year: today.getFullYear(), month: today.getMonth() });
  const [selected, setSelected] = useState(isoDate(today));
  const [form, setForm] = useState<{ initial: Meeting | null } | null>(null);
  const openId = params.get("meeting");

  const grid = useMemo(() => monthGrid(cursor.year, cursor.month), [cursor]);
  const start = isoDate(grid[0]);
  const end = isoDate(grid[grid.length - 1]);
  const feed = useQuery({
    queryKey: calendarQueryKeys.events(start, end),
    queryFn: ({ signal }) => getCalendar(start, end, signal),
  });

  const byDay = useMemo(() => {
    const map = new Map<string, { meetings: Meeting[]; leave: LeaveEvent[] }>();
    const slot = (k: string) => {
      if (!map.has(k)) map.set(k, { meetings: [], leave: [] });
      return map.get(k)!;
    };
    for (const m of feed.data?.meetings ?? [])
      for (const k of meetingDays(m)) slot(k).meetings.push(m);
    for (const l of feed.data?.leave ?? []) {
      for (
        let d = new Date(`${l.start_date}T00:00:00`);
        isoDate(d) <= l.end_date;
        d.setDate(d.getDate() + 1)
      ) {
        if (d.getDay() !== 0 && d.getDay() !== 6) slot(isoDate(d)).leave.push(l);
      }
    }
    return map;
  }, [feed.data]);

  const monthName = new Intl.DateTimeFormat("th-TH", { month: "long", year: "numeric" }).format(
    new Date(cursor.year, cursor.month, 1),
  );
  const move = (by: number) =>
    setCursor(({ year, month }) => ({
      year: month + by < 0 ? year - 1 : month + by > 11 ? year + 1 : year,
      month: (month + by + 12) % 12,
    }));
  const openMeeting = (id: string | null) =>
    router.replace(id ? `/calendar?meeting=${id}` : "/calendar");
  const day = byDay.get(selected);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">ปฏิทิน</h1>
          <p className="text-muted-foreground text-sm">การประชุมของคุณ และวันลาของคนในทีม</p>
        </div>
        <Button onClick={() => setForm({ initial: null })}>
          <Plus aria-hidden />
          นัดประชุม
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" aria-label="เดือนก่อน" onClick={() => move(-1)}>
          <ChevronLeft aria-hidden />
        </Button>
        <span className="min-w-40 text-center font-medium">{monthName}</span>
        <Button variant="outline" size="icon" aria-label="เดือนถัดไป" onClick={() => move(1)}>
          <ChevronRight aria-hidden />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setCursor({ year: today.getFullYear(), month: today.getMonth() });
            setSelected(isoDate(today));
          }}
        >
          วันนี้
        </Button>
        <span className="text-muted-foreground ml-auto hidden items-center gap-3 text-xs md:flex">
          <span className="flex items-center gap-1">
            <span className="bg-primary size-2.5 rounded-sm" />
            เข้าร่วม
          </span>
          <span className="flex items-center gap-1">
            <span className="border-primary/60 size-2.5 rounded-sm border border-dashed" />
            ยังไม่ตอบ
          </span>
          <span className="flex items-center gap-1">
            <span className="size-2.5 rounded-sm bg-emerald-200" />
            ลา
          </span>
        </span>
      </div>

      {feed.isError ? (
        <ErrorState
          message={errorText(feed.error, "โหลดปฏิทินไม่สำเร็จ")}
          onRetry={() => void feed.refetch()}
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="bg-card overflow-hidden rounded-xl border">
            <div className="bg-muted/50 grid grid-cols-7 border-b text-center text-xs font-medium">
              {WEEKDAYS.map((w) => (
                <div key={w} className="py-2">
                  {w}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7">
              {grid.map((d) => {
                const key = isoDate(d);
                const items = byDay.get(key);
                const inMonth = d.getMonth() === cursor.month;
                const isToday = key === isoDate(today);
                const count = (items?.meetings.length ?? 0) + (items?.leave.length ?? 0);
                return (
                  <div
                    key={key}
                    role="button"
                    tabIndex={0}
                    aria-label={`${longDay(key)}${count ? ` มี ${count} รายการ` : ""}`}
                    aria-pressed={selected === key}
                    onClick={() => setSelected(key)}
                    onKeyDown={(e) =>
                      e.key === "Enter" || e.key === " " ? setSelected(key) : undefined
                    }
                    className={cn(
                      "hover:bg-accent/40 min-h-20 cursor-pointer space-y-0.5 border-r border-b p-1 text-left last:border-r-0 sm:min-h-24",
                      !inMonth && "bg-muted/30 text-muted-foreground",
                      selected === key && "ring-primary ring-2 ring-inset",
                    )}
                  >
                    <span
                      className={cn(
                        "inline-flex size-6 items-center justify-center rounded-full text-xs",
                        isToday && "bg-primary text-primary-foreground font-semibold",
                      )}
                    >
                      {d.getDate()}
                    </span>
                    <div className="hidden space-y-0.5 sm:block">
                      {items?.meetings.slice(0, 2).map((m) => (
                        <MeetingChip key={m.id} m={m} onOpen={() => openMeeting(m.id)} />
                      ))}
                      {items?.leave
                        .slice(
                          0,
                          items.meetings.length >= 2 ? 0 : 2 - (items?.meetings.length ?? 0),
                        )
                        .map((l) => (
                          <LeaveChip key={l.id} l={l} />
                        ))}
                      {count > 2 ? (
                        <span className="text-muted-foreground block text-[11px]">
                          +{count - 2} รายการ
                        </span>
                      ) : null}
                    </div>
                    {count ? (
                      <span
                        className="bg-primary mx-auto block size-1.5 rounded-full sm:hidden"
                        aria-hidden
                      />
                    ) : null}
                  </div>
                );
              })}
            </div>
            {feed.isPending ? (
              <p className="text-muted-foreground p-2 text-xs">กำลังโหลด…</p>
            ) : null}
          </div>

          <aside className="space-y-3" aria-label="รายการของวันที่เลือก">
            <h2 className="font-medium">{longDay(selected)}</h2>
            {!day || (day.meetings.length === 0 && day.leave.length === 0) ? (
              <div className="text-muted-foreground flex flex-col items-center gap-2 rounded-xl border border-dashed p-6 text-center text-sm">
                <CalendarDays className="size-6" aria-hidden />
                ไม่มีนัดหมายในวันนี้
              </div>
            ) : (
              <ul className="space-y-2">
                {day.meetings.map((m) => (
                  <li key={m.id}>
                    <button
                      type="button"
                      onClick={() => openMeeting(m.id)}
                      className="hover:bg-accent/50 w-full rounded-xl border p-3 text-left"
                    >
                      <span
                        className={cn("block text-sm font-medium", m.cancelled && "line-through")}
                      >
                        {m.title}
                      </span>
                      <span className="text-muted-foreground block text-xs">
                        {formatTime(m.start_at)}–{formatTime(m.end_at)} น.
                        {m.location ? ` · ${m.location}` : ""}
                      </span>
                      <span className="mt-1 flex flex-wrap gap-1">
                        {m.cancelled ? <Badge variant="outline">ยกเลิกแล้ว</Badge> : null}
                        {!m.is_organizer && m.my_response ? (
                          <Badge variant="outline">{RESPONSE_LABELS[m.my_response]}</Badge>
                        ) : null}
                        {m.is_organizer ? <Badge variant="secondary">คุณเป็นผู้จัด</Badge> : null}
                      </span>
                    </button>
                  </li>
                ))}
                {day.leave.map((l) => (
                  <li
                    key={l.id}
                    className={cn(
                      "rounded-xl px-3 py-2 text-sm",
                      LEAVE_COLORS[l.color] ?? LEAVE_COLORS.blue,
                    )}
                  >
                    {l.person_name} · {l.leave_type}
                    {l.half_day === "MORNING"
                      ? " (ครึ่งเช้า)"
                      : l.half_day === "AFTERNOON"
                        ? " (ครึ่งบ่าย)"
                        : ""}
                  </li>
                ))}
              </ul>
            )}
            <Button variant="outline" className="w-full" onClick={() => setForm({ initial: null })}>
              <Plus aria-hidden />
              นัดประชุมวันนี้
            </Button>
          </aside>
        </div>
      )}

      {form ? (
        <MeetingForm
          key={form.initial?.id ?? `new-${selected}`}
          initial={form.initial}
          day={selected}
          myId={me?.user.id}
          onClose={() => setForm(null)}
        />
      ) : null}
      {openId && !form ? (
        <MeetingDetail
          id={openId}
          onClose={() => openMeeting(null)}
          onEdit={(m) => {
            openMeeting(null);
            setForm({ initial: m });
          }}
        />
      ) : null}
    </div>
  );
}
