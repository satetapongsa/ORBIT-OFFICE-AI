"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Loader2,
  NotebookPen,
  Plus,
  Save,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/features/auth/hooks/use-session";
import { formatDateTime, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import {
  createNote,
  deleteNote,
  getNote,
  listNotes,
  NOTE_MAX_CHARS,
  noteQueryKeys,
  summariseNote,
  updateNote,
  type Note,
} from "@/services/notes";

function errorText(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  const detail = error.details.map((d) => d.message).join(" ");
  return detail ? `${error.message}: ${detail}` : error.message;
}

function Editor({ note, onClosed }: { note: Note; onClosed: () => void }) {
  const client = useQueryClient();
  const { has } = useSession();
  const [title, setTitle] = useState(note.title);
  const [content, setContent] = useState(note.content);
  const dirty = title !== note.title || content !== note.content;

  const refresh = (saved: Note) => {
    client.setQueryData(noteQueryKeys.detail(saved.id), saved);
    return client.invalidateQueries({ queryKey: ["notes", "list"] });
  };

  const save = useMutation({
    mutationFn: () => updateNote(note.id, { title: title.trim(), content }),
    onSuccess: async (saved) => {
      await refresh(saved);
      toast.success("บันทึกโน้ตแล้ว");
    },
    onError: (error) => toast.error(errorText(error, "บันทึกไม่สำเร็จ")),
  });

  const remove = useMutation({
    mutationFn: () => deleteNote(note.id),
    onSuccess: async () => {
      client.removeQueries({ queryKey: noteQueryKeys.detail(note.id) });
      await client.invalidateQueries({ queryKey: ["notes", "list"] });
      toast.success("ลบโน้ตแล้ว");
      onClosed();
    },
    onError: (error) => toast.error(errorText(error, "ลบไม่สำเร็จ")),
  });

  const summary = useMutation({
    mutationFn: async () => {
      // Summarise what is on screen: save unsaved edits first.
      if (dirty) await refresh(await updateNote(note.id, { title: title.trim(), content }));
      return summariseNote(note.id);
    },
    onSuccess: refresh,
    onError: (error) => toast.error(errorText(error, "สรุปด้วย AI ไม่สำเร็จ")),
  });

  const busy = save.isPending || remove.isPending || summary.isPending;
  const canSummarise = has("ai:chat");

  return (
    <section aria-label="แก้ไขโน้ต" className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onClosed}
          aria-label="กลับไปรายการโน้ต"
        >
          <ArrowLeft aria-hidden />
        </Button>
        <span className="text-muted-foreground text-xs">
          แก้ไขล่าสุด {formatDateTime(note.content_updated_at)}
        </span>
        <div className="ml-auto flex flex-wrap gap-2">
          {canSummarise ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => summary.mutate()}
              disabled={busy || !content.trim()}
            >
              {summary.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <Sparkles aria-hidden />
              )}
              สรุปด้วย AI
            </Button>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              if (window.confirm(`ลบโน้ต “${note.title}” ใช่ไหม? ลบแล้วกู้คืนไม่ได้`))
                remove.mutate();
            }}
            disabled={busy}
          >
            <Trash2 aria-hidden />
            ลบ
          </Button>
          <Button
            size="sm"
            onClick={() => save.mutate()}
            disabled={busy || !dirty || !title.trim()}
          >
            {save.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Save aria-hidden />
            )}
            บันทึก
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {note.ai_summary ? (
          <div className="bg-primary/5 border-primary/20 space-y-2 rounded-xl border p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Sparkles className="text-primary size-4" aria-hidden />
              <span className="text-sm font-medium">สรุปโดย AI</span>
              {note.ai_summary_at ? (
                <span className="text-muted-foreground text-xs">
                  {formatRelative(note.ai_summary_at)}
                </span>
              ) : null}
              {note.summary_outdated ? (
                <Badge variant="outline" className="text-amber-700">
                  โน้ตถูกแก้หลังสรุป กดสรุปใหม่ได้
                </Badge>
              ) : null}
            </div>
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{note.ai_summary}</p>
          </div>
        ) : null}
        <Input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={200}
          placeholder="หัวข้อโน้ต"
          aria-label="หัวข้อโน้ต"
          className="text-base font-medium"
        />
        <Textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          maxLength={NOTE_MAX_CHARS}
          placeholder="เขียนโน้ตของคุณที่นี่…"
          aria-label="เนื้อหาโน้ต"
          className="min-h-[18rem] leading-relaxed"
        />
        <p className="text-muted-foreground text-right text-xs">
          {content.length.toLocaleString("th-TH")} / {NOTE_MAX_CHARS.toLocaleString("th-TH")}
          {dirty ? " · ยังไม่ได้บันทึก" : ""}
        </p>
      </div>
    </section>
  );
}

