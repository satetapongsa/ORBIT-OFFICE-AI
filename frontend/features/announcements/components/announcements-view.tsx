"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCheck,
  Loader2,
  Megaphone,
  Pencil,
  Pin,
  Plus,
  Trash2,
  Users,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/empty-state";
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
import { formatDateTime, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  ANNOUNCEMENT_BODY_MAX_CHARS,
  announcementQueryKeys,
  createAnnouncement,
  deleteAnnouncement,
  listAnnouncements,
  markAllAnnouncementsRead,
  markAnnouncementRead,
  updateAnnouncement,
  type Announcement,
  type AnnouncementInput,
} from "@/services/announcements";
import { ApiError } from "@/services/api-client";
import { listDepartments } from "@/services/documents";

function errorText(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  const detail = error.details.map((d) => d.message).join(" ");
  return detail ? `${error.message}: ${detail}` : error.message;
}

/** `datetime-local` value (local time) ⇄ ISO string. */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function AnnouncementForm({
  initial,
  open,
  onOpenChange,
}: {
  initial: Announcement | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const client = useQueryClient();
  const departments = useQuery({
    queryKey: ["departments", "list"],
    queryFn: ({ signal }) => listDepartments(signal),
    enabled: open,
  });
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [important, setImportant] = useState(initial?.important ?? false);
  const [pinned, setPinned] = useState(initial?.pinned ?? false);
  const [department, setDepartment] = useState(initial?.department_id ?? "");
  const [expires, setExpires] = useState(toLocalInput(initial?.expires_at ?? null));
  const [notify, setNotify] = useState(true);

  const save = useMutation({
    mutationFn: () => {
      const input: AnnouncementInput = {
        title: title.trim(),
        body: body.trim(),
        important,
        pinned,
        department_id: department || null,
        expires_at: expires ? new Date(expires).toISOString() : null,
        notify,
      };
      return initial ? updateAnnouncement(initial.id, input) : createAnnouncement(input);
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: announcementQueryKeys.all });
      toast.success(initial ? "บันทึกการแก้ไขแล้ว" : "เผยแพร่ประกาศแล้ว");
      onOpenChange(false);
    },
    onError: (error) => toast.error(errorText(error, "บันทึกประกาศไม่สำเร็จ")),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim() || !body.trim()) return;
    save.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{initial ? "แก้ไขประกาศ" : "สร้างประกาศ"}</DialogTitle>
          <DialogDescription>
            ประกาศจะแสดงในหน้าประกาศและแดชบอร์ดของผู้ที่เกี่ยวข้อง
          </DialogDescription>
        </DialogHeader>
        <form id="announcement-form" className="space-y-4" onSubmit={submit}>
          <div className="space-y-1.5">
            <Label htmlFor="a-title">หัวข้อ</Label>
            <Input
              id="a-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              required
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="a-body">รายละเอียด</Label>
            <Textarea
              id="a-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={ANNOUNCEMENT_BODY_MAX_CHARS}
              className="min-h-40 leading-relaxed"
              required
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="a-audience">ผู้รับประกาศ</Label>
              <select
                id="a-audience"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="border-input bg-background h-9 w-full rounded-lg border px-2.5 text-sm"
              >
                <option value="">ทั้งบริษัท</option>
                {(departments.data ?? []).map((d) => (
                  <option key={d.id} value={d.id}>
                    เฉพาะ{d.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="a-expires">หมดอายุ (ไม่บังคับ)</Label>
              <Input
                id="a-expires"
                type="datetime-local"
                value={expires}
                onChange={(e) => setExpires(e.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={important}
                onChange={(e) => setImportant(e.target.checked)}
              />
              ประกาศสำคัญ
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={pinned}
                onChange={(e) => setPinned(e.target.checked)}
              />
              ปักหมุดไว้ด้านบน
            </label>
            {initial ? null : (
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={notify}
                  onChange={(e) => setNotify(e.target.checked)}
                />
                แจ้งเตือนทุกคนที่เกี่ยวข้อง
              </label>
            )}
          </div>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            ยกเลิก
          </Button>
          <Button
            type="submit"
            form="announcement-form"
            disabled={save.isPending || !title.trim() || !body.trim()}
          >
            {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {initial ? "บันทึก" : "เผยแพร่"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AnnouncementCard({
  item,
  open,
  onToggle,
  canManage,
  onEdit,
}: {
  item: Announcement;
  open: boolean;
  onToggle: () => void;
  canManage: boolean;
  onEdit: () => void;
}) {
  const client = useQueryClient();
  const remove = useMutation({
    mutationFn: () => deleteAnnouncement(item.id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: announcementQueryKeys.all });
      toast.success("ลบประกาศแล้ว");
    },
    onError: (error) => toast.error(errorText(error, "ลบประกาศไม่สำเร็จ")),
  });
  const paragraphs = item.body.split(/\n{2,}/);
  return (
    <article
      id={`announcement-${item.id}`}
      className={cn(
        "bg-card rounded-xl border transition-shadow",
        item.important && "border-amber-300",
        !item.is_read && "ring-primary/30 shadow-sm ring-1",
        item.expired && "opacity-60",
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-start gap-3 p-4 text-left"
      >
        <span
          className={cn(
            "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full",
            item.important ? "bg-amber-100 text-amber-700" : "bg-primary/10 text-primary",
          )}
          aria-hidden
        >
          {item.important ? <AlertTriangle className="size-4" /> : <Megaphone className="size-4" />}
        </span>
        <span className="min-w-0 flex-1 space-y-1">
          <span className="flex flex-wrap items-center gap-1.5">
            {!item.is_read ? (
              <span className="bg-primary size-2 rounded-full" aria-label="ยังไม่อ่าน" />
            ) : null}
            <span className="font-medium">{item.title}</span>
            {item.pinned ? (
              <Badge variant="secondary" className="gap-1">
                <Pin className="size-3" aria-hidden />
                ปักหมุด
              </Badge>
            ) : null}
            {item.important ? (
              <Badge className="bg-amber-500 hover:bg-amber-500">สำคัญ</Badge>
            ) : null}
            {item.expired ? <Badge variant="outline">หมดอายุแล้ว</Badge> : null}
          </span>
          <span className="text-muted-foreground block text-xs">
            {item.author_name ?? "ระบบ"} · {formatRelative(item.published_at)}
            {item.department_name ? ` · เฉพาะ${item.department_name}` : " · ทั้งบริษัท"}
            {item.edited ? " · แก้ไขแล้ว" : ""}
          </span>
          {!open ? (
            <span className="text-muted-foreground line-clamp-2 block text-sm">{item.body}</span>
          ) : null}
        </span>
      </button>
      {open ? (
        <div className="space-y-4 px-4 pb-4 pl-16">
          <div className="space-y-3 text-sm leading-relaxed [overflow-wrap:anywhere]">
            {paragraphs.map((p, i) => (
              <p key={i} className="whitespace-pre-wrap">
                {p}
              </p>
            ))}
          </div>
          <p className="text-muted-foreground text-xs">
            ประกาศเมื่อ {formatDateTime(item.published_at)}
            {item.expires_at ? ` · หมดอายุ ${formatDateTime(item.expires_at)}` : ""}
          </p>
          {canManage ? (
            <div className="flex flex-wrap items-center gap-2 border-t pt-3">
              {item.read_count !== null && item.read_count !== undefined ? (
                <span className="text-muted-foreground mr-auto flex items-center gap-1 text-xs">
                  <Users className="size-3.5" aria-hidden />
                  อ่านแล้ว {item.read_count} จาก {item.audience_count ?? "?"} คน
                </span>
              ) : null}
              <Button variant="outline" size="sm" onClick={onEdit}>
                <Pencil aria-hidden />
                แก้ไข
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={remove.isPending}
                onClick={() => {
                  if (window.confirm(`ลบประกาศ “${item.title}” ใช่ไหม?`)) remove.mutate();
                }}
              >
                <Trash2 aria-hidden />
                ลบ
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

export function AnnouncementsView() {
  const { has } = useSession();
  const canManage = has("announcements:manage");
  const client = useQueryClient();
  const params = useSearchParams();
  const linked = params.get("id");
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [includeExpired, setIncludeExpired] = useState(false);
  const [openId, setOpenId] = useState<string | null>(linked);
  // A new notification link while the page is open: expand that announcement.
  const [seenLink, setSeenLink] = useState(linked);
  if (linked !== seenLink) {
    setSeenLink(linked);
    setOpenId(linked);
  }
  const [editing, setEditing] = useState<Announcement | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const list = useQuery({
    queryKey: announcementQueryKeys.list(includeExpired),
    queryFn: ({ signal }) => listAnnouncements(includeExpired, signal),
  });

  const read = useMutation({
    mutationFn: markAnnouncementRead,
    onSuccess: () => client.invalidateQueries({ queryKey: announcementQueryKeys.all }),
  });
  const readAll = useMutation({
    mutationFn: markAllAnnouncementsRead,
    onSuccess: () => client.invalidateQueries({ queryKey: announcementQueryKeys.all }),
  });

  // Opened from a notification link: expand it, scroll to it and mark it read.
  useEffect(() => {
    if (!linked || !list.data) return;
    const item = list.data.items.find((a) => a.id === linked);
    if (item && !item.is_read) read.mutate(linked);
    document.getElementById(`announcement-${linked}`)?.scrollIntoView({ block: "center" });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per link and data load
  }, [linked, list.data?.items.length]);

  function toggle(item: Announcement) {
    const next = openId === item.id ? null : item.id;
    setOpenId(next);
    if (next && !item.is_read) read.mutate(item.id);
  }

  const items = (list.data?.items ?? []).filter((a) => filter === "all" || !a.is_read);
  const unread = list.data?.unread_count ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">ประกาศบริษัท</h1>
          <p className="text-muted-foreground text-sm">
            ข่าวสารและประกาศจากบริษัท ประกาศที่ปักหมุดจะอยู่ด้านบนเสมอ
          </p>
        </div>
        {canManage ? (
          <Button
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            <Plus aria-hidden />
            สร้างประกาศ
          </Button>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={filter === "all" ? "default" : "outline"}
          onClick={() => setFilter("all")}
        >
          ทั้งหมด
        </Button>
        <Button
          size="sm"
          variant={filter === "unread" ? "default" : "outline"}
          onClick={() => setFilter("unread")}
        >
          ยังไม่อ่าน{unread ? ` (${unread})` : ""}
        </Button>
        {canManage ? (
          <label className="text-muted-foreground ml-1 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={includeExpired}
              onChange={(e) => setIncludeExpired(e.target.checked)}
            />
            แสดงประกาศที่หมดอายุ
          </label>
        ) : null}
        {unread ? (
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            onClick={() => readAll.mutate()}
            disabled={readAll.isPending}
          >
            <CheckCheck aria-hidden />
            อ่านทั้งหมด
          </Button>
        ) : null}
      </div>

      {list.isPending ? (
        <div className="space-y-3" aria-busy="true">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      ) : list.isError ? (
        <ErrorState
          message={errorText(list.error, "โหลดประกาศไม่สำเร็จ")}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Megaphone}
          title={filter === "unread" ? "อ่านครบทุกประกาศแล้ว" : "ยังไม่มีประกาศ"}
          description={
            canManage && filter === "all" ? "กด “สร้างประกาศ” เพื่อแจ้งข่าวถึงพนักงาน" : undefined
          }
        />
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <AnnouncementCard
              key={item.id}
              item={item}
              open={openId === item.id}
              onToggle={() => toggle(item)}
              canManage={canManage}
              onEdit={() => {
                setEditing(item);
                setFormOpen(true);
              }}
            />
          ))}
        </div>
      )}

      {formOpen ? (
        <AnnouncementForm
          key={editing?.id ?? "new"}
          initial={editing}
          open={formOpen}
          onOpenChange={setFormOpen}
        />
      ) : null}
    </div>
  );
}