function EditorPane({ id, onClosed }: { id: string; onClosed: () => void }) {
  const note = useQuery({
    queryKey: noteQueryKeys.detail(id),
    queryFn: ({ signal }) => getNote(id, signal),
  });
  if (note.isPending) {
    return (
      <div className="space-y-3 p-4" aria-busy="true">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }
  if (note.isError) {
    return (
      <div className="p-4">
        {note.error instanceof ApiError && note.error.status === 404 ? (
          <Alert>
            <AlertDescription>ไม่พบโน้ตนี้ อาจถูกลบไปแล้ว</AlertDescription>
          </Alert>
        ) : (
          <ErrorState
            message={errorText(note.error, "โหลดโน้ตไม่สำเร็จ")}
            onRetry={() => void note.refetch()}
            retrying={note.isFetching}
          />
        )}
      </div>
    );
  }
  // Remount when the saved version changes so the form starts from the stored text.
  return (
    <Editor
      key={`${note.data.id}:${note.data.content_updated_at}`}
      note={note.data}
      onClosed={onClosed}
    />
  );
}

export function NotesView() {
  const params = useSearchParams();
  const router = useRouter();
  const client = useQueryClient();
  const selectedId = params.get("n");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const notes = useQuery({
    queryKey: noteQueryKeys.list(query),
    queryFn: ({ signal }) => listNotes(query, signal),
  });

  const create = useMutation({
    mutationFn: () => createNote({ title: "โน้ตใหม่", content: "" }),
    onSuccess: async (note) => {
      client.setQueryData(noteQueryKeys.detail(note.id), note);
      await client.invalidateQueries({ queryKey: ["notes", "list"] });
      router.push(`/notes?n=${note.id}`);
    },
    onError: (error) => toast.error(errorText(error, "สร้างโน้ตไม่สำเร็จ")),
  });

  const items = notes.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">โน้ตของฉัน</h1>
          <p className="text-muted-foreground text-sm">
            จดบันทึกงานส่วนตัว เห็นได้เฉพาะคุณคนเดียว และให้ AI ช่วยสรุปได้
          </p>
        </div>
        <Button onClick={() => create.mutate()} disabled={create.isPending}>
          {create.isPending ? (
            <Loader2 className="animate-spin" aria-hidden />
          ) : (
            <Plus aria-hidden />
          )}
          โน้ตใหม่
        </Button>
      </div>

      <div className="bg-card grid h-[calc(100dvh-14rem)] min-h-[28rem] overflow-hidden rounded-xl border lg:grid-cols-[20rem_minmax(0,1fr)]">
        <aside
          aria-label="รายการโน้ต"
          className={cn("flex min-h-0 flex-col border-r", selectedId ? "hidden lg:flex" : "flex")}
        >
          <div className="relative border-b p-2">
            <Search
              className="text-muted-foreground pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2"
              aria-hidden
            />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="ค้นหาโน้ต"
              aria-label="ค้นหาโน้ต"
              className="pl-8"
            />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {notes.isPending ? (
              <div className="space-y-2 p-2" aria-busy="true">
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
              </div>
            ) : notes.isError ? (
              <ErrorState
                message={errorText(notes.error, "โหลดโน้ตไม่สำเร็จ")}
                onRetry={() => void notes.refetch()}
                retrying={notes.isFetching}
              />
            ) : items.length === 0 ? (
              <EmptyState
                icon={NotebookPen}
                title={query ? "ไม่พบโน้ตที่ค้นหา" : "ยังไม่มีโน้ต"}
                description={query ? undefined : "กด “โน้ตใหม่” เพื่อเริ่มจดบันทึก"}
              />
            ) : (
              <ul className="space-y-1">
                {items.map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      onClick={() => router.push(`/notes?n=${n.id}`)}
                      aria-current={n.id === selectedId ? "true" : undefined}
                      className={cn(
                        "w-full rounded-lg px-3 py-2.5 text-left transition-colors",
                        n.id === selectedId ? "bg-accent" : "hover:bg-accent/60",
                      )}
                    >
                      <span className="flex items-center gap-1.5">
                        <span className="truncate text-sm font-medium">{n.title}</span>
                        {n.has_summary ? (
                          <Sparkles
                            className="text-primary size-3.5 shrink-0"
                            aria-label="มีสรุป AI"
                          />
                        ) : null}
                      </span>
                      <span className="text-muted-foreground block truncate text-xs">
                        {n.preview || "ยังไม่มีเนื้อหา"}
                      </span>
                      <span className="text-muted-foreground block text-[11px]">
                        {formatRelative(n.content_updated_at)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        <div className={cn("min-h-0", selectedId ? "block" : "hidden lg:block")}>
          {selectedId ? (
            <EditorPane id={selectedId} onClosed={() => router.push("/notes")} />
          ) : (
            <div className="text-muted-foreground flex h-full items-center justify-center p-6 text-center text-sm">
              เลือกโน้ตทางซ้าย หรือกด “โน้ตใหม่”
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
